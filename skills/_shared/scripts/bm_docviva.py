#!/usr/bin/env python3
"""Snapshot e verificação determinística da DocViva seletiva.

DocViva é somente a verdade atual compilada em ``.bianchini/current``.
Resultados de change, quick, debug e archive são histórico e, portanto, nunca
entram no snapshot nem satisfazem uma atualização exigida.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Union


CURRENT_PREFIX = PurePosixPath(".bianchini/current")
DOCVIVA_KINDS = frozenset(
    {"internal", "behavioral", "contract", "architecture", "rule"}
)
DOCVIVA_OUTCOMES = frozenset({"updated", "not_applicable", "no_op"})
REQUIRED_KINDS = frozenset({"behavioral", "contract", "architecture", "rule"})


class DocVivaError(ValueError):
    """Falha fechada com código estável para os coordenadores de workflow."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def _fail(code: str, message: str) -> None:
    raise DocVivaError(code, message)


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _repo_root(repo: Union[str, Path]) -> Path:
    raw = Path(repo)
    if any(part.casefold() == ".planning" for part in raw.parts):
        _fail("DOCVIVA_PATH_INVALID", "repositório usa namespace estrangeiro")
    absolute = raw.absolute()
    if absolute.is_symlink():
        _fail("DOCVIVA_SYMLINK", "raiz do repositório não pode ser symlink")
    return absolute.resolve()


def _normalized_relative(value: Union[str, Path], *, label: str) -> PurePosixPath:
    text = str(value)
    if not text or "\\" in text:
        _fail("DOCVIVA_PATH_INVALID", f"{label} vazio ou não POSIX")
    raw = PurePosixPath(text)
    if raw.is_absolute():
        _fail("DOCVIVA_PATH_INVALID", f"{label} deve ser relativo")
    if text != raw.as_posix() or any(part in {"", ".", ".."} for part in raw.parts):
        _fail("DOCVIVA_PATH_INVALID", f"{label} não está normalizado")
    if any(part.casefold() == ".planning" for part in raw.parts):
        _fail("DOCVIVA_PATH_INVALID", f"{label} usa namespace estrangeiro")
    if raw == CURRENT_PREFIX or not raw.is_relative_to(CURRENT_PREFIX):
        _fail("DOCVIVA_PATH_INVALID", f"{label} não pertence a .bianchini/current")
    return raw


def _reject_symlink_chain(root: Path, relative: PurePosixPath, *, label: str) -> Path:
    candidate = root
    for part in relative.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            _fail("DOCVIVA_SYMLINK", f"{label} atravessa symlink: {relative.as_posix()}")
    return candidate


def _current_root(repo: Union[str, Path]) -> tuple[Path, Path]:
    root = _repo_root(repo)
    current = _reject_symlink_chain(root, CURRENT_PREFIX, label="DocViva")
    if not current.is_dir():
        _fail("DOCVIVA_CURRENT_MISSING", ".bianchini/current ausente")
    return root, current


def _validate_text(content: bytes, *, label: str) -> None:
    if b"\x00" in content:
        _fail("DOCVIVA_CONTENT_INVALID", f"{label} contém byte NUL")
    try:
        content.decode("utf-8")
    except UnicodeDecodeError as error:
        _fail("DOCVIVA_CONTENT_INVALID", f"{label} não é UTF-8")
        raise AssertionError from error


def snapshot_docviva(repo: Union[str, Path]) -> dict[str, str]:
    """Produz digests SHA-256 dos arquivos regulares de ``current/**``.

    A travessia não segue symlinks e falha antes de devolver um snapshot parcial.
    As chaves são paths POSIX canônicos relativos ao repositório.
    """

    root, current = _current_root(repo)
    entries: list[tuple[str, bytes]] = []

    def visit(directory: Path) -> None:
        with os.scandir(directory) as iterator:
            children = sorted(iterator, key=lambda entry: entry.name)
        for entry in children:
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            if entry.is_symlink():
                _fail("DOCVIVA_SYMLINK", f"symlink não permitido: {relative}")
            if entry.is_dir(follow_symlinks=False):
                visit(path)
                continue
            if not entry.is_file(follow_symlinks=False):
                _fail("DOCVIVA_PATH_INVALID", f"entrada não regular: {relative}")
            content = path.read_bytes()
            _validate_text(content, label=relative)
            entries.append((relative, content))

    visit(current)
    return {path: _sha256(content) for path, content in sorted(entries)}


