#!/usr/bin/env python3
"""Propostas de aprendizado governadas, determinísticas e opt-in."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
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
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _source_paths(root: Path, since: str | None) -> list[Path]:
    patterns = (
        ".bianchini/debug/resolved/*.md",
        ".bianchini/debug/KNOWLEDGE.md",
        ".bianchini/changes/*/results/**/*.md",
        ".bianchini/archive/*/results/**/*.md",
        ".bianchini/changes/*/COHERENCE.md",
        ".bianchini/archive/*/COHERENCE.md",
    )
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
    result: set[Path] = set()
    for pattern in patterns:
        for path in root.glob(pattern):
            relative = path.relative_to(root).as_posix()
            if ".planning" in Path(relative).parts:
                continue
            if path.is_symlink():
                _fail("LEARNING_PATH_INVALID", f"fonte symlink: {relative}")
            if path.is_file() and (
                allowed_by_since is None or relative in allowed_by_since
            ):
                result.add(path)
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


def _extract_candidate(root: Path, source: Path) -> dict[str, Any] | None:
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
    evidence = _text_list(payload.get("evidence"), "evidence", required=True)
    statement = raw.get("statement")
    validity = raw.get("validity")
    if not isinstance(statement, str) or not statement.strip():
        _fail("LEARNING_CANDIDATE_INVALID", "statement obrigatório")
    if not isinstance(validity, str) or not validity.strip():
        _fail("LEARNING_CANDIDATE_INVALID", "validity obrigatória")
    tags = _text_list(raw.get("tags"), "tags", required=True)
    conflicts = _text_list(raw.get("conflicts"), "conflicts")
    relative = source.relative_to(root).as_posix()
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
    return path, value


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
    original = root / str(value.get("source"))
    if original.is_symlink() or not original.is_file():
        _fail("STALE_EVIDENCE", "fonte do candidato desapareceu")
    if hashlib.sha256(original.read_bytes()).hexdigest() != value.get("source_digest"):
        _fail("STALE_EVIDENCE", "fonte do candidato mudou")
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
    if target.exists():
        _fail("STALE_EVIDENCE", f"lição já existe: {candidate}")
    _atomic_write(target, _canonical(approved))
    source_path.unlink()
    return {
        "id": candidate,
        "status": "approved",
        "path": target.relative_to(root).as_posix(),
        "digest": digest,
    }


def reject_learning(repo: str | Path, candidate: str, reason: str) -> dict[str, Any]:
    root = _repo_root(repo)
    if not isinstance(reason, str) or not reason.strip():
        _fail("LEARNING_REJECTION_INVALID", "rejeição exige motivo")
    source, value = _load_candidate(root, candidate)
    rejected = {
        **value,
        "status": "rejected",
        "rejection_reason": reason.strip(),
        "rejected_at": _now(),
    }
    directory = _fixed_dir(root, ".bianchini/.runtime/learning/rejected", create=True)
    target = directory / f"{candidate}.json"
    if target.exists():
        _fail("STALE_EVIDENCE", f"rejeição já existe: {candidate}")
    _atomic_write(target, _canonical(rejected))
    source.unlink()
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
    "list_learning",
    "propose_learning",
    "reject_learning",
]
