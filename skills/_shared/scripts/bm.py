#!/usr/bin/env python3
"""Primitivas determinísticas do Bianchini Method v2. Somente stdlib."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXIT_INVALID = 2
EXIT_BLOCKED = 3
EXIT_UNSAFE_WORKSPACE = 4


class BMError(Exception):
    def __init__(self, message: str, exit_code: int = EXIT_INVALID):
        super().__init__(message)
        self.exit_code = exit_code


def emit(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def run_git(args: list[str], cwd: Path) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=False
    )
    if completed.returncode != 0:
        raise BMError(completed.stderr.strip() or "comando Git falhou")
    return completed.stdout.strip()


def state_text(path: Path) -> str:
    if not path.is_file():
        raise BMError(f"estado não encontrado: {path}")
    return path.read_text(encoding="utf-8")


def load_state(path: Path) -> dict[str, Any]:
    text = state_text(path)
    fenced = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text.strip()
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        legacy = re.search(r"(?m)^\s*method_version:\s*(\d+)\s*$", text)
        if legacy:
            return {"method_version": int(legacy.group(1)), "_legacy_text": text}
        return {"method_version": 1, "_implicit_legacy": True, "_legacy_text": text}
    if not isinstance(value, dict):
        raise BMError("PROJECT_STATE deve ser um objeto")
    if "method_version" not in value:
        return {**value, "method_version": 1, "_implicit_legacy": True}
    return value


def local_ref(schema: dict[str, Any], ref: str) -> dict[str, Any]:
    if not ref.startswith("#/"):
        raise BMError(f"$ref externo não suportado: {ref}")
    node: Any = schema
    for part in ref[2:].split("/"):
        node = node[part.replace("~1", "/").replace("~0", "~")]
    return node


def validate_node(value: Any, rule: dict[str, Any], schema: dict[str, Any], at: str) -> list[str]:
    if "$ref" in rule:
        return validate_node(value, local_ref(schema, rule["$ref"]), schema, at)
    errors: list[str] = []
    if "const" in rule and value != rule["const"]:
        errors.append(f"{at}: esperado {rule['const']!r}")
    if "enum" in rule and value not in rule["enum"]:
        errors.append(f"{at}: valor {value!r} fora de {rule['enum']}")
    expected = rule.get("type")
    allowed = expected if isinstance(expected, list) else [expected] if expected else []
    type_map = {
        "object": dict,
        "array": list,
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "null": type(None),
    }
    if allowed and not any(isinstance(value, type_map[item]) for item in allowed):
        return [f"{at}: tipo inválido; esperado {allowed}"]
    if isinstance(value, dict):
        for key in rule.get("required", []):
            if key not in value:
                errors.append(f"{at}.{key}: campo obrigatório ausente")
        for key, child in value.items():
            child_rule = rule.get("properties", {}).get(key)
            if child_rule:
                errors.extend(validate_node(child, child_rule, schema, f"{at}.{key}"))
    if isinstance(value, list):
        if len(value) < rule.get("minItems", 0):
            errors.append(f"{at}: lista menor que minItems")
        item_rule = rule.get("items")
        if item_rule:
            for index, child in enumerate(value):
                errors.extend(validate_node(child, item_rule, schema, f"{at}[{index}]"))
    if isinstance(value, str) and "pattern" in rule and not re.search(rule["pattern"], value):
        errors.append(f"{at}: não corresponde a {rule['pattern']}")
    return errors


def default_schema() -> Path:
    return Path(__file__).resolve().parents[1] / "schemas" / "project-state.schema.json"


def validate_state(path: Path, schema_path: Path | None = None) -> dict[str, Any]:
    state = load_state(path)
    if state.get("method_version") != 2:
        raise BMError("schema v2 não deve validar projeto legado")
    schema_file = schema_path or default_schema()
    schema = json.loads(schema_file.read_text(encoding="utf-8"))
    errors = validate_node(state, schema, schema, "state")
    if not errors:
        errors.extend(semantic_errors(state))
    if errors:
        raise BMError("estado inválido:\n- " + "\n- ".join(errors))
    return state


def semantic_errors(state: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    approval = state["approval"]
    plans = state["plans"]
    plan_ids = [item["id"] for item in plans]
    planning_status = state["planning_status"]
    if not plans and planning_status not in {"idle", "in_progress"}:
        errors.append(
            "state.plans: ao menos um plano é obrigatório fora de idle/in_progress"
        )
    if planning_status == "idle":
        if state["scope"] != {
            "status": "pending",
            "source": None,
            "approved_at": None,
        }:
            errors.append("state.scope: idle exige escopo pendente e sem fonte aprovada")
        if state["planning"] != {"spec": None, "review": None}:
            errors.append("state.planning: idle não pode apontar spec ou revisão")
        if approval["status"] != "pending":
            errors.append("state.approval.status: idle exige aprovação pending")
        if approval.get("approved_at") is not None or approval.get("approved_by") is not None:
            errors.append("state.approval: idle não pode conter aprovação anterior")
        if approval["approved_plans"]:
            errors.append("state.approval.approved_plans: idle exige lista vazia")
        if approval["package"].get("manifest_digest") is not None:
            errors.append("state.approval.package.manifest_digest: idle exige null")
        if approval["package"]["files"]:
            errors.append("state.approval.package.files: idle exige lista vazia")
        if plans:
            errors.append("state.plans: idle exige lista vazia")
        if state.get("active_execution") is not None:
            errors.append("state.active_execution: idle exige null")
        idle_verification = {
            "fast": {"commands": [], "status": "pending"},
            "plan": {"commands": [], "status": "pending"},
            "release": {"commands": [], "status": "pending"},
        }
        if state["verification"] != idle_verification:
            errors.append("state.verification: idle exige gates pendentes e sem comandos")
        idle_release = {
            "status": "pending",
            "platforms": [],
            "profiles": [],
            "candidate": None,
            "final_gate": "homologar-sistema",
            "homologation": "pending",
            "final_review": "pending",
            "delivery": "pending",
        }
        if state["release"] != idle_release:
            errors.append("state.release: idle exige release reinicializado")
        if state["architecture_audit_status"] != "not_run":
            errors.append("state.architecture_audit_status: idle exige not_run")
        if state["blockers"]:
            errors.append("state.blockers: idle exige lista vazia")
        if state.get("telemetry", {}).get("enabled"):
            errors.append("state.telemetry.enabled: idle exige false")
    else:
        if state["scope"]["status"] != "approved" or not state["scope"]["source"]:
            errors.append("state.scope: ciclo ativo exige escopo aprovado e fonte local")
        if not state["planning"]["spec"] or not state["planning"]["review"]:
            errors.append("state.planning: ciclo ativo exige spec e revisão")
    if len(plan_ids) != len(set(plan_ids)):
        errors.append("state.plans: IDs duplicados")
    active = state.get("active_execution")
    if isinstance(active, dict):
        active_id = active.get("plan_id")
        if active_id not in plan_ids:
            errors.append("state.active_execution.plan_id: plano inexistente")
        else:
            active_plan = next(plan for plan in plans if plan["id"] == active_id)
            if active_plan["status"] != "in_progress":
                errors.append(
                    "state.active_execution.plan_id: plano ativo deve estar in_progress"
                )
    expected_policy = {
        "low": ("grouped", "plan_gate"),
        "medium": ("slice", "per_slice"),
        "high": ("strict", "per_task"),
        "critical": ("strict", "per_task"),
    }
    rank = {"grouped": 0, "slice": 1, "strict": 2}
    review_for = {"grouped": "plan_gate", "slice": "per_slice", "strict": "per_task"}
    for index, plan in enumerate(plans):
        minimum_execution, _ = expected_policy[plan["risk"]]
        if rank[plan["execution"]] < rank[minimum_execution]:
            errors.append(f"state.plans[{index}].execution: garantia abaixo do risco")
        if plan["review"] != review_for[plan["execution"]]:
            errors.append(f"state.plans[{index}].review: incompatível com execution")
        for dependency in plan["depends_on"]:
            if dependency not in plan_ids:
                errors.append(
                    f"state.plans[{index}].depends_on: plano inexistente {dependency!r}"
                )
            if dependency == plan["id"]:
                errors.append(f"state.plans[{index}].depends_on: autodependência")

    graph = {plan["id"]: plan["depends_on"] for plan in plans}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(plan_id: str) -> bool:
        if plan_id in visiting:
            return True
        if plan_id in visited:
            return False
        visiting.add(plan_id)
        cyclic = any(dependency in graph and visit(dependency) for dependency in graph[plan_id])
        visiting.remove(plan_id)
        visited.add(plan_id)
        return cyclic

    if any(visit(plan_id) for plan_id in plan_ids):
        errors.append("state.plans: ciclo de dependências detectado")
    if approval["status"] == "approved":
        digest = approval["package"].get("manifest_digest")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            errors.append("state.approval.package.manifest_digest: digest aprovado inválido")
        if set(approval["approved_plans"]) != set(plan_ids):
            errors.append("state.approval.approved_plans: aprovação deve cobrir todos os planos")
        package_files = set(approval["package"]["files"])
        contract_files = {
            state["scope"]["source"],
            state["planning"]["spec"],
            state["planning"]["review"],
            *(plan["path"] for plan in plans),
        }
        missing_contract_files = sorted(contract_files - package_files)
        if missing_contract_files:
            errors.append(
                "state.approval.package.files: pacote aprovado não contém "
                + ", ".join(missing_contract_files)
            )
        for index, plan in enumerate(plans):
            if plan["status"] == "planned":
                errors.append(
                    f"state.plans[{index}].status: plano aprovado não pode permanecer planned"
                )
        if state["planning_status"] != "approved":
            errors.append("state.planning_status: deve ser approved após aprovação")
    release = state["release"]
    if release["status"] in {"candidate", "homologated", "ready"} and not release.get("candidate"):
        errors.append("state.release.candidate: obrigatório para RC ativo")
    candidate = release.get("candidate")
    if isinstance(candidate, dict):
        required_fingerprint = ("id", "revision", "build", "checksum")
        missing = [key for key in required_fingerprint if not candidate.get(key)]
        if missing:
            errors.append(
                "state.release.candidate: fingerprint incompleto; ausente " + ", ".join(missing)
            )
    if release["status"] in {"homologated", "ready"} and release["homologation"] != "accepted":
        errors.append("state.release.homologation: deve estar accepted")
    if release["status"] == "ready" and (
        release["final_review"] != "approved" or release["delivery"] != "ready"
    ):
        errors.append("state.release: ready exige revisão e entrega aprovadas")
    return errors


def has_superpowers(path: Path | None) -> bool:
    if not path or not path.is_dir():
        return False
    candidates = (path / "skills", path)
    required = (
        "brainstorming",
        "writing-plans",
        "subagent-driven-development",
        "systematic-debugging",
        "verification-before-completion",
    )
    return any(
        all((candidate / skill / "SKILL.md").is_file() for skill in required)
        for candidate in candidates
    )


def route_project(
    state_path: Path | None,
    superpowers_path: Path | None,
    repo: Path,
    new_project: bool,
    migrate_to_v2: bool,
) -> dict[str, Any]:
    if migrate_to_v2:
        legacy_detected = (repo / "docs" / "superpowers").exists()
        if state_path is not None and state_path.is_file():
            state = load_state(state_path)
            if state.get("method_version") == 2:
                validate_state(state_path)
                return {"route": "v2-standalone", "superpowers_required": False}
            if state.get("method_version") != 1:
                raise BMError(
                    "BLOQUEADO: somente estado v1 pode receber migração explícita para v2",
                    EXIT_BLOCKED,
                )
            legacy_detected = True
        return {
            "route": "v2-migration",
            "legacy_detected": legacy_detected,
            "superpowers_required": False,
        }
    if state_path is None or not state_path.is_file():
        legacy = (repo / "docs" / "superpowers").exists()
        if legacy:
            if not has_superpowers(superpowers_path):
                raise BMError(
                    "BLOQUEADO: artefatos v1 detectados e Superpowers indisponível",
                    EXIT_BLOCKED,
                )
            return {"route": "v1-superpowers-provisional", "superpowers": str(superpowers_path)}
        if new_project:
            return {"route": "v2-new", "superpowers_required": False}
        raise BMError("BLOQUEADO: estado ausente; confirme se o projeto é novo", EXIT_BLOCKED)
    state = load_state(state_path)
    version = state.get("method_version")
    if version == 1:
        available = has_superpowers(superpowers_path)
        if not available:
            raise BMError(
                "BLOQUEADO: projeto v1 exige Superpowers disponível; nenhuma migração automática",
                EXIT_BLOCKED,
            )
        return {"route": "v1-superpowers", "superpowers": str(superpowers_path)}
    if version == 2 and state.get("method_mode") == "standalone-adaptive":
        validate_state(state_path)
        return {"route": "v2-standalone", "superpowers_required": False}
    raise BMError("BLOQUEADO: versão do método ausente, inválida ou não suportada", EXIT_BLOCKED)


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_manifest(root: Path, files: list[str]) -> bytes:
    base = root.resolve()
    normalized: list[str] = []
    for item in files:
        relative_path = Path(item)
        if relative_path.is_absolute():
            raise BMError(f"arquivo do pacote deve ser relativo: {item}")
        normalized.append(relative_path.as_posix())
    normalized = sorted(set(normalized))
    lines: list[str] = []
    for relative in normalized:
        target = (base / relative).resolve()
        try:
            target.relative_to(base)
        except ValueError as error:
            raise BMError(f"arquivo fora da raiz: {relative}") from error
        if not target.is_file():
            raise BMError(f"arquivo do pacote ausente: {relative}")
        lines.append(f"{file_digest(target)}  {relative}\n")
    return "".join(lines).encode("utf-8")


def confined_path(root: Path, value: str, label: str) -> Path:
    base = root.resolve()
    relative = Path(value)
    if relative.is_absolute():
        raise BMError(f"{label} deve ser relativo à raiz")
    target = (base / relative).resolve()
    try:
        target.relative_to(base)
    except ValueError as error:
        raise BMError(f"{label} fora da raiz: {value}") from error
    return target


ROOT_SUPERPOWERS_IGNORE = "/.superpowers/"
ROOT_SUPERPOWERS_ARCHIVE = "docs/bianchini/legacy/root-superpowers"
LEGACY_STATE_ARCHIVE = "docs/bianchini/legacy/transitions/PROJECT_STATE-v1-final.md"
IDLE_NEXT_ACTION = (
    "Aguardar novo escopo; então executar /sdd-planning para iniciar o ciclo v1 standalone."
)


def tracked_root_superpowers(root: Path) -> list[str]:
    output = run_git(["ls-files", "-z", "--", ".superpowers"], root)
    return sorted(item for item in output.split("\0") if item)


def has_versioned_superpowers_ignore(root: Path) -> bool:
    gitignore = root / ".gitignore"
    if not gitignore.is_file():
        return False
    patterns = {
        line.strip()
        for line in gitignore.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    return bool(patterns & {"/.superpowers/", ".superpowers/", "/.superpowers"})


def ensure_versioned_superpowers_ignore(root: Path) -> bool:
    if has_versioned_superpowers_ignore(root):
        return False
    gitignore = root / ".gitignore"
    content = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
    if content and not content.endswith("\n"):
        content += "\n"
    content += "\n# Artefatos locais de execução do Bianchini Method/Superpowers\n"
    content += ROOT_SUPERPOWERS_IGNORE + "\n"
    gitignore.write_text(content.lstrip("\n"), encoding="utf-8")
    return True


def repository_hygiene(
    repo: Path,
    migrate: bool,
    destination: str = ROOT_SUPERPOWERS_ARCHIVE,
) -> dict[str, Any]:
    root = repo.resolve()
    top = Path(run_git(["rev-parse", "--show-toplevel"], root)).resolve()
    if top != root:
        raise BMError(f"--repo deve apontar para a raiz Git: {top}")
    tracked = tracked_root_superpowers(root)
    ignored = has_versioned_superpowers_ignore(root)
    if not migrate:
        problems: list[str] = []
        if tracked:
            problems.append(
                f"{len(tracked)} arquivo(s) de .superpowers ainda rastreado(s)"
            )
        if not ignored:
            problems.append(f"{ROOT_SUPERPOWERS_IGNORE} ausente do .gitignore")
        if problems:
            raise BMError(
                "BLOQUEADO: higiene do repositório: " + "; ".join(problems),
                EXIT_BLOCKED,
            )
        return {
            "valid": True,
            "tracked_root_artifacts": [],
            "ignore_rule": ROOT_SUPERPOWERS_IGNORE,
        }

    status = run_git(["status", "--porcelain=v1", "--untracked-files=all"], root)
    unrelated: list[str] = []
    for line in status.splitlines():
        path = line[3:].split(" -> ")[-1]
        if path != ".superpowers" and not path.startswith(".superpowers/"):
            unrelated.append(path)
    if unrelated:
        raise BMError(
            "BLOQUEADO: migração de higiene exige ausência de mudanças alheias: "
            + ", ".join(sorted(unrelated)),
            EXIT_BLOCKED,
        )

    archive_root = confined_path(root, destination, "destino da higiene")
    if archive_root == root or ".superpowers" in archive_root.relative_to(root).parts:
        raise BMError("destino da higiene deve ficar fora de .superpowers")
    moved: list[dict[str, str]] = []
    for source_name in tracked:
        source_relative = Path(source_name)
        if not source_relative.parts or source_relative.parts[0] != ".superpowers":
            raise BMError(f"caminho Git inesperado: {source_name}")
        source = confined_path(root, source_name, "artefato raiz")
        if source.is_symlink() or not source.is_file():
            raise BMError(f"artefato rastreado ausente ou não regular: {source_name}")
        relative_tail = Path(*source_relative.parts[1:])
        target_relative = Path(destination) / relative_tail
        target = confined_path(root, target_relative.as_posix(), "arquivo histórico")
        if target.exists():
            if (
                target.is_symlink()
                or not target.is_file()
                or target.read_bytes() != source.read_bytes()
            ):
                raise BMError(
                    f"destino histórico já existe com conteúdo diferente: {target_relative}"
                )
            source.unlink()
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            source.replace(target)
        moved.append({"from": source_name, "to": target_relative.as_posix()})

    ignore_added = ensure_versioned_superpowers_ignore(root)
    run_git(["add", "--", ".gitignore"], root)
    if tracked:
        run_git(["add", "-u", "--", ".superpowers"], root)
        run_git(["add", "--", destination], root)
    remaining = tracked_root_superpowers(root)
    if remaining:
        raise BMError(
            "BLOQUEADO: migração não removeu todos os artefatos raiz: "
            + ", ".join(remaining),
            EXIT_BLOCKED,
        )
    return {
        "valid": True,
        "moved": moved,
        "ignore_added": ignore_added,
        "ignore_rule": ROOT_SUPERPOWERS_IGNORE,
        "archive_root": archive_root.relative_to(root).as_posix(),
        "staged": True,
    }


def idle_v2_state(planning_version: str = "v1") -> dict[str, Any]:
    if not re.fullmatch(r"v[1-9][0-9]*", planning_version):
        raise BMError("planning_version inválida; esperado v1, v2, ...")
    return {
        "method_version": 2,
        "method_mode": "standalone-adaptive",
        "planning_version": planning_version,
        "planning_status": "idle",
        "execution_policy": "adaptive",
        "assurance_profile": "lean",
        "architecture_audit": "optional",
        "architecture_audit_status": "not_run",
        "manual_pdf": "scope",
        "scope": {"status": "pending", "source": None, "approved_at": None},
        "planning": {"spec": None, "review": None},
        "approval": {
            "status": "pending",
            "approved_at": None,
            "approved_by": None,
            "approved_plans": [],
            "package": {
                "algorithm": "sha256-manifest-v1",
                "manifest_path": (
                    f"artifacts/bianchini/{planning_version}/approval/manifest.sha256"
                ),
                "manifest_digest": None,
                "files": [],
            },
        },
        "plans": [],
        "verification": {
            "fast": {"commands": [], "status": "pending"},
            "plan": {"commands": [], "status": "pending"},
            "release": {"commands": [], "status": "pending"},
        },
        "release": {
            "status": "pending",
            "platforms": [],
            "profiles": [],
            "candidate": None,
            "final_gate": "homologar-sistema",
            "homologation": "pending",
            "final_review": "pending",
            "delivery": "pending",
        },
        "active_execution": None,
        "telemetry": {
            "enabled": False,
            "path": f"artifacts/bianchini/{planning_version}/telemetry.jsonl",
        },
        "blockers": [],
        "next_action": IDLE_NEXT_ACTION,
    }


def legacy_transition(
    repo: Path,
    state_path: Path,
    completed: bool,
    archive: str = LEGACY_STATE_ARCHIVE,
) -> dict[str, Any]:
    root = repo.resolve()
    top = Path(run_git(["rev-parse", "--show-toplevel"], root)).resolve()
    if top != root:
        raise BMError(f"--repo deve apontar para a raiz Git: {top}")
    candidate = state_path if state_path.is_absolute() else root / state_path
    resolved_state = candidate.resolve()
    try:
        state_relative = resolved_state.relative_to(root)
    except ValueError as error:
        raise BMError("estado legado deve ficar dentro do repositório") from error
    if candidate.is_symlink() or not resolved_state.is_file():
        raise BMError("estado legado deve ser arquivo regular dentro do repositório")

    current = load_state(resolved_state)
    if current.get("method_version") == 2:
        validated = validate_state(resolved_state)
        if validated["planning_status"] != "idle":
            raise BMError(
                "BLOQUEADO: projeto já está em v2 com ciclo ativo",
                EXIT_BLOCKED,
            )
        return {
            "transitioned": False,
            "already_transitioned": True,
            "route": "v2-standalone",
            "planning_status": "idle",
            "planning_version": validated["planning_version"],
            "state": state_relative.as_posix(),
        }
    if current.get("method_version") != 1:
        raise BMError("BLOQUEADO: somente estado legado v1 pode transicionar", EXIT_BLOCKED)
    if not completed:
        raise BMError(
            "BLOQUEADO: --completed é obrigatório e só pode ser informado após gates, entrega e encerramento legado",
            EXIT_BLOCKED,
        )
    dirty = run_git(["status", "--porcelain=v1", "--untracked-files=all"], root)
    if dirty:
        changed = [line[3:] if len(line) > 3 else line for line in dirty.splitlines()]
        raise BMError(
            "BLOQUEADO: transição legado → v2 exige fase concluída commitada e árvore limpa: "
            + ", ".join(changed[:8]),
            EXIT_BLOCKED,
        )
    try:
        tracked = run_git(
            ["ls-files", "--error-unmatch", "--", state_relative.as_posix()], root
        )
    except BMError as error:
        raise BMError(
            "BLOQUEADO: estado legado deve estar commitado no HEAD", EXIT_BLOCKED
        ) from error
    if tracked != state_relative.as_posix():
        raise BMError("BLOQUEADO: estado legado deve estar commitado no HEAD", EXIT_BLOCKED)

    legacy_bytes = resolved_state.read_bytes()
    archive_path = confined_path(root, archive, "arquivo histórico do estado legado")
    if archive_path == resolved_state:
        raise BMError("arquivo histórico deve ser diferente do estado ativo")
    if archive_path.exists() and (
        archive_path.is_symlink()
        or not archive_path.is_file()
        or archive_path.read_bytes() != legacy_bytes
    ):
        raise BMError(
            f"BLOQUEADO: arquivo histórico já existe com conteúdo diferente: {archive}",
            EXIT_BLOCKED,
        )

    repository_hygiene(root, True)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    if not archive_path.exists():
        archive_path.write_bytes(legacy_bytes)
    next_state = idle_v2_state("v1")
    resolved_state.write_text(
        json.dumps(next_state, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    validate_state(resolved_state)
    run_git(
        ["add", "--", state_relative.as_posix(), archive_path.relative_to(root).as_posix()],
        root,
    )
    repository_hygiene(root, False)
    staged = run_git(["diff", "--cached", "--name-only"], root).splitlines()
    return {
        "transitioned": True,
        "already_transitioned": False,
        "route": "v2-standalone",
        "planning_status": "idle",
        "planning_version": "v1",
        "state": state_relative.as_posix(),
        "legacy_archive": archive_path.relative_to(root).as_posix(),
        "staged": sorted(staged),
        "next_action": IDLE_NEXT_ACTION,
    }


TELEMETRY_METRICS = (
    "input_tokens",
    "output_tokens",
    "duration_ms",
    "fix_rounds",
    "gate_failures",
    "homologation_bugs",
)


def telemetry_config(state: dict[str, Any]) -> dict[str, Any]:
    config = state.get("telemetry")
    if not isinstance(config, dict):
        return {"enabled": False, "path": None}
    return {"enabled": bool(config.get("enabled")), "path": config.get("path")}


def telemetry_path(state: dict[str, Any], root: Path) -> Path | None:
    config = telemetry_config(state)
    if not config["enabled"]:
        return None
    if not root.is_dir():
        raise BMError(f"raiz de telemetria não encontrada: {root}")
    if not isinstance(config["path"], str) or not config["path"]:
        raise BMError("telemetry.path é obrigatório quando telemetria está habilitada")
    return confined_path(root, config["path"], "telemetry.path")


def telemetry_record(
    state_path: Path,
    root: Path,
    plan: str | None,
    phase: str,
    recorded_at: str | None,
    metrics: dict[str, int],
) -> dict[str, Any]:
    state = validate_state(state_path)
    destination = telemetry_path(state, root)
    if destination is None:
        return {"enabled": False, "recorded": False}
    if plan and plan not in {item["id"] for item in state["plans"]}:
        raise BMError(f"plano de telemetria inexistente: {plan}")
    if any(value < 0 for value in metrics.values()):
        raise BMError("métricas de telemetria não podem ser negativas")
    if not any(metrics.values()):
        raise BMError("informe ao menos uma métrica maior que zero")
    timestamp = recorded_at or datetime.now(timezone.utc).isoformat()
    try:
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as error:
        raise BMError("--at deve usar timestamp ISO-8601") from error
    record = {
        "schema_version": 1,
        "recorded_at": timestamp,
        "plan": plan,
        "phase": phase,
        "metrics": metrics,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return {
        "enabled": True,
        "recorded": True,
        "path": str(destination),
        "record": record,
    }


def summarize_telemetry(state: dict[str, Any], root: Path) -> dict[str, Any]:
    destination = telemetry_path(state, root)
    empty = {key: 0 for key in TELEMETRY_METRICS}
    if destination is None:
        return {"enabled": False, "records": 0, "totals": empty, "plans": {}}
    if not destination.is_file():
        return {
            "enabled": True,
            "path": str(destination),
            "records": 0,
            "totals": empty,
            "plans": {},
        }
    totals = {key: 0 for key in TELEMETRY_METRICS}
    plans: dict[str, dict[str, int]] = {}
    records = 0
    for line_number, line in enumerate(destination.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise BMError(f"telemetria inválida na linha {line_number}: {error.msg}") from error
        metrics = record.get("metrics") if isinstance(record, dict) else None
        if not isinstance(metrics, dict):
            raise BMError(f"telemetria inválida na linha {line_number}: metrics ausente")
        records += 1
        plan = record.get("plan") or "_release"
        plan_totals = plans.setdefault(plan, {key: 0 for key in TELEMETRY_METRICS})
        for key in TELEMETRY_METRICS:
            value = metrics.get(key, 0)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise BMError(f"telemetria inválida na linha {line_number}: {key}")
            totals[key] += value
            plan_totals[key] += value
    return {
        "enabled": True,
        "path": str(destination),
        "records": records,
        "totals": totals,
        "plans": plans,
    }


def telemetry_summary(state_path: Path, root: Path) -> dict[str, Any]:
    return summarize_telemetry(validate_state(state_path), root)


def snapshot(state_path: Path, root: Path, verify: bool) -> dict[str, Any]:
    state = validate_state(state_path)
    package = state["approval"]["package"]
    content = build_manifest(root, package["files"])
    digest = hashlib.sha256(content).hexdigest()
    manifest = confined_path(root, package["manifest_path"], "manifest_path")
    if verify:
        if not manifest.is_file() or manifest.read_bytes() != content:
            raise BMError("snapshot inválido: conteúdo do manifesto divergiu", EXIT_BLOCKED)
        if package.get("manifest_digest") != digest:
            raise BMError("snapshot inválido: digest do estado divergiu", EXIT_BLOCKED)
    else:
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_bytes(content)
    return {"algorithm": "sha256-manifest-v1", "digest": digest, "manifest": str(manifest)}


def policy(profile: str, risk: str, change: str, manual_pdf: str, manual_in_scope: bool, round_number: int) -> dict[str, Any]:
    if risk == "low":
        execution, review, cadence = "grouped", "plan_gate", "group_seam"
    elif risk == "medium":
        execution, review, cadence = "slice", "per_slice", "slice_seam"
    else:
        execution, review, cadence = "strict", "per_task", "red_green_per_task"
    max_rounds = {"lean": 2, "standard": 3, "full": 5}[profile]
    manual_required = manual_pdf in {"quick_start", "full"} or (
        manual_pdf == "scope" and manual_in_scope
    )
    visual_validation = change == "visual"
    return {
        "execution": execution,
        "review": review,
        "test_cadence": cadence,
        "max_fix_rounds": max_rounds,
        "breaker": round_number >= max_rounds,
        "architecture_audit_required": False,
        "architecture_audit_mode": "manual_report_only",
        "manual_required": manual_required,
        "manual_level": manual_pdf if manual_required else "none",
        "visual_validation": "screenshot_or_visual_regression" if visual_validation else "behavioral_seam",
        "homologation_order": ["automated_regression", "coded_e2e", "proof_map", "manual_gaps"],
    }


def workspace_identity(planning_version: str, plan: str) -> tuple[str, str]:
    if not re.fullmatch(r"v[1-9][0-9]*", planning_version):
        raise BMError("planning_version inválida; esperado v1, v2, ...")
    safe_plan = re.sub(r"[^a-z0-9-]+", "-", plan.lower()).strip("-")
    if not safe_plan:
        raise BMError("identificador de plano inválido")
    identity = f"{planning_version.lower()}-{safe_plan}"
    return identity, f"bm/{identity}"


def worktree_entries(repo: Path) -> list[dict[str, str]]:
    output = run_git(["worktree", "list", "--porcelain"], repo)
    entries: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for line in [*output.splitlines(), ""]:
        if not line:
            if current:
                entries.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        current[key] = value
    return entries


def workspace_locate(
    repo: Path,
    planning_version: str,
    plan: str,
    require_safe: bool = False,
) -> dict[str, Any]:
    identity, branch = workspace_identity(planning_version, plan)
    expected_ref = f"refs/heads/{branch}"
    for entry in worktree_entries(repo):
        if entry.get("branch") == expected_ref:
            workspace = Path(entry["worktree"]).resolve()
            result: dict[str, Any] = {
                "workspace": str(workspace),
                "branch": branch,
                "identity": identity,
                "planning_version": planning_version,
                "plan": plan,
                "source": str(Path(run_git(["rev-parse", "--show-toplevel"], repo)).resolve()),
                "reused": True,
            }
            if require_safe:
                result.update(workspace_check(workspace))
            return result
    raise BMError(
        f"workspace não localizado para {planning_version}/{plan}", EXIT_BLOCKED
    )


def git_ref_exists(repo: Path, ref: str) -> bool:
    completed = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", ref],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    return completed.returncode == 0


def committed_package_preflight(
    root: Path,
    state_path: Path,
    planning_version: str,
    plan: str,
) -> dict[str, Any]:
    dirty = run_git(["status", "--porcelain=v1", "--untracked-files=all"], root)
    if dirty:
        changed = [line[3:] if len(line) > 3 else line for line in dirty.splitlines()]
        raise BMError(
            "BLOQUEADO: repositório possui alterações não commitadas; "
            "commit local do pacote aprovado é obrigatório antes da worktree: "
            + ", ".join(changed[:8]),
            EXIT_BLOCKED,
        )
    repository_hygiene(root, False)
    resolved_state = (
        state_path.resolve()
        if state_path.is_absolute()
        else (root / state_path).resolve()
    )
    try:
        state_relative = resolved_state.relative_to(root).as_posix()
    except ValueError as error:
        raise BMError("estado deve estar dentro do repositório") from error
    state = validate_state(resolved_state)
    if state["planning_version"] != planning_version:
        raise BMError(
            f"planning_version divergente: estado={state['planning_version']} argumento={planning_version}"
        )
    approval = state["approval"]
    if state["planning_status"] != "approved" or approval["status"] != "approved":
        raise BMError("BLOQUEADO: pacote de planejamento ainda não está aprovado", EXIT_BLOCKED)
    if plan not in approval["approved_plans"]:
        raise BMError(f"BLOQUEADO: plano {plan} não pertence ao pacote aprovado", EXIT_BLOCKED)
    selected = next((item for item in state["plans"] if item["id"] == plan), None)
    if not selected or selected["status"] != "approved":
        raise BMError(f"BLOQUEADO: plano {plan} não está com status approved", EXIT_BLOCKED)
    snapshot(resolved_state, root, True)
    package = approval["package"]
    committed_paths = [
        *package["files"],
        state_relative,
        Path(package["manifest_path"]).as_posix(),
    ]
    for relative in dict.fromkeys(committed_paths):
        try:
            tracked = run_git(["ls-files", "--error-unmatch", "--", relative], root)
        except BMError as error:
            raise BMError(
                f"BLOQUEADO: arquivo do pacote aprovado não está commitado: {relative}",
                EXIT_BLOCKED,
            ) from error
        if not tracked:
            raise BMError(
                f"BLOQUEADO: arquivo do pacote aprovado não está commitado: {relative}",
                EXIT_BLOCKED,
            )
        head_digest = run_git(["rev-parse", f"HEAD:{relative}"], root)
        worktree_digest = run_git(["hash-object", f"--path={relative}", relative], root)
        if head_digest != worktree_digest:
            raise BMError(
                f"BLOQUEADO: HEAD não contém os bytes aprovados de {relative}",
                EXIT_BLOCKED,
            )
    return {
        "state": state,
        "state_relative": state_relative,
        "base_revision": run_git(["rev-parse", "HEAD"], root),
    }


def workspace_create(
    repo: Path,
    planning_version: str,
    plan: str,
    state_path: Path,
    target: Path | None,
) -> dict[str, Any]:
    root = Path(run_git(["rev-parse", "--show-toplevel"], repo)).resolve()
    identity, branch = workspace_identity(planning_version, plan)
    destination = target or root.parent / ".bianchini-worktrees" / root.name / identity
    destination = destination.resolve()
    try:
        destination.relative_to(root)
    except ValueError:
        pass
    else:
        raise BMError("workspace deve ficar fora do repositório fonte", EXIT_UNSAFE_WORKSPACE)
    preflight = committed_package_preflight(root, state_path, planning_version, plan)
    try:
        located = workspace_locate(root, planning_version, plan)
    except BMError as error:
        if error.exit_code != EXIT_BLOCKED:
            raise
        located = None
    if located:
        if target and Path(str(located["workspace"])).resolve() != destination:
            raise BMError(f"branch {branch} já está em {located['workspace']}")
        located.update(
            {
                "state": preflight["state_relative"],
                "base_revision": preflight["base_revision"],
            }
        )
        return located
    if destination.exists():
        raise BMError(f"workspace já existe: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if git_ref_exists(root, f"refs/heads/{branch}"):
        run_git(["worktree", "add", str(destination), branch], root)
    else:
        run_git(["worktree", "add", "-b", branch, str(destination), "HEAD"], root)
    return {
        "workspace": str(destination),
        "branch": branch,
        "identity": identity,
        "planning_version": planning_version,
        "plan": plan,
        "source": str(root),
        "state": preflight["state_relative"],
        "base_revision": preflight["base_revision"],
        "reused": False,
    }


def workspace_check(cwd: Path) -> dict[str, Any]:
    branch = run_git(["branch", "--show-current"], cwd)
    if branch in {"main", "master", ""}:
        raise BMError(f"BLOQUEADO: implementação proibida na branch {branch or 'detached'}", EXIT_UNSAFE_WORKSPACE)
    git_dir = Path(run_git(["rev-parse", "--path-format=absolute", "--git-dir"], cwd))
    common = Path(run_git(["rev-parse", "--path-format=absolute", "--git-common-dir"], cwd))
    if git_dir.resolve() == common.resolve():
        raise BMError("BLOQUEADO: execução v2 exige linked worktree isolada", EXIT_UNSAFE_WORKSPACE)
    return {"safe": True, "branch": branch, "git_dir": str(git_dir), "common_dir": str(common)}


def extract_task(plan: Path, task: str) -> str:
    content = plan.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"(?ms)^###\s+(?:Tarefa|Task)\s+{re.escape(task)}\b.*?(?=^###\s+(?:Tarefa|Task)\s+\S+|\Z)"
    )
    match = pattern.search(content)
    if not match:
        raise BMError(f"tarefa {task} não encontrada em {plan}")
    return match.group(0).rstrip() + "\n"


def parse_task_selector(selector: str) -> list[str]:
    tasks: list[str] = []
    for token in (item.strip() for item in selector.split(",")):
        if not token:
            continue
        interval = re.fullmatch(r"(\d+)\s*-\s*(\d+)", token)
        if interval:
            start, end = map(int, interval.groups())
            if end < start:
                raise BMError(f"intervalo de tarefas inválido: {token}")
            tasks.extend(str(number) for number in range(start, end + 1))
        elif re.fullmatch(r"[A-Za-z0-9_.-]+", token):
            tasks.append(token)
        else:
            raise BMError(f"seletor de tarefa inválido: {token}")
    ordered = list(dict.fromkeys(tasks))
    if not ordered:
        raise BMError("nenhuma tarefa selecionada")
    return ordered


def extract_group(plan: Path, heading: str) -> str:
    content = plan.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"(?ms)^###\s+{re.escape(heading)}\s*$.*?(?=^###\s+|\Z)"
    )
    match = pattern.search(content)
    if not match:
        raise BMError(f"grupo {heading!r} não encontrado em {plan}")
    return match.group(0).rstrip() + "\n"


def content_digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def write_task_brief(
    plan: Path,
    task: str | None,
    tasks: str | None,
    group: str | None,
    output: Path,
) -> dict[str, Any]:
    if group:
        labels = [group]
        sections = [extract_group(plan, group)]
        title = group
    else:
        labels = parse_task_selector(tasks or task or "")
        sections = [extract_task(plan, label) for label in labels]
        title = ", ".join(labels)
        if len(labels) > 1:
            executions = []
            for label, section in zip(labels, sections):
                match = re.search(r"(?mi)^\*\*Execution:\*\*\s*([a-z_]+)\s*$", section)
                if not match:
                    raise BMError(f"tarefa {label} não declara Execution")
                executions.append(match.group(1))
            if any(mode != "grouped" for mode in executions):
                raise BMError(
                    "brief com várias tarefas exige Execution: grouped em todas as unidades"
                )
    source_hash = file_digest(plan)
    unit_hashes = [content_digest(section) for section in sections]
    group_digest = content_digest("\n--- bm-unit ---\n".join(sections))
    kind = "heading" if group else "group" if len(labels) > 1 else "task"
    group_id = f"group-{group_digest[:12]}" if kind in {"group", "heading"} else None
    metadata = "\n".join(
        f"- Unit `{label}` SHA-256: `{digest}`"
        for label, digest in zip(labels, unit_hashes)
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        f"# Task Brief {title}\n\n- Plan: `{plan}`\n"
        f"- Plan SHA-256: `{source_hash}`\n"
        f"- Kind: `{kind}`\n"
        f"- Group ID: `{group_id or 'n/a'}`\n"
        f"- Group SHA-256: `{group_digest}`\n{metadata}\n\n"
        + "\n".join(sections),
        encoding="utf-8",
    )
    return {
        "brief": str(output),
        "plan_digest": source_hash,
        "kind": kind,
        "group_id": group_id,
        "group_digest": group_digest,
        "tasks": labels,
        "unit_digests": unit_hashes,
    }


def write_report(brief: Path, output: Path) -> dict[str, Any]:
    brief_digest = file_digest(brief)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "# Implementer Report\n\n"
        f"- Brief: `{brief}`\n- Status: IN_PROGRESS\n\n"
        "## Changes\n\n## Verification\n\n## Decisions\n\n## Concerns\n",
        encoding="utf-8",
    )
    return {"report": str(output), "brief_digest": brief_digest}


def redact_sensitive_diff(diff: str) -> tuple[str, int]:
    patterns = (
        (
            re.compile(
                r"(?ms)-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----"
            ),
            "[REDACTED PRIVATE KEY]",
        ),
        (
            re.compile(
                r"(?im)(\b(?:api[_-]?key|access[_-]?token|auth[_-]?token|password|passwd|secret)\b\s*[:=]\s*)[^\s]+"
            ),
            r"\1[REDACTED]",
        ),
        (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer [REDACTED]"),
        (
            re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
            "[REDACTED EMAIL]",
        ),
    )
    redacted = diff
    total = 0
    for pattern, replacement in patterns:
        redacted, count = pattern.subn(replacement, redacted)
        total += count
    return redacted, total


def write_review_package(cwd: Path, base: str, head: str, brief: Path, report: Path, output: Path) -> dict[str, Any]:
    commits = run_git(["log", "--oneline", f"{base}..{head}"], cwd)
    stat = run_git(["diff", "--stat", base, head], cwd)
    raw_diff = run_git(["diff", "-U10", base, head], cwd)
    diff, redactions = redact_sensitive_diff(raw_diff)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "# Review Package\n\n"
        f"- Base: `{base}`\n- Head: `{head}`\n- Brief: `{brief}` ({file_digest(brief)})\n"
        f"- Report: `{report}` ({file_digest(report)})\n"
        f"- Security notice: sanitização heurística; {redactions} ocorrência(s) removida(s). Revise antes de compartilhar.\n\n"
        f"## Commits\n\n```text\n{commits}\n```\n\n"
        f"## Stat\n\n```text\n{stat}\n```\n\n"
        f"## Diff\n\n```diff\n{diff}\n```\n",
        encoding="utf-8",
    )
    return {
        "review_package": str(output),
        "base": base,
        "head": head,
        "redactions": redactions,
    }


def write_checkpoint(state: Path, ledger: Path, cwd: Path, output: Path) -> dict[str, Any]:
    state_value = load_state(state)
    if state_value.get("method_version") == 2:
        state_value = validate_state(state)
    ledger_lines = ledger.read_text(encoding="utf-8").splitlines()[-80:] if ledger.is_file() else []
    checkpoint = {
        "method_version": state_value.get("method_version"),
        "planning_status": state_value.get("planning_status"),
        "approval": state_value.get("approval", {}).get("status"),
        "plans": [
            {"id": item.get("id"), "status": item.get("status"), "ledger": item.get("ledger")}
            for item in state_value.get("plans", [])
        ],
        "release": state_value.get("release"),
        "next_action": state_value.get("next_action"),
        "workspace": str(cwd.resolve()),
        "git": {
            "branch": run_git(["branch", "--show-current"], cwd),
            "head": run_git(["rev-parse", "HEAD"], cwd),
            "dirty": bool(run_git(["status", "--porcelain"], cwd)),
        },
        "ledger_tail": ledger_lines,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"checkpoint": str(output), "digest": file_digest(output)}


def write_proof_map(state_path: Path, evidence_path: Path, output: Path) -> dict[str, Any]:
    state = validate_state(state_path)
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    if not isinstance(evidence, list) or not all(isinstance(item, dict) for item in evidence):
        raise BMError("evidência deve ser uma lista JSON de objetos")
    candidate = state.get("release", {}).get("candidate")
    if not isinstance(candidate, dict):
        raise BMError("release candidate com fingerprint é obrigatório para proof-map")
    fingerprint = {
        key: candidate[key] for key in ("id", "revision", "build", "checksum")
    }
    by_command = {item.get("command"): item for item in evidence if item.get("command")}
    rows: list[dict[str, Any]] = []
    gaps: list[str] = []
    for command in state["verification"]["release"]["commands"]:
        item = by_command.get(command)
        evidence_fingerprint = (
            {
                "id": item.get("rc", item.get("id")),
                "revision": item.get("revision"),
                "build": item.get("build"),
                "checksum": item.get("checksum"),
            }
            if item
            else None
        )
        same_candidate = evidence_fingerprint == fingerprint
        proven = bool(item and item.get("result") == "passed" and same_candidate)
        rows.append(
            {
                "command": command,
                "proven": proven,
                "candidate": evidence_fingerprint,
                "evidence": item.get("evidence") if item else None,
            }
        )
        if not proven:
            gaps.append(command)
    manual_gaps = [
        item.get("journey")
        for item in evidence
        if item.get("type") == "manual_gap" and item.get("journey")
    ]
    proof = {
        "candidate": fingerprint,
        "automated": rows,
        "automated_total": len(rows),
        "automated_proven": len(rows) - len(gaps),
        "automation_gaps": gaps,
        "manual_gaps": manual_gaps,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"proof_map": str(output), **proof}


def state_summary(path: Path, root: Path | None = None) -> dict[str, Any]:
    state = load_state(path)
    if state.get("method_version") == 1:
        return {
            "method_version": 1,
            "method_mode": "legacy-superpowers",
            "mode": "legacy-superpowers",
            "status": "legacy",
            "implicit_legacy": bool(state.get("_implicit_legacy")),
        }
    validate_state(path)
    plans = state.get("plans", [])
    declared_active = state.get("active_execution") or {}
    active_plan_id = declared_active.get("plan_id")
    if not active_plan_id:
        active_plan_id = next(
            (item["id"] for item in plans if item["status"] == "in_progress"), None
        )
    active_plan = next((item for item in plans if item["id"] == active_plan_id), None)
    completed_ids = {item["id"] for item in plans if item["status"] == "completed"}
    next_plan = next(
        (
            item
            for item in plans
            if item["status"] == "approved"
            and all(dependency in completed_ids for dependency in item["depends_on"])
        ),
        None,
    )
    telemetry = telemetry_config(state)
    if root is not None:
        telemetry = summarize_telemetry(state, root)
    return {
        "method_version": 2,
        "method_mode": state["method_mode"],
        "assurance_profile": state["assurance_profile"],
        "planning_version": state["planning_version"],
        "planning_status": state["planning_status"],
        "approval": state["approval"]["status"],
        "approval_digest": state["approval"]["package"].get("manifest_digest"),
        "approved_plans": state["approval"]["approved_plans"],
        "architecture_audit": state["architecture_audit"],
        "architecture_audit_status": state["architecture_audit_status"],
        "manual_pdf": state["manual_pdf"],
        "plans": {item["id"]: item["status"] for item in plans},
        "active_plan": active_plan_id,
        "active_unit": declared_active.get("unit"),
        "execution_mode": active_plan.get("execution") if active_plan else None,
        "next_plan": next_plan.get("id") if next_plan else None,
        "next_execution_mode": next_plan.get("execution") if next_plan else None,
        "current_gate": declared_active.get("gate"),
        "workspace": declared_active.get("workspace"),
        "active_execution": {
            "plan": active_plan_id,
            "unit": declared_active.get("unit"),
            "mode": active_plan.get("execution") if active_plan else None,
            "gate": declared_active.get("gate"),
            "workspace": declared_active.get("workspace"),
        },
        "verification": {key: value["status"] for key, value in state["verification"].items()},
        "telemetry": telemetry,
        "release": state["release"],
        "blockers": state["blockers"],
        "next_action": state["next_action"],
    }


def render_status(summary: dict[str, Any]) -> str:
    if summary["method_version"] == 1:
        return (
            "# Status do projeto\n\n"
            "- Método: v1 legado (Superpowers)\n"
            f"- Marcador implícito: {'sim' if summary.get('implicit_legacy') else 'não'}\n"
        )
    plans = ", ".join(
        f"{plan_id}={status}" for plan_id, status in summary["plans"].items()
    )
    verification = ", ".join(
        f"{stage}={status}" for stage, status in summary["verification"].items()
    )
    release = summary["release"]
    blockers = summary["blockers"]
    telemetry = summary["telemetry"]
    if telemetry.get("enabled") and "totals" in telemetry:
        totals = telemetry["totals"]
        telemetry_line = (
            f"ativa, registros={telemetry['records']}, "
            f"tokens={totals['input_tokens'] + totals['output_tokens']}, "
            f"duração_ms={totals['duration_ms']}, fix_rounds={totals['fix_rounds']}, "
            f"falhas_gate={totals['gate_failures']}, bugs_homologação={totals['homologation_bugs']}"
        )
    else:
        telemetry_line = "ativa (resumo exige --root)" if telemetry.get("enabled") else "desativada"
    return (
        "# Status do projeto\n\n"
        f"- Método: v2 {summary['method_mode']} / planejamento {summary['planning_version']}\n"
        f"- Perfil: {summary['assurance_profile']}\n"
        f"- Planejamento: {summary['planning_status']}\n"
        f"- Aprovação: {summary['approval']} / digest {summary['approval_digest']}\n"
        f"- Planos: {plans or 'nenhum'}\n"
        f"- Plano ativo: {summary['active_plan'] or 'nenhum'} / "
        f"unidade {summary['active_unit'] or 'nenhuma'} / "
        f"modo {summary['execution_mode'] or 'n/a'}\n"
        f"- Próximo plano: {summary['next_plan'] or 'nenhum'} / "
        f"modo {summary['next_execution_mode'] or 'n/a'}\n"
        f"- Gate atual: {summary['current_gate'] or 'nenhum'}\n"
        f"- Gates: {verification}\n"
        f"- Release: {release['status']} / homologação {release['homologation']} / "
        f"revisão {release['final_review']} / entrega {release['delivery']}\n"
        f"- Auditoria: {summary['architecture_audit']} / {summary['architecture_audit_status']}\n"
        f"- Manual: {summary['manual_pdf']}\n"
        f"- Telemetria: {telemetry_line}\n"
        f"- Bloqueios: {len(blockers)}\n"
        f"- Próxima ação: {summary['next_action']}\n"
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="bm", description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate-state")
    validate.add_argument("state", type=Path)
    validate.add_argument("--schema", type=Path)

    route = commands.add_parser("route")
    route.add_argument("state", type=Path, nargs="?")
    route.add_argument("--superpowers-path", type=Path)
    route.add_argument("--repo", type=Path, default=Path.cwd())
    route.add_argument("--new-project", action="store_true")
    route.add_argument("--migrate-to-v2", action="store_true")

    hygiene = commands.add_parser("repo-hygiene")
    hygiene.add_argument("action", choices=["check", "migrate"])
    hygiene.add_argument("--repo", type=Path, default=Path.cwd())
    hygiene.add_argument("--destination", default=ROOT_SUPERPOWERS_ARCHIVE)

    transition = commands.add_parser("legacy-transition")
    transition.add_argument("--repo", type=Path, default=Path.cwd())
    transition.add_argument("--state", type=Path, required=True)
    transition.add_argument("--completed", action="store_true")
    transition.add_argument("--archive", default=LEGACY_STATE_ARCHIVE)

    snap = commands.add_parser("snapshot")
    snap.add_argument("action", choices=["create", "verify"])
    snap.add_argument("state", type=Path)
    snap.add_argument("--root", type=Path, required=True)

    decide = commands.add_parser("policy")
    decide.add_argument("--profile", choices=["lean", "standard", "full"], required=True)
    decide.add_argument("--risk", choices=["low", "medium", "high", "critical"], required=True)
    decide.add_argument("--change", default="behavioral")
    decide.add_argument(
        "--manual-pdf",
        choices=["none", "quick_start", "full", "scope"],
        default="scope",
    )
    decide.add_argument("--manual-in-scope", action="store_true")
    decide.add_argument("--round", type=int, default=0)

    workspace = commands.add_parser("workspace")
    workspace.add_argument("action", choices=["create", "check", "locate", "resume"])
    workspace.add_argument("--repo", type=Path, default=Path.cwd())
    workspace.add_argument("--plan")
    workspace.add_argument("--planning-version")
    workspace.add_argument("--state", type=Path)
    workspace.add_argument("--target", type=Path)

    brief = commands.add_parser("task-brief")
    brief.add_argument("--plan", type=Path, required=True)
    brief_selector = brief.add_mutually_exclusive_group(required=True)
    brief_selector.add_argument("--task")
    brief_selector.add_argument("--tasks")
    brief_selector.add_argument("--group")
    brief.add_argument("--output", type=Path, required=True)

    report = commands.add_parser("report")
    report.add_argument("--brief", type=Path, required=True)
    report.add_argument("--output", type=Path, required=True)

    review = commands.add_parser("review-package")
    review.add_argument("--cwd", type=Path, default=Path.cwd())
    review.add_argument("--base", required=True)
    review.add_argument("--head", default="HEAD")
    review.add_argument("--brief", type=Path, required=True)
    review.add_argument("--report", type=Path, required=True)
    review.add_argument("--output", type=Path, required=True)

    checkpoint = commands.add_parser("checkpoint")
    checkpoint.add_argument("--state", type=Path, required=True)
    checkpoint.add_argument("--ledger", type=Path, required=True)
    checkpoint.add_argument("--cwd", type=Path, default=Path.cwd())
    checkpoint.add_argument("--output", type=Path, required=True)

    proof = commands.add_parser("proof-map")
    proof.add_argument("--state", type=Path, required=True)
    proof.add_argument("--evidence", type=Path, required=True)
    proof.add_argument("--output", type=Path, required=True)

    telemetry = commands.add_parser("telemetry")
    telemetry.add_argument("action", choices=["record", "summary"])
    telemetry.add_argument("--state", type=Path, required=True)
    telemetry.add_argument("--root", type=Path, required=True)
    telemetry.add_argument("--plan")
    telemetry.add_argument(
        "--phase",
        choices=["planning", "execution", "gate", "homologation", "final_review"],
        default="execution",
    )
    telemetry.add_argument("--at")
    for metric in TELEMETRY_METRICS:
        telemetry.add_argument(f"--{metric.replace('_', '-')}", type=int, default=0)

    summary = commands.add_parser("status")
    summary.add_argument("state", type=Path)
    summary.add_argument("--root", type=Path)
    summary.add_argument("--format", choices=["json", "text"], default="json")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "validate-state":
            emit({"valid": True, "method_version": validate_state(args.state, args.schema)["method_version"]})
        elif args.command == "route":
            emit(
                route_project(
                    args.state,
                    args.superpowers_path,
                    args.repo,
                    args.new_project,
                    args.migrate_to_v2,
                )
            )
        elif args.command == "repo-hygiene":
            emit(
                repository_hygiene(
                    args.repo,
                    args.action == "migrate",
                    args.destination,
                )
            )
        elif args.command == "legacy-transition":
            emit(
                legacy_transition(
                    args.repo,
                    args.state,
                    args.completed,
                    args.archive,
                )
            )
        elif args.command == "snapshot":
            emit(snapshot(args.state, args.root, args.action == "verify"))
        elif args.command == "policy":
            emit(policy(args.profile, args.risk, args.change, args.manual_pdf, args.manual_in_scope, args.round))
        elif args.command == "workspace":
            if args.action == "create":
                if not args.plan or not args.planning_version or not args.state:
                    raise BMError(
                        "--plan, --planning-version e --state são obrigatórios para criar workspace"
                    )
                emit(
                    workspace_create(
                        args.repo,
                        args.planning_version,
                        args.plan,
                        args.state,
                        args.target,
                    )
                )
            elif args.action == "check":
                emit(workspace_check(args.repo))
            else:
                if not args.plan or not args.planning_version:
                    raise BMError(
                        f"--plan e --planning-version são obrigatórios para {args.action}"
                    )
                emit(
                    workspace_locate(
                        args.repo,
                        args.planning_version,
                        args.plan,
                        args.action == "resume",
                    )
                )
        elif args.command == "task-brief":
            emit(write_task_brief(args.plan, args.task, args.tasks, args.group, args.output))
        elif args.command == "report":
            emit(write_report(args.brief, args.output))
        elif args.command == "review-package":
            emit(write_review_package(args.cwd, args.base, args.head, args.brief, args.report, args.output))
        elif args.command == "checkpoint":
            emit(write_checkpoint(args.state, args.ledger, args.cwd, args.output))
        elif args.command == "proof-map":
            emit(write_proof_map(args.state, args.evidence, args.output))
        elif args.command == "telemetry":
            if args.action == "record":
                metrics = {key: getattr(args, key) for key in TELEMETRY_METRICS}
                emit(
                    telemetry_record(
                        args.state,
                        args.root,
                        args.plan,
                        args.phase,
                        args.at,
                        metrics,
                    )
                )
            else:
                emit(telemetry_summary(args.state, args.root))
        elif args.command == "status":
            summary_value = state_summary(args.state, args.root)
            if args.format == "text":
                print(render_status(summary_value), end="")
            else:
                emit(summary_value)
        return 0
    except BMError as error:
        print(str(error), file=sys.stderr)
        return error.exit_code
    except (OSError, UnicodeError, subprocess.SubprocessError, KeyError, TypeError, ValueError) as error:
        print(f"erro de entrada/IO: {error}", file=sys.stderr)
        return EXIT_INVALID


if __name__ == "__main__":
    raise SystemExit(main())
