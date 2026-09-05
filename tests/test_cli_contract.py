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
    def test_every_registered_public_surface_has_golden_fixture(self) -> None:
        payload = json.loads(CONTRACT.read_text(encoding="utf-8"))
        positive = payload["surfaces"]
        negative = payload["negative_surfaces"]
        surfaces = [*positive, *negative]
        missing = sorted(
            surface["id"]
            for surface in surfaces
            if not surface.get("fixtures")
        )
        self.assertEqual(missing, [])

        fixture_root = ROOT / "tests" / "fixtures" / "cli_contract"
        declared_fixtures = {
            fixture_name
            for surface in surfaces
            for fixture_name in surface["fixtures"]
        }
        self.assertEqual(
            declared_fixtures,
            {path.stem for path in fixture_root.glob("*.json")},
        )

        for surface in surfaces:
            observed_steps: list[dict[str, object]] = []
            for fixture_name in surface["fixtures"]:
                fixture_path = fixture_root / (fixture_name + ".json")
                fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
                fixture_surfaces = set(
                    fixture.get("surfaces", [fixture.get("surface")])
                )
                self.assertIn(surface["id"], fixture_surfaces, fixture_name)
                steps = fixture.get("steps") or [
                    {
                        "surface": fixture.get("surface"),
                        "argv": fixture["argv"],
                        "expected": fixture["expected"],
                    }
                ]
                observed_steps.extend(
                    step
                    for step in steps
                    if step.get("surface") == surface["id"]
                    and "expected" in step
                )
            self.assertTrue(observed_steps, surface["id"])

            for step in observed_steps:
                expected_prefix = [surface.get("command"), surface.get("action")]
                expected_prefix = [item for item in expected_prefix if item is not None]
                if "argv" in surface:
                    self.assertEqual(step["argv"], surface["argv"])
                    continue
                self.assertEqual(
                    step["argv"][: len(expected_prefix)],
                    expected_prefix,
                    surface["id"],
                )

            has_success = any(
                step["expected"]["exit_code"] == 0 for step in observed_steps
            )
            if surface in positive and not has_success:
                if surface["id"] == "direct.reopen":
                    self.assertEqual(surface["behavior"], "parser_terminal_error")
                else:
                    self.assertTrue(
                        surface.get("golden_success_exception"),
                        f"superfície positiva sem golden de sucesso: {surface['id']}",
                    )

    def test_canonical_registry_matches_parser_dispatch_and_skill_consumers(self) -> None:
        verified = run_script("verify_cli_contract.py")
        self.assertEqual(verified.returncode, 0, verified.stderr)
        result = json.loads(verified.stdout)
        self.assertTrue(result["valid"])
        self.assertEqual(result["unregistered_skill_surfaces"], [])
        self.assertEqual(result["command_count"], 32)
        self.assertEqual(result["surface_count"], 65)
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
        self.assertEqual(
            completed.returncode, 0,
            f"Relatório das fixtures:\n{completed.stdout}\n{completed.stderr}",
        )
        result = json.loads(completed.stdout)
        self.assertEqual(result["engine"], "python")
        self.assertEqual(result["failed"], 0)
        fixture_count = len(
            list((ROOT / "tests" / "fixtures" / "cli_contract").glob("*.json"))
        )
        self.assertEqual(result["total"], fixture_count)
        self.assertEqual(result["passed"], fixture_count)
        self.assertEqual(result["skipped"], 0)

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
