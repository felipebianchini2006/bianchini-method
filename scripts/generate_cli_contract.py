#!/usr/bin/env python3
"""Gera a projeção Markdown do registry canônico da CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _cli_contract import DOCUMENT, ROOT, handler_module, load_registry


def _cell(value: object) -> str:
    if isinstance(value, list):
        text = "<br>".join(str(item) for item in value) or "—"
    else:
        text = str(value)
    return text.replace("|", "\\|")


def render() -> str:
    registry = load_registry()
    profiles = registry["behavior_profiles"]
    lines = [
        "# Contrato da CLI 0.4",
        "",
        "> Arquivo gerado de `contracts/cli-surfaces.json`. Não edite manualmente.",
        "",
        f"- Schema do registry: `{registry['schema_version']}`",
        f"- Contrato: `{registry['contract_version']}`",
        f"- Base congelada: `{registry['base_commit']}`",
        f"- Comandos do parser: `{registry['command_count']}`",
        f"- Superfícies do parser: `{registry['surface_count']}`",
        "",
        "## Convenções",
        "",
        "`$CWD` é o diretório corrente no instante em que o parser é construído. "
        "`$PACKAGED_SKILLS_ROOT` é a raiz `skills` da instalação que contém o CLI. "
        "A interface listada abaixo inclui flags aceitas pelo argparse mesmo quando uma ação não as consome.",
        "",
        "## Comandos e interfaces",
        "",
    ]
    lines.extend(["## Extensões do backend Go 1.0", "", "As interfaces históricas abaixo permanecem como oráculo. Estas extensões são exclusivas do Go oficial.", ""])
    for name, extension in registry.get("native_extensions", {}).items():
        lines.extend([f"- `{name}`: {extension['help']}"])
    lines.append("")
    for name, command in registry["commands"].items():
        lines.extend(
            [
                f"### `bm {name}`",
                "",
                f"- Geração: `{command['generation']}`",
                f"- Parser: `{command['interface']}`",
                "",
            ]
        )
    lines.extend(
        [
            "## Superfícies",
            "",
            "| ID | Geração | Saída | Exits | Mutações permitidas | Handlers | Módulos | Consumidores | Evidência |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for surface in registry["surfaces"]:
        profile = profiles[surface["behavior"]]
        evidence = [*surface["fixtures"], *surface["behavior_tests"]]
        lines.append(
            "| "
            + " | ".join(
                _cell(value)
                for value in (
                    f"`{surface['id']}`",
                    surface["generation"],
                    profile["stdout"],
                    ", ".join(profile["exit_codes"]),
                    surface["allowed_mutations"],
                    surface["handlers"] or [surface.get("handler_mode", "nenhum")],
                    sorted({handler_module(handler, registry) for handler in surface["handlers"]}) or ["nenhum"],
                    surface["consumers"],
                    evidence,
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Superfícies negativas",
            "",
            "| ID | Estado | Argv | Exit | Mutações | Consumidores | Evidência |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
    )
    for surface in registry["negative_surfaces"]:
        lines.append(
            "| "
            + " | ".join(
                _cell(value)
                for value in (
                    f"`{surface['id']}`",
                    surface["status"],
                    " ".join(surface["argv"]),
                    surface["exit_code"],
                    surface["allowed_mutations"],
                    surface["consumers"],
                    [*surface["fixtures"], *surface["behavior_tests"]],
                )
            )
            + " |"
        )
    lines.extend(
        [
            "",
            "## Perfis de comportamento",
            "",
        ]
    )
    for name, profile in profiles.items():
        lines.extend(
            [
                f"### `{name}`",
                "",
                f"- stdout: {profile['stdout']}",
                f"- stderr: {profile['stderr']}",
                "- exits: " + "; ".join(f"`{code}` = {meaning}" for code, meaning in profile["exit_codes"].items()),
                f"- mutações-base: {_cell(profile['mutations'])}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=DOCUMENT)
    args = parser.parse_args()
    content = render().encode("utf-8")
    if args.check:
        if not args.output.is_file() or args.output.read_bytes() != content:
            print(
                f"documento divergente; execute python3 {Path(__file__).relative_to(ROOT)}",
                file=sys.stderr,
            )
            return 1
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
