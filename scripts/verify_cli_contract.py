#!/usr/bin/env python3
"""Verifica registry -> parser -> dispatcher -> consumidores -> evidências."""

from __future__ import annotations

import ast
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from _cli_contract import (
    FIXTURES,
    ROOT,
    command_signature,
    dispatcher_contract,
    handler_module,
    load_registry,
    parser_contract,
    skill_consumers,
    surface_id,
    runtime_symbol_modules,
)


def _test_methods(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    }


def _error(errors: list[str], condition: bool, message: str) -> None:
    if not condition:
        errors.append(message)


def verify() -> dict[str, Any]:
    registry = load_registry()
    parser = parser_contract()
    dispatcher = dispatcher_contract()
    surfaces = registry["surfaces"]
    negatives = registry["negative_surfaces"]
    errors: list[str] = []

    _error(errors, registry["schema_version"] == 1, "schema_version deve ser 1")
    _error(errors, len(registry["commands"]) == 30, "registry deve conter 30 comandos")
    _error(errors, len(surfaces) == 53, "registry deve conter 53 superfícies")
    _error(errors, registry["command_count"] == len(parser), "command_count divergente")
    actual_surface_count = sum(len(value["actions"]) for value in parser.values())
    _error(errors, registry["surface_count"] == actual_surface_count, "surface_count divergente")
    _error(errors, set(registry["commands"]) == set(parser), "comandos do argparse divergentes")

    expected_ids = {
        surface_id(command, action)
        for command, value in parser.items()
        for action in value["actions"]
    }
    registered_ids = {surface["id"] for surface in surfaces}
    _error(errors, len(registered_ids) == len(surfaces), "IDs de superfície duplicados")
    _error(errors, registered_ids == expected_ids, "ações do argparse divergentes do registry")

    for command, expected in parser.items():
        registered = registry["commands"][command]
        actual_interface = command_signature(expected["arguments"])
        _error(
            errors,
            registered["interface"] == actual_interface,
            f"flags/defaults divergentes em {command}",
        )
        _error(errors, command in dispatcher, f"dispatcher ausente para {command}")

    profiles = registry["behavior_profiles"]
    symbol_modules = runtime_symbol_modules()
    for surface in surfaces:
        command = surface["command"]
        _error(errors, surface["behavior"] in profiles, f"profile inválido: {surface['id']}")
        _error(errors, surface["generation"] in {"core_0_4", "companion", "operational", "legacy_internal"}, f"geração inválida: {surface['id']}")
        _error(errors, bool(surface["allowed_mutations"]), f"mutações não registradas: {surface['id']}")
        direct_calls = set(dispatcher.get(command, {}).get("calls", []))
        for handler in surface["handlers"]:
            _error(errors, handler in direct_calls, f"handler {handler} não ligado no dispatcher de {surface['id']}")
            root_symbol = handler.split(".", 1)[0]
            actual_module = symbol_modules.get(root_symbol)
            if actual_module == "bm":
                actual_path = "skills/_shared/scripts/bm.py"
            elif actual_module:
                actual_path = f"skills/_shared/scripts/{actual_module.replace('.', '/')}.py"
            else:
                actual_path = None
            _error(
                errors,
                actual_path == handler_module(handler, registry),
                f"módulo do handler {handler} divergiu em {surface['id']}",
            )
    reopen = next(surface for surface in surfaces if surface["id"] == "direct.reopen")
    _error(errors, reopen.get("handler_mode") == "parser_only_terminal_error", "direct reopen deve ser parser-only terminal error")
    _error(errors, "ORDER_VIOLATION: quick 0.4 terminal é imutável" in dispatcher["direct"]["error_messages"], "erro terminal de direct reopen não encontrado na AST")

    negative_ids = {item["id"] for item in negatives}
    _error(errors, len(negative_ids) == len(negatives), "IDs negativos duplicados")
    for command in ("route", "legacy-transition", "repo-hygiene"):
        _error(errors, command not in parser, f"comando aposentado voltou ao parser: {command}")
    workspace_options = {
        option
        for argument in parser["workspace"]["arguments"]
        for option in argument["options"]
    }
    for flag in ("--planning-version", "--state"):
        _error(errors, flag not in workspace_options, f"flag antiga voltou ao workspace: {flag}")

    negative_commands = {"route", "legacy-transition", "repo-hygiene"}
    consumed = skill_consumers(parser, negative_commands)
    registry_consumers: defaultdict[str, set[str]] = defaultdict(set)
    for surface in [*surfaces, *negatives]:
        key = surface["id"]
        if key.endswith(".retired"):
            key = key.removesuffix(".retired")
        registry_consumers[key].update(surface["consumers"])
    unregistered: list[dict[str, str]] = []
    for key, documents in consumed.items():
        lookup = key
        if key in negative_commands:
            lookup = f"{key}.retired"
        matching = next((item for item in [*surfaces, *negatives] if item["id"] == lookup), None)
        if matching is None:
            unregistered.extend({"surface": key, "consumer": document} for document in documents)
            continue
        declared = set(matching["consumers"])
        unregistered.extend(
            {"surface": key, "consumer": document}
            for document in documents
            if document not in declared
        )

    fixture_names = {path.stem for path in FIXTURES.glob("*.json")} if FIXTURES.is_dir() else set()
    test_cache: dict[Path, set[str]] = {}
    evidence_errors: list[str] = []
    for surface in [*surfaces, *negatives]:
        for fixture in surface["fixtures"]:
            if fixture not in fixture_names:
                evidence_errors.append(f"fixture ausente: {fixture}")
        for reference in surface["behavior_tests"]:
            path_text, separator, method = reference.partition("::")
            path = ROOT / path_text
            if not separator or not path.is_file():
                evidence_errors.append(f"teste inválido: {reference}")
                continue
            methods = test_cache.setdefault(path, _test_methods(path))
            if method not in methods:
                evidence_errors.append(f"teste ausente: {reference}")
        if surface["consumers"] and not (surface["fixtures"] or surface["behavior_tests"]):
            evidence_errors.append(f"superfície consumida sem evidência: {surface['id']}")
    errors.extend(evidence_errors)
    errors.extend(
        f"consumidor sem registro: {item['surface']} em {item['consumer']}"
        for item in unregistered
    )
    return {
        "valid": not errors,
        "command_count": len(parser),
        "surface_count": actual_surface_count,
        "negative_surface_count": len(negatives),
        "unregistered_skill_surfaces": unregistered,
        "errors": errors,
    }


def main() -> int:
    result = verify()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
