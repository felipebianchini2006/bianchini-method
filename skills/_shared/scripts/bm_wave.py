#!/usr/bin/env python3
"""Projeção determinística e somente leitura da próxima onda executável."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import bm_spec_package
from bm_coherence import DependencyGraph, TaskDependencyGraph
from bm_project_model import PlanContract, ProjectModel


CHANGE_PREFIX = re.compile(r"^C[0-9]{3}$")
CHANGE_FULL = re.compile(r"^C[0-9]{3}-[a-z0-9]+(?:-[a-z0-9]+)*$")
PLAN_ID = re.compile(r"^P[0-9]{2,}$")
TASK_ID = re.compile(r"^T[0-9]{2,}$")
APPROVED_STATUSES = frozenset({"approved", "approved_with_stale"})
BLOCKING_SEVERITIES = frozenset({"ERROR", "WARNING"})
PLAN_RESULT_FIELDS = frozenset(
    {
        "schema_version",
        "change",
        "plan",
        "status",
        "result",
        "promised_delta_digest",
        "actual_delta",
        "actual_delta_digest",
        "model_before_digest",
        "model_after_digest",
        "verification",
        "completed_tasks",
        "impact",
        "completed_at",
    }
)
TASK_RESULT_FIELDS = frozenset(
    {
        "schema_version",
        "change",
        "plan",
        "task",
        "status",
        "expected_result",
        "result",
        "covers",
        "verification",
        "completed_at",
    }
)


class WaveError(ValueError):
    """Erro fechado da projeção, com código estável para o CLI."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def _fail(code: str, message: str) -> None:
    raise WaveError(code, message)


def _stable_digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def _evidence(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(_nonempty_text(item) for item in value)
    )


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
    if not _nonempty_text(approval.get("approved_by")) or not _nonempty_text(
        approval.get("approved_at")
    ):
        _fail("WAVE_INCOMPLETE", "COHERENCE.md possui aprovação incompleta")
    stale = coherence.get("stale_plans", [])
    if not isinstance(stale, list) or not all(isinstance(value, str) for value in stale):
        _fail("WAVE_INCOMPLETE", "COHERENCE.md.stale_plans exige lista")
    return digest, set(stale)


def _validate_artifact_manifest(
    root: Path,
    change: Path,
    coherence: dict[str, Any],
    plan_ids: list[str],
) -> dict[str, str]:
    manifest = coherence.get("artifact_manifest")
    if not isinstance(manifest, dict):
        _fail("WAVE_INCOMPLETE", "pacote aprovado exige artifact_manifest")
    required = [
        "SCOPE.md",
        "RESEARCH.md",
        "ARCHITECTURE.md",
        "SYSTEM_MODEL.md",
        "ROADMAP.md",
        *(f"plans/{identifier}.md" for identifier in plan_ids),
    ]
    if set(manifest) != set(required):
        missing = sorted(set(required) - set(manifest))
        extra = sorted(set(manifest) - set(required))
        details = []
        if missing:
            details.append("ausentes: " + ", ".join(missing))
        if extra:
            details.append("desconhecidos: " + ", ".join(extra))
        _fail(
            "WAVE_INCOMPLETE",
            "artifact_manifest diverge do pacote (" + "; ".join(details) + ")",
        )
    actual_manifest: dict[str, str] = {}
    for relative in required:
        expected = manifest.get(relative)
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            _fail("WAVE_INCOMPLETE", f"digest inválido no artifact_manifest: {relative}")
        path = _safe_file(root, change / relative, f"artefato {relative}")
        try:
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
        except OSError as error:
            _fail("WAVE_INCOMPLETE", f"artefato {relative} não pode ser lido: {error}")
        if actual != expected:
            _fail("WAVE_INCOMPLETE", f"pacote aprovado sofreu drift: {relative}")
        actual_manifest[relative] = actual
    return actual_manifest


def _spec_digest_payload(spec_package: dict[str, Any]) -> dict[str, Any]:
    return {
        "spec_contract": spec_package["spec_contract"],
        "spec_base_digest": spec_package["base_digest"],
        "spec_target_digest": spec_package["target_digest"],
        "spec_manifest_digest": spec_package["manifest_digest"],
        "spec_diff_digest": spec_package["diff_digest"],
    }


