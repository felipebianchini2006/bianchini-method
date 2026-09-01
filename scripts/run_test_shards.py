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
    "ScopeIntakeScenarios",
    "PackageIntegrityTests",
    "StateValidationScenarios",
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

CONTRACT_SHARDS = (
    "CliContractScenarios",
)

PHASE1_SHARDS = (
    ("test_spec_package", "SpecPackageScenarios"),
    ("test_close_recovery", "CloseRecoveryScenarios"),
)

PHASE2_SHARDS = (
    ("test_context_pack", "ContextPackScenarios"),
    ("test_context_cli", "ContextCliScenarios"),
    ("test_context_skill_adoption", "ContextSkillAdoptionScenarios"),
    ("test_docviva", "DocVivaScenarios"),
    ("test_phase2_metrics", "Phase2MetricsScenarios"),
)

PHASE3_SHARDS = (
    ("test_risk_floor", "RiskFloorScenarios"),
    ("test_next_wave", "NextWaveScenarios"),
    ("test_host_adapters", "HostAdapterScenarios"),
    ("test_phase3_cli", "Phase3CliScenarios"),
)

PHASE4_SHARDS = (
    ("test_learning", "GovernedLearningScenarios"),
)

PHASE5_SHARDS = (
    ("test_go_preview", "GoBackendScenarios"),
    ("test_cli_help", "CliHelpScenarios"),
)

FULL_JOURNEY_SHARDS = (
    ("test_full_journey", "FullJourneyScenarios"),
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
        module = (
            "test_method_v04_cli"
            if shard in {"MethodV04Scenarios", "ScopeIntakeScenarios"}
            else "test_method_package"
        )
        if run_shard(module, shard, environment) != 0:
            return 1
    for shard in REVIEW_SHARDS:
        if run_shard("test_context_efficiency_review", shard, environment) != 0:
            return 1
    for shard in CORE_04_SHARDS:
        if run_shard("test_bm_core_modules", shard, environment) != 0:
            return 1
    for shard in CONTRACT_SHARDS:
        if run_shard("test_cli_contract", shard, environment) != 0:
            return 1
    for module, shard in PHASE1_SHARDS:
        if run_shard(module, shard, environment) != 0:
            return 1
    for module, shard in PHASE2_SHARDS:
        if run_shard(module, shard, environment) != 0:
            return 1
    for module, shard in PHASE3_SHARDS:
        if run_shard(module, shard, environment) != 0:
            return 1
    for module, shard in PHASE4_SHARDS:
        if run_shard(module, shard, environment) != 0:
            return 1
    for module, shard in PHASE5_SHARDS:
        if run_shard(module, shard, environment) != 0:
            return 1
    for module, shard in FULL_JOURNEY_SHARDS:
        if run_shard(module, shard, environment) != 0:
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
        + len(CONTRACT_SHARDS)
        + len(PHASE1_SHARDS)
        + len(PHASE2_SHARDS)
        + len(PHASE3_SHARDS)
        + len(PHASE4_SHARDS)
        + len(PHASE5_SHARDS)
        + len(FULL_JOURNEY_SHARDS)
        + len(SELF_UPDATE_SHARDS)
        + len(LINEAGE_SHARDS)
        + len(CODEX_SHARDS)
    )
    print(f"\n{total} shards aprovados.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
