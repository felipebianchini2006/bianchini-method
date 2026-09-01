#!/usr/bin/env python3
"""Fechamento schema 2 recuperável após crash.

Este módulo coordena apenas a promoção já aprovada. Validação de schema,
coerência, resultados e autorização continua no chamador. O journal descreve
uma máquina de estados crash-recoverable; não promete atomicidade global.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


CLOSE_PHASES = (
    "PREPARED",
    "STAGED",
    "CURRENT_PROMOTED",
    "CHANGE_ARCHIVED",
    "STATE_COMMITTED",
    "DONE",
)
_PREPARING_PHASE = "PREPARING"
_CHANGE_ID = re.compile(r"C[0-9]{3}(?:-[a-z0-9]+(?:-[a-z0-9]+)*)?")
_JOURNAL_NAME = "cycle-close.json"
_LOCK_NAME = "cycle-close.lock"


class CloseRecoveryError(RuntimeError):
    """Falha segura do coordenador, com código estável para o CLI."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


class SimulatedCloseCrash(RuntimeError):
    """Failpoint de teste disparado após uma fase durável."""

    def __init__(self, phase: str):
        super().__init__(f"simulated crash after {phase}")
        self.phase = phase


def _workspace_paths(root: Path) -> tuple[Path, Path, Path]:
    repository = root.resolve()
    bianchini = repository / ".bianchini"
    runtime = bianchini / ".runtime"
    return repository, bianchini, runtime


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
        _sync_directory(path.parent)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _file_digest(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise CloseRecoveryError("RECOVERY_AMBIGUOUS", f"arquivo inválido: {path}")
    return _sha256(path.read_bytes())


def _tree_digest(path: Path) -> str:
    if path.is_symlink() or not path.is_dir():
        raise CloseRecoveryError("RECOVERY_AMBIGUOUS", f"árvore inválida: {path}")
    entries: list[bytes] = []
    for directory, names, files in os.walk(path, topdown=True, followlinks=False):
        names.sort()
        files.sort()
        for name in names:
            candidate = Path(directory) / name
            if name == ".planning":
                raise CloseRecoveryError("PATH_UNSAFE", "namespace .planning é proibido")
            metadata = candidate.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise CloseRecoveryError(
                    "PATH_UNSAFE", f"diretório inválido no fechamento: {candidate}"
                )
            relative = candidate.relative_to(path).as_posix()
            mode = stat.S_IMODE(metadata.st_mode)
            entries.append(f"D\0{relative}\0{mode:o}\n".encode("utf-8"))
        for name in files:
            candidate = Path(directory) / name
            if name == ".planning":
                raise CloseRecoveryError("PATH_UNSAFE", "namespace .planning é proibido")
            metadata = candidate.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                raise CloseRecoveryError(
                    "PATH_UNSAFE", f"arquivo inválido no fechamento: {candidate}"
                )
            relative = candidate.relative_to(path).as_posix()
            mode = stat.S_IMODE(metadata.st_mode)
            entries.append(
                f"F\0{relative}\0{mode:o}\0{_file_digest(candidate)}\n".encode("utf-8")
            )
    return _sha256(b"".join(entries))


def _digest_if_present(path: Path, *, directory: bool) -> str | None:
    if not path.exists() and not path.is_symlink():
        return None
    return _tree_digest(path) if directory else _file_digest(path)


def _relative(root: Path, path: Path) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError as error:
        raise CloseRecoveryError("PATH_UNSAFE", f"caminho fora do repositório: {path}") from error
    if ".planning" in relative.parts:
        raise CloseRecoveryError("PATH_UNSAFE", "namespace .planning é proibido")
    return relative.as_posix()


def _journal_path(root: Path) -> Path:
    _, _, runtime = _workspace_paths(root)
    return runtime / _JOURNAL_NAME


def _reject_symlink_chain(repository: Path, relative: Path, label: str) -> None:
    current = repository
    for part in relative.parts:
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            break
        except OSError as error:
            raise CloseRecoveryError(
                "PATH_UNSAFE", f"não foi possível inspecionar {label}: {current}"
            ) from error
        if stat.S_ISLNK(metadata.st_mode):
            raise CloseRecoveryError(
                "PATH_UNSAFE", f"{label} atravessa symlink: {current}"
            )


def _write_journal(path: Path, journal: dict[str, Any]) -> None:
    _atomic_write(
        path,
        (json.dumps(journal, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
            "utf-8"
        ),
    )


def _read_journal(root: Path) -> dict[str, Any] | None:
    path = _journal_path(root)
    if not path.exists():
        return None
    if path.is_symlink() or not path.is_file():
        raise CloseRecoveryError("JOURNAL_CORRUPT", "journal não é arquivo regular")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CloseRecoveryError("JOURNAL_CORRUPT", "journal truncado ou inválido") from error
    if not isinstance(value, dict):
        raise CloseRecoveryError("JOURNAL_CORRUPT", "journal exige objeto JSON")
    if value.get("schema_version") != 1 or value.get("spec_contract") != 1:
        raise CloseRecoveryError("JOURNAL_CORRUPT", "versão do journal inválida")
    if value.get("phase") not in {_PREPARING_PHASE, *CLOSE_PHASES}:
        raise CloseRecoveryError("JOURNAL_CORRUPT", "fase do journal inválida")
    change = value.get("change")
    if not isinstance(change, str) or _CHANGE_ID.fullmatch(change) is None:
        raise CloseRecoveryError("JOURNAL_CORRUPT", "change do journal inválido")
    paths = value.get("paths")
    if not isinstance(paths, dict):
        raise CloseRecoveryError("JOURNAL_CORRUPT", "paths do journal ausentes")
    required_paths = {"current", "change", "archive", "state", "transaction"}
    if set(paths) != required_paths or not all(isinstance(item, str) for item in paths.values()):
        raise CloseRecoveryError("JOURNAL_CORRUPT", "paths do journal inválidos")
    repository = root.resolve()
    expected_paths = {
        "current": ".bianchini/current",
        "change": f".bianchini/changes/{change}",
        "archive": f".bianchini/archive/{change}",
        "state": ".bianchini/STATE.md",
        "transaction": f".bianchini/.runtime/cycle-close-{change}",
    }
    if paths != expected_paths:
        raise CloseRecoveryError("JOURNAL_CORRUPT", "paths não correspondem ao change")
    for item in paths.values():
        relative = Path(item)
        if relative.is_absolute() or ".." in relative.parts or ".planning" in relative.parts:
            raise CloseRecoveryError("JOURNAL_CORRUPT", "path inseguro no journal")
        _reject_symlink_chain(repository, relative, "path do journal")
        resolved = (repository / relative).resolve()
        try:
            resolved.relative_to(repository)
        except ValueError as error:
            raise CloseRecoveryError("JOURNAL_CORRUPT", "path fora do repositório") from error
    digests = value.get("digests")
    if not isinstance(digests, dict) or set(digests) != {"before", "after"}:
        raise CloseRecoveryError("JOURNAL_CORRUPT", "digests do journal inválidos")
    for moment in ("before", "after"):
        item = digests[moment]
        expected_keys = {"current", "change", "state"}
        if (
            moment == "after"
            and value["phase"] in {_PREPARING_PHASE, "PREPARED"}
            and item == {}
        ):
            continue
        if not isinstance(item, dict) or set(item) != expected_keys:
            raise CloseRecoveryError("JOURNAL_CORRUPT", f"digests {moment} inválidos")
        if not all(
            isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)
            for digest in item.values()
        ):
            raise CloseRecoveryError("JOURNAL_CORRUPT", f"digest {moment} malformado")
    inputs = value.get("inputs")
    expected_inputs = {"architecture", "system_model", "specs", "summary", "state"}
    if value["phase"] == _PREPARING_PHASE:
        if inputs != {} or digests["after"] != {}:
            raise CloseRecoveryError(
                "JOURNAL_CORRUPT", "journal PREPARING contém digests prematuros"
            )
        return value
    if not isinstance(inputs, dict) or set(inputs) != expected_inputs:
        raise CloseRecoveryError("JOURNAL_CORRUPT", "digests de input inválidos")
    if not all(
        isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)
        for digest in inputs.values()
    ):
        raise CloseRecoveryError("JOURNAL_CORRUPT", "digest de input malformado")
    return value


