#!/usr/bin/env python3
"""Guarda determinística da convergência do overlay executar-plano-codex."""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
MAX_FIX_ROUNDS = 2
MAX_REDESIGNS_PER_SEAM = 1
IDENTIFIER = re.compile(r"^[A-Za-z0-9._-]+$")
SEVERITIES = {"critical", "important", "minor", "note"}
BLOCKING_SEVERITIES = {"critical", "important"}
STOP_KINDS = {
    "essential_external_credential",
    "destructive_action",
    "new_cost",
    "real_impossibility",
}
CONTINUE_KINDS = {"internal", "local_block"}
PROOF_FIELDS = (
    "approved_requirement",
    "reproduction",
    "material_impact",
    "reachable_scenario",
)


class GuardError(ValueError):
    """Erro de contrato exibível sem traceback."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def identifier(value: str, label: str) -> str:
    if not IDENTIFIER.fullmatch(value):
        raise GuardError(f"{label} inválido: use letras, números, ponto, sublinhado ou hífen")
    return value


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def revision(value: str, label: str) -> str:
    if not nonempty(value) or len(value) > 200 or "\n" in value or "\r" in value:
        raise GuardError(f"{label} inválido")
    return value.strip()


def canonical_sidecar(root: Path, planning_version: str, plan: str, unit: str) -> Path:
    repository = root.resolve()
    planning_version = identifier(planning_version, "planning_version")
    plan = identifier(plan, "plan")
    unit = identifier(unit, "unit")
    candidate = (
        repository
        / "artifacts"
        / "bianchini"
        / planning_version
        / "codex"
        / "convergence"
        / plan
        / f"{unit}.json"
    ).resolve()
    if not candidate.is_relative_to(repository):
        raise GuardError("caminho canônico do sidecar escapa do repositório")
    return candidate


def load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise GuardError(f"{label} não encontrado: {path}") from error
    except json.JSONDecodeError as error:
        raise GuardError(f"{label} inválido: {error.msg}") from error
    except (OSError, UnicodeError) as error:
        raise GuardError(f"{label} ilegível: {path}") from error


def write_atomic(path: Path, value: dict[str, Any], *, rotate_backup: bool = True) -> None:
    rendered = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if "ask_user" in rendered:
        raise GuardError("estado proibido")
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_suffix(path.suffix + ".bak")
    if rotate_backup and path.exists():
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass
        else:
            shutil.copy2(path, backup)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(rendered)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if temporary.exists():
            temporary.unlink()


def validate_state(state: Any) -> dict[str, Any]:
    if not isinstance(state, dict) or state.get("schema_version") != SCHEMA_VERSION:
        raise GuardError("sidecar incompatível")
    if "ask_user" in json.dumps(state, ensure_ascii=False, sort_keys=True):
        raise GuardError("sidecar contém estado proibido")
    for field in (
        "unit_id",
        "plan_id",
        "planning_version",
        "repository_root",
        "seam",
        "status",
        "review_frozen",
        "last_review_head",
        "blockers",
        "deferred_hardening",
        "fix_rounds",
        "redesigns_by_seam",
        "decisions",
        "events",
    ):
        if field not in state:
            raise GuardError(f"sidecar incompleto: {field}")
    identifier(str(state["unit_id"]), "unit_id")
    identifier(str(state["plan_id"]), "plan_id")
    identifier(str(state["planning_version"]), "planning_version")
    identifier(str(state["seam"]), "seam")
    revision(str(state["last_review_head"]), "last_review_head")
    if not isinstance(state["repository_root"], str):
        raise GuardError("repository_root inválido no sidecar")
    if state["status"] not in {"active", "stopped", "completed"}:
        raise GuardError("status de sidecar inválido")
    if state["review_frozen"] is not True:
        raise GuardError("sidecar sem primeira revisão congelada")
    if not isinstance(state["blockers"], dict):
        raise GuardError("blockers inválidos no sidecar")
    for blocker_id, blocker in state["blockers"].items():
        identifier(str(blocker_id), "blocker.id")
        if not isinstance(blocker, dict) or blocker.get("status") not in {"open", "resolved"}:
            raise GuardError(f"blocker {blocker_id}: estado inválido")
        if blocker.get("severity") not in BLOCKING_SEVERITIES or blocker.get("disposition") != "blocker":
            raise GuardError(f"blocker {blocker_id}: classificação inválida")
        if not nonempty(blocker.get("title")) or any(
            not nonempty(blocker.get(field)) for field in PROOF_FIELDS
        ):
            raise GuardError(f"blocker {blocker_id}: provas inválidas")
    if not isinstance(state["deferred_hardening"], list):
        raise GuardError("deferred_hardening inválido no sidecar")
    for item in state["deferred_hardening"]:
        if (
            not isinstance(item, dict)
            or item.get("severity") not in {"minor", "note"}
            or item.get("disposition") != "hardening"
            or not nonempty(item.get("title"))
        ):
            raise GuardError("finding de hardening inválido no sidecar")
    if (
        not isinstance(state["fix_rounds"], int)
        or isinstance(state["fix_rounds"], bool)
        or not 0 <= state["fix_rounds"] <= MAX_FIX_ROUNDS
    ):
        raise GuardError("fix_rounds inválido no sidecar")
    if not isinstance(state["redesigns_by_seam"], dict):
        raise GuardError("redesigns_by_seam inválido no sidecar")
    for seam, count in state["redesigns_by_seam"].items():
        identifier(str(seam), "redesign.seam")
        if (
            not isinstance(count, int)
            or isinstance(count, bool)
            or not 0 <= count <= MAX_REDESIGNS_PER_SEAM
        ):
            raise GuardError(f"seam {seam}: contador de redesign inválido")
    if not isinstance(state["decisions"], list) or not all(
        isinstance(item, dict) for item in state["decisions"]
    ):
        raise GuardError("decisions inválido no sidecar")
    if not isinstance(state["events"], list) or not all(
        isinstance(item, dict) and nonempty(item.get("action"))
        for item in state["events"]
    ):
        raise GuardError("histórico inválido no sidecar")
    return state


def validate_location(path: Path, state: dict[str, Any]) -> None:
    expected = canonical_sidecar(
        Path(state["repository_root"]),
        state["planning_version"],
        state["plan_id"],
        state["unit_id"],
    )
    if path.resolve() != expected:
        raise GuardError(f"sidecar fora do caminho canônico: {expected}")


def load_sidecar(path: Path) -> tuple[dict[str, Any], bool]:
    try:
        state = validate_state(load_json(path, "sidecar"))
        validate_location(path, state)
        return state, False
    except GuardError as primary_error:
        backup = path.with_suffix(path.suffix + ".bak")
        if not backup.exists():
            raise primary_error
        try:
            recovered = validate_state(load_json(backup, "backup do sidecar"))
            validate_location(path, recovered)
        except GuardError:
            raise primary_error
        write_atomic(path, recovered, rotate_backup=False)
        return recovered, True


def ensure_active(state: dict[str, Any]) -> None:
    if state["status"] == "completed":
        raise GuardError("unidade concluída é terminal e não pode reabrir")
    if state["status"] == "stopped":
        raise GuardError("unidade parada por condição terminal registrada")


def event(state: dict[str, Any], action: str, **details: Any) -> None:
    state["events"].append({"at": now(), "action": action, **details})
    state["updated_at"] = now()


def findings_from(path: Path) -> list[dict[str, Any]]:
    value = load_json(path, "findings")
    findings = value.get("findings") if isinstance(value, dict) else value
    if not isinstance(findings, list):
        raise GuardError("findings deve ser lista ou objeto com lista findings")
    if not all(isinstance(item, dict) for item in findings):
        raise GuardError("cada finding deve ser objeto")
    return findings


def normalize_finding(raw: dict[str, Any], *, require_source: bool = False) -> dict[str, Any]:
    finding = copy.deepcopy(raw)
    finding_id = identifier(str(finding.get("id", "")), "finding.id")
    severity = str(finding.get("severity", ""))
    if severity not in SEVERITIES:
        raise GuardError(f"finding {finding_id}: severity inválida")
    if not nonempty(finding.get("title")):
        raise GuardError(f"finding {finding_id}: title obrigatório")
    disposition = str(finding.get("disposition", ""))
    if severity in BLOCKING_SEVERITIES:
        if disposition != "blocker":
            raise GuardError(f"finding {finding_id}: critical/important exige disposition blocker")
        missing = [field for field in PROOF_FIELDS if not nonempty(finding.get(field))]
        if missing:
            raise GuardError(f"finding {finding_id}: blocker sem {', '.join(missing)}")
    elif disposition != "hardening":
        raise GuardError(f"finding {finding_id}: minor/note exige disposition hardening")
    if require_source and finding.get("source") not in {"frozen", "delta_regression"}:
        raise GuardError(
            f"finding {finding_id}: revisão seguinte aceita frozen ou delta_regression"
        )
    finding["id"] = finding_id
    finding["severity"] = severity
    finding["disposition"] = disposition
    return finding


def command_freeze(args: argparse.Namespace) -> dict[str, Any]:
    repository = Path(args.root).resolve()
    path = canonical_sidecar(repository, args.planning_version, args.plan, args.unit)
    if path.exists():
        raise GuardError("primeira revisão já congelada para esta unidade")
    unit = identifier(args.unit, "unit")
    plan = identifier(args.plan, "plan")
    planning_version = identifier(args.planning_version, "planning_version")
    seam = identifier(args.seam, "seam")
    review_head = revision(args.review_head, "review_head")
    blockers: dict[str, Any] = {}
    hardening: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in findings_from(Path(args.findings)):
        finding = normalize_finding(raw)
        if finding["id"] in seen:
            raise GuardError(f"finding duplicado: {finding['id']}")
        seen.add(finding["id"])
        if finding["disposition"] == "blocker":
            blockers[finding["id"]] = {**finding, "source": "initial", "status": "open"}
        else:
            hardening.append({**finding, "deferred_at": now()})
    state: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "unit_id": unit,
        "plan_id": plan,
        "planning_version": planning_version,
        "repository_root": str(repository),
        "seam": seam,
        "status": "active",
        "review_frozen": True,
        "last_review_head": review_head,
        "blockers": blockers,
        "deferred_hardening": hardening,
        "fix_rounds": 0,
        "redesigns_by_seam": {},
        "decisions": [],
        "events": [],
        "created_at": now(),
        "updated_at": now(),
    }
    event(state, "review_frozen", blockers=sorted(blockers), hardening=len(hardening))
    write_atomic(path, state)
    return {"action": "continue", "sidecar": str(path), "state": state}


def command_review(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.sidecar).resolve()
    state, recovered = load_sidecar(path)
    ensure_active(state)
    delta_base = revision(args.delta_base, "delta_base")
    delta_head = revision(args.delta_head, "delta_head")
    if delta_base != state["last_review_head"]:
        raise GuardError(
            f"delta_base não coincide com última revisão: {state['last_review_head']}"
        )
    if delta_head == delta_base:
        raise GuardError("delta_head deve representar novo delta")
    accepted: list[str] = []
    for raw in findings_from(Path(args.findings)):
        finding = normalize_finding(raw, require_source=True)
        finding_id = finding["id"]
        if finding["source"] == "frozen":
            if finding_id not in state["blockers"]:
                raise GuardError(f"finding {finding_id}: não pertence aos blockers congelados")
            frozen = state["blockers"][finding_id]
            if frozen.get("status") != "open":
                raise GuardError(f"finding {finding_id}: blocker resolvido não pode reabrir")
            immutable = ("severity", "disposition", "title", *PROOF_FIELDS)
            if any(finding.get(field) != frozen.get(field) for field in immutable):
                raise GuardError(f"finding {finding_id}: blocker congelado foi alterado")
            accepted.append(finding_id)
            continue
        finding["delta_base"] = delta_base
        finding["delta_head"] = delta_head
        if finding["disposition"] == "hardening":
            state["deferred_hardening"].append({**finding, "deferred_at": now()})
        elif finding_id in state["blockers"] or any(
            item.get("id") == finding_id for item in state["deferred_hardening"]
        ):
            raise GuardError(f"finding {finding_id}: id já existe no sidecar")
        else:
            state["blockers"][finding_id] = {**finding, "status": "open"}
        accepted.append(finding_id)
    state["last_review_head"] = delta_head
    event(
        state,
        "delta_reviewed",
        findings=accepted,
        delta_base=delta_base,
        delta_head=delta_head,
    )
    write_atomic(path, state)
    return {"action": "continue", "recovered": recovered, "state": state}


def command_fix(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.sidecar).resolve()
    state, recovered = load_sidecar(path)
    ensure_active(state)
    blockers = list(dict.fromkeys(args.blocker))
    if any(
        not state["blockers"].get(blocker)
        or state["blockers"][blocker].get("status") != "open"
        for blocker in blockers
    ):
        raise GuardError("fix round exige blockers abertos")
    if state["fix_rounds"] >= MAX_FIX_ROUNDS:
        seam = state["seam"]
        if state["redesigns_by_seam"].get(seam, 0) < MAX_REDESIGNS_PER_SEAM:
            return {
                "action": "redesign_required",
                "recovered": recovered,
                "state": state,
            }
        if not any(
            item.get("action") == "convergence_exhausted"
            for item in state["events"]
        ):
            event(state, "convergence_exhausted", blockers=blockers)
            write_atomic(path, state)
        return {
            "action": "continue_independent",
            "recovered": recovered,
            "state": state,
        }
    state["fix_rounds"] += 1
    event(
        state,
        "fix_round_started",
        round=state["fix_rounds"],
        blockers=blockers,
        summary=args.summary,
    )
    write_atomic(path, state)
    return {"action": "continue", "recovered": recovered, "state": state}


def command_resolve(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.sidecar).resolve()
    state, recovered = load_sidecar(path)
    ensure_active(state)
    blocker = state["blockers"].get(args.blocker)
    if not blocker or blocker.get("status") != "open":
        raise GuardError("resolve exige blocker aberto")
    if not nonempty(args.evidence):
        raise GuardError("resolve exige evidência textual reproduzível")
    blocker["status"] = "resolved"
    blocker["resolution_evidence"] = args.evidence
    blocker["resolved_at"] = now()
    event(state, "blocker_resolved", blocker=args.blocker)
    write_atomic(path, state)
    return {"action": "continue", "recovered": recovered, "state": state}


def command_redesign(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.sidecar).resolve()
    state, recovered = load_sidecar(path)
    ensure_active(state)
    seam = identifier(args.seam, "seam")
    count = int(state["redesigns_by_seam"].get(seam, 0))
    if count >= MAX_REDESIGNS_PER_SEAM:
        raise GuardError(f"seam {seam}: limite de um redesign atingido")
    state["redesigns_by_seam"][seam] = count + 1
    event(state, "redesign_started", seam=seam, summary=args.summary)
    write_atomic(path, state)
    return {"action": "continue", "recovered": recovered, "state": state}


def command_decision(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.sidecar).resolve()
    state, recovered = load_sidecar(path)
    ensure_active(state)
    kind = args.kind
    if kind not in STOP_KINDS | CONTINUE_KINDS:
        raise GuardError("categoria não permite parada nem decisão automática")
    if kind == "internal":
        action = "automatic_continue"
    elif kind == "local_block":
        action = "continue_independent"
    else:
        action = "stop"
        state["status"] = "stopped"
        state["stop"] = {"kind": kind, "summary": args.summary, "at": now()}
    state["decisions"].append(
        {"kind": kind, "summary": args.summary, "action": action, "at": now()}
    )
    event(state, "decision", kind=kind, result=action)
    write_atomic(path, state)
    return {"action": action, "recovered": recovered, "state": state}


def command_complete(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.sidecar).resolve()
    state, recovered = load_sidecar(path)
    ensure_active(state)
    open_blockers = sorted(
        key
        for key, value in state["blockers"].items()
        if value.get("status") == "open"
    )
    if open_blockers:
        raise GuardError(f"blockers abertos impedem conclusão: {', '.join(open_blockers)}")
    state["status"] = "completed"
    state["completed_at"] = now()
    event(state, "completed", deferred_hardening=len(state["deferred_hardening"]))
    write_atomic(path, state)
    return {"action": "completed", "recovered": recovered, "state": state}


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    state, recovered = load_sidecar(Path(args.sidecar).resolve())
    return {"action": "status", "recovered": recovered, "state": state}


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    subparsers = value.add_subparsers(dest="command", required=True)

    freeze = subparsers.add_parser("freeze")
    freeze.add_argument("--root", required=True)
    freeze.add_argument("--planning-version", required=True)
    freeze.add_argument("--plan", required=True)
    freeze.add_argument("--unit", required=True)
    freeze.add_argument("--seam", required=True)
    freeze.add_argument("--review-head", required=True)
    freeze.add_argument("--findings", required=True)
    freeze.set_defaults(handler=command_freeze)

    review = subparsers.add_parser("review")
    review.add_argument("--sidecar", required=True)
    review.add_argument("--findings", required=True)
    review.add_argument("--delta-base", required=True)
    review.add_argument("--delta-head", required=True)
    review.set_defaults(handler=command_review)

    for name, handler in (("fix", command_fix), ("resolve", command_resolve)):
        child = subparsers.add_parser(name)
        child.add_argument("--sidecar", required=True)
        child.add_argument(
            "--blocker",
            required=True,
            action="append" if name == "fix" else "store",
        )
        child.add_argument("--summary" if name == "fix" else "--evidence", required=True)
        child.set_defaults(handler=handler)

    redesign = subparsers.add_parser("redesign")
    redesign.add_argument("--sidecar", required=True)
    redesign.add_argument("--seam", required=True)
    redesign.add_argument("--summary", required=True)
    redesign.set_defaults(handler=command_redesign)

    decision = subparsers.add_parser("decision")
    decision.add_argument("--sidecar", required=True)
    decision.add_argument("--kind", required=True)
    decision.add_argument("--summary", required=True)
    decision.set_defaults(handler=command_decision)

    for name, handler in (("complete", command_complete), ("status", command_status)):
        child = subparsers.add_parser(name)
        child.add_argument("--sidecar", required=True)
        child.set_defaults(handler=handler)
    return value


def main() -> int:
    try:
        args = parser().parse_args()
        result = args.handler(args)
        rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
        if "ask_user" in rendered:
            raise GuardError("resultado proibido")
        print(rendered)
        return 0
    except GuardError as error:
        print(f"erro: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