def _validate_current_package(
    root: Path,
    change: Path,
    coherence: dict[str, Any],
    plans: list[PlanContract],
    artifact_manifest: dict[str, str],
) -> str:
    if (
        coherence.get("schema_version") != 2
        or coherence.get("planning_contract") != 2
        or coherence.get("spec_contract") != 1
        or coherence.get("change") != change.name
    ):
        _fail(
            "WAVE_INCOMPLETE",
            "próxima onda exige COHERENCE schema 2, planning_contract 2 e spec_contract 1",
        )
    findings = coherence.get("findings")
    semantic = coherence.get("semantic")
    if not isinstance(findings, list) or not isinstance(semantic, dict):
        _fail("WAVE_INCOMPLETE", "pacote aprovado possui revisão incompleta")
    try:
        current_path = _safe_file(
            root, root / ".bianchini/current/SYSTEM_MODEL.md", "SYSTEM_MODEL atual"
        )
        expected_path = _safe_file(
            root, change / "SYSTEM_MODEL.md", "SYSTEM_MODEL esperado"
        )
        current = ProjectModel.from_system_model(current_path)
        expected = ProjectModel.from_system_model(expected_path)
    except (OSError, UnicodeError, ValueError) as error:
        _fail("WAVE_INCOMPLETE", f"ProjectModel inválido: {error}")
    try:
        spec_package = bm_spec_package.load_spec_package(
            change_dir=change,
            current_specs=root / ".bianchini/current/specs",
            scope_path=change / "SCOPE.md",
            coherence=coherence,
        )
    except bm_spec_package.SpecPackageError as error:
        _fail("WAVE_INCOMPLETE", str(error))
    if spec_package.get("managed") is not True:
        _fail("WAVE_INCOMPLETE", "próxima onda exige pacote de specs gerenciado")
    spec_digests = _spec_digest_payload(spec_package)
    if any(coherence.get(key) != value for key, value in spec_digests.items()):
        _fail("WAVE_INCOMPLETE", "digests do pacote de specs sofreram drift")
    expected_review_input = _stable_digest(
        {
            "planning_contract": 2,
            "artifact_manifest": artifact_manifest,
            "spec_package": spec_digests,
        }
    )
    if coherence.get("review_input_digest") != expected_review_input:
        _fail("WAVE_INCOMPLETE", "entrada aprovada de revisão sofreu drift")
    package_digest = _stable_digest(
        {
            "current": current.to_mapping(),
            "expected": expected.to_mapping(),
            "plans": [plan.to_mapping() for plan in plans],
            "findings": findings,
            "semantic": semantic,
            "planning_contract": 2,
            "artifact_manifest": artifact_manifest,
            "spec_package": spec_digests,
        }
    )
    if coherence.get("digest") != package_digest:
        _fail("WAVE_INCOMPLETE", "digest aprovado não corresponde ao pacote atual")
    return package_digest


def _validate_state_approval(
    root: Path, state: dict[str, Any], change: Path, package_digest: str
) -> None:
    if state.get("schema_version") != 1 or state.get("method") != "0.4":
        _fail("WAVE_INCOMPLETE", "STATE.md possui contrato inválido")
    if state.get("digest") != package_digest:
        _fail("WAVE_INCOMPLETE", "STATE.md não referencia o pacote aprovado atual")
    active = state.get("active_work")
    if not isinstance(active, dict) or active.get("kind") != "change" or active.get(
        "id"
    ) != change.name:
        _fail("WAVE_INCOMPLETE", "STATE.md não referencia a mudança aprovada")
    approved_lifecycle = {
        "approved",
        "approved_with_stale",
        "executing",
        "blocked",
        "pending_close",
    }
    if state.get("status") not in approved_lifecycle or active.get(
        "status"
    ) not in approved_lifecycle:
        _fail("WAVE_NOT_APPROVED", "STATE.md não está no ciclo do pacote aprovado")
    pointers = state.get("pointers")
    expected_pointer = f".bianchini/changes/{change.name}/COHERENCE.md"
    if not isinstance(pointers, dict) or pointers.get("coherence") != expected_pointer:
        _fail("WAVE_INCOMPLETE", "STATE.md não aponta para o COHERENCE aprovado")
    _safe_file(root, root / expected_pointer, "COHERENCE apontado por STATE.md")


def _completed_results(
    root: Path,
    change: Path,
    plans: list[PlanContract],
) -> tuple[set[str], dict[str, set[str]]]:
    known_plans = {plan.id: plan for plan in plans}
    completed_plans: set[str] = set()
    completed_tasks: dict[str, set[str]] = {plan.id: set() for plan in plans}
    plan_results: dict[str, dict[str, Any]] = {}
    task_results: dict[tuple[str, str], dict[str, Any]] = {}
    results_dir = change / "results"
    for child in _children(root, results_dir, "results"):
        if not child.is_file() or not PLAN_ID.fullmatch(child.stem):
            continue
        if child.stem not in known_plans:
            _fail("WAVE_INCOMPLETE", f"resultado pertence a plano desconhecido: {child.stem}")
        value = _frontmatter(root, child, f"resultado {child.stem}")
        contract = known_plans[child.stem]
        _validate_plan_result(value, contract, change.name)
        plan_results[child.stem] = value
        completed_plans.add(child.stem)

    tasks_root = results_dir / "tasks"
    if tasks_root.exists():
        for plan_dir in _children(root, tasks_root, "resultados de tarefas"):
            if not plan_dir.is_dir() or plan_dir.name not in known_plans:
                _fail(
                    "WAVE_INCOMPLETE",
                    f"resultado de tarefa pertence a plano desconhecido: {plan_dir.name}",
                )
            contract = known_plans[plan_dir.name]
            known_tasks = {task.id: task for task in contract.tasks}
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
                _validate_task_result(
                    value,
                    change.name,
                    plan_dir.name,
                    known_tasks[child.stem],
                )
                task_results[(plan_dir.name, child.stem)] = value
                completed_tasks[plan_dir.name].add(child.stem)

    for plan_id, plan_result in plan_results.items():
        contract = known_plans[plan_id]
        if contract.schema_version != 2:
            continue
        missing = [
            task.id
            for task in contract.tasks
            if (plan_id, task.id) not in task_results
        ]
        if missing:
            _fail(
                "WAVE_INCOMPLETE",
                f"resultado de {plan_id} não possui evidência das tarefas: {', '.join(missing)}",
            )
        for task in contract.tasks:
            task_result = task_results[(plan_id, task.id)]
            for field in ("result", "verification", "completed_at"):
                if task_result.get(field) != plan_result.get(field):
                    _fail(
                        "WAVE_INCOMPLETE",
                        f"resultado de {plan_id}/{task.id} diverge do plano em {field}",
                    )
    return completed_plans, completed_tasks


