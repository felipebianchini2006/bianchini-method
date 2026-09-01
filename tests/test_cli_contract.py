"""Contrato executável das superfícies públicas do Bianchini Method."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts" / "cli-surfaces.json"
DOCUMENT = ROOT / "docs" / "cli-contract.md"
BASELINE = ROOT / "reports" / "evolution-0.4.7" / "baseline.json"


def run_script(name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(ROOT / "scripts" / name), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


class CliContractScenarios(unittest.TestCase):
    def test_canonical_registry_matches_parser_dispatch_and_skill_consumers(self) -> None:
        verified = run_script("verify_cli_contract.py")
        self.assertEqual(verified.returncode, 0, verified.stderr)
        result = json.loads(verified.stdout)
        self.assertTrue(result["valid"])
        self.assertEqual(result["unregistered_skill_surfaces"], [])
        self.assertEqual(result["command_count"], 31)
        self.assertEqual(result["surface_count"], 57)
        self.assertEqual(result["negative_surface_count"], 4)

    def test_generated_document_is_reproducible_byte_for_byte(self) -> None:
        checked = run_script("generate_cli_contract.py", "--check")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        with tempfile.TemporaryDirectory() as temp:
            generated = Path(temp) / "cli-contract.md"
            rendered = run_script(
                "generate_cli_contract.py", "--output", str(generated)
            )
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            self.assertEqual(generated.read_bytes(), DOCUMENT.read_bytes())

    def test_golden_behavior_fixtures_pass_on_python_oracle(self) -> None:
        completed = run_script(
            "run_cli_contract_fixtures.py", "--engine", "python"
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["engine"], "python")
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["passed"], 12)

    def test_phase0_baseline_metrics_are_measured_not_estimated(self) -> None:
        payload = json.loads(BASELINE.read_text(encoding="utf-8"))
        self.assertEqual(
            payload["base_commit"],
            "7c9fa23f524623f3360ebae579048e1765095220",
        )
        self.assertEqual(payload["test_shards"], 22)
        self.assertEqual(
            payload["plan_sha256"],
            "aa170b8054c48a07f2787f7434575731f0302b9328cbae7e83998bd10ea2eacc",
        )
        self.assertGreaterEqual(len(payload["command_timings"]), 3)
        self.assertGreaterEqual(len(payload["skill_context"]), 5)
        for timing in payload["command_timings"]:
            self.assertGreater(timing["samples"], 0)
            self.assertGreaterEqual(timing["median_ms"], 0)
        for context in payload["skill_context"]:
            self.assertGreater(context["files"], 0)
            self.assertGreater(context["bytes"], 0)
        self.assertIn("docviva", payload)
        self.assertIn("persistent_artifacts", payload)


if __name__ == "__main__":
    unittest.main()
