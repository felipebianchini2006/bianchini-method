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
    TaskDependencyGraph,
)
from bm_project_model import PlanContract, ProjectModel, read_frontmatter
import bm_scope
import bm_close
import bm_context
import bm_spec_package
from bm_workspace import MethodWorkspace


class PlanningError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


PLANNING_CONTRACT_VERSION = 2
SPEC_CONTRACT_VERSION = 1
TRACEABLE_SCOPE_PREFIXES = frozenset(
    {"FLW", "REQ", "NFR", "BR", "DAT", "INT", "ERR", "RSK"}
)
SCOPE_ITEM = re.compile(r"(?m)^### ([A-Z]+-[0-9]{3})\b")


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
    *,
    planning_contract: int = 1,
    artifact_manifest: dict[str, str] | None = None,
    spec_package: dict[str, Any] | None = None,
) -> str:
    """Digest estável do pacote que será submetido ao checkpoint humano."""

    payload = {
        "current": current.to_mapping(),
        "expected": expected.to_mapping(),
        "plans": [plan.to_mapping() for plan in plans],
        "findings": list(findings),
        "semantic": semantic,
    }
    if planning_contract >= 2:
        payload.update(
            {
                "planning_contract": planning_contract,
                "artifact_manifest": artifact_manifest or {},
            }
        )
    if spec_package and spec_package.get("managed"):
        payload["spec_package"] = _spec_digest_payload(spec_package)
    return _digest(payload)


def _spec_digest_payload(spec_package: dict[str, Any]) -> dict[str, Any]:
    return {
        "spec_contract": spec_package["spec_contract"],
        "spec_base_digest": spec_package["base_digest"],
        "spec_target_digest": spec_package["target_digest"],
        "spec_manifest_digest": spec_package["manifest_digest"],
        "spec_diff_digest": spec_package["diff_digest"],
    }


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _coherence_contract(directory: Path) -> tuple[dict[str, Any], int, int | None]:
    try:
        coherence = read_frontmatter(directory / "COHERENCE.md")
    except ValueError as error:
        raise PlanningError("COHERENCE_ERROR", str(error)) from error
    schema_version = coherence.get("schema_version", 1)
    if schema_version not in {1, 2}:
        raise PlanningError("COHERENCE_ERROR", "schema_version de COHERENCE inválido")
    planning_contract = coherence.get("planning_contract", 1)
    if planning_contract not in {1, 2}:
        raise PlanningError("COHERENCE_ERROR", "planning_contract inválido")
    if schema_version == 1:
        return coherence, int(planning_contract), None
    if planning_contract != PLANNING_CONTRACT_VERSION:
        raise PlanningError(
            "COHERENCE_ERROR", "COHERENCE schema 2 exige planning_contract: 2"
        )
    spec_contract = coherence.get("spec_contract")
    if spec_contract != SPEC_CONTRACT_VERSION:
        raise PlanningError(
            "SPEC_CONTRACT_UNSUPPORTED",
            "COHERENCE schema 2 exige spec_contract: 1",
        )
    return coherence, int(planning_contract), int(spec_contract)


def _planning_contract_version(directory: Path) -> int:
    return _coherence_contract(directory)[1]


def _load_spec_package(
    workspace: MethodWorkspace,
    directory: Path,
    coherence: dict[str, Any],
) -> dict[str, Any]:
    try:
        return bm_spec_package.load_spec_package(
            change_dir=directory,
            current_specs=workspace.current_specs,
            scope_path=directory / "SCOPE.md",
            coherence=coherence,
        )
    except bm_spec_package.SpecPackageError as error:
        raise PlanningError(error.code, str(error).split(": ", 1)[-1]) from error


def _artifact_manifest(directory: Path) -> dict[str, str]:
    paths = [
        directory / name
        for name in (
            "SCOPE.md",
            "RESEARCH.md",
            "ARCHITECTURE.md",
            "SYSTEM_MODEL.md",
            "ROADMAP.md",
        )
    ]
    paths.extend(sorted((directory / "plans").glob("P*.md")))
    manifest: dict[str, str] = {}
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise PlanningError(
                "COHERENCE_ERROR", f"artefato obrigatório ausente ou symlink: {path.name}"
            )
        relative = path.relative_to(directory).as_posix()
        manifest[relative] = _sha256_bytes(path.read_bytes())
    return manifest