def _sync_directory(directory: Path) -> None:
    try:
        descriptor = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_if_changed(
    repo: Union[str, Path],
    path: Union[str, Path],
    content: Union[str, bytes],
) -> bool:
    """Escreve um artefato ``current/**`` apenas quando os bytes mudarem.

    Retorna ``True`` quando houve escrita. Conteúdo idêntico preserva bytes,
    permissões e mtime porque o arquivo sequer é aberto para escrita.
    """

    root, _current = _current_root(repo)
    relative = _normalized_relative(path, label="artefato DocViva")
    target = _reject_symlink_chain(root, relative, label="artefato DocViva")
    if target.exists() and not target.is_file():
        _fail("DOCVIVA_PATH_INVALID", f"artefato não é arquivo: {relative.as_posix()}")
    data = content.encode("utf-8") if isinstance(content, str) else bytes(content)
    _validate_text(data, label=relative.as_posix())
    if target.is_file() and target.read_bytes() == data:
        return False

    parent_relative = PurePosixPath(*relative.parts[:-1])
    parent = root
    for part in parent_relative.parts:
        parent = parent / part
        if parent.is_symlink():
            _fail("DOCVIVA_SYMLINK", f"diretório atravessa symlink: {relative.as_posix()}")
        if parent.exists() and not parent.is_dir():
            _fail("DOCVIVA_PATH_INVALID", f"ancestral não é diretório: {part}")
        parent.mkdir(exist_ok=True)

    descriptor, temporary_name = tempfile.mkstemp(
        dir=target.parent,
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if target.is_file():
            os.chmod(temporary, target.stat().st_mode & 0o777)
        os.replace(temporary, target)
        _sync_directory(target.parent)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    return True


def _validate_snapshot(value: Mapping[str, str], *, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        _fail("DOCVIVA_SNAPSHOT_INVALID", f"{label} deve ser objeto")
    normalized: dict[str, str] = {}
    for raw_path, digest in value.items():
        if not isinstance(raw_path, str):
            _fail("DOCVIVA_SNAPSHOT_INVALID", f"{label} contém path não textual")
        path = _normalized_relative(raw_path, label=f"{label}.path").as_posix()
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            _fail("DOCVIVA_SNAPSHOT_INVALID", f"digest inválido para {path}")
        normalized[path] = digest
    return normalized


def _snapshot_digest(value: Mapping[str, str]) -> str:
    serialized = json.dumps(
        dict(sorted(value.items())),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return _sha256(serialized)


def _classification(value: Mapping[str, Any]) -> tuple[str, str]:
    if not isinstance(value, Mapping) or set(value) != {"kind", "outcome"}:
        _fail(
            "DOCVIVA_CLASSIFICATION_INVALID",
            "classification exige somente kind e outcome",
        )
    kind = value.get("kind")
    outcome = value.get("outcome")
    if kind not in DOCVIVA_KINDS or outcome not in DOCVIVA_OUTCOMES:
        _fail("DOCVIVA_CLASSIFICATION_INVALID", "kind ou outcome não suportado")
    return str(kind), str(outcome)


def _declared_artifacts(values: Iterable[str]) -> list[str]:
    if isinstance(values, (str, bytes, Mapping)):
        _fail("DOCVIVA_DECLARATION_INVALID", "artifacts deve ser lista de paths")
    declared: list[str] = []
    for value in values:
        if not isinstance(value, str):
            _fail("DOCVIVA_DECLARATION_INVALID", "artifact deve ser path textual")
        declared.append(
            _normalized_relative(value, label="artifact declarado").as_posix()
        )
    if len(declared) != len(set(declared)):
        _fail("DOCVIVA_DECLARATION_INVALID", "artifacts contém duplicatas")
    return sorted(declared)


def _corresponds(kind: str, path: str) -> bool:
    if kind == "architecture":
        return path == ".bianchini/current/ARCHITECTURE.md"
    if kind == "behavioral":
        return path == ".bianchini/current/SYSTEM_MODEL.md" or (
            path.startswith(".bianchini/current/specs/") and path.endswith(".md")
        )
    if kind == "contract":
        return path.startswith(".bianchini/current/specs/") and path.endswith(".md")
    if kind == "rule":
        return path == ".bianchini/current/SYSTEM_MODEL.md" or (
            path.startswith(".bianchini/current/specs/") and path.endswith(".md")
        )
    return True


def verify_docviva_impact(
    repo: Union[str, Path],
    before: Mapping[str, str],
    classification: Mapping[str, Any],
    artifacts: Iterable[str],
    justification: str,
    required: bool,
) -> dict[str, Any]:
    """Compara snapshots e valida a declaração seletiva de DocViva.

    ``classification`` usa ``kind`` + ``outcome`` para que ``not_applicable``
    nunca seja aceito sem provar que o trabalho foi classificado como interno.
    ``artifacts`` deve enumerar exatamente os arquivos current criados,
    modificados ou removidos entre o snapshot inicial e o estado atual.
    """

    if type(required) is not bool:
        _fail("DOCVIVA_CLASSIFICATION_INVALID", "required deve ser booleano")
    kind, outcome = _classification(classification)
    declared = _declared_artifacts(artifacts)
    normalized_before = _validate_snapshot(before, label="before")
    after = snapshot_docviva(repo)

    before_paths = set(normalized_before)
    after_paths = set(after)
    created = sorted(after_paths - before_paths)
    removed = sorted(before_paths - after_paths)
    modified = sorted(
        path
        for path in before_paths & after_paths
        if normalized_before[path] != after[path]
    )
    changed = sorted(created + modified + removed)
    proof = justification.strip() if isinstance(justification, str) else ""

    if declared != changed:
        _fail(
            "DOCVIVA_DECLARATION_MISMATCH",
            "artifacts declarados não correspondem exatamente aos digests alterados",
        )

    if outcome == "not_applicable":
        if kind != "internal" or required or not proof or changed:
            _fail(
                "DOCVIVA_NOT_APPLICABLE_INVALID",
                "not_applicable exige trabalho interno, justificativa e digests iguais",
            )
    elif outcome == "no_op":
        if not proof or changed:
            _fail(
                "DOCVIVA_NO_OP_INVALID",
                "no_op exige prova textual e digests iguais",
            )
    else:
        if kind in REQUIRED_KINDS and not required:
            _fail(
                "DOCVIVA_CLASSIFICATION_INVALID",
                f"{kind} não pode dispensar DocViva exigida",
            )
        if required and not changed:
            _fail(
                "DOCVIVA_UPDATE_REQUIRED",
                f"mudança {kind} exige artefato current correspondente alterado",
            )
        if not changed:
            _fail(
                "DOCVIVA_UPDATE_REQUIRED",
                "outcome updated exige ao menos um artefato current alterado",
            )
        if required and not any(_corresponds(kind, path) for path in changed):
            _fail(
                "DOCVIVA_ARTIFACT_MISMATCH",
                f"nenhum artefato alterado corresponde à classificação {kind}",
            )

    return {
        "schema_version": 1,
        "status": "verified",
        "kind": kind,
        "outcome": outcome,
        "required": required,
        "artifacts": declared,
        "created": created,
        "modified": modified,
        "removed": removed,
        "changed": changed,
        "before_digest": _snapshot_digest(normalized_before),
        "after_digest": _snapshot_digest(after),
        "justification": proof,
    }
