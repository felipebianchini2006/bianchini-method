#!/usr/bin/env python3
"""Primitivas compartilhadas do contrato executável da CLI 0.4."""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import shlex
import sys
from collections import defaultdict
from pathlib import Path
from types import ModuleType
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "skills" / "_shared" / "scripts" / "bm.py"
REGISTRY = ROOT / "contracts" / "cli-surfaces.json"
DOCUMENT = ROOT / "docs" / "cli-contract.md"
FIXTURES = ROOT / "tests" / "fixtures" / "cli_contract"


def load_runtime() -> ModuleType:
    """Carrega o parser oficial sem executar o dispatcher."""

    runtime_dir = str(RUNTIME.parent)
    if runtime_dir not in sys.path:
        sys.path.insert(0, runtime_dir)
    spec = importlib.util.spec_from_file_location("bm_cli_contract_runtime", RUNTIME)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"não foi possível carregar {RUNTIME}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _normalized_default(value: Any) -> Any:
    if value is argparse.SUPPRESS:
        return "$SUPPRESS"
    if isinstance(value, Path):
        resolved = value.resolve()
        if resolved == Path.cwd().resolve():
            return "$CWD"
        packaged_skills = (ROOT / "skills").resolve()
        if resolved == packaged_skills:
            return "$PACKAGED_SKILLS_ROOT"
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return list(value)
    return repr(value)


def _action_kind(action: argparse.Action) -> str:
    names = {
        "_AppendAction": "append",
        "_StoreAction": "store",
        "_StoreTrueAction": "store_true",
        "_StoreFalseAction": "store_false",
    }
    return names.get(type(action).__name__, type(action).__name__)


def _type_name(value: Any) -> str | None:
    if value is None:
        return None
    return getattr(value, "__name__", str(value))


def parser_contract() -> dict[str, dict[str, Any]]:
    """Introspecta o argparse; Markdown nunca participa desta fonte."""

    cli = load_runtime().parser()
    subparsers = next(
        action
        for action in cli._actions
        if isinstance(action, argparse._SubParsersAction)
    )
    commands: dict[str, dict[str, Any]] = {}
    for command, command_parser in subparsers.choices.items():
        arguments: list[dict[str, Any]] = []
        for action in command_parser._actions:
            if isinstance(action, argparse._HelpAction):
                continue
            positional = not action.option_strings
            arguments.append(
                {
                    "dest": action.dest,
                    "kind": "positional" if positional else "flag",
                    "options": list(action.option_strings),
                    "required": bool(action.required),
                    "nargs": action.nargs,
                    "action": _action_kind(action),
                    "type": _type_name(action.type),
                    "choices": list(action.choices) if action.choices is not None else None,
                    "default": _normalized_default(action.default),
                }
            )
        action_argument = next(
            (item for item in arguments if item["dest"] == "action"), None
        )
        actions = list(action_argument["choices"]) if action_argument else [None]
        commands[command] = {"arguments": arguments, "actions": actions}
    return commands


def argument_signatures(arguments: list[dict[str, Any]]) -> list[str]:
    """Serializa flags e defaults sem perder escolhas ou cardinalidade."""

    signatures: list[str] = []
    for argument in arguments:
        name = argument["dest"]
        if argument["options"]:
            name = "/".join(argument["options"])
        parts = [name]
        if argument["type"]:
            parts.append(f"type={argument['type']}")
        if argument["choices"] is not None:
            choices = ",".join(str(choice) for choice in argument["choices"])
            parts.append(f"choices={choices}")
        if argument["action"] != "store":
            parts.append(f"action={argument['action']}")
        if argument["required"]:
            parts.append("required")
        else:
            parts.append(
                "default="
                + json.dumps(argument["default"], ensure_ascii=False, separators=(",", ":"))
            )
        signatures.append(";".join(parts))
    return signatures


def compact_parser_contract() -> dict[str, dict[str, Any]]:
    return {
        command: {
            "actions": value["actions"],
            "arguments": argument_signatures(value["arguments"]),
        }
        for command, value in parser_contract().items()
    }


def command_signature(arguments: list[dict[str, Any]]) -> str:
    """Representação canônica compacta da interface argparse."""

    return " | ".join(argument_signatures(arguments))


def _attribute_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _attribute_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _compared_values(test: ast.AST, attribute: str) -> set[str]:
    values: set[str] = set()
    for node in ast.walk(test):
        if not isinstance(node, ast.Compare) or _attribute_name(node.left) != attribute:
            continue
        for comparator in node.comparators:
            if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                values.add(comparator.value)
            elif isinstance(comparator, (ast.Set, ast.Tuple, ast.List)):
                values.update(
                    item.value
                    for item in comparator.elts
                    if isinstance(item, ast.Constant) and isinstance(item.value, str)
                )
    return values


