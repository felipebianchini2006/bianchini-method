#!/usr/bin/env python3
"""Renderiza e instala adapters finos de host a partir de uma fonte canônica."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Union


START_MARKER = "<!-- bianchini-method:host-adapter:start -->"
END_MARKER = "<!-- bianchini-method:host-adapter:end -->"
ALLOWED_TARGETS = frozenset({"AGENTS.md", "CLAUDE.md"})
SOURCE_PATH = Path(__file__).absolute().parents[1] / "host-adapters" / "adapters.json"


class HostAdapterError(ValueError):
    """Falha fechada com código estável para integração futura no CLI."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def _fail(code: str, message: str) -> None:
    raise HostAdapterError(code, message)


def _text_list(value: Any, *, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        _fail("HOST_ADAPTER_SOURCE_INVALID", f"{label} deve ser lista não vazia")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip() or item != item.strip():
            _fail("HOST_ADAPTER_SOURCE_INVALID", f"{label} contém texto inválido")
        if START_MARKER in item or END_MARKER in item:
            _fail("HOST_ADAPTER_SOURCE_INVALID", f"{label} contém marcador reservado")
        normalized.append(item)
    if len(normalized) != len(set(normalized)):
        _fail("HOST_ADAPTER_SOURCE_INVALID", f"{label} contém duplicatas")
    return normalized


def load_adapter_source() -> dict[str, Any]:
    """Lê e valida a única fonte declarativa dos adapters suportados."""

    source = SOURCE_PATH
    if source.is_symlink() or not source.is_file():
        _fail("HOST_ADAPTER_SOURCE_INVALID", "fonte canônica ausente ou symlink")
    try:
        value = json.loads(source.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail("HOST_ADAPTER_SOURCE_INVALID", f"fonte canônica inválida: {error}")
        raise AssertionError from error
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "common_rules",
        "adapters",
    }:
        _fail("HOST_ADAPTER_SOURCE_INVALID", "campos de topo divergentes")
    if type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        _fail("HOST_ADAPTER_SOURCE_INVALID", "schema_version deve ser 1")
    common_rules = _text_list(value.get("common_rules"), label="common_rules")
    adapters = value.get("adapters")
    if not isinstance(adapters, dict) or set(adapters) != {
        "generic",
        "codex",
        "claude-compatible",
    }:
        _fail("HOST_ADAPTER_SOURCE_INVALID", "conjunto de adapters divergente")

    normalized_adapters: dict[str, dict[str, Any]] = {}
    for host, raw_adapter in adapters.items():
        if not isinstance(raw_adapter, dict) or set(raw_adapter) != {
            "target",
            "capabilities",
            "rules",
        }:
            _fail("HOST_ADAPTER_SOURCE_INVALID", f"adapter {host} inválido")
        target = raw_adapter.get("target")
        if target not in ALLOWED_TARGETS:
            _fail("HOST_ADAPTER_SOURCE_INVALID", f"target inválido para {host}")
        normalized_adapters[host] = {
            "target": target,
            "capabilities": _text_list(
                raw_adapter.get("capabilities"),
                label=f"{host}.capabilities",
            ),
            "rules": _text_list(raw_adapter.get("rules"), label=f"{host}.rules"),
        }
    return {
        "schema_version": 1,
        "common_rules": common_rules,
        "adapters": normalized_adapters,
    }


def _adapter(source: Mapping[str, Any], host: str) -> Mapping[str, Any]:
    if not isinstance(host, str) or host not in source["adapters"]:
        _fail("HOST_ADAPTER_UNKNOWN", f"host não suportado: {host!r}")
    adapter = source["adapters"][host]
    if not isinstance(adapter, Mapping):
        _fail("HOST_ADAPTER_SOURCE_INVALID", f"adapter {host} não é objeto")
    return adapter


def _bullet_lines(values: list[str]) -> list[str]:
    return [f"- {value}" for value in values]


def render_adapter(host: str) -> str:
    """Renderiza o bloco gerenciado de um host de forma reproduzível."""

    source = load_adapter_source()
    adapter = _adapter(source, host)
    capabilities = ", ".join(
        f"`{capability}`" for capability in adapter["capabilities"]
    )
    lines = [
        START_MARKER,
        "## Bianchini Method — adapter de host",
        "",
        f"- Host: `{host}`",
        f"- Arquivo: `{adapter['target']}`",
        f"- Capabilities: {capabilities}",
        "",
        "### Contrato comum",
        "",
        *_bullet_lines(source["common_rules"]),
        "",
        "### Política do host",
        "",
        *_bullet_lines(adapter["rules"]),
        END_MARKER,
        "",
    ]
    return "\n".join(lines)


def _repository_root(repo: Union[str, Path]) -> Path:
    raw = Path(repo)
    if any(part.casefold() == ".planning" for part in raw.parts):
        _fail("HOST_ADAPTER_PATH_INVALID", "repositório usa namespace estrangeiro")
    absolute = raw.absolute()
    if absolute.is_symlink():
        _fail("HOST_ADAPTER_SYMLINK", "raiz do repositório não pode ser symlink")
    if not absolute.is_dir():
        _fail("HOST_ADAPTER_PATH_INVALID", "raiz do repositório ausente")
    return absolute.resolve()


def _managed_bounds(content: bytes) -> tuple[int, int] | None:
    start = START_MARKER.encode("utf-8")
    end = END_MARKER.encode("utf-8")
    start_count = content.count(start)
    end_count = content.count(end)
    if start_count == 0 and end_count == 0:
        return None
    if start_count != 1 or end_count != 1:
        _fail("HOST_ADAPTER_MARKERS_INVALID", "marcadores ausentes ou duplicados")
    start_at = content.index(start)
    end_at = content.index(end)
    if end_at < start_at:
        _fail("HOST_ADAPTER_MARKERS_INVALID", "marcadores fora de ordem")
    end_at += len(end)
    if content[end_at : end_at + 2] == b"\r\n":
        end_at += 2
    elif content[end_at : end_at + 1] == b"\n":
        end_at += 1
    return start_at, end_at


def _append_block(existing: bytes, block: bytes) -> bytes:
    if not existing:
        return block
    if existing.endswith(b"\n\n"):
        separator = b""
    elif existing.endswith(b"\n"):
        separator = b"\n"
    else:
        separator = b"\n\n"
    return existing + separator + block


def _atomic_write(path: Path, content: bytes) -> None:
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
        if path.is_file():
            os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
        try:
            parent_descriptor = os.open(path.parent, os.O_RDONLY)
        except OSError:
            parent_descriptor = None
        if parent_descriptor is not None:
            try:
                os.fsync(parent_descriptor)
            finally:
                os.close(parent_descriptor)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def install_adapter(
    repo: Union[str, Path],
    host: str,
    *,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Instala somente o bloco gerenciado e preserva conteúdo estrangeiro.

    Uma segunda instalação idêntica é no-op. Substituir um bloco gerenciado
    divergente exige ``overwrite=True``; arquivos sem bloco recebem um append que
    mantém todos os bytes estrangeiros como prefixo.
    """

    if type(overwrite) is not bool:
        _fail("HOST_ADAPTER_OVERWRITE_INVALID", "overwrite deve ser booleano")
    source = load_adapter_source()
    adapter = _adapter(source, host)
    root = _repository_root(repo)
    target = root / str(adapter["target"])
    if target.is_symlink():
        _fail("HOST_ADAPTER_SYMLINK", f"target não pode ser symlink: {target.name}")
    if target.exists() and not target.is_file():
        _fail("HOST_ADAPTER_PATH_INVALID", f"target não é arquivo: {target.name}")
    existing = target.read_bytes() if target.is_file() else b""
    try:
        existing.decode("utf-8")
    except UnicodeDecodeError as error:
        _fail("HOST_ADAPTER_CONTENT_INVALID", f"{target.name} não é UTF-8")
        raise AssertionError from error

    block = render_adapter(host).encode("utf-8")
    bounds = _managed_bounds(existing)
    if bounds is None:
        desired = _append_block(existing, block)
    else:
        start, end = bounds
        current_block = existing[start:end]
        if current_block == block:
            desired = existing
        elif not overwrite:
            _fail(
                "HOST_ADAPTER_OVERWRITE_REQUIRED",
                f"{target.name} já possui adapter gerenciado divergente",
            )
        else:
            desired = existing[:start] + block + existing[end:]

    changed = desired != existing
    if changed:
        _atomic_write(target, desired)
    return {
        "schema_version": 1,
        "status": "installed" if changed else "unchanged",
        "host": host,
        "target": target.name,
        "changed": changed,
        "digest": hashlib.sha256(block).hexdigest(),
    }
