#!/usr/bin/env python3
"""Validação de unidades v2 e projeção compacta de contexto operacional."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import unicodedata
from pathlib import Path
from typing import Any

import bm_learning
from bm_feature_support import (
    FIX_ROUNDS_BY_PROFILE,
    confined_path,
    field_value,
    json_document,
    sha256_bytes,
    unit_sections,
)
from bm_project_model import plan_file_for_id
from bm_spec_package import SpecPackageError, parse_spec_requirements


QUALITY_V2_UNIT_FIELDS = ("Change", "Readiness refs")
CHANGE_KINDS = frozenset(
    {
        "api-contract", "authorization", "behavioral", "bug", "business-rule",
        "calculation", "config", "copy", "data-model", "data-transform",
        "dependency", "deployment", "documentation", "financial", "infrastructure",
        "integration", "inventory", "mechanical", "migration", "money",
        "observability", "offline", "parser", "payment", "performance",
        "permission", "platform", "refactor", "security", "state-machine",
        "stock", "style", "sync", "visual", "workflow",
    }
)
MUTATION_RELEVANT_CHANGES = frozenset(
    {
        "api-contract", "authorization", "business-rule", "calculation", "data-model",
        "data-transform", "financial", "inventory", "migration", "money", "offline",
        "parser", "payment", "permission", "security", "state-machine", "stock", "sync",
    }
)
PURE_NON_LOGIC_CHANGES = frozenset(
    {"copy", "documentation", "mechanical", "style", "visual"}
)
READINESS_COLLECTIONS = (
    "decisions", "assumptions", "pitfalls", "user_actions", "spikes",
    "design_surfaces", "spec_deltas",
)
READINESS_ID = re.compile(r"^(?:D|A|P|U|S|DS|SD)-[0-9]{3}$")

# A menor baseline prescrita medida na Fase 0 tem 22.686 bytes. O contrato
# default usa 16 KiB para exigir redução mensurável em bytes, sem alegar tokens.
PRESCRIBED_BASELINE_MIN_BYTES = 22_686
DEFAULT_MAX_BYTES = 16_384
CONTEXT_PACK_SCHEMA_VERSION = 1
CONTEXT_PACK_CONTRACT = "0.4"
LEDGER_TAIL_LINES = 20
UNIT_CHANGE = re.compile(r"^(C[0-9]{3})/(P[0-9]{2})(?:/(T[0-9]{2}))?$")
UNIT_QUICK = re.compile(r"^Q[0-9]{3}$")
UNIT_DEBUG = re.compile(r"^D[0-9]{3}$")
UNIT_RC = re.compile(r"^RC:([A-Za-z0-9][A-Za-z0-9._:-]{0,127})$")
SCOPE_HEADING = re.compile(
    r"(?m)^(#{1,6})\s+((?:FLW|REQ|NFR|BR|DAT|INT|ERR|RSK)-[0-9]+)\b[^\n]*$"
)
DECISION_HEADING = re.compile(r"(?m)^(#{1,6})\s+(D-[0-9]{3})\b[^\n]*$")
DECISION_REFERENCE = re.compile(r"\bD-[0-9]{3}\b")


class ContextPackError(ValueError):
    """Falha fechada com código estável para a interface do context pack."""

    def __init__(
        self, code: str, message: str, *, details: dict[str, Any] | None = None
    ) -> None:
        self.code = code
        self.message = message
        self.details = details or {}
        suffix = (
            " " + json.dumps(self.details, ensure_ascii=False, sort_keys=True)
            if self.details
            else ""
        )
        super().__init__(f"{code}: {message}{suffix}")


def _context_fail(
    code: str, message: str, *, details: dict[str, Any] | None = None
) -> None:
    raise ContextPackError(code, message, details=details)


class _PackSources:
    """Leitor que registra todo arquivo capaz de influenciar o pack."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.digests: dict[str, str] = {}

    def bytes(self, path: Path, label: str) -> bytes:
        safe = _safe_existing_file(self.root, path, label)
        try:
            content = safe.read_bytes()
        except OSError as error:
            _context_fail("PACK_INCOMPLETE", f"não foi possível ler {label}: {error}")
        relative = safe.relative_to(self.root).as_posix()
        self.digests[relative] = hashlib.sha256(content).hexdigest()
        return content

    def text(self, path: Path, label: str) -> str:
        content = self.bytes(path, label)
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            _context_fail("PACK_INCOMPLETE", f"{label} não é UTF-8")
        raise AssertionError

    def frontmatter(self, path: Path, label: str) -> dict[str, Any]:
        text = self.text(path, label)
        match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", text, re.DOTALL)
        if match is None:
            _context_fail("PACK_INCOMPLETE", f"{label} exige frontmatter JSON")
        try:
            value = json.loads(match.group(1))
        except json.JSONDecodeError as error:
            _context_fail(
                "PACK_INCOMPLETE", f"{label} possui JSON inválido na linha {error.lineno}"
            )
        if not isinstance(value, dict):
            _context_fail("PACK_INCOMPLETE", f"{label} exige objeto")
        return value

    def json(self, path: Path, label: str) -> dict[str, Any]:
        try:
            value = json.loads(self.text(path, label))
        except json.JSONDecodeError as error:
            _context_fail(
                "PACK_INCOMPLETE", f"{label} possui JSON inválido na linha {error.lineno}"
            )
        if not isinstance(value, dict):
            _context_fail("PACK_INCOMPLETE", f"{label} exige objeto")
        return value


