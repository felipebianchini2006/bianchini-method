#!/usr/bin/env python3
"""Validação de unidades v2 e projeção compacta de contexto operacional."""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from bm_feature_support import (
    FIX_ROUNDS_BY_PROFILE,
    confined_path,
    field_value,
    json_document,
    sha256_bytes,
    unit_sections,
)


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
                "use categoria factual suportada por bm.py policy"
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
