#!/usr/bin/env python3
"""Executa fixtures douradas do contrato CLI no backend explícito."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from _cli_contract import FIXTURES, ROOT


PYTHON_ENGINE = ROOT / "scripts" / "bm.py"


def _safe_relative(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or ".planning" in path.parts:
        raise ValueError(f"path de fixture inválido: {value}")
    return path


def _bytes(specification: dict[str, Any]) -> bytes:
    if "text" in specification:
        return specification["text"].encode("utf-8")
    return base64.b64decode(specification["base64"], validate=True)


def _tree(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".planning" not in path.parts
    }


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _replace(value: str, repo: Path, temp: Path) -> str:
    return (
        value.replace(str(repo), "{repo}")
        .replace(str(temp), "{tmp}")
        .replace(str(ROOT), "{method_root}")
    )


def _normalize_json(value: Any, repo: Path, temp: Path) -> Any:
    if isinstance(value, dict):
        return {key: _normalize_json(item, repo, temp) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_json(item, repo, temp) for item in value]
    if isinstance(value, str):
        return _replace(value, repo, temp)
    return value


def _normalize_stderr(stderr: str, repo: Path, temp: Path) -> str:
    normalized = _replace(stderr, repo, temp)
    if "usage: bm" not in normalized:
        return normalized
    last = normalized.rstrip().splitlines()[-1]
    if last.startswith("bm: error: argument command: invalid choice:"):
        marker = " (choose from "
        if marker in last:
            last = last.split(marker, 1)[0]
    return f"ARGPARSE: {last}\n"


def _mutation(before: dict[str, bytes], after: dict[str, bytes]) -> dict[str, Any]:
    created = set(after) - set(before)
    deleted = set(before) - set(after)
    altered = sorted(path for path in set(before) & set(after) if before[path] != after[path])
    preserved = sorted(path for path in set(before) & set(after) if before[path] == after[path])
    moved: list[dict[str, str]] = []
    for source in sorted(deleted):
        matches = [target for target in sorted(created) if before[source] == after[target]]
        if len(matches) == 1:
            target = matches[0]
            moved.append({"from": source, "to": target})
            created.remove(target)
            deleted.remove(source)
    return {
        "created": sorted(created),
        "altered": altered,
        "deleted": sorted(deleted),
        "moved": moved,
        "preserved": preserved,
    }


def _engine_command(engine: str, binary: Path | None) -> list[str]:
    if engine == "python":
        return [sys.executable, str(PYTHON_ENGINE)]
    executable = binary or ROOT / "bin" / "bm-preview"
    if not executable.is_file():
        raise FileNotFoundError(f"backend Go explícito ausente: {executable}")
    return [str(executable)]


def _expand_tokens(tokens: list[str], repo: Path, temp: Path) -> list[str]:
    replacements = {
        "{repo}": str(repo),
        "{tmp}": str(temp),
        "{method_root}": str(ROOT),
    }
    expanded: list[str] = []
    for token in tokens:
        for marker, value in replacements.items():
            token = token.replace(marker, value)
        expanded.append(token)
    return expanded


def run_fixture(path: Path, engine: str, binary: Path | None) -> list[str]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="bm-cli-contract-") as temporary:
        temp = Path(temporary)
        repo = temp / "repo"
        repo.mkdir()
        for relative, specification in fixture.get("initial_tree", {}).items():
            destination = repo / _safe_relative(relative)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(_bytes(specification))
            if "mode" in specification:
                destination.chmod(int(specification["mode"], 8))
        before = _tree(repo)
        argv = _expand_tokens(fixture["argv"], repo, temp)
        completed = subprocess.run(
            [*_engine_command(engine, binary), *argv],
            cwd=repo,
            text=True,
            capture_output=True,
            check=False,
            env={
                **os.environ,
                "COLUMNS": "200",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
        after = _tree(repo)
        expected = fixture["expected"]
        if completed.returncode != expected["exit_code"]:
            errors.append(f"exit {completed.returncode} != {expected['exit_code']}")

        stdout_contract = expected["stdout"]
        if stdout_contract["kind"] == "json":
            try:
                actual_stdout = _normalize_json(json.loads(completed.stdout), repo, temp)
            except json.JSONDecodeError as error:
                errors.append(f"stdout não é JSON: {error}")
            else:
                if actual_stdout != stdout_contract["value"]:
                    errors.append(
                        "stdout JSON divergiu: "
                        + json.dumps(actual_stdout, ensure_ascii=False, sort_keys=True)
                    )
        elif stdout_contract["kind"] == "text":
            actual_stdout = _replace(completed.stdout, repo, temp)
            if actual_stdout != stdout_contract["value"]:
                errors.append(f"stdout texto divergiu: {actual_stdout!r}")
        elif completed.stdout:
            errors.append(f"stdout deveria estar vazio: {completed.stdout!r}")

        actual_stderr = _normalize_stderr(completed.stderr, repo, temp)
        if actual_stderr != expected["stderr"]:
            errors.append(f"stderr divergiu: {actual_stderr!r}")

        mutation = _mutation(before, after)
        expected_mutation = expected["mutations"]
        for key in ("created", "altered", "deleted", "moved"):
            if mutation[key] != expected_mutation.get(key, []):
                errors.append(f"{key} divergiu: {mutation[key]!r}")
        missing_preserved = sorted(
            set(expected_mutation.get("preserved", [])) - set(mutation["preserved"])
        )
        if missing_preserved:
            errors.append(f"preservados divergiram: ausentes {missing_preserved!r}")
        for relative, specification in expected.get("files", {}).items():
            checked = repo / _safe_relative(relative)
            if not checked.is_file():
                errors.append(f"arquivo esperado ausente: {relative}")
            elif checked.read_bytes() != _bytes(specification):
                errors.append(f"bytes divergentes: {relative} ({_digest(checked.read_bytes())})")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", choices=["python", "go"], required=True)
    parser.add_argument("--binary", type=Path)
    args = parser.parse_args()
    fixture_paths = sorted(FIXTURES.glob("*.json"))
    failures: dict[str, list[str]] = {}
    for path in fixture_paths:
        errors = run_fixture(path, args.engine, args.binary)
        if errors:
            failures[path.stem] = errors
    result = {
        "engine": args.engine,
        "total": len(fixture_paths),
        "passed": len(fixture_paths) - len(failures),
        "failed": len(failures),
        "failures": failures,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
