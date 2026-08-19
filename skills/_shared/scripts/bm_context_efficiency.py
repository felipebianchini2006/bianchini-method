#!/usr/bin/env python3
"""Primitivas determinísticas de eficiência de contexto do Bianchini Method."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import unicodedata
from pathlib import Path
from typing import Any


EXIT_INVALID = 2
EXIT_BLOCKED = 3


class ContextEfficiencyError(Exception):
    def __init__(self, message: str, exit_code: int = EXIT_INVALID):
        super().__init__(message)
        self.exit_code = exit_code


UNIT_HEADING = re.compile(
    r"(?m)^###\s+(?:Tarefa|Task|Slice|Grupo|Group)\s+[^\n]+$",
    re.IGNORECASE,
)
READINESS_ID = re.compile(r"^(?:D|A|P|U|S|DS|SD)-[0-9]{3}$")
REQUIREMENT_HEADING = re.compile(
    r"^(#{2,6})\s+.*?\b([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-[0-9]{3,})\b.*$"
)

KNOWN_CHANGE_KINDS = frozenset(
    {
        "api",
        "authorization",
        "behavioral",
        "bug",
        "business-rule",
        "calculation",
        "configuration",
        "contract",
        "copy",
        "data-transform",
        "database",
        "docs",
        "documentation",
        "financial",
        "infrastructure",
        "integration",
        "inventory",
        "mechanical",
        "migration",
        "money",
        "offline",
        "parser",
        "payment",
        "permission",
        "refactor",
        "security",
        "state-machine",
        "stock",
        "style",
        "sync",
        "visual",
    }
)
MUTATION_RELEVANT_CHANGES = frozenset(
    {
        "authorization",
        "business-rule",
        "calculation",
        "data-transform",
        "financial",
        "inventory",
        "migration",
        "money",
        "offline",
        "parser",
        "payment",
        "permission",
        "security",
        "state-machine",
        "stock",
        "sync",
    }
)
PURE_NON_LOGIC_CHANGES = frozenset(
    {"copy", "docs", "documentation", "mechanical", "style", "visual"}
)
READINESS_COLLECTIONS = (
    "decisions",
    "assumptions",
    "pitfalls",
    "user_actions",
    "spikes",
    "design_surfaces",
    "spec_deltas",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_document(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ContextEfficiencyError(f"{label} ausente: {path}")
    text = path.read_text(encoding="utf-8")
    fenced = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    candidate = fenced.group(1) if fenced else text
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as error:
        raise ContextEfficiencyError(
            f"{label}: JSON inválido na linha {error.lineno}"
        ) from error
    if not isinstance(value, dict):
        raise ContextEfficiencyError(f"{label}: esperado objeto JSON")
    return value


def _root_path(root: Path, value: str | Path, label: str) -> Path:
    base = root.resolve()
    candidate = Path(value)
    lexical = candidate if candidate.is_absolute() else base / candidate
    resolved = lexical.resolve()
    try:
        resolved.relative_to(base)
    except ValueError as error:
        raise ContextEfficiencyError(f"{label} fora da raiz: {value}") from error
    current = base
    try:
        relative = lexical.absolute().relative_to(base)
    except ValueError as error:
        raise ContextEfficiencyError(f"{label} fora da raiz: {value}") from error
    for part in relative.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise ContextEfficiencyError(f"{label} atravessa symlink: {current}")
    return resolved


def _field(section: str, name: str) -> str | None:
    match = re.search(
        rf"(?mi)^\*\*{re.escape(name)}:\*\*\s*(.*?)\s*$",
        section,
    )
    return match.group(1).strip() if match else None


def _unit_sections(content: str) -> list[tuple[str, str]]:
    matches = list(UNIT_HEADING.finditer(content))
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        sections.append((match.group(0).strip(), content[match.start():end].rstrip() + "\n"))
    return sections


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip().strip("`") for item in re.split(r"\s*[,;]\s*", value) if item.strip()]


def _readiness_index(readiness: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for collection in READINESS_COLLECTIONS:
        values = readiness.get(collection)
        if not isinstance(values, list):
            continue
        for item in values:
            if not isinstance(item, dict):
                continue
            identifier = item.get("id")
            if isinstance(identifier, str) and READINESS_ID.fullmatch(identifier):
                index[identifier] = item
    return index


def quality_v2_unit_contract_errors(
    state: dict[str, Any], root: Path
) -> list[str]:
    """Valida os campos que ligam cada unidade v2 à policy e ao readiness."""
    if state.get("planning", {}).get("quality_version") != 2:
        return []
    errors: list[str] = []
    readiness_value = state.get("planning", {}).get("readiness")
    if not isinstance(readiness_value, str) or not readiness_value:
        return ["planning.readiness: necessário para validar unidades quality v2"]
    try:
        readiness_path = _root_path(root, readiness_value, "planning.readiness")
        readiness = _json_document(readiness_path, "READINESS.md")
    except ContextEfficiencyError as error:
        return [str(error)]
    readiness_index = _readiness_index(readiness)
    for plan in state.get("plans", []):
        plan_id = str(plan.get("id") or "desconhecido")
        plan_value = plan.get("path")
        if not isinstance(plan_value, str) or not plan_value:
            continue
        try:
            plan_path = _root_path(root, plan_value, f"plano {plan_id}")
        except ContextEfficiencyError as error:
            errors.append(str(error))
            continue
        if not plan_path.is_file():
            continue
        for heading, section in _unit_sections(plan_path.read_text(encoding="utf-8")):
            prefix = f"plano {plan_id} / {heading}"
            change = _field(section, "Change")
            if not change:
                errors.append(f"{prefix}: campo Change ausente")
            else:
                normalized_change = change.strip().lower().replace("_", "-")
                if normalized_change not in KNOWN_CHANGE_KINDS:
                    errors.append(f"{prefix}: Change inválido: {change}")
            raw_refs = _field(section, "Readiness refs")
            if not raw_refs:
                errors.append(f"{prefix}: campo Readiness refs ausente")
                continue
            refs = _csv(raw_refs)
            if not refs:
                errors.append(f"{prefix}: Readiness refs deve conter ao menos um ID")
                continue
            for reference in refs:
                if not READINESS_ID.fullmatch(reference):
                    errors.append(f"{prefix}: Readiness ref inválida: {reference}")
                    continue
                item = readiness_index.get(reference)
                if item is None:
                    errors.append(f"{prefix}: Readiness ref inexistente: {reference}")
                    continue
                destinations = item.get("destinations")
                destination_paths = {
                    value.split("#", 1)[0].strip()
                    for value in destinations or []
                    if isinstance(value, str)
                }
                if plan_value not in destination_paths:
                    errors.append(
                        f"{prefix}: Readiness ref {reference} não aponta para o plano {plan_id}"
                    )
    return errors


def _selector_values(task: str | None, tasks: str | None) -> list[str]:
    selected: list[str] = []
    for token in (item.strip() for item in (tasks or task or "").split(",")):
        if not token:
            continue
        interval = re.fullmatch(r"([0-9]+)\s*-\s*([0-9]+)", token)
        if interval:
            start, end = map(int, interval.groups())
            if end < start:
                raise ContextEfficiencyError(f"intervalo de unidades inválido: {token}")
            selected.extend(str(value) for value in range(start, end + 1))
        elif re.fullmatch(r"[A-Za-z0-9_.-]+", token):
            selected.append(token)
        else:
            raise ContextEfficiencyError(f"seletor de unidade inválido: {token}")
    values = list(dict.fromkeys(selected))
    if not values:
        raise ContextEfficiencyError("nenhuma unidade selecionada")
    return values


def _select_units(
    content: str,
    task: str | None,
    tasks: str | None,
    group: str | None,
) -> list[tuple[str, str]]:
    units = _unit_sections(content)
    if group:
        expected = group.strip().casefold()
        selected = [item for item in units if item[0].removeprefix("### ").casefold() == expected]
        if not selected:
            raise ContextEfficiencyError(f"grupo {group!r} não encontrado")
        return selected
    labels = _selector_values(task, tasks)
    selected: list[tuple[str, str]] = []
    for label in labels:
        pattern = re.compile(
            rf"^###\s+(?:Tarefa|Task|Slice|Grupo|Group)\s+{re.escape(label)}\b",
            re.IGNORECASE,
        )
        match = next((item for item in units if pattern.search(item[0])), None)
        if match is None:
            raise ContextEfficiencyError(f"unidade {label} não encontrada")
        selected.append(match)
    return selected


def _normalize(value: str) -> str:
    text = unicodedata.normalize("NFKD", value.casefold())
    return "".join(character for character in text if not unicodedata.combining(character))


def _slug(value: str) -> str:
    normalized = _normalize(value)
    normalized = re.sub(r"[^a-z0-9\s-]", "", normalized)
    return re.sub(r"[\s-]+", "-", normalized).strip("-")


def _markdown_section(content: str, anchor: str, reference: str) -> str:
    lines = content.splitlines()
    headings: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if match:
            headings.append((index, len(match.group(1)), match.group(2)))
    wanted = anchor.lstrip("#")
    for position, (start, level, title) in enumerate(headings):
        if _slug(title) != wanted and _normalize(title).strip() != _normalize(wanted).strip():
            continue
        end = len(lines)
        for next_start, next_level, _ in headings[position + 1:]:
            if next_level <= level:
                end = next_start
                break
        return "\n".join(lines[start:end]).rstrip() + "\n"
    raise ContextEfficiencyError(
        f"Spec ref não resolvida: {reference}; seção #{anchor} ausente"
    )


def _resolve_spec(root: Path, change_root: Path, reference: str) -> tuple[Path, str | None]:
    path_value, separator, anchor = reference.partition("#")
    relative = Path(path_value.strip())
    candidates = [root / relative, change_root / relative]
    selected = next((candidate.resolve() for candidate in candidates if candidate.is_file()), None)
    if selected is None:
        raise ContextEfficiencyError(f"Spec ref aponta arquivo ausente: {reference}")
    try:
        selected.relative_to(root.resolve())
    except ValueError as error:
        raise ContextEfficiencyError(f"Spec ref fora da raiz: {reference}") from error
    return selected, anchor.strip() if separator else None


def write_hydrated_task_brief(
    *,
    plan: Path,
    task: str | None,
    tasks: str | None,
    group: str | None,
    state_path: Path,
    root: Path,
    output: Path,
) -> dict[str, Any]:
    base = root.resolve()
    state_file = _root_path(base, state_path, "PROJECT_STATE")
    state = _json_document(state_file, "PROJECT_STATE")
    approval = state.get("approval", {})
    digest = approval.get("package", {}).get("manifest_digest")
    if approval.get("status") != "approved" or not isinstance(digest, str) or not re.fullmatch(
        r"[0-9a-f]{64}", digest
    ):
        raise ContextEfficiencyError(
            "task-brief hidratado exige pacote integralmente aprovado",
            EXIT_BLOCKED,
        )
    plan_file = _root_path(base, plan, "plano")
    plan_relative = plan_file.relative_to(base).as_posix()
    plan_state = next(
        (item for item in state.get("plans", []) if item.get("path") == plan_relative),
        None,
    )
    if plan_state is None:
        raise ContextEfficiencyError("plano não pertence ao PROJECT_STATE aprovado")
    scratch = (base / ".superpowers").resolve()
    output_path = _root_path(base, output, "saída do task-brief")
    try:
        output_path.relative_to(scratch)
    except ValueError as error:
        raise ContextEfficiencyError(
            "task-brief hidratado deve ser gravado sob .superpowers/"
        ) from error
    content = plan_file.read_text(encoding="utf-8")
    selected = _select_units(content, task, tasks, group)
    readiness_value = state.get("planning", {}).get("readiness")
    if not isinstance(readiness_value, str) or not readiness_value:
        raise ContextEfficiencyError("PROJECT_STATE não aponta READINESS.md")
    readiness_file = _root_path(base, readiness_value, "READINESS.md")
    readiness = _json_document(readiness_file, "READINESS.md")
    readiness_index = _readiness_index(readiness)

    readiness_refs: list[str] = []
    spec_refs: list[str] = []
    changes: list[str] = []
    seams: list[str] = []
    for _, section in selected:
        for reference in _csv(_field(section, "Readiness refs")):
            if reference not in readiness_refs:
                readiness_refs.append(reference)
        for reference in _csv(_field(section, "Spec refs")):
            if reference not in spec_refs:
                spec_refs.append(reference)
        change = _field(section, "Change")
        if change and change not in changes:
            changes.append(change)
        seam = _field(section, "Test seams")
        if seam and seam not in seams:
            seams.append(seam)
    missing = [reference for reference in readiness_refs if reference not in readiness_index]
    if missing:
        raise ContextEfficiencyError(
            "task-brief contém Readiness refs inexistentes: " + ", ".join(missing)
        )

    change_root_value = state.get("planning", {}).get("change_root")
    if not isinstance(change_root_value, str) or not change_root_value:
        raise ContextEfficiencyError("PROJECT_STATE não aponta planning.change_root")
    change_root = _root_path(base, change_root_value, "planning.change_root")
    spec_blocks: list[tuple[str, str]] = []
    for reference in spec_refs:
        spec_file, anchor = _resolve_spec(base, change_root, reference)
        spec_content = spec_file.read_text(encoding="utf-8")
        block = _markdown_section(spec_content, anchor, reference) if anchor else spec_content
        spec_blocks.append((reference, block.rstrip() + "\n"))

    ledger_value = plan_state.get("ledger")
    ledger_lines: list[str] = []
    if isinstance(ledger_value, str) and ledger_value:
        ledger = _root_path(base, ledger_value, "ledger")
        if ledger.is_file():
            ledger_lines = ledger.read_text(encoding="utf-8").splitlines()[-80:]
    active = state.get("active_execution") if isinstance(state.get("active_execution"), dict) else {}
    fast_commands = state.get("verification", {}).get("fast", {}).get("commands", [])
    headings = [heading for heading, _ in selected]
    unit_body = "\n".join(section for _, section in selected).rstrip() + "\n"
    readiness_body = []
    for reference in readiness_refs:
        readiness_body.append(
            f"### {reference}\n\n```json\n"
            + json.dumps(readiness_index[reference], ensure_ascii=False, indent=2)
            + "\n```"
        )
    specs_body = []
    for reference, block in spec_blocks:
        specs_body.append(f"### `{reference}`\n\n{block.rstrip()}")
    verification_body = (
        "\n".join(f"- `{command}`" for command in fast_commands)
        if fast_commands
        else "- Nenhum comando configurado."
    )
    ledger_body = "\n".join(ledger_lines) if ledger_lines else "Nenhum checkpoint registrado."
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        "# Task Brief Hidratado\n\n"
        f"- Package digest: `{digest}`\n"
        f"- State SHA-256: `{_sha256(state_file)}`\n"
        f"- Plan: `{plan_relative}`\n"
        f"- Plan SHA-256: `{_sha256(plan_file)}`\n"
        f"- Plan ID: `{plan_state.get('id')}`\n"
        f"- Risk: `{plan_state.get('risk')}`\n"
        f"- Change: `{', '.join(changes) or 'não declarado'}`\n"
        f"- Risk seams: `{'; '.join(seams) or ', '.join(plan_state.get('test_seams', []))}`\n"
        f"- Active gate: `{active.get('gate') or 'nenhum'}`\n"
        f"- Units: `{', '.join(headings)}`\n\n"
        "## Unidade selecionada\n\n"
        + unit_body
        + "\n## Readiness referenciado\n\n"
        + ("\n\n".join(readiness_body) if readiness_body else "Nenhuma referência.")
        + "\n\n## Specs referenciadas\n\n"
        + ("\n\n".join(specs_body) if specs_body else "Nenhuma referência.")
        + "\n\n## verification.fast\n\n"
        + verification_body
        + "\n\n## Final do ledger\n\n```text\n"
        + ledger_body
        + "\n```\n",
        encoding="utf-8",
    )
    return {
        "brief": str(output_path),
        "hydrated": True,
        "package_digest": digest,
        "plan": plan_relative,
        "plan_id": plan_state.get("id"),
        "tasks": headings,
        "readiness_refs": readiness_refs,
        "spec_refs": spec_refs,
        "fast_commands": fast_commands,
        "ledger_lines": len(ledger_lines),
    }


def _requirements(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    headings: list[tuple[int, int, str]] = []
    for index, line in enumerate(lines):
        match = REQUIREMENT_HEADING.match(line)
        if match:
            headings.append((index, len(match.group(1)), match.group(2)))
    requirements: dict[str, str] = {}
    for position, (start, level, identifier) in enumerate(headings):
        if identifier in requirements:
            raise ContextEfficiencyError(
                f"ID de requisito duplicado em {path}: {identifier}"
            )
        end = len(lines)
        for next_start, next_level, _ in headings[position + 1:]:
            if next_level <= level:
                end = next_start
                break
        requirements[identifier] = "\n".join(lines[start:end]).rstrip() + "\n"
    if not requirements:
        raise ContextEfficiencyError(
            f"spec sem requisitos identificáveis em headings: {path}"
        )
    return requirements


def _indent_markdown(value: str) -> str:
    return "\n".join("    " + line if line else "" for line in value.rstrip().splitlines())


def write_spec_diff(base: Path, target: Path, output: Path) -> dict[str, Any]:
    if not base.is_file() or not target.is_file():
        raise ContextEfficiencyError("spec-diff exige --base e --target existentes")
    if output.resolve() in {base.resolve(), target.resolve()}:
        raise ContextEfficiencyError("spec-diff não pode sobrescrever base ou target")
    before = _requirements(base)
    after = _requirements(target)
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    modified = sorted(
        identifier
        for identifier in set(before) & set(after)
        if before[identifier] != after[identifier]
    )
    sections: list[str] = [
        "# Spec Diff",
        "",
        f"- Base: `{base}`",
        f"- Base SHA-256: `{_sha256(base)}`",
        f"- Target: `{target}`",
        f"- Target SHA-256: `{_sha256(target)}`",
        "",
        "## ADDED",
        "",
    ]
    if added:
        for identifier in added:
            sections.extend([f"### {identifier}", "", _indent_markdown(after[identifier]), ""])
    else:
        sections.extend(["Nenhum.", ""])
    sections.extend(["## MODIFIED", ""])
    if modified:
        for identifier in modified:
            sections.extend(
                [
                    f"### {identifier}",
                    "",
                    "#### Antes",
                    "",
                    _indent_markdown(before[identifier]),
                    "",
                    "#### Depois",
                    "",
                    _indent_markdown(after[identifier]),
                    "",
                ]
            )
    else:
        sections.extend(["Nenhum.", ""])
    sections.extend(["## REMOVED", ""])
    if removed:
        for identifier in removed:
            sections.extend([f"### {identifier}", "", _indent_markdown(before[identifier]), ""])
    else:
        sections.extend(["Nenhum.", ""])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(sections).rstrip() + "\n", encoding="utf-8")
    return {
        "diff": str(output),
        "base": str(base),
        "base_digest": _sha256(base),
        "target": str(target),
        "target_digest": _sha256(target),
        "added": added,
        "modified": modified,
        "removed": removed,
        "unchanged": sorted(set(before) & set(after) - set(modified)),
    }


def _git_head(root: Path) -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ContextEfficiencyError(
            completed.stderr.strip() or "não foi possível determinar HEAD"
        )
    return completed.stdout.strip()


def _mutation_mode(risk: str, change: str) -> str:
    normalized = change.strip().lower().replace("_", "-")
    if risk == "low" or normalized in PURE_NON_LOGIC_CHANGES:
        return "not_required"
    if risk in {"high", "critical"}:
        return "required_selective"
    if normalized in MUTATION_RELEVANT_CHANGES:
        return "selective"
    return "not_required"


def _change_for_seam(plan_content: str, risk_seam: str) -> str:
    wanted = _normalize(risk_seam)
    matches: list[str] = []
    for heading, section in _unit_sections(plan_content):
        seams = _field(section, "Test seams") or ""
        if wanted and wanted in _normalize(seams):
            change = _field(section, "Change")
            if not change:
                raise ContextEfficiencyError(
                    f"{heading}: Change ausente para o risk seam {risk_seam}"
                )
            matches.append(change.strip().lower().replace("_", "-"))
    values = list(dict.fromkeys(matches))
    if not values:
        raise ContextEfficiencyError(
            f"risk seam não encontrado nas unidades do plano: {risk_seam}"
        )
    if len(values) > 1:
        raise ContextEfficiencyError(
            f"risk seam ambíguo com múltiplos Change: {risk_seam}"
        )
    return values[0]


def verify_mutation_evidence(
    *,
    state_path: Path,
    root: Path,
    plan_id: str,
    risk_seam: str,
    tool: str,
    command: str,
    report_path: Path,
    output: Path,
) -> dict[str, Any]:
    base = root.resolve()
    state_file = _root_path(base, state_path, "PROJECT_STATE")
    report_file = _root_path(base, report_path, "mutation report")
    output_file = _root_path(base, output, "mutation evidence output")
    state = _json_document(state_file, "PROJECT_STATE")
    plan = next((item for item in state.get("plans", []) if item.get("id") == plan_id), None)
    if plan is None:
        raise ContextEfficiencyError(f"plano inexistente: {plan_id}")
    plan_value = plan.get("path")
    if not isinstance(plan_value, str):
        raise ContextEfficiencyError(f"plano {plan_id} sem path")
    plan_file = _root_path(base, plan_value, f"plano {plan_id}")
    change = _change_for_seam(plan_file.read_text(encoding="utf-8"), risk_seam)
    risk = str(plan.get("risk") or "low")
    mutation_mode = _mutation_mode(risk, change)
    report = _json_document(report_file, "mutation report")
    if report.get("schema_version") != 1:
        raise ContextEfficiencyError("mutation report: schema_version esperado 1")
    candidate = state.get("release", {}).get("candidate")
    expected_revision = (
        candidate.get("revision")
        if isinstance(candidate, dict) and candidate.get("revision")
        else _git_head(base)
    )
    report_revision = report.get("revision")
    if report_revision != expected_revision:
        raise ContextEfficiencyError(
            "BLOQUEADO: evidência de mutação obsoleta; "
            f"report={report_revision!r}, esperado={expected_revision!r}",
            EXIT_BLOCKED,
        )
    mutants = report.get("mutants")
    if not isinstance(mutants, list) or not all(isinstance(item, dict) for item in mutants):
        raise ContextEfficiencyError("mutation report: mutants deve ser lista de objetos")
    if mutation_mode in {"selective", "required_selective"} and not mutants:
        raise ContextEfficiencyError(
            "BLOQUEADO: política seletiva exige ao menos um mutante executado",
            EXIT_BLOCKED,
        )
    identifiers: set[str] = set()
    counts = {
        "killed": 0,
        "survived": 0,
        "timeout": 0,
        "no_coverage": 0,
        "ignored": 0,
    }
    classifications = {"equivalent", "unreachable", "non_material", "behavior_gap"}
    blocking: list[str] = []
    normalized_mutants: list[dict[str, Any]] = []
    for index, mutant in enumerate(mutants):
        identifier = mutant.get("id")
        status = mutant.get("status")
        if not isinstance(identifier, str) or not identifier.strip():
            raise ContextEfficiencyError(f"mutation report: mutant {index} sem id")
        if identifier in identifiers:
            raise ContextEfficiencyError(f"mutation report: mutant duplicado {identifier}")
        identifiers.add(identifier)
        if status not in counts:
            raise ContextEfficiencyError(
                f"mutation report: status inválido em {identifier}: {status}"
            )
        counts[status] += 1
        normalized = {"id": identifier, "status": status}
        if status in {"survived", "timeout", "no_coverage"}:
            classification = mutant.get("classification")
            justification = mutant.get("justification")
            if classification not in classifications:
                raise ContextEfficiencyError(
                    f"BLOQUEADO: survivor {identifier} sem classificação válida",
                    EXIT_BLOCKED,
                )
            if not isinstance(justification, str) or not justification.strip():
                raise ContextEfficiencyError(
                    f"BLOQUEADO: survivor {identifier} sem justificativa",
                    EXIT_BLOCKED,
                )
            normalized.update(
                {"classification": classification, "justification": justification.strip()}
            )
            if classification == "behavior_gap":
                approved_behavior = mutant.get("approved_behavior")
                impact = mutant.get("risk")
                if not isinstance(approved_behavior, bool):
                    raise ContextEfficiencyError(
                        f"BLOQUEADO: survivor {identifier} behavior_gap exige approved_behavior",
                        EXIT_BLOCKED,
                    )
                if impact not in {"low", "medium", "high", "critical"}:
                    raise ContextEfficiencyError(
                        f"BLOQUEADO: survivor {identifier} behavior_gap exige risk",
                        EXIT_BLOCKED,
                    )
                normalized.update(
                    {"approved_behavior": approved_behavior, "risk": impact}
                )
                if approved_behavior and impact in {"high", "critical"}:
                    blocking.append(identifier)
        normalized_mutants.append(normalized)
    if blocking:
        raise ContextEfficiencyError(
            "BLOQUEADO: survivor altera comportamento aprovado alto/crítico: "
            + ", ".join(blocking),
            EXIT_BLOCKED,
        )
    if not tool.strip() or not command.strip():
        raise ContextEfficiencyError("mutation-evidence exige tool e command não vazios")
    payload: dict[str, Any] = {
        "schema_version": 1,
        "type": "mutation",
        "result": "passed",
        "status": "passed",
        "tool": tool.strip(),
        "command": command.strip(),
        "plan": plan_id,
        "risk_seam": risk_seam,
        "risk": risk,
        "change": change,
        "mutation_policy": mutation_mode,
        "global_score_gate": False,
        "revision": expected_revision,
        "report": report_file.relative_to(base).as_posix(),
        "report_digest": _sha256(report_file),
        "killed": counts["killed"],
        "survived": counts["survived"] + counts["timeout"] + counts["no_coverage"],
        "ignored": counts["ignored"],
        "counts": counts,
        "mutants": normalized_mutants,
    }
    if isinstance(candidate, dict):
        payload.update(
            {
                "rc": candidate.get("id"),
                "build": candidate.get("build"),
                "checksum": candidate.get("checksum"),
            }
        )
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {**payload, "output": str(output_file)}