def pending_close(repo: Path) -> dict[str, Any] | None:
    """Retorna uma cópia do journal pendente sem alterar o workspace."""

    value = _read_journal(repo.resolve())
    return json.loads(json.dumps(value)) if value is not None else None


@contextmanager
def _exclusive_lock(root: Path) -> Iterator[None]:
    _, bianchini, runtime = _workspace_paths(root)
    if bianchini.is_symlink() or not bianchini.is_dir():
        raise CloseRecoveryError("PATH_UNSAFE", "workspace .bianchini ausente ou inválido")
    if runtime.is_symlink():
        raise CloseRecoveryError("PATH_UNSAFE", "runtime não pode ser symlink")
    runtime.mkdir(parents=True, exist_ok=True)
    lock = runtime / _LOCK_NAME
    if lock.is_symlink():
        raise CloseRecoveryError("PATH_UNSAFE", "lock não pode ser symlink")
    descriptor = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise CloseRecoveryError(
                "CLOSE_LOCKED", "outro fechamento está em execução"
            ) from error
        yield
    finally:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _paths(root: Path, journal: dict[str, Any]) -> dict[str, Path]:
    repository = root.resolve()
    result: dict[str, Path] = {}
    for key, value in journal["paths"].items():
        relative = Path(value)
        _reject_symlink_chain(repository, relative, key)
        result[key] = repository / relative
    return result


