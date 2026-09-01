#!/usr/bin/env python3
"""Mede de forma reproduzivel contexto e DocViva da Fase 2."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SHARED_SCRIPTS = ROOT / "skills" / "_shared" / "scripts"
BASELINE = ROOT / "reports" / "evolution-0.4.7" / "baseline.json"
REPORT = ROOT / "reports" / "evolution-0.4.7" / "phase2-context-docviva.json"
BASELINE_COMMIT = "7c9fa23f524623f3360ebae579048e1765095220"
BASELINE_FIXTURE_COMMIT = "c5a85f9bda9ea3e28f32c7c3e6f104063ee88d15"

BASELINE_CONTEXT_PATHS = {
    "executar-plano": (
        "skills/executar-plano/SKILL.md",
        "skills/_shared/METHOD_CONTRACT.md",
        "skills/_shared/ADAPTIVE_GATES.md",
    ),
    "executar-direto": (
        "skills/executar-direto/SKILL.md",
        "skills/_shared/METHOD_CONTRACT.md",
    ),
    "corrigir-bug": (
        "skills/corrigir-bug/SKILL.md",
        "skills/_shared/METHOD_CONTRACT.md",
    ),
    "homologar-sistema": (
        "skills/homologar-sistema/SKILL.md",
        "skills/_shared/METHOD_CONTRACT.md",
    ),
    "status-projeto": (
        "skills/status-projeto/SKILL.md",
        "skills/_shared/METHOD_CONTRACT.md",
    ),
}

BASELINE_RUNTIME_PATHS = (
    "scripts/bm.py",
    "skills/_shared/scripts/bm.py",
    "skills/_shared/scripts/bm_coherence.py",
    "skills/_shared/scripts/bm_context.py",
    "skills/_shared/scripts/bm_feature_support.py",
    "skills/_shared/scripts/bm_mutation.py",
    "skills/_shared/scripts/bm_project_model.py",
    "skills/_shared/scripts/bm_scope.py",
    "skills/_shared/scripts/bm_spec_diff.py",
    "skills/_shared/scripts/bm_update.py",
    "skills/_shared/scripts/bm_v04_planning.py",
    "skills/_shared/scripts/bm_v04_workflows.py",
    "skills/_shared/scripts/bm_workspace.py",
)

BASELINE_RUNNER_PATHS = (
    "scripts/_cli_contract.py",
    "scripts/run_cli_contract_fixtures.py",
)

BASELINE_FIXTURE_PATHS = (
    "tests/fixtures/cli_contract/change-policy-material.json",
    "tests/fixtures/cli_contract/change-policy-read-only.json",
    "tests/fixtures/cli_contract/direct-classify-default.json",
    "tests/fixtures/cli_contract/direct-classify-protected.json",
    "tests/fixtures/cli_contract/direct-reopen-terminal.json",
    "tests/fixtures/cli_contract/retired-legacy-transition.json",
    "tests/fixtures/cli_contract/retired-repo-hygiene.json",
    "tests/fixtures/cli_contract/retired-route.json",
    "tests/fixtures/cli_contract/spec-diff-created-output.json",
    "tests/fixtures/cli_contract/status-legacy-json.json",
    "tests/fixtures/cli_contract/status-legacy-text.json",
    "tests/fixtures/cli_contract/workspace-old-companion-flags.json",
)

SAFE_GIT_PATHS = frozenset(
    path
    for paths in (
        tuple(BASELINE_CONTEXT_PATHS.values())
        + (BASELINE_RUNTIME_PATHS, BASELINE_RUNNER_PATHS, BASELINE_FIXTURE_PATHS)
    )
    for path in paths
)

for path in (ROOT, SHARED_SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from bm_context import (  # noqa: E402
    DEFAULT_MAX_BYTES,
    compile_context_pack,
    verify_context_pack,
)
from bm_docviva import (  # noqa: E402
    snapshot_docviva,
    verify_docviva_impact,
    write_if_changed,
)
from tests.test_context_skill_adoption import (  # noqa: E402
    ContextSkillAdoptionScenarios,
)


CONTEXT_CASES = (
    ("executar-plano", "C001/P01/T01"),
    ("executar-direto", "Q012"),
    ("corrigir-bug", "D004"),
    ("homologar-sistema", "RC:build-a"),
    ("status-projeto", "C001/P01"),
)


def _git_blob(commit: str, path: str) -> bytes:
    candidate = Path(path)
    if (
        path not in SAFE_GIT_PATHS
        or candidate.is_absolute()
        or ".." in candidate.parts
        or ".planning" in candidate.parts
    ):
        raise ValueError(f"path Git fora da allowlist segura: {path}")
    completed = subprocess.run(
        ["git", "show", f"{commit}:{path}"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ValueError(f"git show falhou para {commit}:{path}: {message}")
    return completed.stdout


def _verify_baseline_context(
    payload: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    if payload.get("base_commit") != BASELINE_COMMIT:
        raise ValueError("commit da baseline divergiu do contrato congelado")
    entries = payload.get("skill_context")
    if not isinstance(entries, list):
        raise ValueError("baseline sem skill_context versionado")
    by_skill = {
        str(entry["skill"]): entry
        for entry in entries
        if isinstance(entry, dict) and isinstance(entry.get("skill"), str)
    }
    expected = {skill for skill, _unit in CONTEXT_CASES}
    if set(by_skill) != expected:
        raise ValueError("skill_context da baseline divergiu das cinco interfaces")

    unique_paths = sorted({path for paths in BASELINE_CONTEXT_PATHS.values() for path in paths})
    blobs = {path: _git_blob(BASELINE_COMMIT, path) for path in unique_paths}
    for skill, expected_paths in BASELINE_CONTEXT_PATHS.items():
        entry = by_skill[skill]
        recorded_paths = entry.get("paths")
        if recorded_paths != list(expected_paths):
            raise ValueError(f"paths da baseline divergiram para {skill}")
        measured_bytes = sum(len(blobs[path]) for path in expected_paths)
        if entry.get("bytes") != measured_bytes:
            raise ValueError(f"bytes da baseline divergiram para {skill}")
        if entry.get("files") != len(expected_paths):
            raise ValueError(f"contagem de arquivos da baseline divergiu para {skill}")

    provenance = {
        "commit": BASELINE_COMMIT,
        "method": "git_show_explicit_safe_paths",
        "baseline_json_verified": True,
        "files": [
            {
                "path": path,
                "bytes": len(blobs[path]),
                "sha256": hashlib.sha256(blobs[path]).hexdigest(),
            }
            for path in unique_paths
        ],
        "claim_boundary": (
            "bytes brutos do commit-base em pathspecs explícitos; não mede tokens "
            "nem leitura efetiva do agente"
        ),
    }
    return by_skill, provenance


def _measure_context(
    baseline: dict[str, dict[str, Any]], before_source: dict[str, Any]
) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="bm-phase2-context-") as temp:
        root = ContextSkillAdoptionScenarios().make_repo(Path(temp))
        for skill, unit in CONTEXT_CASES:
            compiled = compile_context_pack(root, unit)
            pack_path = root / str(compiled["path"])
            verified = verify_context_pack(root, pack_path)
            if verified.get("unit") != unit:
                raise ValueError(f"pack verificado com unidade divergente: {unit}")

            before = baseline[skill]
            before_bytes = int(before["bytes"])
            before_files = int(before["files"])
            skill_bytes = (ROOT / "skills" / skill / "SKILL.md").stat().st_size
            pack_bytes = pack_path.stat().st_size
            sources = compiled.get("sources")
            if not isinstance(sources, list):
                raise ValueError(f"pack sem fontes enumeradas: {unit}")
            after_bytes = skill_bytes + pack_bytes
            reduction_bytes = before_bytes - after_bytes
            cases.append(
                {
                    "skill": skill,
                    "unit": unit,
                    "before_bytes": before_bytes,
                    "before_files": before_files,
                    "skill_bytes_after": skill_bytes,
                    "pack_bytes": pack_bytes,
                    "after_bytes": after_bytes,
                    "after_files": 2,
                    "pack_sources": len(sources),
                    "reduction_bytes": reduction_bytes,
                    "reduction_percent": round(
                        reduction_bytes * 100 / before_bytes, 2
                    ),
                }
            )
    return {
        "measurement": (
            "bytes de SKILL.md mais pack compilado em fixture de completude "
            "versionada pelo oráculo Python após o cutover Go"
        ),
        "measurement_backend": "python_oracle",
        "before_source": before_source,
        "default_max_bytes": DEFAULT_MAX_BYTES,
        "token_claim": "não medido; nenhuma alegação de redução de tokens",
        "cases": cases,
    }


def _materialize_git_paths(
    commit: str, paths: tuple[str, ...], destination: Path
) -> None:
    for path in paths:
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_git_blob(commit, path))


def _init_git_repo(root: Path) -> None:
    root.mkdir(parents=True)
    for args in (
        ("init", "-b", "main"),
        ("config", "user.name", "BM Phase 2 Metrics"),
        ("config", "user.email", "metrics@example.invalid"),
    ):
        completed = subprocess.run(
            ["git", *args], cwd=root, text=True, capture_output=True, check=False
        )
        if completed.returncode != 0:
            raise ValueError(completed.stderr.strip() or "git temporário falhou")


def _run_historical_cli(method_root: Path, repo: Path, *args: str) -> dict[str, Any]:
    completed = subprocess.run(
        [sys.executable, str(method_root / "scripts" / "bm.py"), *args],
        cwd=repo,
        env={
            **os.environ,
            "COLUMNS": "200",
            "PYTHONDONTWRITEBYTECODE": "1",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ValueError(
            f"oráculo histórico falhou ({completed.returncode}): {completed.stderr}"
        )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ValueError("oráculo histórico não retornou JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("oráculo histórico retornou payload não-objeto")
    return payload


def _docviva_current_tree(root: Path) -> dict[str, bytes]:
    current = root / ".bianchini" / "current"
    if not current.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(current.rglob("*"))
        if path.is_file()
    }


def _docviva_flow(
    flow: str, before: dict[str, bytes], after: dict[str, bytes]
) -> dict[str, Any]:
    created = sorted(set(after) - set(before))
    deleted = sorted(set(before) - set(after))
    altered = sorted(
        path for path in set(before) & set(after) if before[path] != after[path]
    )
    return {
        "flow": flow,
        "created": created,
        "altered": altered,
        "deleted": deleted,
        "changed_files": len(created) + len(altered) + len(deleted),
        "bytes_after": sum(len(content) for content in after.values()),
    }


def _verify_historical_flows(
    recorded: dict[str, Any], actual: list[dict[str, Any]], fixture_changed: int
) -> None:
    flows = recorded.get("flows")
    if not isinstance(flows, list) or len(flows) != 4:
        raise ValueError("baseline DocViva sem quatro fluxos registrados")
    for expected, measured in zip(flows[:3], actual):
        for field in (
            "flow",
            "created",
            "altered",
            "deleted",
            "changed_files",
            "bytes_after",
        ):
            if expected.get(field) != measured.get(field):
                raise ValueError(
                    f"baseline DocViva divergiu em {measured['flow']}.{field}"
                )
    if flows[3].get("changed_files") != fixture_changed:
        raise ValueError("baseline DocViva divergiu nas 12 fixtures iniciais")


def _verify_fixture_blob(path: str, content: bytes) -> None:
    try:
        fixture = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError(f"fixture histórica inválida: {path}") from error
    if not isinstance(fixture, dict):
        raise ValueError(f"fixture histórica não é objeto: {path}")
    candidates = list(fixture.get("initial_tree", {}))
    candidates.extend(fixture.get("expected", {}).get("files", {}))
    for value in candidates:
        candidate = Path(value)
        if candidate.is_absolute() or ".." in candidate.parts or ".planning" in candidate.parts:
            raise ValueError(f"fixture histórica contém path inseguro: {path}")
    if any(".planning" in str(token) for token in fixture.get("argv", [])):
        raise ValueError(f"fixture histórica referencia namespace proibido: {path}")


def _run_historical_fixtures(method_root: Path) -> dict[str, Any]:
    for path in BASELINE_FIXTURE_PATHS:
        _verify_fixture_blob(path, _git_blob(BASELINE_FIXTURE_COMMIT, path))
    _materialize_git_paths(
        BASELINE_FIXTURE_COMMIT,
        BASELINE_RUNNER_PATHS + BASELINE_FIXTURE_PATHS,
        method_root,
    )

    scripts_dir = str(method_root / "scripts")
    sys.path.insert(0, scripts_dir)
    previous_contract = sys.modules.pop("_cli_contract", None)
    try:
        runner_path = method_root / "scripts" / "run_cli_contract_fixtures.py"
        specification = importlib.util.spec_from_file_location(
            "bm_historical_cli_fixture_runner", runner_path
        )
        if specification is None or specification.loader is None:
            raise ValueError("não foi possível carregar o runner histórico")
        runner = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(runner)

        fixture_results: list[dict[str, Any]] = []
        original_tree = runner._tree
        for path in sorted(
            (method_root / "tests" / "fixtures" / "cli_contract").glob("*.json")
        ):
            captured: list[dict[str, bytes]] = []

            def capturing_tree(root: Path) -> dict[str, bytes]:
                captured.append(_docviva_current_tree(root))
                return original_tree(root)

            runner._tree = capturing_tree
            errors = runner.run_fixture(path, "python", None)
            if len(captured) != 2:
                raise ValueError(f"runner histórico não capturou before/after: {path.name}")
            before, after = captured
            changed = _docviva_flow(path.stem, before, after)["changed_files"]
            fixture_results.append(
                {"fixture": path.name, "passed": not errors, "changed_files": changed}
            )
            if errors:
                raise ValueError(f"fixture histórica divergiu ({path.name}): {errors}")
    finally:
        if previous_contract is not None:
            sys.modules["_cli_contract"] = previous_contract
        else:
            sys.modules.pop("_cli_contract", None)
        sys.path.remove(scripts_dir)

    return {
        "total": len(fixture_results),
        "passed": sum(1 for item in fixture_results if item["passed"]),
        "docviva_current_changed_files": sum(
            int(item["changed_files"]) for item in fixture_results
        ),
        "fixture_files": [item["fixture"] for item in fixture_results],
    }


def _reproduce_historical_docviva(recorded: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="bm-phase2-historical-") as temporary:
        method_root = Path(temporary) / "method"
        _materialize_git_paths(BASELINE_COMMIT, BASELINE_RUNTIME_PATHS, method_root)
        repo = Path(temporary) / "repo"
        _init_git_repo(repo)

        before_init = _docviva_current_tree(repo)
        _run_historical_cli(method_root, repo, "model", "init", "--repo", str(repo))
        after_init = _docviva_current_tree(repo)
        init_flow = _docviva_flow("model init em projeto novo", before_init, after_init)

        before_existing = _docviva_current_tree(repo)
        _run_historical_cli(method_root, repo, "model", "init", "--repo", str(repo))
        after_existing = _docviva_current_tree(repo)
        existing_flow = _docviva_flow(
            "model init em workspace existente", before_existing, after_existing
        )

        before_validate = _docviva_current_tree(repo)
        _run_historical_cli(
            method_root, repo, "model", "validate", "--repo", str(repo)
        )
        after_validate = _docviva_current_tree(repo)
        validate_flow = _docviva_flow(
            "model validate", before_validate, after_validate
        )

        fixtures = _run_historical_fixtures(method_root)
        flows = [init_flow, existing_flow, validate_flow]
        _verify_historical_flows(
            recorded, flows, int(fixtures["docviva_current_changed_files"])
        )
        return {
            "runtime_commit": BASELINE_COMMIT,
            "fixture_contract_commit": BASELINE_FIXTURE_COMMIT,
            "git_source_method": "git_show_explicit_safe_paths",
            "runtime_files_materialized": len(BASELINE_RUNTIME_PATHS),
            "runtime_paths": list(BASELINE_RUNTIME_PATHS),
            "fixture_runner_paths": list(BASELINE_RUNNER_PATHS),
            "flows": flows,
            "fixtures": fixtures,
            "baseline_json_verified": True,
            "provenance_note": (
                "runtime Python extraído do commit-base; runner e 12 contratos "
                "dourados extraídos do commit da Fase 0 que congelou a interface"
            ),
            "claim_boundary": (
                "reexecução estrutural em repositórios temporários; confirma bytes e "
                "mutações de DocViva do runtime-base contra o snapshot da Fase 0, "
                "não qualidade semântica nem que as fixtures já existiam no commit-base"
            ),
        }


def _measure_docviva(baseline_docviva: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="bm-phase2-docviva-") as temp:
        root = Path(temp)
        current = root / ".bianchini" / "current"
        specs = current / "specs"
        specs.mkdir(parents=True)
        (current / "ARCHITECTURE.md").write_text("# Atual\n", encoding="utf-8")
        model = current / "SYSTEM_MODEL.md"
        model.write_text("# Modelo atual\n", encoding="utf-8")

        before = snapshot_docviva(root)
        initial_bytes = sum(
            (root / relative).stat().st_size for relative in sorted(before)
        )

        fixed_mtime = 1_700_000_000_123_456_789
        os.utime(model, ns=(fixed_mtime, fixed_mtime))
        identical_write = write_if_changed(
            root,
            ".bianchini/current/SYSTEM_MODEL.md",
            model.read_bytes(),
        )
        preserved_mtime = model.stat().st_mtime_ns == fixed_mtime

        internal = verify_docviva_impact(
            root,
            before,
            {"kind": "internal", "outcome": "not_applicable"},
            [],
            "Alteração interna sem mudança observável na verdade atual.",
            False,
        )

        payment_path = ".bianchini/current/specs/payment.md"
        payment_content = "# Pagamento\n\nPIX obrigatório.\n"
        if not write_if_changed(root, payment_path, payment_content):
            raise ValueError("fixture comportamental não criou o artefato DocViva")
        behavioral = verify_docviva_impact(
            root,
            before,
            {"kind": "behavioral", "outcome": "updated"},
            [payment_path],
            "O contrato observável de pagamento mudou.",
            True,
        )

        return {
            "measurement": "snapshots SHA-256 e mtimes em workspace temporário",
            "historical_baseline": _reproduce_historical_docviva(baseline_docviva),
            "initial_files": len(before),
            "initial_bytes": initial_bytes,
            "identical_write_returned": identical_write,
            "identical_write_preserved_mtime": preserved_mtime,
            "internal_not_applicable_changed_files": len(internal["changed"]),
            "behavioral_updated_files": behavioral["changed"],
            "behavioral_artifact_bytes": len(payment_content.encode("utf-8")),
            "claim_boundary": (
                "medição estrutural; a revisão humana continua responsável pela "
                "semântica textual"
            ),
        }


def measure() -> dict[str, Any]:
    baseline_payload = json.loads(BASELINE.read_text(encoding="utf-8"))
    baseline_context, before_source = _verify_baseline_context(baseline_payload)
    baseline_docviva = baseline_payload.get("docviva")
    if not isinstance(baseline_docviva, dict):
        raise ValueError("baseline sem DocViva versionada")
    return {
        "schema_version": 1,
        "phase": 2,
        "measured_at": str(baseline_payload["measured_at"])[:10],
        "remeasured_after_audit": True,
        "remeasured_after_go_cutover": True,
        "measurement_backend": "python_oracle",
        "context": _measure_context(baseline_context, before_source),
        "docviva": _measure_docviva(baseline_docviva),
        "evidence": [
            "scripts/measure_phase2_context_docviva.py",
            "tests/test_phase2_metrics.py",
            "tests/test_context_pack.py",
            "tests/test_context_cli.py",
            "tests/test_context_skill_adoption.py",
            "tests/test_docviva.py",
            "tests/test_method_v04_cli.py",
        ],
    }


def render() -> bytes:
    return (json.dumps(measure(), ensure_ascii=False, indent=2) + "\n").encode(
        "utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=REPORT)
    args = parser.parse_args()

    content = render()
    if args.check:
        if not args.output.is_file() or args.output.read_bytes() != content:
            print(
                "metricas da Fase 2 divergentes; execute "
                "python3 scripts/measure_phase2_context_docviva.py",
                file=sys.stderr,
            )
            return 1
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
