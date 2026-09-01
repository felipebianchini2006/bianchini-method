"""Gates executáveis do backend Go explicitamente experimental."""

from __future__ import annotations

import hashlib
import json
import os
import re
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
    def test_external_go_modules_are_reconciled_with_distributed_notices(self) -> None:
        go_mod = (ROOT / "go.mod").read_text(encoding="utf-8")
        external_modules = re.findall(
            r"(?m)^\s*(?:require\s+)?(golang\.org/\S+)\s+v\S+", go_mod
        )
        notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        self.assertTrue(external_modules)
        for module in external_modules:
            with self.subTest(module=module):
                self.assertIn(module, notices)
        self.assertIn("Copyright 2009 The Go Authors", notices)
        self.assertIn("Redistribution and use in source and binary forms", notices)

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

    def test_go_risk_path_policy_matches_python_oracle(self) -> None:
        cases = (
            "pyproject.toml",
            "src/contracts/payments.proto",
            "src/webhooks/delivery.py",
            "db/migrations/0001.sql",
            "docs/payments/example.md",
            "api/openapi.yaml",
        )
        with tempfile.TemporaryDirectory(prefix="bm-go-risk-parity-") as temp:
            binary = Path(temp) / "bm-preview"
            built = run("go", "build", "-trimpath", "-o", str(binary), "./cmd/bm-preview")
            self.assertEqual(built.returncode, 0, built.stderr)
            for changed_file in cases:
                with self.subTest(changed_file=changed_file):
                    argv = ("direct", "classify", "--changed-file", changed_file)
                    python = run("python3", str(ROOT / "scripts" / "bm.py"), *argv)
                    go = run(str(binary), *argv)
                    self.assertEqual(python.returncode, 0, python.stderr)
                    self.assertEqual(go.returncode, 0, go.stderr)
                    self.assertEqual(json.loads(go.stdout), json.loads(python.stdout))

    def test_go_and_python_reject_unsafe_risk_paths_identically(self) -> None:
        changed_files = ("src/cafe\u0301.py", "src/.planning/x")
        with tempfile.TemporaryDirectory(prefix="bm-go-risk-unicode-") as temp:
            binary = Path(temp) / "bm-preview"
            built = run("go", "build", "-trimpath", "-o", str(binary), "./cmd/bm-preview")
            self.assertEqual(built.returncode, 0, built.stderr)
            for changed_file in changed_files:
                with self.subTest(changed_file=changed_file):
                    argv = ("direct", "classify", "--changed-file", changed_file)
                    python = run("python3", str(ROOT / "scripts" / "bm.py"), *argv)
                    go = run(str(binary), *argv)
                    self.assertEqual(go.returncode, python.returncode)
                    self.assertEqual(go.stdout, python.stdout)
                    self.assertEqual(go.stderr, python.stderr)

    def test_go_policy_matches_python_oracle(self) -> None:
        cases = (
            ("--profile", "lean", "--risk", "low", "--change", "visual"),
            (
                "--profile", "standard", "--risk", "medium",
                "--change", "business-rule", "--manual-pdf", "scope",
                "--manual-in-scope", "--round", "1", "--risk-seam",
                "payments-ledger", "--seam-round", "3",
            ),
            (
                "--profile", "full", "--risk", "critical", "--round", "1",
                "--structural-finding", "crash_window",
                "--structural-finding", "toctou",
            ),
        )
        with tempfile.TemporaryDirectory(prefix="bm-go-policy-parity-") as temp:
            binary = Path(temp) / "bm-preview"
            built = run("go", "build", "-trimpath", "-o", str(binary), "./cmd/bm-preview")
            self.assertEqual(built.returncode, 0, built.stderr)
            for arguments in cases:
                with self.subTest(arguments=arguments):
                    argv = ("policy", *arguments)
                    python = run("python3", str(ROOT / "scripts" / "bm.py"), *argv)
                    go = run(str(binary), *argv)
                    self.assertEqual(python.returncode, 0, python.stderr)
                    self.assertEqual(go.returncode, python.returncode, go.stderr)
                    self.assertEqual(json.loads(go.stdout), json.loads(python.stdout))
                    self.assertEqual(go.stderr, python.stderr)

    def test_go_adapter_render_and_install_match_python_oracle(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bm-go-adapter-parity-") as temp:
            base = Path(temp)
            binary = base / "bm-preview"
            built = run("go", "build", "-trimpath", "-o", str(binary), "./cmd/bm-preview")
            self.assertEqual(built.returncode, 0, built.stderr)
            for host in ("generic", "codex", "claude-compatible"):
                with self.subTest(host=host):
                    argv = ("adapter", "render", "--host", host)
                    python = run("python3", str(ROOT / "scripts" / "bm.py"), *argv)
                    go = run(str(binary), *argv)
                    self.assertEqual(go.returncode, python.returncode)
                    self.assertEqual(json.loads(go.stdout), json.loads(python.stdout))
                    self.assertEqual(go.stderr, python.stderr)

            python_repo = base / "python-repo"
            go_repo = base / "go-repo"
            python_repo.mkdir()
            go_repo.mkdir()
            foreign = b"# Regras estrangeiras\n\nPreservar.\n"
            for repo in (python_repo, go_repo):
                target = repo / "AGENTS.md"
                target.write_bytes(foreign)
                target.chmod(0o640)
            python = run(
                "python3", str(ROOT / "scripts" / "bm.py"), "adapter", "install",
                "--host", "generic", "--repo", str(python_repo),
            )
            go = run(
                str(binary), "adapter", "install", "--host", "generic",
                "--repo", str(go_repo),
            )
            self.assertEqual(go.returncode, python.returncode)
            self.assertEqual(json.loads(go.stdout), json.loads(python.stdout))
            self.assertEqual(go.stderr, python.stderr)
            self.assertEqual(
                (go_repo / "AGENTS.md").read_bytes(),
                (python_repo / "AGENTS.md").read_bytes(),
            )
            self.assertEqual(
                (go_repo / "AGENTS.md").stat().st_mode & 0o777,
                (python_repo / "AGENTS.md").stat().st_mode & 0o777,
            )

    def test_go_validate_state_matches_python_oracle(self) -> None:
        with tempfile.TemporaryDirectory(prefix="bm-go-state-parity-") as temp:
            base = Path(temp)
            binary = base / "bm-preview"
            built = run("go", "build", "-trimpath", "-o", str(binary), "./cmd/bm-preview")
            self.assertEqual(built.returncode, 0, built.stderr)
            cases = (
                (str(ROOT / "tests" / "fixtures" / "project-state-v2.json"),),
                (str(base / "missing-state.json"),),
            )
            for arguments in cases:
                with self.subTest(arguments=arguments):
                    argv = ("validate-state", *arguments)
                    python = run("python3", str(ROOT / "scripts" / "bm.py"), *argv)
                    go = run(str(binary), *argv)
                    self.assertEqual(go.returncode, python.returncode)
                    self.assertEqual(go.stderr, python.stderr)
                    if python.stdout:
                        self.assertEqual(json.loads(go.stdout), json.loads(python.stdout))
                    else:
                        self.assertEqual(go.stdout, python.stdout)

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
