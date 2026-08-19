#!/usr/bin/env python3
"""Primitivas stdlib compartilhadas por extensões determinísticas do método."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any


UNIT_HEADING = re.compile(
    r"(?m)^###\s+(?:Tarefa|Task|Slice|Grupo|Group)\s+[^\n]+$",
    re.IGNORECASE,
)
FIX_ROUNDS_BY_PROFILE = {
    "lean": 2,
    "standard": 3,
    "full": 5,
}


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def confined_path(root: Path, value: str | Path, label: str) -> Path:
    base = root.resolve()
    relative = Path(value)
    target = relative.resolve() if relative.is_absolute() else (base / relative).resolve()
    try:
        target.relative_to(base)
    except ValueError as error:
        raise ValueError(f"{label} fora da raiz: {value}") from error
    return target


def json_document(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"{label} ausente: {path}")
    text = path.read_text(encoding="utf-8")
    fenced = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    candidate = fenced.group(1) if fenced else text
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as error:
        raise ValueError(f"{label}: JSON inválido na linha {error.lineno}") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label}: esperado objeto JSON")
    return value


def unit_sections(content: str) -> list[tuple[str, str]]:
    matches = list(UNIT_HEADING.finditer(content))
    return [
        (
            match.group(0).strip(),
            content[
                match.start() : matches[index + 1].start()
                if index + 1 < len(matches)
                else len(content)
            ],
        )
        for index, match in enumerate(matches)
    ]


def field_value(section: str, field: str) -> str | None:
    match = re.search(rf"(?mi)^\*\*{re.escape(field)}:\*\*\s*(\S[^\n]*)$", section)
    return match.group(1).strip() if match else None
