"""Orquestra ProjectModel, coerência e impacto para o CLI 0.4."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from bm_coherence import (
    DependencyGraph,
    FindingStatus,
    ImpactAnalyzer,
    SemanticReviewer,
    Severity,
    StructuralValidator,
)
from bm_project_model import PlanContract, ProjectModel, read_frontmatter
import bm_scope
from bm_workspace import MethodWorkspace


class PlanningError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    result = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    if not result:
        raise PlanningError("MODEL_MISMATCH", "slug da mudança é obrigatório")
    return result[:48].rstrip("-")


def _document(frontmatter: dict[str, Any], body: str) -> str:
    return (
        "---\n"
        + json.dumps(frontmatter, ensure_ascii=False, sort_keys=True, indent=2)
        + "\n---\n\n"
        + body.rstrip()
        + "\n"
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _package_digest(
    current: ProjectModel,
    expected: ProjectModel,
    plans: Iterable[PlanContract],
    findings: Iterable[dict[str, Any]],
    semantic: dict[str, Any] | None,
) -> str:
    """Digest estável do pacote que será submetido ao checkpoint humano."""

    return _digest(
        {
            "current": current.to_mapping(),
            "expected": expected.to_mapping(),
            "plans": [plan.to_mapping() for plan in plans],
            "findings": list(findings),
            "semantic": semantic,
        }
    )


def _git(root: Path, *args: str) -> str:
    completed = __import__("subprocess").run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=False
    )
    if completed.returncode != 0:
        raise PlanningError(
            "DIRTY_WORKSPACE", completed.stderr.strip() or "comando Git falhou"
        )
    return completed.stdout.strip()


def _change_directory(workspace: MethodWorkspace, reference: str) -> Path:
    if re.fullmatch(r"C\d{3}", reference):
        matches = sorted(workspace.changes_dir.glob(f"{reference}-*"))
        if len(matches) != 1:
            raise PlanningError(
                "MODEL_MISMATCH", f"{reference} deve localizar exatamente uma mudança"
            )
        directory = matches[0]
    elif re.fullmatch(r"C\d{3}-[a-z0-9]+(?:-[a-z0-9]+)*", reference):
        directory = workspace.changes_dir / reference
    else:
        raise PlanningError("MODEL_MISMATCH", f"ID de mudança inválido: {reference}")
    workspace.resolve(directory)
    if directory.is_symlink() or not directory.is_dir():
        raise PlanningError("MODEL_MISMATCH", f"mudança não encontrada: {reference}")
    return directory


def create_change(repo: Path, name: str) -> dict[str, Any]:
    workspace = MethodWorkspace(repo)
    state = workspace.read_state()
    if state.get("active_work"):
        raise PlanningError("COHERENCE_ERROR", "já existe trabalho ativo")
    slug = _slug(name)
    identifier = workspace.allocate_id("change")
    work_id = f"{identifier}-{slug}"
    directory = workspace.changes_dir / work_id
    if directory.exists():
        raise PlanningError("MODEL_MISMATCH", f"mudança já existe: {work_id}")
    directory.mkdir(parents=True)
    (directory / "plans").mkdir()
    (directory / "results").mkdir()
    templates = {
        "SCOPE.md": "# Escopo\n\nDefina resultado, aceite e não escopo.\n",
        "RESEARCH.md": "# Pesquisa\n\nRegistre stack, fontes oficiais e decisões aplicadas.\n",
        "ARCHITECTURE.md": "# Arquitetura global\n\nDecisões, alternativas rejeitadas e trade-offs.\n",
        "ROADMAP.md": "# Roadmap\n\nListe todas as fases e suas dependências.\n",
        "SUMMARY.md": "# Resumo\n\nPreenchido no fechamento.\n",
    }
    try:
        for relative, content in templates.items():
            workspace.atomic_write(directory / relative, content)
        shutil.copyfile(workspace.current_system_model, directory / "SYSTEM_MODEL.md")
        workspace.atomic_write(
            directory / "COHERENCE.md",
            _document(
                {
                    "schema_version": 1,
                    "change": work_id,
                    "status": "pending",
                    "findings": [],
                    "impact": None,
                    "digest": None,
                    "updated_at": _now(),
                },
                "# Coerência\n\nAguardando arquitetura, modelo e planos.",
            ),
        )
        state.update(
            {
                "active_work": {"kind": "change", "id": work_id, "status": "planning"},
                "current_unit": "research",
                "status": "planning",
                "blockers": [],
                "next_action": f"Pesquisar a stack e definir o SYSTEM_MODEL de {work_id}.",
                "digest": None,
                "updated_at": _now(),
            }
        )
        pointers = state.setdefault("pointers", {})
        pointers.update(
            {
                "architecture": f".bianchini/changes/{work_id}/ARCHITECTURE.md",
                "system_model": f".bianchini/changes/{work_id}/SYSTEM_MODEL.md",
                "specs": ".bianchini/current/specs",
                "coherence": f".bianchini/changes/{work_id}/COHERENCE.md",
            }
        )
        workspace.write_state(state)
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    return {"method": "0.4", "change": work_id, "status": "planning", "path": str(directory)}


def _load_package(
    repo: Path, change: str
) -> tuple[MethodWorkspace, Path, ProjectModel, ProjectModel, list[PlanContract]]:
    workspace = MethodWorkspace(repo)
    state = workspace.read_state()
    directory = _change_directory(workspace, change)
    active = state.get("active_work")
    if (
        isinstance(active, dict)
        and active.get("id") == directory.name
        and (
            state.get("status") == "scope_ready"
            or active.get("status") == "scope_ready"
        )
    ):
        try:
            bm_scope.verify_scope(repo, directory.name)
        except bm_scope.ScopeError as error:
            raise PlanningError("STALE_EVIDENCE", str(error)) from error
    try:
        current = ProjectModel.from_system_model(workspace.current_system_model)
        expected = ProjectModel.from_system_model(directory / "SYSTEM_MODEL.md")
        plans = [
            PlanContract.from_markdown(path)
            for path in sorted((directory / "plans").glob("P*.md"))
        ]
    except ValueError as error:
        raise PlanningError("MODEL_MISMATCH", str(error)) from error
    if not plans:
        raise PlanningError("COHERENCE_ERROR", "a mudança exige ao menos um plano")
    return workspace, directory, current, expected, plans


def validate_change_model(repo: Path, change: str) -> dict[str, Any]:
    _, directory, current, expected, plans = _load_package(repo, change)
    calculated = ProjectModel.simulate(current, plans)
    differences = calculated.differences(expected)
    return {
        "valid": not differences,
        "change": directory.name,
        "current_digest": current.digest(),
        "calculated_digest": calculated.digest(),
        "expected_digest": expected.digest(),
        "differences": differences,
    }


def _read_semantic_report(path: Path, reviewer: SemanticReviewer) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise PlanningError("COHERENCE_ERROR", f"relatório semântico ausente: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise PlanningError(
            "COHERENCE_ERROR", f"relatório semântico inválido na linha {error.lineno}"
        ) from error
    if not isinstance(value, dict) or not isinstance(value.get("findings", []), list):
        raise PlanningError("COHERENCE_ERROR", "relatório semântico exige findings")
    try:
        review = reviewer.normalize(
            value.get("findings", []),
            prompt=str(value.get("prompt", "")),
            inputs=str(value.get("inputs", "")),
            sources=value.get("sources", []),
        )
    except ValueError as error:
        raise PlanningError("COHERENCE_ERROR", str(error)) from error
    return review.to_mapping()


def coherence_check(
    repo: Path,
    change: str,
    *,
    structural_only: bool,
    semantic_report: Path | None,
) -> dict[str, Any]:
    workspace, directory, current, expected, plans = _load_package(repo, change)
    findings = StructuralValidator().validate(current, plans, expected)
    semantic: dict[str, Any] | None
    if structural_only:
        semantic = None
    elif semantic_report is None:
        semantic = SemanticReviewer().unavailable(
            "Relatório semântico não foi fornecido."
        ).to_mapping()
    else:
        semantic = _read_semantic_report(semantic_report, SemanticReviewer())
    mappings = [finding.to_mapping() for finding in findings]
    if semantic is not None:
        mappings.extend(semantic["findings"])
    open_blockers = [
        item
        for item in mappings
        if item["status"] == FindingStatus.OPEN.value
        and item["severity"] in {Severity.ERROR.value, Severity.WARNING.value}
    ]
    if open_blockers:
        status = "changes_required"
    elif structural_only:
        status = "structurally_valid"
    else:
        status = "ready_for_approval"
    package_digest = _package_digest(current, expected, plans, mappings, semantic)
    payload = {
        "schema_version": 1,
        "change": directory.name,
        "status": status,
        "structural_only": structural_only,
        "findings": mappings,
        "semantic": semantic,
        "model": {
            "current": current.digest(),
            "expected": expected.digest(),
        },
        "plans": [plan.to_mapping() for plan in plans],
        "impact": None,
        "stale_plans": [],
        "approval": None,
        "updated_at": _now(),
        "digest": package_digest,
    }
    workspace.atomic_write(
        directory / "COHERENCE.md",
        _document(
            payload,
            "# Coerência\n\n"
            f"Status: {status}.\n\n"
            "## Impact Radius\n\nAinda não calculado para uma mudança executada.",
        ),
    )
    state = workspace.read_state()
    state.update(
        {
            "current_unit": "coherence",
            "status": (
                "pending_approval" if status == "ready_for_approval" else "planning"
            ),
            "blockers": [item["code"] for item in open_blockers],
            "next_action": (
                "Aprovar o digest global do planejamento."
                if status == "ready_for_approval"
                else (
                    "Executar a revisão semântica do pacote global."
                    if status == "structurally_valid"
                    else "Resolver ERRORs e WARNINGs abertos em COHERENCE.md."
                )
            ),
            "digest": payload["digest"],
            "updated_at": _now(),
        }
    )
    state.setdefault("pointers", {})["coherence"] = (
        f".bianchini/changes/{directory.name}/COHERENCE.md"
    )
    workspace.write_state(state)
    return {
        "change": directory.name,
        "status": status,
        "digest": payload["digest"],
        "findings": mappings,
        "structural_findings": len(findings),
        "semantic_available": semantic.get("available") if semantic else None,
    }


def coherence_approve(
    repo: Path,
    change: str,
    *,
    digest: str,
    approved_by: str,
) -> dict[str, Any]:
    """Aprova exatamente o pacote global revisado, sem executar nova análise semântica."""

    workspace, directory, current, expected, plans = _load_package(repo, change)
    try:
        payload = read_frontmatter(directory / "COHERENCE.md")
    except ValueError as error:
        raise PlanningError("COHERENCE_ERROR", str(error)) from error
    if payload.get("status") != "ready_for_approval":
        raise PlanningError(
            "WARNING_UNRESOLVED",
            "somente um pacote com revisão completa pode ser aprovado",
        )
    semantic = payload.get("semantic")
    if not isinstance(semantic, dict) or semantic.get("available") is not True:
        raise PlanningError(
            "WARNING_UNRESOLVED", "revisão semântica indisponível não pode ser aprovada"
        )
    findings = payload.get("findings", [])
    if not isinstance(findings, list):
        raise PlanningError("COHERENCE_ERROR", "findings inválidos em COHERENCE.md")
    unresolved = [
        item
        for item in findings
        if isinstance(item, dict)
        and item.get("status") == FindingStatus.OPEN.value
        and item.get("severity") in {Severity.ERROR.value, Severity.WARNING.value}
    ]
    if unresolved:
        raise PlanningError(
            "WARNING_UNRESOLVED", "ERRORs e WARNINGs abertos impedem aprovação"
        )
    current_digest = _package_digest(current, expected, plans, findings, semantic)
    if digest != payload.get("digest") or digest != current_digest:
        raise PlanningError(
            "STALE_EVIDENCE", "digest informado não corresponde ao pacote atual"
        )
    actor = approved_by.strip()
    if not actor:
        raise PlanningError("EXTERNAL_AUTHORITY_REQUIRED", "--approved-by é obrigatório")
    payload.update(
        {
            "status": "approved",
            "approval": {"digest": digest, "approved_by": actor, "approved_at": _now()},
            "updated_at": _now(),
        }
    )
    workspace.atomic_write(
        directory / "COHERENCE.md",
        _document(
            payload,
            "# Coerência\n\n"
            "Status: approved.\n\n"
            "## Impact Radius\n\nAinda não calculado para uma mudança executada.",
        ),
    )
    state = workspace.read_state()
    state.update(
        {
            "current_unit": None,
            "status": "approved",
            "blockers": [],
            "next_action": f"Executar {plans[0].id} de {directory.name}.",
            "digest": digest,
            "updated_at": _now(),
        }
    )
    active = state.get("active_work")
    if isinstance(active, dict):
        active["status"] = "approved"
    workspace.write_state(state)
    return {
        "change": directory.name,
        "status": "approved",
        "digest": digest,
        "approved_by": actor,
    }


def impact_analyze(
    repo: Path,
    change: str,
    plan: str,
    *,
    changed_contracts: Iterable[str] = (),
    changed_ownership: Iterable[str] = (),
    changed_interfaces: Iterable[str] = (),
    changed_data: Iterable[str] = (),
    changed_migrations: Iterable[str] = (),
    changed_journeys: Iterable[str] = (),
    changed_effects: Iterable[str] = (),
    changed_invariants: Iterable[str] = (),
    global_change: bool = False,
) -> dict[str, Any]:
    workspace, directory, _, expected, plans = _load_package(repo, change)
    try:
        result = ImpactAnalyzer(DependencyGraph(plans), expected).analyze(
            plan,
            changed_contracts=changed_contracts,
            changed_ownership=changed_ownership,
            changed_interfaces=changed_interfaces,
            changed_data=changed_data,
            changed_migrations=changed_migrations,
            changed_journeys=changed_journeys,
            changed_effects=changed_effects,
            changed_invariants=changed_invariants,
            global_change=global_change,
        )
    except ValueError as error:
        raise PlanningError("IMPACT_STALE", str(error)) from error
    coherence_path = directory / "COHERENCE.md"
    try:
        payload = read_frontmatter(coherence_path)
    except ValueError as error:
        raise PlanningError("COHERENCE_ERROR", str(error)) from error
    impact = result.to_mapping()
    preview = payload.get("status") != "approved"
    impact["preview"] = preview
    payload["impact"] = impact
    payload["stale_plans"] = [] if preview else impact["stale_plans"]
    if not preview and impact["stale_plans"]:
        payload["status"] = "approved_with_stale"
    payload["updated_at"] = _now()
    # Impacto pós-aprovação é dado derivado do pacote já aprovado. Preserve o
    # digest humano original; um novo digest só nasce após nova auditoria.
    if preview:
        payload["digest"] = _digest(
            {key: value for key, value in payload.items() if key != "digest"}
        )
    body = (
        "# Coerência\n\n"
        f"Status: {payload.get('status', 'pending')}.\n\n"
        "## Impact Radius\n\n"
        f"- Modo: {'preview' if preview else 'invalidation'}\n"
        f"- Classificação: {impact['radius']}\n"
        f"- Plano alterado: {impact['changed_plan']}\n"
        f"- Diretos: {', '.join(impact['direct_plans']) or 'nenhum'}\n"
        f"- Transitivos: {', '.join(impact['transitive_plans']) or 'nenhum'}\n"
        f"- Stale: {', '.join(impact['stale_plans']) or 'nenhum'}\n"
        f"- Journeys: {', '.join(impact['affected_journeys']) or 'nenhuma'}\n"
        f"- Verificações: {', '.join(impact['verifications']) or 'nenhuma'}"
    )
    workspace.atomic_write(coherence_path, _document(payload, body))
    state = workspace.read_state()
    state.update(
        {
            "current_unit": plan,
            "status": (
                "approved_with_stale"
                if not preview and impact["stale_plans"]
                else state.get("status")
            ),
            "blockers": (
                ["IMPACT_STALE"]
                if not preview and impact["stale_plans"]
                else state.get("blockers", [])
            ),
            "next_action": (
                "Replanejar e revalidar planos stale: " + ", ".join(impact["stale_plans"])
                if not preview and impact["stale_plans"]
                else (
                    "Revisar o raio potencial antes da aprovação global."
                    if preview
                    else f"Continuar {plan}; nenhuma fase posterior foi invalidada."
                )
            ),
            "digest": payload["digest"],
            "updated_at": _now(),
        }
    )
    workspace.write_state(state)
    return impact


def _plan_by_id(plans: Iterable[PlanContract], plan_id: str) -> PlanContract:
    matches = [plan for plan in plans if plan.id == plan_id]
    if len(matches) != 1:
        raise PlanningError("MODEL_MISMATCH", f"{plan_id} deve localizar exatamente um plano")
    return matches[0]


def _result_payloads(directory: Path) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for path in sorted((directory / "results").glob("P*.md")):
        try:
            payload = read_frontmatter(path)
        except ValueError as error:
            raise PlanningError("DOCVIVA_INCOMPLETE", str(error)) from error
        plan_id = payload.get("plan")
        if not isinstance(plan_id, str) or plan_id in results:
            raise PlanningError("DOCVIVA_INCOMPLETE", f"resultado inválido: {path.name}")
        results[plan_id] = payload
    return results


def _effective_model(
    current: ProjectModel,
    plans: Iterable[PlanContract],
    results: dict[str, dict[str, Any]],
) -> ProjectModel:
    model = current
    for plan in plans:
        result = results.get(plan.id)
        if result is None:
            continue
        if result.get("status") != "completed":
            raise PlanningError("DOCVIVA_INCOMPLETE", f"resultado de {plan.id} não está completo")
        delta = result.get("actual_delta")
        if not isinstance(delta, dict):
            raise PlanningError("DOCVIVA_INCOMPLETE", f"resultado de {plan.id} não declara actual_delta")
        try:
            model = model.apply_delta(delta)
        except ValueError as error:
            raise PlanningError("MODEL_MISMATCH", f"{plan.id}: {error}") from error
    return model


def plan_complete(
    repo: Path,
    change: str,
    plan_id: str,
    *,
    actual_delta: Path,
    result: str,
    verification: Iterable[str],
) -> dict[str, Any]:
    """Registra a entrega real e rejeita drift silencioso do contrato aprovado."""

    workspace, directory, current, _, plans = _load_package(repo, change)
    coherence = read_frontmatter(directory / "COHERENCE.md")
    if coherence.get("status") not in {"approved", "approved_with_stale"}:
        raise PlanningError("COHERENCE_ERROR", "plano exige pacote global aprovado")
    if plan_id in coherence.get("stale_plans", []):
        raise PlanningError("IMPACT_STALE", f"{plan_id} está stale")
    plan = _plan_by_id(plans, plan_id)
    results = _result_payloads(directory)
    if plan_id in results:
        raise PlanningError("COHERENCE_ERROR", f"{plan_id} já possui resultado")
    missing_dependencies = sorted(set(plan.depends_on) - set(results))
    if missing_dependencies:
        raise PlanningError(
            "MISSING_PROVIDER",
            f"dependências ainda não concluídas: {', '.join(missing_dependencies)}",
        )
    evidence = [value.strip() for value in verification if value.strip()]
    if not evidence:
        raise PlanningError("STALE_EVIDENCE", "conclusão do plano exige verificação")
    summary = result.strip()
    if not summary:
        raise PlanningError("DOCVIVA_INCOMPLETE", "conclusão do plano exige resultado")
    if actual_delta.is_symlink() or not actual_delta.is_file():
        raise PlanningError("MODEL_MISMATCH", "--actual-delta exige arquivo JSON regular")
    try:
        delta = json.loads(actual_delta.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise PlanningError("MODEL_MISMATCH", f"actual_delta inválido: {error}") from error
    if not isinstance(delta, dict):
        raise PlanningError("MODEL_MISMATCH", "actual_delta exige objeto JSON")
    if delta != plan.model_delta:
        raise PlanningError(
            "IMPACT_STALE",
            "delta entregue diverge do plano; execute impact analyze e revalide o pacote",
        )
    effective_before = _effective_model(current, plans, results)
    missing_contracts = sorted(set(plan.consumes) - set(effective_before.contracts))
    if missing_contracts:
        raise PlanningError(
            "MISSING_PROVIDER",
            f"contratos consumidos ainda ausentes: {', '.join(missing_contracts)}",
        )
    try:
        effective_after = effective_before.apply_delta(delta)
    except ValueError as error:
        raise PlanningError("MODEL_MISMATCH", str(error)) from error
    payload = {
        "schema_version": 1,
        "change": directory.name,
        "plan": plan.id,
        "status": "completed",
        "result": summary,
        "promised_delta_digest": _digest(plan.model_delta),
        "actual_delta": delta,
        "actual_delta_digest": _digest(delta),
        "model_before_digest": effective_before.digest(),
        "model_after_digest": effective_after.digest(),
        "verification": evidence,
        "impact": {
            "radius": "local",
            "stale_plans": [],
            "reason": "entrega equivalente ao delta aprovado",
        },
        "completed_at": _now(),
    }
    workspace.atomic_write(
        directory / "results" / f"{plan.id}.md",
        _document(payload, f"# Resultado {plan.id}\n\n{summary}"),
    )
    completed = set(results) | {plan.id}
    pending = [item.id for item in plans if item.id not in completed]
    state = workspace.read_state()
    state.update(
        {
            "current_unit": pending[0] if pending else None,
            "status": "approved" if pending else "pending_close",
            "blockers": [],
            "next_action": (
                f"Executar {pending[0]} de {directory.name}."
                if pending
                else f"Executar o fechamento global de {directory.name}."
            ),
            "digest": coherence.get("digest"),
            "updated_at": _now(),
        }
    )
    active = state.get("active_work")
    if isinstance(active, dict):
        active["status"] = state["status"]
    workspace.write_state(state)
    return {
        "change": directory.name,
        "plan": plan.id,
        "status": "completed",
        "model_digest": effective_after.digest(),
        "next_plan": pending[0] if pending else None,
    }


def _execution_identity(change: str, plan: str) -> tuple[str, str]:
    change_prefix = change.split("-", 1)[0]
    if not re.fullmatch(r"C\d{3}", change_prefix):
        raise PlanningError("MODEL_MISMATCH", "change exige C seguido de três dígitos")
    if not re.fullmatch(r"P\d{2,}", plan):
        raise PlanningError("MODEL_MISMATCH", "plan exige P seguido de ao menos dois dígitos")
    identity = f"{change_prefix.lower()}-{plan.lower()}"
    return identity, f"bm/{identity}"


def execution_workspace_create(
    repo: Path, change: str, plan: str, target: Path | None = None
) -> dict[str, Any]:
    root = Path(_git(repo.resolve(), "rev-parse", "--show-toplevel")).resolve()
    if root != repo.resolve():
        raise PlanningError("DIRTY_WORKSPACE", f"--repo deve apontar para {root}")
    if _git(root, "status", "--porcelain"):
        raise PlanningError("DIRTY_WORKSPACE", "workspace de execução exige Git limpo")
    workspace, directory, current, _, plans = _load_package(root, change)
    state = workspace.read_state()
    coherence = read_frontmatter(directory / "COHERENCE.md")
    if coherence.get("status") not in {"approved", "approved_with_stale"}:
        raise PlanningError("COHERENCE_ERROR", "planejamento exige COHERENCE approved")
    if plan in coherence.get("stale_plans", []):
        raise PlanningError("IMPACT_STALE", f"{plan} está stale")
    contract = _plan_by_id(plans, plan)
    results = _result_payloads(directory)
    if plan in results:
        raise PlanningError("COHERENCE_ERROR", f"{plan} já foi concluído")
    missing_dependencies = sorted(set(contract.depends_on) - set(results))
    if missing_dependencies:
        raise PlanningError(
            "MISSING_PROVIDER",
            f"dependências ainda não concluídas: {', '.join(missing_dependencies)}",
        )
    effective = _effective_model(current, plans, results)
    missing_contracts = sorted(set(contract.consumes) - set(effective.contracts))
    if missing_contracts:
        raise PlanningError(
            "MISSING_PROVIDER",
            f"contratos consumidos ainda ausentes: {', '.join(missing_contracts)}",
        )
    plan_matches = sorted((directory / "plans").glob(f"{plan}*.md"))
    if len(plan_matches) != 1:
        raise PlanningError("MODEL_MISMATCH", f"{plan} deve localizar exatamente um plano")
    head = _git(root, "rev-parse", "HEAD")
    for required in (directory / "COHERENCE.md", directory / "SYSTEM_MODEL.md", plan_matches[0]):
        relative = required.relative_to(root).as_posix()
        if not _git(root, "ls-files", "--error-unmatch", relative):
            raise PlanningError("COHERENCE_ERROR", f"pacote não commitado: {relative}")
        committed = _git(root, "show", f"HEAD:{relative}").encode()
        if committed != required.read_bytes().rstrip(b"\n"):
            # git show remove somente o newline final pelo .strip do helper;
            # compare também o formato textual normalizado.
            if committed.decode() != required.read_text(encoding="utf-8").rstrip("\n"):
                raise PlanningError("COHERENCE_ERROR", f"pacote diverge do HEAD: {relative}")
    identity, branch = _execution_identity(directory.name, plan)
    destination = (
        target.resolve()
        if target is not None
        else root.parent / ".bianchini-worktrees" / root.name / identity
    )
    try:
        destination.relative_to(root)
    except ValueError:
        pass
    else:
        raise PlanningError("DIRTY_WORKSPACE", "destino do worktree deve ficar fora do repo")
    if destination.exists():
        raise PlanningError("DIRTY_WORKSPACE", f"destino já existe: {destination}")
    branches = set(_git(root, "for-each-ref", "--format=%(refname:short)", "refs/heads").splitlines())
    if branch in branches:
        raise PlanningError("DIRTY_WORKSPACE", f"branch já existe: {branch}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        _git(root, "worktree", "add", "-b", branch, str(destination), head)
        target_workspace = MethodWorkspace(destination)
        target_workspace.runtime_dir.mkdir(parents=True, exist_ok=True)
        metadata = {
            "schema_version": 1,
            "source_repo": str(root),
            "change": directory.name,
            "plan": plan,
            "branch": branch,
            "base_commit": head,
            "coherence_digest": coherence.get("digest"),
            "created_at": _now(),
        }
        target_workspace.atomic_write(
            target_workspace.runtime_dir / f"workspace-{identity}.json",
            json.dumps(metadata, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        )
        target_state = target_workspace.read_state()
        target_state.update(
            {
                "current_unit": plan,
                "status": "executing",
                "active_work": {
                    "kind": "change",
                    "id": directory.name,
                    "status": "executing",
                },
                "next_action": f"Executar {plan} neste workspace isolado.",
                "updated_at": _now(),
            }
        )
        target_workspace.write_state(target_state)
    except Exception:
        if destination.exists():
            __import__("subprocess").run(
                ["git", "worktree", "remove", "--force", str(destination)],
                cwd=root,
                capture_output=True,
                check=False,
            )
        __import__("subprocess").run(
            ["git", "branch", "-D", branch], cwd=root, capture_output=True, check=False
        )
        raise
    return {
        "workspace": str(destination),
        "branch": branch,
        "change": directory.name,
        "plan": plan,
        "base_commit": head,
    }


def _worktree_records(root: Path) -> list[dict[str, str]]:
    output = _git(root, "worktree", "list", "--porcelain")
    records: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in [*output.splitlines(), ""]:
        if not line:
            if current:
                records.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        current[key] = value
    return records


def execution_workspace_locate(
    repo: Path, change: str, plan: str, *, resume: bool = False
) -> dict[str, Any]:
    root = Path(_git(repo.resolve(), "rev-parse", "--show-toplevel")).resolve()
    identity, branch = _execution_identity(change, plan)
    reference = f"refs/heads/{branch}"
    matches = [record for record in _worktree_records(root) if record.get("branch") == reference]
    if len(matches) != 1:
        raise PlanningError("DIRTY_WORKSPACE", f"workspace não localizado para {identity}")
    path = Path(matches[0]["worktree"])
    result = {"workspace": str(path), "branch": branch, "change": change, "plan": plan}
    if resume:
        metadata_path = MethodWorkspace(path).runtime_dir / f"workspace-{identity}.json"
        if not metadata_path.is_file():
            raise PlanningError("DIRTY_WORKSPACE", "metadados do workspace estão ausentes")
        result["metadata"] = json.loads(metadata_path.read_text(encoding="utf-8"))
    return result


def execution_workspace_check(repo: Path) -> dict[str, Any]:
    root = repo.resolve()
    branch = _git(root, "branch", "--show-current")
    if not re.fullmatch(r"bm/c\d{3}-p\d{2,}", branch):
        raise PlanningError("DIRTY_WORKSPACE", "branch de execução 0.4 inválida")
    metadata = sorted(MethodWorkspace(root).runtime_dir.glob("workspace-*.json"))
    if len(metadata) != 1:
        raise PlanningError("DIRTY_WORKSPACE", "metadados de execução ausentes ou ambíguos")
    value = json.loads(metadata[0].read_text(encoding="utf-8"))
    return {"valid": True, "branch": branch, "workspace": str(root), "metadata": value}


def close_change(repo: Path, change: str) -> dict[str, Any]:
    """Promove o modelo final para ``current`` e arquiva o ciclo completo."""

    root = repo.resolve()
    if _git(root, "status", "--porcelain"):
        raise PlanningError("DIRTY_WORKSPACE", "fechamento exige Git limpo")
    workspace, directory, current, expected, plans = _load_package(root, change)
    coherence = read_frontmatter(directory / "COHERENCE.md")
    if coherence.get("status") != "approved":
        raise PlanningError("COHERENCE_ERROR", "fechamento exige COHERENCE approved")
    if coherence.get("stale_plans"):
        raise PlanningError("IMPACT_STALE", "fechamento contém planos stale")
    findings = coherence.get("findings", [])
    semantic = coherence.get("semantic")
    if not isinstance(findings, list) or not isinstance(semantic, dict):
        raise PlanningError("COHERENCE_ERROR", "auditoria global está incompleta")
    package_digest = _package_digest(current, expected, plans, findings, semantic)
    if package_digest != coherence.get("digest"):
        raise PlanningError("STALE_EVIDENCE", "pacote aprovado mudou após o checkpoint")
    results = _result_payloads(directory)
    missing = [plan.id for plan in plans if plan.id not in results]
    if missing:
        raise PlanningError(
            "DOCVIVA_INCOMPLETE", f"resultados ausentes: {', '.join(missing)}"
        )
    for plan in plans:
        result = results[plan.id]
        if result.get("actual_delta") != plan.model_delta:
            raise PlanningError("IMPACT_STALE", f"resultado de {plan.id} diverge do delta aprovado")
        if not result.get("verification"):
            raise PlanningError("STALE_EVIDENCE", f"resultado de {plan.id} não possui verificação")
    calculated = _effective_model(current, plans, results)
    differences = calculated.differences(expected)
    if differences:
        raise PlanningError(
            "MODEL_MISMATCH", "modelo entregue diverge do SYSTEM_MODEL final"
        )
    closing_findings = StructuralValidator().validate(current, plans, expected)
    if any(finding.severity is Severity.ERROR for finding in closing_findings):
        raise PlanningError("COHERENCE_ERROR", "auditoria estrutural final encontrou ERROR")
    archive = workspace.archive_dir / directory.name
    workspace.resolve(archive)
    if archive.exists():
        raise PlanningError("COHERENCE_ERROR", f"arquivo já existe: {archive.name}")
    summary = {
        "schema_version": 1,
        "change": directory.name,
        "status": "completed",
        "plans": [plan.id for plan in plans],
        "coherence_digest": package_digest,
        "final_model_digest": expected.digest(),
        "closed_at": _now(),
    }
    workspace.atomic_write(
        directory / "SUMMARY.md",
        _document(
            summary,
            "# Resumo\n\n"
            f"Mudança {directory.name} concluída com {len(plans)} plano(s) verificado(s).",
        ),
    )
    architecture = (directory / "ARCHITECTURE.md").read_bytes()
    system_model = (directory / "SYSTEM_MODEL.md").read_bytes()
    previous_architecture = workspace.current_architecture.read_bytes()
    previous_system_model = workspace.current_system_model.read_bytes()
    moved = False
    try:
        workspace.atomic_write(workspace.current_architecture, architecture)
        workspace.atomic_write(workspace.current_system_model, system_model)
        os.replace(directory, archive)
        moved = True
        state = workspace.read_state()
        state.update(
            {
                "active_work": None,
                "current_unit": None,
                "status": "idle",
                "blockers": [],
                "next_action": "Iniciar o próximo trabalho a partir do modelo atual.",
                "last_completed": {
                    "kind": "change",
                    "id": archive.name,
                    "status": "completed",
                },
                "pointers": {
                    "architecture": ".bianchini/current/ARCHITECTURE.md",
                    "system_model": ".bianchini/current/SYSTEM_MODEL.md",
                    "specs": ".bianchini/current/specs",
                    "coherence": f".bianchini/archive/{archive.name}/COHERENCE.md",
                },
                "digest": expected.digest(),
                "updated_at": _now(),
            }
        )
        workspace.write_state(state)
    except Exception:
        if moved and archive.exists() and not directory.exists():
            os.replace(archive, directory)
        workspace.atomic_write(workspace.current_architecture, previous_architecture)
        workspace.atomic_write(workspace.current_system_model, previous_system_model)
        raise
    return {
        "change": archive.name,
        "status": "completed",
        "archive": str(archive),
        "model_digest": expected.digest(),
    }


__all__ = [
    "PlanningError",
    "coherence_approve",
    "coherence_check",
    "close_change",
    "create_change",
    "impact_analyze",
    "plan_complete",
    "execution_workspace_check",
    "execution_workspace_create",
    "execution_workspace_locate",
    "validate_change_model",
]
