"""Workflows persistentes do Bianchini Method 0.4.

O CLI e as skills cruzam este seam. A Implementation concentra layout,
transições de quick/debug e a migração explícita sem consultar `.planning`.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import bm_docviva
import bm_risk
from bm_project_model import ProjectModel, plan_file_for_id, read_frontmatter
from bm_workspace import MethodWorkspace


METHOD_VERSION = "0.4"
MAX_STATE_BYTES = 64 * 1024
WORKSPACE_ROOT = ".bianchini"
STATE_RELATIVE = ".bianchini/STATE.md"
TERMINAL_DEBUG = {"resolved", "blocked", "escalated"}


class WorkflowError(Exception):
    """Falha esperada com código estável para callers e testes."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _digest_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _frontmatter(value: dict[str, Any], body: str) -> bytes:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)
    return f"---\n{encoded}\n---\n\n{body.rstrip()}\n".encode("utf-8")


def _read_frontmatter(path: Path, label: str) -> dict[str, Any]:
    try:
        return read_frontmatter(path)
    except (OSError, UnicodeError, ValueError) as error:
        raise WorkflowError("MODEL_MISMATCH", f"{label}: {error}") from error


def _atomic_write(path: Path, content: bytes) -> None:
    absolute = path.absolute()
    marker = next((parent for parent in (absolute.parent, *absolute.parents) if parent.name == ".bianchini"), None)
    if marker is None:
        raise WorkflowError("MODEL_MISMATCH", f"escrita fora de .bianchini: {path}")
    try:
        MethodWorkspace(marker.parent).atomic_write(absolute, content)
    except (OSError, UnicodeError, ValueError) as error:
        raise WorkflowError("MODEL_MISMATCH", str(error)) from error


def _repo_root(repo: Path) -> Path:
    root = repo.resolve()
    completed = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise WorkflowError("DIRTY_WORKSPACE", "o diretório não é uma raiz Git")
    top = Path(completed.stdout.strip()).resolve()
    if top != root:
        raise WorkflowError("DIRTY_WORKSPACE", f"--repo deve apontar para {top}")
    return root


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=False
    )
    if completed.returncode != 0:
        raise WorkflowError(
            "DIRTY_WORKSPACE", completed.stderr.strip() or "comando Git falhou"
        )
    return completed.stdout.strip()


def _workspace(root: Path) -> Path:
    return root / WORKSPACE_ROOT


def _state_path(root: Path) -> Path:
    return root / STATE_RELATIVE


def _empty_system_model() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "modules": [],
        "interfaces": [],
        "capabilities": [],
        "contracts": [],
        "ownership": [],
        "data": [],
        "integrations": [],
        "journeys": [],
        "invariants": [],
        "effects": [],
    }


def _has_legacy_bianchini_artifacts(root: Path) -> bool:
    """Detecta somente fontes aceitas pela migração explícita do método."""

    direct_sources = (
        root / "docs/living/PROJECT_STATE.md",
        root / "docs/bianchini",
        root / "artifacts/bianchini",
        root / ".superpowers/bianchini/direct",
    )
    if any(path.exists() for path in direct_sources):
        return True
    return bool(_recognized_design_files(root / "docs/design"))


def init_workspace(repo: Path, *, allow_existing: bool = False) -> dict[str, Any]:
    """Cria a raiz canônica sem percorrer namespaces estrangeiros."""

    root = _repo_root(repo)
    workspace = _workspace(root)
    state = _state_path(root)
    if state.is_file():
        current = _read_frontmatter(state, "STATE.md")
        return {
            "method": current.get("method"),
            "status": current.get("status"),
            "workspace": str(workspace),
            "created": False,
        }
    if _has_legacy_bianchini_artifacts(root):
        raise WorkflowError(
            "MIGRATION_REQUIRED", "documentação anterior detectada; use /migrar-bianchini"
        )
    if workspace.exists() and not allow_existing:
        raise WorkflowError("MODEL_MISMATCH", ".bianchini existe sem STATE.md válido")

    method_workspace = MethodWorkspace(root)
    method_workspace.initialize()
    state_value = method_workspace.read_state()
    state_value["next_action"] = "Iniciar /sdd-planning, /executar-direto ou /corrigir-bug."
    state_value["updated_at"] = _now()
    state_value.setdefault("pointers", {})["coherence"] = None
    method_workspace.write_state(state_value)
    return {
        "method": METHOD_VERSION,
        "status": "idle",
        "workspace": str(workspace),
        "created": True,
    }


def require_workspace(repo: Path, *, create: bool = False) -> dict[str, Any]:
    """Resolve exclusivamente o workspace 0.4, sem fallback para formatos antigos."""

    root = _repo_root(repo)
    state = _state_path(root)
    if state.is_file():
        return read_state(root)
    if _has_legacy_bianchini_artifacts(root):
        raise WorkflowError(
            "MIGRATION_REQUIRED", "documentação anterior detectada; use /migrar-bianchini"
        )
    if create:
        init_workspace(root)
        return read_state(root)
    if _workspace(root).exists():
        raise WorkflowError("DOCVIVA_INCOMPLETE", ".bianchini existe sem STATE.md válido")
    raise WorkflowError(
        "DOCVIVA_INCOMPLETE", "Bianchini Method 0.4 não iniciado; execute model init"
    )


