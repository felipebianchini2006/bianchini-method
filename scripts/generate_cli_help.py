#!/usr/bin/env python3
"""Generate terminal help text from the frozen Python CLI oracle."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "cli-surfaces.json"
ORACLE = ROOT / "scripts" / "bm_python_oracle.py"
OUTPUT = ROOT / "internal" / "gokernel" / "assets" / "cli-help.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command_paths(contract: dict[str, object]) -> list[tuple[str, ...]]:
    commands = contract.get("commands")
    surfaces = contract.get("surfaces")
    if not isinstance(commands, dict) or not isinstance(surfaces, list):
        raise ValueError("contrato CLI sem commands/surfaces válidos")

    paths: set[tuple[str, ...]] = {()}
    paths.update((str(command),) for command in commands)
    for surface in surfaces:
        if not isinstance(surface, dict):
            raise ValueError("surface inválida no contrato CLI")
        command = surface.get("command")
        action = surface.get("action")
        if action is not None:
            paths.add((str(command), str(action)))
    return sorted(paths)


def oracle_help(path: tuple[str, ...]) -> str:
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    environment["COLUMNS"] = "80"
    result = subprocess.run(
        [sys.executable, str(ORACLE), *path, "--help"],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    label = "bm" if not path else "bm " + " ".join(path)
    if result.returncode != 0:
        raise RuntimeError(
            f"oráculo falhou para {label} --help: exit={result.returncode}: "
            f"{result.stderr.strip()}"
        )
    if result.stderr:
        raise RuntimeError(f"oráculo escreveu stderr para {label} --help: {result.stderr!r}")
    if not result.stdout.endswith("\n"):
        raise RuntimeError(f"oráculo não encerrou help com newline para {label}")
    return result.stdout


def generated_bytes() -> bytes:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    help_by_path = {" ".join(path): oracle_help(path) for path in command_paths(contract)}
    value_flags = {}
    for command, specification in contract["commands"].items():
        interface = specification.get("interface", "")
        value_flags[command] = sorted(
            field.split(";", 1)[0]
            for field in interface.split(" | ")
            if field.startswith("--") and "action=store_true" not in field
        )
    document = {
        "schema_version": 1,
        "command_choices": list(contract["commands"]),
        "source": {
            "contract": "contracts/cli-surfaces.json",
            "contract_sha256": digest(CONTRACT),
            "oracle": "scripts/bm_python_oracle.py",
            "oracle_sha256": digest(ORACLE),
        },
        "help": help_by_path,
        "value_flags": value_flags,
    }
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="falha quando o asset versionado diverge do oráculo",
    )
    args = parser.parse_args()

    expected = generated_bytes()
    if args.check:
        try:
            current = OUTPUT.read_bytes()
        except FileNotFoundError:
            print(f"CLI_HELP_STALE: asset ausente: {OUTPUT.relative_to(ROOT)}", file=sys.stderr)
            return 1
        if current != expected:
            print(
                f"CLI_HELP_STALE: regenere {OUTPUT.relative_to(ROOT)} com "
                "python3 scripts/generate_cli_help.py",
                file=sys.stderr,
            )
            return 1
        print(f"CLI_HELP_OK: {len(json.loads(expected)['help'])} paths")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(expected)
    print(f"CLI_HELP_GENERATED: {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