def _remove_known(path: Path, *, expected_digest: str | None = None) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_symlink():
        raise CloseRecoveryError("PATH_UNSAFE", f"remoção recusada para symlink: {path}")
    if path.is_dir():
        for _, names, files in os.walk(path, topdown=True, followlinks=False):
            if ".planning" in names or ".planning" in files:
                raise CloseRecoveryError("PATH_UNSAFE", "namespace .planning é proibido")
    if expected_digest is not None:
        actual = _tree_digest(path) if path.is_dir() else _file_digest(path)
        if actual != expected_digest:
            raise CloseRecoveryError(
                "RECOVERY_AMBIGUOUS", f"digest inesperado antes de remover {path}"
            )
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    _sync_directory(path.parent)


def _rename(source: Path, target: Path) -> None:
    os.replace(source, target)
    _sync_directory(target.parent)


def _fail_if_requested(failpoint: str | None, phase: str) -> None:
    if failpoint == phase:
        raise SimulatedCloseCrash(phase)


def _assert_digest(actual: str | None, expected: str, label: str) -> None:
    if actual != expected:
        raise CloseRecoveryError(
            "RECOVERY_AMBIGUOUS",
            f"{label} divergiu do digest conhecido",
        )


def _stage(root: Path, journal: dict[str, Any]) -> None:
    paths = _paths(root, journal)
    transaction = paths["transaction"]
    inputs = transaction / "inputs"
    staged_current = transaction / "staged-current"
    staged_archive = transaction / "staged-archive"
    before = journal["digests"]["before"]
    expected_inputs = journal["inputs"]
    actual_inputs = {
        "architecture": _file_digest(inputs / "ARCHITECTURE.md"),
        "system_model": _file_digest(inputs / "SYSTEM_MODEL.md"),
        "specs": _tree_digest(inputs / "specs"),
        "summary": _file_digest(inputs / "SUMMARY.md"),
        "state": _file_digest(inputs / "STATE.md"),
    }
    if actual_inputs != expected_inputs:
        raise CloseRecoveryError("RECOVERY_AMBIGUOUS", "inputs do fechamento divergiram")
    _assert_digest(_file_digest(inputs / "STATE.before.md"), before["state"], "STATE.md anterior")
    _assert_digest(_digest_if_present(paths["current"], directory=True), before["current"], "current")
    _assert_digest(_digest_if_present(paths["change"], directory=True), before["change"], "change")
    _assert_digest(_digest_if_present(paths["state"], directory=False), before["state"], "STATE.md")
    _remove_known(staged_current)
    _remove_known(staged_archive)
    shutil.copytree(paths["current"], staged_current)
    _atomic_write(staged_current / "ARCHITECTURE.md", (inputs / "ARCHITECTURE.md").read_bytes())
    _atomic_write(staged_current / "SYSTEM_MODEL.md", (inputs / "SYSTEM_MODEL.md").read_bytes())
    staged_specs = staged_current / "specs"
    _remove_known(staged_specs)
    shutil.copytree(inputs / "specs", staged_specs)
    shutil.copytree(paths["change"], staged_archive)
    _atomic_write(staged_archive / "SUMMARY.md", (inputs / "SUMMARY.md").read_bytes())
    journal["digests"]["after"] = {
        "current": _tree_digest(staged_current),
        "change": _tree_digest(staged_archive),
        "state": _file_digest(inputs / "STATE.md"),
    }
    journal["phase"] = "STAGED"
    _write_journal(_journal_path(root), journal)