def read_state(root: Path) -> dict[str, Any]:
    try:
        value = MethodWorkspace(root).read_state()
    except (OSError, UnicodeError, ValueError) as error:
        raise WorkflowError("DOCVIVA_INCOMPLETE", str(error)) from error
    if value.get("method") != METHOD_VERSION:
        raise WorkflowError("MIGRATION_REQUIRED", "STATE.md não pertence ao método 0.4")
    if any(key in value for key in ("history", "events", "ledger", "hypotheses")):
        raise WorkflowError("DOCVIVA_INCOMPLETE", "STATE.md deve ser somente um índice")
    return value


def write_state(root: Path, value: dict[str, Any]) -> None:
    try:
        MethodWorkspace(root).write_state(
            value,
            "# Estado atual\n\nEste arquivo é um índice compacto. Siga os ponteiros para detalhes.",
        )
    except (OSError, UnicodeError, ValueError) as error:
        raise WorkflowError("DOCVIVA_INCOMPLETE", str(error)) from error


def update_state(root: Path, **changes: Any) -> dict[str, Any]:
    state = read_state(root)
    state.update(changes)
    state["updated_at"] = _now()
    write_state(root, state)
    return state


def validate_workspace(repo: Path) -> dict[str, Any]:
    root = _repo_root(repo)
    state = read_state(root)
    required = {
        "schema_version",
        "method",
        "status",
        "active_work",
        "blockers",
        "next_action",
        "pointers",
        "updated_at",
    }
    missing = sorted(required - set(state))
    if missing:
        raise WorkflowError("MODEL_MISMATCH", "STATE.md incompleto: " + ", ".join(missing))
    model = root / str(state["pointers"]["system_model"])
    model_value = _read_frontmatter(model, "SYSTEM_MODEL.md")
    model_required = set(_empty_system_model())
    model_missing = sorted(model_required - set(model_value))
    if model_missing:
        raise WorkflowError(
            "MODEL_MISMATCH", "SYSTEM_MODEL.md incompleto: " + ", ".join(model_missing)
        )
    return {
        "valid": True,
        "method": METHOD_VERSION,
        "status": state["status"],
        "state": str(_state_path(root)),
        "system_model": str(model),
    }


def classify_quick_risk(
    scope: int,
    external_effect: int,
    migration: int,
    concurrency: int,
    money: int,
    overrides: Iterable[str] = (),
) -> dict[str, Any]:
    values = {
        "scope": scope,
        "external_effect": external_effect,
        "migration": migration,
        "concurrency": concurrency,
        "money": money,
    }
    invalid = [name for name, value in values.items() if value not in {0, 1, 2}]
    if invalid:
        raise WorkflowError("MISSING_GUARD", "scores devem estar entre 0 e 2: " + ", ".join(invalid))
    automatic_overrides = {
        name
        for name, enabled in (
            ("multiple_objectives", scope == 2),
            ("destructive_migration", migration == 2),
            ("uncontrolled_concurrency", concurrency == 2),
        )
        if enabled
    }
    forced = sorted(set(overrides) | automatic_overrides)
    score = sum(values.values())
    if score >= 3 or forced:
        route = "protected"
    else:
        route = "normal"
    reasons = [f"{name}={value}" for name, value in values.items() if value]
    reasons.extend(f"override:{name}" for name in forced)
    return {
        "score": score,
        "dimensions": values,
        "route": route,
        "overrides": forced,
        "reasons": reasons,
    }


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    if not slug:
        raise WorkflowError("MODEL_MISMATCH", "não foi possível gerar slug")
    return slug[:48].rstrip("-")


