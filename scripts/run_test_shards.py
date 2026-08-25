#!/usr/bin/env python3
"""Executa a suíte por classe para liberar recursos entre grupos de cenários."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
SHARDS = (
    "MethodV04Scenarios",
    "PackageIntegrityTests",
    "RoutingAndStateScenarios",
    "SnapshotScenarios",
    "PlanningQualityScenarios",
    "PlanningStabilityScenarios",
    "ContextEfficiencyScenarios",
    "AdaptivePolicyScenarios",
    "BehavioralProjectScenarios",
    "AgentContractScenarios",
    "SkillBehaviorContracts",
)

REVIEW_SHARDS = (
    "ContextEfficiencyReviewScenarios",
)

CORE_04_SHARDS = (
    "MethodWorkspaceTests",
    "ProjectModelTests",
    "CoherenceTests",
)

SELF_UPDATE_SHARDS = (
    "SelfUpdateScenarios",
)

LINEAGE_SHARDS = (
    "LineageResetPackageScenarios",
    "LineageResetGitScenarios",
)

CODEX_SHARDS = (
    "CodexOverlayPackageTests",
    "ReviewGuardScenarios",
    "CodexInstallerScenarios",
)


def run_shard(module: str, shard: str, environment: dict[str, str]) -> int:
    print(f"\n=== {shard} ===", file=sys.stderr, flush=True)
    completed = subprocess.run(
        [sys.executable, "-m", "unittest", f"{module}.{shard}", "-v"],
        cwd=TESTS,
        env=environment,
        check=False,
    )
    return completed.returncode


def main() -> int:
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    for shard in SHARDS:
        module = "test_method_v04_cli" if shard == "MethodV04Scenarios" else "test_method_package"
        if run_shard(module, shard, environment) != 0:
            return 1
    for shard in REVIEW_SHARDS:
        if run_shard("test_context_efficiency_review", shard, environment) != 0:
            return 1
    for shard in CORE_04_SHARDS:
        if run_shard("test_bm_core_modules", shard, environment) != 0:
            return 1
    for shard in SELF_UPDATE_SHARDS:
        if run_shard("test_self_update", shard, environment) != 0:
            return 1
    for shard in LINEAGE_SHARDS:
        if run_shard("test_update_lineage_reset", shard, environment) != 0:
            return 1
    for shard in CODEX_SHARDS:
        if run_shard("test_codex_overlay", shard, environment) != 0:
            return 1
    total = (
        len(SHARDS)
        + len(REVIEW_SHARDS)
        + len(CORE_04_SHARDS)
        + len(SELF_UPDATE_SHARDS)
        + len(LINEAGE_SHARDS)
        + len(CODEX_SHARDS)
    )
    print(f"\n{total} shards aprovados.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