def _review_input_digest(
    planning_contract: int,
    artifact_manifest: dict[str, str],
    spec_package: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "planning_contract": planning_contract,
        "artifact_manifest": artifact_manifest,
    }
    if spec_package and spec_package.get("managed"):
        payload["spec_package"] = _spec_digest_payload(spec_package)
    return _digest(payload)


def _scope_requirements(directory: Path) -> list[str]:
    scope = directory / "SCOPE.md"
    if scope.is_symlink() or not scope.is_file():
        raise PlanningError("COHERENCE_ERROR", "SCOPE.md ausente")
    identifiers = []
    for identifier in SCOPE_ITEM.findall(scope.read_text(encoding="utf-8")):
        prefix = identifier.split("-", 1)[0]
        if prefix in TRACEABLE_SCOPE_PREFIXES and identifier not in identifiers:
            identifiers.append(identifier)
    if not identifiers:
        raise PlanningError(
            "COHERENCE_ERROR",
            "SCOPE.md não possui itens rastreáveis FLW/REQ/NFR/BR/DAT/INT/ERR/RSK",
        )
    return identifiers


def _roadmap_document(plans: Iterable[PlanContract]) -> str:
    plan_values = list(plans)
    payload = {
        "schema_version": 1,
        "planning_contract": PLANNING_CONTRACT_VERSION,
        "phases": [
            {
                "id": plan.id,
                "result": plan.result,
                "depends_on": list(plan.depends_on),
                "requirements": list(plan.requirements),
                "execution": plan.execution,
                "tasks": [task.id for task in plan.tasks],
            }
            for plan in plan_values
        ],
    }
    body = ["# Roadmap", "", "Gerado deterministicamente a partir dos planos."]
    for plan in plan_values:
        body.extend(
            [
                "",
                f"## {plan.id} — {plan.result or 'Entrega planejada'}",
                "",
                f"- Depende de: {', '.join(plan.depends_on) or 'nenhum'}",
                f"- Escopo: {', '.join(plan.requirements) or 'legado'}",
                f"- Tarefas: {', '.join(task.id for task in plan.tasks) or 'legado'}",
            ]
        )
    return _document(payload, "\n".join(body))


def _schedule(plans: Iterable[PlanContract]) -> dict[str, Any]:
    plan_values = list(plans)
    graph = DependencyGraph(plan_values)
    return {
        "plan_waves": graph.execution_waves(),
        "task_waves": {
            plan.id: TaskDependencyGraph(plan.tasks).execution_waves()
            for plan in plan_values
            if plan.schema_version == 2
        },
    }


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


