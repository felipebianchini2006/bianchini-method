#!/usr/bin/env python3
"""Executa fixtures douradas do contrato CLI no backend explícito."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from _cli_contract import FIXTURES, ROOT


PYTHON_ENGINE = ROOT / "scripts" / "bm_python_oracle.py"
FIXED_GIT_ENV = {
    "GIT_AUTHOR_DATE": "2000-01-01T00:00:00Z",
    "GIT_COMMITTER_DATE": "2000-01-01T00:00:00Z",
}
ISO_TIMESTAMP = re.compile(
    r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})\b"
)


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
        if path.is_file()
        and ".git" not in path.relative_to(root).parts
        and ".planning" not in path.parts
    }


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _replace(value: str, repo: Path, temp: Path) -> str:
    replacements = (
        (repo.resolve(), "{repo}"),
        (repo, "{repo}"),
        (temp.resolve(), "{tmp}"),
        (temp, "{tmp}"),
        (ROOT.resolve(), "{method_root}"),
        (ROOT, "{method_root}"),
    )
    normalized = value
    for source, marker in replacements:
        normalized = normalized.replace(str(source), marker)
    return normalized


def _normalize_text(value: str, repo: Path, temp: Path) -> str:
    return ISO_TIMESTAMP.sub("{timestamp}", _replace(value, repo, temp))


def _normalize_json(value: Any, repo: Path, temp: Path) -> Any:
    if isinstance(value, dict):
        return {key: _normalize_json(item, repo, temp) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_json(item, repo, temp) for item in value]
    if isinstance(value, str):
        return _normalize_text(value, repo, temp)
    return value


def _json_matches(actual: Any, expected: Any) -> bool:
    if expected == "{sha256}":
        return isinstance(actual, str) and re.fullmatch(r"[0-9a-f]{64}", actual) is not None
    if expected == "{git_sha}":
        return isinstance(actual, str) and re.fullmatch(r"[0-9a-f]{40}", actual) is not None
    if isinstance(expected, dict):
        return (
            isinstance(actual, dict)
            and actual.keys() == expected.keys()
            and all(_json_matches(actual[key], value) for key, value in expected.items())
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(actual) == len(expected)
            and all(_json_matches(left, right) for left, right in zip(actual, expected))
        )
    return actual == expected


def _normalize_stderr(stderr: str, repo: Path, temp: Path) -> str:
    normalized = _normalize_text(stderr, repo, temp)
    return normalized


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
    executable = binary or ROOT / "bin" / "bm"
    if not executable.is_file():
        raise FileNotFoundError(f"backend Go explícito ausente: {executable}")
    return [str(executable)]


def _expand_tokens(
    tokens: list[str],
    repo: Path,
    temp: Path,
    captured: dict[str, str] | None = None,
) -> list[str]:
    replacements = {
        "{repo}": str(repo),
        "{tmp}": str(temp),
        "{method_root}": str(ROOT),
        **{f"{{{key}}}": value for key, value in (captured or {}).items()},
    }
    expanded: list[str] = []
    for token in tokens:
        for marker, value in replacements.items():
            token = token.replace(marker, value)
        expanded.append(token)
    return expanded


def _write_tree(
    repo: Path,
    tree: dict[str, dict[str, Any]],
    temp: Path,
    captured: dict[str, str],
) -> None:
    for relative, specification in tree.items():
        destination = repo / _safe_relative(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if "text" in specification:
            value = _expand_tokens(
                [specification["text"]], repo, temp, captured
            )[0].encode("utf-8")
        else:
            value = _bytes(specification)
        destination.write_bytes(value)
        if "mode" in specification:
            destination.chmod(int(specification["mode"], 8))


def _step_root(
    value: str | None,
    repo: Path,
    temp: Path,
    captured: dict[str, str],
) -> Path:
    selected = Path(
        _expand_tokens([value or "{repo}"], repo, temp, captured)[0]
    ).absolute()
    if ".planning" in selected.parts:
        raise ValueError(f"raiz de passo inválida: {selected}")
    try:
        selected.resolve(strict=False).relative_to(temp.resolve())
    except ValueError as error:
        raise ValueError(f"raiz de passo fora do temporário: {selected}") from error
    return selected


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, **FIXED_GIT_ENV},
    )


def _initialize_git(repo: Path, *, commit_initial: bool) -> None:
    initialized = _git(repo, "init", "-q", "-b", "main")
    if initialized.returncode != 0:
        raise RuntimeError(initialized.stderr.strip() or "git init falhou")
    for key, value in (
        ("user.name", "BM Fixture"),
        ("user.email", "fixture@example.invalid"),
    ):
        configured = _git(repo, "config", key, value)
        if configured.returncode != 0:
            raise RuntimeError(configured.stderr.strip() or "git config falhou")
    if commit_initial:
        added = _git(repo, "add", ".")
        committed = _git(repo, "commit", "-q", "-m", "fixture inicial")
        if added.returncode != 0 or committed.returncode != 0:
            raise RuntimeError(
                added.stderr.strip()
                or committed.stderr.strip()
                or "commit inicial falhou"
            )


def _capture_json(
    stdout: str,
    capture: dict[str, str],
) -> dict[str, str]:
    value: Any = json.loads(stdout)
    result: dict[str, str] = {}
    for name, dotted_path in capture.items():
        selected = value
        for key in dotted_path.split("."):
            if isinstance(selected, list) and key.isdigit():
                position = int(key)
                if position >= len(selected):
                    raise KeyError(dotted_path)
                selected = selected[position]
            elif isinstance(selected, dict) and key in selected:
                selected = selected[key]
            else:
                raise KeyError(dotted_path)
        if not isinstance(selected, (str, int, float)) or isinstance(selected, bool):
            raise TypeError(f"capture não escalar: {dotted_path}")
        result[name] = str(selected)
    return result


def _check_expected(
    completed: subprocess.CompletedProcess[str],
    expected: dict[str, Any],
    before: dict[str, bytes],
    after: dict[str, bytes],
    repo: Path,
    temp: Path,
) -> list[str]:
    errors: list[str] = []
    if completed.returncode != expected["exit_code"]:
        errors.append(f"exit {completed.returncode} != {expected['exit_code']}")

    stdout_contract = expected["stdout"]
    if stdout_contract["kind"] == "json":
        try:
            decoded_stdout = json.loads(completed.stdout)
            canonical_stdout = (
                json.dumps(
                    decoded_stdout,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )
            if completed.stdout != canonical_stdout:
                errors.append("stdout JSON não está na forma canônica byte a byte")
            actual_stdout = _normalize_json(decoded_stdout, repo, temp)
        except json.JSONDecodeError as error:
            errors.append(f"stdout não é JSON: {error}")
        else:
            if not _json_matches(actual_stdout, stdout_contract["value"]):
                errors.append(
                    "stdout JSON divergiu: "
                    + json.dumps(actual_stdout, ensure_ascii=False, sort_keys=True)
                )
    elif stdout_contract["kind"] == "text":
        actual_stdout = _normalize_text(completed.stdout, repo, temp)
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
        elif "mode" in specification:
            actual_mode = f"{checked.stat().st_mode & 0o777:04o}"
            if actual_mode != specification["mode"]:
                errors.append(
                    f"modo divergente: {relative} ({actual_mode} != {specification['mode']})"
                )
    return errors


def run_fixture(path: Path, engine: str, binary: Path | None) -> list[str]:
    fixture = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    with tempfile.TemporaryDirectory(prefix="bm-cli-contract-") as temporary:
        temp = Path(temporary)
        repo = temp / "repo"
        repo.mkdir()
        captured: dict[str, str] = {}
        _write_tree(repo, fixture.get("initial_tree", {}), temp, captured)
        git_setup = fixture.get("git")
        if git_setup:
            _initialize_git(
                repo,
                commit_initial=(
                    git_setup.get("commit_initial", False)
                    if isinstance(git_setup, dict)
                    else False
                ),
            )
        steps = fixture.get("steps") or [
            {"argv": fixture["argv"], "expected": fixture["expected"]}
        ]
        for index, step in enumerate(steps, start=1):
            label = f"passo {index}"
            if "json_update" in step:
                update_root = _step_root(step.get("root"), repo, temp, captured)
                update_path = update_root / _safe_relative(step["json_update"]["path"])
                document = json.loads(update_path.read_text(encoding="utf-8"))
                for dotted_key, value in step["json_update"]["values"].items():
                    if not isinstance(dotted_key, str) or not dotted_key:
                        errors.append(f"{label}: chave JSON inválida")
                        break
                    if isinstance(value, str):
                        value = _expand_tokens([value], repo, temp, captured)[0]
                    selected = document
                    keys = dotted_key.split(".")
                    for key in keys[:-1]:
                        if not isinstance(selected, dict) or key not in selected:
                            errors.append(f"{label}: chave JSON ausente: {dotted_key}")
                            break
                        selected = selected[key]
                    if errors:
                        break
                    if not isinstance(selected, dict):
                        errors.append(f"{label}: destino JSON inválido: {dotted_key}")
                        break
                    selected[keys[-1]] = value
                if errors:
                    break
                update_path.write_text(
                    json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n",
                    encoding="utf-8",
                )
                continue
            if "write_tree" in step:
                write_root = _step_root(
                    step.get("root"), repo, temp, captured
                )
                write_root.mkdir(parents=True, exist_ok=True)
                _write_tree(write_root, step["write_tree"], temp, captured)
                continue
            if "git" in step:
                git_step = step["git"]
                git_root = _step_root(step.get("root"), repo, temp, captured)
                if git_step.get("action") == "capture_head":
                    head = _git(git_root, "rev-parse", "HEAD")
                    if head.returncode != 0:
                        errors.append(f"{label}: Git falhou: {head.stderr.strip()}")
                        break
                    captured[git_step.get("name", "git_head")] = head.stdout.strip()
                    continue
                if git_step.get("action") != "commit_all":
                    errors.append(f"{label}: ação Git desconhecida")
                    break
                added = _git(git_root, "add", ".")
                committed = _git(
                    git_root,
                    "commit",
                    "-q",
                    "-m",
                    git_step.get("message", "fixture"),
                )
                if added.returncode != 0 or committed.returncode != 0:
                    errors.append(
                        f"{label}: Git falhou: "
                        + (added.stderr or committed.stderr).strip()
                    )
                    break
                continue
            tree_root = _step_root(step.get("tree_root"), repo, temp, captured)
            command_root = _step_root(step.get("cwd"), repo, temp, captured)
            before = _tree(tree_root)
            argv = _expand_tokens(step["argv"], repo, temp, captured)
            completed = subprocess.run(
                [*_engine_command(engine, binary), *argv],
                cwd=command_root,
                text=True,
                capture_output=True,
                check=False,
                env={
                    **os.environ,
                    **FIXED_GIT_ENV,
                    "COLUMNS": "200",
                    "PYTHONDONTWRITEBYTECODE": "1",
                },
            )
            after = _tree(tree_root)
            if "expected" in step:
                errors.extend(
                    f"{label}: {error}"
                    for error in _check_expected(
                        completed,
                        step["expected"],
                        before,
                        after,
                        repo,
                        temp,
                    )
                )
            elif completed.returncode != 0:
                errors.append(
                    f"{label}: setup CLI falhou ({completed.returncode}): "
                    + _normalize_stderr(completed.stderr, repo, temp).strip()
                )
                break
            if completed.returncode != 0:
                break
            if step.get("capture"):
                try:
                    captured.update(_capture_json(completed.stdout, step["capture"]))
                except (json.JSONDecodeError, KeyError, TypeError) as error:
                    errors.append(f"{label}: capture inválido: {error}")
                    break
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
