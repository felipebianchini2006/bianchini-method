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

    def test_go_model_init_validate_and_change_match_python_oracle(self) -> None:
        def frontmatter(path: Path) -> dict[str, object]:
            return json.loads(path.read_text(encoding="utf-8").split("---", 2)[1])

        with tempfile.TemporaryDirectory(prefix="bm-go-model-parity-") as temp:
            base = Path(temp)
            binary = base / "bm-preview"
            built = run("go", "build", "-trimpath", "-o", str(binary), "./cmd/bm-preview")
            self.assertEqual(built.returncode, 0, built.stderr)
            python_repo = base / "python-repo"
            go_repo = base / "go-repo"
            for repo in (python_repo, go_repo):
                initialized = run("git", "init", str(repo))
                self.assertEqual(initialized.returncode, 0, initialized.stderr)

            python = run(
                "python3", str(ROOT / "scripts" / "bm.py"),
                "model", "init", "--repo", str(python_repo),
            )
            go = run(str(binary), "model", "init", "--repo", str(go_repo))
            self.assertEqual(go.returncode, python.returncode)
            self.assertEqual(go.stderr, python.stderr)
            python_result = json.loads(python.stdout)
            go_result = json.loads(go.stdout)
            for payload in (python_result, go_result):
                payload.pop("workspace")
            self.assertEqual(go_result, python_result)
            for relative in (
                ".bianchini/.gitignore", ".bianchini/PROJECT.md",
                ".bianchini/current/ARCHITECTURE.md",
                ".bianchini/current/SYSTEM_MODEL.md",
                ".bianchini/current/specs/MANIFEST.json",
                ".bianchini/debug/KNOWLEDGE.md",
            ):
                self.assertEqual(
                    (go_repo / relative).read_bytes(),
                    (python_repo / relative).read_bytes(),
                    relative,
                )
            python_state = frontmatter(python_repo / ".bianchini/STATE.md")
            go_state = frontmatter(go_repo / ".bianchini/STATE.md")
            python_state.pop("updated_at")
            go_state.pop("updated_at")
            self.assertEqual(go_state, python_state)

            python_validate = run(
                "python3", str(ROOT / "scripts" / "bm.py"),
                "model", "validate", "--repo", str(python_repo),
            )
            go_validate = run(
                str(binary), "model", "validate", "--repo", str(go_repo),
            )
            self.assertEqual(go_validate.returncode, python_validate.returncode)
            self.assertEqual(go_validate.stderr, python_validate.stderr)
            python_valid = json.loads(python_validate.stdout)
            go_valid = json.loads(go_validate.stdout)
            for payload in (python_valid, go_valid):
                payload.pop("state")
                payload.pop("system_model")
            self.assertEqual(go_valid, python_valid)

            python_change = run(
                "python3", str(ROOT / "scripts" / "bm.py"), "model", "init",
                "--repo", str(python_repo), "--change", "Checkout seguro",
            )
            go_change = run(
                str(binary), "model", "init", "--repo", str(go_repo),
                "--change", "Checkout seguro",
            )
            self.assertEqual(go_change.returncode, python_change.returncode)
            self.assertEqual(go_change.stderr, python_change.stderr)
            python_changed = json.loads(python_change.stdout)
            go_changed = json.loads(go_change.stdout)
            for payload in (python_changed, go_changed):
                payload.pop("path")
            self.assertEqual(go_changed, python_changed)
            change = str(go_changed["change"])
            for relative in (
                "SCOPE.md", "RESEARCH.md", "ARCHITECTURE.md", "SYSTEM_MODEL.md",
                "ROADMAP.md", "SUMMARY.md", "specs/MANIFEST.json",
            ):
                self.assertEqual(
                    (go_repo / ".bianchini/changes" / change / relative).read_bytes(),
                    (python_repo / ".bianchini/changes" / change / relative).read_bytes(),
                    relative,
                )
            python_coherence = frontmatter(
                python_repo / ".bianchini/changes" / change / "COHERENCE.md"
            )
            go_coherence = frontmatter(
                go_repo / ".bianchini/changes" / change / "COHERENCE.md"
            )
            python_coherence.pop("updated_at")
            go_coherence.pop("updated_at")
            self.assertEqual(go_coherence, python_coherence)

            expected_model = """---
schema_version: 1
modules: []
interfaces: []
capabilities: []
contracts:
  - id: checkout_ready
    owner: payments
ownership: []
data: []
integrations: []
journeys: []
invariants: []
effects: []
---
# Modelo esperado
"""
            plan = """---
id: P01
model_delta:
  contracts:
    add:
      - id: checkout_ready
        owner: payments
---
# Plano
"""
            coherence = """---
{"schema_version":1,"planning_contract":1,"status":"pending"}
---
# Coerencia
"""
            for repo in (python_repo, go_repo):
                directory = repo / ".bianchini" / "changes" / change
                (directory / "SYSTEM_MODEL.md").write_text(
                    expected_model, encoding="utf-8"
                )
                (directory / "plans" / "P01.md").write_text(plan, encoding="utf-8")
                (directory / "COHERENCE.md").write_text(coherence, encoding="utf-8")
            python_change_validate = run(
                "python3", str(ROOT / "scripts" / "bm.py"), "model", "validate",
                "--repo", str(python_repo), "--change", "C001",
            )
            go_change_validate = run(
                str(binary), "model", "validate", "--repo", str(go_repo),
                "--change", "C001",
            )
            self.assertEqual(
                go_change_validate.returncode, python_change_validate.returncode
            )
            self.assertEqual(go_change_validate.stderr, python_change_validate.stderr)
            self.assertEqual(
                json.loads(go_change_validate.stdout),
                json.loads(python_change_validate.stdout),
            )

    def test_go_scope_seal_and_verify_match_python_oracle(self) -> None:
        from tests.test_method_v04_cli import detailed_scope_body, write_text_pdf

        with tempfile.TemporaryDirectory(prefix="bm-go-scope-parity-") as temp:
            base = Path(temp)
            binary = base / "bm-preview"
            built = run("go", "build", "-trimpath", "-o", str(binary), "./cmd/bm-preview")
            self.assertEqual(built.returncode, 0, built.stderr)
            source = base / "scope.pdf"
            draft = base / "draft.md"
            write_text_pdf(source, ["Portal", "Aceite"])
            draft.write_text(detailed_scope_body(), encoding="utf-8")
            repositories = {"python": base / "python-repo", "go": base / "go-repo"}
            commands = {
                "python": ("python3", str(ROOT / "scripts" / "bm.py")),
                "go": (str(binary),),
            }
            changes: dict[str, str] = {}
            for engine, repo in repositories.items():
                initialized = run("git", "init", str(repo))
                self.assertEqual(initialized.returncode, 0, initialized.stderr)
                init = run(*commands[engine], "model", "init", "--repo", str(repo))
                self.assertEqual(init.returncode, 0, init.stderr)
                change = run(
                    *commands[engine], "model", "init", "--repo", str(repo),
                    "--change", "Portal suporte",
                )
                self.assertEqual(change.returncode, 0, change.stderr)
                changes[engine] = str(json.loads(change.stdout)["change"])
            self.assertEqual(changes["go"], changes["python"])
            sealed: dict[str, dict[str, object]] = {}
            for engine, repo in repositories.items():
                result = run(
                    *commands[engine], "scope", "seal", "--repo", str(repo),
                    "--change", changes[engine], "--source", str(source),
                    "--draft", str(draft), "--pages", "2", "--extraction", "mixed",
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                sealed[engine] = json.loads(result.stdout)
            for payload in sealed.values():
                payload.pop("scope")
                payload.pop("scope_digest")
            self.assertEqual(sealed["go"], sealed["python"])
            change = changes["go"]
            scope_documents = {}
            for engine, repo in repositories.items():
                path = repo / ".bianchini" / "changes" / change / "SCOPE.md"
                text_value = path.read_text(encoding="utf-8")
                metadata = json.loads(text_value.split("---", 2)[1])
                metadata.pop("sealed_at")
                metadata.pop("scope_digest")
                scope_documents[engine] = (metadata, text_value.split("---", 2)[2])
            self.assertEqual(scope_documents["go"], scope_documents["python"])
            for engine, repo in repositories.items():
                verified = run(
                    *commands[engine], "scope", "verify", "--repo", str(repo),
                    "--change", change, "--source", str(source),
                )
                self.assertEqual(verified.returncode, 0, verified.stderr)
                self.assertTrue(json.loads(verified.stdout)["verified"])

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