def _promote_current(root: Path, journal: dict[str, Any]) -> None:
    paths = _paths(root, journal)
    transaction = paths["transaction"]
    stage = transaction / "staged-current"
    backup = transaction / "previous-current"
    before = journal["digests"]["before"]["current"]
    after = journal["digests"]["after"]["current"]
    current_digest = _digest_if_present(paths["current"], directory=True)
    stage_digest = _digest_if_present(stage, directory=True)
    backup_digest = _digest_if_present(backup, directory=True)
    if current_digest == before and stage_digest == after and backup_digest is None:
        _rename(paths["current"], backup)
        current_digest = None
        backup_digest = before
    if current_digest is None and stage_digest == after and backup_digest == before:
        _rename(stage, paths["current"])
        current_digest = after
        stage_digest = None
    if not (
        current_digest == after and stage_digest is None and backup_digest == before
    ):
        raise CloseRecoveryError(
            "RECOVERY_AMBIGUOUS", "promoção de current está em estado desconhecido"
        )
    journal["phase"] = "CURRENT_PROMOTED"
    _write_journal(_journal_path(root), journal)


def _archive_change(root: Path, journal: dict[str, Any]) -> None:
    paths = _paths(root, journal)
    transaction = paths["transaction"]
    stage = transaction / "staged-archive"
    backup = transaction / "previous-change"
    before = journal["digests"]["before"]["change"]
    after = journal["digests"]["after"]["change"]
    change_digest = _digest_if_present(paths["change"], directory=True)
    archive_digest = _digest_if_present(paths["archive"], directory=True)
    stage_digest = _digest_if_present(stage, directory=True)
    backup_digest = _digest_if_present(backup, directory=True)
    if (
        change_digest == before
        and archive_digest is None
        and stage_digest == after
        and backup_digest is None
    ):
        _rename(paths["change"], backup)
        change_digest = None
        backup_digest = before
    if (
        change_digest is None
        and archive_digest is None
        and stage_digest == after
        and backup_digest == before
    ):
        paths["archive"].parent.mkdir(parents=True, exist_ok=True)
        _rename(stage, paths["archive"])
        archive_digest = after
        stage_digest = None
    if not (
        change_digest is None
        and archive_digest == after
        and stage_digest is None
        and backup_digest == before
    ):
        raise CloseRecoveryError(
            "RECOVERY_AMBIGUOUS", "arquivamento da mudança está em estado desconhecido"
        )
    journal["phase"] = "CHANGE_ARCHIVED"
    _write_journal(_journal_path(root), journal)


