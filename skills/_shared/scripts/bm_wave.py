#!/usr/bin/env python3
"""Projeção determinística e somente leitura da próxima onda executável."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from bm_coherence import DependencyGraph, TaskDependencyGraph
from bm_project_model import PlanContract


CHANGE_PREFIX = re.compile(r"^C[0-9]{3}$")
CHANGE_FULL = re.compile(r"^C[0-9]{3}-[a-z0-9]+(?:-[a-z0-9]+)*$")
PLAN_ID = re.compile(r"^P[0-9]{2,}$")
TASK_ID = re.compile(r"^T[0-9]{2,}$")
APPROVED_STATUSES = frozenset({"approved", "approved_with_stale"})
BLOCKING_SEVERITIES = frozenset({"ERROR", "WARNING"})


class WaveError(ValueError):
    """Erro fechado da projeção, com código estável para o CLI."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def _fail(code: str, message: str) -> None:
    raise WaveError(code, message)


def _root(repo: str | Path) -> Path:
    raw = Path(repo)
    if raw.is_symlink():
        _fail("PATH_UNSAFE", "repo não pode ser symlink")
    root = raw.absolute()
    if not root.is_dir() or not (root / ".bianchini").is_dir():
        _fail("WAVE_INCOMPLETE", "repo 0.4 exige .bianchini")
    _reject_symlink_chain(root, root / ".bianchini", ".bianchini")
    return root


def _reject_symlink_chain(root: Path, target: Path, label: str) -> None:
    lexical = target.absolute()
    try:
        relative = lexical.relative_to(root)
    except ValueError:
        try:
            relative = lexical.resolve(strict=False).relative_to(root.resolve())
        except ValueError:
            _fail("PATH_UNSAFE", f"{label} sai do repo")
    if any(part in {"", ".", ".."} for part in relative.parts):
        _fail("PATH_UNSAFE", f"{label} contém traversal")
    if any(part.casefold() == ".planning" for part in relative.parts):
        _fail("PATH_UNSAFE", f"{label} usa namespace estrangeiro")
    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            _fail("PATH_UNSAFE", f"{label} atravessa symlink: {current}")


def _safe_file(root: Path, path: Path, label: str) -> Path:
    _reject_symlink_chain(root, path, label)
    if path.is_symlink():
        _fail("PATH_UNSAFE", f"{label} não pode ser symlink")
    if not path.is_file():
        _fail("WAVE_INCOMPLETE", f"{label} ausente")
    return path


def _children(root: Path, directory: Path, label: str) -> list[Path]:
    _reject_symlink_chain(root, directory, label)
    if directory.is_symlink():
        _fail("PATH_UNSAFE", f"{label} não pode ser symlink")
    if not directory.is_dir():
        _fail("WAVE_INCOMPLETE", f"{label} ausente")
    children = sorted(directory.iterdir(), key=lambda path: path.name)
    for child in children:
        if child.is_symlink():
            _fail("PATH_UNSAFE", f"{label} contém symlink: {child.name}")
    return children


def _frontmatter(root: Path, path: Path, label: str) -> dict[str, Any]:
    source = _safe_file(root, path, label)
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        _fail("WAVE_INCOMPLETE", f"{label} não pode ser lido: {error}")
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", text, re.DOTALL)
    if match is None:
        _fail("WAVE_INCOMPLETE", f"{label} exige frontmatter JSON")
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError as error:
        _fail("WAVE_INCOMPLETE", f"{label} possui JSON inválido na linha {error.lineno}")
    if not isinstance(value, dict):
        _fail("WAVE_INCOMPLETE", f"{label} exige objeto")
    return value