def _validate_plan_result(
    value: dict[str, Any], contract: PlanContract, change_name: str
) -> None:
    if set(value) != PLAN_RESULT_FIELDS:
        _fail("WAVE_INCOMPLETE", f"resultado de {contract.id} possui shape não canônico")
    if (
        type(value.get("schema_version")) is not int
        or value.get("schema_version") != 1
        or value.get("change") != change_name
        or value.get("plan") != contract.id
        or value.get("status") != "completed"
        or not _nonempty_text(value.get("result"))
        or not _nonempty_text(value.get("completed_at"))
    ):
        _fail("WAVE_INCOMPLETE", f"resultado inválido de {contract.id}")
    if not _evidence(value.get("verification")):
        _fail("WAVE_INCOMPLETE", f"resultado de {contract.id} não possui verificação")
    actual_delta = value.get("actual_delta")
    if not isinstance(actual_delta, dict) or actual_delta != contract.model_delta:
        _fail("WAVE_INCOMPLETE", f"resultado de {contract.id} diverge do delta aprovado")
    promised_digest = _stable_digest(contract.model_delta)
    if value.get("promised_delta_digest") != promised_digest:
        _fail("WAVE_INCOMPLETE", f"resultado de {contract.id} alterou o delta prometido")
    if value.get("actual_delta_digest") != _stable_digest(actual_delta):
        _fail("WAVE_INCOMPLETE", f"resultado de {contract.id} possui digest de delta inválido")
    for field in ("model_before_digest", "model_after_digest"):
        if not isinstance(value.get(field), str) or not re.fullmatch(
            r"[0-9a-f]{64}", value[field]
        ):
            _fail("WAVE_INCOMPLETE", f"resultado de {contract.id} possui {field} inválido")
    if not actual_delta and value.get("model_before_digest") != value.get(
        "model_after_digest"
    ):
        _fail("WAVE_INCOMPLETE", f"resultado de {contract.id} forjou mudança de modelo")
    expected_tasks = [task.id for task in contract.tasks]
    if value.get("completed_tasks") != expected_tasks:
        _fail(
            "WAVE_INCOMPLETE",
            f"resultado de {contract.id} não comprova todas as tarefas",
        )
    if value.get("impact") != {
        "radius": "local",
        "stale_plans": [],
        "reason": "entrega equivalente ao delta aprovado",
    }:
        _fail("WAVE_INCOMPLETE", f"resultado de {contract.id} possui impacto não canônico")


def _validate_task_result(
    value: dict[str, Any], change_name: str, plan_id: str, task: Any
) -> None:
    identity = f"{plan_id}/{task.id}"
    if set(value) != TASK_RESULT_FIELDS:
        _fail("WAVE_INCOMPLETE", f"resultado de {identity} possui shape não canônico")
    if (
        type(value.get("schema_version")) is not int
        or value.get("schema_version") != 1
        or value.get("change") != change_name
        or value.get("plan") != plan_id
        or value.get("task") != task.id
        or value.get("status") != "completed"
        or value.get("expected_result") != task.result
        or value.get("covers") != list(task.covers)
        or not _nonempty_text(value.get("result"))
        or not _nonempty_text(value.get("completed_at"))
    ):
        _fail("WAVE_INCOMPLETE", f"resultado inválido de {identity}")
    if not _evidence(value.get("verification")):
        _fail("WAVE_INCOMPLETE", f"resultado de {identity} não possui verificação")


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
    artifact_manifest = _validate_artifact_manifest(
        root, directory, coherence, plan_ids
    )
    current_package_digest = _validate_current_package(
        root, directory, coherence, plans, artifact_manifest
    )
    if current_package_digest != package_digest:
        _fail("WAVE_INCOMPLETE", "aprovação diverge do pacote recalculado")

    state = _frontmatter(root, root / ".bianchini/STATE.md", "STATE.md")
    _validate_state_approval(root, state, directory, package_digest)
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