def _commit_state(root: Path, journal: dict[str, Any]) -> None:
    paths = _paths(root, journal)
    before = journal["digests"]["before"]["state"]
    after = journal["digests"]["after"]["state"]
    current = _digest_if_present(paths["state"], directory=False)
    if current == before:
        _atomic_write(paths["state"], (paths["transaction"] / "inputs/STATE.md").read_bytes())
        current = _file_digest(paths["state"])
    _assert_digest(current, after, "STATE.md promovido")
    journal["phase"] = "STATE_COMMITTED"
    _write_journal(_journal_path(root), journal)


def _verify_done(root: Path, journal: dict[str, Any]) -> None:
    paths = _paths(root, journal)
    after = journal["digests"]["after"]
    _assert_digest(_digest_if_present(paths["current"], directory=True), after["current"], "current final")
    _assert_digest(_digest_if_present(paths["archive"], directory=True), after["change"], "archive final")
    _assert_digest(_digest_if_present(paths["state"], directory=False), after["state"], "STATE.md final")
    if paths["change"].exists() or paths["change"].is_symlink():
        raise CloseRecoveryError("RECOVERY_AMBIGUOUS", "change ainda existe após arquivamento")


def _cleanup_done(root: Path, journal: dict[str, Any]) -> None:
    paths = _paths(root, journal)
    _verify_done(root, journal)
    transaction = paths["transaction"]
    if transaction.exists() or transaction.is_symlink():
        _remove_known(transaction)
    journal_path = _journal_path(root)
    if journal_path.exists():
        journal_path.unlink()
        _sync_directory(journal_path.parent)


def _advance(root: Path, journal: dict[str, Any], failpoint: str | None) -> dict[str, Any]:
    while True:
        phase = journal["phase"]
        if phase == "PREPARED":
            _stage(root, journal)
            _fail_if_requested(failpoint, "STAGED")
        elif phase == "STAGED":
            _promote_current(root, journal)
            _fail_if_requested(failpoint, "CURRENT_PROMOTED")
        elif phase == "CURRENT_PROMOTED":
            _archive_change(root, journal)
            _fail_if_requested(failpoint, "CHANGE_ARCHIVED")
        elif phase == "CHANGE_ARCHIVED":
            _commit_state(root, journal)
            _fail_if_requested(failpoint, "STATE_COMMITTED")
        elif phase == "STATE_COMMITTED":
            _verify_done(root, journal)
            journal["phase"] = "DONE"
            _write_journal(_journal_path(root), journal)
            _fail_if_requested(failpoint, "DONE")
        elif phase == "DONE":
            result = {
                "change": journal["change"],
                "status": "completed",
                "archive": str(_paths(root, journal)["archive"]),
                "current_digest": journal["digests"]["after"]["current"],
                "archive_digest": journal["digests"]["after"]["change"],
                "state_digest": journal["digests"]["after"]["state"],
            }
            _cleanup_done(root, journal)
            return result


