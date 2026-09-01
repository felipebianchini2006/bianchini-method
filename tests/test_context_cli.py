from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BM = ROOT / "skills/_shared/scripts/bm.py"
TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

from test_context_pack import ContextPackScenarios  # noqa: E402


class ContextCliScenarios(unittest.TestCase):
    def run_bm(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(BM), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_context_pack_and_verify_are_public_and_json_observable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = ContextPackScenarios().make_repo(Path(temp))
            packed = self.run_bm(
                "context", "pack", "--repo", str(repo), "--unit", "C001/P01/T01"
            )
            self.assertEqual(packed.returncode, 0, packed.stderr)
            payload = json.loads(packed.stdout)
            self.assertEqual(payload["unit"], "C001/P01/T01")
            self.assertFalse(payload["cache_hit"])

            verified = self.run_bm(
                "context", "verify", "--repo", str(repo), "--path", payload["path"]
            )
            self.assertEqual(verified.returncode, 0, verified.stderr)
            verified_payload = json.loads(verified.stdout)
            self.assertTrue(verified_payload["cache_hit"])
            self.assertEqual(verified_payload["digest"], payload["digest"])

    def test_context_pack_failure_keeps_stable_error_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = ContextPackScenarios().make_repo(Path(temp))
            failed = self.run_bm(
                "context", "pack", "--repo", str(repo), "--unit", "invalid"
            )
            self.assertEqual(failed.returncode, 3)
            self.assertIn("PACK_INCOMPLETE", failed.stderr)


if __name__ == "__main__":
    unittest.main()
