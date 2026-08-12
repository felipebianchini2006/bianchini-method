#!/usr/bin/env python3
"""Primitivas determinísticas do Bianchini Method v2. Somente stdlib."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import unicodedata
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


def legacy_evidence(path: Path, repo: Path | None, text: str) -> bool:
    candidates: list[Path] = []
    if repo is not None:
        candidates.append(repo.resolve())
    for parent in (path.resolve().parent, *path.resolve().parents):
        if (parent / ".git").exists() or (parent / "docs/superpowers").exists():
            candidates.append(parent)
    if any(
        (candidate / "docs/superpowers").exists()
        or (candidate / ".superpowers/sdd").exists()
        for candidate in candidates
    ):
        return True
    return bool(re.search(r"(?i)\bdocs/superpowers/(?:v\d+|plans?|specs?)/", text))


def load_state(path: Path, repo: Path | None = None) -> dict[str, Any]:
    text = state_text(path)
    fenced = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    json_fence_present = bool(re.search(r"```json\b", text, re.IGNORECASE))
    candidate = fenced.group(1).strip() if fenced else text.strip()
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as error:
        if json_fence_present or candidate.startswith(("{", "[")):
            raise BMError(
                f"BLOQUEADO: PROJECT_STATE inválido: JSON corrompido na linha {error.lineno}",
                EXIT_BLOCKED,
            ) from error
        marker_values = re.findall(
            r"(?m)^\s*method_version:\s*(\d+)\s*(?:#.*)?$", text
        )
        markers = {int(match) for match in marker_values}
        if len(marker_values) > 1 or len(markers) > 1:
            raise BMError(
                "BLOQUEADO: PROJECT_STATE inválido: method_version duplicado ou conflitante",
                EXIT_BLOCKED,
            )
        if markers == {1}:
            return {"method_version": 1, "_legacy_text": text}
        if markers:
            raise BMError(
                "BLOQUEADO: estado v2 deve ser JSON válido; versão declarada não suportada",
                EXIT_BLOCKED,
            )
        if legacy_evidence(path, repo, text):
            return {"method_version": 1, "_implicit_legacy": True, "_legacy_text": text}
        raise BMError(
            "BLOQUEADO: não foi possível determinar method_version com segurança",
            EXIT_BLOCKED,
        )
    if not isinstance(value, dict):
        raise BMError("PROJECT_STATE deve ser um objeto")
    if "method_version" not in value:
        if legacy_evidence(path, repo, text):
            return {**value, "method_version": 1, "_implicit_legacy": True}
        raise BMError(
            "BLOQUEADO: não foi possível determinar method_version com segurança",
            EXIT_BLOCKED,
        )
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
        if any(
            state["planning"].get(field) is not None
            for field in ("research", "spec", "review")
        ):
            errors.append("state.planning: idle não pode apontar pesquisa, spec ou revisão")
        complexity = state.get("complexity_review")
        if complexity is not None and (
            complexity.get("decision") != "pending"
            or complexity.get("justification") is not None
            or complexity.get("deferred_scope") != []
            or complexity.get("scope_split_approved", False)
            or complexity.get("scope_split_approved_by") is not None
            or complexity.get("scope_split_approved_at") is not None
        ):
            errors.append("state.complexity_review: idle exige revisão pendente e vazia")
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
        if state["planning"].get("quality_version") == 1:
            if not state["planning"].get("research"):
                errors.append("state.planning.research: contrato de qualidade v1 exige pesquisa")
            if not isinstance(state.get("complexity_review"), dict):
                errors.append(
                    "state.complexity_review: contrato de qualidade v1 exige revisão de complexidade"
                )
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
        if state["planning"].get("research"):
            contract_files.add(state["planning"]["research"])
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
            state = load_state(state_path, repo)
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
    state = load_state(state_path, repo)
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
DIRECT_SCRATCH_ROOT = ".superpowers/bianchini/direct"
LEGACY_STATE_ARCHIVE = "docs/bianchini/legacy/transitions/PROJECT_STATE-v1-final.md"
IDLE_NEXT_ACTION = (
    "Aguardar novo escopo; então executar /sdd-planning para iniciar o ciclo v1 standalone."
)
LEGACY_COMPLETED_STATUSES = {
    "completed",
    "done",
    "delivered",
    "accepted",
    "concluido",
}
LEGACY_BLOCKING_STATUSES = {
    "in_progress",
    "pending",
    "active",
    "blocked",
    "em_andamento",
}


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


def path_uses_symlink(root: Path, target: Path) -> bool:
    current = root.resolve()
    for part in target.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


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
    migration_plan: list[dict[str, Any]] = []
    target_names: set[str] = set()
    for source_name in tracked:
        source_relative = Path(source_name)
        if not source_relative.parts or source_relative.parts[0] != ".superpowers":
            raise BMError(f"caminho Git inesperado: {source_name}")
        source_lexical = root / source_relative
        source = confined_path(root, source_name, "artefato raiz")
        if path_uses_symlink(root, source_lexical) or not source.is_file():
            raise BMError(f"artefato rastreado ausente ou não regular: {source_name}")
        relative_tail = Path(*source_relative.parts[1:])
        target_relative = Path(destination) / relative_tail
        target_lexical = root / target_relative
        target = confined_path(root, target_relative.as_posix(), "arquivo histórico")
        if target_relative.as_posix() in target_names:
            raise BMError(
                f"BLOQUEADO: destinos históricos duplicados: {target_relative}",
                EXIT_BLOCKED,
            )
        target_names.add(target_relative.as_posix())
        if path_uses_symlink(root, target_lexical):
            raise BMError(
                f"BLOQUEADO: destino histórico atravessa symlink: {target_relative}",
                EXIT_BLOCKED,
            )
        target_exists = target.exists()
        if target_exists:
            if (
                target.is_symlink()
                or not target.is_file()
                or target.read_bytes() != source.read_bytes()
                or (target.stat().st_mode & 0o111) != (source.stat().st_mode & 0o111)
            ):
                raise BMError(
                    f"BLOQUEADO: destino histórico já existe com conteúdo diferente: {target_relative}",
                    EXIT_BLOCKED,
                )
        missing_parents: list[Path] = []
        parent = target.parent
        while parent != root and not parent.exists():
            missing_parents.append(parent)
            parent = parent.parent
        migration_plan.append(
            {
                "source_name": source_name,
                "source": source,
                "source_bytes": source.read_bytes(),
                "source_mode": source.stat().st_mode,
                "target_relative": target_relative,
                "target": target,
                "target_exists": target_exists,
                "missing_parents": missing_parents,
            }
        )

    gitignore = root / ".gitignore"
    if (
        gitignore.is_symlink()
        or path_uses_symlink(root, gitignore)
        or (gitignore.exists() and not gitignore.is_file())
    ):
        raise BMError(
            "BLOQUEADO: .gitignore deve ser arquivo regular dentro do repositório",
            EXIT_BLOCKED,
        )
    original_gitignore = gitignore.read_bytes() if gitignore.exists() else None
    applied: list[dict[str, Any]] = []
    ignore_added = False
    try:
        for item in migration_plan:
            source = item["source"]
            target = item["target"]
            if item["target_exists"]:
                source.unlink()
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                source.replace(target)
            applied.append(item)
        ignore_added = ensure_versioned_superpowers_ignore(root)
        run_git(["add", "--", ".gitignore"], root)
        if tracked:
            run_git(["add", "-u", "--", ".superpowers"], root)
            run_git(["add", "--", destination], root)
        remaining = tracked_root_superpowers(root)
        if remaining:
            raise BMError(
                "migração não removeu todos os artefatos raiz: " + ", ".join(remaining)
            )
        repository_hygiene(root, False)
    except Exception as error:
        restored: list[str] = []
        rollback_errors: list[str] = []
        for item in reversed(applied):
            try:
                source = item["source"]
                target = item["target"]
                source.parent.mkdir(parents=True, exist_ok=True)
                if item["target_exists"]:
                    source.write_bytes(item["source_bytes"])
                    source.chmod(item["source_mode"])
                elif target.exists():
                    target.replace(source)
                restored.append(item["source_name"])
            except OSError as rollback_error:
                rollback_errors.append(f"{item['source_name']}: {rollback_error}")
        try:
            if original_gitignore is None:
                if gitignore.exists():
                    gitignore.unlink()
            else:
                gitignore.write_bytes(original_gitignore)
            subprocess.run(
                ["git", "reset", "-q", "HEAD", "--", ".gitignore", ".superpowers", destination],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
        except OSError as rollback_error:
            rollback_errors.append(f".gitignore/index: {rollback_error}")
        created_parents = {
            parent for item in migration_plan for parent in item["missing_parents"]
        }
        for parent in sorted(created_parents, key=lambda value: len(value.parts), reverse=True):
            try:
                parent.rmdir()
            except OSError:
                pass
        detail = f"restaurados: {', '.join(sorted(restored)) or 'nenhum movimento aplicado'}"
        if rollback_errors:
            detail += "; falhas de rollback: " + ", ".join(rollback_errors)
        raise BMError(
            f"BLOQUEADO: falha durante aplicação da higiene; {detail}; causa: {error}",
            EXIT_BLOCKED,
        ) from error

    moved = [
        {"from": item["source_name"], "to": item["target_relative"].as_posix()}
        for item in migration_plan
    ]
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
        "planning": {
            "quality_version": 1,
            "research_mode": None,
            "research": None,
            "spec": None,
            "review": None,
        },
        "complexity_review": {
            "decision": "pending",
            "justification": None,
            "deferred_scope": [],
            "scope_split_approved": False,
            "scope_split_approved_by": None,
            "scope_split_approved_at": None,
        },
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


def normalize_legacy_status(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip().lower())
    normalized = "".join(character for character in normalized if not unicodedata.combining(character))
    return re.sub(r"[\s-]+", "_", normalized.strip(" \t\r\n\"',;]}"))


def legacy_status_values(text: str) -> list[str]:
    values = re.findall(
        r"(?im)(?:^|[,{])[ \t]*(?:[-*][ \t]*)?[\"']?(?:[a-z][a-z0-9_]*_)?status[\"']?"
        r"[ \t]*:[ \t]*[\"']?([^\n,}\]]+)",
        text,
    )
    return [normalize_legacy_status(value) for value in values if value.strip()]


def legacy_completion_marker(text: str) -> dict[str, Any] | None:
    statuses = legacy_status_values(text)
    blocking = sorted(set(statuses) & LEGACY_BLOCKING_STATUSES)
    if blocking:
        raise BMError(
            "BLOQUEADO: estado legado ainda está " + ", ".join(blocking),
            EXIT_BLOCKED,
        )
    completed = sorted(set(statuses) & LEGACY_COMPLETED_STATUSES)
    if completed:
        return {"source": "legacy_state", "statuses": completed}
    return None


def validate_completion_proof(root: Path, proof: Path | None) -> dict[str, str]:
    if proof is None:
        raise BMError(
            "BLOQUEADO: estado legado sem marcador objetivo de conclusão; informe --completion-proof <arquivo>",
            EXIT_BLOCKED,
        )
    candidate = proof if proof.is_absolute() else root / proof
    lexical = candidate.absolute()
    resolved = candidate.resolve()
    try:
        relative = resolved.relative_to(root)
        lexical.relative_to(root)
    except ValueError as error:
        raise BMError("BLOQUEADO: completion proof deve ficar dentro do repositório", EXIT_BLOCKED) from error
    if candidate.is_symlink() or path_uses_symlink(root, lexical) or not resolved.is_file():
        raise BMError("BLOQUEADO: completion proof deve ser arquivo regular sem symlink", EXIT_BLOCKED)
    relative_name = relative.as_posix()
    try:
        tracked = run_git(["ls-files", "--error-unmatch", "--", relative_name], root)
        run_git(["cat-file", "-e", f"HEAD:{relative_name}"], root)
    except BMError as error:
        raise BMError(
            "BLOQUEADO: completion proof deve estar rastreado e commitado no HEAD",
            EXIT_BLOCKED,
        ) from error
    if tracked != relative_name:
        raise BMError(
            "BLOQUEADO: completion proof deve estar rastreado e commitado no HEAD",
            EXIT_BLOCKED,
        )
    proof_text = resolved.read_text(encoding="utf-8")
    evidence = re.search(
        r"(?i)\b(gates?|verification|verifica[cç][aã]o|delivery|entrega|accept(?:ed|ance)?|aceite)\b",
        proof_text,
    )
    outcome = re.search(
        r"(?i)\b(passed|completed|done|accepted|approved|conclu[ií]d[oa]|entregue|aprovad[oa])\b",
        proof_text,
    )
    if not evidence or not outcome:
        raise BMError(
            "BLOQUEADO: completion proof não registra gates, entrega ou aceite concluído",
            EXIT_BLOCKED,
        )
    return {"path": relative_name, "sha256": file_digest(resolved)}


def legacy_transition(
    repo: Path,
    state_path: Path,
    completed: bool,
    archive: str = LEGACY_STATE_ARCHIVE,
    completion_proof: Path | None = None,
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

    current = load_state(resolved_state, root)
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

    completion_evidence = legacy_completion_marker(state_text(resolved_state))
    proof_result: dict[str, str] | None = None
    if completion_evidence is None:
        proof_result = validate_completion_proof(root, completion_proof)
        completion_evidence = {"source": "completion_proof"}

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
    result = {
        "transitioned": True,
        "already_transitioned": False,
        "route": "v2-standalone",
        "planning_status": "idle",
        "planning_version": "v1",
        "state": state_relative.as_posix(),
        "legacy_archive": archive_path.relative_to(root).as_posix(),
        "staged": sorted(staged),
        "completion_evidence": completion_evidence,
        "next_action": IDLE_NEXT_ACTION,
    }
    if proof_result is not None:
        result["completion_proof"] = proof_result
    return result


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


PLANNING_LIMITS_BY_PROFILE = {
    "lean": {
        "plans": 7,
        "execution_units": 16,
        "platforms": 2,
        "shared_context_words": 8_000,
        "max_plan_words": 8_000,
        "max_execution_unit_words": 4_000,
    },
    "standard": {
        "plans": 16,
        "execution_units": 40,
        "platforms": 6,
        "shared_context_words": 24_000,
        "max_plan_words": 16_000,
        "max_execution_unit_words": 8_000,
    },
    "full": {
        "plans": 32,
        "execution_units": 80,
        "platforms": 12,
        "shared_context_words": 48_000,
        "max_plan_words": 32_000,
        "max_execution_unit_words": 16_000,
    },
}
PLANNING_PROFILES = ("lean", "standard", "full")
PLANNING_UNIT = re.compile(
    r"(?m)^###\s+(?:Tarefa|Task|Slice|Grupo|Group)\s+[^\n]+$",
    re.IGNORECASE,
)
PLANNING_PLACEHOLDER = re.compile(
    r"(?i)\b(?:TBD|TODO|FIXME|a definir|tratar erros|preencher depois)\b|"
    r"<(?:alvo|arquivo|comando|caminho|se[cç][aã]o|descri[cç][aã]o|id|nome)[^>]*>"
)
LEGACY_OPERATIONAL_REFERENCE = re.compile(
    r"(?i)(?:docs/superpowers|(?:^|/)inputs/|PLANO\s+Task|writing-plans|"
    r"Superpowers)"
)
NON_COMMAND_PREFIXES = {
    "aplicar",
    "confirmar",
    "executar",
    "revisar",
    "rodar",
    "testar",
    "validar",
    "verificar",
}
WEB_RESEARCH_HEADINGS = (
    "## Stack detectada",
    "## Fontes primárias",
    "## Decisões aplicadas",
    "## Alternativas rejeitadas",
    "## Riscos e lacunas",
)
REPO_RESEARCH_HEADINGS = (
    "## Stack detectada",
    "## Inventário local",
    "## Decisões aplicadas",
    "## Riscos e lacunas",
)
FULL_RESEARCH_HEADINGS = (
    "## Escopo da pesquisa",
    "## Decisões críticas",
)
RESEARCH_MODES = ("repo_only", "targeted_web", "full")
UNIT_FIELDS = (
    "Execution",
    "Review",
    "Test seams",
    "Spec refs",
    "Files",
    "Contract",
    "Verification",
    "Done when",
)


def word_count(content: str) -> int:
    return len(re.findall(r"\b[\wÀ-ÿ-]+\b", content, flags=re.UNICODE))


def planning_file(root: Path, value: Any, label: str) -> tuple[Path | None, str]:
    if not isinstance(value, str) or not value.strip():
        return None, ""
    target = confined_path(root, value, label)
    if not target.is_file():
        return target, ""
    return target, target.read_text(encoding="utf-8")


def exceeded_planning_limits(
    metrics: dict[str, int], limits: dict[str, int]
) -> list[str]:
    return [key for key, limit in limits.items() if metrics[key] > limit]


def recommended_planning_profile(
    metrics: dict[str, int], plans: list[dict[str, Any]]
) -> str:
    capacity_profile = "full"
    for profile in PLANNING_PROFILES:
        if not exceeded_planning_limits(metrics, PLANNING_LIMITS_BY_PROFILE[profile]):
            capacity_profile = profile
            break
    risks = {plan.get("risk") for plan in plans}
    critical_ids = {plan.get("id") for plan in plans if plan.get("risk") == "critical"}
    dependencies = {
        plan.get("id"): set(plan.get("depends_on", [])) for plan in plans
    }

    def depends_on_critical(plan_id: Any, seen: set[Any] | None = None) -> bool:
        visited = set() if seen is None else seen
        if plan_id in visited:
            return False
        visited.add(plan_id)
        for dependency in dependencies.get(plan_id, set()):
            if dependency in critical_ids:
                return True
            if depends_on_critical(dependency, visited):
                return True
        return False

    interdependent_critical = len(critical_ids) > 1 and any(
        depends_on_critical(plan_id) for plan_id in critical_ids
    )
    if interdependent_critical:
        risk_profile = "full"
    elif risks & {"medium", "high", "critical"}:
        risk_profile = "standard"
    else:
        risk_profile = "lean"
    return PLANNING_PROFILES[
        max(PLANNING_PROFILES.index(capacity_profile), PLANNING_PROFILES.index(risk_profile))
    ]


def planning_audit(state_path: Path, root: Path, strict: bool) -> dict[str, Any]:
    state = validate_state(state_path)
    quality_enabled = state.get("planning", {}).get("quality_version") == 1
    enforced = strict or quality_enabled
    errors: list[str] = []
    warnings: list[str] = []
    if state["planning_status"] == "idle":
        if enforced:
            raise BMError("planejamento inválido:\n- ciclo idle ainda não possui pacote auditável")
        limits = PLANNING_LIMITS_BY_PROFILE[state["assurance_profile"]]
        return {
            "valid": True,
            "quality_contract": "legacy-compatible",
            "profile": state["assurance_profile"],
            "recommended_profile": "lean",
            "metrics": {**{key: 0 for key in limits}, "package_words": 0},
            "limits": limits,
            "warnings": [],
        }

    package_files = set(state["approval"]["package"]["files"])
    research_value = state["planning"].get("research")
    research_mode = state["planning"].get("research_mode")
    inferred_legacy_research_mode = False
    spec_value = state["planning"].get("spec")
    review_value = state["planning"].get("review")
    plan_values = [plan["path"] for plan in state["plans"]]
    contract_values = [research_value, spec_value, review_value, *plan_values]
    if enforced:
        if not quality_enabled:
            errors.append("planning.quality_version: esperado 1 para novo planejamento")
        if research_mode is not None and research_mode not in RESEARCH_MODES:
            errors.append(
                "planning.research_mode: esperado repo_only, targeted_web ou full"
            )
        for value in contract_values:
            if not isinstance(value, str) or not value:
                errors.append("pacote: pesquisa, spec, revisão e planos devem ter caminhos locais")
            elif value not in package_files:
                errors.append(f"pacote: artefato contratual ausente do manifesto: {value}")

    research_path, research = planning_file(root, research_value, "planning.research")
    if enforced:
        if research_path is None or not research:
            errors.append("pesquisa: STACK_RESEARCH.md local é obrigatório")
        else:
            if research_mode is None and state["approval"]["status"] == "approved":
                research_mode = (
                    "targeted_web"
                    if "https://" in research and "Fonte primária:" in research
                    else "repo_only"
                )
                inferred_legacy_research_mode = True
                warnings.append(
                    "planning.research_mode ausente em pacote aprovado anterior; "
                    f"inferido como {research_mode} somente para compatibilidade"
                )
            elif research_mode is None:
                errors.append(
                    "planning.research_mode: esperado repo_only, targeted_web ou full"
                )
            if not inferred_legacy_research_mode:
                declared_mode = re.search(r"(?mi)^Research mode:\s*(\S+)\s*$", research)
                if not declared_mode or declared_mode.group(1) != research_mode:
                    errors.append("pesquisa: Research mode deve coincidir com planning.research_mode")
                if not re.search(r"(?mi)^Motivo:\s*\S", research):
                    errors.append("pesquisa: registre Motivo para o menor modo suficiente")
            if research_mode == "repo_only":
                for heading in REPO_RESEARCH_HEADINGS:
                    if heading not in research:
                        errors.append(f"pesquisa: seção obrigatória ausente: {heading}")
                for field in ("Manifests:", "Lockfiles:", "CI:", "Testes:", "Padrões locais:"):
                    if field not in research:
                        errors.append(f"pesquisa repo_only: inventário ausente: {field}")
            elif research_mode in {"targeted_web", "full"}:
                for heading in WEB_RESEARCH_HEADINGS:
                    if heading not in research:
                        errors.append(f"pesquisa: seção obrigatória ausente: {heading}")
                if "https://" not in research:
                    errors.append("pesquisa: ao menos uma URL HTTPS de fonte primária é obrigatória")
                if "Fonte primária:" not in research:
                    errors.append("pesquisa: classifique explicitamente cada referência como Fonte primária")
                if not re.search(r"(?i)Acessado em:\s*\d{4}-\d{2}-\d{2}", research):
                    errors.append("pesquisa: registre Acessado em: YYYY-MM-DD")
                if research_mode == "full":
                    for heading in FULL_RESEARCH_HEADINGS:
                        if heading not in research:
                            errors.append(
                                f"pesquisa: seção obrigatória do modo full ausente: {heading}"
                            )

    shared_context = ""
    for value, label in (
        (research_value, "planning.research"),
        (spec_value, "planning.spec"),
        (review_value, "planning.review"),
    ):
        path, content = planning_file(root, value, label)
        if enforced and (path is None or not content):
            errors.append(f"{label}: arquivo ausente ou vazio")
        if content and label == "planning.spec":
            shared_context = content

    unit_count = 0
    plan_words: list[int] = []
    execution_unit_words: list[int] = []
    for plan in state["plans"]:
        path, content = planning_file(root, plan["path"], f"plan {plan['id']}")
        if enforced and (path is None or not content):
            errors.append(f"plano {plan['id']}: arquivo ausente ou vazio")
            continue
        if not content:
            continue
        plan_words.append(word_count(content))
        matches = list(PLANNING_UNIT.finditer(content))
        unit_count += len(matches)
        if enforced and not matches:
            errors.append(f"plano {plan['id']}: nenhuma unidade executável encontrada")
        if enforced and PLANNING_PLACEHOLDER.search(content):
            errors.append(f"plano {plan['id']}: placeholder ou instrução vaga")
        if enforced and LEGACY_OPERATIONAL_REFERENCE.search(content):
            errors.append(
                f"plano {plan['id']}: referência operacional a fonte bruta/legado"
            )
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
            section = content[match.start():end]
            execution_unit_words.append(word_count(section))
            for field in UNIT_FIELDS:
                if not re.search(rf"(?mi)^\*\*{re.escape(field)}:\*\*\s*\S", section):
                    errors.append(
                        f"plano {plan['id']} / {match.group(0).strip()}: campo {field} ausente"
                    )
        title_lines = "\n".join(match.group(0) for match in matches)
        if re.search(r"(?i)\b(?:baseline|lint|setup)\b", title_lines):
            warnings.append(
                f"plano {plan['id']}: confirme que baseline/lint/setup foi incorporado à primeira entrega real"
            )
        if re.search(r"(?i)\b(?:homologa[cç][aã]o|evid[eê]ncias? de release)\b", title_lines):
            warnings.append(
                f"plano {plan['id']}: possível duplicação do gate homologar-sistema"
            )

    if enforced:
        for stage, stage_value in state["verification"].items():
            commands = stage_value.get("commands", [])
            if not commands:
                errors.append(f"verification.{stage}: informe ao menos um comando real")
            for command in commands:
                first = command.strip().split(maxsplit=1)[0].lower() if command.strip() else ""
                if not first or PLANNING_PLACEHOLDER.search(command):
                    errors.append(f"verification.{stage}: comando vazio, vago ou com placeholder")
                elif first in NON_COMMAND_PREFIXES:
                    errors.append(
                        f"verification.{stage}: procedimento em prosa não é comando reproduzível: {command}"
                    )

    package_words = 0
    for value in package_files:
        _, content = planning_file(root, value, "approval.package.files")
        package_words += word_count(content)
    metrics = {
        "plans": len(state["plans"]),
        "execution_units": unit_count,
        "platforms": len(state.get("release", {}).get("platforms", [])),
        "shared_context_words": word_count(shared_context),
        "max_plan_words": max(plan_words, default=0),
        "max_execution_unit_words": max(execution_unit_words, default=0),
        "package_words": package_words,
    }
    profile = state["assurance_profile"]
    if profile == "lean" and metrics["plans"] > 4:
        warnings.append(
            "perfil lean acima da faixa típica de 1–4 planos; 7 é teto, não meta"
        )
    limits = PLANNING_LIMITS_BY_PROFILE[profile]
    exceeded = exceeded_planning_limits(metrics, limits)
    recommended_profile = recommended_planning_profile(metrics, state["plans"])
    complexity = state.get("complexity_review")
    if enforced:
        if not isinstance(complexity, dict):
            errors.append("complexity_review: revisão obrigatória ausente")
        else:
            decision = complexity.get("decision")
            justification = (complexity.get("justification") or "").strip()
            deferred = complexity.get("deferred_scope") or []
            split_approved = complexity.get("scope_split_approved") is True
            split_approved_by = (complexity.get("scope_split_approved_by") or "").strip()
            split_approved_at = complexity.get("scope_split_approved_at") or ""

            if deferred:
                if decision != "split":
                    errors.append(
                        "complexity_review: deferred_scope exige decision split"
                    )
                if not (
                    split_approved
                    and split_approved_by
                    and re.match(r"^\d{4}-\d{2}-\d{2}T", split_approved_at)
                ):
                    errors.append(
                        "complexity_review: escopo aprovado não pode ser adiado para caber no orçamento; "
                        "split exige autorização explícita do responsável com autor e horário"
                    )
            elif decision == "split":
                errors.append(
                    "complexity_review.deferred_scope: split exige escopo adiado autorizado"
                )
            elif split_approved or split_approved_by or split_approved_at:
                errors.append(
                    "complexity_review: autorização de split não pode permanecer sem deferred_scope"
                )
            if PLANNING_PROFILES.index(profile) < PLANNING_PROFILES.index(
                recommended_profile
            ):
                errors.append(
                    f"assurance_profile {profile}: insuficiente para risco/capacidade; "
                    f"preserve todo o escopo e escale para {recommended_profile}"
                )
            if exceeded:
                if profile == "full" and (
                    decision not in {"indivisible", "split"}
                    or len(justification) < 40
                ):
                    errors.append(
                        "complexity_review: perfil full acima da faixa exige justificativa "
                        "de indivisibilidade em 40+ caracteres; nunca reduza escopo automaticamente"
                    )
            elif decision not in {"within_budget", "split"}:
                errors.append(
                    "complexity_review.decision: use within_budget ou split dentro do orçamento"
                )

    if errors:
        raise BMError("planejamento inválido:\n- " + "\n- ".join(dict.fromkeys(errors)))
    return {
        "valid": True,
        "quality_contract": "planning-quality-v1" if quality_enabled else "legacy-compatible",
        "profile": profile,
        "recommended_profile": recommended_profile,
        "research_mode": research_mode,
        "metrics": metrics,
        "limits": limits,
        "budget_exceeded": exceeded,
        "warnings": sorted(set(warnings)),
    }


def snapshot(state_path: Path, root: Path, verify: bool) -> dict[str, Any]:
    state = validate_state(state_path)
    if state.get("planning", {}).get("quality_version") == 1:
        planning_audit(state_path, root, strict=True)
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
    state_value = load_state(state, cwd)
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


DIRECT_HAZARDS = {
    "new-auth",
    "new-payment",
    "webhook",
    "multi-tenant",
    "rls",
    "data-migration",
    "sensitive-infra",
    "secrets-iam",
    "concurrency",
    "offline-sync",
    "critical-geolocation",
    "destructive",
    "new-architecture",
    "multi-platform-differences",
    "ambiguous-business-rule",
}
DIRECT_RED_GREEN_KINDS = {
    "bug",
    "business-rule",
    "calculation",
    "data-transform",
    "parser",
    "permission",
    "state-machine",
}


def direct_repo(repo: Path) -> Path:
    root = repo.resolve()
    top = Path(run_git(["rev-parse", "--show-toplevel"], root)).resolve()
    if top != root:
        raise BMError(f"--repo deve apontar para a raiz Git: {top}")
    return root


def direct_slug(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", value):
        raise BMError("slug inválido; use letras minúsculas, números e hífens")
    return value


def direct_directory(root: Path, slug: str) -> Path:
    normalized = direct_slug(slug)
    lexical = root / DIRECT_SCRATCH_ROOT / normalized
    target = confined_path(root, f"{DIRECT_SCRATCH_ROOT}/{normalized}", "scratch direto")
    if path_uses_symlink(root, lexical):
        raise BMError("scratch direto não pode atravessar symlink")
    return target


def direct_state_path(root: Path, slug: str) -> Path:
    return direct_directory(root, slug) / ".state.json"


def read_direct_state(root: Path, slug: str) -> dict[str, Any]:
    path = direct_state_path(root, slug)
    if path.is_symlink() or not path.is_file():
        raise BMError(f"execução direta não encontrada: {slug}", EXIT_BLOCKED)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise BMError(f"estado da execução direta inválido: {error.msg}", EXIT_BLOCKED) from error
    if not isinstance(value, dict) or value.get("mode") not in {"direct", "escalated"}:
        raise BMError("estado da execução direta inválido", EXIT_BLOCKED)
    return value


def write_direct_state(root: Path, state: dict[str, Any]) -> Path:
    directory = direct_directory(root, state["slug"])
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / ".state.json"
    temporary = directory / ".state.json.tmp"
    temporary.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)
    return path


def markdown_list(values: list[str], empty: str = "Nenhum.") -> str:
    return "\n".join(f"- {value}" for value in values) if values else f"- {empty}"


def render_direct_brief(state: dict[str, Any]) -> str:
    return (
        "# Brief da execução direta\n\n"
        f"## Objetivo\n\n{state['objective']}\n\n"
        f"## Estado atual relevante\n\n{state['current_state']}\n\n"
        f"## Escopo\n\n{state['scope']}\n\n"
        "## Não objetivos\n\n"
        f"{markdown_list(state['non_objectives'])}\n\n"
        "## Critérios de aceite\n\n"
        f"{markdown_list(state['acceptance'])}\n\n"
        "## Arquivos e interfaces prováveis\n\n"
        f"{markdown_list(state['likely_files'], 'A confirmar pela leitura localizada.')}\n\n"
        f"## Risco inicial\n\n{state['risk']}\n\n"
        "## Comandos de verificação\n\n"
        f"{markdown_list(state['verification_commands'])}\n\n"
        f"## Branch\n\n`{state['branch']}`\n\n"
        f"## Commit base\n\n`{state['base_commit']}`\n"
    )


def render_direct_progress(state: dict[str, Any]) -> str:
    return (
        "# Progresso da execução direta\n\n"
        f"- Objetivo: {state['objective']}\n"
        f"- Branch: `{state['branch']}`\n"
        f"- Commit base: `{state['base_commit']}`\n"
        f"- Último checkpoint concluído: {state['last_checkpoint'] or 'nenhum'}\n"
        f"- Verificação atual: {state['verification']}\n"
        f"- Próxima ação: {state['next_action']}\n\n"
        "## Arquivos alterados\n\n"
        f"{markdown_list(state['changed_files'])}\n\n"
        "## Comandos executados\n\n"
        f"{markdown_list(state['commands'])}\n\n"
        "## Resultados\n\n"
        f"{markdown_list(state['results'])}\n\n"
        "## Bloqueios\n\n"
        f"{markdown_list(state['blockers'])}\n"
    )


def render_direct_result(state: dict[str, Any]) -> str:
    status_label = {
        "active": "em andamento",
        "completed": "concluído",
        "blocked": "bloqueado",
        "escalated": "escalado",
    }[state["status"]]
    return (
        "# Resultado da execução direta\n\n"
        f"## Objetivo\n\n{state['objective']}\n\n"
        f"Status: {status_label}\n\n"
        f"## Estado atual confirmado\n\n{state['current_state']}\n\n"
        f"## Escopo e decisão de risco\n\n{state['scope']}\n\n"
        f"- Risco: {state['risk']}\n"
        f"- Hazards: {', '.join(state['hazards']) if state['hazards'] else 'nenhum'}\n\n"
        "## Fatos confirmados\n\n"
        f"{markdown_list(state['results'])}\n\n"
        "## Comportamentos implementados\n\n"
        f"{markdown_list(state['behaviors'])}\n\n"
        "## Arquivos alterados\n\n"
        f"{markdown_list(state['changed_files'])}\n\n"
        "## Comandos executados\n\n"
        f"{markdown_list(state['commands'])}\n\n"
        "## Resultados das verificações\n\n"
        f"{markdown_list(state['verification_results'])}\n\n"
        "## Limitações\n\n"
        f"{markdown_list(state['limitations'])}\n\n"
        "## Itens fora de escopo encontrados\n\n"
        f"{markdown_list(state['out_of_scope'])}\n\n"
        "## Bloqueios\n\n"
        f"{markdown_list(state['blockers'])}\n\n"
        "## Branch e estado Git\n\n"
        f"- Branch: `{state['branch']}`\n- Commit base: `{state['base_commit']}`\n"
        f"- Estado: {state.get('git_status', 'unknown')}\n\n"
        f"## Próximo passo\n\n{state['next_action']}\n"
    )


def direct_payload(state: dict[str, Any], directory: Path) -> dict[str, Any]:
    return {
        "mode": state["mode"],
        "slug": state["slug"],
        "objective": state["objective"],
        "status": state["status"],
        "risk": state["risk"],
        "verification_strategy": state["verification_strategy"],
        "branch": state["branch"],
        "base_commit": state["base_commit"],
        "last_checkpoint": state["last_checkpoint"],
        "verification": state["verification"],
        "blockers": state["blockers"],
        "next_action": state["next_action"],
        "git_status": state.get("git_status", "unknown"),
        "brief": str(directory / "BRIEF.md"),
        "progress": str(directory / "PROGRESS.md"),
        "result": str(directory / "RESULT.md"),
        "next_step": "/sdd-planning" if state["mode"] == "escalated" else None,
    }


def direct_git_status(root: Path) -> tuple[str, list[str]]:
    lines = run_git(
        ["status", "--porcelain=v1", "--untracked-files=all"], root
    ).splitlines()
    paths = sorted(
        {line[3:].split(" -> ")[-1] for line in lines if len(line) > 3}
    )
    return ("clean" if not paths else "modified", paths)


def direct_base_is_ancestor(root: Path, base_commit: str) -> bool:
    completed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", base_commit, "HEAD"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode not in {0, 1}:
        raise BMError(completed.stderr.strip() or "não foi possível validar o commit base")
    return completed.returncode == 0


def direct_start(
    repo: Path,
    slug: str,
    objective: str,
    scope: str,
    current_state: str,
    acceptance: list[str],
    non_objectives: list[str],
    likely_files: list[str],
    verification_commands: list[str],
    risk: str,
    change_kind: str,
    hazards: list[str],
    subsystems: int,
    related_changes: list[str],
    initial_commands: list[str],
    initial_results: list[str],
) -> dict[str, Any]:
    root = direct_repo(repo)
    directory = direct_directory(root, slug)
    branch = run_git(["branch", "--show-current"], root)
    if not branch:
        raise BMError("BLOQUEADO: executar-direto não funciona em detached HEAD", EXIT_UNSAFE_WORKSPACE)
    base_commit = run_git(["rev-parse", "HEAD"], root)
    unknown_hazards = sorted(set(hazards) - DIRECT_HAZARDS)
    if unknown_hazards:
        raise BMError("hazard inválido: " + ", ".join(unknown_hazards))
    escalation_reasons = sorted(set(hazards))
    if risk in {"high", "critical"}:
        escalation_reasons.append(f"risk:{risk}")
    if subsystems > 1:
        escalation_reasons.append(f"independent-subsystems:{subsystems}")
    mode = "escalated" if escalation_reasons else "direct"

    existing_path = directory / ".state.json"
    if existing_path.is_file():
        existing = read_direct_state(root, slug)
        if existing.get("objective") != objective:
            raise BMError("BLOQUEADO: slug já pertence a outro objetivo", EXIT_BLOCKED)
        ensure_direct_branch(root, existing)
        git_state, observed_paths = direct_git_status(root)
        existing["git_status"] = git_state
        existing["observed_changes"] = observed_paths
        return {**direct_payload(existing, directory), "resumed": True}

    _, observed_dirty_paths = direct_git_status(root)
    dirty_paths = set(observed_dirty_paths)
    recognized = set(related_changes)
    if dirty_paths - recognized:
        raise BMError(
            "BLOQUEADO: alterações não relacionadas não foram reconhecidas no brief: "
            + ", ".join(sorted(dirty_paths - recognized)),
            EXIT_BLOCKED,
        )

    target_branch = branch
    if mode == "direct" and branch in {"main", "master"}:
        target_branch = f"bm/direct/{slug}"
        if run_git(["branch", "--list", target_branch], root):
            raise BMError(f"BLOQUEADO: branch direta já existe: {target_branch}", EXIT_BLOCKED)
        run_git(["switch", "-c", target_branch], root)

    if change_kind in DIRECT_RED_GREEN_KINDS:
        strategy = "red_green"
    elif change_kind == "visual":
        strategy = "visual_evidence"
    else:
        strategy = "affected_checks"
    timestamp = datetime.now(timezone.utc).isoformat()
    state: dict[str, Any] = {
        "version": 1,
        "mode": mode,
        "slug": slug,
        "objective": objective,
        "scope": scope,
        "current_state": current_state,
        "acceptance": acceptance,
        "non_objectives": non_objectives,
        "likely_files": likely_files,
        "verification_commands": verification_commands,
        "risk": risk,
        "change_kind": change_kind,
        "verification_strategy": strategy,
        "hazards": escalation_reasons,
        "subsystems": subsystems,
        "branch": target_branch,
        "base_commit": base_commit,
        "status": "escalated" if mode == "escalated" else "active",
        "last_checkpoint": None,
        "changed_files": sorted(recognized),
        "commands": initial_commands,
        "results": initial_results,
        "verification": "pending",
        "verification_results": [],
        "behaviors": [],
        "limitations": [],
        "out_of_scope": [],
        "blockers": escalation_reasons,
        "git_status": "clean" if not dirty_paths else "modified",
        "next_action": (
            "Executar /sdd-planning com este handoff compacto."
            if mode == "escalated"
            else "Implementar a menor sequência coerente e registrar checkpoint relevante."
        ),
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    write_direct_state(root, state)
    (directory / "BRIEF.md").write_text(render_direct_brief(state), encoding="utf-8")
    (directory / "PROGRESS.md").write_text(render_direct_progress(state), encoding="utf-8")
    (directory / "RESULT.md").write_text(render_direct_result(state), encoding="utf-8")
    return {**direct_payload(state, directory), "resumed": False}


def direct_status(repo: Path, slug: str | None) -> dict[str, Any]:
    root = direct_repo(repo)
    if slug:
        state = read_direct_state(root, slug)
        if state["status"] == "active":
            ensure_direct_branch(root, state)
        git_state, observed_paths = direct_git_status(root)
        state["git_status"] = git_state
        result = direct_payload(state, direct_directory(root, slug))
        result["observed_changes"] = observed_paths
        result["unrecorded_changes"] = sorted(
            set(observed_paths) - set(state["changed_files"])
        )
        return result
    base = confined_path(root, DIRECT_SCRATCH_ROOT, "scratch direto")
    if path_uses_symlink(root, root / DIRECT_SCRATCH_ROOT):
        raise BMError("scratch direto não pode atravessar symlink")
    if not base.is_dir():
        return {"mode": "none", "active": False, "executions": []}
    executions: list[dict[str, Any]] = []
    for child in sorted(base.iterdir(), key=lambda item: item.name):
        if child.is_dir() and not child.is_symlink() and (child / ".state.json").is_file():
            state = read_direct_state(root, child.name)
            executions.append(direct_payload(state, child))
    active = [item for item in executions if item["status"] == "active"]
    if len(active) == 1:
        return {**active[0], "active": True, "executions": executions}
    return {"mode": "direct" if active else "none", "active": bool(active), "executions": executions}


def ensure_direct_branch(root: Path, state: dict[str, Any]) -> None:
    current = run_git(["branch", "--show-current"], root)
    if not current:
        raise BMError("BLOQUEADO: execução direta em detached HEAD", EXIT_UNSAFE_WORKSPACE)
    if state["mode"] == "direct" and current != state["branch"]:
        raise BMError(
            f"BLOQUEADO: execução direta pertence à branch {state['branch']}, atual {current}",
            EXIT_UNSAFE_WORKSPACE,
        )
    if state["mode"] == "direct" and not direct_base_is_ancestor(
        root, state["base_commit"]
    ):
        raise BMError(
            "BLOQUEADO: commit base da execução direta não pertence mais ao HEAD atual",
            EXIT_UNSAFE_WORKSPACE,
        )


def direct_checkpoint(
    repo: Path,
    slug: str,
    checkpoint: str,
    changed_files: list[str],
    commands: list[str],
    results: list[str],
    verification: str,
    next_action: str,
    blockers: list[str],
) -> dict[str, Any]:
    root = direct_repo(repo)
    state = read_direct_state(root, slug)
    ensure_direct_branch(root, state)
    if state["status"] != "active":
        raise BMError("BLOQUEADO: somente execução direta ativa aceita checkpoint", EXIT_BLOCKED)
    state["last_checkpoint"] = checkpoint
    state["changed_files"] = sorted(set(state["changed_files"] + changed_files))
    state["commands"] = state["commands"] + commands
    state["results"] = state["results"] + results
    state["verification"] = verification
    state["next_action"] = next_action
    state["blockers"] = blockers
    state["git_status"], _ = direct_git_status(root)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    directory = direct_directory(root, slug)
    write_direct_state(root, state)
    (directory / "PROGRESS.md").write_text(render_direct_progress(state), encoding="utf-8")
    return direct_payload(state, directory)


def direct_finish(
    repo: Path,
    slug: str,
    status: str,
    behaviors: list[str],
    verification_results: list[str],
    limitations: list[str],
    out_of_scope: list[str],
    next_action: str,
) -> dict[str, Any]:
    root = direct_repo(repo)
    state = read_direct_state(root, slug)
    ensure_direct_branch(root, state)
    state["status"] = status
    if status == "escalated":
        state["mode"] = "escalated"
    state["behaviors"] = behaviors
    state["verification_results"] = verification_results
    state["limitations"] = limitations
    state["out_of_scope"] = out_of_scope
    state["next_action"] = next_action
    state["git_status"], _ = direct_git_status(root)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    directory = direct_directory(root, slug)
    write_direct_state(root, state)
    (directory / "PROGRESS.md").write_text(render_direct_progress(state), encoding="utf-8")
    (directory / "RESULT.md").write_text(render_direct_result(state), encoding="utf-8")
    return direct_payload(state, directory)


def state_summary(path: Path, root: Path | None = None) -> dict[str, Any]:
    state = load_state(path, root)
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
    transition.add_argument("--completion-proof", type=Path)
    transition.add_argument("--archive", default=LEGACY_STATE_ARCHIVE)

    snap = commands.add_parser("snapshot")
    snap.add_argument("action", choices=["create", "verify"])
    snap.add_argument("state", type=Path)
    snap.add_argument("--root", type=Path, required=True)

    planning_check = commands.add_parser("planning-audit")
    planning_check.add_argument("state", type=Path)
    planning_check.add_argument("--root", type=Path, required=True)
    planning_check.add_argument("--strict", action="store_true")

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

    direct = commands.add_parser("direct")
    direct.add_argument("action", choices=["start", "status", "checkpoint", "finish"])
    direct.add_argument("--repo", type=Path, default=Path.cwd())
    direct.add_argument("--slug")
    direct.add_argument("--objective")
    direct.add_argument("--scope")
    direct.add_argument("--current-state", default="Arquitetura existente a confirmar por leitura localizada.")
    direct.add_argument("--acceptance", action="append", default=[])
    direct.add_argument("--non-objective", action="append", default=[])
    direct.add_argument("--likely-file", action="append", default=[])
    direct.add_argument("--verification", action="append", default=[])
    direct.add_argument(
        "--risk", choices=["low", "medium", "high", "critical"], default="low"
    )
    direct.add_argument(
        "--change-kind",
        choices=[
            "behavioral",
            "mechanical",
            "visual",
            "bug",
            "business-rule",
            "calculation",
            "data-transform",
            "parser",
            "permission",
            "state-machine",
        ],
        default="behavioral",
    )
    direct.add_argument("--hazard", action="append", default=[])
    direct.add_argument("--subsystems", type=int, default=1)
    direct.add_argument("--related-change", action="append", default=[])
    direct.add_argument("--checkpoint")
    direct.add_argument("--changed-file", action="append", default=[])
    direct.add_argument(
        "--command",
        dest="executed_commands",
        metavar="COMMAND",
        action="append",
        default=[],
    )
    direct.add_argument("--result-entry", action="append", default=[])
    direct.add_argument("--blocker", action="append", default=[])
    direct.add_argument("--next-action")
    direct.add_argument(
        "--status", choices=["completed", "blocked", "escalated"]
    )
    direct.add_argument("--behavior", action="append", default=[])
    direct.add_argument("--limitation", action="append", default=[])
    direct.add_argument("--out-of-scope", action="append", default=[])

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
                args.completion_proof,
            )
            )
        elif args.command == "snapshot":
            emit(snapshot(args.state, args.root, args.action == "verify"))
        elif args.command == "planning-audit":
            emit(planning_audit(args.state, args.root, args.strict))
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
        elif args.command == "direct":
            if args.action == "start":
                if not all((args.slug, args.objective, args.scope)):
                    raise BMError("direct start exige --slug, --objective e --scope")
                if not args.acceptance or not args.verification:
                    raise BMError(
                        "direct start exige ao menos um --acceptance e um --verification"
                    )
                if args.subsystems < 1:
                    raise BMError("--subsystems deve ser positivo")
                emit(
                    direct_start(
                        args.repo,
                        args.slug,
                        args.objective,
                        args.scope,
                        args.current_state,
                        args.acceptance,
                        args.non_objective,
                        args.likely_file,
                        args.verification,
                        args.risk,
                        args.change_kind,
                        args.hazard,
                        args.subsystems,
                        args.related_change,
                        args.executed_commands,
                        args.result_entry,
                    )
                )
            elif args.action == "status":
                emit(direct_status(args.repo, args.slug))
            elif args.action == "checkpoint":
                if not all((args.slug, args.checkpoint, args.next_action)):
                    raise BMError(
                        "direct checkpoint exige --slug, --checkpoint e --next-action"
                    )
                emit(
                    direct_checkpoint(
                        args.repo,
                        args.slug,
                        args.checkpoint,
                        args.changed_file,
                        args.executed_commands,
                        args.result_entry,
                        args.verification[0] if args.verification else "pending",
                        args.next_action,
                        args.blocker,
                    )
                )
            else:
                if not all((args.slug, args.status, args.next_action)):
                    raise BMError("direct finish exige --slug, --status e --next-action")
                emit(
                    direct_finish(
                        args.repo,
                        args.slug,
                        args.status,
                        args.behavior,
                        args.verification,
                        args.limitation,
                        args.out_of_scope,
                        args.next_action,
                    )
                )
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