def readiness_index(readiness: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for collection in READINESS_COLLECTIONS:
        values = readiness.get(collection, [])
        if not isinstance(values, list):
            continue
        for item in values:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                index[item["id"]] = {**item, "collection": collection}
    return index


def destination_path(value: str) -> str:
    return value.split("#", 1)[0].strip()


def parse_readiness_refs(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def validate_quality_v2_plan(
    plan_path: str,
    content: str,
    readiness: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    index = readiness_index(readiness)
    referenced_by_plan: set[str] = set()
    for heading, section in unit_sections(content):
        change = field_value(section, "Change")
        if change is None:
            errors.append(f"plano {plan_path} / {heading}: campo Change ausente")
        elif change not in CHANGE_KINDS:
            errors.append(
                f"plano {plan_path} / {heading}: Change inválido {change!r}; "
                "use categoria factual suportada por bm policy"
            )
        raw_refs = field_value(section, "Readiness refs")
        if raw_refs is None:
            errors.append(f"plano {plan_path} / {heading}: campo Readiness refs ausente")
            continue
        refs = parse_readiness_refs(raw_refs)
        if not refs:
            errors.append(f"plano {plan_path} / {heading}: Readiness refs vazio")
            continue
        if len(refs) != len(set(refs)):
            errors.append(f"plano {plan_path} / {heading}: Readiness refs contém duplicatas")
        for identifier in refs:
            if not READINESS_ID.fullmatch(identifier):
                errors.append(
                    f"plano {plan_path} / {heading}: readiness ref inválida {identifier!r}"
                )
                continue
            item = index.get(identifier)
            if item is None:
                errors.append(
                    f"plano {plan_path} / {heading}: readiness ref inexistente {identifier}"
                )
                continue
            allowed = {
                destination_path(value)
                for value in item.get("destinations", [])
                if isinstance(value, str) and value.strip()
            }
            if plan_path not in allowed:
                errors.append(
                    f"plano {plan_path} / {heading}: readiness ref {identifier} "
                    "não declara este plano em destinations"
                )
                continue
            referenced_by_plan.add(identifier)
    expected = {
        identifier
        for identifier, item in index.items()
        if plan_path in {
            destination_path(value)
            for value in item.get("destinations", [])
            if isinstance(value, str) and value.strip()
        }
    }
    missing = sorted(expected - referenced_by_plan)
    if missing:
        errors.append(
            f"plano {plan_path}: readiness refs destinadas ao plano não foram ligadas "
            "a nenhuma unidade: " + ", ".join(missing)
        )
    return errors


def mutation_mode_for_change(risk: str, change: str) -> str:
    normalized = change.strip().lower().replace("_", "-")
    if risk == "low" or normalized in PURE_NON_LOGIC_CHANGES:
        return "not_required"
    if risk in {"high", "critical"}:
        return "required_selective"
    if normalized in MUTATION_RELEVANT_CHANGES:
        return "selective"
    return "not_required"


def strongest_mutation_mode(risk: str, changes: list[str]) -> str:
    rank = {"not_required": 0, "selective": 1, "required_selective": 2}
    modes = [mutation_mode_for_change(risk, value) for value in changes or ["behavioral"]]
    return max(modes, key=rank.__getitem__)


def slugify_heading(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "-", normalized.lower().strip()).strip("-")


def extract_markdown_section(content: str, anchor: str, label: str) -> str:
    headings = list(re.finditer(r"(?m)^(#{1,6})\s+([^\n]+)$", content))
    for index, match in enumerate(headings):
        if slugify_heading(match.group(2)) != anchor:
            continue
        level = len(match.group(1))
        end = len(content)
        for following in headings[index + 1 :]:
            if len(following.group(1)) <= level:
                end = following.start()
                break
        return content[match.start():end].strip()
    raise ValueError(f"spec ref não encontrada: {label}#{anchor}")


def resolve_spec_ref(root: Path, change_root: Path, raw: str) -> tuple[str, str]:
    path_value, separator, anchor = raw.strip().partition("#")
    if not path_value:
        raise ValueError(f"spec ref inválida: {raw!r}")
    if not separator or not anchor.strip():
        raise ValueError(f"spec ref hidratada exige seção #anchor: {raw}")
    candidate = Path(path_value)
    value = candidate if candidate.parts[:1] == ("docs",) else change_root / candidate
    target = confined_path(root, value, "spec ref")
    if not target.is_file():
        raise ValueError(f"spec ref ausente: {raw}")
    content = target.read_text(encoding="utf-8")
    relative = target.relative_to(root.resolve()).as_posix()
    normalized_anchor = anchor.strip()
    return (
        f"{relative}#{normalized_anchor}",
        extract_markdown_section(content, normalized_anchor, relative),
    )


def hydrate_task_context(
    *,
    root: Path,
    state: dict[str, Any],
    plan_path: Path,
    labels: list[str],
    sections: list[str],
    ledger_tail_lines: int,
) -> tuple[str, dict[str, Any]]:
    base = root.resolve()
    if state.get("method_version") != 2:
        raise ValueError("contexto hidratado exige PROJECT_STATE v2")
    planning = state.get("planning") or {}
    if planning.get("quality_version") != 2:
        raise ValueError("contexto hidratado exige planning.quality_version 2")
    plan_file = confined_path(base, plan_path, "plan")
    plan_relative = plan_file.relative_to(base).as_posix()
    plan = next((item for item in state.get("plans", []) if item.get("path") == plan_relative), None)
    if plan is None:
        raise ValueError("plan não pertence ao PROJECT_STATE informado")
    readiness_path = confined_path(base, planning.get("readiness", ""), "planning.readiness")
    readiness = json_document(readiness_path, "READINESS.md")
    errors = validate_quality_v2_plan(plan_relative, plan_file.read_text(encoding="utf-8"), readiness)
    if errors:
        raise ValueError("contexto não pode ser hidratado:\n- " + "\n- ".join(errors))
    selected_refs: list[str] = []
    spec_refs: list[str] = []
    changes: list[str] = []
    for section in sections:
        selected_refs.extend(parse_readiness_refs(field_value(section, "Readiness refs") or ""))
        spec_refs.extend(
            item.strip()
            for item in (field_value(section, "Spec refs") or "").split(",")
            if item.strip()
        )
        if change := field_value(section, "Change"):
            changes.append(change)
    selected_refs = list(dict.fromkeys(selected_refs))
    spec_refs = list(dict.fromkeys(spec_refs))
    index = readiness_index(readiness)
    selected_items = [index[identifier] for identifier in selected_refs]
    change_root = confined_path(base, planning.get("change_root", ""), "planning.change_root")
    resolved_specs = [resolve_spec_ref(base, change_root, raw) for raw in spec_refs]
    ledger_tail: list[str] = []
    if isinstance(plan.get("ledger"), str) and plan["ledger"]:
        ledger = confined_path(base, plan["ledger"], "plan.ledger")
        if ledger.is_file():
            ledger_lines = ledger.read_text(encoding="utf-8").splitlines()
            ledger_tail = [] if ledger_tail_lines == 0 else ledger_lines[-ledger_tail_lines:]
    active = state.get("active_execution")
    active_for_plan = active if isinstance(active, dict) and active.get("plan_id") == plan.get("id") else None
    profile = state.get("assurance_profile")
    metadata = {
        "schema_version": 1,
        "planning_version": state.get("planning_version"),
        "package_digest": state.get("approval", {}).get("package", {}).get("manifest_digest"),
        "plan_id": plan.get("id"),
        "plan_path": plan_relative,
        "profile": profile,
        "risk": plan.get("risk"),
        "execution": plan.get("execution"),
        "review": plan.get("review"),
        "test_seams": plan.get("test_seams", []),
        "max_fix_rounds": FIX_ROUNDS_BY_PROFILE.get(str(profile)),
        "units": labels,
        "changes": changes,
        "readiness_refs": selected_refs,
        "spec_refs": [label for label, _ in resolved_specs],
        "verification_fast": state.get("verification", {}).get("fast", {}).get("commands", []),
        "active_execution": active_for_plan,
        "ledger_tail_lines": len(ledger_tail),
    }
    chunks = [
        "## Contexto hidratado", "", "```json",
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True), "```", "",
        "### Readiness aplicável", "", "```json",
        json.dumps(selected_items, ensure_ascii=False, indent=2, sort_keys=True), "```", "",
        "### Specs aplicáveis",
    ]
    for label, content in resolved_specs:
        chunks.extend(("", f"#### `{label}`", "", content))
    chunks.extend(("", "### Verification.fast", ""))
    chunks.extend(f"- `{command}`" for command in metadata["verification_fast"])
    if not metadata["verification_fast"]:
        chunks.append("- Nenhum comando configurado.")
    chunks.extend(("", "### Último estado operacional", ""))
    chunks.extend(("```text", "\n".join(ledger_tail), "```") if ledger_tail else ("Nenhum ledger registrado para o plano.",))
    rendered = "\n".join(chunks).rstrip() + "\n"
    metadata["context_digest"] = sha256_bytes(rendered.encode("utf-8"))
    return rendered, metadata


def _repo_root(repo: str | Path) -> Path:
    raw = Path(repo)
    if raw.is_symlink():
        _context_fail("PATH_UNSAFE", f"repo não pode ser symlink: {raw}")
    # Preserva a grafia lexical do root (macOS pode expor /var ou /private/var)
    # para que a inspeção da cadeia não perca symlinks internos.
    root = raw.absolute()
    if not root.is_dir():
        _context_fail("PACK_INCOMPLETE", f"repo ausente: {root}")
    if not (root / ".bianchini").is_dir():
        _context_fail("PACK_INCOMPLETE", ".bianchini ausente")
    _reject_symlink_chain(root, root / ".bianchini", ".bianchini")
    return root


def _relative_candidate(root: Path, value: str | Path, label: str) -> Path:
    raw_text = str(value)
    if "\\" in raw_text:
        _context_fail("PATH_UNSAFE", f"{label} contém separador inválido")
    raw = Path(value)
    candidate = raw if raw.is_absolute() else root / raw
    lexical = candidate.absolute()
    try:
        relative = lexical.relative_to(root)
    except ValueError:
        try:
            # macOS apresenta /var e /private/var como aliases do mesmo volume.
            relative = lexical.resolve(strict=False).relative_to(root.resolve())
        except ValueError:
            _context_fail("PATH_UNSAFE", f"{label} sai do repo: {value}")
    if any(part in {"", ".", ".."} for part in relative.parts):
        _context_fail("PATH_UNSAFE", f"{label} contém traversal: {value}")
    if any(part.casefold() == ".planning" for part in relative.parts):
        _context_fail("PATH_UNSAFE", f"{label} usa namespace estrangeiro")
    canonical = root / relative
    _reject_symlink_chain(root, canonical, label)
    return canonical


def _reject_symlink_chain(root: Path, target: Path, label: str) -> None:
    try:
        relative = target.absolute().relative_to(root.absolute())
    except ValueError:
        _context_fail("PATH_UNSAFE", f"{label} sai do repo")
    current = root.absolute()
    if current.is_symlink():
        _context_fail("PATH_UNSAFE", f"{label} atravessa symlink")
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            _context_fail("PATH_UNSAFE", f"{label} atravessa symlink: {current}")


def _safe_existing_file(root: Path, path: Path, label: str) -> Path:
    candidate = _relative_candidate(root, path, label)
    if not candidate.is_file():
        _context_fail("PACK_INCOMPLETE", f"{label} ausente: {candidate.relative_to(root)}")
    return candidate


def _safe_output(root: Path, output: str | Path) -> Path:
    candidate = _relative_candidate(root, output, "output")
    runtime_context = root / ".bianchini/.runtime/context"
    try:
        relative = candidate.relative_to(runtime_context)
    except ValueError:
        _context_fail(
            "PATH_UNSAFE",
            "output deve ficar em .bianchini/.runtime/context",
        )
    if not relative.parts:
        _context_fail("PATH_UNSAFE", "output exige nome de arquivo")
    if candidate.exists() and not candidate.is_file():
        _context_fail("PATH_UNSAFE", "output existente não é arquivo regular")
    return candidate


def _children(directory: Path, label: str) -> list[Path]:
    if directory.is_symlink():
        _context_fail("PATH_UNSAFE", f"{label} não pode ser symlink")
    if not directory.is_dir():
        _context_fail("PACK_INCOMPLETE", f"{label} ausente")
    result: list[Path] = []
    for candidate in sorted(directory.iterdir(), key=lambda item: item.name):
        if candidate.is_symlink():
            _context_fail("PATH_UNSAFE", f"{label} contém symlink: {candidate.name}")
        result.append(candidate)
    return result


def _find_prefixed_directory(root: Path, directory: Path, identifier: str, label: str) -> Path:
    matches = [
        candidate
        for candidate in _children(directory, label)
        if candidate.is_dir()
        and (candidate.name == identifier or candidate.name.startswith(identifier + "-"))
    ]
    if len(matches) != 1:
        _context_fail(
            "PACK_INCOMPLETE",
            f"{label} {identifier} exige uma correspondência; encontradas {len(matches)}",
        )
    _relative_candidate(root, matches[0], label)
    return matches[0]


def _find_debug(root: Path, identifier: str) -> Path:
    debug_root = root / ".bianchini/debug"
    matches: list[Path] = []
    for state in ("active", "resolved"):
        directory = debug_root / state
        if not directory.exists():
            continue
        for candidate in _children(directory, f"debug/{state}"):
            if candidate.is_file() and (
                candidate.stem == identifier or candidate.stem.startswith(identifier + "-")
            ):
                matches.append(candidate)
        if matches:
            break
    if len(matches) != 1:
        _context_fail(
            "PACK_INCOMPLETE",
            f"debug {identifier} exige uma correspondência; encontradas {len(matches)}",
        )
    return matches[0]


def _git_head(root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.stdout.strip() if completed.returncode == 0 else "UNBORN"


def _state_slice(value: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "active_work",
        "current_unit",
        "status",
        "blockers",
        "next_action",
        "last_completed",
        "pointers",
    )
    return {field: value.get(field) for field in fields}


def _section_slices(
    content: str,
    identifiers: set[str],
    pattern: re.Pattern[str],
    label: str,
) -> list[dict[str, str]]:
    headings = list(pattern.finditer(content))
    all_headings = list(re.finditer(r"(?m)^(#{1,6})\s+[^\n]+$", content))
    by_position = {match.start(): index for index, match in enumerate(all_headings)}
    selected: dict[str, str] = {}
    for match in headings:
        identifier = match.group(2)
        if identifier not in identifiers:
            continue
        level = len(match.group(1))
        end = len(content)
        for following in all_headings[by_position[match.start()] + 1 :]:
            if len(following.group(1)) <= level:
                end = following.start()
                break
        selected[identifier] = content[match.start():end].strip()
    missing = sorted(identifiers - set(selected))
    if missing:
        _context_fail("PACK_INCOMPLETE", f"{label} não contém: {', '.join(missing)}")
    return [{"id": identifier, "content": selected[identifier]} for identifier in sorted(selected)]


def _mapping_strings(value: Any) -> set[str]:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    return set(DECISION_REFERENCE.findall(encoded))


def _model_touches(plan: dict[str, Any]) -> dict[str, set[str]]:
    touches: dict[str, set[str]] = {}
    for field in ("modules", "interfaces", "ownership", "data"):
        values = plan.get(field, [])
        if isinstance(values, list):
            touches[field] = {value for value in values if isinstance(value, str)}
    delta = plan.get("model_delta", {})
    if isinstance(delta, dict):
        for section, operations in delta.items():
            if not isinstance(section, str):
                continue
            values: list[Any] = []
            if isinstance(operations, list):
                values = operations
            elif isinstance(operations, dict):
                for operation_values in operations.values():
                    if isinstance(operation_values, list):
                        values.extend(operation_values)
            identifiers = {
                value
                if isinstance(value, str)
                else value.get("id")
                if isinstance(value, dict)
                else None
                for value in values
            }
            touches.setdefault(section, set()).update(
                value for value in identifiers if isinstance(value, str)
            )
    return {section: identifiers for section, identifiers in touches.items() if identifiers}


def _model_slice(model: dict[str, Any], touches: dict[str, set[str]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for section in sorted(touches):
        raw_entries = model.get(section, [])
        if isinstance(raw_entries, dict):
            entries = [{"id": key, **value} for key, value in raw_entries.items() if isinstance(value, dict)]
        elif isinstance(raw_entries, list):
            entries = [value for value in raw_entries if isinstance(value, dict)]
        else:
            entries = []
        by_id = {
            value["id"]: value
            for value in entries
            if isinstance(value.get("id"), str)
        }
        for identifier in sorted(touches[section]):
            selected.append(
                {
                    "section": section,
                    "id": identifier,
                    "value": by_id.get(identifier),
                }
            )
    return selected


def _spec_slices(
    sources: _PackSources,
    change: Path,
    scope_ids: set[str],
    required_refs: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    manifest_path = change / "specs/MANIFEST.json"
    manifest = sources.json(manifest_path, "MANIFEST.json de specs")
    if manifest.get("schema_version") != 1 or manifest.get("spec_contract") != 1:
        _context_fail("PACK_INCOMPLETE", "MANIFEST.json de specs possui contrato inválido")
    specs = manifest.get("specs")
    if not isinstance(specs, list):
        _context_fail("PACK_INCOMPLETE", "MANIFEST.json.specs exige lista")
    result: list[dict[str, Any]] = []
    covered: set[str] = set()
    for spec in specs:
        if not isinstance(spec, dict) or not isinstance(spec.get("path"), str):
            _context_fail("PACK_INCOMPLETE", "entrada inválida em MANIFEST.json.specs")
        declarations = spec.get("requirements", [])
        if not isinstance(declarations, list):
            _context_fail("PACK_INCOMPLETE", "requirements de spec exige lista")
        selected_declarations = []
        for declaration in declarations:
            if not isinstance(declaration, dict):
                _context_fail("PACK_INCOMPLETE", "requirement inválido no manifesto")
            requirement_id = declaration.get("id")
            scopes = declaration.get("scope")
            if not isinstance(requirement_id, str) or not isinstance(scopes, list):
                _context_fail("PACK_INCOMPLETE", "requirement incompleto no manifesto")
            relevant_scope = sorted(
                value for value in scopes if isinstance(value, str) and value in scope_ids
            )
            if relevant_scope:
                selected_declarations.append((requirement_id, relevant_scope))
                covered.update(relevant_scope)
        if not selected_declarations:
            continue
        path_value = spec["path"]
        spec_path = _relative_candidate(
            sources.root, change / "specs/expected" / path_value, "spec target"
        )
        content = sources.text(spec_path, f"spec {path_value}")
        try:
            parsed = parse_spec_requirements(content, path_value)
        except SpecPackageError as error:
            _context_fail("PACK_INCOMPLETE", str(error))
        for requirement_id, relevant_scope in selected_declarations:
            section = parsed.get(requirement_id)
            if section is None:
                _context_fail(
                    "PACK_INCOMPLETE", f"spec {path_value} não contém {requirement_id}"
                )
            result.append(
                {
                    "id": requirement_id,
                    "spec": spec.get("id"),
                    "path": path_value,
                    "scope": relevant_scope,
                    "content": section,
                }
            )
            required_refs.add(f"spec:{spec.get('id')}#{requirement_id}")
    raw_risk_coverage = manifest.get("risk_coverage", [])
    if not isinstance(raw_risk_coverage, list):
        _context_fail("PACK_INCOMPLETE", "MANIFEST.json.risk_coverage exige lista")
    relevant_risk_coverage: list[dict[str, Any]] = []
    for item in raw_risk_coverage:
        if not isinstance(item, dict):
            _context_fail("PACK_INCOMPLETE", "risk_coverage contém item inválido")
        scope_id = item.get("scope")
        if isinstance(scope_id, str) and scope_id in scope_ids:
            relevant_risk_coverage.append(item)
            covered.add(scope_id)
            required_refs.add(
                f"risk-coverage:{scope_id}:{item.get('kind')}:{item.get('target')}"
            )
    missing = sorted(scope_ids - covered)
    if missing:
        _context_fail(
            "PACK_INCOMPLETE",
            "requirements do pack sem cobertura de spec: " + ", ".join(missing),
        )
    return (
        sorted(result, key=lambda item: (str(item["path"]), str(item["id"]))),
        sorted(
            relevant_risk_coverage,
            key=lambda item: (
                str(item.get("scope")),
                str(item.get("kind")),
                str(item.get("target")),
            ),
        ),
    )


def _result_value(sources: _PackSources, path: Path, label: str) -> dict[str, Any]:
    return sources.frontmatter(path, label)


def _open_findings(value: dict[str, Any], plan_id: str) -> list[dict[str, Any]]:
    findings = value.get("findings", [])
    if not isinstance(findings, list):
        _context_fail("PACK_INCOMPLETE", "COHERENCE.findings exige lista")
    return [
        item
        for item in findings
        if isinstance(item, dict)
        and item.get("status", "open") == "open"
        and (
            not isinstance(item.get("phases"), list)
            or not item.get("phases")
            or plan_id in item["phases"]
        )
    ]


def _ledger_tail(sources: _PackSources, change: Path) -> list[Any]:
    candidates = (
        change / "results/LEDGER.jsonl",
        change / "LEDGER.jsonl",
        change / "results/LEDGER.md",
        change / "LEDGER.md",
    )
    path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if path is None:
        return []
    lines = sources.text(path, "ledger").splitlines()[-LEDGER_TAIL_LINES:]
    result: list[Any] = []
    for line in lines:
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            result.append(line)
    return result


def _change_context(
    root: Path,
    sources: _PackSources,
    state: dict[str, Any],
    change_id: str,
    plan_id: str,
    task_id: str | None,
    required_refs: set[str],
) -> dict[str, Any]:
    change = _find_prefixed_directory(
        root, root / ".bianchini/changes", change_id, "mudança"
    )
    plan_path = plan_file_for_id(change / "plans", plan_id)
    if plan_path is None:
        _context_fail(
            "PACK_INCOMPLETE",
            f"plano {plan_id} deve localizar exatamente um arquivo",
        )
    plan = sources.frontmatter(plan_path, f"plano {plan_id}")
    if plan.get("id") != plan_id:
        _context_fail("PACK_INCOMPLETE", f"plano {plan_id} possui id divergente")
    required_refs.add(f"plan:{change_id}/{plan_id}")

    tasks = plan.get("tasks", [])
    if not isinstance(tasks, list):
        _context_fail("PACK_INCOMPLETE", f"plano {plan_id}.tasks exige lista")
    selected_task: dict[str, Any] | None = None
    if task_id:
        matches = [item for item in tasks if isinstance(item, dict) and item.get("id") == task_id]
        if len(matches) != 1:
            _context_fail("PACK_INCOMPLETE", f"tarefa {task_id} não existe em {plan_id}")
        selected_task = matches[0]
        required_refs.add(f"task:{change_id}/{plan_id}/{task_id}")

    raw_scope = (
        selected_task.get("covers", [])
        if selected_task is not None
        else plan.get("requirements", [])
    )
    if not isinstance(raw_scope, list) or not raw_scope or not all(
        isinstance(value, str) for value in raw_scope
    ):
        _context_fail("PACK_INCOMPLETE", "unidade não declara cobertura de SCOPE")
    scope_ids = set(raw_scope)
    scope = _section_slices(
        sources.text(change / "SCOPE.md", "SCOPE.md"),
        scope_ids,
        SCOPE_HEADING,
        "SCOPE.md",
    )
    required_refs.update(f"scope:{identifier}" for identifier in scope_ids)
    spec_requirements, risk_coverage = _spec_slices(
        sources, change, scope_ids, required_refs
    )

    touches = _model_touches(plan)
    model_nodes: list[dict[str, Any]] = []
    if touches:
        model_nodes = _model_slice(
            sources.frontmatter(change / "SYSTEM_MODEL.md", "SYSTEM_MODEL.md"), touches
        )

    all_plans: list[dict[str, Any]] = []
    plans_dir = change / "plans"
    for candidate in _children(plans_dir, "plans"):
        if candidate.is_file() and candidate.suffix == ".md":
            value = sources.frontmatter(candidate, f"plano {candidate.stem}")
            if isinstance(value.get("id"), str):
                all_plans.append(value)
    by_id = {str(value["id"]): value for value in all_plans}
    consumes = {value for value in plan.get("consumes", []) if isinstance(value, str)}
    provides = {value for value in plan.get("provides", []) if isinstance(value, str)}
    provider_ids = {
        str(value["id"])
        for value in all_plans
        if value.get("id") != plan_id
        and consumes
        & {contract for contract in value.get("provides", []) if isinstance(contract, str)}
    }
    dependency_ids = {
        value for value in plan.get("depends_on", []) if isinstance(value, str)
    }
    required_plan_results = sorted(provider_ids | dependency_ids)
    completed_providers: list[dict[str, Any]] = []
    dependency_results: list[dict[str, Any]] = []
    for dependency_id in required_plan_results:
        result_path = change / f"results/{dependency_id}.md"
        result = _result_value(sources, result_path, f"resultado {dependency_id}")
        if result.get("status") != "completed":
            _context_fail(
                "PACK_INCOMPLETE", f"resultado de {dependency_id} não está concluído"
            )
        item = {"id": dependency_id, "result": result}
        dependency_results.append(item)
        required_refs.add(f"dependency-result:{change_id}/{dependency_id}")
        if dependency_id in provider_ids:
            provider = by_id.get(dependency_id, {})
            completed_providers.append(
                {
                    **item,
                    "contracts": sorted(
                        consumes
                        & {
                            contract
                            for contract in provider.get("provides", [])
                            if isinstance(contract, str)
                        }
                    ),
                }
            )

    if selected_task is not None:
        task_dependencies = sorted(
            value
            for value in selected_task.get("depends_on", [])
            if isinstance(value, str)
        )
        for dependency_id in task_dependencies:
            result_path = change / f"results/tasks/{plan_id}/{dependency_id}.md"
            result = _result_value(
                sources, result_path, f"resultado da tarefa {plan_id}/{dependency_id}"
            )
            if result.get("status") != "completed":
                _context_fail(
                    "PACK_INCOMPLETE",
                    f"resultado da tarefa {plan_id}/{dependency_id} não está concluído",
                )
            dependency_results.append(
                {"id": f"{plan_id}/{dependency_id}", "result": result}
            )
            required_refs.add(
                f"dependency-result:{change_id}/{plan_id}/{dependency_id}"
            )

    affected_consumers = [
        {
            "id": str(value["id"]),
            "contracts": sorted(
                provides
                & {
                    contract
                    for contract in value.get("consumes", [])
                    if isinstance(contract, str)
                }
            ),
        }
        for value in all_plans
        if value.get("id") != plan_id
        and provides
        & {contract for contract in value.get("consumes", []) if isinstance(contract, str)}
    ]

    decision_ids = _mapping_strings(selected_task or plan) | _mapping_strings(plan)
    architecture_decisions: list[dict[str, str]] = []
    if decision_ids:
        architecture_decisions = _section_slices(
            sources.text(change / "ARCHITECTURE.md", "ARCHITECTURE.md"),
            decision_ids,
            DECISION_HEADING,
            "ARCHITECTURE.md",
        )
        required_refs.update(f"architecture:{identifier}" for identifier in decision_ids)

    coherence = sources.frontmatter(change / "COHERENCE.md", "COHERENCE.md")
    roadmap: dict[str, Any] | None = None
    roadmap_path = change / "ROADMAP.md"
    if roadmap_path.is_file():
        roadmap_value = sources.frontmatter(roadmap_path, "ROADMAP.md")
        status = roadmap_value.get("status")
        roadmap = {
            "phase": plan_id,
            "status": status.get(plan_id) if isinstance(status, dict) else None,
        }
        required_refs.add(f"roadmap:{change_id}/{plan_id}")

    gates: list[Any] = []
    verifications = plan.get("verifications", [])
    if isinstance(verifications, list):
        gates.extend(verifications)
    if selected_task is not None and isinstance(selected_task.get("verify"), dict):
        gates.append(selected_task["verify"])

    return {
        "kind": "task" if selected_task else "plan",
        "state": _state_slice(state),
        "plan": (
            {key: value for key, value in plan.items() if key != "tasks"}
            if selected_task is not None
            else plan
        ),
        "task": selected_task,
        "roadmap": roadmap,
        "scope": scope,
        "spec_requirements": spec_requirements,
        "risk_coverage": risk_coverage,
        "model_nodes": model_nodes,
        "completed_providers": sorted(completed_providers, key=lambda item: item["id"]),
        "affected_consumers": sorted(affected_consumers, key=lambda item: item["id"]),
        "architecture_decisions": architecture_decisions,
        "gates": gates,
        "blockers": state.get("blockers", []),
        "open_findings": _open_findings(coherence, plan_id),
        "dependency_results": dependency_results,
        "ledger_tail": _ledger_tail(sources, change),
    }


def _quick_context(
    root: Path,
    sources: _PackSources,
    state: dict[str, Any],
    identifier: str,
    required_refs: set[str],
) -> dict[str, Any]:
    directory = _find_prefixed_directory(
        root, root / ".bianchini/quick", identifier, "quick"
    )
    brief = sources.frontmatter(directory / "BRIEF.md", f"brief {identifier}")
    progress_path = directory / "PROGRESS.md"
    result_path = directory / "RESULT.md"
    progress = (
        sources.frontmatter(progress_path, f"progresso {identifier}")
        if progress_path.is_file()
        else None
    )
    result = (
        sources.frontmatter(result_path, f"resultado {identifier}")
        if result_path.is_file()
        else None
    )
    latest_event = None
    if isinstance(progress, dict) and isinstance(progress.get("events"), list):
        latest_event = progress["events"][-1] if progress["events"] else None
    required_refs.add(f"quick:{identifier}")
    return {
        "kind": "quick",
        "state": _state_slice(state),
        "brief": brief,
        "latest_event": latest_event,
        "result": result,
        "gates": brief.get("gates", []),
        "blockers": brief.get("blockers", state.get("blockers", [])),
        "open_findings": brief.get("findings", []),
    }


def _debug_context(
    root: Path,
    sources: _PackSources,
    state: dict[str, Any],
    identifier: str,
    required_refs: set[str],
) -> dict[str, Any]:
    path = _find_debug(root, identifier)
    debug = sources.frontmatter(path, f"debug {identifier}")
    events = debug.get("events", [])
    latest_event = events[-1] if isinstance(events, list) and events else None
    required_refs.add(f"debug:{identifier}")
    return {
        "kind": "debug",
        "state": _state_slice(state),
        "debug": {
            key: debug.get(key)
            for key in (
                "id",
                "stage",
                "objective",
                "root_cause",
                "hypotheses",
                "experiments",
                "red",
                "green",
                "residual_risk",
            )
            if key in debug
        },
        "latest_event": latest_event,
        "gates": debug.get("gates", []),
        "blockers": debug.get("blockers", state.get("blockers", [])),
        "open_findings": debug.get("findings", []),
    }


def _rc_context(
    root: Path,
    sources: _PackSources,
    state: dict[str, Any],
    fingerprint: str,
    required_refs: set[str],
) -> dict[str, Any]:
    matches: list[tuple[Path, dict[str, Any]]] = []
    for cycle_root, label in (
        (root / ".bianchini/changes", "mudanças"),
        (root / ".bianchini/archive", "archive"),
    ):
        if not cycle_root.exists():
            continue
        for change in _children(cycle_root, label):
            if not change.is_dir():
                continue
            candidate = change / "results/HOMOLOGATION.md"
            if candidate.is_symlink():
                _context_fail("PATH_UNSAFE", "HOMOLOGATION.md não pode ser symlink")
            if candidate.is_file():
                value = sources.frontmatter(candidate, "HOMOLOGATION.md")
                if value.get("fingerprint") == fingerprint:
                    matches.append((candidate, value))
    if len(matches) != 1:
        _context_fail(
            "PACK_INCOMPLETE",
            "RC exige uma fonte explícita HOMOLOGATION.md com fingerprint exato em changes ou archive",
        )
    path, candidate = matches[0]
    required_refs.add(f"release-candidate:{fingerprint}")
    declared_refs = candidate.get("required_refs", [])
    if not isinstance(declared_refs, list) or not all(
        isinstance(value, str) for value in declared_refs
    ):
        _context_fail("PACK_INCOMPLETE", "RC.required_refs exige lista de paths")
    referenced: list[dict[str, Any]] = []
    for value in declared_refs:
        ref_candidates = [_relative_candidate(root, value, "RC.required_refs")]
        value_parts = Path(value).parts
        if (
            ".bianchini/archive" in path.relative_to(root).as_posix()
            and len(value_parts) >= 4
            and value_parts[:2] == (".bianchini", "changes")
        ):
            ref_candidates.append(
                _relative_candidate(
                    root,
                    Path(".bianchini/archive") / Path(*value_parts[2:]),
                    "RC.required_refs archive",
                )
            )
        existing_refs = [candidate for candidate in ref_candidates if candidate.is_file()]
        if len(existing_refs) != 1:
            _context_fail(
                "PACK_INCOMPLETE", f"referência do RC exige uma fonte íntegra: {value}"
            )
        ref_path = existing_refs[0]
        actual_value = ref_path.relative_to(root).as_posix()
        text = sources.text(ref_path, f"referência do RC {actual_value}")
        if ref_path.suffix == ".json":
            try:
                parsed: Any = json.loads(text)
            except json.JSONDecodeError:
                _context_fail("PACK_INCOMPLETE", f"referência JSON inválida do RC: {actual_value}")
        else:
            match = re.match(
                r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", text, re.DOTALL
            )
            if match is None:
                _context_fail("PACK_INCOMPLETE", f"referência do RC sem frontmatter: {actual_value}")
            try:
                parsed = json.loads(match.group(1))
            except json.JSONDecodeError:
                _context_fail("PACK_INCOMPLETE", f"referência do RC inválida: {actual_value}")
        referenced.append({"path": actual_value, "value": parsed})
        required_refs.add(f"evidence:{actual_value}")
    return {
        "kind": "release_candidate",
        "state": _state_slice(state),
        "release_candidate": candidate,
        "source": path.relative_to(root).as_posix(),
        "gates": candidate.get("gates", []),
        "blockers": candidate.get("blockers", state.get("blockers", [])),
        "open_findings": [
            item
            for item in candidate.get("findings", [])
            if isinstance(item, dict) and item.get("status", "open") == "open"
        ],
        "evidence": referenced,
    }


def _lesson_selectors(unit: str, context: dict[str, Any]) -> set[str]:
    selectors = {unit}
    plan = context.get("plan")
    if isinstance(plan, dict):
        for field in ("requirements", "provides", "consumes", "modules", "interfaces", "data"):
            values = plan.get(field, [])
            if isinstance(values, list):
                selectors.update(value for value in values if isinstance(value, str))
    task = context.get("task")
    if isinstance(task, dict):
        for field in ("covers", "files"):
            values = task.get(field, [])
            if isinstance(values, list):
                selectors.update(value for value in values if isinstance(value, str))
        if isinstance(task.get("risk_seam"), str):
            selectors.add(task["risk_seam"])
    for name in ("brief", "debug", "release_candidate"):
        value = context.get(name)
        if not isinstance(value, dict):
            continue
        for field in ("scope", "requirements", "paths", "contracts", "seams", "tags"):
            values = value.get(field, [])
            if isinstance(values, list):
                selectors.update(item for item in values if isinstance(item, str))
    return selectors


def _lesson_tags(value: dict[str, Any]) -> set[str]:
    tags = value.get("tags", [])
    if isinstance(tags, list):
        return {item for item in tags if isinstance(item, str)}
    if not isinstance(tags, dict):
        return set()
    result: set[str] = set()
    for tagged in tags.values():
        if isinstance(tagged, str):
            result.add(tagged)
        elif isinstance(tagged, list):
            result.update(item for item in tagged if isinstance(item, str))
    return result


def _approved_lessons(
    root: Path,
    sources: _PackSources,
    unit: str,
    context: dict[str, Any],
    required_refs: set[str],
) -> list[dict[str, Any]]:
    directory = root / ".bianchini/current/lessons"
    if not directory.exists():
        return []
    selectors = _lesson_selectors(unit, context)
    selected: list[dict[str, Any]] = []
    selected_ids: set[str] = set()
    for path in _children(directory, "lições aprovadas"):
        if not path.is_file() or path.suffix not in {".json", ".md"}:
            continue
        value = (
            sources.json(path, f"lição {path.name}")
            if path.suffix == ".json"
            else sources.frontmatter(path, f"lição {path.name}")
        )
        if value.get("status") != "approved" or value.get("active", True) is False:
            continue
        identifier = value.get("id")
        if not isinstance(identifier, str) or not re.fullmatch(r"L[0-9A-F]{12}", identifier):
            _context_fail("PACK_INCOMPLETE", f"lição aprovada possui id inválido: {path.name}")
        approved_by = value.get("approved_by")
        approved_digest = value.get("approved_digest")
        if not isinstance(approved_by, str) or not re.fullmatch(
            r"human:[^\s:][^\s]*", approved_by
        ):
            _context_fail(
                "PACK_INCOMPLETE", f"lesson:{identifier} não possui aprovação humana"
            )
        if not isinstance(approved_digest, str) or not re.fullmatch(
            r"[0-9a-f]{64}", approved_digest
        ):
            _context_fail(
                "PACK_INCOMPLETE", f"lesson:{identifier} possui digest de aprovação inválido"
            )
        candidate = {
            key: item
            for key, item in value.items()
            if key not in {"active", "approved_by", "approved_digest", "approved_at"}
        }
        candidate["status"] = "pending"
        candidate_digest = hashlib.sha256(_canonical_pack(candidate)).hexdigest()
        base = {key: item for key, item in candidate.items() if key != "id"}
        expected_id = "L" + hashlib.sha256(_canonical_pack(base)).hexdigest()[:12].upper()
        if candidate_digest != approved_digest or expected_id != identifier:
            _context_fail(
                "PACK_INCOMPLETE", f"lesson:{identifier} não deriva de candidato aprovado"
            )
        source_value = value.get("source")
        source_digest = value.get("source_digest")
        if (
            not isinstance(source_value, str)
            or not isinstance(source_digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", source_digest)
        ):
            _context_fail("PACK_INCOMPLETE", f"lesson:{identifier} não possui fonte")
        if not (_lesson_tags(value) & selectors):
            continue
        source_candidates = [
            _relative_candidate(root, source_value, f"lesson:{identifier}.source")
        ]
        source_parts = Path(source_value).parts
        if len(source_parts) >= 4 and source_parts[:2] == (".bianchini", "changes"):
            source_candidates.append(
                _relative_candidate(
                    root,
                    Path(".bianchini/archive") / Path(*source_parts[2:]),
                    f"lesson:{identifier}.archive_source",
                )
            )
        existing_sources = [candidate for candidate in source_candidates if candidate.is_file()]
        if len(existing_sources) != 1:
            _context_fail(
                "PACK_INCOMPLETE",
                f"lesson:{identifier} exige uma fonte histórica íntegra",
            )
        source = _safe_existing_file(
            root, existing_sources[0], f"lesson:{identifier}.source"
        )
        source_bytes = source.read_bytes()
        source_relative = source.relative_to(root).as_posix()
        sources.digests[source_relative] = hashlib.sha256(source_bytes).hexdigest()
        if sources.digests[source_relative] != source_digest:
            _context_fail("PACK_INCOMPLETE", f"lesson:{identifier} possui fonte alterada")
        try:
            expected_candidate = bm_learning.candidate_from_source(
                root, source, source_identity=source_value
            )
        except bm_learning.LearningError as error:
            _context_fail(
                "PACK_INCOMPLETE",
                f"lesson:{identifier} não deriva de fonte governada ({error.code})",
            )
        actual_candidate = {**candidate, "digest": approved_digest}
        if (
            expected_candidate is None
            or _canonical_pack(expected_candidate) != _canonical_pack(actual_candidate)
        ):
            _context_fail(
                "PACK_INCOMPLETE", f"lesson:{identifier} diverge da proposta da fonte"
            )
        selected.append(value)
        selected_ids.add(identifier)
        required_refs.add(f"lesson:{identifier}")
    for lesson in selected:
        conflicts = lesson.get("conflicts", [])
        if not isinstance(conflicts, list) or not all(
            isinstance(item, str) for item in conflicts
        ):
            _context_fail(
                "PACK_INCOMPLETE", f"lesson:{lesson.get('id')} possui conflicts inválido"
            )
        active_conflicts = sorted(set(conflicts) & selected_ids)
        if active_conflicts:
            _context_fail(
                "PACK_INCOMPLETE",
                f"lições relevantes conflitam: {lesson.get('id')} x {', '.join(active_conflicts)}",
            )
    return sorted(selected, key=lambda value: str(value["id"]))


def _canonical_pack(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _result_for_pack(
    root: Path,
    output: Path,
    content: bytes,
    payload: dict[str, Any],
    *,
    cache_hit: bool,
) -> dict[str, Any]:
    return {
        "path": output.relative_to(root).as_posix(),
        "digest": hashlib.sha256(content).hexdigest(),
        "bytes": len(content),
        "unit": payload["unit"],
        "source_digests": payload["source_digests"],
        "sources": payload["sources"],
        "required_refs": payload["required_refs"],
        "cache_hit": cache_hit,
    }


def _assemble_context_payload(root: Path, unit: str) -> dict[str, Any]:
    change_match = UNIT_CHANGE.fullmatch(unit)
    rc_match = UNIT_RC.fullmatch(unit)
    if not (
        change_match
        or UNIT_QUICK.fullmatch(unit)
        or UNIT_DEBUG.fullmatch(unit)
        or rc_match
    ):
        _context_fail("PACK_INCOMPLETE", f"identidade de unidade inválida: {unit}")

    sources = _PackSources(root)
    state = sources.frontmatter(root / ".bianchini/STATE.md", "STATE.md")
    required_refs = {"state:.bianchini/STATE.md"}
    if change_match:
        context = _change_context(
            root,
            sources,
            state,
            change_match.group(1),
            change_match.group(2),
            change_match.group(3),
            required_refs,
        )
    elif UNIT_QUICK.fullmatch(unit):
        context = _quick_context(root, sources, state, unit, required_refs)
    elif UNIT_DEBUG.fullmatch(unit):
        context = _debug_context(root, sources, state, unit, required_refs)
    else:
        assert rc_match is not None
        context = _rc_context(root, sources, state, rc_match.group(1), required_refs)

    context["approved_lessons"] = _approved_lessons(
        root, sources, unit, context, required_refs
    )
    head = _git_head(root)
    source_digests = {key: sources.digests[key] for key in sorted(sources.digests)}
    cache_material = {
        "unit": unit,
        "head": head,
        "source_digests": source_digests,
    }
    return {
        "schema_version": CONTEXT_PACK_SCHEMA_VERSION,
        "contract": CONTEXT_PACK_CONTRACT,
        "unit": unit,
        "head": head,
        "cache_key": hashlib.sha256(_canonical_pack(cache_material)).hexdigest(),
        "source_digests": source_digests,
        "sources": sorted(source_digests),
        "required_refs": sorted(required_refs),
        "context": context,
    }


def compile_context_pack(
    repo: str | Path,
    unit: str,
    output: str | Path | None = None,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    """Compila um pack mínimo, determinístico e vinculado às fontes atuais.

    O limite default de 16 KiB é inferior à menor baseline prescrita da Fase 0
    (22.686 bytes). Isso torna a redução verificável em bytes e arquivos; a API
    não estima nem declara redução de tokens.
    """

    root = _repo_root(repo)
    if not isinstance(unit, str):
        _context_fail("PACK_INCOMPLETE", "identidade da unidade exige string")
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes <= 0:
        _context_fail("PACK_INCOMPLETE", "max_bytes exige inteiro positivo")

    payload = _assemble_context_payload(root, unit)
    context = payload["context"]
    content = _canonical_pack(payload)
    if len(content) > max_bytes:
        largest = sorted(
            (
                {
                    "name": key,
                    "bytes": len(_canonical_pack({"value": value})),
                }
                for key, value in context.items()
            ),
            key=lambda item: (-item["bytes"], item["name"]),
        )[:5]
        _context_fail(
            "PACK_TOO_LARGE",
            f"pack possui {len(content)} bytes; limite {max_bytes}",
            details={"largest_consumers": largest},
        )

    safe_unit = re.sub(r"[^A-Za-z0-9._-]+", "-", unit).strip("-")
    target = _safe_output(
        root,
        output
        if output is not None
        else root / f".bianchini/.runtime/context/{safe_unit}.json",
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    target = _safe_output(root, target)
    if target.is_file() and target.read_bytes() == content:
        return _result_for_pack(root, target, content, payload, cache_hit=True)
    _atomic_write(target, content)
    return _result_for_pack(root, target, content, payload, cache_hit=False)


def verify_context_pack(repo: str | Path, path: str | Path) -> dict[str, Any]:
    """Valida formato canônico, HEAD e digests de toda fonte antes do uso."""

    root = _repo_root(repo)
    target = _safe_existing_file(root, _relative_candidate(root, path, "pack"), "pack")
    content = target.read_bytes()
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        _context_fail("STALE_EVIDENCE", f"pack possui JSON inválido na linha {error.lineno}")
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        _context_fail("STALE_EVIDENCE", "pack possui schema_version inválido")
    if payload.get("contract") != CONTEXT_PACK_CONTRACT:
        _context_fail("STALE_EVIDENCE", "pack possui contrato inválido")
    if _canonical_pack(payload) != content:
        _context_fail("STALE_EVIDENCE", "pack não está em forma canônica")
    unit = payload.get("unit")
    if not isinstance(unit, str) or not (
        UNIT_CHANGE.fullmatch(unit)
        or UNIT_QUICK.fullmatch(unit)
        or UNIT_DEBUG.fullmatch(unit)
        or UNIT_RC.fullmatch(unit)
    ):
        _context_fail("STALE_EVIDENCE", "identidade do pack inválida")
    if payload.get("head") != _git_head(root):
        _context_fail("STALE_EVIDENCE", "HEAD mudou depois da montagem do pack")
    source_digests = payload.get("source_digests")
    sources = payload.get("sources")
    if not isinstance(source_digests, dict) or sources != sorted(source_digests):
        _context_fail("STALE_EVIDENCE", "índice de fontes do pack é inválido")
    for relative, expected in source_digests.items():
        if not isinstance(relative, str) or not isinstance(expected, str):
            _context_fail("STALE_EVIDENCE", "digest de fonte inválido")
        try:
            source = _safe_existing_file(root, root / relative, f"fonte {relative}")
        except ContextPackError as error:
            _context_fail(
                "STALE_EVIDENCE", f"fonte inválida ou ausente: {relative} ({error.code})"
            )
        actual = hashlib.sha256(source.read_bytes()).hexdigest()
        if actual != expected:
            _context_fail("STALE_EVIDENCE", f"fonte mudou: {relative}")
    cache_material = {
        "unit": unit,
        "head": payload["head"],
        "source_digests": source_digests,
    }
    expected_cache_key = hashlib.sha256(_canonical_pack(cache_material)).hexdigest()
    if payload.get("cache_key") != expected_cache_key:
        _context_fail("STALE_EVIDENCE", "cache key do pack diverge")
    try:
        expected_payload = _assemble_context_payload(root, unit)
    except ContextPackError as error:
        _context_fail(
            "STALE_EVIDENCE", f"pack não pode ser recompilado: {error.code}"
        )
    if _canonical_pack(expected_payload) != content:
        _context_fail("STALE_EVIDENCE", "conteúdo derivado do pack diverge das fontes")
    return _result_for_pack(root, target, content, payload, cache_hit=True)


__all__ = [
    "CONTEXT_PACK_CONTRACT",
    "CONTEXT_PACK_SCHEMA_VERSION",
    "DEFAULT_MAX_BYTES",
    "PRESCRIBED_BASELINE_MIN_BYTES",
    "ContextPackError",
    "compile_context_pack",
    "destination_path",
    "extract_markdown_section",
    "hydrate_task_context",
    "mutation_mode_for_change",
    "parse_readiness_refs",
    "readiness_index",
    "resolve_spec_ref",
    "slugify_heading",
    "strongest_mutation_mode",
    "validate_quality_v2_plan",
    "verify_context_pack",
]
