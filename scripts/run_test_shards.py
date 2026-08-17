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
    "PackageIntegrityTests",
    "RoutingAndStateScenarios",
    "SnapshotScenarios",
    "PlanningQualityScenarios",
    "PlanningStabilityScenarios",
    "AdaptivePolicyScenarios",
    "WorkspaceAndArtifactScenarios",
    "BehavioralProjectScenarios",
    "DirectExecutionScenarios",
    "AgentContractScenarios",
    "SkillBehaviorContracts",
)

CODEX_SHARDS = (
    "CodexOverlayPackageTests",
    "ReviewGuardScenarios",
    "CodexInstallerScenarios",
)


def main() -> int:
    environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    for shard in SHARDS:
        print(f"\n=== {shard} ===", file=sys.stderr, flush=True)
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", f"test_method_package.{shard}", "-v"],
            cwd=TESTS,
            env=environment,
            check=False,
        )
        if completed.returncode != 0:
            return completed.returncode
    for shard in CODEX_SHARDS:
        print(f"\n=== {shard} ===", file=sys.stderr, flush=True)
        completed = subprocess.run(
            [sys.executable, "-m", "unittest", f"test_codex_overlay.{shard}", "-v"],
            cwd=TESTS,
            env=environment,
            check=False,
        )
        if completed.returncode != 0:
            return completed.returncode
    print(f"\n{len(SHARDS) + len(CODEX_SHARDS)} shards aprovados.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