def quick_start(
    repo: Path,
    objective: str,
    scope_text: str,
    acceptance: list[str],
    verification: list[str],
    risk: dict[str, Any],
    guards: list[str],
    *,
    webhook_flow: bool = False,
    payment_flow: bool = False,
) -> dict[str, Any]:
    root = _repo_root(repo)
    state = read_state(root)
    if state.get("active_work"):
        raise WorkflowError("COHERENCE_ERROR", "já existe trabalho ativo")
    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    base_head = head.stdout.strip() if head.returncode == 0 else "UNBORN"
    try:
        model_before = ProjectModel.from_system_model(
            root / ".bianchini/current/SYSTEM_MODEL.md"
        ).to_mapping()
    except (OSError, UnicodeError, ValueError) as error:
        raise WorkflowError("MODEL_MISMATCH", f"SYSTEM_MODEL atual: {error}") from error
    quick_id = MethodWorkspace(root).allocate_id("quick")
    slug = _slug(objective)
    work_id = f"{quick_id}-{slug}"
    directory = root / ".bianchini/quick" / work_id
    directory.mkdir()
    required: set[str] = set()
    dimensions = risk["dimensions"]
    if dimensions["external_effect"]:
        required.update({"official_docs", "timeout_recovery", "rollback", "sandbox"})
    if dimensions["migration"]:
        required.add("rollback")
    if dimensions["concurrency"]:
        required.update({"idempotency", "deduplication", "replay_order"})
    if dimensions["money"]:
        required.update(
            {
                "source_of_truth",
                "idempotency",
                "persistence",
                "reconciliation",
                "sandbox",
            }
        )
    if risk["route"] == "protected":
        required.add("local_contract")
    if webhook_flow:
        required.update(
            {"authenticity", "deduplication", "replay_order", "persistence"}
        )
    if payment_flow:
        required.update(
            {
                "source_of_truth",
                "idempotency",
                "timeout_recovery",
                "persistence",
                "reconciliation",
            }
        )
    required.update(risk.get("additional_guards", []))
    missing = sorted(required - set(guards))
    brief = {
        "schema_version": 1,
        "docviva_contract": 1,
        "docviva_before": bm_docviva.snapshot_docviva(root),
        "id": work_id,
        "base_head": base_head,
        "model_before": model_before,
        "status": "active",
        "objective": objective,
        "scope": scope_text,
        "acceptance": acceptance,
        "verification": verification,
        "risk": risk,
        "guards": sorted(set(guards)),
        "required_guards": sorted(required),
        "missing_guards": missing,
        "flow": {"webhook": webhook_flow, "payment": payment_flow},
        "production_checkpoint_required": bool(
            dimensions["external_effect"] == 2 or dimensions["money"] == 2
        ),
        "created_at": _now(),
    }
    brief["digest"] = _digest_bytes(
        json.dumps(brief, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    )
    _atomic_write(directory / "BRIEF.md", _frontmatter(brief, f"# Quick {work_id}\n\n{objective}"))
    _atomic_write(
        directory / "PROGRESS.md",
        _frontmatter(
            {"schema_version": 1, "id": work_id, "status": "active", "events": []},
            "# Progresso\n\nNenhum checkpoint registrado.",
        ),
    )
    update_state(
        root,
        active_work={"kind": "quick", "id": work_id, "status": "active"},
        status="active",
        next_action=(
            "Completar guards ausentes durante a execução: " + ", ".join(missing)
            if missing
            else f"Executar e verificar {work_id}."
        ),
    )
    return {**brief, "path": str(directory)}


def _quick_directory(root: Path, work_id: str) -> Path:
    if not re.fullmatch(r"Q\d{3}-[a-z0-9]+(?:-[a-z0-9]+)*", work_id):
        raise WorkflowError("MODEL_MISMATCH", "ID de quick inválido")
    directory = MethodWorkspace(root).resolve(f"quick/{work_id}")
    if directory.is_symlink() or not directory.is_dir():
        raise WorkflowError("MODEL_MISMATCH", f"quick não encontrado: {work_id}")
    return directory


def quick_status(repo: Path, work_id: str | None = None) -> dict[str, Any]:
    root = _repo_root(repo)
    read_state(root)
    if work_id:
        directory = _quick_directory(root, work_id)
        brief = _read_frontmatter(directory / "BRIEF.md", "brief do quick")
        result_path = directory / "RESULT.md"
        result = _read_frontmatter(result_path, "resultado do quick") if result_path.is_file() else None
        return {
            "id": work_id,
            "status": result.get("status") if result else brief.get("status", "active"),
            "route": brief["risk"]["route"],
            "missing_guards": brief.get("missing_guards", []),
            "path": str(directory),
        }
    items: list[dict[str, Any]] = []
    for directory in sorted((root / ".bianchini/quick").glob("Q*")):
        if directory.is_dir() and not directory.is_symlink():
            brief = _read_frontmatter(directory / "BRIEF.md", "brief do quick")
            result_path = directory / "RESULT.md"
            result = _read_frontmatter(result_path, "resultado do quick") if result_path.is_file() else None
            items.append(
                {
                    "id": brief["id"],
                    "status": result.get("status") if result else brief.get("status", "active"),
                    "route": brief["risk"]["route"],
                }
            )
    return {"items": items}


def quick_checkpoint(
    repo: Path,
    work_id: str,
    summary: str,
    changed_files: list[str],
    commands: list[str],
    evidence: list[str],
    blockers: list[str],
    next_action: str,
    guards: list[str] | None = None,
) -> dict[str, Any]:
    root = _repo_root(repo)
    directory = _quick_directory(root, work_id)
    if (directory / "RESULT.md").is_file():
        raise WorkflowError("ORDER_VIOLATION", "quick terminal é imutável")
    progress_path = directory / "PROGRESS.md"
    progress = _read_frontmatter(progress_path, "progresso do quick")
    event = {
        "summary": summary.strip(),
        "changed_files": sorted(set(changed_files)),
        "commands": commands,
        "evidence": evidence,
        "blockers": blockers,
        "guards": sorted(set(guards or [])),
        "fingerprint": _tree_fingerprint(root),
        "at": _now(),
    }
    progress.setdefault("events", []).append(event)
    progress["updated_at"] = _now()
    brief = _read_frontmatter(directory / "BRIEF.md", "brief do quick")
    event["brief_digest"] = brief.get("digest")
    risk, missing_guards = _quick_final_risk(root, brief, progress.get("events", []))
    event["risk"] = risk
    event["missing_guards"] = missing_guards
    _atomic_write(
        progress_path,
        _frontmatter(progress, f"# Progresso de {work_id}\n\n{summary.strip()}"),
    )
    update_state(
        root,
        next_action=next_action,
        blockers=blockers,
        active_work={"kind": "quick", "id": work_id, "status": "active"},
    )
    return {
        "id": work_id,
        "status": "active",
        "checkpoint": len(progress["events"]),
        "risk": risk,
        "missing_guards": missing_guards,
    }


def _quick_diff_paths(root: Path, base_head: str | None = None) -> list[str]:
    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    tracked_args = ["diff", "--name-only"]
    if base_head and base_head != "UNBORN":
        base = subprocess.run(
            ["git", "rev-parse", "--verify", f"{base_head}^{{commit}}"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        ancestor = subprocess.run(
            ["git", "merge-base", "--is-ancestor", base_head, "HEAD"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        if base.returncode != 0 or ancestor.returncode != 0:
            raise WorkflowError(
                "STALE_EVIDENCE", "base Git do quick não pertence ao HEAD atual"
            )
        tracked_args.append(base_head)
    elif head.returncode == 0 and base_head != "UNBORN":
        tracked_args.append("HEAD")
    tracked_args.extend(
        ["--", ".", ":(exclude).bianchini", ":(exclude).planning"]
    )
    tracked = set(_git(root, *tracked_args).splitlines())
    if base_head == "UNBORN" and head.returncode == 0:
        tracked.update(
            _git(
                root,
                "ls-files",
                "--",
                ".",
                ":(exclude).bianchini",
                ":(exclude).planning",
            ).splitlines()
        )
    untracked = set(
        _git(
            root,
            "ls-files",
            "--others",
            "--exclude-standard",
            "--",
            ".",
            ":(exclude).bianchini",
            ":(exclude).planning",
        ).splitlines()
    )
    return sorted(path for path in tracked | untracked if path)


def _quick_final_risk(
    root: Path, brief: dict[str, Any], events: Iterable[dict[str, Any]]
) -> tuple[dict[str, Any], list[str]]:
    initial = brief.get("risk", {})
    if initial.get("risk_contract") != bm_risk.RISK_CONTRACT:
        return initial, list(brief.get("missing_guards", []))
    inputs = initial.get("risk_inputs", {})
    declared_paths = set(inputs.get("declared_paths", []))
    available_guards = set(brief.get("guards", []))
    for event in events:
        if not isinstance(event, dict):
            continue
        declared_paths.update(event.get("changed_files", []))
        available_guards.update(event.get("guards", []))
    try:
        model_before = brief.get("model_before")
        model_after = None
        if model_before is not None:
            model_after = ProjectModel.from_system_model(
                root / ".bianchini/current/SYSTEM_MODEL.md"
            ).to_mapping()
        risk = bm_risk.assess_quick_risk(
            int(initial.get("declared_score", initial.get("score", 0))),
            flags=inputs.get("flags", {}),
            declared_paths=declared_paths,
            diff_paths=_quick_diff_paths(root, brief.get("base_head")),
            current_model=model_before,
            expected_model=model_after,
            phase="finish",
        )
    except (OSError, UnicodeError, ValueError, bm_risk.RiskInputError) as error:
        if isinstance(error, bm_risk.RiskInputError):
            raise WorkflowError(error.code, str(error).split(": ", 1)[-1]) from error
        raise WorkflowError("MODEL_MISMATCH", f"SYSTEM_MODEL atual: {error}") from error
    initial_floor = int(initial.get("derived_floor", 0))
    initial_guards = set(initial.get("additional_guards", []))
    risk["start_floor"] = initial_floor
    risk["reclassified"] = bool(
        risk.get("derived_floor", 0) > initial_floor
        or set(risk.get("additional_guards", [])) - initial_guards
    )
    required = set(brief.get("required_guards", [])) | set(
        risk.get("additional_guards", [])
    )
    return risk, sorted(required - available_guards)


def quick_finish(
    repo: Path,
    work_id: str,
    status: str,
    behaviors: list[str],
    verification: list[str],
    limitations: list[str],
    next_action: str,
    blockers: list[str],
    production_authorized: bool,
    docviva_kind: str | None = None,
    docviva_outcome: str | None = None,
    docviva_artifacts: Iterable[str] = (),
    docviva_justification: str | None = None,
) -> dict[str, Any]:
    root = _repo_root(repo)
    directory = _quick_directory(root, work_id)
    if status not in {"completed", "blocked"}:
        raise WorkflowError("MODEL_MISMATCH", "status terminal de quick inválido")
    if (directory / "RESULT.md").is_file():
        raise WorkflowError("ORDER_VIOLATION", "quick terminal é imutável")
    brief = _read_frontmatter(directory / "BRIEF.md", "brief do quick")
    docviva: dict[str, Any] | None = None
    if status == "completed":
        stored_digest = brief.get("digest")
        unsigned = {key: value for key, value in brief.items() if key != "digest"}
        current_digest = _digest_bytes(
            json.dumps(
                unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        )
        if stored_digest != current_digest:
            raise WorkflowError("STALE_EVIDENCE", "BRIEF.md mudou após a classificação")
        if brief.get("production_checkpoint_required") and not production_authorized:
            raise WorkflowError(
                "EXTERNAL_AUTHORITY_REQUIRED", "efeito real exige checkpoint explícito"
            )
        if not verification:
            raise WorkflowError("STALE_EVIDENCE", "conclusão exige evidência de verificação")
        progress = _read_frontmatter(directory / "PROGRESS.md", "progresso do quick")
        events = progress.get("events", [])
        last = events[-1] if isinstance(events, list) and events else None
        if not isinstance(last, dict):
            raise WorkflowError("STALE_EVIDENCE", "conclusão exige checkpoint verificado")
        if last.get("brief_digest") != stored_digest:
            raise WorkflowError("STALE_EVIDENCE", "checkpoint pertence a outro brief")
        if last.get("fingerprint") != _tree_fingerprint(root):
            raise WorkflowError(
                "STALE_EVIDENCE", "código mudou após o último checkpoint"
            )
        final_risk, missing_guards = _quick_final_risk(root, brief, events)
        if missing_guards:
            raise WorkflowError(
                "MISSING_GUARD", "guards ausentes: " + ", ".join(missing_guards)
            )
        if brief.get("docviva_contract") == 1:
            if not docviva_kind or not docviva_outcome:
                raise WorkflowError(
                    "DOCVIVA_INCOMPLETE",
                    "quick concluído exige classificação DocViva explícita",
                )
            try:
                docviva = bm_docviva.verify_docviva_impact(
                    root,
                    brief.get("docviva_before", {}),
                    {"kind": docviva_kind, "outcome": docviva_outcome},
                    docviva_artifacts,
                    docviva_justification or "",
                    required=docviva_kind in bm_docviva.REQUIRED_KINDS,
                )
            except bm_docviva.DocVivaError as error:
                raise WorkflowError(error.code, str(error).split(": ", 1)[-1]) from error
    elif not blockers:
        raise WorkflowError("MODEL_MISMATCH", "quick bloqueado exige motivo")
    else:
        final_risk = brief.get("risk")
    result = {
        "schema_version": 1,
        "id": work_id,
        "status": status,
        "behaviors": behaviors,
        "verification": verification,
        "limitations": limitations,
        "blockers": blockers,
        "production_authorized": production_authorized,
        "docviva": docviva,
        "risk": final_risk,
        "fingerprint": _tree_fingerprint(root),
        "finished_at": _now(),
    }
    _atomic_write(
        directory / "RESULT.md",
        _frontmatter(result, f"# Resultado de {work_id}\n\nStatus: {status}."),
    )
    update_state(
        root,
        active_work=None,
        current_unit=None,
        status="idle" if status != "blocked" else "blocked",
        blockers=blockers,
        last_completed={"kind": "quick", "id": work_id, "status": status},
        next_action=next_action,
    )
    return {
        "id": work_id,
        "status": status,
        "path": str(directory / "RESULT.md"),
        "docviva": docviva,
        "risk": final_risk,
    }


DEBUG_TRANSITIONS = {
    "intake": "reproduced",
    "reproduced": "diagnosed",
    "diagnosed": "red",
    "red": "fixing",
    "fixing": "green",
    "green": "regression_checked",
    "regression_checked": "documented",
}


def _debug_path(root: Path, debug_id: str, resolved: bool = False) -> Path:
    folder = "resolved" if resolved else "active"
    if not re.fullmatch(r"D\d{3}-[a-z0-9]+(?:-[a-z0-9]+)*", debug_id):
        raise WorkflowError("MODEL_MISMATCH", "ID de debug inválido")
    return MethodWorkspace(root).resolve(f"debug/{folder}/{debug_id}.md")


def _tree_fingerprint(root: Path) -> str:
    head_result = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if head_result.returncode == 0:
        head = head_result.stdout.strip()
        diff = _git(
            root,
            "diff",
            "--binary",
            "HEAD",
            "--",
            ".",
            ":(exclude).bianchini",
            ":(exclude).planning",
        )
    else:
        head = "UNBORN"
        diff = _git(
            root,
            "diff",
            "--binary",
            "--",
            ".",
            ":(exclude).bianchini",
            ":(exclude).planning",
        )
    untracked = _git(
        root,
        "ls-files",
        "--others",
        "--exclude-standard",
        "--",
        ".",
        ":(exclude).bianchini",
        ":(exclude).planning",
    ).splitlines()
    digest = hashlib.sha256(f"{head}\n{diff}".encode())
    for relative in sorted(untracked):
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError as error:
            raise WorkflowError("STALE_EVIDENCE", "arquivo não rastreado escapou do repo") from error
        if path.is_file() and not path.is_symlink():
            digest.update(relative.encode())
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _reference_exists(root: Path, reference: str) -> bool:
    if not re.fullmatch(r"C\d{3}(?:-[a-z0-9-]+)?/P\d{2}", reference):
        return False
    change, plan = reference.split("/", 1)
    candidates = [root / ".bianchini/changes", root / ".bianchini/archive"]
    for base in candidates:
        if not base.is_dir():
            continue
        for directory in base.glob(f"{change}*"):
            if plan_file_for_id(directory / "plans", plan) is not None:
                return True
    return False


def debug_start(
    repo: Path,
    objective: str,
    expected: str,
    actual: str,
    environment: str,
    origin_refs: list[str],
    relation: str | None,
    origin_evidence: str | None,
) -> dict[str, Any]:
    root = _repo_root(repo)
    state = read_state(root)
    if state.get("active_work"):
        raise WorkflowError("COHERENCE_ERROR", "já existe trabalho ativo")
    invalid_refs = [ref for ref in origin_refs if not _reference_exists(root, ref)]
    if invalid_refs:
        raise WorkflowError("MODEL_MISMATCH", "referências inexistentes: " + ", ".join(invalid_refs))
    if origin_refs and relation not in {"caused_by", "detected_in", "regression_of"}:
        raise WorkflowError("MODEL_MISMATCH", "relação causal válida é obrigatória")
    if origin_refs and not (origin_evidence or "").strip():
        raise WorkflowError(
            "STALE_EVIDENCE", "relação com mudança anterior exige --origin-evidence"
        )
    base_id = MethodWorkspace(root).allocate_id("debug")
    debug_id = f"{base_id}-{_slug(objective)}"
    value = {
        "schema_version": 1,
        "docviva_contract": 1,
        "docviva_before": bm_docviva.snapshot_docviva(root),
        "id": debug_id,
        "status": "active",
        "stage": "intake",
        "objective": objective,
        "expected": expected,
        "actual": actual,
        "environment": environment,
        "origin_refs": origin_refs,
        "relation": relation,
        "origin_evidence": origin_evidence.strip() if origin_evidence else None,
        "hypotheses": [],
        "experiments": [],
        "eliminated_hypotheses": [],
        "root_cause": None,
        "red": None,
        "green": None,
        "neighboring_regressions": [],
        "residual_risk": None,
        "events": [],
        "created_at": _now(),
        "updated_at": _now(),
    }
    _atomic_write(
        _debug_path(root, debug_id),
        _frontmatter(value, f"# Debug {debug_id}\n\n{objective}"),
    )
    update_state(
        root,
        active_work={"kind": "debug", "id": debug_id, "status": "active"},
        current_unit="intake",
        status="active",
        next_action=f"Reproduzir {debug_id} de forma determinística.",
    )
    return {"id": debug_id, "status": "active", "stage": "intake"}


def debug_checkpoint(
    repo: Path,
    debug_id: str,
    event: str,
    evidence: str,
    *,
    hypotheses: Iterable[str] = (),
    experiments: Iterable[str] = (),
    eliminated_hypotheses: Iterable[str] = (),
    root_cause: str | None = None,
    neighboring_regressions: Iterable[str] = (),
    residual_risk: str | None = None,
) -> dict[str, Any]:
    root = _repo_root(repo)
    path = _debug_path(root, debug_id)
    value = _read_frontmatter(path, "debug ativo")
    expected = DEBUG_TRANSITIONS.get(str(value.get("stage")))
    if event != expected:
        raise WorkflowError(
            "ORDER_VIOLATION", f"após {value.get('stage')} o próximo evento é {expected}"
        )
    if not evidence.strip():
        raise WorkflowError("STALE_EVIDENCE", "checkpoint exige evidência")
    fingerprint = _tree_fingerprint(root)
    normalized_hypotheses = [item.strip() for item in hypotheses if item.strip()]
    normalized_experiments = [item.strip() for item in experiments if item.strip()]
    normalized_eliminated = [
        item.strip() for item in eliminated_hypotheses if item.strip()
    ]
    normalized_regressions = [
        item.strip() for item in neighboring_regressions if item.strip()
    ]
    if event == "diagnosed" and not (root_cause or "").strip():
        raise WorkflowError("STALE_EVIDENCE", "diagnóstico exige --root-cause")
    events = value.get("events", [])
    if not isinstance(events, list):
        raise WorkflowError("DOCVIVA_INCOMPLETE", "eventos do debug são inválidos")
    by_event = {
        item.get("event"): item
        for item in events
        if isinstance(item, dict) and isinstance(item.get("event"), str)
    }
    if event == "green":
        red_event = by_event.get("red")
        if not red_event or red_event.get("fingerprint") == fingerprint:
            raise WorkflowError(
                "STALE_EVIDENCE", "GREEN exige patch posterior à evidência RED"
            )
    if event == "regression_checked":
        green_event = by_event.get("green")
        if not green_event or green_event.get("fingerprint") != fingerprint:
            raise WorkflowError(
                "STALE_EVIDENCE", "patch posterior ao GREEN exige repetir o GREEN"
            )
        if not normalized_regressions:
            raise WorkflowError(
                "STALE_EVIDENCE", "regressão exige --neighbor-regression"
            )
    if event == "documented":
        regression_event = by_event.get("regression_checked")
        if not regression_event or regression_event.get("fingerprint") != fingerprint:
            raise WorkflowError(
                "STALE_EVIDENCE", "patch posterior à regressão exige repetir os gates"
            )
        if not (residual_risk or "").strip():
            raise WorkflowError("STALE_EVIDENCE", "documentação exige --residual-risk")
    value.setdefault("hypotheses", []).extend(normalized_hypotheses)
    value.setdefault("experiments", []).extend(normalized_experiments)
    value.setdefault("eliminated_hypotheses", []).extend(normalized_eliminated)
    if root_cause is not None:
        value["root_cause"] = root_cause.strip()
    if event == "red":
        value["red"] = evidence.strip()
    if event == "green":
        value["green"] = evidence.strip()
    if normalized_regressions:
        value.setdefault("neighboring_regressions", []).extend(normalized_regressions)
    if residual_risk is not None:
        value["residual_risk"] = residual_risk.strip()
    value["stage"] = event
    value["updated_at"] = _now()
    value.setdefault("events", []).append(
        {
            "event": event,
            "evidence": evidence.strip(),
            "fingerprint": fingerprint,
            "at": _now(),
        }
    )
    _atomic_write(path, _frontmatter(value, f"# Debug {debug_id}\n\n{value['objective']}"))
    update_state(
        root,
        current_unit=event,
        next_action=(
            f"Finalizar {debug_id}."
            if event == "documented"
            else f"Registrar {DEBUG_TRANSITIONS[event]} em {debug_id}."
        ),
    )
    return {"id": debug_id, "status": "active", "stage": event}


def debug_status(repo: Path, debug_id: str | None = None) -> dict[str, Any]:
    root = _repo_root(repo)
    read_state(root)
    if debug_id:
        for resolved in (False, True):
            path = _debug_path(root, debug_id, resolved)
            if path.is_file():
                value = _read_frontmatter(path, "debug")
                return {
                    "id": debug_id,
                    "status": value["status"],
                    "stage": value["stage"],
                    "path": str(path),
                }
        raise WorkflowError("MODEL_MISMATCH", f"debug não encontrado: {debug_id}")
    items: list[dict[str, Any]] = []
    for resolved, directory in (
        (False, root / ".bianchini/debug/active"),
        (True, root / ".bianchini/debug/resolved"),
    ):
        for path in sorted(directory.glob("D*.md")):
            value = _read_frontmatter(path, "debug")
            items.append(
                {
                    "id": value["id"],
                    "status": value["status"],
                    "stage": value["stage"],
                    "resolved": resolved,
                }
            )
    return {"items": items}


def debug_finish(
    repo: Path,
    debug_id: str,
    status: str = "resolved",
    reason: str | None = None,
    docviva_kind: str | None = None,
    docviva_outcome: str | None = None,
    docviva_artifacts: Iterable[str] = (),
    docviva_justification: str | None = None,
    learning_candidate: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = _repo_root(repo)
    if status not in TERMINAL_DEBUG:
        raise WorkflowError("MODEL_MISMATCH", "status terminal inválido")
    source = _debug_path(root, debug_id)
    value = _read_frontmatter(source, "debug ativo")
    if status == "resolved" and value.get("stage") != "documented":
        raise WorkflowError("ORDER_VIOLATION", "debug resolvido exige RED, GREEN, regressão e documentação")
    docviva: dict[str, Any] | None = None
    if status == "resolved":
        events = value.get("events", [])
        last = events[-1] if isinstance(events, list) and events else None
        if not isinstance(last, dict) or last.get("fingerprint") != _tree_fingerprint(root):
            raise WorkflowError(
                "STALE_EVIDENCE", "alteração posterior à documentação exige repetir os gates"
            )
        required = ("root_cause", "red", "green", "neighboring_regressions", "residual_risk")
        missing = [name for name in required if not value.get(name)]
        if missing:
            raise WorkflowError(
                "DOCVIVA_INCOMPLETE", "debug não documenta: " + ", ".join(missing)
            )
        if value.get("docviva_contract") == 1:
            if not docviva_kind or not docviva_outcome:
                raise WorkflowError(
                    "DOCVIVA_INCOMPLETE",
                    "debug resolvido exige classificação DocViva explícita",
                )
            try:
                docviva = bm_docviva.verify_docviva_impact(
                    root,
                    value.get("docviva_before", {}),
                    {"kind": docviva_kind, "outcome": docviva_outcome},
                    docviva_artifacts,
                    docviva_justification or "",
                    required=docviva_kind in bm_docviva.REQUIRED_KINDS,
                )
            except bm_docviva.DocVivaError as error:
                raise WorkflowError(error.code, str(error).split(": ", 1)[-1]) from error
    if status != "resolved" and not (reason or "").strip():
        raise WorkflowError("MODEL_MISMATCH", "debug bloqueado ou escalado exige motivo")
    if learning_candidate is not None:
        if status != "resolved":
            raise WorkflowError(
                "LEARNING_CANDIDATE_INVALID",
                "somente debug resolvido pode nomear aprendizado",
            )
        expected_fields = {"classification", "statement", "tags", "validity", "conflicts"}
        if set(learning_candidate) != expected_fields:
            raise WorkflowError(
                "LEARNING_CANDIDATE_INVALID", "nomeação de aprendizado incompleta"
            )
        value["learning_candidate"] = learning_candidate
    value["status"] = status
    value["reason"] = reason
    value["docviva"] = docviva
    value["finished_at"] = _now()
    target = _debug_path(root, debug_id, resolved=True)
    _atomic_write(source, _frontmatter(value, f"# Debug {debug_id}\n\n{value['objective']}"))
    os.replace(source, target)
    update_state(
        root,
        active_work=None,
        current_unit=None,
        status="idle" if status != "blocked" else "blocked",
        last_completed={"kind": "debug", "id": debug_id, "status": status},
        next_action="Revisar o resultado do debug e seguir o trabalho registrado.",
    )
    return {
        "id": debug_id,
        "status": status,
        "stage": value["stage"],
        "path": str(target),
        "docviva": docviva,
    }


def _legacy_idle(root: Path) -> bool:
    state = root / "docs/living/PROJECT_STATE.md"
    if not state.is_file():
        return True
    text = state.read_text(encoding="utf-8")
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        lowered = text.lower()
        return any(marker in lowered for marker in ("status: idle", "status: completed"))
    statuses = {
        str(value.get("status", "")).lower(),
        str(value.get("planning_status", "")).lower(),
    }
    return bool(statuses & {"idle", "completed", "done", "concluido"})


def _walk_known_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    files: list[Path] = []
    for current, directories, names in os.walk(directory, followlinks=False):
        current_path = Path(current)
        for name in [*directories, *names]:
            entry = current_path / name
            if entry.is_symlink():
                raise WorkflowError("MIGRATION_REQUIRED", f"symlink não permitido: {entry}")
        files.extend(current_path / name for name in names)
    return sorted(files, key=lambda path: path.as_posix())


def _recognized_design_files(directory: Path) -> list[Path]:
    """Seleciona somente pacotes com manifesto Bianchini reconhecível."""

    if not directory.is_dir():
        return []
    files: list[Path] = []
    for candidate in sorted(directory.iterdir()):
        if candidate.is_symlink():
            raise WorkflowError("MIGRATION_REQUIRED", f"symlink não permitido: {candidate}")
        if not candidate.is_dir():
            continue
        manifest = candidate / "DESIGN_MANIFEST.json"
        if not manifest.is_file() or manifest.is_symlink():
            continue
        try:
            value = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            continue
        # Match the public Go contract regardless of filesystem enumeration.
        files.extend(path for path in _walk_known_files(candidate) if path != manifest)
        files.append(manifest)
    return files


def migration_check(repo: Path) -> dict[str, Any]:
    root = _repo_root(repo)
    if _workspace(root).exists():
        raise WorkflowError("MIGRATION_REQUIRED", ".bianchini já existe")
    if _git(root, "status", "--porcelain"):
        raise WorkflowError("DIRTY_WORKSPACE", "migração exige Git limpo")
    if not _legacy_idle(root):
        raise WorkflowError("MIGRATION_REQUIRED", "o trabalho anterior precisa estar idle ou concluído")
    day = datetime.now(timezone.utc).date().isoformat()
    archive_base = Path(f".bianchini/archive/import-{day}")
    entries: list[dict[str, str]] = []
    seen: set[Path] = set()

    def add(source: Path, target: Path) -> None:
        if source in seen or not source.is_file():
            return
        seen.add(source)
        entries.append(
            {
                "source": source.relative_to(root).as_posix(),
                "target": target.as_posix(),
                "sha256": _digest_bytes(source.read_bytes()),
            }
        )

    legacy_state = root / "docs/living/PROJECT_STATE.md"
    add(legacy_state, archive_base / "legacy/PROJECT_STATE.md")
    specs = root / "docs/bianchini/current/specs"
    for source in _walk_known_files(specs):
        add(source, Path(".bianchini/current/specs") / source.relative_to(specs))
    bianchini_docs = root / "docs/bianchini"
    for source in _walk_known_files(bianchini_docs):
        add(source, archive_base / "docs-bianchini" / source.relative_to(bianchini_docs))
    artifacts = root / "artifacts/bianchini"
    for source in _walk_known_files(artifacts):
        add(source, archive_base / "artifacts-bianchini" / source.relative_to(artifacts))
    designs = root / "docs/design"
    for source in _recognized_design_files(designs):
        add(source, archive_base / "docs-design" / source.relative_to(designs))
    direct = root / ".superpowers/bianchini/direct"
    for source in _walk_known_files(direct):
        add(source, Path(".bianchini/quick/imported") / source.relative_to(direct))

    if not entries:
        raise WorkflowError("MIGRATION_REQUIRED", "nenhum artefato Bianchini anterior encontrado")
    targets = [entry["target"] for entry in entries]
    if len(targets) != len(set(targets)):
        raise WorkflowError("MIGRATION_REQUIRED", "colisão no mapa de migração")
    for target in targets:
        if (root / target).exists():
            raise WorkflowError("MIGRATION_REQUIRED", f"destino já existe: {target}")
    return {"eligible": True, "entries": entries, "archive": archive_base.as_posix()}


def _remove_empty_legacy_directories(root: Path) -> None:
    for relative in (
        "docs/living",
        "docs/bianchini",
        "artifacts/bianchini",
        "docs/design",
        ".superpowers/bianchini/direct",
    ):
        directory = root / relative
        if not directory.exists():
            continue
        for current, directories, files in os.walk(directory, topdown=False):
            path = Path(current)
            if not directories and not files:
                path.rmdir()
            elif path.exists() and not any(path.iterdir()):
                path.rmdir()


def migration_apply(repo: Path) -> dict[str, Any]:
    root = _repo_root(repo)
    report = migration_check(root)
    entries = list(report["entries"])
    copied: list[tuple[Path, Path]] = []
    removed_sources: list[tuple[Path, Path]] = []
    try:
        for entry in entries:
            source = root / entry["source"]
            target = root / entry["target"]
            if _digest_bytes(source.read_bytes()) != entry["sha256"]:
                raise WorkflowError("MIGRATION_REQUIRED", f"checksum divergente: {entry['source']}")
            target.parent.mkdir(parents=True, exist_ok=True)
            part = target.with_name(target.name + ".part")
            if part.exists():
                raise WorkflowError("MIGRATION_REQUIRED", f"staging já existe: {part}")
            shutil.copy2(source, part, follow_symlinks=False)
            if _digest_bytes(part.read_bytes()) != entry["sha256"]:
                part.unlink(missing_ok=True)
                raise WorkflowError(
                    "MIGRATION_REQUIRED", f"checksum do destino divergiu: {entry['target']}"
                )
            os.replace(part, target)
            copied.append((source, target))
        for source, target in copied:
            if _digest_bytes(target.read_bytes()) != _digest_bytes(source.read_bytes()):
                raise WorkflowError(
                    "MIGRATION_REQUIRED", f"verificação final divergiu: {target}"
                )
        for source, target in copied:
            source.unlink()
            removed_sources.append((source, target))
        _remove_empty_legacy_directories(root)
        init_workspace(root, allow_existing=True)
        manifest = root / report["archive"] / "MANIFEST.md"
        manifest_value = {
            "schema_version": 1,
            "method": METHOD_VERSION,
            "imported_at": _now(),
            "entries": entries,
        }
        _atomic_write(
            manifest,
            _frontmatter(manifest_value, "# Manifesto de migração\n\nArquivos anteriores preservados por checksum."),
        )
        update_state(
            root,
            last_completed={"kind": "migration", "id": report["archive"], "status": "completed"},
            next_action="Revisar o modelo atual e iniciar o próximo trabalho.",
        )
    except Exception:
        for source, target in reversed(removed_sources):
            if target.exists() and not source.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, source, follow_symlinks=False)
        workspace = _workspace(root)
        if workspace.exists():
            shutil.rmtree(workspace)
        raise
    return {
        "status": "migrated",
        "entries": entries,
        "manifest": str(root / report["archive"] / "MANIFEST.md"),
        "state": str(_state_path(root)),
    }
