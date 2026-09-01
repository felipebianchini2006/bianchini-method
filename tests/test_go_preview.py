"""Gates executáveis do backend Go explicitamente experimental."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GO_ENTRYPOINT = ROOT / "cmd" / "bm-preview"


def run(*argv: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


class GoPreviewScenarios(unittest.TestCase):
    def test_go_unit_suite_is_green(self) -> None:
        completed = run("go", "test", "./...")
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_preview_has_no_python_fallback_and_reports_its_backend(self) -> None:
        sources = "\n".join(
            path.read_text(encoding="utf-8")
            for root in (ROOT / "cmd", ROOT / "internal")
            for path in sorted(root.rglob("*.go"))
        )
        self.assertNotIn("os/exec", sources)
        self.assertNotIn("exec.Command", sources)
        self.assertNotIn("scripts/bm.py", sources)
        with tempfile.TemporaryDirectory(prefix="bm-go-preview-") as temp:
            binary = Path(temp) / "bm-preview"
            built = run("go", "build", "-trimpath", "-o", str(binary), "./cmd/bm-preview")
            self.assertEqual(built.returncode, 0, built.stderr)
            versioned = run(str(binary), "version", "--json", env={"PATH": ""})
            self.assertEqual(versioned.returncode, 0, versioned.stderr)
            payload = json.loads(versioned.stdout)
            self.assertEqual(payload["engine"], "go-preview")
            self.assertEqual(payload["contract_version"], "0.4")
            self.assertFalse(payload["official"])
            self.assertGreater(len(payload["implemented_surfaces"]), 0)

    def test_all_phase0_fixtures_have_byte_level_parity(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bm-go-parity-") as temp:
            binary = Path(temp) / "bm-preview"
            built = run("go", "build", "-trimpath", "-o", str(binary), "./cmd/bm-preview")
            self.assertEqual(built.returncode, 0, built.stderr)
            parity = run(
                "python3",
                str(ROOT / "scripts" / "run_cli_contract_fixtures.py"),
                "--engine",
                "go",
                "--binary",
                str(binary),
            )
            self.assertEqual(parity.returncode, 0, parity.stdout + parity.stderr)
            payload = json.loads(parity.stdout)
            self.assertEqual(payload["passed"], 12)
            self.assertEqual(payload["failed"], 0)

    def test_preview_cross_compiles_for_required_matrix(self) -> None:
        targets = (
            ("linux", "amd64"),
            ("linux", "arm64"),
            ("darwin", "amd64"),
            ("darwin", "arm64"),
            ("windows", "amd64"),
        )
        with tempfile.TemporaryDirectory(prefix="bm-go-matrix-") as temp:
            digests: dict[str, str] = {}
            for goos, goarch in targets:
                suffix = ".exe" if goos == "windows" else ""
                target = Path(temp) / f"bm-preview-{goos}-{goarch}{suffix}"
                environment = {
                    **os.environ,
                    "CGO_ENABLED": "0",
                    "GOOS": goos,
                    "GOARCH": goarch,
                }
                built = run(
                    "go",
                    "build",
                    "-trimpath",
                    "-o",
                    str(target),
                    "./cmd/bm-preview",
                    env=environment,
                )
                self.assertEqual(built.returncode, 0, built.stderr)
                digests[f"{goos}-{goarch}"] = hashlib.sha256(target.read_bytes()).hexdigest()
            self.assertEqual(set(digests), {f"{os_}-{arch}" for os_, arch in targets})
            self.assertEqual(len(set(digests.values())), len(targets))


if __name__ == "__main__":
    unittest.main()