def _prepare(
    root: Path,
    change: str,
    *,
    specs_source: Path,
    specs_manifest: Path | None,
    summary: bytes,
    next_state: bytes,
) -> dict[str, Any]:
    repository, bianchini, runtime = _workspace_paths(root)
    if _CHANGE_ID.fullmatch(change) is None:
        raise CloseRecoveryError("PATH_UNSAFE", f"change inválido: {change}")
    current = bianchini / "current"
    change_dir = bianchini / "changes" / change
    archive = bianchini / "archive" / change
    state = bianchini / "STATE.md"
    transaction = runtime / f"cycle-close-{change}"
    if not current.is_dir() or current.is_symlink():
        raise CloseRecoveryError("CLOSE_INCOMPLETE", "current ausente ou inválido")
    if not change_dir.is_dir() or change_dir.is_symlink():
        raise CloseRecoveryError("CLOSE_INCOMPLETE", "change ausente ou inválido")
    if archive.exists() or archive.is_symlink():
        raise CloseRecoveryError("CLOSE_CONFLICT", f"archive já existe: {archive}")
    if not state.is_file() or state.is_symlink():
        raise CloseRecoveryError("CLOSE_INCOMPLETE", "STATE.md ausente ou inválido")
    architecture = change_dir / "ARCHITECTURE.md"
    system_model = change_dir / "SYSTEM_MODEL.md"
    for label, source in (("ARCHITECTURE.md", architecture), ("SYSTEM_MODEL.md", system_model)):
        if not source.is_file() or source.is_symlink():
            raise CloseRecoveryError("CLOSE_INCOMPLETE", f"{label} final ausente")
    raw_source = specs_source if specs_source.is_absolute() else repository / specs_source
    if ".." in raw_source.parts or ".planning" in raw_source.parts:
        raise CloseRecoveryError("PATH_UNSAFE", "specs source inseguro")
    try:
        lexical_relative = raw_source.absolute().relative_to(change_dir.absolute())
    except ValueError as error:
        raise CloseRecoveryError("PATH_UNSAFE", "specs source fora do change") from error
    inspected = change_dir
    for part in lexical_relative.parts:
        inspected = inspected / part
        if inspected.is_symlink():
            raise CloseRecoveryError("PATH_UNSAFE", f"symlink proibido: {inspected}")
    source = raw_source.resolve()
    try:
        source.relative_to(change_dir.resolve())
    except ValueError as error:
        raise CloseRecoveryError("PATH_UNSAFE", "specs source fora do change") from error
    _tree_digest(source)
    manifest_source: Path | None = None
    if specs_manifest is not None:
        raw_manifest = (
            specs_manifest if specs_manifest.is_absolute() else repository / specs_manifest
        )
        if ".." in raw_manifest.parts or ".planning" in raw_manifest.parts:
            raise CloseRecoveryError("PATH_UNSAFE", "specs manifest inseguro")
        try:
            manifest_relative = raw_manifest.absolute().relative_to(
                change_dir.absolute()
            )
        except ValueError as error:
            raise CloseRecoveryError(
                "PATH_UNSAFE", "specs manifest fora do change"
            ) from error
        inspected = change_dir
        for part in manifest_relative.parts:
            inspected = inspected / part
            if inspected.is_symlink():
                raise CloseRecoveryError(
                    "PATH_UNSAFE", f"symlink proibido: {inspected}"
                )
        manifest_source = raw_manifest.resolve()
        try:
            manifest_source.relative_to(change_dir.resolve())
        except ValueError as error:
            raise CloseRecoveryError(
                "PATH_UNSAFE", "specs manifest fora do change"
            ) from error
        if manifest_source.is_symlink() or not manifest_source.is_file():
            raise CloseRecoveryError("PATH_UNSAFE", "specs manifest inválido")
    if not summary or not next_state:
        raise CloseRecoveryError("CLOSE_INCOMPLETE", "summary e next_state são obrigatórios")
    if transaction.exists() or transaction.is_symlink():
        raise CloseRecoveryError("RECOVERY_AMBIGUOUS", "staging órfão sem journal")
    runtime.mkdir(parents=True, exist_ok=True)
    journal = {
        "schema_version": 1,
        "spec_contract": 1,
        "change": change,
        "phase": _PREPARING_PHASE,
        "paths": {
            "current": _relative(repository, current),
            "change": _relative(repository, change_dir),
            "archive": _relative(repository, archive),
            "state": _relative(repository, state),
            "transaction": _relative(repository, transaction),
        },
        "digests": {
            "before": {
                "current": _tree_digest(current),
                "change": _tree_digest(change_dir),
                "state": _file_digest(state),
            },
            "after": {},
        },
        "inputs": {},
    }
    _write_journal(_journal_path(root), journal)
    inputs = transaction / "inputs"
    inputs.mkdir(parents=True)
    _atomic_write(inputs / "ARCHITECTURE.md", architecture.read_bytes())
    _atomic_write(inputs / "SYSTEM_MODEL.md", system_model.read_bytes())
    _atomic_write(inputs / "SUMMARY.md", summary)
    _atomic_write(inputs / "STATE.md", next_state)
    _atomic_write(inputs / "STATE.before.md", state.read_bytes())
    shutil.copytree(source, inputs / "specs")
    if manifest_source is not None:
        _atomic_write(inputs / "specs" / "MANIFEST.json", manifest_source.read_bytes())
    journal["inputs"] = {
        "architecture": _file_digest(inputs / "ARCHITECTURE.md"),
        "system_model": _file_digest(inputs / "SYSTEM_MODEL.md"),
        "specs": _tree_digest(inputs / "specs"),
        "summary": _file_digest(inputs / "SUMMARY.md"),
        "state": _file_digest(inputs / "STATE.md"),
    }
    journal["phase"] = "PREPARED"
    _write_journal(_journal_path(root), journal)
    return journal