def _current_spec_snapshot(
    workspace: MethodWorkspace,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Valida a base gerenciada inteira antes de reservar ID ou criar change."""

    current_specs = workspace.current_specs
    manifest_path = current_specs / "MANIFEST.json"
    try:
        trusted_specs = bm_spec_package.confined_no_symlink(
            workspace.root,
            current_specs,
            "base de specs",
        )
        if not trusted_specs.is_dir():
            raise bm_spec_package.SpecPackageError(
                "SPEC_PATH_INVALID", "base de specs não é diretório"
            )
        entries: list[Path] = []
        for candidate in sorted(
            trusted_specs.rglob("*"), key=lambda item: item.as_posix()
        ):
            inspected = bm_spec_package.confined_no_symlink(
                workspace.root,
                candidate,
                "entrada da base de specs",
            )
            if not inspected.is_dir() and not inspected.is_file():
                raise bm_spec_package.SpecPackageError(
                    "SPEC_PATH_INVALID",
                    f"entrada de spec inválida: {candidate}",
                )
            entries.append(inspected)
        if manifest_path.exists():
            manifest = bm_spec_package.validate_manifest(
                manifest_path,
                trusted_root=workspace.root,
            )
        else:
            if any(candidate.is_file() for candidate in entries):
                raise bm_spec_package.SpecPackageError(
                    "SPEC_BASE_MANIFEST_MISSING",
                    "specs atuais legadas exigem manifesto explícito antes de change schema 2",
                )
            manifest = {
                "schema_version": 1,
                "spec_contract": SPEC_CONTRACT_VERSION,
                "specs": [],
                "risk_coverage": [],
            }
        if manifest["specs"]:
            tree = bm_spec_package.inspect_spec_tree(
                current_specs,
                trusted_root=workspace.root,
                required=True,
                allow_root_manifest=True,
            )
            manifest_paths = [item["path"] for item in manifest["specs"]]
            tree_paths = sorted(tree["requirements"])
            if manifest_paths != tree_paths:
                raise bm_spec_package.SpecPackageError(
                    "SPEC_BASE_MANIFEST_MISMATCH",
                    "paths do manifesto da base não correspondem às specs aceitas",
                )
            bm_spec_package._validate_target_requirements(manifest, tree)
        else:
            tree = {"files": {}, "requirements": {}}
    except bm_spec_package.SpecPackageError as error:
        raise PlanningError(error.code, str(error).split(": ", 1)[-1]) from error
    return manifest, tree


def create_change(repo: Path, name: str) -> dict[str, Any]:
    workspace = MethodWorkspace(repo)
    state = workspace.read_state()
    if state.get("active_work"):
        raise PlanningError("COHERENCE_ERROR", "já existe trabalho ativo")
    slug = _slug(name)
    current_manifest, current_tree = _current_spec_snapshot(workspace)
    identifier = workspace.allocate_id("change")
    work_id = f"{identifier}-{slug}"
    directory = workspace.changes_dir / work_id
    if directory.exists():
        raise PlanningError("MODEL_MISMATCH", f"mudança já existe: {work_id}")
    directory.mkdir(parents=True)
    (directory / "plans").mkdir()
    (directory / "results").mkdir()
    expected_specs = directory / "specs" / "expected"
    expected_specs.mkdir(parents=True)
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
        current_specs = workspace.current_specs
        base_manifest_path = current_specs / "MANIFEST.json"
        if not base_manifest_path.exists():
            workspace.atomic_write(
                base_manifest_path,
                json.dumps(
                    {
                        "schema_version": 1,
                        "spec_contract": SPEC_CONTRACT_VERSION,
                        "specs": [],
                        "risk_coverage": [],
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
            )
        for spec in current_manifest["specs"]:
            destination = expected_specs / spec["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            workspace.atomic_write(destination, current_tree["files"][spec["path"]])
        workspace.atomic_write(
            directory / "specs" / "MANIFEST.json",
            json.dumps(
                {
                    "schema_version": 1,
                    "spec_contract": SPEC_CONTRACT_VERSION,
                    "specs": [],
                    "risk_coverage": [],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )
        workspace.atomic_write(
            directory / "COHERENCE.md",
            _document(
                {
                    "schema_version": 2,
                    "planning_contract": PLANNING_CONTRACT_VERSION,
                    "spec_contract": SPEC_CONTRACT_VERSION,
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
                "specs": f".bianchini/changes/{work_id}/specs/expected",
                "coherence": f".bianchini/changes/{work_id}/COHERENCE.md",
            }
        )
        workspace.write_state(state)
    except Exception:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    return {
        "method": "0.4",
        "change": work_id,
        "status": "planning",
        "spec_contract": SPEC_CONTRACT_VERSION,
        "path": str(directory),
    }


def sync_roadmap(repo: Path, change: str) -> dict[str, Any]:
    workspace, directory, _, _, plans = _load_package(repo, change)
    planning_contract = _planning_contract_version(directory)
    if planning_contract < 2:
        raise PlanningError(
            "COHERENCE_ERROR", "roadmap sync exige planning_contract 2"
        )
    if any(plan.schema_version != 2 for plan in plans):
        raise PlanningError(
            "COHERENCE_ERROR", "roadmap v2 exige todos os planos em schema_version 2"
        )
    content = _roadmap_document(plans)
    workspace.atomic_write(directory / "ROADMAP.md", content)
    return {
        "change": directory.name,
        "planning_contract": planning_contract,
        "phases": [plan.id for plan in plans],
        "roadmap": str(directory / "ROADMAP.md"),
        "digest": _sha256_bytes(content.encode("utf-8")),
    }


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
    workspace, directory, current, expected, plans = _load_package(repo, change)
    coherence, _, spec_contract = _coherence_contract(directory)
    spec_package = _load_spec_package(workspace, directory, coherence)
    calculated = ProjectModel.simulate(current, plans)
    differences = calculated.differences(expected)
    result = {
        "valid": not differences,
        "change": directory.name,
        "current_digest": current.digest(),
        "calculated_digest": calculated.digest(),
        "expected_digest": expected.digest(),
        "differences": differences,
    }
    if spec_contract is not None:
        result.update(_spec_digest_payload(spec_package))
    return result


def _read_semantic_report(
    path: Path,
    reviewer: SemanticReviewer,
    *,
    expected_inputs: str | None = None,
) -> dict[str, Any]:
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
    if expected_inputs is not None and value.get("inputs") != expected_inputs:
        raise PlanningError(
            "STALE_EVIDENCE",
            "relatório semântico não corresponde ao manifest atual do pacote",
        )
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


def _assert_approved_package_current(
    workspace: MethodWorkspace,
    directory: Path,
    current: ProjectModel,
    expected: ProjectModel,
    plans: Iterable[PlanContract],
    coherence: dict[str, Any],
) -> dict[str, str]:
    """Recalcula o pacote v2 aprovado antes de executar ou concluir trabalho."""

    planning_contract = int(coherence.get("planning_contract", 1))
    if planning_contract < 2:
        return {}
    _, _, spec_contract = _coherence_contract(directory)
    spec_package = (
        _load_spec_package(workspace, directory, coherence)
        if spec_contract is not None
        else None
    )
    findings = coherence.get("findings")
    semantic = coherence.get("semantic")
    if not isinstance(findings, list) or not isinstance(semantic, dict):
        raise PlanningError("COHERENCE_ERROR", "pacote aprovado está incompleto")
    manifest = _artifact_manifest(directory)
    review_input_digest = _review_input_digest(
        planning_contract, manifest, spec_package
    )
    package_digest = _package_digest(
        current,
        expected,
        plans,
        findings,
        semantic,
        planning_contract=planning_contract,
        artifact_manifest=manifest,
        spec_package=spec_package,
    )
    spec_digests = _spec_digest_payload(spec_package) if spec_package else {}
    if (
        manifest != coherence.get("artifact_manifest")
        or review_input_digest != coherence.get("review_input_digest")
        or package_digest != coherence.get("digest")
        or any(coherence.get(key) != value for key, value in spec_digests.items())
    ):
        raise PlanningError(
            "STALE_EVIDENCE", "pacote aprovado mudou depois do checkpoint"
        )
    return manifest


def coherence_check(
    repo: Path,
    change: str,
    *,
    structural_only: bool,
    semantic_report: Path | None,
) -> dict[str, Any]:
    workspace, directory, current, expected, plans = _load_package(repo, change)
    coherence_contract, planning_contract, spec_contract = _coherence_contract(
        directory
    )
    requirements: list[str] = []
    artifact_manifest: dict[str, str] = {}
    review_input_digest: str | None = None
    schedule: dict[str, Any] | None = None
    spec_package: dict[str, Any] | None = None
    if planning_contract >= 2:
        if any(plan.schema_version != 2 for plan in plans):
            raise PlanningError(
                "COHERENCE_ERROR",
                "mudança v2 exige todos os planos em schema_version 2",
            )
        expected_roadmap = _roadmap_document(plans)
        roadmap_path = directory / "ROADMAP.md"
        if roadmap_path.is_symlink() or not roadmap_path.is_file():
            raise PlanningError("COHERENCE_ERROR", "ROADMAP.md ausente")
        if roadmap_path.read_text(encoding="utf-8") != expected_roadmap:
            raise PlanningError(
                "COHERENCE_ERROR",
                "ROADMAP.md diverge dos planos; execute roadmap sync",
            )
        requirements = _scope_requirements(directory)
        spec_package = _load_spec_package(workspace, directory, coherence_contract)
        artifact_manifest = _artifact_manifest(directory)
        review_input_digest = _review_input_digest(
            planning_contract, artifact_manifest, spec_package
        )
    findings = StructuralValidator().validate(
        current,
        plans,
        expected,
        requirements=requirements,
        require_typed_tasks=planning_contract >= 2,
    )
    if planning_contract >= 2:
        try:
            schedule = _schedule(plans)
        except ValueError:
            # O StructuralValidator já materializa o erro de grafo. Não deixe
            # uma projeção derivada esconder os findings acionáveis.
            schedule = None
    semantic: dict[str, Any] | None
    if structural_only:
        semantic = None
    elif semantic_report is None:
        semantic = SemanticReviewer().unavailable(
            "Relatório semântico não foi fornecido."
        ).to_mapping()
    else:
        semantic = _read_semantic_report(
            semantic_report,
            SemanticReviewer(),
            expected_inputs=review_input_digest if planning_contract >= 2 else None,
        )
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
    package_digest = _package_digest(
        current,
        expected,
        plans,
        mappings,
        semantic,
        planning_contract=planning_contract,
        artifact_manifest=artifact_manifest,
        spec_package=spec_package,
    )
    payload = {
        "schema_version": coherence_contract.get("schema_version", 1),
        "planning_contract": planning_contract,
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
        "artifact_manifest": artifact_manifest,
        "review_input_digest": review_input_digest,
        "schedule": schedule,
        "impact": None,
        "stale_plans": [],
        "approval": None,
        "updated_at": _now(),
        "digest": package_digest,
    }
    if spec_contract is not None and spec_package is not None:
        payload.update(_spec_digest_payload(spec_package))
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
    active = state.get("active_work")
    if isinstance(active, dict):
        active["status"] = state["status"]
    workspace.write_state(state)
    result = {
        "change": directory.name,
        "planning_contract": planning_contract,
        "status": status,
        "digest": payload["digest"],
        "findings": mappings,
        "structural_findings": len(findings),
        "semantic_available": semantic.get("available") if semantic else None,
        "artifact_manifest": artifact_manifest,
        "review_input_digest": review_input_digest,
        "schedule": schedule,
    }
    if spec_contract is not None:
        result["spec_contract"] = spec_contract
    return result


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
    planning_contract = int(payload.get("planning_contract", 1))
    _, _, spec_contract = _coherence_contract(directory)
    spec_package = (
        _load_spec_package(workspace, directory, payload)
        if spec_contract is not None
        else None
    )
    artifact_manifest = (
        _artifact_manifest(directory) if planning_contract >= 2 else {}
    )
    if planning_contract >= 2:
        if artifact_manifest != payload.get("artifact_manifest"):
            raise PlanningError(
                "STALE_EVIDENCE", "artefatos mudaram depois da revisão semântica"
            )
        expected_review_input = _review_input_digest(
            planning_contract, artifact_manifest, spec_package
        )
        if payload.get("review_input_digest") != expected_review_input:
            raise PlanningError(
                "STALE_EVIDENCE", "manifest revisado diverge do pacote atual"
            )
    current_digest = _package_digest(
        current,
        expected,
        plans,
        findings,
        semantic,
        planning_contract=planning_contract,
        artifact_manifest=artifact_manifest,
        spec_package=spec_package,
    )
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
    workspace, directory, current, expected, plans = _load_package(repo, change)
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
    if payload.get("status") in {"approved", "approved_with_stale"}:
        _assert_approved_package_current(
            workspace, directory, current, expected, plans, payload
        )
    else:
        _load_spec_package(workspace, directory, payload)
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
        "pack_identity",
        "pack_digest",
        "package_digest",
        "completed_at",
    }
)


def _task_result_payloads(
    workspace: MethodWorkspace,
    directory: Path,
    plan: PlanContract,
    package_digest: str,
) -> dict[str, dict[str, Any]]:
    task_directory = directory / "results" / "tasks" / plan.id
    workspace.resolve(task_directory)
    if not task_directory.exists():
        return {}
    if task_directory.is_symlink() or not task_directory.is_dir():
        raise PlanningError("MODEL_MISMATCH", f"resultados de {plan.id} são inseguros")
    known = {task.id: task for task in plan.tasks}
    results: dict[str, dict[str, Any]] = {}
    change_prefix = directory.name.split("-", 1)[0]
    for path in sorted(task_directory.iterdir(), key=lambda candidate: candidate.name):
        if path.is_symlink() or not path.is_file() or not re.fullmatch(r"T\d{2,}\.md", path.name):
            raise PlanningError(
                "MODEL_MISMATCH", f"resultado de tarefa inválido: {path.name}"
            )
        task_id = path.stem
        task = known.get(task_id)
        if task is None or task_id in results:
            raise PlanningError(
                "MODEL_MISMATCH", f"resultado pertence a tarefa desconhecida: {task_id}"
            )
        try:
            value = read_frontmatter(path)
        except ValueError as error:
            raise PlanningError("DOCVIVA_INCOMPLETE", str(error)) from error
        identity = f"{change_prefix}/{plan.id}/{task_id}"
        if (
            set(value) != TASK_RESULT_FIELDS
            or value.get("schema_version") != 1
            or value.get("change") != directory.name
            or value.get("plan") != plan.id
            or value.get("task") != task_id
            or value.get("status") != "completed"
            or value.get("expected_result") != task.result
            or value.get("covers") != list(task.covers)
            or value.get("pack_identity") != identity
            or value.get("package_digest") != package_digest
            or not isinstance(value.get("result"), str)
            or not value["result"].strip()
            or not isinstance(value.get("completed_at"), str)
            or not value["completed_at"].strip()
            or not isinstance(value.get("pack_digest"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", value["pack_digest"])
            or not isinstance(value.get("verification"), list)
            or not value["verification"]
            or not all(
                isinstance(item, str) and item.strip()
                for item in value["verification"]
            )
        ):
            raise PlanningError(
                "DOCVIVA_INCOMPLETE", f"resultado inválido de {identity}"
            )
        results[task_id] = value
    return results


def task_complete(
    repo: Path,
    change: str,
    plan_id: str,
    task_id: str,
    *,
    context_pack: Path,
    result: str,
    verification: Iterable[str],
) -> dict[str, Any]:
    """Registra uma tarefa executada a partir do pack explícito e vigente."""

    workspace, directory, _current, _expected, plans = _load_package(repo, change)
    coherence = read_frontmatter(directory / "COHERENCE.md")
    if coherence.get("status") not in {"approved", "approved_with_stale"}:
        raise PlanningError("COHERENCE_ERROR", "tarefa exige pacote global aprovado")
    _assert_approved_package_current(
        workspace, directory, _current, _expected, plans, coherence
    )
    if plan_id in coherence.get("stale_plans", []):
        raise PlanningError("IMPACT_STALE", f"{plan_id} está stale")
    plan = _plan_by_id(plans, plan_id)
    if plan.schema_version != 2:
        raise PlanningError(
            "MODEL_MISMATCH", "resultado por tarefa exige plano schema 2"
        )
    matches = [task for task in plan.tasks if task.id == task_id]
    if len(matches) != 1:
        raise PlanningError("MODEL_MISMATCH", f"tarefa desconhecida: {plan_id}/{task_id}")
    task = matches[0]
    package_digest = coherence.get("digest")
    if not isinstance(package_digest, str) or not re.fullmatch(
        r"[0-9a-f]{64}", package_digest
    ):
        raise PlanningError("STALE_EVIDENCE", "pacote aprovado possui digest inválido")
    plan_results = _result_payloads(directory)
    missing_plans = [dependency for dependency in plan.depends_on if dependency not in plan_results]
    if missing_plans:
        raise PlanningError(
            "MISSING_PROVIDER",
            "dependências ainda não concluídas: " + ", ".join(missing_plans),
        )
    task_results = _task_result_payloads(workspace, directory, plan, package_digest)
    if task_id in task_results:
        raise PlanningError("COHERENCE_ERROR", f"{plan_id}/{task_id} já foi concluída")
    missing_tasks = [dependency for dependency in task.depends_on if dependency not in task_results]
    if missing_tasks:
        raise PlanningError(
            "MISSING_PROVIDER",
            "tarefas ainda não concluídas: " + ", ".join(missing_tasks),
        )
    try:
        pack = bm_context.verify_context_pack(workspace.root, context_pack)
    except bm_context.ContextPackError as error:
        raise PlanningError(error.code, str(error).split(": ", 1)[-1]) from error
    identity = f"{directory.name.split('-', 1)[0]}/{plan.id}/{task.id}"
    if pack.get("unit") != identity:
        raise PlanningError(
            "STALE_EVIDENCE", f"context pack pertence a {pack.get('unit')}, não a {identity}"
        )
    summary = result.strip()
    evidence = [item.strip() for item in verification if item.strip()]
    if not summary:
        raise PlanningError("DOCVIVA_INCOMPLETE", "conclusão da tarefa exige resultado")
    if not evidence:
        raise PlanningError("STALE_EVIDENCE", "conclusão da tarefa exige verificação")
    completed_at = _now()
    payload = {
        "schema_version": 1,
        "change": directory.name,
        "plan": plan.id,
        "task": task.id,
        "status": "completed",
        "expected_result": task.result,
        "result": summary,
        "covers": list(task.covers),
        "verification": evidence,
        "pack_identity": identity,
        "pack_digest": pack["digest"],
        "package_digest": package_digest,
        "completed_at": completed_at,
    }
    workspace.atomic_write(
        directory / "results" / "tasks" / plan.id / f"{task.id}.md",
        _document(payload, f"# Resultado {plan.id}/{task.id}\n\n{summary}"),
    )
    state = workspace.read_state()
    state.update(
        {
            "current_unit": None,
            "status": "approved",
            "blockers": [],
            "next_action": f"Consultar a próxima onda de {directory.name}.",
            "digest": package_digest,
            "updated_at": _now(),
        }
    )
    active = state.get("active_work")
    if isinstance(active, dict):
        active["status"] = "approved"
    workspace.write_state(state)
    return {
        "change": directory.name,
        "plan": plan.id,
        "task": task.id,
        "status": "completed",
        "pack_identity": identity,
        "pack_digest": pack["digest"],
        "package_digest": package_digest,
    }


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
    completed_tasks: Iterable[str] = (),
) -> dict[str, Any]:
    """Registra a entrega real e rejeita drift silencioso do contrato aprovado."""

    workspace, directory, current, expected, plans = _load_package(repo, change)
    coherence = read_frontmatter(directory / "COHERENCE.md")
    if coherence.get("status") not in {"approved", "approved_with_stale"}:
        raise PlanningError("COHERENCE_ERROR", "plano exige pacote global aprovado")
    _assert_approved_package_current(
        workspace, directory, current, expected, plans, coherence
    )
    if plan_id in coherence.get("stale_plans", []):
        raise PlanningError("IMPACT_STALE", f"{plan_id} está stale")
    plan = _plan_by_id(plans, plan_id)
    completed_task_ids = list(
        dict.fromkeys(value.strip() for value in completed_tasks if value.strip())
    )
    managed_task_results = (
        plan.schema_version == 2
        and coherence.get("schema_version") == 2
        and coherence.get("spec_contract") == SPEC_CONTRACT_VERSION
    )
    if plan.schema_version == 2:
        expected_tasks = [task.id for task in plan.tasks]
        if managed_task_results:
            task_results = _task_result_payloads(
                workspace, directory, plan, str(coherence.get("digest"))
            )
            recorded_tasks = [
                task_id for task_id in expected_tasks if task_id in task_results
            ]
            if recorded_tasks != expected_tasks:
                missing = [task for task in expected_tasks if task not in recorded_tasks]
                raise PlanningError(
                    "DOCVIVA_INCOMPLETE",
                    "conclusão exige resultados próprios para todas as tarefas (ausentes: "
                    + ", ".join(missing)
                    + ")",
                )
        if (
            (managed_task_results and completed_task_ids)
            or not managed_task_results
        ) and completed_task_ids != expected_tasks:
            missing = [task for task in expected_tasks if task not in completed_task_ids]
            unknown = [task for task in completed_task_ids if task not in expected_tasks]
            details = []
            if missing:
                details.append("ausentes: " + ", ".join(missing))
            if unknown:
                details.append("desconhecidas: " + ", ".join(unknown))
            if not details:
                details.append("ordem divergente do plano")
            raise PlanningError(
                "DOCVIVA_INCOMPLETE",
                "conclusão exige todas as tarefas na ordem aprovada ("
                + "; ".join(details)
                + ")",
            )
        completed_task_ids = expected_tasks
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
    completed_at = _now()
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
        "completed_tasks": completed_task_ids,
        "impact": {
            "radius": "local",
            "stale_plans": [],
            "reason": "entrega equivalente ao delta aprovado",
        },
        "completed_at": completed_at,
    }
    if plan.schema_version == 2 and not managed_task_results:
        for task in plan.tasks:
            task_payload = {
                "schema_version": 1,
                "change": directory.name,
                "plan": plan.id,
                "task": task.id,
                "status": "completed",
                "expected_result": task.result,
                "result": summary,
                "covers": list(task.covers),
                "verification": evidence,
                "completed_at": completed_at,
            }
            workspace.atomic_write(
                directory / "results" / "tasks" / plan.id / f"{task.id}.md",
                _document(
                    task_payload,
                    f"# Resultado {plan.id}/{task.id}\n\n{summary}",
                ),
            )
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
        "completed_tasks": completed_task_ids,
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
    workspace, directory, current, expected, plans = _load_package(root, change)
    state = workspace.read_state()
    coherence = read_frontmatter(directory / "COHERENCE.md")
    if coherence.get("status") not in {"approved", "approved_with_stale"}:
        raise PlanningError("COHERENCE_ERROR", "planejamento exige COHERENCE approved")
    planning_contract = int(coherence.get("planning_contract", 1))
    manifest = _assert_approved_package_current(
        workspace, directory, current, expected, plans, coherence
    )
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
    required_paths = [directory / "COHERENCE.md"]
    if planning_contract >= 2:
        required_paths.extend(directory / relative for relative in manifest)
    else:
        required_paths.extend((directory / "SYSTEM_MODEL.md", plan_matches[0]))
    for required in required_paths:
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


def _public_close_result(
    result: dict[str, Any],
    *,
    model_digest: str,
    specs_promoted: bool,
    specs_status: str,
) -> dict[str, Any]:
    return {
        **result,
        "model_digest": model_digest,
        "specs_promoted": specs_promoted,
        "specs_status": specs_status,
    }


def close_change(repo: Path, change: str) -> dict[str, Any]:
    """Promove o modelo final para ``current`` e arquiva o ciclo completo."""

    root = repo.resolve()
    preparing_recovered = False
    try:
        pending = bm_close.pending_close(root)
        if pending is not None:
            if pending.get("change") != change:
                raise PlanningError(
                    "CLOSE_CONFLICT",
                    f"fechamento pendente pertence a {pending.get('change')}",
                )
            recovered = bm_close.recover_pending_close(root)
            if recovered is None:
                raise PlanningError("JOURNAL_CORRUPT", "journal desapareceu durante recovery")
            if recovered.get("status") != "restored":
                try:
                    recovered_model = ProjectModel.from_system_model(
                        MethodWorkspace(root).current_system_model
                    )
                except ValueError as error:
                    raise PlanningError("MODEL_MISMATCH", str(error)) from error
                return _public_close_result(
                    recovered,
                    model_digest=recovered_model.digest(),
                    specs_promoted=True,
                    specs_status="managed",
                )
            preparing_recovered = True
    except bm_close.CloseRecoveryError as error:
        raise PlanningError(error.code, str(error).split(": ", 1)[-1]) from error
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
    planning_contract = int(coherence.get("planning_contract", 1))
    _, _, spec_contract = _coherence_contract(directory)
    spec_package = (
        _load_spec_package(workspace, directory, coherence)
        if spec_contract is not None
        else None
    )
    artifact_manifest = _assert_approved_package_current(
        workspace, directory, current, expected, plans, coherence
    )
    package_digest = _package_digest(
        current,
        expected,
        plans,
        findings,
        semantic,
        planning_contract=planning_contract,
        artifact_manifest=artifact_manifest,
        spec_package=spec_package,
    )
    if planning_contract < 2 and package_digest != coherence.get("digest"):
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
        if plan.schema_version == 2 and result.get("completed_tasks") != [
            task.id for task in plan.tasks
        ]:
            raise PlanningError(
                "DOCVIVA_INCOMPLETE",
                f"resultado de {plan.id} não comprova todas as tarefas",
            )
    calculated = _effective_model(current, plans, results)
    differences = calculated.differences(expected)
    if differences:
        raise PlanningError(
            "MODEL_MISMATCH", "modelo entregue diverge do SYSTEM_MODEL final"
        )
    closing_findings = StructuralValidator().validate(
        current,
        plans,
        expected,
        requirements=(
            _scope_requirements(directory) if planning_contract >= 2 else ()
        ),
        require_typed_tasks=planning_contract >= 2,
    )
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
    if spec_package is not None:
        summary.update(
            {
                "specs_promoted": True,
                "specs_status": "managed",
                **_spec_digest_payload(spec_package),
            }
        )
    summary_document = _document(
        summary,
        "# Resumo\n\n"
        f"Mudança {directory.name} concluída com {len(plans)} plano(s) verificado(s).",
    )
    if spec_package is not None:
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
                    "id": directory.name,
                    "status": "completed",
                },
                "pointers": {
                    "architecture": ".bianchini/current/ARCHITECTURE.md",
                    "system_model": ".bianchini/current/SYSTEM_MODEL.md",
                    "specs": ".bianchini/current/specs",
                    "coherence": f".bianchini/archive/{directory.name}/COHERENCE.md",
                },
                "digest": expected.digest(),
                "updated_at": _now(),
            }
        )
        normalized_state = workspace._validate_state(state)
        next_state = (
            "---\n"
            + json.dumps(
                normalized_state,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n---\n# Estado atual\n"
        )
        try:
            result = bm_close.crash_recoverable_close(
                root,
                directory.name,
                specs_source=directory / "specs" / "expected",
                specs_manifest=directory / "specs" / "MANIFEST.json",
                summary=summary_document,
                next_state=next_state,
            )
        except bm_close.CloseRecoveryError as error:
            raise PlanningError(error.code, str(error).split(": ", 1)[-1]) from error
        if preparing_recovered:
            result = {**result, "recovered": True}
        return _public_close_result(
            result,
            model_digest=expected.digest(),
            specs_promoted=True,
            specs_status="managed",
        )
    workspace.atomic_write(
        directory / "SUMMARY.md",
        summary_document,
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
    "sync_roadmap",
    "execution_workspace_check",
    "execution_workspace_create",
    "execution_workspace_locate",
    "validate_change_model",
]
