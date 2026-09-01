#!/usr/bin/env python3
"""Propostas de aprendizado governadas, determinísticas e opt-in."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
import fcntl
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from bm_project_model import read_frontmatter


CLASSIFICATIONS = frozenset(
    {
        "environment_fact",
        "human_preference",
        "repeatable_procedure",
        "deterministic_invariant",
        "architecture_decision",
        "isolated_error",
    }
)
APPROVABLE = frozenset({"repeatable_procedure", "deterministic_invariant"})
TERMINAL_SUCCESS = frozenset({"resolved", "completed", "passed", "accepted"})
CANDIDATE_ID = re.compile(r"L[0-9A-F]{12}")


class LearningError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def _fail(code: str, message: str) -> None:
    raise LearningError(code, message)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _canonical(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _digest(value: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _repo_root(repo: str | Path) -> Path:
    raw = Path(repo).absolute()
    if raw.is_symlink() or any(part.casefold() == ".planning" for part in raw.parts):
        _fail("LEARNING_PATH_INVALID", "raiz insegura")
    completed = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=raw,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        _fail("LEARNING_PATH_INVALID", "repo Git obrigatório")
    root = Path(completed.stdout.strip()).resolve()
    if root != raw.resolve():
        _fail("LEARNING_PATH_INVALID", "--repo deve apontar para a raiz Git")
    return root


def _fixed_dir(root: Path, relative: str, *, create: bool) -> Path:
    path = root
    for part in Path(relative).parts:
        path = path / part
        if path.is_symlink():
            _fail("LEARNING_PATH_INVALID", f"symlink não permitido: {relative}")
        if path.exists() and not path.is_dir():
            _fail("LEARNING_PATH_INVALID", f"diretório inválido: {relative}")
        if create:
            path.mkdir(exist_ok=True)
            _sync_directory(path.parent)
    return path


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _sync_directory(path.parent)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _durable_unlink(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    _sync_directory(path.parent)


def _approved_transition_matches(
    existing: dict[str, Any], candidate: dict[str, Any], digest: str, actor: str
) -> bool:
    if (
        existing.get("status") != "approved"
        or existing.get("active") is not True
        or existing.get("approved_by") != actor
        or existing.get("approved_digest") != digest
        or not isinstance(existing.get("approved_at"), str)
        or not existing["approved_at"].strip()
    ):
        return False
    reconstructed = dict(existing)
    for key in ("active", "approved_by", "approved_digest", "approved_at"):
        reconstructed.pop(key, None)
    reconstructed["status"] = "pending"
    reconstructed["digest"] = digest
    return _canonical(reconstructed) == _canonical(candidate)


def _rejected_transition_matches(
    existing: dict[str, Any], candidate: dict[str, Any], reason: str
) -> bool:
    if (
        existing.get("status") != "rejected"
        or existing.get("rejection_reason") != reason.strip()
        or not isinstance(existing.get("rejected_at"), str)
        or not existing["rejected_at"].strip()
    ):
        return False
    reconstructed = dict(existing)
    reconstructed.pop("rejection_reason", None)
    reconstructed.pop("rejected_at", None)
    reconstructed["status"] = "pending"
    return _canonical(reconstructed) == _canonical(candidate)


@contextmanager
def _exclusive_transition(root: Path) -> Iterable[None]:
    directory = _fixed_dir(root, ".bianchini/.runtime/learning", create=True)
    lock = directory / "transition.lock"
    if lock.is_symlink():
        _fail("LEARNING_PATH_INVALID", "lock de aprendizado não pode ser symlink")
    descriptor = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            _fail("LEARNING_BUSY", "outra transição de aprendizado está em execução")
            raise AssertionError from error
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _transition_locked(function):
    @wraps(function)
    def wrapped(repo: str | Path, *args: Any, **kwargs: Any) -> dict[str, Any]:
        root = _repo_root(repo)
        with _exclusive_transition(root):
            return function(root, *args, **kwargs)

    return wrapped


def _source_paths(root: Path, since: str | None) -> list[Path]:
    bianchini = _fixed_dir(root, ".bianchini", create=False)
    allowed_by_since: set[str] | None = None
    if since:
        checked = subprocess.run(
            ["git", "rev-parse", "--verify", f"{since}^{{commit}}"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        if checked.returncode != 0:
            _fail("LEARNING_SINCE_INVALID", f"ref inexistente: {since}")
        changed = subprocess.run(
            ["git", "diff", "--name-only", f"{since}..HEAD", "--", ".bianchini"],
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        if changed.returncode != 0:
            _fail("LEARNING_SINCE_INVALID", changed.stderr.strip() or "diff falhou")
        allowed_by_since = set(changed.stdout.splitlines())
    if not bianchini.is_dir():
        return []

    def add_file(result: set[Path], path: Path) -> None:
        relative = path.relative_to(root).as_posix()
        if any(part.casefold() == ".planning" for part in Path(relative).parts):
            return
        if path.is_symlink():
            _fail("LEARNING_PATH_INVALID", f"fonte symlink: {relative}")
        if path.is_file() and (allowed_by_since is None or relative in allowed_by_since):
            result.add(path)

    def add_markdown_tree(result: set[Path], directory: Path) -> None:
        if directory.is_symlink():
            _fail(
                "LEARNING_PATH_INVALID",
                f"diretório symlink: {directory.relative_to(root).as_posix()}",
            )
        if not directory.is_dir():
            return
        for current, directories, files in os.walk(directory, followlinks=False):
            current_path = Path(current)
            safe_directories: list[str] = []
            for name in sorted(directories):
                if name.casefold() == ".planning":
                    continue
                child = current_path / name
                if child.is_symlink():
                    _fail(
                        "LEARNING_PATH_INVALID",
                        f"diretório symlink: {child.relative_to(root).as_posix()}",
                    )
                safe_directories.append(name)
            directories[:] = safe_directories
            for name in sorted(files):
                if name.casefold() == ".planning":
                    continue
                path = current_path / name
                if path.suffix == ".md":
                    add_file(result, path)

    result: set[Path] = set()
    debug = _fixed_dir(root, ".bianchini/debug", create=False)
    resolved = _fixed_dir(root, ".bianchini/debug/resolved", create=False)
    if resolved.is_dir():
        for path in sorted(resolved.iterdir()):
            if path.suffix == ".md":
                add_file(result, path)
    add_file(result, debug / "KNOWLEDGE.md")
    for area in ("changes", "archive"):
        directory = _fixed_dir(root, f".bianchini/{area}", create=False)
        if not directory.is_dir():
            continue
        for work in sorted(directory.iterdir()):
            if work.name.casefold() == ".planning":
                continue
            if work.is_symlink():
                _fail(
                    "LEARNING_PATH_INVALID",
                    f"diretório symlink: {work.relative_to(root).as_posix()}",
                )
            if not work.is_dir():
                continue
            add_file(result, work / "COHERENCE.md")
            add_markdown_tree(result, work / "results")
    return sorted(result)


def _text_list(value: Any, label: str, *, required: bool = False) -> list[str]:
    if required and value is None:
        _fail("LEARNING_EVIDENCE_REQUIRED", f"{label} obrigatório")
    if not isinstance(value, list) or not all(
        isinstance(item, str) and item.strip() for item in value
    ):
        _fail("LEARNING_CANDIDATE_INVALID", f"{label} exige lista de textos")
    result = list(dict.fromkeys(item.strip() for item in value))
    if required and not result:
        _fail("LEARNING_EVIDENCE_REQUIRED", f"{label} não pode ser vazio")
    return result


def _extract_candidate(
    root: Path, source: Path, *, source_identity: str | None = None
) -> dict[str, Any] | None:
    try:
        text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        _fail("LEARNING_SOURCE_INVALID", f"{source.name}: {error}")
    if not text.startswith("---\n"):
        return None
    try:
        payload = read_frontmatter(source)
    except (OSError, UnicodeError, ValueError) as error:
        _fail("LEARNING_SOURCE_INVALID", f"{source.name}: {error}")
    raw = payload.get("learning_candidate")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        _fail("LEARNING_CANDIDATE_INVALID", "learning_candidate exige objeto")
    unknown = sorted(
        set(raw) - {"classification", "statement", "tags", "validity", "conflicts"}
    )
    if unknown:
        _fail("LEARNING_CANDIDATE_INVALID", f"campo desconhecido: {unknown[0]}")
    classification = raw.get("classification")
    if classification not in CLASSIFICATIONS:
        _fail("LEARNING_CANDIDATE_INVALID", "classification inválida")
    if classification == "isolated_error":
        return None
    if payload.get("status") not in TERMINAL_SUCCESS or not payload.get("green"):
        _fail(
            "LEARNING_EVIDENCE_REQUIRED",
            "somente fonte terminal com sucesso comprovado pode propor aprendizado",
        )
    evidence_value = payload.get("evidence")
    if evidence_value is None:
        evidence_value = payload.get("verification")
    if evidence_value is None and isinstance(payload.get("events"), list):
        evidence_value = [
            item["evidence"]
            for item in payload["events"]
            if isinstance(item, dict)
            and isinstance(item.get("evidence"), str)
            and item["evidence"].strip()
        ]
    evidence = _text_list(evidence_value, "evidence", required=True)
    statement = raw.get("statement")
    validity = raw.get("validity")
    if not isinstance(statement, str) or not statement.strip():
        _fail("LEARNING_CANDIDATE_INVALID", "statement obrigatório")
    if not isinstance(validity, str) or not validity.strip():
        _fail("LEARNING_CANDIDATE_INVALID", "validity obrigatória")
    tags = _text_list(raw.get("tags"), "tags", required=True)
    conflicts = _text_list(raw.get("conflicts"), "conflicts")
    relative = source_identity or source.relative_to(root).as_posix()
    source_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    base = {
        "schema_version": 1,
        "status": "pending",
        "classification": classification,
        "statement": statement.strip(),
        "tags": tags,
        "validity": validity.strip(),
        "conflicts": conflicts,
        "evidence": evidence,
        "source": relative,
        "source_digest": source_digest,
    }
    identifier = "L" + _digest(base)[:12].upper()
    candidate = {"id": identifier, **base}
    candidate["digest"] = _digest(candidate)
    return candidate


def candidate_from_source(
    repo: str | Path, source: str | Path, *, source_identity: str | None = None
) -> dict[str, Any] | None:
    """Reconstrói o candidato sem persistência e com identidade histórica opcional."""

    root = _repo_root(repo)
    path = Path(source)
    if not path.is_absolute():
        path = root / path
    path = path.absolute()
    if path.is_symlink() or not path.is_file():
        _fail("LEARNING_PATH_INVALID", "fonte governada inválida")
    path = path.resolve()
    try:
        path.relative_to(root)
    except ValueError:
        _fail("LEARNING_PATH_INVALID", "fonte governada fora do repo")
    return _extract_candidate(root, path, source_identity=source_identity)


@_transition_locked
def propose_learning(repo: str | Path, since: str | None = None) -> dict[str, Any]:
    """Cria somente candidatos pendentes a partir de marcação explícita e evidenciada."""

    root = _repo_root(repo)
    candidates = [
        candidate
        for source in _source_paths(root, since)
        for candidate in [_extract_candidate(root, source)]
        if candidate is not None
    ]
    pending = _fixed_dir(root, ".bianchini/.runtime/learning/pending", create=True)
    created = 0
    results: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda value: value["id"]):
        path = pending / f"{candidate['id']}.json"
        content = _canonical(candidate)
        if path.exists():
            if path.is_symlink() or path.read_bytes() != content:
                _fail("STALE_EVIDENCE", f"candidato divergente: {candidate['id']}")
        else:
            _atomic_write(path, content)
            created += 1
        results.append(
            {
                "id": candidate["id"],
                "digest": candidate["digest"],
                "classification": candidate["classification"],
                "path": path.relative_to(root).as_posix(),
            }
        )
    return {
        "status": "proposed",
        "created": created,
        "candidates": results,
        "since": since,
    }


def _load_candidate(root: Path, candidate: str) -> tuple[Path, dict[str, Any]]:
    if not CANDIDATE_ID.fullmatch(candidate):
        _fail("LEARNING_CANDIDATE_INVALID", "ID de candidato inválido")
    pending = _fixed_dir(root, ".bianchini/.runtime/learning/pending", create=False)
    path = pending / f"{candidate}.json"
    if path.is_symlink() or not path.is_file():
        _fail("LEARNING_CANDIDATE_INVALID", f"candidato ausente: {candidate}")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        _fail("STALE_EVIDENCE", f"candidato corrompido: {error}")
    if not isinstance(value, dict) or _canonical(value) != raw:
        _fail("STALE_EVIDENCE", "candidato não está em forma canônica")
    stored_digest = value.get("digest")
    unsigned = {key: item for key, item in value.items() if key != "digest"}
    if stored_digest != _digest(unsigned):
        _fail("STALE_EVIDENCE", "digest interno do candidato divergiu")
    expected_fields = {
        "id",
        "schema_version",
        "status",
        "classification",
        "statement",
        "tags",
        "validity",
        "conflicts",
        "evidence",
        "source",
        "source_digest",
        "digest",
    }
    if set(value) != expected_fields or value.get("schema_version") != 1:
        _fail("STALE_EVIDENCE", "schema do candidato divergiu")
    if value.get("status") != "pending" or value.get("classification") not in CLASSIFICATIONS:
        _fail("STALE_EVIDENCE", "estado do candidato divergiu")
    base = {key: item for key, item in unsigned.items() if key != "id"}
    expected_id = "L" + _digest(base)[:12].upper()
    if value.get("id") != candidate or expected_id != candidate:
        _fail("STALE_EVIDENCE", "ID não deriva do conteúdo do candidato")
    for field in ("tags", "conflicts", "evidence"):
        _text_list(value.get(field), field, required=field != "conflicts")
    for field in ("statement", "validity", "source"):
        if not isinstance(value.get(field), str) or not value[field].strip():
            _fail("STALE_EVIDENCE", f"{field} inválido no candidato")
    if not isinstance(value.get("source_digest"), str) or not re.fullmatch(
        r"[0-9a-f]{64}", value["source_digest"]
    ):
        _fail("STALE_EVIDENCE", "source_digest inválido no candidato")
    return path, value


def _safe_source(root: Path, value: str) -> Path:
    if "\\" in value:
        _fail("LEARNING_PATH_INVALID", "source contém barra invertida")
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or value != relative.as_posix()
        or any(part in {"", ".", ".."} for part in relative.parts)
        or any(part.casefold() == ".planning" for part in relative.parts)
    ):
        _fail("LEARNING_PATH_INVALID", "source deve ser path relativo confinado")
    candidate = root
    for part in relative.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            _fail("LEARNING_PATH_INVALID", "source não aceita symlink")
    if not candidate.is_file():
        _fail("STALE_EVIDENCE", "fonte do candidato desapareceu")
    return candidate


@_transition_locked
def approve_learning(
    repo: str | Path, candidate: str, digest: str, approved_by: str
) -> dict[str, Any]:
    root = _repo_root(repo)
    if not isinstance(approved_by, str) or not re.fullmatch(r"human:[^\s:][^\s]*", approved_by):
        _fail("HUMAN_APPROVAL_REQUIRED", "approved_by exige identidade human:<id>")
    source_path, value = _load_candidate(root, candidate)
    if value.get("digest") != digest:
        _fail("STALE_EVIDENCE", "digest informado não corresponde ao candidato")
    if value.get("classification") not in APPROVABLE:
        _fail(
            "LEARNING_DESTINATION_REQUIRED",
            "classificação pertence a outro mecanismo de verdade",
        )
    original = _safe_source(root, str(value.get("source")))
    if original not in _source_paths(root, None):
        _fail("LEARNING_PATH_INVALID", "source não pertence ao conjunto governado")
    if hashlib.sha256(original.read_bytes()).hexdigest() != value.get("source_digest"):
        _fail("STALE_EVIDENCE", "fonte do candidato mudou")
    expected = _extract_candidate(root, original)
    if expected is None or _canonical(expected) != _canonical(value):
        _fail("STALE_EVIDENCE", "candidato não deriva da fonte governada atual")
    approved = {
        **{key: item for key, item in value.items() if key != "digest"},
        "status": "approved",
        "active": True,
        "approved_by": approved_by,
        "approved_digest": digest,
        "approved_at": _now(),
    }
    lessons = _fixed_dir(root, ".bianchini/current/lessons", create=True)
    target = lessons / f"{candidate}.json"
    if target.is_symlink():
        _fail("LEARNING_PATH_INVALID", "target de lição não pode ser symlink")
    if target.exists():
        try:
            existing = json.loads(target.read_bytes())
        except (OSError, json.JSONDecodeError) as error:
            _fail("STALE_EVIDENCE", f"lição já existe: {candidate}: {error}")
        if (
            not isinstance(existing, dict)
            or _canonical(existing) != target.read_bytes()
            or not _approved_transition_matches(existing, value, digest, approved_by)
        ):
            _fail("STALE_EVIDENCE", f"lição já existe: {candidate}")
        _durable_unlink(source_path)
        return {
            "id": candidate,
            "status": "approved",
            "path": target.relative_to(root).as_posix(),
            "digest": digest,
        }
    _atomic_write(target, _canonical(approved))
    _durable_unlink(source_path)
    return {
        "id": candidate,
        "status": "approved",
        "path": target.relative_to(root).as_posix(),
        "digest": digest,
    }


@_transition_locked
def deactivate_learning(
    repo: str | Path, candidate: str, reason: str, deactivated_by: str
) -> dict[str, Any]:
    """Desativa uma lição sem apagar sua aprovação nem seu histórico."""

    root = _repo_root(repo)
    if not CANDIDATE_ID.fullmatch(candidate):
        _fail("LEARNING_CANDIDATE_INVALID", "ID de lição inválido")
    if not isinstance(reason, str) or not reason.strip():
        _fail("LEARNING_DEACTIVATION_INVALID", "desativação exige motivo")
    if not isinstance(deactivated_by, str) or not re.fullmatch(
        r"human:[^\s:][^\s]*", deactivated_by
    ):
        _fail("HUMAN_APPROVAL_REQUIRED", "deactivated_by exige identidade human:<id>")
    lessons = _fixed_dir(root, ".bianchini/current/lessons", create=False)
    path = lessons / f"{candidate}.json"
    if path.is_symlink() or not path.is_file():
        _fail("LEARNING_CANDIDATE_INVALID", f"lição ausente: {candidate}")
    raw = path.read_bytes()
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as error:
        _fail("STALE_EVIDENCE", f"lição corrompida: {error}")
    if not isinstance(value, dict) or _canonical(value) != raw:
        _fail("STALE_EVIDENCE", "lição não está em forma canônica")
    if (
        value.get("id") != candidate
        or value.get("status") != "approved"
        or value.get("active", True) is False
        or not isinstance(value.get("approved_by"), str)
        or not isinstance(value.get("approved_digest"), str)
    ):
        _fail("STALE_EVIDENCE", "lição aprovada possui estado inválido")
    deactivated = {
        **value,
        "active": False,
        "deactivated_by": deactivated_by,
        "deactivated_at": _now(),
        "deactivation_reason": reason.strip(),
    }
    _atomic_write(path, _canonical(deactivated))
    return {
        "id": candidate,
        "status": "approved",
        "active": False,
        "path": path.relative_to(root).as_posix(),
    }


@_transition_locked
def reject_learning(repo: str | Path, candidate: str, reason: str) -> dict[str, Any]:
    root = _repo_root(repo)
    if not isinstance(reason, str) or not reason.strip():
        _fail("LEARNING_REJECTION_INVALID", "rejeição exige motivo")
    source, value = _load_candidate(root, candidate)
    clean_reason = reason.strip()
    rejected = {
        **value,
        "status": "rejected",
        "rejection_reason": clean_reason,
        "rejected_at": _now(),
    }
    directory = _fixed_dir(root, ".bianchini/.runtime/learning/rejected", create=True)
    target = directory / f"{candidate}.json"
    if target.is_symlink():
        _fail("LEARNING_PATH_INVALID", "target de rejeição não pode ser symlink")
    if target.exists():
        try:
            existing = json.loads(target.read_bytes())
        except (OSError, json.JSONDecodeError) as error:
            _fail("STALE_EVIDENCE", f"rejeição já existe: {candidate}: {error}")
        if (
            not isinstance(existing, dict)
            or _canonical(existing) != target.read_bytes()
            or not _rejected_transition_matches(existing, value, clean_reason)
        ):
            _fail("STALE_EVIDENCE", f"rejeição já existe: {candidate}")
        _durable_unlink(source)
        return {
            "id": candidate,
            "status": "rejected",
            "path": target.relative_to(root).as_posix(),
        }
    _atomic_write(target, _canonical(rejected))
    _durable_unlink(source)
    return {
        "id": candidate,
        "status": "rejected",
        "path": target.relative_to(root).as_posix(),
    }


def _listed(root: Path, relative: str) -> list[dict[str, Any]]:
    directory = _fixed_dir(root, relative, create=False)
    if not directory.is_dir():
        return []
    result: list[dict[str, Any]] = []
    for path in sorted(directory.glob("L*.json")):
        if path.is_symlink() or not path.is_file():
            _fail("LEARNING_PATH_INVALID", f"entrada insegura: {path.name}")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            _fail("LEARNING_SOURCE_INVALID", f"{path.name}: {error}")
        result.append(
            {
                "id": value.get("id"),
                "status": value.get("status"),
                "classification": value.get("classification"),
                "path": path.relative_to(root).as_posix(),
                "digest": value.get("digest") or value.get("approved_digest"),
            }
        )
    return result


def list_learning(repo: str | Path) -> dict[str, Any]:
    root = _repo_root(repo)
    return {
        "pending": _listed(root, ".bianchini/.runtime/learning/pending"),
        "rejected": _listed(root, ".bianchini/.runtime/learning/rejected"),
        "approved": _listed(root, ".bianchini/current/lessons"),
    }


__all__ = [
    "LearningError",
    "approve_learning",
    "candidate_from_source",
    "deactivate_learning",
    "list_learning",
    "propose_learning",
    "reject_learning",
]
