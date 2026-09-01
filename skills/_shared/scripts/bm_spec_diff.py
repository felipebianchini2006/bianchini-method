#!/usr/bin/env python3
"""Geração determinística de ADDED, MODIFIED e REMOVED entre specs completas."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from bm_feature_support import confined_path, sha256_path
from bm_spec_package import (
    confined_no_symlink,
    derive_directory_diff,
    reject_foreign_namespace,
)


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


def spec_diff(
    *,
    root: Path,
    base: Path,
    target: Path,
    output: Path,
    manifest: Path | None = None,
) -> dict[str, Any]:
    reject_foreign_namespace(root, "spec root")
    reject_foreign_namespace(base, "spec base")
    reject_foreign_namespace(target, "spec target")
    reject_foreign_namespace(output, "spec diff output")
    if manifest is not None:
        reject_foreign_namespace(manifest, "spec manifest")
    trusted_root = root.absolute()
    raw_paths = {
        "spec base": base if base.is_absolute() else trusted_root / base,
        "spec target": target if target.is_absolute() else trusted_root / target,
        "spec diff output": output if output.is_absolute() else trusted_root / output,
    }
    if manifest is not None:
        raw_paths["spec manifest"] = (
            manifest if manifest.is_absolute() else trusted_root / manifest
        )
    safe_raw_paths = {
        label: confined_no_symlink(trusted_root, raw_path, label)
        for label, raw_path in raw_paths.items()
    }
    repository = root.resolve()
    base_path = confined_path(repository, base, "spec base")
    target_path = confined_path(repository, target, "spec target")
    output_path = confined_path(repository, output, "spec diff output")
    if output_path in {base_path, target_path}:
        raise ValueError("spec diff output deve ser diferente da base e do target")
    if base_path.is_dir() or target_path.is_dir():
        if not base_path.is_dir() or not target_path.is_dir():
            raise ValueError("spec diff exige base e target do mesmo tipo")
        try:
            output_path.relative_to(base_path)
        except ValueError:
            pass
        else:
            raise ValueError("spec diff output não pode ficar dentro da base")
        try:
            output_path.relative_to(target_path)
        except ValueError:
            pass
        else:
            raise ValueError("spec diff output não pode ficar dentro do target")
        manifest_value = (
            manifest
            if manifest is not None
            else raw_paths["spec target"].parent / "MANIFEST.json"
        )
        raw_manifest = (
            manifest_value
            if manifest_value.is_absolute()
            else repository / manifest_value
        )
        safe_manifest = confined_no_symlink(
            trusted_root, raw_manifest, "spec manifest"
        )
        metadata, rendered = derive_directory_diff(
            root=trusted_root,
            base=safe_raw_paths["spec base"],
            target=safe_raw_paths["spec target"],
            manifest_path=safe_manifest,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered, encoding="utf-8")
        return {
            **metadata,
            "output": output_path.relative_to(repository).as_posix(),
            "output_digest": sha256_path(output_path),
        }
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
