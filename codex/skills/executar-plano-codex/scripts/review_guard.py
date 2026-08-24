#!/usr/bin/env python3
"""Guarda determinística da convergência do overlay executar-plano-codex."""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import hmac
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable


SCHEMA_VERSION = 2
MAX_FIX_ROUNDS = 2
MAX_REDESIGNS_PER_UNIT = 1
IDENTIFIER = re.compile(r"^[A-Za-z0-9._-]+$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
BRIEF_UNIT_DIGEST = re.compile(r"(?m)^- Unit `[^`]+` SHA-256: `([0-9a-f]{64})`$")
SEVERITIES = {"critical", "important", "minor", "note"}
BLOCKING_SEVERITIES = {"critical", "important"}
STRUCTURAL_CLASSES = {
    "architecture_boundary",
    "data_model",
    "public_contract",
    "state_machine",
    "cross_cutting_invariant",
}
STOP_KINDS = {
    "essential_external_credential",
    "destructive_action",
    "new_cost",
    "material_change",
    "real_impossibility",
}
MATERIAL_CHANGE_KINDS = {
    "scope",
    "public_contract",
    "approved_design",
    "critical_invariant",
}
PHASES = {
    "review_frozen",
    "fixing",
    "awaiting_review",
    "redesigning",
    "parked",
    "completed",
    "stopped",
}
TERMINAL_PHASES = {"completed", "stopped"}
NEXT_ACTIONS = {
    "approve",
    "fix_required",
    "redesign_allowed",
    "park_unit",
    "completed",
    "stopped",
}
TRANSITIONS: dict[str, dict[str, set[str]]] = {
    "review_frozen": {
        "submit_delta": {"awaiting_review"},
        "fix": {"fixing"},
        "redesign": {"redesigning"},
        "park": {"parked"},
        "complete": {"completed"},
        "stop": {"stopped"},
    },
    "fixing": {
        "submit_delta": {"awaiting_review"},
        "stop": {"stopped"},
    },
    "awaiting_review": {
        "review": {"review_frozen", "parked"},
        "stop": {"stopped"},
    },
    "redesigning": {
        "submit_delta": {"awaiting_review"},
        "stop": {"stopped"},
    },
    "parked": {"stop": {"stopped"}},
    "completed": {},
    "stopped": {},
}
VERIFICATION_TEST_ROOTS = {
    "test",
    "tests",
    "fixtures",
    "integrationTest",
    "e2e",
    "__tests__",
    "spec",
    "specs",
}
VERIFICATION_TEST_SOURCE_SETS = {
    "test",
    "testFixtures",
    "androidTest",
    "integrationTest",
    "commonTest",
    "jvmTest",
    "jsTest",
    "iosTest",
    "nativeTest",
    "e2e",
    "spec",
    "specs",
    "testResources",
}
PROOF_FIELDS = (
    "approved_requirement",
    "material_impact",
    "reachable_scenario",
)
PROOF_STORE_VERSION = 1
MAX_INITIAL_BLOCKERS = 3
PROOF_ID = re.compile(r"^proof-[0-9a-f]{32}$")


class GuardError(ValueError):
    """Erro de contrato exibível sem traceback."""


class SecurityGuardError(GuardError):
    """Violação de confinamento que nunca pode virar hardening."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def identifier(value: str, label: str) -> str:
    if not IDENTIFIER.fullmatch(value):
        raise GuardError(
            f"{label} inválido: use letras, números, ponto, sublinhado ou hífen"
        )
    return value


def unit_identity(
    repository_root: str, planning_version: str, plan_id: str, unit_digest: str
) -> str:
    material = "\0".join(
        (repository_root, planning_version, plan_id, unit_digest)
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def digest_identifier(value: str, label: str) -> str:
    if not DIGEST.fullmatch(value):
        raise GuardError(f"{label} deve ser SHA-256 hexadecimal")
    return value


def file_digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def validate_task_brief(
    root: Path, value: str | Path, unit_digest: str
) -> tuple[str, str]:
    brief = confined_path(root, value, "task-brief", must_exist=True)
    try:
        content = brief.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise GuardError("task-brief ilegível") from error
    if unit_digest not in BRIEF_UNIT_DIGEST.findall(content):
        raise GuardError("unit_identity não pertence ao task-brief")
    return brief.relative_to(root).as_posix(), file_digest(brief)


def frozen_task_brief_content(state: dict[str, Any], root: Path) -> str:
    if state.get("unit_identity_source") != "task_brief":
        raise GuardError("task-brief congelado indisponível")
    brief = confined_path(
        root, str(state.get("task_brief", "")), "task-brief", must_exist=True
    )
    if file_digest(brief) != state.get("task_brief_digest"):
        raise GuardError("task-brief da identidade foi alterado")
    try:
        return brief.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise GuardError("task-brief ilegível") from error


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
    )


def validate_repository(path: Path) -> Path:
    if path.is_symlink():
        raise SecurityGuardError("raiz do repositório não pode ser symlink")
    root = path.resolve()
    result = git(root, "rev-parse", "--show-toplevel")
    if result.returncode != 0:
        raise GuardError("root não é repositório Git válido")
    top = Path(result.stdout.strip()).resolve()
    if top != root:
        raise GuardError(f"root deve ser o toplevel Git exato: {top}")
    return root


def resolve_commit(root: Path, value: str, label: str) -> str:
    if not nonempty(value) or "\n" in value or "\r" in value:
        raise GuardError(f"{label} inválido")
    result = git(root, "rev-parse", "--verify", f"{value.strip()}^{{commit}}")
    if result.returncode != 0:
        raise GuardError(f"{label} não é commit Git real deste repositório")
    return result.stdout.strip()


def current_head(root: Path) -> str:
    return resolve_commit(root, "HEAD", "HEAD")


def verify_delta(
    root: Path, base: str, head: str, expected_base: str
) -> tuple[str, str]:
    base_oid = resolve_commit(root, base, "delta_base")
    head_oid = resolve_commit(root, head, "delta_head")
    expected_oid = resolve_commit(root, expected_base, "last_review_head")
    if base_oid != expected_oid:
        raise GuardError("delta_base difere de last_review_head")
    if head_oid != current_head(root):
        raise GuardError("delta_head difere do HEAD atual")
    ancestry = git(root, "merge-base", "--is-ancestor", base_oid, head_oid)
    if ancestry.returncode != 0:
        raise GuardError("delta_head não descende de delta_base")
    if base_oid == head_oid:
        raise GuardError("delta vazio: base e head são iguais")
    return base_oid, head_oid


def ensure_no_symlink_between(root: Path, path: Path, label: str) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise SecurityGuardError(f"{label} escapa do repositório") from error
    current = root
    for part in relative.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise SecurityGuardError(f"{label} contém symlink")


def confined_path(
    root: Path,
    value: str | Path,
    label: str,
    *,
    must_exist: bool = False,
    directory: bool = False,
) -> Path:
    raw = Path(value)
    candidate = raw if raw.is_absolute() else root / raw
    lexical = Path(os.path.abspath(candidate))
    resolved = lexical.resolve()
    if not resolved.is_relative_to(root):
        raise SecurityGuardError(f"{label} escapa do repositório")
    # macOS expõe temporários por /var, cujo caminho canônico é /private/var.
    # Ache o spelling da raiz usado pelo chamador e inspecione somente os
    # componentes internos; assim o alias do sistema é aceito, mas qualquer
    # symlink dentro (ou apontando para dentro) do repositório é rejeitado.
    anchor = next(
        (parent for parent in (lexical, *lexical.parents) if parent.resolve() == root),
        None,
    )
    if anchor is None:
        raise SecurityGuardError(f"{label} não deriva da raiz do repositório")
    current = anchor
    for part in lexical.relative_to(anchor).parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise SecurityGuardError(f"{label} contém symlink")
    if must_exist and not resolved.exists():
        raise GuardError(f"{label} não encontrado: {resolved}")
    if directory and (not resolved.exists() or not resolved.is_dir()):
        raise GuardError(f"{label} deve ser diretório existente")
    return resolved


def relative_repo_path(root: Path, value: str, label: str) -> str:
    if not nonempty(value):
        raise GuardError(f"{label} obrigatório")
    pure = PurePosixPath(value)
    if value == ".":
        confined_path(root, ".", label, must_exist=True, directory=True)
        return "."
    if pure.is_absolute() or ".." in pure.parts or "." in pure.parts:
        raise SecurityGuardError(f"{label} deve ser relativo e confinado")
    confined_path(root, Path(*pure.parts), label)
    return pure.as_posix()


def canonical_sidecar(root: Path, planning_version: str, plan: str, unit: str) -> Path:
    planning_version = identifier(planning_version, "planning_version")
    plan = identifier(plan, "plan")
    unit = identifier(unit, "unit")
    candidate = (
        root
        / "artifacts"
        / "bianchini"
        / planning_version
        / "codex"
        / "convergence"
        / plan
        / f"{unit}.json"
    )
    ensure_no_symlink_between(root, Path(os.path.abspath(candidate)), "sidecar")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise SecurityGuardError("caminho canônico do sidecar escapa do repositório")
    return resolved


def canonical_proof_store(
    root: Path, planning_version: str, plan: str, unit: str
) -> Path:
    planning_version = identifier(planning_version, "planning_version")
    plan = identifier(plan, "plan")
    unit = identifier(unit, "unit")
    candidate = (
        root
        / "artifacts"
        / "bianchini"
        / planning_version
        / "codex"
        / "convergence"
        / plan
        / ".proofs"
        / f"{unit}.json"
    )
    ensure_no_symlink_between(root, Path(os.path.abspath(candidate)), "proof store")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root):
        raise SecurityGuardError("proof store escapa do repositório")
    return resolved


def load_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise GuardError(f"{label} não encontrado: {path}") from error
    except json.JSONDecodeError as error:
        raise GuardError(f"{label} inválido: {error.msg}") from error
    except (OSError, UnicodeError) as error:
        raise GuardError(f"{label} ilegível: {path}") from error


def write_atomic(
    path: Path, value: dict[str, Any], *, rotate_backup: bool = True
) -> None:
    rendered = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if "ask_user" in rendered:
        raise GuardError("estado proibido")
    path.parent.mkdir(parents=True, exist_ok=True)
    backup = path.with_suffix(path.suffix + ".bak")
    if backup.is_symlink():
        raise SecurityGuardError("backup do sidecar não pode ser symlink")
    if backup.exists() and not backup.is_file():
        raise SecurityGuardError("backup do sidecar deve ser arquivo regular")
    if rotate_backup and path.exists():
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            pass
        else:
            shutil.copy2(path, backup)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
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


def proof_key_path(root: Path) -> Path:
    result = git(root, "rev-parse", "--git-common-dir")
    if result.returncode != 0 or not nonempty(result.stdout):
        raise GuardError("diretório Git comum indisponível")
    raw = Path(result.stdout.strip())
    git_directory = (raw if raw.is_absolute() else root / raw).resolve()
    if not git_directory.is_dir():
        raise GuardError("diretório Git comum inválido")
    return git_directory / "bianchini-codex" / "proof.key"


def proof_key(root: Path, *, create: bool = False) -> bytes:
    path = proof_key_path(root)
    if path.parent.exists() and path.parent.is_symlink():
        raise SecurityGuardError("diretório da chave de proof não pode ser symlink")
    if path.is_symlink():
        raise SecurityGuardError("chave de proof não pode ser symlink")
    if not path.exists() and create:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.parent.is_symlink():
            raise SecurityGuardError("diretório da chave de proof não pode ser symlink")
        try:
            descriptor = os.open(
                path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            pass
        else:
            try:
                os.write(descriptor, os.urandom(32).hex().encode("ascii") + b"\n")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            directory_descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
    if not path.is_file() or path.is_symlink():
        raise GuardError("chave guard-owned de proof ausente")
    try:
        encoded = path.read_text(encoding="ascii").strip()
        key = bytes.fromhex(encoded)
    except (OSError, UnicodeError, ValueError) as error:
        raise GuardError("chave guard-owned de proof inválida") from error
    if len(key) != 32:
        raise GuardError("chave guard-owned de proof inválida")
    return key


def proof_signature(
    root: Path, record: dict[str, Any], *, create_key: bool = False
) -> str:
    material = {key: value for key, value in record.items() if key != "signature"}
    payload = json.dumps(
        material,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hmac.new(
        proof_key(root, create=create_key), payload, hashlib.sha256
    ).hexdigest()


@contextmanager
def proof_store_lock(path: Path) -> Any:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_suffix(path.suffix + ".lock")
    if lock_path.is_symlink():
        raise SecurityGuardError("lock do proof store não pode ser symlink")
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "r+b", closefd=True) as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def validate_proof_record(root: Path, proof_id: str, value: Any) -> dict[str, Any]:
    if not PROOF_ID.fullmatch(proof_id) or not isinstance(value, dict):
        raise GuardError("proof inválido")
    if value.get("proof_id") != proof_id:
        raise GuardError(f"proof {proof_id}: identidade interna inválida")
    command = validate_command(value.get("command"), f"proof {proof_id}")
    cwd = relative_repo_path(root, str(value.get("cwd", "")), f"proof {proof_id}.cwd")
    stored_commit = str(value.get("commit", ""))
    commit = resolve_commit(root, stored_commit, f"proof {proof_id}.commit")
    if stored_commit != commit:
        raise GuardError(f"proof {proof_id}: commit deve ser OID canônico")
    exit_code = value.get("exit_code")
    timeout = value.get("timeout_seconds")
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        raise GuardError(f"proof {proof_id}: exit_code inválido")
    if (
        not isinstance(timeout, (int, float))
        or isinstance(timeout, bool)
        or timeout <= 0
        or not math.isfinite(timeout)
    ):
        raise GuardError(f"proof {proof_id}: timeout inválido")
    for field in ("stdout_sha256", "stderr_sha256"):
        digest_identifier(str(value.get(field, "")), f"proof {proof_id}.{field}")
    if (
        not isinstance(value.get("timed_out"), bool)
        or not isinstance(value.get("spawn_error"), bool)
        or not nonempty(value.get("created_at"))
    ):
        raise GuardError(f"proof {proof_id}: metadados inválidos")
    normalized = copy.deepcopy(value)
    normalized.update({"command": command, "cwd": cwd, "commit": commit})
    signature = value.get("signature")
    if not isinstance(signature, str) or not hmac.compare_digest(
        signature, proof_signature(root, normalized)
    ):
        raise GuardError(f"proof {proof_id}: assinatura guard-owned inválida")
    return normalized


def validate_proof_store(
    root: Path,
    path: Path,
    value: Any,
    planning_version: str,
    plan: str,
    unit: str,
) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("store_version") != PROOF_STORE_VERSION:
        raise GuardError("proof store incompatível")
    expected = {
        "repository_root": str(root),
        "planning_version": planning_version,
        "plan_id": plan,
        "unit_id": unit,
    }
    if any(
        value.get(key) != expected_value for key, expected_value in expected.items()
    ):
        raise GuardError("identidade do proof store inválida")
    if path != canonical_proof_store(root, planning_version, plan, unit):
        raise SecurityGuardError("proof store fora do caminho canônico")
    proofs = value.get("proofs")
    if not isinstance(proofs, dict):
        raise GuardError("proof store sem proofs")
    normalized = copy.deepcopy(value)
    normalized_proofs: dict[str, Any] = {}
    for proof_id, proof in proofs.items():
        record = validate_proof_record(root, proof_id, proof)
        if (
            record.get("planning_version") != planning_version
            or record.get("plan_id") != plan
            or record.get("unit_id") != unit
        ):
            raise GuardError(f"proof {proof_id}: identidade da unidade inválida")
        normalized_proofs[proof_id] = record
    normalized["proofs"] = normalized_proofs
    return normalized


def load_proof_store(
    root: Path,
    planning_version: str,
    plan: str,
    unit: str,
    *,
    create: bool = False,
) -> tuple[Path, dict[str, Any]]:
    path = canonical_proof_store(root, planning_version, plan, unit)
    if path.is_symlink():
        raise SecurityGuardError("proof store não pode ser symlink")
    if not path.exists():
        if not create:
            raise GuardError("proof store não encontrado")
        return path, {
            "store_version": PROOF_STORE_VERSION,
            "repository_root": str(root),
            "planning_version": planning_version,
            "plan_id": plan,
            "unit_id": unit,
            "proofs": {},
            "created_at": now(),
            "updated_at": now(),
        }
    try:
        raw = load_json(path, "proof store")
        return path, validate_proof_store(root, path, raw, planning_version, plan, unit)
    except GuardError as primary_error:
        backup = path.with_suffix(path.suffix + ".bak")
        if not backup.exists() or backup.is_symlink():
            raise primary_error
        recovered = validate_proof_store(
            root,
            path,
            load_json(backup, "backup do proof store"),
            planning_version,
            plan,
            unit,
        )
        write_atomic(path, recovered, rotate_backup=False)
        return path, recovered


def proof_for(
    root: Path,
    planning_version: str,
    plan: str,
    unit: str,
    proof_id: Any,
) -> dict[str, Any]:
    if not isinstance(proof_id, str) or not PROOF_ID.fullmatch(proof_id):
        raise GuardError("proof_id inválido")
    _, store = load_proof_store(root, planning_version, plan, unit)
    proof = store["proofs"].get(proof_id)
    if proof is None:
        raise GuardError(f"proof_id desconhecido: {proof_id}")
    return proof


def state_proof(state: dict[str, Any], proof_id: Any) -> dict[str, Any]:
    return proof_for(
        Path(state["repository_root"]),
        state["planning_version"],
        state["plan_id"],
        state["unit_id"],
        proof_id,
    )


def require_proof(
    state: dict[str, Any],
    proof_id: Any,
    *,
    commit: str,
    success: bool,
    label: str,
) -> dict[str, Any]:
    proof = state_proof(state, proof_id)
    if proof["commit"] != commit:
        raise GuardError(f"{label}: proof commit não coincide com revisão exigida")
    if proof["spawn_error"]:
        raise GuardError(f"{label}: comando do proof não chegou a executar")
    if success and proof["exit_code"] != 0:
        raise GuardError(f"{label}: proof deve estar verde")
    if not success and proof["exit_code"] == 0:
        raise GuardError(f"{label}: proof deve conter falha real")
    return proof


def command_proof(args: argparse.Namespace) -> dict[str, Any]:
    root = validate_repository(Path(args.root))
    planning_version = identifier(args.planning_version, "planning_version")
    plan = identifier(args.plan, "plan")
    unit = identifier(args.unit, "unit")
    commit = resolve_commit(root, args.commit, "commit")
    timeout = args.timeout
    if not isinstance(timeout, float) or timeout <= 0 or not timeout < float("inf"):
        raise GuardError("timeout deve ser número positivo finito")
    raw_argv = args.argv[1:] if args.argv and args.argv[0] == "--" else args.argv
    command = validate_command(raw_argv, "proof")
    cwd_value = relative_repo_path(root, args.cwd, "proof.cwd")
    checkout_parent = Path(tempfile.mkdtemp(prefix="bianchini-codex-proof-")).resolve()
    checkout = checkout_parent / "checkout"
    added = False
    stdout = b""
    stderr = b""
    timed_out = False
    spawn_error = False
    exit_code: int
    try:
        added_result = git(
            root, "worktree", "add", "--detach", "--quiet", str(checkout), commit
        )
        if added_result.returncode != 0:
            raise GuardError("não foi possível criar checkout isolado do proof")
        added = True
        proof_cwd = confined_path(
            checkout,
            cwd_value,
            "proof.cwd no commit",
            must_exist=True,
            directory=True,
        )
        try:
            process = subprocess.Popen(
                command,
                cwd=proof_cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                start_new_session=True,
            )
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                stdout, stderr = process.communicate()
            exit_code = process.returncode
        except OSError as error:
            spawn_error = True
            stdout = b""
            stderr = str(error).encode("utf-8", errors="replace")
            exit_code = 127
    finally:
        if added:
            git(root, "worktree", "remove", "--force", str(checkout))
        shutil.rmtree(checkout_parent, ignore_errors=True)
    created_at = now()
    proof_id = (
        "proof-"
        + hashlib.sha256(
            os.urandom(32)
            + commit.encode("ascii")
            + json.dumps(command, ensure_ascii=False).encode("utf-8")
            + created_at.encode("ascii")
        ).hexdigest()[:32]
    )
    record = {
        "proof_id": proof_id,
        "planning_version": planning_version,
        "plan_id": plan,
        "unit_id": unit,
        "command": command,
        "cwd": cwd_value,
        "timeout_seconds": timeout,
        "exit_code": exit_code,
        "commit": commit,
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "timed_out": timed_out,
        "spawn_error": spawn_error,
        "created_at": created_at,
    }
    record["signature"] = proof_signature(root, record, create_key=True)
    path = canonical_proof_store(root, planning_version, plan, unit)
    with proof_store_lock(path):
        path, store = load_proof_store(root, planning_version, plan, unit, create=True)
        store["proofs"][proof_id] = record
        store["updated_at"] = now()
        write_atomic(path, store)
    return {"proof_id": proof_id, "proof": record, "proof_store": str(path)}


def event(state: dict[str, Any], action: str, **details: Any) -> None:
    state["events"].append({"at": now(), "action": action, **details})
    state["updated_at"] = now()


def transition(state: dict[str, Any], action: str, target: str) -> None:
    source = state["phase"]
    allowed = TRANSITIONS.get(source, {}).get(action, set())
    if target not in allowed:
        raise GuardError(f"transição inválida: {source} --{action}--> {target}")
    state["phase"] = target
    event(state, "phase_transition", source=source, command=action, target=target)


def validate_command(value: Any, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or not all(nonempty(item) and "\0" not in item for item in value)
    ):
        raise GuardError(f"{label}.command deve ser argv estruturado não vazio")
    return [str(item) for item in value]


def validate_execution_evidence(
    value: Any,
    root: Path,
    label: str,
    *,
    require_success: bool | None = None,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GuardError(f"{label} deve ser objeto")
    command = validate_command(value.get("command"), label)
    cwd_value = value.get("cwd")
    if not nonempty(cwd_value):
        raise GuardError(f"{label}.cwd obrigatório")
    cwd = confined_path(
        root, cwd_value, f"{label}.cwd", must_exist=True, directory=True
    )
    exit_code = value.get("exit_code")
    if not isinstance(exit_code, int) or isinstance(exit_code, bool):
        raise GuardError(f"{label}.exit_code deve ser inteiro")
    if require_success is True and exit_code != 0:
        raise GuardError(f"{label}.exit_code deve ser 0")
    if require_success is False and exit_code == 0:
        raise GuardError(f"{label}.exit_code deve indicar falha")
    observation = value.get("observation")
    if not nonempty(observation):
        raise GuardError(f"{label}.observation obrigatória")
    return {
        "command": command,
        "cwd": cwd.relative_to(root).as_posix() or ".",
        "exit_code": exit_code,
        "observation": observation.strip(),
    }


def validate_reproduction(value: Any, root: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GuardError("reproduction deve ser objeto estruturado")
    command = validate_command(value.get("command"), "reproduction")
    cwd_value = value.get("cwd")
    if not nonempty(cwd_value):
        raise GuardError("reproduction.cwd obrigatório")
    cwd = confined_path(
        root, cwd_value, "reproduction.cwd", must_exist=True, directory=True
    )
    base_exit = value.get("base_exit_code")
    head_exit = value.get("head_exit_code")
    if base_exit != 0 or not isinstance(base_exit, int) or isinstance(base_exit, bool):
        raise GuardError("reproduction exige base_exit_code 0")
    if not isinstance(head_exit, int) or isinstance(head_exit, bool) or head_exit == 0:
        raise GuardError("reproduction exige head_exit_code diferente de 0")
    return {
        "command": command,
        "cwd": cwd.relative_to(root).as_posix() or ".",
        "base_exit_code": base_exit,
        "head_exit_code": head_exit,
    }


def validate_structural_fields(
    finding: dict[str, Any],
    root: Path,
    seam: str,
    *,
    state: dict[str, Any] | None = None,
    expected_commit: str | None = None,
    allow_legacy: bool = False,
) -> dict[str, Any]:
    risk_seam = identifier(str(finding.get("risk_seam", "")), "risk_seam")
    if risk_seam != seam:
        raise GuardError("risk_seam deve coincidir com seam congelado")
    structural = finding.get("structural")
    if not isinstance(structural, bool):
        raise GuardError("structural deve ser booleano")
    structural_class = finding.get("structural_class")
    structural_evidence = finding.get("structural_evidence")
    if structural is False:
        if structural_class is not None or structural_evidence is not None:
            raise GuardError(
                "blocker não estrutural exige structural_class/evidence nulos"
            )
        return {
            "risk_seam": risk_seam,
            "structural": False,
            "structural_class": None,
            "structural_evidence": None,
        }
    if structural_class not in STRUCTURAL_CLASSES:
        raise GuardError("structural_class não reconhecida")
    if allow_legacy and isinstance(structural_evidence, dict):
        evidence: Any = validate_execution_evidence(
            structural_evidence, root, "structural_evidence"
        )
    else:
        if state is None or expected_commit is None:
            raise GuardError("structural_evidence exige contexto de proof")
        require_proof(
            state,
            structural_evidence,
            commit=expected_commit,
            success=False,
            label="structural_evidence",
        )
        evidence = structural_evidence
    return {
        "risk_seam": risk_seam,
        "structural": True,
        "structural_class": structural_class,
        "structural_evidence": evidence,
    }


def normalize_initial_finding(
    raw: dict[str, Any],
    state: dict[str, Any],
    root: Path,
    seam: str,
    brief_content: str,
    review_head: str,
) -> dict[str, Any]:
    finding = copy.deepcopy(raw)
    finding_id = identifier(str(finding.get("id", "")), "finding.id")
    severity = str(finding.get("severity", ""))
    if severity not in SEVERITIES:
        raise GuardError(f"finding {finding_id}: severity inválida")
    if not nonempty(finding.get("title")):
        raise GuardError(f"finding {finding_id}: title obrigatório")
    disposition = finding.get("disposition")
    if severity in BLOCKING_SEVERITIES:
        if disposition != "blocker":
            raise GuardError(f"finding {finding_id}: critical/important exige blocker")
        missing = [field for field in PROOF_FIELDS if not nonempty(finding.get(field))]
        if missing:
            raise GuardError(f"finding {finding_id}: blocker sem {', '.join(missing)}")
        approved = finding["approved_requirement"].strip()
        if approved not in brief_content:
            finding.update(
                {
                    "id": finding_id,
                    "severity": severity,
                    "disposition": "hardening",
                    "deferred_reason": "approved_requirement não existe no task-brief congelado",
                }
            )
            return finding
        if any(
            field in finding
            for field in ("reproduction", "exit_code", "command", "cwd")
        ):
            raise GuardError(
                f"finding {finding_id}: evidência manual proibida; use somente proof_id"
            )
        proof_id = finding.get("proof_id")
        proof = state_proof(state, proof_id)
        if proof["commit"] != review_head:
            raise GuardError(
                f"finding {finding_id}: proof não pertence ao HEAD revisado"
            )
        if proof["spawn_error"]:
            raise GuardError(f"finding {finding_id}: comando do proof não executou")
        if proof["exit_code"] == 0:
            finding.update(
                {
                    "id": finding_id,
                    "severity": severity,
                    "disposition": "hardening",
                    "deferred_reason": "proof real está verde no HEAD revisado",
                }
            )
            return finding
        finding["proof_id"] = proof_id
        finding["approved_requirement"] = approved
        finding.update(
            validate_structural_fields(
                finding,
                root,
                seam,
                state=state,
                expected_commit=review_head,
            )
        )
    elif disposition != "hardening":
        raise GuardError(f"finding {finding_id}: minor/note exige hardening")
    finding["id"] = finding_id
    finding["severity"] = severity
    finding["disposition"] = disposition
    return finding


def findings_from(path: Path, root: Path) -> list[dict[str, Any]]:
    confined = confined_path(root, path, "findings", must_exist=True)
    value = load_json(confined, "findings")
    findings = value.get("findings") if isinstance(value, dict) else value
    if not isinstance(findings, list) or not all(
        isinstance(item, dict) for item in findings
    ):
        raise GuardError("findings deve ser lista de objetos")
    return findings


def sanitized_hardening(finding: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(finding)
    for field in (
        "reproduction",
        "resolution_evidence",
        "exit_code",
        "base_exit_code",
        "head_exit_code",
        "command",
        "cwd",
    ):
        value.pop(field, None)
    return value


def open_blockers(state: dict[str, Any]) -> list[str]:
    return sorted(
        finding_id
        for finding_id, finding in state["blockers"].items()
        if finding["status"] == "open"
    )


def determine_next_action(state: dict[str, Any]) -> str:
    if state["phase"] == "completed":
        return "completed"
    if state["phase"] == "stopped":
        return "stopped"
    if state["phase"] == "parked":
        return "park_unit"
    blockers = [state["blockers"][key] for key in open_blockers(state)]
    if not blockers:
        return "approve"
    if state["fix_rounds"] < MAX_FIX_ROUNDS:
        return "fix_required"
    if state["redesign_count"] < MAX_REDESIGNS_PER_UNIT and any(
        blocker["structural"] for blocker in blockers
    ):
        return "redesign_allowed"
    return "park_unit"


def parse_diff(root: Path, base: str, head: str) -> list[dict[str, Any]]:
    result = git(
        root,
        "-c",
        "core.quotePath=false",
        "diff",
        "--unified=0",
        "--find-renames=50%",
        "--no-color",
        "--no-ext-diff",
        base,
        head,
        "--",
    )
    if result.returncode != 0:
        raise GuardError("não foi possível calcular diff Git")
    hunks: list[dict[str, Any]] = []
    old_path: str | None = None
    new_path: str | None = None
    for line in result.stdout.splitlines():
        if line.startswith("--- "):
            raw = line[4:]
            old_path = None if raw == "/dev/null" else raw.removeprefix("a/")
            continue
        if line.startswith("+++ "):
            raw = line[4:]
            new_path = None if raw == "/dev/null" else raw.removeprefix("b/")
            continue
        match = HUNK.match(line)
        if not match:
            continue
        old_start = int(match.group(1))
        old_count = int(match.group(2) or "1")
        new_start = int(match.group(3))
        new_count = int(match.group(4) or "1")
        hunks.append(
            {
                "old_path": old_path,
                "new_path": new_path,
                "old_lines": set(range(old_start, old_start + old_count)),
                "new_lines": set(range(new_start, new_start + new_count)),
                "replacement": old_count > 0 and new_count > 0,
            }
        )
    return hunks


def line_touched(
    hunks: list[dict[str, Any]], file_path: str, line: int, change_kind: str
) -> bool:
    for hunk in hunks:
        if change_kind == "removed":
            if hunk["old_path"] == file_path and line in hunk["old_lines"]:
                return True
        elif change_kind == "added":
            if (
                hunk["new_path"] == file_path
                and line in hunk["new_lines"]
                and not hunk["replacement"]
            ):
                return True
        elif change_kind == "modified":
            if (
                hunk["new_path"] == file_path
                and line in hunk["new_lines"]
                and hunk["replacement"]
            ):
                return True
    return False


def verification_path_allowed(path: str) -> bool:
    """Return whether a committed path can belong to a verification-only delta."""
    pure = PurePosixPath(path)
    if pure.is_absolute() or ".." in pure.parts or "." in pure.parts:
        return False
    if pure.parts and pure.parts[0] in {"docs", "artifacts"}:
        return True
    source_sets = [
        pure.parts[index + 1]
        for index, part in enumerate(pure.parts[:-1])
        if part == "src"
    ]
    if source_sets and any(
        source_set not in VERIFICATION_TEST_SOURCE_SETS
        for source_set in source_sets
    ):
        return False
    if any(source_set in VERIFICATION_TEST_SOURCE_SETS for source_set in source_sets):
        return True
    if any(part in VERIFICATION_TEST_ROOTS for part in pure.parts):
        return True
    name = pure.name
    if name.lower().endswith((".md", ".mdx", ".rst", ".adoc", ".asciidoc")):
        return True
    return False


def verification_changed_paths(root: Path, base: str, head: str) -> list[str]:
    """List both sides of renames so production code cannot be hidden as a test rename."""
    result = git(
        root,
        "-c",
        "core.quotePath=false",
        "diff",
        "--name-only",
        "--no-renames",
        "-z",
        base,
        head,
        "--",
    )
    if result.returncode != 0:
        raise GuardError("não foi possível calcular paths do delta de verification")
    paths = sorted({item for item in result.stdout.split("\0") if item})
    for path in paths:
        relative_repo_path(root, path, "verification diff path")
    return paths


def ensure_verification_delta_only(root: Path, base: str, head: str) -> None:
    paths = verification_changed_paths(root, base, head)
    if not paths:
        raise GuardError("verification exige delta não vazio")
    production = [path for path in paths if not verification_path_allowed(path)]
    if production:
        rendered = ", ".join(production[:8])
        suffix = " ..." if len(production) > 8 else ""
        raise GuardError(
            "verification proibida: diff altera código de produção "
            f"({rendered}{suffix}); use somente testes, docs ou artifacts"
        )


def ensure_clean_implementation_review(state: dict[str, Any]) -> None:
    if state.get("delta_submissions") != 1:
        raise GuardError(
            "verification exige revisão limpa após o único delta implementation"
        )
    if open_blockers(state):
        raise GuardError("verification exige revisão limpa sem blockers abertos")
    events = state.get("events")
    if not isinstance(events, list):
        raise GuardError("verification exige histórico da revisão implementation")
    submissions = [
        (index, event)
        for index, event in enumerate(events)
        if isinstance(event, dict) and event.get("action") == "delta_submitted"
    ]
    if len(submissions) != 1 or submissions[0][1].get("kind") != "implementation":
        raise GuardError(
            "verification exige revisão limpa após o único delta implementation"
        )
    submission_index, submission = submissions[0]
    reviews = [
        (index, event)
        for index, event in enumerate(events)
        if isinstance(event, dict) and event.get("action") == "review_frozen"
    ]
    if not reviews or reviews[-1][0] <= submission_index:
        raise GuardError("verification exige revisão limpa após implementation")
    submitted_head = submission.get("head")
    if submitted_head and state.get("last_review_head") != submitted_head:
        raise GuardError("verification exige HEAD da revisão implementation congelado")


def ensure_pending_verification_state(
    state: dict[str, Any], pending: dict[str, Any]
) -> None:
    if state.get("delta_submissions") != 1 or open_blockers(state):
        raise GuardError("pending verification exige revisão implementation limpa")
    events = state.get("events")
    if not isinstance(events, list):
        raise GuardError("pending verification exige histórico válido")
    submissions = [
        (index, event)
        for index, event in enumerate(events)
        if isinstance(event, dict) and event.get("action") == "delta_submitted"
    ]
    if len(submissions) != 2 or [
        event.get("kind") for _, event in submissions
    ] != ["implementation", "verification"]:
        raise GuardError(
            "pending verification exige implementation revisado e verification único"
        )
    implementation_index, implementation = submissions[0]
    verification_index, verification = submissions[1]
    reviewed_between = any(
        implementation_index < index < verification_index
        and isinstance(event, dict)
        and event.get("action") == "review_frozen"
        for index, event in enumerate(events)
    )
    if not reviewed_between:
        raise GuardError("pending verification exige revisão limpa após implementation")
    last_review_head = state.get("last_review_head")
    if implementation.get("head") != last_review_head:
        raise GuardError("pending verification diverge do HEAD implementation revisado")
    for field in ("base", "head"):
        if verification.get(field) != pending.get(field):
            raise GuardError("pending verification diverge do evento submetido")
    if pending.get("base") != last_review_head:
        raise GuardError("pending verification deve partir do último HEAD revisado")
    if any(
        isinstance(event, dict) and event.get("action") == "review_frozen"
        for event in events[verification_index + 1 :]
    ):
        raise GuardError("pending verification já possui revisão posterior")


def validate_delta_regression(
    finding: dict[str, Any],
    state: dict[str, Any],
    root: Path,
    hunks: list[dict[str, Any]],
    base: str,
    head: str,
) -> dict[str, Any]:
    finding_id = identifier(str(finding.get("id", "")), "finding.id")
    if finding.get("source") != "delta_regression":
        raise GuardError(f"finding {finding_id}: source inválida")
    if finding.get("severity") not in BLOCKING_SEVERITIES:
        raise GuardError("delta_regression não material")
    if finding.get("disposition") != "blocker":
        raise GuardError("delta_regression deve declarar blocker candidato")
    if not nonempty(finding.get("title")):
        raise GuardError("delta_regression sem title")
    if (
        resolve_commit(root, str(finding.get("delta_base", "")), "finding.delta_base")
        != base
    ):
        raise GuardError("finding.delta_base não coincide com delta submetido")
    if (
        resolve_commit(root, str(finding.get("delta_head", "")), "finding.delta_head")
        != head
    ):
        raise GuardError("finding.delta_head não coincide com delta submetido")
    file_path = relative_repo_path(root, str(finding.get("file", "")), "finding.file")
    line = finding.get("line")
    if not isinstance(line, int) or isinstance(line, bool) or line < 1:
        raise GuardError("finding.line deve ser inteiro positivo")
    change_kind = finding.get("change_kind")
    if change_kind not in {"added", "modified", "removed"}:
        raise GuardError("finding.change_kind inválido")
    if not line_touched(hunks, file_path, line, change_kind):
        raise GuardError("finding aponta linha fora do delta ou somente contexto")
    if any(
        field in finding
        for field in (
            "reproduction",
            "exit_code",
            "base_exit_code",
            "head_exit_code",
            "command",
            "cwd",
        )
    ):
        raise GuardError("delta_regression aceita somente base_proof_id/head_proof_id")
    base_proof_id = finding.get("base_proof_id")
    head_proof_id = finding.get("head_proof_id")
    base_proof = require_proof(
        state,
        base_proof_id,
        commit=base,
        success=True,
        label="delta_regression base",
    )
    head_proof = require_proof(
        state,
        head_proof_id,
        commit=head,
        success=False,
        label="delta_regression head",
    )
    if (
        base_proof["command"] != head_proof["command"]
        or base_proof["cwd"] != head_proof["cwd"]
    ):
        raise GuardError("delta_regression exige dois proofs do mesmo comando e cwd")
    if not nonempty(finding.get("causal_explanation")):
        raise GuardError("causal_explanation obrigatória")
    missing = [field for field in PROOF_FIELDS if not nonempty(finding.get(field))]
    if missing:
        raise GuardError(f"delta_regression sem {', '.join(missing)}")
    approved = finding["approved_requirement"].strip()
    brief_content = frozen_task_brief_content(state, root)
    if approved not in brief_content:
        raise GuardError("approved_requirement não existe no task-brief congelado")
    structural = validate_structural_fields(
        finding,
        root,
        state["seam"],
        state=state,
        expected_commit=head,
    )
    normalized = copy.deepcopy(finding)
    normalized.update(structural)
    normalized.update(
        {
            "id": finding_id,
            "file": file_path,
            "line": line,
            "change_kind": change_kind,
            "delta_base": base,
            "delta_head": head,
            "base_proof_id": base_proof_id,
            "head_proof_id": head_proof_id,
            "approved_requirement": approved,
            "causal_explanation": finding["causal_explanation"].strip(),
            "status": "open",
        }
    )
    return normalized


def migrate_v1_to_v2(state: dict[str, Any], path: Path) -> dict[str, Any]:
    migrated = copy.deepcopy(state)
    root = validate_repository(Path(str(migrated.get("repository_root", ""))))
    legacy_head = str(migrated.get("last_review_head", ""))
    last_head = resolve_commit(root, legacy_head, "legacy.last_review_head")
    status = migrated.get("status", "active")
    if status == "completed":
        phase = "completed"
    elif status == "stopped":
        phase = "stopped"
    else:
        actions = [
            item.get("action")
            for item in migrated.get("events", [])
            if isinstance(item, dict)
        ]
        last_action = actions[-1] if actions else None
        if last_action == "redesign_started":
            phase = "redesigning"
        elif last_action == "fix_round_started":
            phase = "fixing"
        else:
            phase = "review_frozen"
    seam = identifier(str(migrated.get("seam", "")), "seam")
    blockers = migrated.get("blockers", {})
    if not isinstance(blockers, dict):
        raise GuardError("sidecar v1 com blockers inválidos")
    for blocker in blockers.values():
        if not isinstance(blocker, dict):
            raise GuardError("sidecar v1 com blocker inválido")
        blocker.setdefault("risk_seam", seam)
        blocker.setdefault("structural", False)
        blocker.setdefault("structural_class", None)
        blocker.setdefault("structural_evidence", None)
        reproduction = blocker.get("reproduction")
        if isinstance(reproduction, str) and reproduction.strip():
            blocker["reproduction"] = {
                "command": ["legacy-reproduction"],
                "cwd": ".",
                "exit_code": 1,
                "observation": reproduction.strip(),
            }
        resolution = blocker.get("resolution_evidence")
        if blocker.get("status") == "resolved" and isinstance(resolution, str):
            blocker["resolution_evidence"] = {
                "command": blocker["reproduction"]["command"],
                "cwd": blocker["reproduction"]["cwd"],
                "exit_code": 0,
                "observation": resolution.strip() or "resolução legado registrada",
            }
    redesigns = migrated.get("redesigns_by_seam", {})
    redesign_count = min(
        MAX_REDESIGNS_PER_UNIT,
        sum(value for value in redesigns.values() if isinstance(value, int))
        if isinstance(redesigns, dict)
        else 0,
    )
    required_gates: list[str] = ["migration-required"]
    gates: dict[str, Any] = {}
    if phase == "completed":
        required_gates = ["legacy-migrated"]
        gates = {
            "legacy-migrated": {
                "status": "passed",
                "revision": last_head,
                "evidence": {
                    "command": ["migration-v1"],
                    "cwd": ".",
                    "exit_code": 0,
                    "observation": "estado terminal preservado",
                },
            }
        }
    repository_root = str(root)
    legacy_unit_digest = hashlib.sha256(
        "\0".join(
            (
                "legacy-v1",
                repository_root,
                str(migrated["planning_version"]),
                str(migrated["plan_id"]),
                str(migrated["unit_id"]),
            )
        ).encode("utf-8")
    ).hexdigest()
    migrated.update(
        {
            "schema_version": SCHEMA_VERSION,
            "phase": phase,
            "unit_digest": legacy_unit_digest,
            "unit_identity_source": "legacy_v1",
            "task_brief": None,
            "task_brief_digest": None,
            "unit_identity": unit_identity(
                repository_root,
                migrated["planning_version"],
                migrated["plan_id"],
                legacy_unit_digest,
            ),
            "last_review_head": last_head,
            "pending_delta": None,
            "delta_submissions": 0,
            "redesign_count": redesign_count,
            "required_gates": required_gates,
            "gates": gates,
            "migration": {
                "from": 1,
                "legacy_last_review_head": legacy_head,
            },
        }
    )
    migrated.pop("status", None)
    migrated.pop("review_frozen", None)
    migrated.pop("redesigns_by_seam", None)
    event(migrated, "sidecar_migrated", source_version=1, target_version=2)
    return migrated


MIGRATIONS: dict[int, Callable[[dict[str, Any], Path], dict[str, Any]]] = {
    1: migrate_v1_to_v2
}


def migrate_state(state: Any, path: Path) -> tuple[dict[str, Any], bool]:
    if not isinstance(state, dict) or not isinstance(state.get("schema_version"), int):
        raise GuardError("sidecar incompatível")
    migrated = False
    value = state
    while value["schema_version"] < SCHEMA_VERSION:
        migration = MIGRATIONS.get(value["schema_version"])
        if migration is None:
            raise GuardError("migração de sidecar indisponível")
        value = migration(value, path)
        migrated = True
    if value["schema_version"] != SCHEMA_VERSION:
        raise GuardError("sidecar de versão futura não suportado")
    return value, migrated


def validate_blocker(
    blocker_id: str,
    blocker: Any,
    state: dict[str, Any],
    root: Path,
    seam: str,
) -> None:
    identifier(blocker_id, "blocker.id")
    if not isinstance(blocker, dict) or blocker.get("status") not in {
        "open",
        "resolved",
    }:
        raise GuardError(f"blocker {blocker_id}: estado inválido")
    if blocker.get("severity") not in BLOCKING_SEVERITIES:
        raise GuardError(f"blocker {blocker_id}: severity inválida")
    if blocker.get("disposition") != "blocker" or not nonempty(blocker.get("title")):
        raise GuardError(f"blocker {blocker_id}: classificação inválida")
    missing = [field for field in PROOF_FIELDS if not nonempty(blocker.get(field))]
    if missing:
        raise GuardError(f"blocker {blocker_id}: provas ausentes: {', '.join(missing)}")
    legacy = state.get("unit_identity_source") == "legacy_v1"
    if legacy:
        if blocker.get("source") == "delta_regression":
            reproduction = validate_reproduction(blocker.get("reproduction"), root)
        else:
            reproduction = validate_execution_evidence(
                blocker.get("reproduction"),
                root,
                f"blocker {blocker_id}.reproduction",
                require_success=False,
            )
        if blocker.get("status") == "resolved":
            resolution = validate_execution_evidence(
                blocker.get("resolution_evidence"),
                root,
                f"blocker {blocker_id}.resolution_evidence",
                require_success=True,
            )
            if (
                resolution["command"] != reproduction["command"]
                or resolution["cwd"] != reproduction["cwd"]
            ):
                raise GuardError(
                    f"blocker {blocker_id}: resolução não reproduz a prova congelada"
                )
        validate_structural_fields(blocker, root, seam, allow_legacy=True)
        return
    brief = frozen_task_brief_content(state, root)
    if blocker["approved_requirement"].strip() not in brief:
        raise GuardError(f"blocker {blocker_id}: approved_requirement não congelado")
    if blocker.get("source") == "delta_regression":
        base_proof = state_proof(state, blocker.get("base_proof_id"))
        head_proof = state_proof(state, blocker.get("head_proof_id"))
        delta_base = resolve_commit(
            root, str(blocker.get("delta_base", "")), f"blocker {blocker_id}.delta_base"
        )
        delta_head = resolve_commit(
            root, str(blocker.get("delta_head", "")), f"blocker {blocker_id}.delta_head"
        )
        if base_proof["commit"] != delta_base or head_proof["commit"] != delta_head:
            raise GuardError(
                f"blocker {blocker_id}: proofs não pertencem ao delta congelado"
            )
        if base_proof["spawn_error"] or head_proof["spawn_error"]:
            raise GuardError(f"blocker {blocker_id}: comando de proof não executou")
        if base_proof["exit_code"] != 0 or head_proof["exit_code"] == 0:
            raise GuardError(f"blocker {blocker_id}: proofs de regressão inválidos")
        if (
            base_proof["command"] != head_proof["command"]
            or base_proof["cwd"] != head_proof["cwd"]
        ):
            raise GuardError(f"blocker {blocker_id}: comandos de regressão divergem")
        reproduction = head_proof
    else:
        reproduction = state_proof(state, blocker.get("proof_id"))
        review_commit = resolve_commit(
            root,
            str(blocker.get("review_commit", "")),
            f"blocker {blocker_id}.review_commit",
        )
        if reproduction["commit"] != review_commit:
            raise GuardError(
                f"blocker {blocker_id}: proof não pertence à revisão congelada"
            )
        if reproduction["spawn_error"]:
            raise GuardError(f"blocker {blocker_id}: comando de proof não executou")
        if reproduction["exit_code"] == 0:
            raise GuardError(f"blocker {blocker_id}: proof inicial está verde")
    if blocker.get("status") == "resolved":
        resolution = state_proof(state, blocker.get("resolution_proof_id"))
        resolved_commit = resolve_commit(
            root,
            str(blocker.get("resolved_commit", "")),
            f"blocker {blocker_id}.resolved_commit",
        )
        if resolution["commit"] != resolved_commit:
            raise GuardError(f"blocker {blocker_id}: proof não pertence à resolução")
        if resolution["spawn_error"]:
            raise GuardError(f"blocker {blocker_id}: comando de resolução não executou")
        if resolution["exit_code"] != 0:
            raise GuardError(f"blocker {blocker_id}: proof de resolução está vermelho")
        if (
            resolution["command"] != reproduction["command"]
            or resolution["cwd"] != reproduction["cwd"]
        ):
            raise GuardError(
                f"blocker {blocker_id}: resolução não reproduz a prova congelada"
            )
    expected_structural_commit = reproduction["commit"]
    validate_structural_fields(
        blocker,
        root,
        seam,
        state=state,
        expected_commit=expected_structural_commit,
    )


def validate_state(state: Any, path: Path) -> dict[str, Any]:
    if not isinstance(state, dict) or state.get("schema_version") != SCHEMA_VERSION:
        raise GuardError("sidecar incompatível")
    if "ask_user" in json.dumps(state, ensure_ascii=False, sort_keys=True):
        raise GuardError("sidecar contém estado proibido")
    required = (
        "unit_id",
        "unit_digest",
        "unit_identity_source",
        "task_brief",
        "task_brief_digest",
        "plan_id",
        "planning_version",
        "repository_root",
        "unit_identity",
        "seam",
        "phase",
        "last_review_head",
        "pending_delta",
        "delta_submissions",
        "blockers",
        "deferred_hardening",
        "fix_rounds",
        "redesign_count",
        "required_gates",
        "gates",
        "decisions",
        "events",
    )
    missing = [field for field in required if field not in state]
    if missing:
        raise GuardError(f"sidecar incompleto: {', '.join(missing)}")
    root = validate_repository(Path(state["repository_root"]))
    for field in ("unit_id", "plan_id", "planning_version", "seam"):
        identifier(str(state[field]), field)
    unit_digest = digest_identifier(str(state["unit_digest"]), "unit_digest")
    expected_identity = unit_identity(
        str(root), state["planning_version"], state["plan_id"], unit_digest
    )
    if state["unit_identity"] != expected_identity:
        raise GuardError("unit_identity inválida")
    identity_source = state["unit_identity_source"]
    if identity_source == "task_brief":
        task_brief, task_brief_digest = validate_task_brief(
            root, str(state["task_brief"]), unit_digest
        )
        if (
            task_brief != state["task_brief"]
            or task_brief_digest != state["task_brief_digest"]
        ):
            raise GuardError("task-brief da identidade foi alterado")
    elif (
        identity_source != "legacy_v1"
        or state["task_brief"] is not None
        or state["task_brief_digest"] is not None
    ):
        raise GuardError("fonte da identidade da unidade inválida")
    expected_path = canonical_sidecar(
        root, state["planning_version"], state["plan_id"], state["unit_id"]
    )
    confined = confined_path(root, path, "sidecar", must_exist=True)
    if confined != expected_path:
        raise SecurityGuardError(f"sidecar fora do caminho canônico: {expected_path}")
    if state["phase"] not in PHASES:
        raise GuardError("phase inválida")
    resolve_commit(root, state["last_review_head"], "last_review_head")
    if not isinstance(state["blockers"], dict):
        raise GuardError("blockers inválidos")
    for blocker_id, blocker in state["blockers"].items():
        validate_blocker(blocker_id, blocker, state, root, state["seam"])
    if not isinstance(state["deferred_hardening"], list) or not all(
        isinstance(item, dict) for item in state["deferred_hardening"]
    ):
        raise GuardError("deferred_hardening inválido")
    for counter, maximum, label in (
        (state["fix_rounds"], MAX_FIX_ROUNDS, "fix_rounds"),
        (state["redesign_count"], MAX_REDESIGNS_PER_UNIT, "redesign_count"),
    ):
        if (
            not isinstance(counter, int)
            or isinstance(counter, bool)
            or not 0 <= counter <= maximum
        ):
            raise GuardError(f"{label} inválido")
    if (
        not isinstance(state["delta_submissions"], int)
        or isinstance(state["delta_submissions"], bool)
        or state["delta_submissions"] < 0
    ):
        raise GuardError("delta_submissions inválido")
    if not isinstance(state["required_gates"], list) or not state["required_gates"]:
        raise GuardError("required_gates deve conter ao menos um gate")
    if not all(
        isinstance(item, str) and IDENTIFIER.fullmatch(item)
        for item in state["required_gates"]
    ):
        raise GuardError("required_gates inválido")
    if not isinstance(state["gates"], dict):
        raise GuardError("gates inválido")
    for gate, result in state["gates"].items():
        identifier(str(gate), "gate")
        if gate not in state["required_gates"] or not isinstance(result, dict):
            raise GuardError("gate não declarado ou inválido")
        status = result.get("status")
        if status not in {"passed", "failed"}:
            raise GuardError("status de gate inválido")
        revision = resolve_commit(
            root, str(result.get("revision", "")), "gate.revision"
        )
        if revision != result.get("revision"):
            raise GuardError("gate.revision deve ser commit canônico")
        if state.get("unit_identity_source") == "legacy_v1":
            validate_execution_evidence(
                result.get("evidence"),
                root,
                f"gate {gate}.evidence",
                require_success=status == "passed",
            )
        else:
            proof = state_proof(state, result.get("proof_id"))
            if proof["spawn_error"]:
                raise GuardError("gate usa proof cujo comando não executou")
            expected_status = "passed" if proof["exit_code"] == 0 else "failed"
            if proof["commit"] != revision or status != expected_status:
                raise GuardError("gate diverge do proof registrado")
    if not isinstance(state["decisions"], list) or not all(
        isinstance(item, dict) for item in state["decisions"]
    ):
        raise GuardError("decisions inválido")
    if not isinstance(state["events"], list) or not all(
        isinstance(item, dict) for item in state["events"]
    ):
        raise GuardError("histórico inválido")
    pending = state["pending_delta"]
    if state["phase"] == "awaiting_review":
        if not isinstance(pending, dict) or pending.get("kind") not in {
            "implementation",
            "fix",
            "redesign",
            "verification",
        }:
            raise GuardError("awaiting_review exige pending_delta válido")
        pending_base, pending_head = verify_delta(
            root,
            str(pending.get("base", "")),
            str(pending.get("head", "")),
            state["last_review_head"],
        )
        if pending.get("kind") == "verification":
            ensure_pending_verification_state(state, pending)
            ensure_verification_delta_only(root, pending_base, pending_head)
    elif pending is not None:
        raise GuardError("pending_delta fora de awaiting_review")
    if state["phase"] == "fixing" and state["fix_rounds"] < 1:
        raise GuardError("fixing exige fix round registrado")
    if state["phase"] == "redesigning" and state["redesign_count"] != 1:
        raise GuardError("redesigning exige redesign registrado")
    if state["phase"] == "parked" and not open_blockers(state):
        raise GuardError("parked exige blocker aberto")
    if state["phase"] == "completed":
        if open_blockers(state):
            raise GuardError("completed contém blocker aberto")
        if any(
            state["gates"].get(gate, {}).get("status") != "passed"
            for gate in state["required_gates"]
        ):
            raise GuardError("completed sem gates aprovados")
    if state["phase"] == "stopped":
        stop = state.get("stop")
        if not isinstance(stop, dict) or stop.get("kind") not in STOP_KINDS:
            raise GuardError("stopped sem categoria válida")
        validate_stop_evidence(
            stop["kind"],
            stop.get("evidence"),
            root,
            state,
            resolve_commit(root, str(stop.get("commit", "")), "stop.commit"),
        )
    return state


def load_sidecar(path: Path) -> tuple[dict[str, Any], bool, bool]:
    if path.is_symlink():
        raise SecurityGuardError("sidecar não pode ser symlink")
    recovered = False
    try:
        raw = load_json(path, "sidecar")
    except GuardError as primary_error:
        backup = path.with_suffix(path.suffix + ".bak")
        if not backup.exists() or backup.is_symlink():
            raise primary_error
        raw = load_json(backup, "backup do sidecar")
        recovered = True
    state, migrated = migrate_state(raw, path)
    try:
        state = validate_state(state, path)
    except GuardError as primary_error:
        backup = path.with_suffix(path.suffix + ".bak")
        if recovered or not backup.exists() or backup.is_symlink():
            raise primary_error
        backup_state, backup_migrated = migrate_state(
            load_json(backup, "backup do sidecar"), path
        )
        state = validate_state(backup_state, path)
        recovered = True
        migrated = migrated or backup_migrated
    if recovered or migrated:
        write_atomic(path, state, rotate_backup=False)
    return state, recovered, migrated


def ensure_mutable(state: dict[str, Any]) -> None:
    if state["phase"] in TERMINAL_PHASES:
        raise GuardError(f"fase {state['phase']} é terminal")


def command_freeze(args: argparse.Namespace) -> dict[str, Any]:
    root = validate_repository(Path(args.root))
    path = canonical_sidecar(root, args.planning_version, args.plan, args.unit)
    if path.exists() or path.is_symlink():
        raise GuardError("primeira revisão já congelada para esta unidade")
    planning_version = identifier(args.planning_version, "planning_version")
    plan = identifier(args.plan, "plan")
    unit = identifier(args.unit, "unit")
    unit_digest = digest_identifier(args.unit_identity, "unit_identity")
    task_brief, task_brief_digest = validate_task_brief(
        root, args.task_brief, unit_digest
    )
    seam = identifier(args.seam, "seam")
    head = resolve_commit(root, args.review_head, "review_head")
    if head != current_head(root):
        raise GuardError("review_head deve coincidir com HEAD atual")
    required_gates = list(dict.fromkeys(args.required_gate))
    for gate in required_gates:
        identifier(gate, "required_gate")
    identity = unit_identity(str(root), planning_version, plan, unit_digest)
    for sibling in path.parent.glob("*.json"):
        if sibling.is_symlink():
            raise SecurityGuardError("sidecar irmão não pode ser symlink")
        sibling_state, _ = migrate_state(load_json(sibling, "sidecar irmão"), sibling)
        sibling_state = validate_state(sibling_state, sibling)
        if sibling_state["unit_identity"] == identity:
            raise GuardError(
                "identidade da unidade já possui sidecar; renomear unit não reinicia limites"
            )
    blockers: dict[str, Any] = {}
    hardening: list[dict[str, Any]] = []
    seen: set[str] = set()
    proof_context = {
        "repository_root": str(root),
        "planning_version": planning_version,
        "plan_id": plan,
        "unit_id": unit,
    }
    try:
        brief_content = (root / task_brief).read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise GuardError("task-brief ilegível") from error
    accepted_root_causes: dict[str, str] = {}
    for raw in findings_from(Path(args.findings), root):
        finding = normalize_initial_finding(
            raw, proof_context, root, seam, brief_content, head
        )
        if finding["id"] in seen:
            raise GuardError(f"finding duplicado: {finding['id']}")
        seen.add(finding["id"])
        if finding["disposition"] == "blocker":
            root_cause = str(finding.get("root_cause") or finding["title"]).strip()
            root_cause_key = " ".join(root_cause.casefold().split())
            if root_cause_key in accepted_root_causes:
                hardening.append(
                    {
                        **sanitized_hardening(finding),
                        "disposition": "hardening",
                        "deferred_reason": "causa raiz consolidada no blocker "
                        + accepted_root_causes[root_cause_key],
                        "deferred_at": now(),
                    }
                )
            elif len(accepted_root_causes) >= MAX_INITIAL_BLOCKERS:
                hardening.append(
                    {
                        **sanitized_hardening(finding),
                        "disposition": "hardening",
                        "deferred_reason": "limite de três blockers iniciais consolidados atingido",
                        "deferred_at": now(),
                    }
                )
            else:
                finding["root_cause"] = root_cause
                accepted_root_causes[root_cause_key] = finding["id"]
                blockers[finding["id"]] = {
                    **finding,
                    "source": "initial",
                    "status": "open",
                    "review_commit": head,
                }
        else:
            hardening.append({**sanitized_hardening(finding), "deferred_at": now()})
    state: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "unit_id": unit,
        "unit_digest": unit_digest,
        "unit_identity_source": "task_brief",
        "task_brief": task_brief,
        "task_brief_digest": task_brief_digest,
        "plan_id": plan,
        "planning_version": planning_version,
        "repository_root": str(root),
        "unit_identity": identity,
        "seam": seam,
        "phase": "review_frozen",
        "last_review_head": head,
        "pending_delta": None,
        "delta_submissions": 0,
        "blockers": blockers,
        "deferred_hardening": hardening,
        "fix_rounds": 0,
        "redesign_count": 0,
        "required_gates": required_gates,
        "gates": {},
        "decisions": [],
        "events": [],
        "created_at": now(),
        "updated_at": now(),
    }
    event(state, "review_frozen", blockers=sorted(blockers), hardening=len(hardening))
    write_atomic(path, state)
    next_action = determine_next_action(state)
    return {
        "phase": state["phase"],
        "next_action": next_action,
        "sidecar": str(path),
        "state": state,
    }


def command_fix(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.sidecar)
    state, recovered, migrated = load_sidecar(path)
    ensure_mutable(state)
    if determine_next_action(state) != "fix_required":
        raise GuardError("fix não permitido pela revisão congelada")
    blockers = list(dict.fromkeys(args.blocker))
    if not blockers or any(blocker not in open_blockers(state) for blocker in blockers):
        raise GuardError("fix exige blockers abertos")
    if state["fix_rounds"] >= MAX_FIX_ROUNDS:
        raise GuardError("terceiro fix round proibido")
    state["fix_rounds"] += 1
    transition(state, "fix", "fixing")
    event(
        state,
        "fix_started",
        round=state["fix_rounds"],
        blockers=blockers,
        summary=args.summary,
    )
    write_atomic(path, state)
    return {
        "phase": state["phase"],
        "recovered": recovered,
        "migrated": migrated,
        "state": state,
    }


def command_redesign(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.sidecar)
    state, recovered, migrated = load_sidecar(path)
    ensure_mutable(state)
    if state["phase"] != "review_frozen":
        raise GuardError("redesign exige revisão congelada")
    if determine_next_action(state) != "redesign_allowed":
        raise GuardError("redesign exige blocker estrutural aberto após dois fixes")
    if args.seam != state["seam"]:
        raise GuardError(
            "seam do redesign deve coincidir exatamente com seam congelado"
        )
    if state["redesign_count"] >= MAX_REDESIGNS_PER_UNIT:
        raise GuardError("segundo redesign da unidade é proibido")
    blocker = state["blockers"].get(args.blocker)
    if not blocker or blocker["status"] != "open" or not blocker["structural"]:
        raise GuardError("redesign exige blocker estrutural aberto")
    if blocker["structural_evidence"] is None:
        raise GuardError("redesign exige structural_evidence reproduzível")
    state["redesign_count"] += 1
    transition(state, "redesign", "redesigning")
    event(
        state,
        "redesign_started",
        blocker=args.blocker,
        seam=state["seam"],
        unit_identity=state["unit_identity"],
        summary=args.summary,
    )
    write_atomic(path, state)
    return {
        "phase": state["phase"],
        "recovered": recovered,
        "migrated": migrated,
        "state": state,
    }


def command_submit_delta(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.sidecar)
    state, recovered, migrated = load_sidecar(path)
    ensure_mutable(state)
    source = state["phase"]
    expected = {
        "implementation": "review_frozen",
        "fix": "fixing",
        "redesign": "redesigning",
        "verification": "review_frozen",
    }[args.kind]
    if source != expected:
        raise GuardError(f"submit-delta {args.kind} inválido na fase {source}")
    if args.kind == "implementation":
        if state["delta_submissions"] != 0 or open_blockers(state):
            raise GuardError("delta de implementação inicial exige unidade sem blocker")
    root = Path(state["repository_root"])
    base, head = verify_delta(root, args.base, args.head, state["last_review_head"])
    if args.kind == "verification":
        ensure_clean_implementation_review(state)
        ensure_verification_delta_only(root, base, head)
    transition(state, "submit_delta", "awaiting_review")
    state["pending_delta"] = {
        "kind": args.kind,
        "base": base,
        "head": head,
        "submitted_at": now(),
    }
    event(state, "delta_submitted", kind=args.kind, base=base, head=head)
    write_atomic(path, state)
    return {
        "phase": state["phase"],
        "recovered": recovered,
        "migrated": migrated,
        "state": state,
    }


def command_review(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.sidecar)
    state, recovered, migrated = load_sidecar(path)
    ensure_mutable(state)
    if state["phase"] != "awaiting_review":
        raise GuardError("review só pode executar em awaiting_review")
    pending = state.get("pending_delta")
    if not isinstance(pending, dict):
        raise GuardError("review sem delta submetido")
    root = Path(state["repository_root"])
    base, head = verify_delta(
        root, pending["base"], pending["head"], state["last_review_head"]
    )
    hunks = parse_diff(root, base, head)
    accepted: list[str] = []
    resolved: list[str] = []
    hardening: list[str] = []
    for raw in findings_from(Path(args.findings), root):
        finding_id = identifier(str(raw.get("id", "")), "finding.id")
        source = raw.get("source")
        if source == "frozen":
            blocker = state["blockers"].get(finding_id)
            if not blocker or blocker["status"] != "open":
                raise GuardError(
                    f"finding {finding_id}: blocker congelado aberto inexistente"
                )
            resolution = raw.get("resolution", "open")
            if resolution not in {"open", "resolved"}:
                raise GuardError("resolution deve ser open ou resolved")
            if resolution == "resolved":
                if any(
                    field in raw
                    for field in ("resolution_evidence", "exit_code", "command", "cwd")
                ):
                    raise GuardError(
                        "resolução aceita somente proof_id gerado pelo guard"
                    )
                proof_id = raw.get("proof_id")
                evidence = require_proof(
                    state,
                    proof_id,
                    commit=head,
                    success=True,
                    label="resolução",
                )
                if blocker.get("source") == "delta_regression":
                    reproduction = state_proof(state, blocker["head_proof_id"])
                else:
                    reproduction = state_proof(state, blocker["proof_id"])
                if (
                    evidence["command"] != reproduction["command"]
                    or evidence["cwd"] != reproduction["cwd"]
                ):
                    raise GuardError(
                        "proof de resolução deve executar o mesmo comando do blocker"
                    )
                blocker["status"] = "resolved"
                blocker["resolution_proof_id"] = proof_id
                blocker["resolved_commit"] = head
                blocker["resolved_at"] = now()
                resolved.append(finding_id)
            accepted.append(finding_id)
            continue
        if source != "delta_regression":
            raise GuardError(f"finding {finding_id}: source fora do escopo da revisão")
        if finding_id in state["blockers"] or any(
            item.get("id") == finding_id for item in state["deferred_hardening"]
        ):
            raise GuardError(f"finding {finding_id}: id já existe")
        try:
            blocker = validate_delta_regression(raw, state, root, hunks, base, head)
        except SecurityGuardError:
            raise
        except GuardError as error:
            deferred = sanitized_hardening(raw)
            deferred.update(
                {
                    "id": finding_id,
                    "disposition": "hardening",
                    "deferred_reason": str(error),
                    "deferred_at": now(),
                }
            )
            state["deferred_hardening"].append(deferred)
            hardening.append(finding_id)
        else:
            state["blockers"][finding_id] = blocker
            accepted.append(finding_id)
    state["last_review_head"] = head
    state["pending_delta"] = None
    state["delta_submissions"] += 1
    provisional = determine_next_action(state)
    target = "parked" if provisional == "park_unit" else "review_frozen"
    transition(state, "review", target)
    next_action = determine_next_action(state)
    event(
        state,
        "review_frozen",
        accepted=accepted,
        resolved=resolved,
        hardening=hardening,
        next_action=next_action,
    )
    write_atomic(path, state)
    return {
        "phase": state["phase"],
        "next_action": next_action,
        "recovered": recovered,
        "migrated": migrated,
        "state": state,
    }


def command_gate(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.sidecar)
    state, recovered, migrated = load_sidecar(path)
    ensure_mutable(state)
    gate = identifier(args.gate, "gate")
    if gate not in state["required_gates"]:
        raise GuardError("gate não declarado como obrigatório")
    root = Path(state["repository_root"])
    revision = current_head(root)
    proof = state_proof(state, args.proof_id)
    if proof["commit"] != revision:
        raise GuardError("gate exige proof do HEAD atual")
    if proof["spawn_error"]:
        raise GuardError("gate exige comando de proof executado")
    status = "passed" if proof["exit_code"] == 0 else "failed"
    state["gates"][gate] = {
        "status": status,
        "revision": revision,
        "proof_id": args.proof_id,
        "recorded_at": now(),
    }
    event(state, "gate_recorded", gate=gate, status=status, proof_id=args.proof_id)
    write_atomic(path, state)
    return {
        "phase": state["phase"],
        "recovered": recovered,
        "migrated": migrated,
        "state": state,
    }


def validate_stop_evidence(
    kind: str,
    value: Any,
    root: Path,
    state: dict[str, Any],
    expected_commit: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GuardError("stop evidence deve ser objeto")
    if kind == "essential_external_credential":
        fields = (
            "service",
            "missing_credential",
            "blocked_operation",
            "local_alternative_proof",
        )
        if any(not nonempty(value.get(field)) for field in fields):
            raise GuardError("evidência de credencial externa incompleta")
        return {field: value[field].strip() for field in fields}
    if kind == "destructive_action":
        fields = ("action", "target", "irreversible_effect", "safe_alternative_proof")
        if any(not nonempty(value.get(field)) for field in fields):
            raise GuardError("evidência de ação destrutiva incompleta")
        return {field: value[field].strip() for field in fields}
    if kind == "new_cost":
        fields = ("provider", "operation", "indispensability_proof")
        if any(not nonempty(value.get(field)) for field in fields):
            raise GuardError("evidência de custo novo incompleta")
        estimate = value.get("estimate")
        currency = value.get("currency")
        if (
            not isinstance(estimate, (int, float))
            or isinstance(estimate, bool)
            or estimate <= 0
            or not isinstance(currency, str)
            or not re.fullmatch(r"[A-Z]{3}", currency)
        ):
            raise GuardError("estimate/currency inválidos para custo novo")
        return {
            **{field: value[field].strip() for field in fields},
            "estimate": estimate,
            "currency": currency,
        }
    if kind == "material_change":
        fields = (
            "approved_requirement",
            "change_kind",
            "current_contract",
            "required_change",
            "execution_blocker",
            "evidence_proof_id",
        )
        if any(not nonempty(value.get(field)) for field in fields):
            raise GuardError("evidência de mudança material incompleta")
        change_kind = value["change_kind"].strip()
        if change_kind not in MATERIAL_CHANGE_KINDS:
            raise GuardError("change_kind inválido para mudança material")
        brief_content = frozen_task_brief_content(state, root)
        approved_requirement = value["approved_requirement"].strip()
        if approved_requirement not in brief_content:
            raise GuardError("approved_requirement ausente do task-brief congelado")
        proof_id = value["evidence_proof_id"].strip()
        require_proof(
            state,
            proof_id,
            commit=expected_commit,
            success=False,
            label="material_change.evidence_proof_id",
        )
        return {
            "approved_requirement": approved_requirement,
            "change_kind": change_kind,
            "current_contract": value["current_contract"].strip(),
            "required_change": value["required_change"].strip(),
            "execution_blocker": value["execution_blocker"].strip(),
            "evidence_proof_id": proof_id,
        }
    if kind == "real_impossibility":
        if not nonempty(value.get("invariant")) or not nonempty(
            value.get("safe_workaround_absence_proof")
        ):
            raise GuardError("evidência de impossibilidade incompleta")
        attempts = value.get("attempts")
        if not isinstance(attempts, list) or not attempts:
            raise GuardError("real_impossibility exige tentativas")
        normalized_attempts: list[dict[str, str]] = []
        for index, attempt in enumerate(attempts):
            if not isinstance(attempt, dict) or set(attempt) != {"proof_id"}:
                raise GuardError(
                    f"attempts[{index}] aceita somente proof_id gerado pelo guard"
                )
            proof_id = attempt["proof_id"]
            require_proof(
                state,
                proof_id,
                commit=expected_commit,
                success=False,
                label=f"attempts[{index}]",
            )
            normalized_attempts.append({"proof_id": proof_id})
        return {
            "invariant": value["invariant"].strip(),
            "attempts": normalized_attempts,
            "safe_workaround_absence_proof": value[
                "safe_workaround_absence_proof"
            ].strip(),
        }
    raise GuardError("categoria de parada inválida")


def command_stop(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.sidecar)
    state, recovered, migrated = load_sidecar(path)
    ensure_mutable(state)
    if args.kind not in STOP_KINDS:
        raise GuardError(f"somente {len(STOP_KINDS)} categorias podem produzir stopped")
    root = Path(state["repository_root"])
    evidence_path = confined_path(root, args.evidence, "stop evidence", must_exist=True)
    head = current_head(root)
    evidence = validate_stop_evidence(
        args.kind,
        load_json(evidence_path, "stop evidence"),
        root,
        state,
        head,
    )
    transition(state, "stop", "stopped")
    state["stop"] = {
        "kind": args.kind,
        "evidence": evidence,
        "commit": head,
        "at": now(),
    }
    event(state, "stopped", kind=args.kind)
    write_atomic(path, state)
    return {
        "phase": state["phase"],
        "next_action": "stopped",
        "recovered": recovered,
        "migrated": migrated,
        "state": state,
    }


def command_decision(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.sidecar)
    state, recovered, migrated = load_sidecar(path)
    ensure_mutable(state)
    if args.kind not in {"internal", "local_block"}:
        raise GuardError("decision aceita somente internal ou local_block")
    if not nonempty(args.summary):
        raise GuardError("summary obrigatório")
    result = "automatic" if args.kind == "internal" else "independent_work_continues"
    state["decisions"].append(
        {
            "kind": args.kind,
            "summary": args.summary.strip(),
            "result": result,
            "at": now(),
        }
    )
    event(state, "decision", kind=args.kind, result=result)
    write_atomic(path, state)
    return {
        "phase": state["phase"],
        "result": result,
        "recovered": recovered,
        "migrated": migrated,
        "state": state,
    }


def command_complete(args: argparse.Namespace) -> dict[str, Any]:
    path = Path(args.sidecar)
    state, recovered, migrated = load_sidecar(path)
    ensure_mutable(state)
    if state["phase"] != "review_frozen":
        raise GuardError("complete exige review_frozen")
    blockers = open_blockers(state)
    if blockers:
        raise GuardError(f"blockers abertos impedem conclusão: {', '.join(blockers)}")
    missing = [
        gate
        for gate in state["required_gates"]
        if state["gates"].get(gate, {}).get("status") != "passed"
    ]
    if missing:
        raise GuardError(f"gates obrigatórios sem aprovação: {', '.join(missing)}")
    head = current_head(Path(state["repository_root"]))
    if head != state["last_review_head"]:
        raise GuardError("HEAD atual ainda não foi revisado")
    stale = [
        gate
        for gate in state["required_gates"]
        if state["gates"][gate].get("revision") != head
    ]
    if stale:
        raise GuardError(f"gates executados em revision antiga: {', '.join(stale)}")
    transition(state, "complete", "completed")
    state["completed_at"] = now()
    event(state, "completed", deferred_hardening=len(state["deferred_hardening"]))
    write_atomic(path, state)
    return {
        "phase": state["phase"],
        "next_action": "completed",
        "recovered": recovered,
        "migrated": migrated,
        "state": state,
    }


def command_status(args: argparse.Namespace) -> dict[str, Any]:
    state, recovered, migrated = load_sidecar(Path(args.sidecar))
    result = {
        "phase": state["phase"],
        "recovered": recovered,
        "migrated": migrated,
        "state": state,
    }
    if state["phase"] in {"review_frozen", "parked", "completed", "stopped"}:
        result["next_action"] = determine_next_action(state)
    return result


def command_migrate(args: argparse.Namespace) -> dict[str, Any]:
    state, recovered, migrated = load_sidecar(Path(args.sidecar))
    return {
        "phase": state["phase"],
        "recovered": recovered,
        "migrated": migrated,
        "state": state,
    }


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    subparsers = value.add_subparsers(dest="command", required=True)

    proof = subparsers.add_parser("proof")
    proof.add_argument("--root", required=True)
    proof.add_argument("--planning-version", required=True)
    proof.add_argument("--plan", required=True)
    proof.add_argument("--unit", required=True)
    proof.add_argument("--commit", required=True)
    proof.add_argument("--cwd", required=True)
    proof.add_argument("--timeout", required=True, type=float)
    proof.add_argument("argv", nargs=argparse.REMAINDER)
    proof.set_defaults(handler=command_proof)

    freeze = subparsers.add_parser("freeze")
    freeze.add_argument("--root", required=True)
    freeze.add_argument("--planning-version", required=True)
    freeze.add_argument("--plan", required=True)
    freeze.add_argument("--unit", required=True)
    freeze.add_argument("--unit-identity", required=True)
    freeze.add_argument("--task-brief", required=True)
    freeze.add_argument("--seam", required=True)
    freeze.add_argument("--review-head", required=True)
    freeze.add_argument("--findings", required=True)
    freeze.add_argument("--required-gate", action="append", required=True)
    freeze.set_defaults(handler=command_freeze)

    fix = subparsers.add_parser("fix")
    fix.add_argument("--sidecar", required=True)
    fix.add_argument("--blocker", action="append", required=True)
    fix.add_argument("--summary", required=True)
    fix.set_defaults(handler=command_fix)

    redesign = subparsers.add_parser("redesign")
    redesign.add_argument("--sidecar", required=True)
    redesign.add_argument("--blocker", required=True)
    redesign.add_argument("--seam", required=True)
    redesign.add_argument("--summary", required=True)
    redesign.set_defaults(handler=command_redesign)

    submit = subparsers.add_parser("submit-delta")
    submit.add_argument("--sidecar", required=True)
    submit.add_argument(
        "--kind",
        choices=("implementation", "fix", "redesign", "verification"),
        required=True,
    )
    submit.add_argument("--base", required=True)
    submit.add_argument("--head", required=True)
    submit.set_defaults(handler=command_submit_delta)

    review = subparsers.add_parser("review")
    review.add_argument("--sidecar", required=True)
    review.add_argument("--findings", required=True)
    review.set_defaults(handler=command_review)

    gate = subparsers.add_parser("gate")
    gate.add_argument("--sidecar", required=True)
    gate.add_argument("--gate", required=True)
    gate.add_argument("--proof-id", required=True)
    gate.set_defaults(handler=command_gate)

    stop = subparsers.add_parser("stop")
    stop.add_argument("--sidecar", required=True)
    stop.add_argument("--kind", choices=tuple(sorted(STOP_KINDS)), required=True)
    stop.add_argument("--evidence", required=True)
    stop.set_defaults(handler=command_stop)

    decision = subparsers.add_parser("decision")
    decision.add_argument("--sidecar", required=True)
    decision.add_argument("--kind", choices=("internal", "local_block"), required=True)
    decision.add_argument("--summary", required=True)
    decision.set_defaults(handler=command_decision)

    for name, handler in (
        ("complete", command_complete),
        ("status", command_status),
        ("migrate", command_migrate),
    ):
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