def _discard_preparing(root: Path, journal: dict[str, Any]) -> dict[str, Any]:
    """Volta um intent incompleto ao estado anterior sem tocar dados visíveis."""

    if journal["phase"] != _PREPARING_PHASE:
        raise CloseRecoveryError("RECOVERY_AMBIGUOUS", "journal não está preparando")
    paths = _paths(root, journal)
    before = journal["digests"]["before"]
    _assert_digest(
        _digest_if_present(paths["current"], directory=True),
        before["current"],
        "current durante preparação",
    )
    _assert_digest(
        _digest_if_present(paths["change"], directory=True),
        before["change"],
        "change durante preparação",
    )
    _assert_digest(
        _digest_if_present(paths["state"], directory=False),
        before["state"],
        "STATE.md durante preparação",
    )
    if paths["archive"].exists() or paths["archive"].is_symlink():
        raise CloseRecoveryError(
            "RECOVERY_AMBIGUOUS", "archive apareceu durante preparação"
        )
    transaction = paths["transaction"]
    if transaction.exists() or transaction.is_symlink():
        transaction_digest = _tree_digest(transaction)
        _remove_known(transaction, expected_digest=transaction_digest)
    journal_path = _journal_path(root)
    journal_path.unlink()
    _sync_directory(journal_path.parent)
    return {"change": journal["change"], "status": "restored"}


def _restore_tree(current: Path, backup: Path, before: str, after: str) -> None:
    current_digest = _digest_if_present(current, directory=True)
    backup_digest = _digest_if_present(backup, directory=True)
    if current_digest == before and backup_digest is None:
        return
    if current_digest == after and backup_digest == before:
        _remove_known(current, expected_digest=after)
        _rename(backup, current)
        return
    if current_digest is None and backup_digest == before:
        _rename(backup, current)
        return
    raise CloseRecoveryError("RECOVERY_AMBIGUOUS", f"não foi possível restaurar {current}")


