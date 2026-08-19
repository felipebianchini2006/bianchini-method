#!/usr/bin/env python3
"""Geração determinística de ADDED, MODIFIED e REMOVED entre specs completas."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from bm_feature_support import confined_path, sha256_path


REQUIREMENT_HEADING = re.compile(
    r"(?m)^(#{2,6})\s+\[?([A-Z][A-Z0-9_-]*-[0-9]{3,})\]?"
    r"(?:\s*[:—-]\s*|\s+)([^\n]+)$"
)


def parse_requirements(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise ValueError(f"spec ausente: {path}")
    content = path.read_text(encoding="utf-8")
    requirements = list(REQUIREMENT_HEADING.finditer(content))
    if not requirements:
        raise ValueError(
            f"spec {path} não contém requisitos com ID estável em heading, "
            "como ## AUTH-001: Título"
        )
    headings = list(re.finditer(r"(?m)^(#{1,6})\s+([^\n]+)$", content))
    positions = {match.start(): index for index, match in enumerate(headings)}
    parsed: dict[str, str] = {}
    for match in requirements:
        identifier = match.group(2)
        if identifier in parsed:
            raise ValueError(f"spec {path} contém ID duplicado: {identifier}")
        level = len(match.group(1))
        end = len(content)
        for following in headings[positions[match.start()] + 1 :]:
            if len(following.group(1)) <= level:
                end = following.start()
                break
        parsed[identifier] = re.sub(
            r"[ \t]+$", "", content[match.start():end].strip(), flags=re.MULTILINE
        )
    return parsed


def spec_diff(*, root: Path, base: Path, target: Path, output: Path) -> dict[str, Any]:
    repository = root.resolve()
    base_path = confined_path(repository, base, "spec base")
    target_path = confined_path(repository, target, "spec target")
    output_path = confined_path(repository, output, "spec diff output")
    if output_path in {base_path, target_path}:
        raise ValueError("spec diff output deve ser diferente da base e do target")
    current = parse_requirements(base_path)
    future = parse_requirements(target_path)
    added = sorted(set(future) - set(current))
    removed = sorted(set(current) - set(future))
    modified = sorted(
        identifier
        for identifier in set(current) & set(future)
        if current[identifier] != future[identifier]
    )
    metadata = {
        "schema_version": 1,
        "base": base_path.relative_to(repository).as_posix(),
        "base_digest": sha256_path(base_path),
        "target": target_path.relative_to(repository).as_posix(),
        "target_digest": sha256_path(target_path),
        "added": added,
        "modified": modified,
        "removed": removed,
    }
    lines = [
        "# Spec Diff", "",
        "Esta é uma projeção derivada. A spec target completa permanece a fonte de verdade.",
        "", "```json", json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True), "```",
    ]
    for title, identifiers, source in (
        ("ADDED", added, future), ("MODIFIED", modified, future), ("REMOVED", removed, current)
    ):
        lines.extend(("", f"## {title}", ""))
        if not identifiers:
            lines.append("Nenhum.")
        for identifier in identifiers:
            lines.extend((f"### {identifier}", "", source[identifier], ""))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return {
        **metadata,
        "output": output_path.relative_to(repository).as_posix(),
        "output_digest": sha256_path(output_path),
    }
