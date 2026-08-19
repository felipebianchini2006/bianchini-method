#!/usr/bin/env python3
"""Aplica correções revisadas no CLI e inclui o novo shard adversarial."""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path.cwd()


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    content = path.read_text(encoding="utf-8")
    count = content.count(old)
    if count != 1:
        raise SystemExit(f"{label}: esperado 1, encontrado {count}")
    path.write_text(content.replace(old, new, 1), encoding="utf-8")


def replace_pattern_once(
    path: Path,
    pattern: str,
    replacement: str,
    label: str,
) -> None:
    content = path.read_text(encoding="utf-8")
    match = re.search(pattern, content, re.DOTALL)
    if match is None:
        raise SystemExit(f"{label}: trecho não encontrado")
    if re.search(pattern, content[match.end() :], re.DOTALL):
        raise SystemExit(f"{label}: mais de um trecho encontrado")
    path.write_text(
        content[: match.start()] + replacement + content[match.end() :],
        encoding="utf-8",
    )


bm = ROOT / "skills/_shared/scripts/bm.py"
replace_once(
    bm,
    "from bm_mutation import mutation_evidence_verify\nfrom bm_spec_diff import spec_diff\n",
    "from bm_feature_support import FIX_ROUNDS_BY_PROFILE\n"
    "from bm_mutation import mutation_evidence_verify\n"
    "from bm_spec_diff import spec_diff\n",
    "import do limite de fix rounds",
)
replace_once(
    bm,
    '    max_rounds = {"lean": 2, "standard": 3, "full": 5}[profile]\n',
    "    max_rounds = FIX_ROUNDS_BY_PROFILE[profile]\n",
    "fonte única do limite de fix rounds",
)