def _change_directory(root: Path, reference: str) -> Path:
    if not isinstance(reference, str) or not (
        CHANGE_PREFIX.fullmatch(reference) or CHANGE_FULL.fullmatch(reference)
    ):
        _fail("WAVE_INCOMPLETE", f"ID de mudança inválido: {reference}")
    changes = root / ".bianchini/changes"
    candidates = [
        child
        for child in _children(root, changes, "changes")
        if child.is_dir()
        and (
            child.name == reference
            or (
                CHANGE_PREFIX.fullmatch(reference)
                and child.name.startswith(reference + "-")
            )
        )
    ]
    if len(candidates) != 1:
        _fail(
            "WAVE_INCOMPLETE",
            f"{reference} exige uma mudança; encontradas {len(candidates)}",
        )
    return candidates[0]


def _roadmap_phases(value: dict[str, Any]) -> list[dict[str, Any]]:
    if value.get("schema_version") != 1 or value.get("planning_contract") != 2:
        _fail("WAVE_INCOMPLETE", "ROADMAP.md exige contrato de planejamento 2")
    phases = value.get("phases")
    if not isinstance(phases, list) or not phases:
        _fail("WAVE_INCOMPLETE", "ROADMAP.md.phases exige lista não vazia")
    if not all(isinstance(phase, dict) for phase in phases):
        _fail("WAVE_INCOMPLETE", "ROADMAP.md possui fase inválida")
    identifiers = [phase.get("id") for phase in phases]
    if not all(isinstance(identifier, str) and PLAN_ID.fullmatch(identifier) for identifier in identifiers):
        _fail("WAVE_INCOMPLETE", "ROADMAP.md possui ID de plano inválido")
    if len(identifiers) != len(set(identifiers)):
        _fail("WAVE_INCOMPLETE", "ROADMAP.md possui plano duplicado")
    return phases


def _load_plans(
    root: Path, change: Path, phases: list[dict[str, Any]]
) -> list[PlanContract]:
    plans_dir = change / "plans"
    children = _children(root, plans_dir, "plans")
    invalid_plan_files = [
        child.name
        for child in children
        if child.is_file()
        and child.suffix == ".md"
        and child.name.startswith("P")
        and not PLAN_ID.fullmatch(child.stem)
    ]
    if invalid_plan_files:
        _fail(
            "WAVE_INCOMPLETE",
            "arquivo de plano com identidade inválida: " + invalid_plan_files[0],
        )
    actual_files = [
        child for child in children if child.is_file() and PLAN_ID.fullmatch(child.stem)
    ]
    phase_ids = [str(phase["id"]) for phase in phases]
    if [path.stem for path in actual_files] != sorted(phase_ids):
        _fail("WAVE_INCOMPLETE", "ROADMAP.md diverge dos arquivos de plano")
    by_id = {path.stem: path for path in actual_files}
    plans: list[PlanContract] = []
    for phase in phases:
        identifier = str(phase["id"])
        raw = _frontmatter(root, by_id[identifier], f"plano {identifier}")
        try:
            contract = PlanContract.from_mapping(raw)
        except ValueError as error:
            _fail("WAVE_INCOMPLETE", f"plano {identifier} inválido: {error}")
        expected = {
            "id": contract.id,
            "result": contract.result,
            "depends_on": list(contract.depends_on),
            "requirements": list(contract.requirements),
            "execution": contract.execution,
            "tasks": [task.id for task in contract.tasks],
        }
        observed = {key: phase.get(key) for key in expected}
        if observed != expected:
            _fail("WAVE_INCOMPLETE", f"ROADMAP.md diverge do plano {identifier}")
        plans.append(contract)
    try:
        DependencyGraph(plans).topological_order()
        for contract in plans:
            if contract.schema_version == 2:
                TaskDependencyGraph(contract.tasks).topological_order()
    except ValueError as error:
        _fail("WAVE_INCOMPLETE", str(error))
    return plans


