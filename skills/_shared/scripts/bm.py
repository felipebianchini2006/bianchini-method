#!/usr/bin/env python3
"""Primitivas determinísticas do Bianchini Method 0.4. Somente stdlib."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from bm_context import (
    QUALITY_V2_UNIT_FIELDS,
    hydrate_task_context,
    mutation_mode_for_change,
    validate_quality_v2_plan,
)
from bm_feature_support import FIX_ROUNDS_BY_PROFILE
from bm_mutation import mutation_evidence_verify
from bm_spec_diff import spec_diff
from bm_update import (
    UpdateError as BMUpdateError,
    render_update_result,
    update_bianchini_method,
)
import bm_v04_workflows as v04
import bm_v04_planning as v04_planning


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
    if isinstance(value, int) and not isinstance(value, bool):
        if "minimum" in rule and value < rule["minimum"]:
            errors.append(f"{at}: menor que minimum {rule['minimum']}")
        if "maximum" in rule and value > rule["maximum"]:
            errors.append(f"{at}: maior que maximum {rule['maximum']}")
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
            for field in (
                "research",
                "readiness",
                "user_actions",
                "spec",
                "review",
                "checker",
                "design_manifest",
                "change_root",
            )
        ):
            errors.append(
                "state.planning: idle não pode apontar pesquisa, readiness, spec, revisão ou mudança"
            )
        current_specs = state["planning"].get("current_specs")
        if current_specs is not None and (
            not isinstance(current_specs, str) or not current_specs.strip()
        ):
            errors.append("state.planning.current_specs: idle exige caminho válido ou null")
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
        quality_version = state["planning"].get("quality_version")
        if quality_version in {1, 2}:
            if not state["planning"].get("research"):
                errors.append(
                    f"state.planning.research: contrato de qualidade v{quality_version} exige pesquisa"
                )
            if not isinstance(state.get("complexity_review"), dict):
                errors.append(
                    f"state.complexity_review: contrato de qualidade v{quality_version} exige revisão de complexidade"
                )
        if quality_version == 2:
            for field in ("readiness", "user_actions", "change_root", "current_specs"):
                if not isinstance(state["planning"].get(field), str) or not state[
                    "planning"
                ][field].strip():
                    errors.append(f"state.planning.{field}: contrato de qualidade v2 exige caminho")
            checker = state["planning"].get("checker")
            if not isinstance(checker, dict):
                errors.append("state.planning.checker: contrato de qualidade v2 exige objeto")
            elif state["approval"]["status"] == "approved":
                if checker.get("status") != "passed":
                    errors.append("state.planning.checker.status: aprovação exige passed")
                if checker.get("rounds") not in {1, 2}:
                    errors.append("state.planning.checker.rounds: aprovação exige 1 ou 2")
                for digest_field in ("package_digest", "report_digest"):
                    digest_value = checker.get(digest_field)
                    if not isinstance(digest_value, str) or not re.fullmatch(
                        r"[0-9a-f]{64}", digest_value
                    ):
                        errors.append(
                            f"state.planning.checker.{digest_field}: aprovação exige digest válido"
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
        if state["planning"].get("quality_version") == 2:
            for field in ("readiness", "user_actions", "design_manifest"):
                value = state["planning"].get(field)
                if value:
                    contract_files.add(value)
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


def reject_symlink_chain(root: Path, path: Path, label: str) -> None:
    base = root.resolve()
    candidate = path if path.is_absolute() else base / path
    # macOS pode expor o mesmo diretório lexicalmente por /var e /private/var.
    # Resolva o pai existente antes de comparar, mas preserve o último nome para
    # ainda detectar o próprio alvo quando ele for um symlink.
    candidate_parent = candidate.parent.resolve()
    candidate = candidate_parent / candidate.name
    try:
        relative = candidate.absolute().relative_to(base)
    except ValueError as error:
        raise BMError(f"{label} fora da raiz: {candidate}") from error
    current = base
    for part in relative.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise BMError(f"{label} contém symlink: {current}", EXIT_BLOCKED)


def reject_tree_symlinks(root: Path, directory: Path, label: str) -> None:
    base = root.resolve()
    candidate = directory if directory.is_absolute() else base / directory
    reject_symlink_chain(base, candidate, label)
    if not candidate.exists():
        return
    if not candidate.is_dir():
        raise BMError(f"{label} deve ser diretório: {candidate}", EXIT_BLOCKED)
    for current, directories, files in os.walk(candidate, followlinks=False):
        current_path = Path(current)
        for name in [*directories, *files]:
            entry = current_path / name
            if entry.is_symlink():
                raise BMError(f"{label} contém symlink: {entry}", EXIT_BLOCKED)


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_bytes(
        path,
        (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
    )


def json_document(text: str, label: str) -> dict[str, Any]:
    fenced = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    candidate = fenced.group(1) if fenced else text
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as error:
        raise BMError(f"{label}: JSON inválido na linha {error.lineno}") from error
    if not isinstance(value, dict):
        raise BMError(f"{label}: esperado objeto JSON")
    return value


def next_planning_version(value: str) -> str:
    match = re.fullmatch(r"v([1-9][0-9]*)", value)
    if not match:
        raise BMError("planning_version inválida; esperado v1, v2, ...")
    return f"v{int(match.group(1)) + 1}"


def relative_to_root(root: Path, path: Path, label: str) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as error:
        raise BMError(f"{label} fora da raiz: {path}") from error


def path_under_root(root: Path, value: Path, label: str) -> Path:
    base = root.resolve()
    candidate = value if value.is_absolute() else base / value
    resolved = candidate.resolve()
    try:
        resolved.relative_to(base)
    except ValueError as error:
        raise BMError(f"{label} fora da raiz: {value}") from error
    reject_symlink_chain(base, candidate, label)
    return resolved


ROOT_SUPERPOWERS_IGNORE = "/.superpowers/"
DIRECT_SCRATCH_ROOT = ".superpowers/bianchini/direct"


def idle_next_action(planning_version: str) -> str:
    return (
        "Aguardar novo escopo; então executar /sdd-planning para iniciar o ciclo "
        f"{planning_version} standalone."
    )
DESIGN_MANIFEST_REQUIRED = (
    "schema_version",
    "status",
    "source",
    "scope_source",
    "scope_digest",
    "design_digest",
    "contract",
    "prototype",
    "tokens",
    "screenshots",
    "surfaces",
    "breakpoints",
    "files",
)


def design_audit(
    root: Path,
    scope_path: Path,
    manifest_path: Path,
    seal: bool,
) -> dict[str, Any]:
    base = root.resolve()
    if not base.is_dir():
        raise BMError(f"raiz de design não encontrada: {root}")
    scope = path_under_root(base, scope_path, "scope de design")
    manifest_file = path_under_root(base, manifest_path, "manifesto de design")
    if not scope.is_file():
        raise BMError(f"scope de design ausente: {scope}")
    if not manifest_file.is_file():
        raise BMError(f"manifesto de design ausente: {manifest_file}")
    manifest = json_document(manifest_file.read_text(encoding="utf-8"), "manifesto de design")
    missing = [field for field in DESIGN_MANIFEST_REQUIRED if field not in manifest]
    if missing:
        raise BMError("manifesto de design incompleto: " + ", ".join(missing))
    if manifest.get("schema_version") != 1:
        raise BMError("manifesto de design: schema_version esperado 1")
    if manifest.get("status") not in {"draft", "approved"}:
        raise BMError("manifesto de design: status esperado draft ou approved")
    if manifest.get("source") not in {"generated", "imported", "existing"}:
        raise BMError("manifesto de design: source inválido")
    files = manifest.get("files")
    if not isinstance(files, list) or not files or not all(
        isinstance(item, str) and item for item in files
    ):
        raise BMError("manifesto de design: files deve ser lista não vazia")
    if len(files) != len(set(files)):
        raise BMError("manifesto de design: files contém duplicatas")
    manifest_relative = relative_to_root(base, manifest_file, "manifesto de design")
    design_root = manifest_file.parent.resolve()
    required_file_fields = ("contract", "prototype", "tokens")
    for field in required_file_fields:
        value = manifest.get(field)
        if not isinstance(value, str) or value not in files:
            raise BMError(f"manifesto de design: {field} deve constar em files")
    screenshots = manifest.get("screenshots")
    if not isinstance(screenshots, list) or not screenshots or not all(
        isinstance(item, str) and item in files for item in screenshots
    ):
        raise BMError("manifesto de design: screenshots deve ser lista não vazia e referenciar files")
    screenshot_extensions = {".png", ".jpg", ".jpeg", ".webp"}
    for item in screenshots:
        screenshot = path_under_root(base, Path(item), f"screenshot de design {item}")
        if screenshot.suffix.lower() not in screenshot_extensions:
            raise BMError(f"manifesto de design: screenshot deve ser PNG, JPEG ou WebP: {item}")
        if not screenshot.is_file() or screenshot.stat().st_size == 0:
            raise BMError(f"manifesto de design: screenshot vazio ou ausente: {item}")
    for field in ("surfaces", "breakpoints"):
        value = manifest.get(field)
        if not isinstance(value, list) or not value or not all(
            isinstance(item, str) and item.strip() for item in value
        ):
            raise BMError(f"manifesto de design: {field} deve ser lista não vazia")
    for item in files:
        target = path_under_root(base, Path(item), f"arquivo de design {item}")
        try:
            target.relative_to(design_root)
        except ValueError as error:
            raise BMError(
                f"manifesto de design: arquivo fora do diretório do manifesto: {item}"
            ) from error
        if not target.is_file():
            raise BMError(f"manifesto de design: arquivo ausente: {item}")
        if target.stat().st_size == 0:
            raise BMError(f"manifesto de design: arquivo vazio: {item}")
    contract = path_under_root(base, Path(str(manifest["contract"])), "contract")
    prototype = path_under_root(base, Path(str(manifest["prototype"])), "prototype")
    tokens = path_under_root(base, Path(str(manifest["tokens"])), "tokens")
    if contract.suffix.lower() != ".md":
        raise BMError("manifesto de design: contract deve ser Markdown")
    if prototype.suffix.lower() != ".html":
        raise BMError("manifesto de design: prototype deve ser HTML estático")
    if tokens.suffix.lower() != ".css":
        raise BMError("manifesto de design: tokens deve ser CSS")
    scope_relative = relative_to_root(base, scope, "scope de design")
    scope_digest = file_digest(scope)
    digest_manifest = {
        key: value
        for key, value in manifest.items()
        if key not in {"status", "scope_digest", "design_digest"}
    }
    digest_manifest["scope_source"] = scope_relative
    metadata = json.dumps(
        digest_manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    design_digest = hashlib.sha256(
        build_manifest(base, files) + b"\0" + metadata
    ).hexdigest()
    if seal:
        manifest["scope_source"] = scope_relative
        manifest["scope_digest"] = scope_digest
        manifest["design_digest"] = design_digest
        atomic_write_json(manifest_file, manifest)
    else:
        if manifest.get("status") != "approved":
            raise BMError(
                "BLOQUEADO: manifesto de design ainda não está approved",
                EXIT_BLOCKED,
            )
        if manifest.get("scope_source") != scope_relative:
            raise BMError(
                "BLOQUEADO: manifesto de design aponta outro scope_source",
                EXIT_BLOCKED,
            )
        if manifest.get("scope_digest") != scope_digest:
            raise BMError(
                "BLOQUEADO: scope_digest do design está obsoleto",
                EXIT_BLOCKED,
            )
        if manifest.get("design_digest") != design_digest:
            raise BMError(
                "BLOQUEADO: design_digest divergiu dos arquivos atuais",
                EXIT_BLOCKED,
            )
    return {
        "valid": True,
        "action": "seal" if seal else "verify",
        "status": manifest.get("status"),
        "manifest": manifest_relative,
        "scope_source": scope_relative,
        "scope_digest": scope_digest,
        "design_digest": design_digest,
        "files": sorted(files),
        "surfaces": manifest["surfaces"],
        "breakpoints": manifest["breakpoints"],
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



def path_uses_symlink(root: Path, target: Path) -> bool:
    current = root.resolve()
    for part in target.relative_to(root).parts:
        current = current / part
        if current.is_symlink():
            return True
    return False



def repository_hygiene(repo: Path) -> dict[str, Any]:
    root = repo.resolve()
    top = Path(run_git(["rev-parse", "--show-toplevel"], root)).resolve()
    if top != root:
        raise BMError(f"--repo deve apontar para a raiz Git: {top}")
    tracked = tracked_root_superpowers(root)
    problems: list[str] = []
    if tracked:
        problems.append(f"{len(tracked)} arquivo(s) de .superpowers ainda rastreado(s)")
    if not has_versioned_superpowers_ignore(root):
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

def idle_v2_state(
    planning_version: str = "v1",
    current_specs: str = "docs/bianchini/current/specs",
) -> dict[str, Any]:
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
            "quality_version": 2,
            "research_mode": None,
            "research": None,
            "readiness": None,
            "user_actions": None,
            "spec": None,
            "review": None,
            "checker": None,
            "design_manifest": None,
            "change_root": None,
            "current_specs": current_specs,
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
        "next_action": idle_next_action(planning_version),
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


READINESS_COLLECTION_PATTERNS = {
    "decisions": re.compile(r"^D-[0-9]{3}$"),
    "assumptions": re.compile(r"^A-[0-9]{3}$"),
    "pitfalls": re.compile(r"^P-[0-9]{3}$"),
    "user_actions": re.compile(r"^U-[0-9]{3}$"),
    "spikes": re.compile(r"^S-[0-9]{3}$"),
    "design_surfaces": re.compile(r"^DS-[0-9]{3}$"),
    "spec_deltas": re.compile(r"^SD-[0-9]{3}$"),
}
READINESS_IMPACT_KEYS = ("applications", "modules", "contracts", "data", "platforms")
READINESS_HIGH_IMPACT = {"high", "critical"}


def readiness_document(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise BMError(f"readiness ausente: {path}")
    return json_document(path.read_text(encoding="utf-8"), "READINESS.md")


def destination_path(value: str) -> str:
    return value.split("#", 1)[0].strip()


def planning_input_paths(state: dict[str, Any]) -> list[str]:
    review = state.get("planning", {}).get("review")
    excluded = {review} if isinstance(review, str) else set()
    return sorted(
        item
        for item in state["approval"]["package"]["files"]
        if item not in excluded
    )


def planning_input_digest(state: dict[str, Any], root: Path) -> str:
    paths = planning_input_paths(state)
    if not paths:
        raise BMError("checker: pacote sem entradas auditáveis")
    return hashlib.sha256(build_manifest(root, paths)).hexdigest()


def repository_revision(root: Path) -> str:
    base = root.resolve()
    top = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=base,
        text=True,
        capture_output=True,
        check=False,
    )
    if top.returncode != 0:
        return "new-project"
    if Path(top.stdout.strip()).resolve() != base:
        raise BMError("readiness: --root deve apontar para a raiz Git")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=base,
        text=True,
        capture_output=True,
        check=False,
    )
    return head.stdout.strip() if head.returncode == 0 else "unborn"


def validate_readiness(
    state: dict[str, Any], root: Path, package_files: set[str]
) -> tuple[dict[str, Any], list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    planning = state["planning"]
    change_root_value = planning.get("change_root")
    change_root_path: Path | None = None
    if not isinstance(change_root_value, str) or not change_root_value:
        errors.append("planning.change_root: diretório canônico obrigatório")
    else:
        try:
            change_root_path = confined_path(root, change_root_value, "planning.change_root")
            reject_symlink_chain(root, root / change_root_value, "planning.change_root")
        except BMError as error:
            errors.append(str(error))
        else:
            if not change_root_path.is_dir():
                errors.append("planning.change_root: diretório ausente")
    readiness_value = planning.get("readiness")
    readiness_path, _ = planning_file(root, readiness_value, "planning.readiness")
    if readiness_path is None or not readiness_path.is_file():
        return {}, ["planning.readiness: READINESS.md local é obrigatório"], []
    readiness = readiness_document(readiness_path)
    if readiness.get("schema_version") != 1:
        errors.append("readiness.schema_version: esperado 1")
    if readiness.get("status") != "ready":
        errors.append("readiness.status: esperado ready antes dos planos")
    scope_value = state["scope"].get("source")
    scope_path, _ = planning_file(root, scope_value, "scope.source")
    if scope_path is None or not scope_path.is_file():
        errors.append("readiness.scope_digest: escopo local ausente")
    elif readiness.get("scope_digest") != file_digest(scope_path):
        errors.append("readiness.scope_digest: divergiu do escopo aprovado")

    def require_change_path(path: Path | None, label: str) -> None:
        if path is None or change_root_path is None:
            return
        try:
            path.resolve().relative_to(change_root_path.resolve())
        except ValueError:
            errors.append(f"{label}: deve ficar dentro de planning.change_root")

    require_change_path(scope_path, "scope.source")
    require_change_path(readiness_path, "planning.readiness")
    declared_revision = readiness.get("repository_revision")
    if not isinstance(declared_revision, str) or not declared_revision.strip():
        errors.append("readiness.repository_revision: valor factual obrigatório")
    elif state.get("approval", {}).get("status") != "approved":
        try:
            current_revision = repository_revision(root)
        except BMError as error:
            errors.append(str(error))
        else:
            if declared_revision != current_revision:
                errors.append(
                    "readiness.repository_revision: repositório mudou após o gate de prontidão"
                )
    design_required = readiness.get("design_required")
    if not isinstance(design_required, bool):
        errors.append("readiness.design_required: esperado boolean")
    impact_map = readiness.get("impact_map")
    if not isinstance(impact_map, dict):
        errors.append("readiness.impact_map: objeto obrigatório")
    else:
        for key in READINESS_IMPACT_KEYS:
            value = impact_map.get(key)
            if not isinstance(value, list) or not all(
                isinstance(item, str) and item.strip() for item in value
            ):
                errors.append(f"readiness.impact_map.{key}: esperado lista de strings")

    identifiers: set[str] = set()
    plan_ids = {plan["id"] for plan in state["plans"]}
    package_content: dict[str, str] = {}

    def content_for(path_value: str) -> str:
        if path_value not in package_content:
            path, content = planning_file(root, path_value, f"readiness destination {path_value}")
            if path is None or not content:
                errors.append(f"readiness destination ausente ou vazio: {path_value}")
                package_content[path_value] = ""
            else:
                package_content[path_value] = content
        return package_content[path_value]

    def check_destinations(item: dict[str, Any], identifier: str) -> None:
        destinations = item.get("destinations")
        if not isinstance(destinations, list) or not destinations or not all(
            isinstance(value, str) and value.strip() for value in destinations
        ):
            errors.append(f"readiness {identifier}: destinations não vazio é obrigatório")
            return
        for raw in destinations:
            path_value = destination_path(raw)
            if path_value not in package_files:
                errors.append(
                    f"readiness {identifier}: destino fora do pacote aprovado: {path_value}"
                )
                continue
            if identifier not in content_for(path_value):
                errors.append(
                    f"readiness {identifier}: ID ausente no destino {path_value}"
                )

    collections: dict[str, list[dict[str, Any]]] = {}
    for name, pattern in READINESS_COLLECTION_PATTERNS.items():
        value = readiness.get(name)
        if not isinstance(value, list):
            errors.append(f"readiness.{name}: esperado lista")
            collections[name] = []
            continue
        collections[name] = []
        for index, item in enumerate(value):
            if not isinstance(item, dict):
                errors.append(f"readiness.{name}[{index}]: esperado objeto")
                continue
            identifier = item.get("id")
            if not isinstance(identifier, str) or not pattern.fullmatch(identifier):
                errors.append(f"readiness.{name}[{index}].id: formato inválido")
                continue
            if identifier in identifiers:
                errors.append(f"readiness: ID duplicado {identifier}")
            identifiers.add(identifier)
            collections[name].append(item)
            check_destinations(item, identifier)

    for item in collections["decisions"]:
        identifier = item["id"]
        if not str(item.get("statement") or "").strip():
            errors.append(f"readiness {identifier}: statement obrigatório")
        if not str(item.get("evidence") or "").strip():
            errors.append(f"readiness {identifier}: evidence obrigatório")

    for item in collections["assumptions"]:
        identifier = item["id"]
        impact = item.get("impact")
        status = item.get("status")
        if impact not in {"low", "medium", "high", "critical"}:
            errors.append(f"readiness {identifier}: impact inválido")
        if status not in {"confirmed", "bounded", "not_applicable"}:
            errors.append(f"readiness {identifier}: suposição ainda não resolvida")
        if impact in READINESS_HIGH_IMPACT and not str(item.get("evidence") or "").strip():
            errors.append(f"readiness {identifier}: evidência obrigatória para alto impacto")
        if status == "bounded" and not str(item.get("fallback") or "").strip():
            errors.append(f"readiness {identifier}: fallback obrigatório quando bounded")

    for item in collections["pitfalls"]:
        identifier = item["id"]
        impact = item.get("impact")
        if impact not in {"low", "medium", "high", "critical"}:
            errors.append(f"readiness {identifier}: impact inválido")
        if impact in READINESS_HIGH_IMPACT:
            for field in ("prevention", "recovery", "verification"):
                if not str(item.get(field) or "").strip():
                    errors.append(f"readiness {identifier}: {field} obrigatório")

    user_actions_value = planning.get("user_actions")
    user_actions_path, user_actions_content = planning_file(
        root, user_actions_value, "planning.user_actions"
    )
    if user_actions_path is None or not user_actions_content:
        errors.append("planning.user_actions: USER_ACTIONS.md local é obrigatório")
    require_change_path(user_actions_path, "planning.user_actions")
    for field in ("research", "spec", "review"):
        field_path, _ = planning_file(root, planning.get(field), f"planning.{field}")
        require_change_path(field_path, f"planning.{field}")
    for plan in state["plans"]:
        plan_path, _ = planning_file(root, plan.get("path"), f"plan {plan.get('id')}")
        require_change_path(plan_path, f"plan {plan.get('id')}")
    for item in collections["user_actions"]:
        identifier = item["id"]
        if item.get("needed_by") not in plan_ids:
            errors.append(f"readiness {identifier}: needed_by deve apontar plano existente")
        if not isinstance(item.get("can_continue_without"), bool):
            errors.append(f"readiness {identifier}: can_continue_without deve ser boolean")
        if item.get("can_continue_without") and not str(item.get("fallback") or "").strip():
            errors.append(f"readiness {identifier}: fallback obrigatório")
        if not str(item.get("evidence_required") or "").strip():
            errors.append(f"readiness {identifier}: evidence_required obrigatório")
        if identifier not in user_actions_content:
            errors.append(f"planning.user_actions: ação {identifier} ausente")

    for item in collections["spikes"]:
        identifier = item["id"]
        if item.get("status") not in {"passed", "failed", "not_needed"}:
            errors.append(f"readiness {identifier}: spike deve estar encerrado")
        if item.get("status") == "passed":
            if not str(item.get("evidence") or "").strip():
                errors.append(f"readiness {identifier}: evidence obrigatório")
            if not str(item.get("decision") or "").strip():
                errors.append(f"readiness {identifier}: decision obrigatória")
        if item.get("status") == "failed":
            errors.append(f"readiness {identifier}: spike falhou e bloqueia o plano")

    design_manifest_value = planning.get("design_manifest")
    design_summary: dict[str, Any] | None = None
    if design_required:
        if not isinstance(design_manifest_value, str) or not design_manifest_value:
            errors.append("planning.design_manifest: design obrigatório sem manifesto aprovado")
        if not collections["design_surfaces"]:
            errors.append("readiness.design_surfaces: UI obrigatória sem superfície DS")
    if isinstance(design_manifest_value, str) and design_manifest_value:
        if design_manifest_value not in package_files:
            errors.append("planning.design_manifest: manifesto ausente do pacote")
        elif scope_path is not None:
            try:
                design_summary = design_audit(
                    root,
                    scope_path,
                    confined_path(root, design_manifest_value, "planning.design_manifest"),
                    False,
                )
                for item in design_summary["files"]:
                    if item not in package_files:
                        errors.append(
                            f"planning.design_manifest: arquivo de design fora do pacote: {item}"
                        )
            except BMError as error:
                errors.append(str(error))
    for item in collections["design_surfaces"]:
        identifier = item["id"]
        if item.get("required") is not True:
            warnings.append(f"readiness {identifier}: superfície opcional não deve ampliar escopo")
        if item.get("manifest_ref") != design_manifest_value:
            errors.append(f"readiness {identifier}: manifest_ref diverge do estado")

    current_specs_value = planning.get("current_specs")
    if not isinstance(current_specs_value, str) or not current_specs_value:
        errors.append("planning.current_specs: diretório canônico obrigatório")
        current_specs_root = None
    else:
        current_specs_root = confined_path(root, current_specs_value, "planning.current_specs")
        reject_symlink_chain(root, root / current_specs_value, "planning.current_specs")
    if not collections["spec_deltas"]:
        warnings.append("readiness.spec_deltas vazio: ciclo não altera comportamento persistido nas specs atuais")
    spec_deltas: list[dict[str, str]] = []
    spec_sources: set[str] = set()
    spec_targets: set[str] = set()
    for item in collections["spec_deltas"]:
        identifier = item["id"]
        source = item.get("source")
        target = item.get("target")
        if not isinstance(source, str) or source not in package_files:
            errors.append(f"readiness {identifier}: source deve constar no pacote")
            continue
        if not isinstance(target, str) or not target:
            errors.append(f"readiness {identifier}: target obrigatório")
            continue
        if source in spec_sources:
            errors.append(f"readiness {identifier}: source duplicado em spec_deltas")
        if target in spec_targets:
            errors.append(f"readiness {identifier}: target duplicado em spec_deltas")
        spec_sources.add(source)
        spec_targets.add(target)
        source_path, source_content = planning_file(root, source, f"readiness {identifier}.source")
        require_change_path(source_path, f"readiness {identifier}.source")
        if source_path is None or not source_content:
            errors.append(f"readiness {identifier}: source ausente ou vazio")
        elif identifier not in source_content:
            errors.append(f"readiness {identifier}: ID ausente no source")
        target_path = confined_path(root, target, f"readiness {identifier}.target")
        reject_symlink_chain(root, root / target, f"readiness {identifier}.target")
        if current_specs_root is not None:
            try:
                target_path.relative_to(current_specs_root.resolve())
            except ValueError as error:
                errors.append(f"readiness {identifier}: target fora de current_specs")
        if target_path.exists():
            if target not in package_files:
                errors.append(
                    f"readiness {identifier}: spec atual existente deve constar no pacote"
                )
        spec_deltas.append({"id": identifier, "source": source, "target": target})

    return (
        {
            "status": readiness.get("status"),
            "scope_digest": readiness.get("scope_digest"),
            "design_required": design_required,
            "design": design_summary,
            "counts": {name: len(value) for name, value in collections.items()},
            "coverage_gaps": sorted(set(errors)),
            "spec_deltas": spec_deltas,
        },
        errors,
        warnings,
    )


def checker_report(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise BMError(f"checker: relatório ausente: {path}")
    report = json_document(path.read_text(encoding="utf-8"), "PLANNING_REVIEW.md")
    verdict = report.get("verdict")
    if verdict not in {"passed", "changes_requested", "blocked"}:
        raise BMError("checker: verdict inválido")
    findings = report.get("findings")
    if not isinstance(findings, list):
        raise BMError("checker: findings deve ser lista")
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            raise BMError(f"checker: finding {index} deve ser objeto")
        if finding.get("severity") not in {"critical", "important", "minor", "note"}:
            raise BMError(f"checker: finding {index} tem severity inválida")
        for field in ("id", "summary", "evidence"):
            if not isinstance(finding.get(field), str) or not finding[field].strip():
                raise BMError(f"checker: finding {index} sem {field}")
    material_findings = [
        finding
        for finding in findings
        if finding.get("severity") in {"critical", "important"}
    ]
    if verdict == "passed" and material_findings:
        raise BMError("checker: passed não aceita finding critical/important")
    if verdict in {"changes_requested", "blocked"} and not material_findings:
        raise BMError(f"checker: {verdict} exige finding critical/important")
    identifiers = [finding["id"].strip() for finding in findings]
    if len(identifiers) != len(set(identifiers)):
        raise BMError("checker: IDs de findings duplicados")
    return report


def planning_check_record(
    state_path: Path, root: Path, report_path: Path
) -> dict[str, Any]:
    state = validate_state(state_path)
    if state.get("planning", {}).get("quality_version") != 2:
        raise BMError("planning-check exige planning.quality_version 2")
    planning_audit(state_path, root, strict=True, require_checker=False)
    planning = state["planning"]
    checker = planning.get("checker")
    if not isinstance(checker, dict):
        raise BMError("planning.checker: contrato ausente")
    canonical_review = planning.get("review")
    report_file = path_under_root(root, report_path, "checker report")
    if not isinstance(canonical_review, str) or relative_to_root(
        root, report_file, "checker report"
    ) != canonical_review:
        raise BMError(
            "BLOQUEADO: planning-check deve usar exatamente planning.review",
            EXIT_BLOCKED,
        )
    history_value = checker.get("history_path")
    if not isinstance(history_value, str) or not history_value:
        raise BMError("planning.checker.history_path: caminho obrigatório")
    history_path = confined_path(root, history_value, "planning.checker.history_path")
    reject_symlink_chain(root, history_path, "planning.checker.history_path")
    history: list[dict[str, Any]] = []
    if history_path.is_file():
        for line_number, line in enumerate(
            history_path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as error:
                raise BMError(
                    f"checker: histórico inválido na linha {line_number}"
                ) from error
            if not isinstance(value, dict):
                raise BMError(f"checker: histórico inválido na linha {line_number}")
            history.append(value)
    if len(history) >= 2 or (history and history[-1].get("verdict") == "blocked"):
        raise BMError(
            "BLOQUEADO: checker atingiu o máximo de duas revisões",
            EXIT_BLOCKED,
        )
    report = checker_report(report_file)
    digest = planning_input_digest(state, root)
    round_number = len(history) + 1
    if round_number == 2:
        if history[-1].get("verdict") not in {"changes_requested", "passed"}:
            raise BMError("BLOQUEADO: segunda revisão não foi autorizada", EXIT_BLOCKED)
        if history[-1].get("package_digest") == digest:
            raise BMError(
                "BLOQUEADO: segunda revisão exige correção factual no pacote",
                EXIT_BLOCKED,
            )
        if history[-1].get("report_digest") == file_digest(report_file):
            raise BMError(
                "BLOQUEADO: segunda revisão exige relatório novo para o pacote corrigido",
                EXIT_BLOCKED,
            )
        if report["verdict"] == "changes_requested":
            raise BMError(
                "BLOQUEADO: segunda revisão deve aprovar ou bloquear",
                EXIT_BLOCKED,
            )
    report_digest = file_digest(report_file)
    record = {
        "schema_version": 1,
        "round": round_number,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "package_digest": digest,
        "report_digest": report_digest,
        "verdict": report["verdict"],
        "findings": report["findings"],
    }
    history_existed = history_path.exists()
    history_bytes = history_path.read_bytes() if history_existed else b""
    state_bytes = state_path.read_bytes()
    history_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with history_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        checker.update(
            {
                "status": report["verdict"],
                "rounds": round_number,
                "package_digest": digest,
                "report_digest": report_digest,
            }
        )
        atomic_write_json(state_path, state)
    except Exception:
        atomic_write_bytes(state_path, state_bytes)
        if history_existed:
            atomic_write_bytes(history_path, history_bytes)
        elif history_path.exists():
            history_path.unlink()
        raise
    return {
        "recorded": True,
        "round": round_number,
        "status": report["verdict"],
        "package_digest": digest,
        "report_digest": report_digest,
        "history_path": relative_to_root(root, history_path, "checker history"),
        "next_action": (
            "freeze_and_request_approval"
            if report["verdict"] == "passed"
            else "apply_single_correction"
            if report["verdict"] == "changes_requested"
            else "planning_blocked"
        ),
    }


def change_policy(
    *,
    scope_change: bool,
    public_contract_change: bool,
    approved_design_change: bool,
    new_cost: bool,
    irreversible_action: bool,
    external_impossibility: bool,
    critical_invariant: bool,
    plan_command: bool,
    file_location: bool,
    internal_order: bool,
) -> dict[str, Any]:
    plan_invalidating = any(
        (
            scope_change,
            public_contract_change,
            approved_design_change,
            external_impossibility,
            critical_invariant,
        )
    )
    authorization_only = any((new_cost, irreversible_action)) and not plan_invalidating
    material = plan_invalidating or authorization_only
    bounded = any((plan_command, file_location, internal_order))
    if plan_invalidating:
        classification = "material_change"
        action = "invalidate_package_and_replan_affected_scope"
        reapproval = True
    elif authorization_only:
        classification = "material_change"
        action = "pause_for_owner_authorization_without_replanning"
        reapproval = True
    elif bounded:
        classification = "bounded_amendment"
        action = "record_in_ledger_and_continue"
        reapproval = False
    else:
        classification = "implementation_detail"
        action = "decide_reversibly_record_if_material_and_continue"
        reapproval = False
    return {
        "classification": classification,
        "action": action,
        "reapproval_required": reapproval,
        "plan_invalidating": plan_invalidating,
        "plan_files_mutable": False,
        "extra_review_required": plan_invalidating,
        "redesign_allowed": plan_invalidating,
    }


def cycle_close(state_path: Path, root: Path) -> dict[str, Any]:
    base = root.resolve()
    if Path(run_git(["rev-parse", "--show-toplevel"], base)).resolve() != base:
        raise BMError("--root deve apontar para a raiz Git")
    state_file = path_under_root(base, state_path, "PROJECT_STATE")
    if not state_file.is_file():
        raise BMError("PROJECT_STATE ausente")
    state_relative = relative_to_root(base, state_file, "PROJECT_STATE")
    try:
        tracked = run_git(["ls-files", "--error-unmatch", "--", state_relative], base)
    except BMError as error:
        raise BMError(
            "BLOQUEADO: cycle-close exige PROJECT_STATE commitado",
            EXIT_BLOCKED,
        ) from error
    if tracked != state_relative:
        raise BMError("BLOQUEADO: PROJECT_STATE não está rastreado", EXIT_BLOCKED)
    dirty = run_git(["status", "--porcelain=v1", "--untracked-files=all"], base)
    if dirty:
        changed = [line[3:] if len(line) > 3 else line for line in dirty.splitlines()]
        raise BMError(
            "BLOQUEADO: cycle-close exige release commitado e árvore limpa: "
            + ", ".join(changed[:8]),
            EXIT_BLOCKED,
        )
    state = validate_state(state_file)
    if state.get("planning", {}).get("quality_version") != 2:
        raise BMError("cycle-close exige planning.quality_version 2")
    incomplete_plans = [plan["id"] for plan in state["plans"] if plan["status"] != "completed"]
    release_gate_passed = state["verification"]["release"]["status"] == "passed"
    active_execution = state.get("active_execution")
    if incomplete_plans or not release_gate_passed or active_execution is not None:
        reasons: list[str] = []
        if incomplete_plans:
            reasons.append("planos completed obrigatórios: " + ", ".join(incomplete_plans))
        if not release_gate_passed:
            reasons.append("verification.release passed obrigatório")
        if active_execution is not None:
            reasons.append("active_execution deve estar null")
        raise BMError("BLOQUEADO: cycle-close exige " + "; ".join(reasons), EXIT_BLOCKED)
    release = state["release"]
    if not (
        release.get("status") == "ready"
        and release.get("homologation") == "accepted"
        and release.get("final_review") == "approved"
        and release.get("delivery") == "ready"
    ):
        raise BMError(
            "BLOQUEADO: cycle-close exige release ready, homologação aceita, revisão aprovada e entrega pronta",
            EXIT_BLOCKED,
        )
    snapshot(state_file, base, verify=True)
    package_files = set(state["approval"]["package"]["files"])
    readiness_summary, readiness_errors, _ = validate_readiness(state, base, package_files)
    if readiness_errors:
        raise BMError(
            "BLOQUEADO: readiness inválido no fechamento:\n- "
            + "\n- ".join(readiness_errors),
            EXIT_BLOCKED,
        )
    planning = state["planning"]
    change_root_value = planning.get("change_root")
    current_specs_value = planning.get("current_specs")
    if not isinstance(change_root_value, str) or not isinstance(current_specs_value, str):
        raise BMError("cycle-close: change_root/current_specs ausentes")
    change_root = confined_path(base, change_root_value, "planning.change_root")
    current_specs = confined_path(base, current_specs_value, "planning.current_specs")
    reject_tree_symlinks(base, change_root, "planning.change_root")
    reject_tree_symlinks(base, current_specs, "planning.current_specs")
    if not change_root.is_dir():
        raise BMError("cycle-close: change_root ausente")
    version = state["planning_version"]
    archive_value = f"docs/bianchini/archive/{version}"
    archive_root = confined_path(base, archive_value, "cycle archive")
    reject_symlink_chain(base, archive_root, "cycle archive")
    if archive_root.exists():
        raise BMError(
            f"BLOQUEADO: archive já existe: {archive_value}", EXIT_BLOCKED
        )
    deltas = readiness_summary.get("spec_deltas") or []
    prepared: list[tuple[str, Path, str, Path, bytes]] = []
    target_backups: dict[Path, bytes | None] = {}
    for item in deltas:
        source_value = item["source"]
        target_value = item["target"]
        source = confined_path(base, source_value, f"{item['id']}.source")
        target = confined_path(base, target_value, f"{item['id']}.target")
        reject_symlink_chain(base, source, f"{item['id']}.source")
        reject_symlink_chain(base, target, f"{item['id']}.target")
        if not source.is_file():
            raise BMError(f"cycle-close: source ausente: {source_value}")
        try:
            source.relative_to(change_root.resolve())
        except ValueError as error:
            raise BMError(f"cycle-close: source fora do change_root: {source_value}") from error
        try:
            target.relative_to(current_specs.resolve())
        except ValueError as error:
            raise BMError(f"cycle-close: target fora de current_specs: {target_value}") from error
        if source == target:
            raise BMError("cycle-close: source e target não podem ser iguais")
        content = source.read_bytes()
        prepared.append((item["id"], source, target_value, target, content))
        target_backups[target] = target.read_bytes() if target.is_file() else None

    backup_root = confined_path(
        base,
        f".superpowers/bianchini/cycle-close/{version}",
        "cycle backup",
    )
    if backup_root.exists():
        shutil.rmtree(backup_root)
    backup_root.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(change_root, backup_root)
    state_bytes = state_file.read_bytes()
    manifest_path = confined_path(
        base, state["approval"]["package"]["manifest_path"], "approval manifest"
    )
    manifest_bytes = manifest_path.read_bytes()
    try:
        archive_root.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(backup_root, archive_root)
        atomic_write_bytes(archive_root / "FINAL_PROJECT_STATE.json", state_bytes)
        atomic_write_bytes(archive_root / "APPROVAL_MANIFEST.sha256", manifest_bytes)
        synchronized: list[dict[str, str]] = []
        for identifier, _, target_value, target, content in prepared:
            target.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_bytes(target, content)
            synchronized.append({"id": identifier, "target": target_value})
        next_version = next_planning_version(version)
        next_state = idle_v2_state(next_version, current_specs_value)
        atomic_write_json(state_file, next_state)
        shutil.rmtree(change_root)
        stage_paths = [archive_value, change_root_value, state_relative]
        if current_specs.exists() or prepared:
            stage_paths.insert(0, current_specs_value)
        run_git(["add", "-A", "--", *stage_paths], base)
    except Exception as error:
        atomic_write_bytes(state_file, state_bytes)
        for target, original in target_backups.items():
            if original is None:
                if target.exists():
                    target.unlink()
            else:
                atomic_write_bytes(target, original)
        if archive_root.exists():
            shutil.rmtree(archive_root)
        if not change_root.exists():
            shutil.copytree(backup_root, change_root)
        reset_paths = [archive_value, change_root_value, state_relative]
        if current_specs.exists() or prepared:
            reset_paths.insert(0, current_specs_value)
        subprocess.run(
            ["git", "reset", "-q", "HEAD", "--", *reset_paths],
            cwd=base,
            text=True,
            capture_output=True,
            check=False,
        )
        raise BMError(f"BLOQUEADO: cycle-close revertido: {error}", EXIT_BLOCKED) from error
    finally:
        if backup_root.exists():
            shutil.rmtree(backup_root)
        try:
            backup_root.parent.rmdir()
        except OSError:
            pass
    return {
        "closed": True,
        "previous_planning_version": version,
        "planning_version": next_version,
        "archive": archive_value,
        "current_specs": current_specs_value,
        "synchronized": synchronized,
        "state": state_relative,
        "staged": sorted(run_git(["diff", "--cached", "--name-only"], base).splitlines()),
        "next_action": next_state["next_action"],
    }


def planning_audit(
    state_path: Path,
    root: Path,
    strict: bool,
    require_checker: bool = True,
) -> dict[str, Any]:
    state = validate_state(state_path)
    quality_version = state.get("planning", {}).get("quality_version")
    quality_enabled = quality_version in {1, 2}
    quality_v2 = quality_version == 2
    enforced = strict or quality_enabled
    errors: list[str] = []
    warnings: list[str] = []
    if state["planning_status"] == "idle":
        if enforced:
            raise BMError("planejamento inválido:\n- ciclo idle ainda não possui pacote auditável")
        limits = PLANNING_LIMITS_BY_PROFILE[state["assurance_profile"]]
        return {
            "valid": True,
            "quality_contract": "planning-quality-v2" if quality_v2 else "legacy-compatible",
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
    if quality_v2:
        contract_values.extend(
            [
                state["planning"].get("readiness"),
                state["planning"].get("user_actions"),
            ]
        )
        if state["planning"].get("design_manifest"):
            contract_values.append(state["planning"]["design_manifest"])
    if enforced:
        if not quality_enabled:
            errors.append("planning.quality_version: esperado 1 ou 2 para novo planejamento")
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
    plan_contents: dict[str, str] = {}
    for plan in state["plans"]:
        path, content = planning_file(root, plan["path"], f"plan {plan['id']}")
        if enforced and (path is None or not content):
            errors.append(f"plano {plan['id']}: arquivo ausente ou vazio")
            continue
        if not content:
            continue
        plan_contents[plan["path"]] = content
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
            required_fields = (
                (*UNIT_FIELDS, *QUALITY_V2_UNIT_FIELDS) if quality_v2 else UNIT_FIELDS
            )
            for field in required_fields:
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

    readiness_summary: dict[str, Any] | None = None
    if quality_v2:
        readiness_summary, readiness_errors, readiness_warnings = validate_readiness(
            state, root, package_files
        )
        errors.extend(readiness_errors)
        warnings.extend(readiness_warnings)
        readiness_value = state["planning"].get("readiness")
        readiness_path, _ = planning_file(root, readiness_value, "planning.readiness")
        if readiness_path is not None and readiness_path.is_file():
            readiness_value_document = readiness_document(readiness_path)
            for plan_path_value, plan_content in plan_contents.items():
                errors.extend(
                    validate_quality_v2_plan(
                        plan_path_value,
                        plan_content,
                        readiness_value_document,
                    )
                )
        checker = state["planning"].get("checker")
        if require_checker:
            if not isinstance(checker, dict):
                errors.append("planning.checker: contrato obrigatório ausente")
            else:
                if checker.get("status") != "passed":
                    errors.append("planning.checker.status: esperado passed")
                rounds = checker.get("rounds")
                if not isinstance(rounds, int) or isinstance(rounds, bool) or rounds not in {1, 2}:
                    errors.append("planning.checker.rounds: esperado 1 ou 2")
                try:
                    current_digest = planning_input_digest(state, root)
                except BMError as error:
                    errors.append(str(error))
                else:
                    if checker.get("package_digest") != current_digest:
                        errors.append("planning.checker.package_digest: pacote mudou após a revisão")
                review_value = state["planning"].get("review")
                review_path, _ = planning_file(root, review_value, "planning.review")
                if review_path is None or not review_path.is_file():
                    errors.append("planning.checker.report_digest: planning.review ausente")
                elif checker.get("report_digest") != file_digest(review_path):
                    errors.append("planning.checker.report_digest: relatório mudou após a revisão")

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
        "quality_contract": (
            "planning-quality-v2"
            if quality_v2
            else "planning-quality-v1"
            if quality_enabled
            else "legacy-compatible"
        ),
        "profile": profile,
        "recommended_profile": recommended_profile,
        "research_mode": research_mode,
        "metrics": metrics,
        "limits": limits,
        "budget_exceeded": exceeded,
        "warnings": sorted(set(warnings)),
        "readiness": readiness_summary,
    }


def snapshot(state_path: Path, root: Path, verify: bool) -> dict[str, Any]:
    state = validate_state(state_path)
    if state.get("planning", {}).get("quality_version") in {1, 2}:
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


STRUCTURAL_FINDING_CLASSES = (
    "crash_window",
    "partial_commit",
    "toctou",
    "external_effect_before_persistence",
    "retry_after_timeout",
    "concurrent_idempotency",
    "recovery_after_restart",
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


def policy(
    profile: str,
    risk: str,
    change: str,
    manual_pdf: str,
    manual_in_scope: bool,
    round_number: int,
    risk_seam: str | None = None,
    seam_round: int | None = None,
    structural_findings: tuple[str, ...] = (),
    consecutive_seam_findings: int = 0,
) -> dict[str, Any]:
    if risk == "low":
        execution, review, cadence = "grouped", "plan_gate", "group_seam"
    elif risk == "medium":
        execution, review, cadence = "slice", "per_slice", "slice_seam"
    else:
        execution, review, cadence = "strict", "per_task", "red_green_per_task"
    if (seam_round is not None or consecutive_seam_findings) and not risk_seam:
        raise BMError("--seam-round e --consecutive-seam-findings exigem --risk-seam")
    for finding in structural_findings:
        if finding not in STRUCTURAL_FINDING_CLASSES:
            raise BMError(f"classe estrutural desconhecida: {finding}")
    max_rounds = FIX_ROUNDS_BY_PROFILE[profile]
    manual_required = manual_pdf in {"quick_start", "full"} or (
        manual_pdf == "scope" and manual_in_scope
    )
    change_kind = change.strip().lower().replace("_", "-")
    visual_validation = change_kind == "visual"
    mutation_mode = mutation_mode_for_change(risk, change_kind)
    effective_round = max(round_number, seam_round or 0)
    hypothesis_invalidated = bool(structural_findings) or consecutive_seam_findings >= 2
    return {
        "execution": execution,
        "review": review,
        "test_cadence": cadence,
        "max_fix_rounds": max_rounds,
        "risk_seam": risk_seam,
        "breaker_scope": "risk_seam" if risk_seam else "unit",
        "effective_fix_round": effective_round,
        "structural_findings": list(structural_findings),
        "hypothesis_invalidated": hypothesis_invalidated,
        "redesign_required": hypothesis_invalidated,
        "breaker": effective_round >= max_rounds or hypothesis_invalidated,
        "architecture_audit_required": False,
        "architecture_audit_mode": "manual_report_only",
        "manual_required": manual_required,
        "manual_level": manual_pdf if manual_required else "none",
        "visual_validation": "screenshot_or_visual_regression" if visual_validation else "behavioral_seam",
        "test_strategy": {
            "fast": [
                "targeted_unit_if_logic_changed",
                "targeted_integration_if_boundary_changed",
                "related_regression",
            ],
            "plan": [
                "affected_unit_suite",
                "affected_integration_and_contracts",
                "affected_regression",
                "critical_journey_e2e",
                "selective_mutation_if_required",
            ],
            "release": [
                "complete_unit_suite",
                "applicable_integration_and_contracts",
                "critical_journey_e2e",
                "full_regression",
                "current_mutation_evidence_if_required",
                "release_build",
            ],
        },
        "mutation_policy": {
            "mode": mutation_mode,
            "scope": "changed_material_risk_seams",
            "run_stage": "plan_and_release_only",
            "global_score_gate": False,
            "blocking_rule": "survivor_changes_approved_high_or_critical_behavior",
            "install_new_tool_during_execution": False,
        },
        "autonomy_policy": {
            "decision_order": [
                "approved_owner_decision",
                "existing_repository_pattern",
                "existing_stack_and_dependencies",
                "official_documentation",
                "lowest_risk_reversible_option",
            ],
            "stop_categories": [
                "essential_external_credential",
                "new_cost",
                "destructive_or_irreversible_action",
                "material_scope_contract_or_design_change",
                "proven_real_impossibility",
            ],
        },
        "plan_change_policy": {
            "implementation_detail": "decide_and_continue",
            "bounded_amendment": "record_in_ledger_without_editing_approved_plan",
            "plan_invalidating_material_change": "invalidate_and_replan_affected_scope",
            "authorization_material_change": "pause_for_owner_authorization_without_replanning",
        },
        "homologation_order": [
            "automated_regression",
            "coded_e2e",
            "proof_map",
            "real_system_pass",
            "visual_sweep",
        ],
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
    repository_hygiene(root)
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
        rf"(?ms)^###\s+(?:Tarefa|Task|Slice)\s+{re.escape(task)}\b.*?(?=^###\s+(?:Tarefa|Task|Slice)\s+\S+|\Z)"
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
    state_path: Path | None = None,
    root: Path | None = None,
    hydrate_context: bool = False,
    ledger_tail_lines: int = 40,
) -> dict[str, Any]:
    if ledger_tail_lines < 0:
        raise BMError("--ledger-tail-lines não pode ser negativo")
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
    content = (
        f"# Task Brief {title}\n\n- Plan: `{plan}`\n"
        f"- Plan SHA-256: `{source_hash}`\n"
        f"- Kind: `{kind}`\n"
        f"- Group ID: `{group_id or 'n/a'}`\n"
        f"- Group SHA-256: `{group_digest}`\n{metadata}\n\n"
        + "\n".join(sections)
    )
    context_metadata: dict[str, Any] | None = None
    if hydrate_context:
        if state_path is None or root is None:
            raise BMError("--hydrate-context exige --state e --root")
        state = validate_state(state_path)
        try:
            context, context_metadata = hydrate_task_context(
                root=root,
                state=state,
                plan_path=plan,
                labels=labels,
                sections=sections,
                ledger_tail_lines=ledger_tail_lines,
            )
        except ValueError as error:
            raise BMError(str(error)) from error
        content = content.rstrip() + "\n\n" + context
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content.rstrip() + "\n", encoding="utf-8")
    return {
        "brief": str(output),
        "plan_digest": source_hash,
        "kind": kind,
        "group_id": group_id,
        "group_digest": group_digest,
        "tasks": labels,
        "unit_digests": unit_hashes,
        "hydrated": hydrate_context,
        "context_digest": context_metadata.get("context_digest") if context_metadata else None,
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


def write_proof_map(
    state_path: Path,
    evidence_path: Path,
    output: Path,
    mutation_evidence_paths: list[Path] | None = None,
) -> dict[str, Any]:
    state = validate_state(state_path)
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BMError(f"evidência inválida: {error}") from error
    if not isinstance(evidence, list) or not all(isinstance(item, dict) for item in evidence):
        raise BMError("evidência deve ser uma lista JSON de objetos")
    candidate = state.get("release", {}).get("candidate")
    if not isinstance(candidate, dict):
        raise BMError("release candidate com fingerprint é obrigatório para proof-map")
    fingerprint = {
        key: candidate[key] for key in ("id", "revision", "build", "checksum")
    }
    mutation_sources: list[str] = []
    for mutation_path in mutation_evidence_paths or []:
        if not mutation_path.is_file():
            raise BMError(f"evidência de mutação ausente: {mutation_path}")
        try:
            mutation = json.loads(mutation_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise BMError(
                f"evidência de mutação inválida na linha {error.lineno}: {mutation_path}"
            ) from error
        if not isinstance(mutation, dict) or mutation.get("schema_version") != 1:
            raise BMError(f"evidência de mutação inválida: {mutation_path}")
        mutation_candidate = mutation.get("candidate")
        command = mutation.get("command")
        result = mutation.get("result", mutation.get("status"))
        if not isinstance(mutation_candidate, dict):
            raise BMError(
                f"evidência de mutação não está vinculada a um RC: {mutation_path}"
            )
        if not isinstance(command, str) or not command.strip():
            raise BMError(f"evidência de mutação sem command: {mutation_path}")
        if result not in {"passed", "blocked"}:
            raise BMError(f"evidência de mutação sem resultado válido: {mutation_path}")
        evidence.append(
            {
                "type": "mutation",
                "command": command,
                "result": result,
                "evidence": str(mutation_path),
                "rc": mutation_candidate.get("id"),
                "revision": mutation_candidate.get("revision"),
                "build": mutation_candidate.get("build"),
                "checksum": mutation_candidate.get("checksum"),
            }
        )
        mutation_sources.append(str(mutation_path))
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
                "source_type": item.get("type") if item else None,
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
        "mutation_evidence": mutation_sources,
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
DIRECT_TERMINAL_STATUSES = {"completed", "blocked", "escalated"}
DIRECT_GENERIC_CURRENT_STATE = re.compile(
    r"(?i)\b(?:a\s+confirmar|n[aã]o\s+analisad\w*|a\s+verificar|a\s+definir|TBD|TODO)\b"
)
DIRECT_EVIDENCE_KINDS = {"command", "browser", "manual", "screenshot"}
DIRECT_EVIDENCE_STATUSES = {"passed", "failed", "blocked", "not_run"}


def parse_direct_evidence(entries: list[str]) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    for raw in entries:
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as error:
            raise BMError(f"--evidence exige JSON válido: {error.msg}") from error
        if not isinstance(value, dict):
            raise BMError("--evidence exige um objeto JSON")
        kind = value.get("kind")
        status = value.get("status")
        summary = value.get("summary")
        if kind not in DIRECT_EVIDENCE_KINDS:
            raise BMError(
                "--evidence.kind deve ser command, browser, manual ou screenshot"
            )
        if status not in DIRECT_EVIDENCE_STATUSES:
            raise BMError(
                "--evidence.status deve ser passed, failed, blocked ou not_run"
            )
        if not isinstance(summary, str) or not summary.strip():
            raise BMError("--evidence.summary é obrigatório")
        check_id = value.get("check_id")
        if check_id is not None and (
            not isinstance(check_id, str) or not check_id.strip()
        ):
            raise BMError("--evidence.check_id, quando presente, deve ser texto não vazio")
        if kind == "command":
            command = value.get("command")
            exit_code = value.get("exit_code")
            if not isinstance(command, str) or not command.strip():
                raise BMError("evidência de comando exige o campo command")
            if not isinstance(exit_code, int) or isinstance(exit_code, bool):
                raise BMError("evidência de comando exige exit_code inteiro")
            if status == "passed" and exit_code != 0:
                raise BMError(
                    "evidência de comando com status passed exige exit_code 0"
                )
        else:
            evidence_ref = value.get("evidence")
            if not isinstance(evidence_ref, str) or not evidence_ref.strip():
                raise BMError(
                    f"evidência {kind} exige o campo evidence com caminho ou descrição"
                )
        parsed.append(value)
    return parsed


def direct_tree_digest(root: Path) -> str:
    head = run_git(["rev-parse", "HEAD"], root)
    diff = run_git(["diff", "HEAD"], root)
    _, paths = direct_git_status(root)
    hasher = hashlib.sha256()
    hasher.update(head.encode("utf-8"))
    hasher.update(diff.encode("utf-8"))
    for path in paths:
        target = root / path
        hasher.update(path.encode("utf-8"))
        if target.is_file() and not target.is_symlink():
            hasher.update(target.read_bytes())
    return hasher.hexdigest()


def current_direct_evidence(entries: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    current: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in entries:
        if entry["kind"] == "command":
            key = ("command", entry["command"])
        else:
            key = (entry["kind"], entry.get("check_id") or entry["evidence"])
        current[key] = entry
    return current


def parse_direct_waivers(entries: list[str], planned: list[str]) -> dict[str, str]:
    waived: dict[str, str] = {}
    for entry in entries:
        matched: tuple[str, str] | None = None
        for command in sorted(planned, key=len, reverse=True):
            prefix = command + ":"
            if entry.startswith(prefix) and entry[len(prefix):].strip():
                matched = (command, entry[len(prefix):].strip())
                break
        if matched is None:
            command_part, separator, justification = entry.partition(":")
            if not separator or not command_part.strip() or not justification.strip():
                raise BMError(
                    "--waive-verification exige o formato 'comando: justificativa'"
                )
            matched = (command_part.strip(), justification.strip())
        waived[matched[0]] = matched[1]
    return waived


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


def validate_direct_current_state(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        raise BMError("direct start exige --current-state com síntese factual do repositório")
    if len(text) < 20 or DIRECT_GENERIC_CURRENT_STATE.search(text):
        raise BMError(
            "--current-state deve conter síntese factual obtida por leitura localizada; "
            "texto genérico como 'a confirmar' ou 'não analisado' não é aceito"
        )
    return text


def direct_brief_digest(fields: dict[str, Any]) -> str:
    payload = {
        "objective": fields["objective"],
        "current_state": fields["current_state"],
        "scope": fields["scope"],
        "non_objectives": sorted(fields["non_objectives"]),
        "acceptance": sorted(fields["acceptance"]),
        "risk": fields["risk"],
        "change_kind": fields["change_kind"],
        "hazards": sorted(set(fields["hazards"])),
        "subsystems": fields["subsystems"],
        "verification_commands": sorted(fields["verification_commands"]),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def stored_brief_digest(state: dict[str, Any]) -> str:
    declared = state.get("brief_digest")
    if isinstance(declared, str) and re.fullmatch(r"[0-9a-f]{64}", declared):
        return declared
    hazards = state.get(
        "hazards_declared",
        [
            item
            for item in state.get("hazards", [])
            if not item.startswith(("risk:", "independent-subsystems:"))
        ],
    )
    return direct_brief_digest(
        {
            "objective": state["objective"],
            "current_state": state["current_state"],
            "scope": state["scope"],
            "non_objectives": state["non_objectives"],
            "acceptance": state["acceptance"],
            "risk": state["risk"],
            "change_kind": state["change_kind"],
            "hazards": hazards,
            "subsystems": state.get("subsystems", 1),
            "verification_commands": state["verification_commands"],
        }
    )


def direct_exclude_file(root: Path) -> Path:
    return Path(
        run_git(["rev-parse", "--path-format=absolute", "--git-path", "info/exclude"], root)
    )


def ensure_direct_scratch_excluded(root: Path) -> bool:
    exclude = direct_exclude_file(root)
    content = exclude.read_text(encoding="utf-8") if exclude.is_file() else ""
    patterns = {
        line.strip()
        for line in content.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    if patterns & {"/.superpowers/", ".superpowers/", "/.superpowers"}:
        return False
    exclude.parent.mkdir(parents=True, exist_ok=True)
    if content and not content.endswith("\n"):
        content += "\n"
    content += ROOT_SUPERPOWERS_IGNORE + "\n"
    exclude.write_text(content, encoding="utf-8")
    return True


def assert_direct_scratch_untracked(root: Path) -> None:
    _, paths = direct_git_status(root)
    leaked = sorted(
        path
        for path in paths
        if path == ".superpowers" or path.startswith(".superpowers/")
    )
    if leaked:
        raise BMError(
            "BLOQUEADO: o scratch direto aparece no git status: " + ", ".join(leaked[:8]),
            EXIT_BLOCKED,
        )


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
    completed = subprocess.run(
        ["git", "status", "--porcelain=v1", "--untracked-files=all"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise BMError(completed.stderr.strip() or "comando Git falhou")
    lines = completed.stdout.splitlines()
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
    update_brief: bool = False,
) -> dict[str, Any]:
    root = direct_repo(repo)
    directory = direct_directory(root, slug)
    branch = run_git(["branch", "--show-current"], root)
    if not branch:
        raise BMError("BLOQUEADO: executar-direto não funciona em detached HEAD", EXIT_UNSAFE_WORKSPACE)
    current_state = validate_direct_current_state(current_state)
    ensure_direct_scratch_excluded(root)
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
    incoming_digest = direct_brief_digest(
        {
            "objective": objective,
            "current_state": current_state,
            "scope": scope,
            "non_objectives": non_objectives,
            "acceptance": acceptance,
            "risk": risk,
            "change_kind": change_kind,
            "hazards": hazards,
            "subsystems": subsystems,
            "verification_commands": verification_commands,
        }
    )

    existing_path = directory / ".state.json"
    if existing_path.is_file():
        existing = read_direct_state(root, slug)
        if existing.get("status") in DIRECT_TERMINAL_STATUSES:
            raise BMError(
                f"BLOQUEADO: execução direta {slug} está em estado terminal "
                f"{existing['status']}; use um novo slug (ou 'direct reopen' para "
                "execução bloqueada). Execução escalada continua em /sdd-planning.",
                EXIT_BLOCKED,
            )
        if stored_brief_digest(existing) != incoming_digest:
            if not update_brief:
                raise BMError(
                    "BLOQUEADO: digest do brief divergente do registrado; use um novo "
                    "slug ou atualize explicitamente o brief com --update-brief",
                    EXIT_BLOCKED,
                )
            if mode == "escalated":
                raise BMError(
                    "BLOQUEADO: a atualização do brief introduz risco/hazard que exige "
                    "escalonamento; use um novo slug e /sdd-planning",
                    EXIT_BLOCKED,
                )
            if change_kind in DIRECT_RED_GREEN_KINDS:
                updated_strategy = "red_green"
            elif change_kind == "visual":
                updated_strategy = "visual_evidence"
            else:
                updated_strategy = "affected_checks"
            existing.update(
                {
                    "objective": objective,
                    "current_state": current_state,
                    "scope": scope,
                    "non_objectives": non_objectives,
                    "acceptance": acceptance,
                    "risk": risk,
                    "change_kind": change_kind,
                    "verification_strategy": updated_strategy,
                    "hazards_declared": sorted(set(hazards)),
                    "subsystems": subsystems,
                    "verification_commands": verification_commands,
                    "brief_digest": incoming_digest,
                    "verification": "pending",
                    "evidence": [],
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            existing["results"] = existing.get("results", []) + [
                "Brief atualizado explicitamente; verificação e evidências anteriores invalidadas."
            ]
            write_direct_state(root, existing)
            (directory / "BRIEF.md").write_text(
                render_direct_brief(existing), encoding="utf-8"
            )
        ensure_direct_branch(root, existing)
        git_state, observed_paths = direct_git_status(root)
        existing["git_status"] = git_state
        existing["observed_changes"] = observed_paths
        assert_direct_scratch_untracked(root)
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
        "hazards_declared": sorted(set(hazards)),
        "brief_digest": incoming_digest,
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
        "evidence": [],
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
    assert_direct_scratch_untracked(root)
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
    evidence: list[str],
) -> dict[str, Any]:
    root = direct_repo(repo)
    state = read_direct_state(root, slug)
    ensure_direct_branch(root, state)
    if state["status"] != "active":
        raise BMError("BLOQUEADO: somente execução direta ativa aceita checkpoint", EXIT_BLOCKED)
    new_evidence = parse_direct_evidence(evidence)
    if new_evidence:
        brief_now = stored_brief_digest(state)
        tree_now = direct_tree_digest(root)
        for entry in new_evidence:
            entry["brief_digest"] = brief_now
            entry["tree_digest"] = tree_now
    state["evidence"] = state.get("evidence", []) + new_evidence
    if verification == "passed" and not any(
        entry["status"] == "passed" for entry in state["evidence"]
    ):
        raise BMError(
            "BLOQUEADO: checkpoint com --verification passed exige ao menos uma "
            "evidência estruturada aprovada registrada via --evidence",
            EXIT_BLOCKED,
        )
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
    blockers: list[str],
    accepted_unrecorded: list[str],
    waive_verification: list[str],
) -> dict[str, Any]:
    root = direct_repo(repo)
    state = read_direct_state(root, slug)
    if state["status"] in DIRECT_TERMINAL_STATUSES:
        raise BMError(
            f"BLOQUEADO: execução direta {slug} já está em estado terminal "
            f"{state['status']}; finish não pode ser repetido. Use um novo slug ou "
            "'direct reopen' para execução bloqueada.",
            EXIT_BLOCKED,
        )
    ensure_direct_branch(root, state)
    accepted: dict[str, str] = {}
    for entry in accepted_unrecorded:
        path_part, separator, justification = entry.partition(":")
        if not separator or not path_part.strip() or not justification.strip():
            raise BMError(
                "--accept-unrecorded exige o formato 'caminho: justificativa'"
            )
        accepted[path_part.strip()] = justification.strip()
    evidence_entries = state.get("evidence", [])
    current_evidence = current_direct_evidence(evidence_entries)
    if status == "completed":
        waived = parse_direct_waivers(waive_verification, state["verification_commands"])
        problems: list[str] = []
        if blockers:
            problems.append("--blocker é incompatível com --status completed")
        if state["verification"] != "passed":
            problems.append(
                f"verificação atual é {state['verification']!r}; conclusão exige "
                "checkpoint com --verification passed"
            )
        if not evidence_entries:
            problems.append(
                "nenhuma evidência estruturada registrada; registre com "
                "checkpoint --evidence '{\"kind\": ..., \"status\": ...}'"
            )
        brief_now = stored_brief_digest(state)
        tree_now = direct_tree_digest(root)
        stale = [
            entry
            for entry in current_evidence.values()
            if entry.get("brief_digest") != brief_now
            or entry.get("tree_digest") != tree_now
        ]
        if stale:
            problems.append(
                "evidência obsoleta (brief ou código mudou depois do registro): "
                + "; ".join(
                    str(entry.get("command") or entry.get("evidence"))
                    for entry in stale[:5]
                )
                + "; reexecute as verificações no estado final e registre novo checkpoint"
            )
        not_passed = [
            entry
            for entry in current_evidence.values()
            if entry["status"] != "passed"
        ]
        if not_passed:
            problems.append(
                "evidência atual não aprovada: "
                + "; ".join(
                    f"{entry.get('command') or entry.get('evidence')} ({entry['status']})"
                    for entry in not_passed[:5]
                )
            )
        passed_commands = {
            key[1]
            for key, entry in current_evidence.items()
            if key[0] == "command" and entry["status"] == "passed"
        }
        unknown_waivers = sorted(set(waived) - set(state["verification_commands"]))
        if unknown_waivers:
            problems.append(
                "dispensa não corresponde a comando planejado: "
                + ", ".join(unknown_waivers)
            )
        missing_commands = [
            command
            for command in state["verification_commands"]
            if command not in passed_commands and command not in waived
        ]
        if missing_commands:
            problems.append(
                "comando de verificação planejado sem evidência aprovada: "
                + ", ".join(missing_commands)
                + "; registre evidência estruturada ou dispense explicitamente com "
                "--waive-verification 'comando: justificativa'"
            )
        if not behaviors:
            problems.append("informe ao menos um comportamento entregue com --behavior")
        if state["blockers"]:
            problems.append(
                "bloqueios abertos impedem conclusão: " + ", ".join(state["blockers"][:5])
            )
        _, observed_paths = direct_git_status(root)
        recorded = set(state["changed_files"])
        unknown_accepted = sorted(set(accepted) - set(observed_paths))
        if unknown_accepted:
            problems.append(
                "aceite não corresponde a alteração observada: "
                + ", ".join(unknown_accepted)
            )
        unrecorded = sorted(set(observed_paths) - recorded - set(accepted))
        if unrecorded:
            problems.append(
                "alterações não registradas no resultado: "
                + ", ".join(unrecorded[:8])
                + "; registre com checkpoint --changed-file ou aceite explicitamente "
                "com --accept-unrecorded 'caminho: justificativa'"
            )
        if problems:
            raise BMError(
                "BLOQUEADO: conclusão sem verificação suficiente:\n- " + "\n- ".join(problems),
                EXIT_BLOCKED,
            )
        if accepted:
            state["changed_files"] = sorted(recorded | set(accepted))
            limitations = limitations + [
                f"Alteração não registrada aceita: {path} — {justification}"
                for path, justification in sorted(accepted.items())
            ]
        if waived:
            limitations = limitations + [
                f"Comando de verificação dispensado: {command} — {justification}"
                for command, justification in sorted(waived.items())
            ]
    else:
        merged_blockers = state["blockers"] + [
            item for item in blockers if item not in state["blockers"]
        ]
        if not merged_blockers and not limitations:
            raise BMError(
                f"BLOQUEADO: status {status} exige motivo registrado via --blocker "
                "ou --limitation",
                EXIT_BLOCKED,
            )
        state["blockers"] = merged_blockers
    verification_results = verification_results + [
        (
            f"{entry['kind']}: {entry.get('command') or entry.get('evidence')} — "
            f"{entry['status']} — {entry['summary']}"
        )
        for entry in current_evidence.values()
    ]
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


def direct_reopen(repo: Path, slug: str, next_action: str) -> dict[str, Any]:
    root = direct_repo(repo)
    state = read_direct_state(root, slug)
    if state["status"] == "active":
        raise BMError("execução direta já está ativa; reabertura desnecessária")
    if state["status"] == "escalated":
        raise BMError(
            "BLOQUEADO: execução escalada não pode ser reaberta nem concluída; "
            "use um novo slug ou continue em /sdd-planning",
            EXIT_BLOCKED,
        )
    if state["status"] == "completed":
        raise BMError(
            "BLOQUEADO: execução concluída é imutável; use um novo slug",
            EXIT_BLOCKED,
        )
    ensure_direct_branch(root, state)
    directory = direct_directory(root, slug)
    reopen_count = int(state.get("reopen_count", 0)) + 1
    previous_result = directory / "RESULT.md"
    if previous_result.is_file():
        archive = directory / f"RESULT-{reopen_count:02d}-{state['status']}.md"
        archive.write_bytes(previous_result.read_bytes())
    state["reopen_count"] = reopen_count
    state["status"] = "active"
    state["next_action"] = next_action
    state["git_status"], _ = direct_git_status(root)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    write_direct_state(root, state)
    (directory / "PROGRESS.md").write_text(render_direct_progress(state), encoding="utf-8")
    (directory / "RESULT.md").write_text(render_direct_result(state), encoding="utf-8")
    return {**direct_payload(state, directory), "reopened": True, "reopen_count": reopen_count}


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
        "planning_quality_version": state.get("planning", {}).get("quality_version"),
        "readiness": state.get("planning", {}).get("readiness"),
        "user_actions": state.get("planning", {}).get("user_actions"),
        "design_manifest": state.get("planning", {}).get("design_manifest"),
        "change_root": state.get("planning", {}).get("change_root"),
        "current_specs": state.get("planning", {}).get("current_specs"),
        "checker": state.get("planning", {}).get("checker"),
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
        f"- Planejamento: {summary['planning_status']} / qualidade v{summary.get('planning_quality_version') or 'legado'}\n"
        f"- Readiness: {summary.get('readiness') or 'não aplicável'} / checker {((summary.get('checker') or {}).get('status') or 'não aplicável')}\n"
        f"- Design: {summary.get('design_manifest') or 'não aplicável'}\n"
        f"- Specs atuais: {summary.get('current_specs') or 'não aplicável'} / mudança {summary.get('change_root') or 'não aplicável'}\n"
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


def direct_risk_from_args(args: argparse.Namespace) -> dict[str, Any]:
    overrides = [
        name
        for name, enabled in (
            ("multiple_objectives", args.multiple_objectives),
            ("destructive_migration", args.destructive_migration),
            ("uncontrolled_concurrency", args.uncontrolled_concurrency),
            ("undefined_ownership", args.undefined_ownership),
            ("ambiguous_financial_rule", args.ambiguous_financial_rule),
            ("new_material_architecture", args.new_material_architecture),
        )
        if enabled
    ]
    return v04.classify_quick_risk(
        args.scope_score,
        args.external_effect_score,
        args.migration_score,
        args.concurrency_score,
        args.money_score,
        overrides,
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="bm", description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate-state")
    validate.add_argument("state", type=Path)
    validate.add_argument("--schema", type=Path)

    model = commands.add_parser("model")
    model.add_argument("action", choices=["init", "validate"])
    model.add_argument("--repo", type=Path, default=Path.cwd())
    model.add_argument("--change")

    coherence = commands.add_parser("coherence")
    coherence.add_argument("action", choices=["check", "approve"])
    coherence.add_argument("--repo", type=Path, default=Path.cwd())
    coherence.add_argument("--change", required=True)
    coherence.add_argument("--structural-only", action="store_true")
    coherence.add_argument("--semantic-report", type=Path)
    coherence.add_argument("--digest")
    coherence.add_argument("--approved-by")

    impact = commands.add_parser("impact")
    impact.add_argument("action", choices=["analyze"])
    impact.add_argument("--repo", type=Path, default=Path.cwd())
    impact.add_argument("--change", required=True)
    impact.add_argument("--plan", required=True)
    impact.add_argument("--changed-contract", action="append", default=[])
    impact.add_argument("--changed-ownership", action="append", default=[])
    impact.add_argument("--changed-interface", action="append", default=[])
    impact.add_argument("--changed-data", action="append", default=[])
    impact.add_argument("--changed-migration", action="append", default=[])
    impact.add_argument("--changed-journey", action="append", default=[])
    impact.add_argument("--changed-effect", action="append", default=[])
    impact.add_argument("--changed-invariant", action="append", default=[])
    impact.add_argument("--global-change", action="store_true")

    plan_result = commands.add_parser("plan")
    plan_result.add_argument("action", choices=["complete"])
    plan_result.add_argument("--repo", type=Path, default=Path.cwd())
    plan_result.add_argument("--change", required=True)
    plan_result.add_argument("--plan", required=True)
    plan_result.add_argument("--actual-delta", type=Path, required=True)
    plan_result.add_argument("--result", required=True)
    plan_result.add_argument("--verification", action="append", default=[])

    debug = commands.add_parser("debug")
    debug.add_argument(
        "action", choices=["start", "list", "status", "resume", "checkpoint", "finish"]
    )
    debug.add_argument("--repo", type=Path, default=Path.cwd())
    debug.add_argument("--id")
    debug.add_argument("--objective")
    debug.add_argument("--expected")
    debug.add_argument("--actual")
    debug.add_argument("--environment")
    debug.add_argument("--origin-ref", action="append", default=[])
    debug.add_argument("--origin-evidence")
    debug.add_argument(
        "--relation", choices=["caused_by", "detected_in", "regression_of"]
    )
    debug.add_argument(
        "--event",
        choices=[
            "reproduced",
            "diagnosed",
            "red",
            "fixing",
            "green",
            "regression_checked",
            "documented",
        ],
    )
    debug.add_argument("--evidence")
    debug.add_argument("--hypothesis", action="append", default=[])
    debug.add_argument("--experiment", action="append", default=[])
    debug.add_argument("--eliminated-hypothesis", action="append", default=[])
    debug.add_argument("--root-cause")
    debug.add_argument("--neighbor-regression", action="append", default=[])
    debug.add_argument("--residual-risk")
    debug.add_argument("--status", choices=["resolved", "blocked", "escalated"])
    debug.add_argument("--reason")

    migrate = commands.add_parser("migrate")
    migrate.add_argument("action", choices=["check", "apply"])
    migrate.add_argument("--repo", type=Path, default=Path.cwd())

    snap = commands.add_parser("snapshot")
    snap.add_argument("action", choices=["create", "verify"])
    snap.add_argument("state", type=Path)
    snap.add_argument("--root", type=Path, required=True)

    planning_check = commands.add_parser("planning-audit")
    planning_check.add_argument("state", type=Path)
    planning_check.add_argument("--root", type=Path, required=True)
    planning_check.add_argument("--strict", action="store_true")

    design = commands.add_parser("design-audit")
    design.add_argument("action", choices=["seal", "verify"])
    design.add_argument("--root", type=Path, required=True)
    design.add_argument("--scope", type=Path, required=True)
    design.add_argument("--manifest", type=Path, required=True)

    checker = commands.add_parser("planning-check")
    checker.add_argument("action", choices=["record"])
    checker.add_argument("--state", type=Path, required=True)
    checker.add_argument("--root", type=Path, required=True)
    checker.add_argument("--report", type=Path, required=True)

    change = commands.add_parser("change-policy")
    change.add_argument("--scope-change", action="store_true")
    change.add_argument("--public-contract-change", action="store_true")
    change.add_argument("--approved-design-change", action="store_true")
    change.add_argument("--new-cost", action="store_true")
    change.add_argument("--irreversible-action", action="store_true")
    change.add_argument("--external-impossibility", action="store_true")
    change.add_argument("--critical-invariant", action="store_true")
    change.add_argument("--plan-command", action="store_true")
    change.add_argument("--file-location", action="store_true")
    change.add_argument("--internal-order", action="store_true")

    close = commands.add_parser("cycle-close")
    close.add_argument("--repo", type=Path, default=Path.cwd())
    close.add_argument("--change", required=True)

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
    decide.add_argument("--risk-seam")
    decide.add_argument("--seam-round", type=int, default=None)
    decide.add_argument(
        "--structural-finding",
        action="append",
        default=[],
        choices=list(STRUCTURAL_FINDING_CLASSES),
    )
    decide.add_argument("--consecutive-seam-findings", type=int, default=0)

    workspace = commands.add_parser("workspace")
    workspace.add_argument("action", choices=["create", "check", "locate", "resume"])
    workspace.add_argument("--repo", type=Path, default=Path.cwd())
    workspace.add_argument("--plan")
    workspace.add_argument("--change")
    workspace.add_argument("--target", type=Path)

    brief = commands.add_parser("task-brief")
    brief.add_argument("--plan", type=Path, required=True)
    brief_selector = brief.add_mutually_exclusive_group(required=True)
    brief_selector.add_argument("--task")
    brief_selector.add_argument("--tasks")
    brief_selector.add_argument("--group")
    brief.add_argument("--state", type=Path)
    brief.add_argument("--root", type=Path)
    brief.add_argument("--hydrate-context", action="store_true")
    brief.add_argument("--ledger-tail-lines", type=int, default=40)
    brief.add_argument("--output", type=Path, required=True)

    spec_delta = commands.add_parser("spec-diff")
    spec_delta.add_argument("--root", type=Path, required=True)
    spec_delta.add_argument("--base", type=Path, required=True)
    spec_delta.add_argument("--target", type=Path, required=True)
    spec_delta.add_argument("--output", type=Path, required=True)

    mutation_evidence = commands.add_parser("mutation-evidence")
    mutation_evidence.add_argument("action", choices=["verify"])
    mutation_evidence.add_argument("--state", type=Path, required=True)
    mutation_evidence.add_argument("--root", type=Path, required=True)
    mutation_evidence.add_argument("--plan", required=True)
    mutation_evidence.add_argument("--risk-seam", required=True)
    mutation_evidence.add_argument(
        "--tool", choices=["normalized", "stryker"], required=True
    )
    mutation_evidence.add_argument("--command", dest="mutation_command", required=True)
    mutation_evidence.add_argument("--report", type=Path, required=True)
    mutation_evidence.add_argument("--revision", required=True)
    mutation_evidence.add_argument("--classifications", type=Path)
    mutation_evidence.add_argument("--output", type=Path, required=True)

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
    proof.add_argument(
        "--mutation-evidence", action="append", type=Path, default=[]
    )
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
    direct.add_argument(
        "action",
        choices=["classify", "start", "status", "checkpoint", "finish", "reopen"],
    )
    direct.add_argument("--repo", type=Path, default=Path.cwd())
    direct.add_argument("--slug")
    direct.add_argument("--objective")
    direct.add_argument("--scope")
    direct.add_argument("--acceptance", action="append", default=[])
    direct.add_argument("--verification", action="append", default=[])
    direct.add_argument("--checkpoint")
    direct.add_argument("--changed-file", action="append", default=[])
    direct.add_argument(
        "--command",
        dest="executed_commands",
        metavar="COMMAND",
        action="append",
        default=[],
    )
    direct.add_argument("--blocker", action="append", default=[])
    direct.add_argument("--next-action")
    direct.add_argument(
        "--status", choices=["completed", "blocked", "escalated"]
    )
    direct.add_argument("--behavior", action="append", default=[])
    direct.add_argument("--limitation", action="append", default=[])
    direct.add_argument("--evidence", action="append", default=[])
    direct.add_argument("--scope-score", type=int, choices=[0, 1, 2], default=0)
    direct.add_argument(
        "--external-effect-score", type=int, choices=[0, 1, 2], default=0
    )
    direct.add_argument("--migration-score", type=int, choices=[0, 1, 2], default=0)
    direct.add_argument("--concurrency-score", type=int, choices=[0, 1, 2], default=0)
    direct.add_argument("--money-score", type=int, choices=[0, 1, 2], default=0)
    direct.add_argument("--guard", action="append", default=[])
    direct.add_argument("--webhook-flow", action="store_true")
    direct.add_argument("--payment-flow", action="store_true")
    direct.add_argument("--production-authorized", action="store_true")
    direct.add_argument("--multiple-objectives", action="store_true")
    direct.add_argument("--destructive-migration", action="store_true")
    direct.add_argument("--uncontrolled-concurrency", action="store_true")
    direct.add_argument("--undefined-ownership", action="store_true")
    direct.add_argument("--ambiguous-financial-rule", action="store_true")
    direct.add_argument("--new-material-architecture", action="store_true")

    updater = commands.add_parser("update-bm")
    updater.add_argument("--check", action="store_true")
    updater.add_argument(
        "--skills-root",
        type=Path,
        default=_SCRIPT_DIR.parents[1],
    )
    updater.add_argument("--timeout", type=float, default=15.0)
    updater.add_argument(
        "--format", choices=["text", "json"], default="text"
    )

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
        elif args.command == "model":
            if args.action == "init":
                initialized = v04.init_workspace(args.repo)
                if args.change:
                    emit(v04_planning.create_change(args.repo, args.change))
                else:
                    emit(initialized)
            else:
                if args.change:
                    emit(v04_planning.validate_change_model(args.repo, args.change))
                else:
                    emit(v04.validate_workspace(args.repo))
        elif args.command == "coherence":
            if args.action == "check":
                emit(
                    v04_planning.coherence_check(
                        args.repo,
                        args.change,
                        structural_only=args.structural_only,
                        semantic_report=args.semantic_report,
                    )
                )
            else:
                if not args.digest or not args.approved_by:
                    raise BMError("coherence approve exige --digest e --approved-by")
                emit(
                    v04_planning.coherence_approve(
                        args.repo,
                        args.change,
                        digest=args.digest,
                        approved_by=args.approved_by,
                    )
                )
        elif args.command == "impact":
            emit(
                v04_planning.impact_analyze(
                    args.repo,
                    args.change,
                    args.plan,
                    changed_contracts=args.changed_contract,
                    changed_ownership=args.changed_ownership,
                    changed_interfaces=args.changed_interface,
                    changed_data=args.changed_data,
                    changed_migrations=args.changed_migration,
                    changed_journeys=args.changed_journey,
                    changed_effects=args.changed_effect,
                    changed_invariants=args.changed_invariant,
                    global_change=args.global_change,
                )
            )
        elif args.command == "plan":
            emit(
                v04_planning.plan_complete(
                    args.repo,
                    args.change,
                    args.plan,
                    actual_delta=args.actual_delta,
                    result=args.result,
                    verification=args.verification,
                )
            )
        elif args.command == "migrate":
            if args.action == "check":
                emit(v04.migration_check(args.repo))
            else:
                emit(v04.migration_apply(args.repo))
        elif args.command == "debug":
            if args.action == "start":
                if not all((args.objective, args.expected, args.actual, args.environment)):
                    raise BMError(
                        "debug start exige --objective, --expected, --actual e --environment"
                    )
                v04.require_workspace(args.repo, create=True)
                emit(
                    v04.debug_start(
                        args.repo,
                        args.objective,
                        args.expected,
                        args.actual,
                        args.environment,
                        args.origin_ref,
                        args.relation,
                        args.origin_evidence,
                    )
                )
            elif args.action in {"list", "status", "resume"}:
                v04.require_workspace(args.repo)
                if args.action in {"status", "resume"} and not args.id:
                    raise BMError(f"debug {args.action} exige --id")
                emit(v04.debug_status(args.repo, args.id if args.action != "list" else None))
            elif args.action == "checkpoint":
                v04.require_workspace(args.repo)
                if not all((args.id, args.event, args.evidence)):
                    raise BMError("debug checkpoint exige --id, --event e --evidence")
                emit(
                    v04.debug_checkpoint(
                        args.repo,
                        args.id,
                        args.event,
                        args.evidence,
                        hypotheses=args.hypothesis,
                        experiments=args.experiment,
                        eliminated_hypotheses=args.eliminated_hypothesis,
                        root_cause=args.root_cause,
                        neighboring_regressions=args.neighbor_regression,
                        residual_risk=args.residual_risk,
                    )
                )
            else:
                v04.require_workspace(args.repo)
                if not args.id:
                    raise BMError("debug finish exige --id")
                emit(
                    v04.debug_finish(
                        args.repo,
                        args.id,
                        args.status or "resolved",
                        args.reason,
                    )
                )
        elif args.command == "snapshot":
            emit(snapshot(args.state, args.root, args.action == "verify"))
        elif args.command == "planning-audit":
            emit(planning_audit(args.state, args.root, args.strict))
        elif args.command == "design-audit":
            emit(
                design_audit(
                    args.root,
                    args.scope,
                    args.manifest,
                    args.action == "seal",
                )
            )
        elif args.command == "planning-check":
            emit(planning_check_record(args.state, args.root, args.report))
        elif args.command == "change-policy":
            emit(
                change_policy(
                    scope_change=args.scope_change,
                    public_contract_change=args.public_contract_change,
                    approved_design_change=args.approved_design_change,
                    new_cost=args.new_cost,
                    irreversible_action=args.irreversible_action,
                    external_impossibility=args.external_impossibility,
                    critical_invariant=args.critical_invariant,
                    plan_command=args.plan_command,
                    file_location=args.file_location,
                    internal_order=args.internal_order,
                )
            )
        elif args.command == "cycle-close":
            v04.require_workspace(args.repo)
            if not args.change:
                raise BMError("cycle-close 0.4 exige --change")
            emit(v04_planning.close_change(args.repo, args.change))
        elif args.command == "policy":
            emit(
                policy(
                    args.profile,
                    args.risk,
                    args.change,
                    args.manual_pdf,
                    args.manual_in_scope,
                    args.round,
                    args.risk_seam,
                    args.seam_round,
                    tuple(args.structural_finding),
                    args.consecutive_seam_findings,
                )
            )
        elif args.command == "workspace":
            v04.require_workspace(args.repo)
            if args.action == "create":
                if not args.plan or not args.change:
                    raise BMError("--change e --plan são obrigatórios para criar workspace 0.4")
                emit(
                    v04_planning.execution_workspace_create(
                        args.repo, args.change, args.plan, args.target
                    )
                )
            elif args.action == "check":
                emit(v04_planning.execution_workspace_check(args.repo))
            else:
                if not args.plan or not args.change:
                    raise BMError(
                        f"--change e --plan são obrigatórios para {args.action} no método 0.4"
                    )
                emit(
                    v04_planning.execution_workspace_locate(
                        args.repo,
                        args.change,
                        args.plan,
                        resume=args.action == "resume",
                    )
                )
        elif args.command == "task-brief":
            emit(
                write_task_brief(
                    args.plan,
                    args.task,
                    args.tasks,
                    args.group,
                    args.output,
                    args.state,
                    args.root,
                    args.hydrate_context,
                    args.ledger_tail_lines,
                )
            )
        elif args.command == "spec-diff":
            try:
                emit(
                    spec_diff(
                        root=args.root,
                        base=args.base,
                        target=args.target,
                        output=args.output,
                    )
                )
            except ValueError as error:
                raise BMError(str(error)) from error
        elif args.command == "mutation-evidence":
            try:
                mutation_result = mutation_evidence_verify(
                    root=args.root,
                    state=validate_state(args.state),
                    plan_id=args.plan,
                    risk_seam=args.risk_seam,
                    tool=args.tool,
                    command=args.mutation_command,
                    report=args.report,
                    output=args.output,
                    revision=args.revision,
                    classifications=args.classifications,
                )
            except ValueError as error:
                raise BMError(str(error)) from error
            if mutation_result["status"] != "passed":
                raise BMError(
                    "BLOQUEADO: mutation evidence bloqueada; consulte "
                    + mutation_result["output"],
                    EXIT_BLOCKED,
                )
            emit(mutation_result)
        elif args.command == "report":
            emit(write_report(args.brief, args.output))
        elif args.command == "review-package":
            emit(write_review_package(args.cwd, args.base, args.head, args.brief, args.report, args.output))
        elif args.command == "checkpoint":
            emit(write_checkpoint(args.state, args.ledger, args.cwd, args.output))
        elif args.command == "proof-map":
            emit(
                write_proof_map(
                    args.state,
                    args.evidence,
                    args.output,
                    args.mutation_evidence,
                )
            )
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
            risk = direct_risk_from_args(args)
            if args.action == "classify":
                emit(risk)
            elif args.action == "start":
                if not all((args.objective, args.scope)):
                    raise BMError("direct start exige --objective e --scope")
                if not args.acceptance or not args.verification:
                    raise BMError(
                        "direct start exige ao menos um --acceptance e um --verification"
                    )
                v04.require_workspace(args.repo, create=True)
                emit(
                    v04.quick_start(
                        args.repo,
                        args.objective,
                        args.scope,
                        args.acceptance,
                        args.verification,
                        risk,
                        args.guard,
                        webhook_flow=args.webhook_flow,
                        payment_flow=args.payment_flow,
                    )
                )
            elif args.action == "status":
                v04.require_workspace(args.repo)
                emit(v04.quick_status(args.repo, args.slug))
            elif args.action == "checkpoint":
                v04.require_workspace(args.repo)
                if not all((args.slug, args.checkpoint, args.next_action)):
                    raise BMError(
                        "direct checkpoint exige --slug, --checkpoint e --next-action"
                    )
                emit(
                    v04.quick_checkpoint(
                        args.repo,
                        args.slug,
                        args.checkpoint,
                        args.changed_file,
                        args.executed_commands,
                        args.evidence,
                        args.blocker,
                        args.next_action,
                    )
                )
            elif args.action == "finish":
                v04.require_workspace(args.repo)
                if not all((args.slug, args.status, args.next_action)):
                    raise BMError("direct finish exige --slug, --status e --next-action")
                emit(
                    v04.quick_finish(
                        args.repo,
                        args.slug,
                        args.status,
                        args.behavior,
                        [*args.verification, *args.evidence],
                        args.limitation,
                        args.next_action,
                        args.blocker,
                        args.production_authorized,
                    )
                )
            else:
                raise BMError("ORDER_VIOLATION: quick 0.4 terminal é imutável")
        elif args.command == "update-bm":
            try:
                update_result = update_bianchini_method(
                    skills_root=args.skills_root,
                    check_only=args.check,
                    timeout=args.timeout,
                )
            except BMUpdateError as error:
                raise BMError(str(error), error.exit_code) from error
            if args.format == "json":
                emit(update_result)
            else:
                print(render_update_result(update_result), end="")
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
    except v04.WorkflowError as error:
        print(str(error), file=sys.stderr)
        return EXIT_BLOCKED
    except v04_planning.PlanningError as error:
        print(str(error), file=sys.stderr)
        return EXIT_BLOCKED
    except (OSError, UnicodeError, subprocess.SubprocessError, KeyError, TypeError, ValueError) as error:
        print(f"erro de entrada/IO: {error}", file=sys.stderr)
        return EXIT_INVALID


if __name__ == "__main__":
    raise SystemExit(main())
