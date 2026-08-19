"""Cenários comportamentais da camada de eficiência de contexto v3.1."""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from test_method_package import (
    PlanningQualityScenarios,
    PlanningStabilityScenarios,
    cli,
    cli_json,
    git,
    read,
)


class ContextEfficiencyScenarios(unittest.TestCase):
    def make_v2_project(self, root: Path, *, initialize_git: bool = False) -> Path:
        builder = PlanningStabilityScenarios(methodName="runTest")
        return builder.make_project(root, initialize_git=initialize_git)

    def approve_project(self, state_path: Path, root: Path) -> dict[str, object]:
        builder = PlanningStabilityScenarios(methodName="runTest")
        builder.pass_checker(state_path, root)
        snapshot = cli_json("snapshot", "create", str(state_path), "--root", str(root))
        state = json.loads(read(state_path))
        plan_ids = [plan["id"] for plan in state["plans"]]
        state["planning_status"] = "approved"
        state["approval"].update(
            {
                "status": "approved",
                "approved_at": "2026-08-18T22:00:00Z",
                "approved_by": "owner",
                "approved_plans": plan_ids,
            }
        )
        state["approval"]["package"]["manifest_digest"] = snapshot["digest"]
        for plan in state["plans"]:
            plan["status"] = "approved"
        state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return state

    def test_quality_v2_requires_change_and_readiness_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_v2_project(root)
            state = json.loads(read(state_path))
            plan = root / state["plans"][0]["path"]
            plan.write_text(
                read(plan)
                .replace("**Change:** state-machine\n", "")
                .replace(
                    "**Readiness refs:** D-001, A-001, P-001, U-001, SD-001\n",
                    "",
                ),
                encoding="utf-8",
            )
            result = cli(
                "planning-audit", str(state_path), "--root", str(root), "--strict"
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("campo Change ausente", result.stderr)
            self.assertIn("campo Readiness refs ausente", result.stderr)

    def test_quality_v1_remains_compatible_without_new_unit_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            builder = PlanningQualityScenarios(methodName="runTest")
            state_path = builder.make_project(root)
            result = cli_json(
                "planning-audit", str(state_path), "--root", str(root), "--strict"
            )
            self.assertEqual(result["quality_contract"], "planning-quality-v1")

    def test_quality_v2_rejects_unknown_change_category(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_v2_project(root)
            state = json.loads(read(state_path))
            plan = root / state["plans"][0]["path"]
            plan.write_text(
                read(plan).replace(
                    "**Change:** state-machine", "**Change:** categoria-inventada"
                ),
                encoding="utf-8",
            )
            result = cli(
                "planning-audit", str(state_path), "--root", str(root), "--strict"
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("Change inválido", result.stderr)
            self.assertIn("categoria-inventada", result.stderr)

    def test_quality_v2_rejects_unknown_or_misdirected_readiness_ref(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_v2_project(root)
            state = json.loads(read(state_path))
            plan = root / state["plans"][0]["path"]
            plan.write_text(
                read(plan).replace("SD-001", "ZZ-999"), encoding="utf-8"
            )
            unknown = cli(
                "planning-audit", str(state_path), "--root", str(root), "--strict"
            )
            self.assertEqual(unknown.returncode, 2)
            self.assertIn("Readiness ref inexistente: ZZ-999", unknown.stderr)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_v2_project(root)
            state = json.loads(read(state_path))
            readiness_path = root / state["planning"]["readiness"]
            match = re.search(
                r"```json\s*(.*?)\s*```", read(readiness_path), re.DOTALL | re.IGNORECASE
            )
            self.assertIsNotNone(match)
            readiness = json.loads(match.group(1))
            readiness["pitfalls"][0]["destinations"] = [
                state["planning"]["spec"]
            ]
            readiness_path.write_text(
                "# Planning Readiness\n\n```json\n"
                + json.dumps(readiness, ensure_ascii=False, indent=2)
                + "\n```\n",
                encoding="utf-8",
            )
            misdirected = cli(
                "planning-audit", str(state_path), "--root", str(root), "--strict"
            )
            self.assertEqual(misdirected.returncode, 2)
            self.assertIn(
                "Readiness ref P-001 não aponta para o plano P01", misdirected.stderr
            )

    def test_hydrated_task_brief_contains_only_referenced_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_v2_project(root, initialize_git=True)
            state = self.approve_project(state_path, root)
            output = root / ".superpowers/bianchini/context/P01-S1.md"
            result = cli_json(
                "task-brief",
                "--plan",
                str(root / state["plans"][0]["path"]),
                "--task",
                "1",
                "--state",
                str(state_path),
                "--root",
                str(root),
                "--hydrate-context",
                "--output",
                str(output),
            )
            self.assertTrue(result["hydrated"])
            self.assertEqual(result["readiness_refs"], [
                "D-001",
                "A-001",
                "P-001",
                "U-001",
                "SD-001",
            ])
            content = read(output)
            self.assertIn(state["approval"]["package"]["manifest_digest"], content)
            self.assertIn("D-001", content)
            self.assertIn("P-001", content)
            self.assertIn("## Contratos", content)
            self.assertIn("state-machine", content)
            self.assertIn("python3 -m unittest tests.test_auth", content)
            self.assertNotIn("S-001", content)

    def test_hydrated_task_brief_is_confined_to_ignored_scratch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_v2_project(root, initialize_git=True)
            state = self.approve_project(state_path, root)
            result = cli(
                "task-brief",
                "--plan",
                str(root / state["plans"][0]["path"]),
                "--task",
                "1",
                "--state",
                str(state_path),
                "--root",
                str(root),
                "--hydrate-context",
                "--output",
                str(root / "docs/context.md"),
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn(".superpowers", result.stderr)

    def test_spec_diff_derives_added_modified_and_removed_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base = root / "auth-current.md"
            target = root / "auth-next.md"
            output = root / "auth-diff.md"
            base.write_text(
                "# Auth\n\n"
                "## AUTH-001 Login\n\nAceita e-mail e senha.\n\n"
                "## AUTH-002 Usuário legado\n\nAceita nome de usuário.\n",
                encoding="utf-8",
            )
            target.write_text(
                "# Auth\n\n"
                "## AUTH-001 Login\n\nAceita e-mail, senha e segundo fator.\n\n"
                "## AUTH-003 Bloqueio\n\nBloqueia após cinco falhas.\n",
                encoding="utf-8",
            )
            result = cli_json(
                "spec-diff",
                "--base",
                str(base),
                "--target",
                str(target),
                "--output",
                str(output),
            )
            self.assertEqual(result["added"], ["AUTH-003"])
            self.assertEqual(result["modified"], ["AUTH-001"])
            self.assertEqual(result["removed"], ["AUTH-002"])
            self.assertRegex(result["base_digest"], r"^[0-9a-f]{64}$")
            self.assertRegex(result["target_digest"], r"^[0-9a-f]{64}$")
            content = read(output)
            self.assertIn("## ADDED", content)
            self.assertIn("## MODIFIED", content)
            self.assertIn("## REMOVED", content)
            self.assertIn("AUTH-003", content)

    def test_spec_diff_rejects_duplicate_requirement_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base = root / "base.md"
            target = root / "target.md"
            base.write_text(
                "## AUTH-001 Primeiro\n\nA.\n\n## AUTH-001 Segundo\n\nB.\n",
                encoding="utf-8",
            )
            target.write_text("## AUTH-001 Primeiro\n\nA.\n", encoding="utf-8")
            result = cli(
                "spec-diff",
                "--base",
                str(base),
                "--target",
                str(target),
                "--output",
                str(root / "diff.md"),
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("ID de requisito duplicado", result.stderr)

    def test_mutation_evidence_accepts_classified_survivors_and_ignores_score(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_v2_project(root, initialize_git=True)
            revision = git(root, "rev-parse", "HEAD")
            report = root / "mutation.json"
            output = root / "artifacts/mutation/P01-session.json"
            report.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "revision": revision,
                        "score": 12.5,
                        "mutants": [
                            {"id": "M-001", "status": "killed"},
                            {
                                "id": "M-002",
                                "status": "survived",
                                "classification": "equivalent",
                                "justification": "A mutação mantém o mesmo resultado observável.",
                            },
                        ],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            result = cli_json(
                "mutation-evidence",
                "verify",
                "--state",
                str(state_path),
                "--root",
                str(root),
                "--plan",
                "P01",
                "--risk-seam",
                "sessão pública",
                "--tool",
                "mutmut",
                "--command",
                "mutmut run src/auth.py",
                "--report",
                str(report),
                "--output",
                str(output),
            )
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["mutation_policy"], "selective")
            self.assertFalse(result["global_score_gate"])
            self.assertEqual(result["survived"], 1)
            normalized = json.loads(read(output))
            self.assertEqual(normalized["result"], "passed")
            self.assertEqual(normalized["revision"], revision)

    def test_mutation_evidence_blocks_unclassified_material_survivor(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_v2_project(root, initialize_git=True)
            revision = git(root, "rev-parse", "HEAD")
            report = root / "mutation.json"
            output = root / "artifacts/mutation/P01-session.json"
            report.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "revision": revision,
                        "mutants": [
                            {
                                "id": "M-009",
                                "status": "survived",
                                "classification": "behavior_gap",
                                "approved_behavior": True,
                                "risk": "high",
                                "justification": "A regra aprovada muda sem o teste falhar.",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            result = cli(
                "mutation-evidence",
                "verify",
                "--state",
                str(state_path),
                "--root",
                str(root),
                "--plan",
                "P01",
                "--risk-seam",
                "sessão pública",
                "--tool",
                "mutmut",
                "--command",
                "mutmut run src/auth.py",
                "--report",
                str(report),
                "--output",
                str(output),
            )
            self.assertEqual(result.returncode, 3)
            self.assertIn("comportamento aprovado", result.stderr)
            self.assertFalse(output.exists())

    def test_mutation_evidence_blocks_stale_revision(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_v2_project(root, initialize_git=True)
            report = root / "mutation.json"
            report.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "revision": "0" * 40,
                        "mutants": [{"id": "M-001", "status": "killed"}],
                    }
                ),
                encoding="utf-8",
            )
            result = cli(
                "mutation-evidence",
                "verify",
                "--state",
                str(state_path),
                "--root",
                str(root),
                "--plan",
                "P01",
                "--risk-seam",
                "sessão pública",
                "--tool",
                "mutmut",
                "--command",
                "mutmut run src/auth.py",
                "--report",
                str(report),
                "--output",
                str(root / "artifacts/mutation/stale.json"),
            )
            self.assertEqual(result.returncode, 3)
            self.assertIn("evidência de mutação obsoleta", result.stderr)


if __name__ == "__main__":
    unittest.main()
