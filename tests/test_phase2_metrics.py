"""Reprodutibilidade das metricas de contexto e DocViva da Fase 2."""

from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "evolution-0.4.7" / "phase2-context-docviva.json"
SCRIPT = ROOT / "scripts" / "measure_phase2_context_docviva.py"


def load_measurement_module():
    specification = importlib.util.spec_from_file_location(
        "phase2_metrics_measurement", SCRIPT
    )
    if specification is None or specification.loader is None:
        raise AssertionError(f"não foi possível carregar {SCRIPT}")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def run_measurement(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


class Phase2MetricsScenarios(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.measurement = load_measurement_module()

    def test_versioned_report_is_reproducible_byte_for_byte(self) -> None:
        checked = run_measurement("--check")
        self.assertEqual(checked.returncode, 0, checked.stderr)

        with tempfile.TemporaryDirectory() as temp:
            generated = Path(temp) / "phase2-context-docviva.json"
            rendered = run_measurement("--output", str(generated))
            self.assertEqual(rendered.returncode, 0, rendered.stderr)
            self.assertEqual(generated.read_bytes(), REPORT.read_bytes())

    def test_check_fails_when_versioned_metrics_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            divergent = Path(temp) / "phase2-context-docviva.json"
            payload = json.loads(REPORT.read_text(encoding="utf-8"))
            payload["context"]["cases"][0]["pack_bytes"] += 1
            divergent.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            checked = run_measurement("--check", "--output", str(divergent))

            self.assertEqual(checked.returncode, 1)
            self.assertIn("metricas da Fase 2 divergentes", checked.stderr)

    def test_before_context_is_recomputed_from_base_commit(self) -> None:
        payload = self.measurement.measure()
        source = payload["context"]["before_source"]

        self.assertEqual(source["commit"], self.measurement.BASELINE_COMMIT)
        self.assertEqual(source["method"], "git_show_explicit_safe_paths")
        self.assertTrue(source["baseline_json_verified"])
        self.assertEqual(len(source["files"]), 7)
        self.assertTrue(all(item["sha256"] for item in source["files"]))

    def test_before_context_fails_closed_when_baseline_bytes_drift(self) -> None:
        payload = json.loads(self.measurement.BASELINE.read_text(encoding="utf-8"))
        payload["skill_context"][0]["bytes"] += 1

        with self.assertRaisesRegex(ValueError, "bytes da baseline divergiram"):
            self.measurement._verify_baseline_context(payload)

    def test_docviva_historical_claims_are_reexecuted(self) -> None:
        payload = self.measurement.measure()
        historical = payload["docviva"]["historical_baseline"]

        self.assertEqual(
            historical["runtime_commit"], self.measurement.BASELINE_COMMIT
        )
        self.assertEqual(
            historical["fixture_contract_commit"],
            self.measurement.BASELINE_FIXTURE_COMMIT,
        )
        self.assertEqual(historical["fixtures"]["total"], 12)
        self.assertEqual(historical["fixtures"]["passed"], 12)
        self.assertEqual(
            historical["fixtures"]["docviva_current_changed_files"], 0
        )
        self.assertEqual(
            [flow["changed_files"] for flow in historical["flows"]], [2, 0, 0]
        )


if __name__ == "__main__":
    unittest.main()
