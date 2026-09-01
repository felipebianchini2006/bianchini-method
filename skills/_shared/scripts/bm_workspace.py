#!/usr/bin/env python3
"""Workspace canônico, compacto e transacional do Bianchini Method 0.4."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Mapping


STATE_LIMIT_BYTES = 64 * 1024
STATE_ALLOWED_FIELDS = frozenset(
    {
        "schema_version",
        "method",
        "active_work",
        "current_unit",
        "status",
        "blockers",
        "next_action",
        "last_completed",
        "pointers",
        "digest",
        "updated_at",
    }
)
STATE_HISTORY_FIELDS = frozenset(
    {"history", "ledger", "events", "results", "timeline", "completed_work"}
)
ID_KINDS = {
    "change": ("C", 3),
    "quick": ("Q", 3),
    "debug": ("D", 3),
    "plan": ("P", 2),
}


class MethodWorkspace:
    """Acesso único ao namespace ``.bianchini`` de um projeto.

    Caminhos fornecidos por chamadores nunca escapam do namespace. Escritas usam
    ``os.replace`` no mesmo diretório para que leitores observem o conteúdo antigo
    ou o novo, mas nunca um arquivo parcial.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.bianchini_dir = self.root / ".bianchini"
        self.project_file = self.bianchini_dir / "PROJECT.md"
        self.state_file = self.bianchini_dir / "STATE.md"
        self.current_dir = self.bianchini_dir / "current"
        self.current_architecture = self.current_dir / "ARCHITECTURE.md"
        self.current_system_model = self.current_dir / "SYSTEM_MODEL.md"
        self.current_specs = self.current_dir / "specs"
        self.changes_dir = self.bianchini_dir / "changes"
        self.quick_dir = self.bianchini_dir / "quick"
        self.debug_dir = self.bianchini_dir / "debug"
        self.debug_active = self.debug_dir / "active"
        self.debug_resolved = self.debug_dir / "resolved"
        self.debug_knowledge = self.debug_dir / "KNOWLEDGE.md"
        self.archive_dir = self.bianchini_dir / "archive"
        self.runtime_dir = self.bianchini_dir / ".runtime"

    def resolve(self, value: str | Path = ".") -> Path:
        """Resolve ``value`` dentro de ``.bianchini`` e rejeita escapes/symlinks."""

        raw = Path(value)
        candidate = raw.resolve() if raw.is_absolute() else (self.bianchini_dir / raw).resolve()
        base = self.bianchini_dir.resolve()
        try:
            candidate.relative_to(base)
        except ValueError as error:
            raise ValueError(f"caminho fora de .bianchini: {value}") from error
        return candidate

    def initialize(self) -> None:
        """Cria o esqueleto 0.4 sem inspecionar namespaces estrangeiros."""

        for directory in (
            self.current_specs,
            self.changes_dir,
            self.quick_dir,
            self.debug_active,
            self.debug_resolved,
            self.archive_dir,
            self.runtime_dir,
        ):
            self.resolve(directory)
            directory.mkdir(parents=True, exist_ok=True)
        defaults = {
            self.bianchini_dir / ".gitignore": ".runtime/\n",
            self.project_file: "# Projeto\n\nPropósito, limites e invariantes estáveis.\n",
            self.current_architecture: "# Arquitetura atual\n",
            self.current_system_model: self._empty_system_model(),
            self.current_specs / "MANIFEST.json": json.dumps(
                {
                    "schema_version": 1,
                    "spec_contract": 1,
                    "specs": [],
                    "risk_coverage": [],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            self.debug_knowledge: "# Conhecimento de debug\n",
        }
        for path, content in defaults.items():
            self.resolve(path)
            if not path.exists():
                self.atomic_write(path, content)
        if not self.state_file.exists():
            self.write_state(
                {
                    "schema_version": 1,
                    "method": "0.4",
                    "active_work": None,
                    "current_unit": None,
                    "status": "idle",
                    "blockers": [],
                    "next_action": None,
                    "last_completed": None,
                    "pointers": {
                        "architecture": ".bianchini/current/ARCHITECTURE.md",
                        "system_model": ".bianchini/current/SYSTEM_MODEL.md",
                        "specs": ".bianchini/current/specs",
                        "coherence": None,
                    },
                    "digest": None,
                    "updated_at": None,
                },
                "# Estado atual\n",
            )

    def atomic_write(self, path: str | Path, content: str | bytes) -> Path:
        """Escreve conteúdo de modo atômico e durável dentro do workspace."""

        target = self.resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        data = content.encode("utf-8") if isinstance(content, str) else bytes(content)
        if target.is_file() and target.read_bytes() == data:
            return target
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
            if target.exists():
                os.chmod(temporary, target.stat().st_mode & 0o777)
            os.replace(temporary, target)
            self._sync_directory(target.parent)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return target

    def write_state(self, state: Mapping[str, Any], body: str = "# Estado atual\n") -> Path:
        """Valida e persiste o índice atual, limitado a 64 KiB."""

        normalized = self._validate_state(state)
        frontmatter = json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        document = f"---\n{frontmatter}\n---\n{body.rstrip()}\n"
        if len(document.encode("utf-8")) > STATE_LIMIT_BYTES:
            raise ValueError("STATE.md excede o limite de 64 KiB")
        return self.atomic_write(self.state_file, document)

    def read_state(self) -> dict[str, Any]:
        """Lê o frontmatter JSON de ``STATE.md`` e reaplica as invariantes."""

        state_path = self.resolve(self.state_file)
        if not state_path.is_file():
            raise ValueError(f"STATE.md ausente: {self.state_file}")
        data = state_path.read_bytes()
        if len(data) > STATE_LIMIT_BYTES:
            raise ValueError("STATE.md excede o limite de 64 KiB")
        text = data.decode("utf-8")
        match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", text, re.DOTALL)
        if match is None:
            raise ValueError("STATE.md exige frontmatter JSON")
        try:
            value = json.loads(match.group(1))
        except json.JSONDecodeError as error:
            raise ValueError(f"STATE.md contém JSON inválido na linha {error.lineno}") from error
        if not isinstance(value, dict):
            raise ValueError("STATE.md exige objeto no frontmatter")
        return self._validate_state(value)

    def allocate_id(self, kind: str) -> str:
        """Reserva o próximo ID monotônico de uma categoria operacional."""

        if kind not in ID_KINDS:
            raise ValueError(f"tipo de ID desconhecido: {kind}")
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        prefix, width = ID_KINDS[kind]
        counters_path = self.runtime_dir / "id-counters.json"
        self.resolve(counters_path)
        counters: dict[str, int] = {}
        if counters_path.is_file():
            try:
                loaded = json.loads(counters_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as error:
                raise ValueError("registro de IDs inválido") from error
            if isinstance(loaded, dict):
                counters = {
                    key: int(value)
                    for key, value in loaded.items()
                    if key in ID_KINDS and isinstance(value, int) and value >= 0
                }
        observed = self._largest_observed_id(prefix)
        value = max(observed, counters.get(kind, 0)) + 1
        counters[kind] = value
        self.atomic_write(
            counters_path,
            json.dumps(counters, sort_keys=True, separators=(",", ":")) + "\n",
        )
        return f"{prefix}{value:0{width}d}"

    def _largest_observed_id(self, prefix: str) -> int:
        if not self.bianchini_dir.exists():
            return 0
        pattern = re.compile(rf"^{re.escape(prefix)}([0-9]+)(?:\b|[-_.])")
        largest = 0
        for candidate in self.bianchini_dir.rglob(f"{prefix}[0-9]*"):
            match = pattern.match(candidate.name)
            if match:
                largest = max(largest, int(match.group(1)))
        return largest

    def _validate_state(self, state: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(state, Mapping):
            raise ValueError("STATE.md exige objeto")
        keys = set(state)
        forbidden = sorted(keys & STATE_HISTORY_FIELDS)
        if forbidden:
            raise ValueError(f"campo de histórico proibido em STATE.md: {forbidden[0]}")
        unknown = sorted(keys - STATE_ALLOWED_FIELDS)
        if unknown:
            raise ValueError(f"campo não suportado em STATE.md: {unknown[0]}")
        if state.get("schema_version") != 1:
            raise ValueError("STATE.md exige schema_version 1")
        if state.get("method") != "0.4":
            raise ValueError("STATE.md exige method 0.4")
        blockers = state.get("blockers", [])
        if not isinstance(blockers, list) or not all(isinstance(item, str) for item in blockers):
            raise ValueError("STATE.md.blockers exige lista de strings")
        pointers = state.get("pointers", {})
        if not isinstance(pointers, Mapping) or not all(
            isinstance(key, str) and (isinstance(value, str) or value is None)
            for key, value in pointers.items()
        ):
            raise ValueError("STATE.md.pointers exige objeto de strings ou null")
        if "model" in pointers:
            raise ValueError("pointer não canônico: use system_model")
        for label, value in pointers.items():
            if value is None:
                continue
            prefix = ".bianchini/"
            if not value.startswith(prefix):
                raise ValueError(f"pointer fora de .bianchini: {label}")
            self.resolve(value[len(prefix) :])
        return json.loads(json.dumps(dict(state), ensure_ascii=False))

    @staticmethod
    def _sync_directory(path: Path) -> None:
        flags = getattr(os, "O_DIRECTORY", 0) | os.O_RDONLY
        descriptor = os.open(path, flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _empty_system_model() -> str:
        fields = (
            "modules",
            "interfaces",
            "capabilities",
            "contracts",
            "ownership",
            "data",
            "integrations",
            "journeys",
            "invariants",
            "effects",
        )
        payload = {field: [] for field in fields}
        payload["schema_version"] = 1
        return (
            "---\n"
            + json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2)
            + "\n---\n# Modelo do sistema\n"
        )


__all__ = [
    "ID_KINDS",
    "MethodWorkspace",
    "STATE_ALLOWED_FIELDS",
    "STATE_LIMIT_BYTES",
]
