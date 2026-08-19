#!/usr/bin/env python3
"""Normalização e validação determinística de evidência de mutation testing."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from bm_context import strongest_mutation_mode
from bm_feature_support import confined_path, field_value, json_document, sha256_path, unit_sections


CLASSIFICATIONS = frozenset({"equivalent", "unreachable", "non_material", "blocking"})


def git_output(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=False
    )
    if completed.returncode != 0:
        raise ValueError(completed.stderr.strip() or "comando Git falhou")
    return completed.stdout.strip()


def classifications_document(path: Path | None) -> tuple[dict[str, dict[str, Any]], str | None]:
    if path is None:
        return {}, None
    value = json_document(path, "classificações de mutantes")
    source = value.get("mutants", value)
    if not isinstance(source, dict):
        raise ValueError("classificações de mutantes devem ser objeto por ID")
    normalized: dict[str, dict[str, Any]] = {}
    for identifier, classification in source.items():
        if not isinstance(identifier, str) or not isinstance(classification, dict):
            raise ValueError("classificação de mutante inválida")
        normalized[identifier] = classification
    return normalized, sha256_path(path)


def normalized_mutants(
    report: dict[str, Any], tool: str, classifications: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    if tool == "normalized":
        values = report.get("mutants")
        if report.get("schema_version") != 1 or not isinstance(values, list):
            raise ValueError("relatório normalized exige schema_version 1 e lista mutants")
        source_values: list[tuple[str | None, Any]] = [(None, item) for item in values]
    elif tool == "stryker":
        files = report.get("files")
        if not isinstance(files, dict):
            raise ValueError("relatório Stryker exige objeto files")
        source_values = []
        for file_name, file_data in files.items():
            mutants = file_data.get("mutants") if isinstance(file_data, dict) else None
            if isinstance(mutants, list):
                source_values.extend((str(file_name), item) for item in mutants)
    else:
        raise ValueError(f"tool de mutação não suportada: {tool}")
    status_map = {
        "killed": "killed", "timeout": "killed", "survived": "survived",
        "nocoverage": "survived", "no_coverage": "survived", "ignored": "ignored",
        "compileerror": "error", "compile_error": "error",
        "runtimeerror": "error", "runtime_error": "error", "error": "error",
    }
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, (file_name, raw) in enumerate(source_values):
        if not isinstance(raw, dict):
            raise ValueError("mutante deve ser objeto")
        identifier = str(raw.get("id") or f"{file_name or 'mutant'}:{index}")
        if identifier in seen:
            raise ValueError(f"ID de mutante duplicado: {identifier}")
        seen.add(identifier)
        raw_status = str(raw.get("status", "")).replace("-", "").replace(" ", "").lower()
        status = status_map.get(raw_status)
        if status is None:
            raise ValueError(f"status de mutante desconhecido {raw.get('status')!r}: {identifier}")
        external = classifications.get(identifier, {})
        result.append(
            {
                "id": identifier,
                "file": file_name or raw.get("file"),
                "status": status,
                "classification": external.get("classification", raw.get("classification")),
                "justification": external.get("justification", raw.get("justification")),
            }
        )
    if not result:
        raise ValueError("relatório de mutação não contém mutantes")
    return result


def mutation_evidence_verify(
    *,
    root: Path,
    state: dict[str, Any],
    plan_id: str,
    risk_seam: str,
    tool: str,
    command: str,
    report: Path,
    output: Path,
    revision: str,
    classifications: Path | None,
) -> dict[str, Any]:
    repository = root.resolve()
    if Path(git_output(repository, "rev-parse", "--show-toplevel")).resolve() != repository:
        raise ValueError("--root deve apontar para a raiz Git")
    report_path = confined_path(repository, report, "mutation report")
    output_path = confined_path(repository, output, "mutation evidence output")
    classifications_path = (
        confined_path(repository, classifications, "mutation classifications")
        if classifications is not None
        else None
    )
    input_paths = {report_path}
    if classifications_path is not None:
        input_paths.add(classifications_path)
    if output_path in input_paths:
        raise ValueError(
            "mutation evidence output deve ser diferente dos arquivos de entrada"
        )
    allowed_artifacts = {
        path.relative_to(repository).as_posix()
        for path in (*input_paths, output_path)
    }
    dirty = git_output(repository, "status", "--porcelain=v1", "--untracked-files=all")
    unrelated = sorted(
        line[3:].split(" -> ")[-1]
        for line in dirty.splitlines()
        if len(line) > 3 and line[3:].split(" -> ")[-1] not in allowed_artifacts
    )
    if unrelated:
        raise ValueError(
            "mutation-evidence exige código limpo; alterações alheias: " + ", ".join(unrelated[:8])
        )
    plan = next((item for item in state.get("plans", []) if item.get("id") == plan_id), None)
    if plan is None:
        raise ValueError(f"plano inexistente: {plan_id}")
    plan_path = confined_path(repository, plan.get("path", ""), "plan.path")
    if not plan_path.is_file():
        raise ValueError(f"plano ausente: {plan_path}")
    changes = [
        value
        for _, section in unit_sections(plan_path.read_text(encoding="utf-8"))
        if (value := field_value(section, "Change"))
    ]
    policy = strongest_mutation_mode(str(plan.get("risk")), changes)
    candidate = state.get("release", {}).get("candidate")
    current_revision = git_output(repository, "rev-parse", "HEAD")
    expected_revision = (
        str(candidate.get("revision"))
        if isinstance(candidate, dict) and candidate.get("revision")
        else current_revision
    )
    classifications_data, classifications_digest = classifications_document(classifications_path)
    mutants = normalized_mutants(
        json_document(report_path, "mutation report"), tool, classifications_data
    )
    known_mutants = {mutant["id"] for mutant in mutants}
    unknown_classifications = sorted(set(classifications_data) - known_mutants)
    if unknown_classifications:
        raise ValueError(
            "classificações referenciam mutantes ausentes: "
            + ", ".join(unknown_classifications)
        )
    blocking: list[str] = []
    unclassified: list[str] = []
    accepted: list[str] = []
    errors: list[str] = []
    ignored: list[str] = []
    for mutant in mutants:
        identifier = mutant["id"]
        if mutant["status"] == "error":
            errors.append(identifier)
        elif mutant["status"] == "ignored":
            ignored.append(identifier)
        elif mutant["status"] == "survived":
            classification = mutant.get("classification")
            justification = mutant.get("justification")
            if classification not in CLASSIFICATIONS:
                unclassified.append(identifier)
            elif classification == "blocking":
                blocking.append(identifier)
            elif not isinstance(justification, str) or not justification.strip():
                unclassified.append(identifier)
            else:
                accepted.append(identifier)
    if revision != expected_revision:
        blocking.append("revision-mismatch")
    if policy in {"selective", "required_selective"}:
        blocking.extend(errors)
        blocking.extend(ignored)
        blocking.extend(unclassified)
    counts = {
        "total": len(mutants),
        "killed": sum(item["status"] == "killed" for item in mutants),
        "survived": sum(item["status"] == "survived" for item in mutants),
        "ignored": len(ignored),
        "errors": len(errors),
        "accepted_survivors": len(accepted),
        "unclassified_survivors": len(unclassified),
        "blocking": len(set(blocking)),
    }
    fingerprint = (
        {key: candidate.get(key) for key in ("id", "revision", "build", "checksum")}
        if isinstance(candidate, dict)
        else None
    )
    status = "passed" if not blocking else "blocked"
    payload = {
        "schema_version": 1,
        "status": status,
        "result": status,
        "policy": policy,
        "plan": plan_id,
        "risk_seam": risk_seam,
        "changes": changes,
        "tool": tool,
        "command": command,
        "revision": revision,
        "expected_revision": expected_revision,
        "candidate": fingerprint,
        "report": report_path.relative_to(repository).as_posix(),
        "report_digest": sha256_path(report_path),
        "classifications_digest": classifications_digest,
        "mutants": counts,
        "accepted_survivors": sorted(accepted),
        "unclassified_survivors": sorted(unclassified),
        "blocking_mutants": sorted(set(blocking)),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    payload["output"] = output_path.relative_to(repository).as_posix()
    payload["output_digest"] = sha256_path(output_path)
    return payload