def _restore(root: Path, journal: dict[str, Any]) -> dict[str, Any]:
    if journal["phase"] == "DONE":
        raise CloseRecoveryError("RECOVERY_AMBIGUOUS", "fechamento DONE não pode ser restaurado")
    paths = _paths(root, journal)
    transaction = paths["transaction"]
    before = journal["digests"]["before"]
    after = journal["digests"].get("after", {})
    if journal["phase"] in {"CURRENT_PROMOTED", "CHANGE_ARCHIVED", "STATE_COMMITTED"}:
        _restore_tree(
            paths["current"],
            transaction / "previous-current",
            before["current"],
            after["current"],
        )
    else:
        _assert_digest(_digest_if_present(paths["current"], directory=True), before["current"], "current")
    if journal["phase"] in {"CHANGE_ARCHIVED", "STATE_COMMITTED"}:
        archive_digest = _digest_if_present(paths["archive"], directory=True)
        change_backup = transaction / "previous-change"
        backup_digest = _digest_if_present(change_backup, directory=True)
        if archive_digest == after["change"] and backup_digest == before["change"]:
            _remove_known(paths["archive"], expected_digest=after["change"])
            _rename(change_backup, paths["change"])
        elif _digest_if_present(paths["change"], directory=True) != before["change"]:
            raise CloseRecoveryError("RECOVERY_AMBIGUOUS", "não foi possível restaurar change")
    else:
        _assert_digest(_digest_if_present(paths["change"], directory=True), before["change"], "change")
    state_digest = _digest_if_present(paths["state"], directory=False)
    if state_digest != before["state"]:
        if after and state_digest == after.get("state"):
            _atomic_write(paths["state"], (transaction / "inputs/STATE.before.md").read_bytes())
        else:
            raise CloseRecoveryError("RECOVERY_AMBIGUOUS", "não foi possível restaurar STATE.md")
    _assert_digest(_digest_if_present(paths["current"], directory=True), before["current"], "current restaurado")
    _assert_digest(_digest_if_present(paths["change"], directory=True), before["change"], "change restaurado")
    _assert_digest(_digest_if_present(paths["state"], directory=False), before["state"], "STATE.md restaurado")
    if paths["archive"].exists() or paths["archive"].is_symlink():
        raise CloseRecoveryError("RECOVERY_AMBIGUOUS", "archive permaneceu após restore")
    _remove_known(transaction)
    journal_path = _journal_path(root)
    journal_path.unlink()
    _sync_directory(journal_path.parent)
    return {"change": journal["change"], "status": "restored"}


def recover_pending_close(
    repo: Path,
    *,
    strategy: str = "continue",
    failpoint: str | None = None,
) -> dict[str, Any] | None:
    """Continua ou restaura um journal incompleto usando somente digests conhecidos."""

    if strategy not in {"continue", "restore"}:
        raise ValueError("strategy deve ser continue ou restore")
    root = repo.resolve()
    with _exclusive_lock(root):
        journal = _read_journal(root)
        if journal is None:
            return None
        if journal["phase"] == _PREPARING_PHASE:
            return _discard_preparing(root, journal)
        if strategy == "restore":
            return _restore(root, journal)
        result = _advance(root, journal, failpoint)
        result["recovered"] = True
        return result


def crash_recoverable_close(
    repo: Path,
    change: str,
    *,
    specs_source: Path,
    specs_manifest: Path | None = None,
    summary: bytes | str,
    next_state: bytes | str,
    failpoint: str | None = None,
) -> dict[str, Any]:
    """Executa ou recupera o fechamento schema 2 sob lock exclusivo."""

    if failpoint is not None and failpoint not in CLOSE_PHASES:
        raise ValueError(f"failpoint inválido: {failpoint}")
    root = repo.resolve()
    summary_bytes = summary.encode("utf-8") if isinstance(summary, str) else bytes(summary)
    state_bytes = next_state.encode("utf-8") if isinstance(next_state, str) else bytes(next_state)
    with _exclusive_lock(root):
        journal = _read_journal(root)
        recovered = journal is not None
        if journal is not None:
            if journal["change"] != change:
                raise CloseRecoveryError(
                    "CLOSE_CONFLICT",
                    f"journal pendente pertence a {journal['change']}",
                )
            if journal["phase"] == _PREPARING_PHASE:
                _discard_preparing(root, journal)
                journal = None
        if journal is None:
            journal = _prepare(
                root,
                change,
                specs_source=specs_source,
                specs_manifest=specs_manifest,
                summary=summary_bytes,
                next_state=state_bytes,
            )
            _fail_if_requested(failpoint, "PREPARED")
        result = _advance(root, journal, failpoint)
        result["recovered"] = recovered
        return result


__all__ = [
    "CLOSE_PHASES",
    "CloseRecoveryError",
    "SimulatedCloseCrash",
    "crash_recoverable_close",
    "pending_close",
    "recover_pending_close",
]