proof_map = '''def write_proof_map(
    state_path: Path,
    evidence_path: Path,
    output: Path,
    mutation_evidence_paths: list[Path] | None = None,
) -> dict[str, Any]:
    state = validate_state(state_path)
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BMError(f"evidência inválida: {error}") from error
    if not isinstance(evidence, list) or not all(isinstance(item, dict) for item in evidence):
        raise BMError("evidência deve ser uma lista JSON de objetos")
    candidate = state.get("release", {}).get("candidate")
    if not isinstance(candidate, dict):
        raise BMError("release candidate com fingerprint é obrigatório para proof-map")
    fingerprint = {
        key: candidate[key] for key in ("id", "revision", "build", "checksum")
    }
    mutation_sources: list[str] = []
    for mutation_path in mutation_evidence_paths or []:
        if not mutation_path.is_file():
            raise BMError(f"evidência de mutação ausente: {mutation_path}")
        try:
            mutation = json.loads(mutation_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise BMError(
                f"evidência de mutação inválida na linha {error.lineno}: {mutation_path}"
            ) from error
        if not isinstance(mutation, dict) or mutation.get("schema_version") != 1:
            raise BMError(f"evidência de mutação inválida: {mutation_path}")
        mutation_candidate = mutation.get("candidate")
        command = mutation.get("command")
        result = mutation.get("result", mutation.get("status"))
        if not isinstance(mutation_candidate, dict):
            raise BMError(
                f"evidência de mutação não está vinculada a um RC: {mutation_path}"
            )
        if not isinstance(command, str) or not command.strip():
            raise BMError(f"evidência de mutação sem command: {mutation_path}")
        if result not in {"passed", "blocked"}:
            raise BMError(f"evidência de mutação sem resultado válido: {mutation_path}")
        evidence.append(
            {
                "type": "mutation",
                "command": command,
                "result": result,
                "evidence": str(mutation_path),
                "rc": mutation_candidate.get("id"),
                "revision": mutation_candidate.get("revision"),
                "build": mutation_candidate.get("build"),
                "checksum": mutation_candidate.get("checksum"),
            }
        )
        mutation_sources.append(str(mutation_path))
    by_command = {item.get("command"): item for item in evidence if item.get("command")}
    rows: list[dict[str, Any]] = []
    gaps: list[str] = []
    for command in state["verification"]["release"]["commands"]:
        item = by_command.get(command)
        evidence_fingerprint = (
            {
                "id": item.get("rc", item.get("id")),
                "revision": item.get("revision"),
                "build": item.get("build"),
                "checksum": item.get("checksum"),
            }
            if item
            else None
        )
        same_candidate = evidence_fingerprint == fingerprint
        proven = bool(item and item.get("result") == "passed" and same_candidate)
        rows.append(
            {
                "command": command,
                "proven": proven,
                "source_type": item.get("type") if item else None,
                "candidate": evidence_fingerprint,
                "evidence": item.get("evidence") if item else None,
            }
        )
        if not proven:
            gaps.append(command)
    manual_gaps = [
        item.get("journey")
        for item in evidence
        if item.get("type") == "manual_gap" and item.get("journey")
    ]
    proof = {
        "candidate": fingerprint,
        "automated": rows,
        "automated_total": len(rows),
        "automated_proven": len(rows) - len(gaps),
        "automation_gaps": gaps,
        "manual_gaps": manual_gaps,
        "mutation_evidence": mutation_sources,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(proof, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
    return {"proof_map": str(output), **proof}
'''
replace_pattern_once(
    bm,
    r"def write_proof_map\(.*?\n\nDIRECT_HAZARDS =",
    proof_map + "\n\nDIRECT_HAZARDS =",
    "integração de mutação no proof-map",
)
replace_once(
    bm,
    '    proof.add_argument("--output", type=Path, required=True)\n',
    '    proof.add_argument(\n'
    '        "--mutation-evidence", action="append", type=Path, default=[]\n'
    '    )\n'
    '    proof.add_argument("--output", type=Path, required=True)\n',
    "parser de mutation evidence no proof-map",
)
replace_once(
    bm,
    '        elif args.command == "proof-map":\n'
    '            emit(write_proof_map(args.state, args.evidence, args.output))\n',
    '        elif args.command == "proof-map":\n'
    '            emit(\n'
    '                write_proof_map(\n'
    '                    args.state,\n'
    '                    args.evidence,\n'
    '                    args.output,\n'
    '                    args.mutation_evidence,\n'
    '                )\n'
    '            )\n',
    "handler do proof-map",
)

runner = ROOT / "scripts/run_test_shards.py"
replace_once(
    runner,
    'CODEX_SHARDS = (\n',
    'REVIEW_SHARDS = (\n'
    '    "ContextEfficiencyReviewScenarios",\n'
    ')\n\n'
    'CODEX_SHARDS = (\n',
    "lista de shards adversariais",
)
replace_once(
    runner,
    '    for shard in CODEX_SHARDS:\n',
    '    for shard in REVIEW_SHARDS:\n'
    '        print(f"\\n=== {shard} ===", file=sys.stderr, flush=True)\n'
    '        completed = subprocess.run(\n'
    '            [\n'
    '                sys.executable,\n'
    '                "-m",\n'
    '                "unittest",\n'
    '                f"test_context_efficiency_review.{shard}",\n'
    '                "-v",\n'
    '            ],\n'
    '            cwd=TESTS,\n'
    '            env=environment,\n'
    '            check=False,\n'
    '        )\n'
    '        if completed.returncode != 0:\n'
    '            return completed.returncode\n'
    '    for shard in CODEX_SHARDS:\n',
    "execução dos shards adversariais",
)
replace_once(
    runner,
    '    print(f"\\n{len(SHARDS) + len(CODEX_SHARDS)} shards aprovados.", file=sys.stderr)\n',
    '    total = len(SHARDS) + len(REVIEW_SHARDS) + len(CODEX_SHARDS)\n'
    '    print(f"\\n{total} shards aprovados.", file=sys.stderr)\n',
    "total de shards",
)