def dispatcher_contract() -> dict[str, dict[str, Any]]:
    """Extrai dispatcher e símbolos chamados diretamente da AST do runtime."""

    tree = ast.parse(RUNTIME.read_text(encoding="utf-8"), filename=str(RUNTIME))
    main = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    result: dict[str, dict[str, Any]] = {}
    for node in ast.walk(main):
        if not isinstance(node, ast.If):
            continue
        commands = _compared_values(node.test, "args.command")
        if len(commands) != 1:
            continue
        command = next(iter(commands))
        calls = sorted(
            {
                name
                for child in node.body
                for call in ast.walk(child)
                if isinstance(call, ast.Call)
                for name in [_attribute_name(call.func)]
                if name
            }
        )
        actions = sorted(
            {
                action
                for child in node.body
                for candidate in ast.walk(child)
                if isinstance(candidate, ast.If)
                for action in _compared_values(candidate.test, "args.action")
            }
        )
        messages = sorted(
            {
                child.value
                for statement in node.body
                for child in ast.walk(statement)
                if isinstance(child, ast.Constant)
                and isinstance(child.value, str)
                and ("exige" in child.value or "ORDER_VIOLATION" in child.value)
            }
        )
        result[command] = {
            "actions_seen": actions,
            "calls": calls,
            "error_messages": messages,
        }
    return result


def runtime_symbol_modules() -> dict[str, str]:
    """Resolve aliases/imports pela AST para provar o módulo de cada handler."""

    tree = ast.parse(RUNTIME.read_text(encoding="utf-8"), filename=str(RUNTIME))
    symbols: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                symbols[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                symbols[alias.asname or alias.name] = node.module
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols[node.name] = "bm"
    return symbols


def handler_module(handler: str, registry: dict[str, Any]) -> str:
    modules = registry["handler_modules"]
    root_symbol = handler.split(".", 1)[0]
    return modules.get(root_symbol, modules["$local"])


def _logical_lines(text: str) -> Iterable[str]:
    pending = ""
    for raw in text.splitlines():
        line = raw.strip()
        if pending:
            line = pending + " " + line
        if line.endswith("\\"):
            pending = line[:-1]
            continue
        yield line
        pending = ""
    if pending:
        yield pending


def _clean_token(token: str) -> str:
    return token.strip("`'\"<>()[]{}:,;#")


def skill_consumers(
    parser_commands: dict[str, dict[str, Any]],
    negative_commands: set[str],
) -> dict[str, list[str]]:
    """Lexa invocações bm.py nas skills públicas e no companion Codex."""

    documents = [
        *sorted((ROOT / "skills").glob("*/SKILL.md")),
        *sorted((ROOT / "codex" / "skills").glob("*/SKILL.md")),
        *sorted((ROOT / "codex" / "skills").glob("*/references/*.md")),
    ]
    known_commands = set(parser_commands) | negative_commands
    consumers: defaultdict[str, set[str]] = defaultdict(set)
    for document in documents:
        if ".planning" in document.parts:
            continue
        for line in _logical_lines(document.read_text(encoding="utf-8")):
            lexer = shlex.shlex(line.replace("`", " "), posix=True, punctuation_chars="|")
            lexer.whitespace_split = True
            try:
                tokens = [_clean_token(token) for token in lexer if _clean_token(token)]
            except ValueError:
                tokens = [_clean_token(token) for token in line.split() if _clean_token(token)]
            for index, token in enumerate(tokens):
                if Path(token).name != "bm.py" or index + 1 >= len(tokens):
                    continue
                command = tokens[index + 1]
                if command not in known_commands:
                    continue
                key = command
                actions = parser_commands.get(command, {}).get("actions", [None])
                if actions != [None] and index + 2 < len(tokens):
                    action_candidates: list[str] = []
                    cursor = index + 2
                    while cursor < len(tokens):
                        candidate = tokens[cursor]
                        if candidate == "|":
                            cursor += 1
                            continue
                        if candidate.startswith("-") or candidate not in actions:
                            break
                        action_candidates.append(candidate)
                        cursor += 1
                    for action in action_candidates:
                        consumers[f"{command}.{action}"].add(str(document.relative_to(ROOT)))
                    if action_candidates:
                        continue
                consumers[key].add(str(document.relative_to(ROOT)))
    return {key: sorted(value) for key, value in sorted(consumers.items())}


def load_registry() -> dict[str, Any]:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def surface_id(command: str, action: str | None) -> str:
    return f"{command}.{action}" if action else command