def _validate_approval(coherence: dict[str, Any]) -> tuple[str, set[str]]:
    if coherence.get("status") not in APPROVED_STATUSES:
        _fail("WAVE_NOT_APPROVED", "próxima onda exige pacote aprovado")
    digest = coherence.get("digest")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        _fail("WAVE_INCOMPLETE", "COHERENCE.md possui digest inválido")
    approval = coherence.get("approval")
    if not isinstance(approval, dict) or approval.get("digest") != digest:
        _fail("WAVE_INCOMPLETE", "COHERENCE.md não vincula aprovação ao pacote")
    stale = coherence.get("stale_plans", [])
    if not isinstance(stale, list) or not all(isinstance(value, str) for value in stale):
        _fail("WAVE_INCOMPLETE", "COHERENCE.md.stale_plans exige lista")
    return digest, set(stale)


def _validate_artifact_manifest(
    root: Path,
    change: Path,
    coherence: dict[str, Any],
    plan_ids: list[str],
) -> None:
    manifest = coherence.get("artifact_manifest")
    if not isinstance(manifest, dict):
        _fail("WAVE_INCOMPLETE", "pacote aprovado exige artifact_manifest")
    required = ["ROADMAP.md", *(f"plans/{identifier}.md" for identifier in plan_ids)]
    missing = [relative for relative in required if relative not in manifest]
    if missing:
        _fail(
            "WAVE_INCOMPLETE",
            "artifact_manifest não contém: " + ", ".join(missing),
        )
    for relative in required:
        expected = manifest.get(relative)
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            _fail("WAVE_INCOMPLETE", f"digest inválido no artifact_manifest: {relative}")
        path = _safe_file(root, change / relative, f"artefato {relative}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            _fail("WAVE_INCOMPLETE", f"pacote aprovado sofreu drift: {relative}")


def _completed_results(
    root: Path,
    change: Path,
    plans: list[PlanContract],
) -> tuple[set[str], dict[str, set[str]]]:
    known_plans = {plan.id: plan for plan in plans}
    completed_plans: set[str] = set()
    completed_tasks: dict[str, set[str]] = {plan.id: set() for plan in plans}
    results_dir = change / "results"
    for child in _children(root, results_dir, "results"):
        if not child.is_file() or not PLAN_ID.fullmatch(child.stem):
            continue
        if child.stem not in known_plans:
            _fail("WAVE_INCOMPLETE", f"resultado pertence a plano desconhecido: {child.stem}")
        value = _frontmatter(root, child, f"resultado {child.stem}")
        if value.get("status") != "completed" or value.get("plan") != child.stem:
            _fail("WAVE_INCOMPLETE", f"resultado inválido de {child.stem}")
        contract = known_plans[child.stem]
        if contract.schema_version == 2 and value.get("completed_tasks") != [
            task.id for task in contract.tasks
        ]:
            _fail(
                "WAVE_INCOMPLETE",
                f"resultado de {child.stem} não comprova todas as tarefas",
            )
        completed_plans.add(child.stem)

    tasks_root = results_dir / "tasks"
    if tasks_root.exists():
        for plan_dir in _children(root, tasks_root, "resultados de tarefas"):
            if not plan_dir.is_dir() or plan_dir.name not in known_plans:
                _fail(
                    "WAVE_INCOMPLETE",
                    f"resultado de tarefa pertence a plano desconhecido: {plan_dir.name}",
                )
            known_tasks = {task.id for task in known_plans[plan_dir.name].tasks}
            for child in _children(root, plan_dir, f"tarefas de {plan_dir.name}"):
                if not child.is_file() or not TASK_ID.fullmatch(child.stem):
                    _fail("WAVE_INCOMPLETE", f"resultado de tarefa inválido: {child.name}")
                if child.stem not in known_tasks:
                    _fail(
                        "WAVE_INCOMPLETE",
                        f"resultado pertence a tarefa desconhecida: {plan_dir.name}/{child.stem}",
                    )
                value = _frontmatter(
                    root, child, f"resultado {plan_dir.name}/{child.stem}"
                )
                if (
                    value.get("status") != "completed"
                    or value.get("plan") != plan_dir.name
                    or value.get("task") != child.stem
                ):
                    _fail(
                        "WAVE_INCOMPLETE",
                        f"resultado inválido de {plan_dir.name}/{child.stem}",
                    )
                completed_tasks[plan_dir.name].add(child.stem)
    return completed_plans, completed_tasks


def _blocking_findings(
    coherence: dict[str, Any], plan_ids: set[str]
) -> dict[str, list[str]]:
    findings = coherence.get("findings", [])
    if not isinstance(findings, list):
        _fail("WAVE_INCOMPLETE", "COHERENCE.md.findings exige lista")
    blocked: dict[str, list[str]] = {identifier: [] for identifier in plan_ids}
    for finding in findings:
        if not isinstance(finding, dict):
            _fail("WAVE_INCOMPLETE", "COHERENCE.md possui finding inválido")
        if (
            finding.get("status") != "open"
            or finding.get("severity") not in BLOCKING_SEVERITIES
        ):
            continue
        code = finding.get("code")
        if not isinstance(code, str) or not code:
            _fail("WAVE_INCOMPLETE", "finding bloqueante exige code")
        phases = finding.get("phases", [])
        if not isinstance(phases, list) or not all(isinstance(value, str) for value in phases):
            _fail("WAVE_INCOMPLETE", f"finding {code} possui phases inválido")
        targets = set(phases) if phases else plan_ids
        unknown = targets - plan_ids
        if unknown:
            _fail("WAVE_INCOMPLETE", f"finding {code} referencia plano inexistente")
        for identifier in targets:
            blocked[identifier].append(code)
    return {identifier: sorted(codes) for identifier, codes in blocked.items() if codes}


def _identities(change_prefix: str, plan: PlanContract) -> list[str]:
    if plan.schema_version == 2:
        return [f"{change_prefix}/{plan.id}/{task.id}" for task in plan.tasks]
    return [f"{change_prefix}/{plan.id}"]


def next_wave(repo: str | Path, change: str) -> dict[str, Any]:
    """Retorna a primeira onda consumível pelo host sem criar ou executar agentes."""

    root = _root(repo)
    directory = _change_directory(root, change)
    change_prefix = directory.name.split("-", 1)[0]
    roadmap_path = _safe_file(root, directory / "ROADMAP.md", "ROADMAP.md")
    roadmap_bytes = roadmap_path.read_bytes()
    roadmap = _frontmatter(root, roadmap_path, "ROADMAP.md")
    phases = _roadmap_phases(roadmap)
    plans = _load_plans(root, directory, phases)
    plan_ids = [plan.id for plan in plans]

    coherence = _frontmatter(root, directory / "COHERENCE.md", "COHERENCE.md")
    package_digest, stale_plans = _validate_approval(coherence)
    unknown_stale = stale_plans - set(plan_ids)
    if unknown_stale:
        _fail("WAVE_INCOMPLETE", "stale_plans referencia plano inexistente")
    _validate_artifact_manifest(root, directory, coherence, plan_ids)

    state = _frontmatter(root, root / ".bianchini/STATE.md", "STATE.md")
    state_blockers = state.get("blockers", [])
    if not isinstance(state_blockers, list) or not all(
        isinstance(value, str) for value in state_blockers
    ):
        _fail("WAVE_INCOMPLETE", "STATE.md.blockers exige lista")
    # IMPACT_STALE já é localizado por stale_plans. Os demais blockers são
    # globais porque STATE.md não possui ownership mais granular.
    global_blockers = sorted(value for value in state_blockers if value != "IMPACT_STALE")
    if state.get("status") == "blocked" and not global_blockers:
        global_blockers = ["STATE_BLOCKED"]

    completed_plans, completed_tasks = _completed_results(
        root, directory, plans
    )
    if stale_plans & completed_plans:
        _fail("WAVE_INCOMPLETE", "plano concluído não pode permanecer stale")
    findings = _blocking_findings(coherence, set(plan_ids))
    graph = DependencyGraph(plans)

    parallel_units: list[dict[str, Any]] = []
    stale_units: list[dict[str, Any]] = []
    blocked_units: list[dict[str, Any]] = []
    waiting_units: list[dict[str, Any]] = []
    completed_units: list[str] = []

    for plan in plans:
        identities = _identities(change_prefix, plan)
        if plan.id in completed_plans:
            completed_units.append(f"{change_prefix}/{plan.id}")
            continue
        for task_id in sorted(
            completed_tasks[plan.id],
            key=lambda identifier: [task.id for task in plan.tasks].index(identifier),
        ):
            completed_units.append(f"{change_prefix}/{plan.id}/{task_id}")

        incomplete_identities = [
            identity
            for identity in identities
            if identity.rsplit("/", 1)[-1] not in completed_tasks[plan.id]
        ]
        if plan.id in stale_plans:
            stale_units.extend(
                {"identity": identity, "reason": "plan_stale"}
                for identity in incomplete_identities
            )
            continue
        if global_blockers:
            blocked_units.extend(
                {
                    "identity": identity,
                    "reason": "state_blocker",
                    "details": global_blockers,
                }
                for identity in incomplete_identities
            )
            continue
        if plan.id in findings:
            blocked_units.extend(
                {
                    "identity": identity,
                    "reason": "open_finding",
                    "details": findings[plan.id],
                }
                for identity in incomplete_identities
            )
            continue

        plan_dependencies = sorted(
            graph.dependencies.get(plan.id, set()),
            key=lambda identifier: plan_ids.index(identifier),
        )
        pending_plans = [
            f"{change_prefix}/{identifier}"
            for identifier in plan_dependencies
            if identifier not in completed_plans
        ]
        satisfied_plans = [
            f"{change_prefix}/{identifier}"
            for identifier in plan_dependencies
            if identifier in completed_plans
        ]
        if pending_plans:
            waiting_units.extend(
                {
                    "identity": identity,
                    "reason": "plan_dependencies_pending",
                    "pending": pending_plans,
                }
                for identity in incomplete_identities
            )
            continue

        if plan.schema_version == 1:
            identity = f"{change_prefix}/{plan.id}"
            parallel_units.append(
                {
                    "identity": identity,
                    "plan": plan.id,
                    "task": None,
                    "pack_identity": identity,
                    "dependencies_satisfied": satisfied_plans,
                }
            )
            continue

        for task in plan.tasks:
            identity = f"{change_prefix}/{plan.id}/{task.id}"
            if task.id in completed_tasks[plan.id]:
                continue
            pending_tasks = [
                f"{change_prefix}/{plan.id}/{identifier}"
                for identifier in task.depends_on
                if identifier not in completed_tasks[plan.id]
            ]
            satisfied_tasks = [
                f"{change_prefix}/{plan.id}/{identifier}"
                for identifier in task.depends_on
                if identifier in completed_tasks[plan.id]
            ]
            if pending_tasks:
                waiting_units.append(
                    {
                        "identity": identity,
                        "reason": "task_dependencies_pending",
                        "pending": pending_tasks,
                    }
                )
                continue
            parallel_units.append(
                {
                    "identity": identity,
                    "plan": plan.id,
                    "task": task.id,
                    "pack_identity": identity,
                    "dependencies_satisfied": satisfied_plans + satisfied_tasks,
                }
            )

    return {
        "schema_version": 1,
        "change": directory.name,
        "eligible_wave": [item["identity"] for item in parallel_units],
        "parallel_units": parallel_units,
        "stale_units": stale_units,
        "blocked_units": blocked_units,
        "waiting_units": waiting_units,
        "completed_units": completed_units,
        "roadmap_digest": hashlib.sha256(roadmap_bytes).hexdigest(),
        "package_digest": package_digest,
    }


__all__ = ["WaveError", "next_wave"]
