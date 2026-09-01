"""Reprodutibilidade do help estático usado pelo kernel Go."""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSET = ROOT / "internal" / "gokernel" / "assets" / "cli-help.json"


class CliHelpScenarios(unittest.TestCase):
    def test_generated_help_matches_python_oracle_byte_for_byte(self) -> None:
        checked = subprocess.run(
            ["python3", str(ROOT / "scripts" / "generate_cli_help.py"), "--check"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertIn("CLI_HELP_OK: 77 paths", checked.stdout)

    def test_asset_covers_root_commands_and_actions(self) -> None:
        asset = json.loads(ASSET.read_text(encoding="utf-8"))
        contract = json.loads(
            (ROOT / "contracts" / "cli-surfaces.json").read_text(encoding="utf-8")
        )
        expected = {"", *contract["commands"]}
        expected.update(
            f"{surface['command']} {surface['action']}"
            for surface in contract["surfaces"]
            if surface["action"] is not None
        )
        self.assertEqual(set(asset["help"]), expected)
        self.assertTrue(all(text.endswith("\n") for text in asset["help"].values()))


if __name__ == "__main__":
    unittest.main()
