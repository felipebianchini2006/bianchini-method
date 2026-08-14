"""Contratos comportamentais exclusivos do overlay Codex."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "codex" / "skills" / "executar-plano-codex"
GUARD = OVERLAY / "scripts" / "review_guard.py"
INSTALLER = ROOT / "codex" / "install.sh"


def run_guard(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(GUARD), *args],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def output_json(result: subprocess.CompletedProcess[str]) -> dict[str, object]:
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise AssertionError("saída não é objeto")
    return value


def finding(
    finding_id: str = "B1",
    *,
    severity: str = "important",
    disposition: str = "blocker",
    **extra: object,
) -> dict[str, object]:
    value: dict[str, object] = {
        "id": finding_id,
        "severity": severity,
        "disposition": disposition,
        "title": f"Finding {finding_id}",
        "approved_requirement": "Spec §2",
        "reproduction": "python3 -m unittest: falha determinística",
        "material_impact": "requisito aprovado não funciona",
        "reachable_scenario": "entrada pública válida",
    }
    value.update(extra)
    return value


def write_findings(path: Path, values: list[dict[str, object]]) -> None:
    path.write_text(json.dumps({"findings": values}), encoding="utf-8")


def freeze(root: Path, values: list[dict[str, object]] | None = None) -> Path:
    sidecar = root / "artifacts/bianchini/v1/codex/convergence/P01/U1.json"
    findings = root / "findings.json"
    write_findings(findings, values if values is not None else [finding()])
    result = run_guard(
        "freeze",
        "--root",
        str(root),
        "--planning-version",
        "v1",
        "--plan",
        "P01",
        "--unit",
        "U1",
        "--seam",
        "api",
        "--review-head",
        "head-1",
        "--findings",
        str(findings),
    )
    output_json(result)
    return sidecar


class CodexOverlayPackageTests(unittest.TestCase):
    def test_required_package_and_manual_activation_exist(self) -> None:
        required = (
            OVERLAY / "SKILL.md",
            OVERLAY / "agents/openai.yaml",
            OVERLAY / "references/CODEX_CONVERGENCE.md",
            OVERLAY / "references/plan-reviewer-codex.md",
            GUARD,
            INSTALLER,
        )
        for path in required:
            with self.subTest(path=path):
                self.assertTrue(path.is_file())
        skill = (OVERLAY / "SKILL.md").read_text(encoding="utf-8")
        openai = (OVERLAY / "agents/openai.yaml").read_text(encoding="utf-8")
        self.assertIn("disable-model-invocation: true", skill)
        self.assertIn("allow_implicit_invocation: false", openai)
        self.assertIn("$executar-plano-codex all", skill)

    def test_overlay_keeps_base_contracts_outside_its_directory(self) -> None:
        skill = (OVERLAY / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("preflight, rota v1/v2", skill)
        self.assertIn("gates do plano", skill)
        self.assertIn("homologação e entrega", skill)
        self.assertIn("ignorar somente `max_fix_rounds` e `breaker`", skill)
        self.assertIn("A revisão final do release também usa o revisor Codex", skill)

    def test_base_cli_and_schema_copies_remain_identical(self) -> None:
        wrapper = (ROOT / "scripts/bm.py").read_text(encoding="utf-8")
        packaged_cli = (ROOT / "skills/_shared/scripts/bm.py").read_text(encoding="utf-8")
        self.assertIn("runpy.run_path", wrapper)
        self.assertIn('"skills" / "_shared" / "scripts" / "bm.py"', wrapper)
        self.assertNotIn("executar-plano-codex", wrapper)
        self.assertNotIn("executar-plano-codex", packaged_cli)
        self.assertEqual(
            (ROOT / "schemas/project-state.schema.json").read_bytes(),
            (ROOT / "skills/_shared/schemas/project-state.schema.json").read_bytes(),
        )


class ReviewGuardScenarios(unittest.TestCase):
    def test_first_review_freezes_blockers_and_defers_noncritical(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            hardening = finding(
                "H1",
                severity="minor",
                disposition="hardening",
                approved_requirement="",
                reproduction="",
                material_impact="",
                reachable_scenario="",
            )
            sidecar = freeze(root, [finding(), hardening])
            state = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertEqual(sorted(state["blockers"]), ["B1"])
            self.assertEqual(state["deferred_hardening"][0]["id"], "H1")
            second = run_guard(
                "freeze",
                "--root",
                str(root),
                "--planning-version",
                "v1",
                "--plan",
                "P01",
                "--unit",
                "U1",
                "--seam",
                "api",
                "--review-head",
                "head-1",
                "--findings",
                str(root / "findings.json"),
            )
            self.assertEqual(second.returncode, 2)
            self.assertIn("já congelada", second.stderr)

    def test_blocker_requires_all_four_proofs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            incomplete = finding(material_impact="")
            findings = root / "findings.json"
            write_findings(findings, [incomplete])
            result = run_guard(
                "freeze",
                "--root",
                str(root),
                "--planning-version",
                "v1",
                "--plan",
                "P01",
                "--unit",
                "U1",
                "--seam",
                "api",
                "--review-head",
                "head-1",
                "--findings",
                str(findings),
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("material_impact", result.stderr)
            self.assertFalse(
                (root / "artifacts/bianchini/v1/codex/convergence/P01/U1.json").exists()
            )

    def test_forbidden_action_token_is_never_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            forbidden = finding(title="ask_user")
            findings = root / "findings.json"
            write_findings(findings, [forbidden])
            result = run_guard(
                "freeze",
                "--root",
                str(root),
                "--planning-version",
                "v1",
                "--plan",
                "P01",
                "--unit",
                "U1",
                "--seam",
                "api",
                "--review-head",
                "head-1",
                "--findings",
                str(findings),
            )
            self.assertEqual(result.returncode, 2)
            self.assertFalse(
                (root / "artifacts/bianchini/v1/codex/convergence/P01/U1.json").exists()
            )

    def test_later_review_accepts_only_frozen_or_delta_regression(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sidecar = freeze(root)
            frozen = finding(source="frozen")
            regression = finding(
                "R1",
                source="delta_regression",
                delta_base="abc",
                delta_head="def",
            )
            findings = root / "next.json"
            write_findings(findings, [frozen, regression])
            accepted = output_json(
                run_guard(
                    "review",
                    "--sidecar",
                    str(sidecar),
                    "--findings",
                    str(findings),
                    "--delta-base",
                    "head-1",
                    "--delta-head",
                    "head-2",
                )
            )
            self.assertIn("R1", accepted["state"]["blockers"])

            wrong_chain = run_guard(
                "review",
                "--sidecar",
                str(sidecar),
                "--findings",
                str(findings),
                "--delta-base",
                "head-1",
                "--delta-head",
                "head-3",
            )
            self.assertEqual(wrong_chain.returncode, 2)
            self.assertIn("última revisão", wrong_chain.stderr)

            new_opinion = finding("N1", source="frozen")
            write_findings(findings, [new_opinion])
            rejected = run_guard(
                "review",
                "--sidecar",
                str(sidecar),
                "--findings",
                str(findings),
                "--delta-base",
                "head-2",
                "--delta-head",
                "head-3",
            )
            self.assertEqual(rejected.returncode, 2)
            self.assertIn("não pertence", rejected.stderr)

            output_json(
                run_guard(
                    "resolve",
                    "--sidecar",
                    str(sidecar),
                    "--blocker",
                    "B1",
                    "--evidence",
                    "teste passou",
                )
            )
            write_findings(findings, [frozen])
            reopened = run_guard(
                "review",
                "--sidecar",
                str(sidecar),
                "--findings",
                str(findings),
                "--delta-base",
                "head-2",
                "--delta-head",
                "head-4",
            )
            self.assertEqual(reopened.returncode, 2)
            self.assertIn("não pode reabrir", reopened.stderr)

    def test_two_fix_rounds_one_redesign_and_completed_is_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sidecar = freeze(root, [finding("B1"), finding("B2"), finding("B3")])
            for round_number in (1, 2):
                result = output_json(
                    run_guard(
                        "fix",
                        "--sidecar",
                        str(sidecar),
                        "--blocker",
                        "B1",
                        "--blocker",
                        "B2",
                        "--blocker",
                        "B3",
                        "--summary",
                        f"round {round_number}",
                    )
                )
                self.assertEqual(result["state"]["fix_rounds"], round_number)
            third = run_guard(
                "fix",
                "--sidecar",
                str(sidecar),
                "--blocker",
                "B1",
                "--summary",
                "round 3",
            )
            self.assertEqual(output_json(third)["action"], "redesign_required")

            first_redesign = run_guard(
                "redesign", "--sidecar", str(sidecar), "--seam", "api", "--summary", "estrutura"
            )
            self.assertEqual(first_redesign.returncode, 0)
            exhausted = output_json(
                run_guard(
                    "fix",
                    "--sidecar",
                    str(sidecar),
                    "--blocker",
                    "B1",
                    "--summary",
                    "sem nova rodada",
                )
            )
            self.assertEqual(exhausted["action"], "continue_independent")
            second_redesign = run_guard(
                "redesign", "--sidecar", str(sidecar), "--seam", "api", "--summary", "outra"
            )
            self.assertEqual(second_redesign.returncode, 2)

            empty_evidence = run_guard(
                "resolve",
                "--sidecar",
                str(sidecar),
                "--blocker",
                "B1",
                "--evidence",
                " ",
            )
            self.assertEqual(empty_evidence.returncode, 2)

            for blocker in ("B1", "B2", "B3"):
                output_json(
                    run_guard(
                        "resolve",
                        "--sidecar",
                        str(sidecar),
                        "--blocker",
                        blocker,
                        "--evidence",
                        "teste passou",
                    )
                )
            completed = output_json(run_guard("complete", "--sidecar", str(sidecar)))
            self.assertEqual(completed["action"], "completed")
            reopen = run_guard(
                "redesign", "--sidecar", str(sidecar), "--seam", "ui", "--summary", "reabrir"
            )
            self.assertEqual(reopen.returncode, 2)
            self.assertIn("terminal", reopen.stderr)
            duplicate = run_guard(
                "freeze",
                "--root",
                str(root),
                "--planning-version",
                "v1",
                "--plan",
                "P01",
                "--unit",
                "U1",
                "--seam",
                "api",
                "--review-head",
                "head-new",
                "--findings",
                str(root / "findings.json"),
            )
            self.assertEqual(duplicate.returncode, 2)

    def test_decisions_continue_automatically_and_stop_only_for_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sidecar = freeze(root)
            internal = output_json(
                run_guard(
                    "decision",
                    "--sidecar",
                    str(sidecar),
                    "--kind",
                    "internal",
                    "--summary",
                    "escolher parser existente",
                )
            )
            self.assertEqual(internal["action"], "automatic_continue")
            local = output_json(
                run_guard(
                    "decision",
                    "--sidecar",
                    str(sidecar),
                    "--kind",
                    "local_block",
                    "--summary",
                    "serviço local indisponível",
                )
            )
            self.assertEqual(local["action"], "continue_independent")
            invalid = run_guard(
                "decision",
                "--sidecar",
                str(sidecar),
                "--kind",
                "uncertainty",
                "--summary",
                "dúvida interna",
            )
            self.assertEqual(invalid.returncode, 2)

            for index, kind in enumerate(
                (
                    "essential_external_credential",
                    "destructive_action",
                    "new_cost",
                    "real_impossibility",
                ),
                start=2,
            ):
                unit_root = root / str(index)
                unit_root.mkdir()
                other = freeze(unit_root)
                stopped = output_json(
                    run_guard(
                        "decision",
                        "--sidecar",
                        str(other),
                        "--kind",
                        kind,
                        "--summary",
                        "condição comprovada",
                    )
                )
                self.assertEqual(stopped["action"], "stop")
                self.assertNotIn("ask_user", json.dumps(stopped))

    def test_corrupt_sidecar_recovers_from_backup(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            sidecar = freeze(root)
            run_guard(
                "decision",
                "--sidecar",
                str(sidecar),
                "--kind",
                "internal",
                "--summary",
                "criar backup",
            )
            backup = sidecar.with_suffix(".json.bak")
            self.assertTrue(backup.is_file())
            sidecar.write_bytes(b"\xff\xfe")
            recovered = output_json(run_guard("status", "--sidecar", str(sidecar)))
            self.assertTrue(recovered["recovered"])
            self.assertEqual(json.loads(sidecar.read_text(encoding="utf-8"))["unit_id"], "U1")

    def test_unit_identifier_rejects_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            findings = root / "findings.json"
            write_findings(findings, [])
            result = run_guard(
                "freeze",
                "--root",
                str(root),
                "--planning-version",
                "v1",
                "--plan",
                "P01",
                "--unit",
                "../escape",
                "--seam",
                "api",
                "--review-head",
                "head-1",
                "--findings",
                str(findings),
            )
            self.assertEqual(result.returncode, 2)
            sidecar = freeze(root)
            outside = root / "outside.json"
            outside.write_bytes(sidecar.read_bytes())
            escaped = run_guard("status", "--sidecar", str(outside))
            self.assertEqual(escaped.returncode, 2)
            self.assertIn("caminho canônico", escaped.stderr)


class CodexInstallerScenarios(unittest.TestCase):
    def test_installer_targets_only_codex_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            codex_home = root / "codex-home"
            claude_home = root / "claude-home"
            default_claude_home = root / "home/.claude"
            environment = {
                **os.environ,
                "CODEX_HOME": str(codex_home),
                "CLAUDE_HOME": str(claude_home),
                "HOME": str(root / "home"),
            }
            for _ in range(2):
                result = subprocess.run(
                    ["bash", str(INSTALLER)],
                    cwd=ROOT,
                    env=environment,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
            installed = codex_home / "skills/executar-plano-codex"
            self.assertTrue((installed / "SKILL.md").is_file())
            self.assertTrue((installed / "scripts/review_guard.py").is_file())
            self.assertTrue((codex_home / "skills/executar-plano/SKILL.md").is_file())
            self.assertTrue((codex_home / "skills/_shared/scripts/bm.py").is_file())
            self.assertFalse(claude_home.exists())
            self.assertFalse(default_claude_home.exists())


if __name__ == "__main__":
    unittest.main()
