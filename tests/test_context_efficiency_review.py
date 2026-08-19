"""Regressões adversariais da eficiência de contexto v3.1."""

from __future__ import annotations

import json
import re
import tempfile
import unittest
from pathlib import Path

from test_method_package import (
    PlanningStabilityScenarios,
    cli,
    cli_json,
    git,
    read,
)


class ContextEfficiencyReviewScenarios(unittest.TestCase):
    def make_project(self, root: Path, *, initialize_git: bool = False) -> Path:
        builder = PlanningStabilityScenarios(methodName="runTest")
        return builder.make_project(root, initialize_git=initialize_git)

    def make_rc_project(
        self,
        root: Path,
        *,
        command: str = "python3 mutation_runner.py",
    ) -> tuple[Path, str, Path]:
        root.rmdir()
        state_path = self.make_project(root, initialize_git=True)
        report = root / "artifacts/mutation/report.json"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "mutants": [{"id": "M1", "status": "killed"}],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        state = json.loads(read(state_path))
        state["verification"]["release"]["commands"] = [command]
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        git(root, "add", ".")
        git(root, "commit", "-m", "test: prepare rc source and mutation report")
        candidate_revision = git(root, "rev-parse", "HEAD")

        state = json.loads(read(state_path))
        state["release"].update(
            {
                "status": "candidate",
                "candidate": {
                    "id": "rc-context-1",
                    "revision": candidate_revision,
                    "build": "build-1",
                    "checksum": "sha256:context-1",
                },
            }
        )
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        git(root, "add", str(state_path.relative_to(root)))
        git(root, "commit", "-m", "test: record rc fingerprint")
        self.assertNotEqual(candidate_revision, git(root, "rev-parse", "HEAD"))
        return state_path, candidate_revision, report

    def verify_mutation(
        self,
        root: Path,
        state_path: Path,
        revision: str,
        report: Path,
        *,
        command: str = "python3 mutation_runner.py",
        output: str = "artifacts/bianchini/v1/mutation/P01-context.json",
        classifications: Path | None = None,
    ) -> dict[str, object]:
        arguments = [
            "mutation-evidence",
            "verify",
            "--state",
            str(state_path),
            "--root",
            str(root),
            "--plan",
            "P01",
            "--risk-seam",
            "session-state",
            "--tool",
            "normalized",
            "--command",
            command,
            "--report",
            str(report.relative_to(root)),
            "--revision",
            revision,
            "--output",
            output,
        ]
        if classifications is not None:
            arguments.extend(("--classifications", str(classifications.relative_to(root))))
        return cli_json(*arguments)

    def test_hydrated_context_zero_ledger_tail_is_empty_and_reports_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_project(root)
            state = json.loads(read(state_path))
            plan = root / state["plans"][0]["path"]
            ledger = root / state["plans"][0]["ledger"]
            ledger.parent.mkdir(parents=True, exist_ok=True)
            ledger.write_text("segredo antigo\ncheckpoint atual\n", encoding="utf-8")
            output = root / ".superpowers/bianchini/context/P01-S1.md"

            result = cli_json(
                "task-brief",
                "--plan",
                str(plan),
                "--task",
                "1",
                "--state",
                str(state_path),
                "--root",
                str(root),
                "--hydrate-context",
                "--ledger-tail-lines",
                "0",
                "--output",
                str(output),
            )

            rendered = read(output)
            match = re.search(
                r"## Contexto hidratado\n\n```json\n(.*?)\n```",
                rendered,
                re.DOTALL,
            )
            self.assertIsNotNone(match)
            metadata = json.loads(match.group(1))
            self.assertTrue(result["hydrated"])
            self.assertEqual(metadata["profile"], "standard")
            self.assertEqual(metadata["max_fix_rounds"], 3)
            self.assertEqual(metadata["test_seams"], ["session", "navigation"])
            self.assertEqual(metadata["ledger_tail_lines"], 0)
            self.assertNotIn("segredo antigo", rendered)
            self.assertNotIn("checkpoint atual", rendered)
            self.assertIn("Nenhum ledger registrado para o plano.", rendered)

    def test_hydrated_context_requires_exact_spec_section(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_project(root)
            state = json.loads(read(state_path))
            plan = root / state["plans"][0]["path"]
            plan.write_text(
                read(plan).replace(
                    "**Spec refs:** specs/system-change.md#contratos",
                    "**Spec refs:** specs/system-change.md",
                ),
                encoding="utf-8",
            )
            result = cli(
                "task-brief",
                "--plan",
                str(plan),
                "--task",
                "1",
                "--state",
                str(state_path),
                "--root",
                str(root),
                "--hydrate-context",
                "--output",
                str(root / ".superpowers/bianchini/context/P01-S1.md"),
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("spec ref hidratada exige seção #anchor", result.stderr)

    def test_mutation_evidence_accepts_rc_revision_before_state_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path, candidate_revision, report = self.make_rc_project(root)
            result = self.verify_mutation(
                root,
                state_path,
                candidate_revision,
                report,
            )
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["result"], "passed")
            self.assertEqual(result["expected_revision"], candidate_revision)
            self.assertEqual(result["candidate"]["revision"], candidate_revision)

    def test_mutation_evidence_rejects_output_input_collision(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path, candidate_revision, report = self.make_rc_project(root)
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
                "session-state",
                "--tool",
                "normalized",
                "--command",
                "python3 mutation_runner.py",
                "--report",
                str(report.relative_to(root)),
                "--revision",
                candidate_revision,
                "--output",
                str(report.relative_to(root)),
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("output deve ser diferente dos arquivos de entrada", result.stderr)

    def test_mutation_evidence_rejects_unknown_classification_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path, candidate_revision, report = self.make_rc_project(root)
            classifications = root / "artifacts/mutation/classifications.json"
            classifications.write_text(
                json.dumps(
                    {
                        "mutants": {
                            "M999": {
                                "classification": "equivalent",
                                "justification": "Não pertence ao relatório atual.",
                            }
                        }
                    },
                    indent=2,
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
                "session-state",
                "--tool",
                "normalized",
                "--command",
                "python3 mutation_runner.py",
                "--report",
                str(report.relative_to(root)),
                "--revision",
                candidate_revision,
                "--classifications",
                str(classifications.relative_to(root)),
                "--output",
                "artifacts/bianchini/v1/mutation/P01-context.json",
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("classificações referenciam mutantes ausentes: M999", result.stderr)

    def test_proof_map_consumes_verified_mutation_evidence(self) -> None:
        command = "python3 mutation_runner.py"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path, candidate_revision, report = self.make_rc_project(
                root,
                command=command,
            )
            mutation = self.verify_mutation(
                root,
                state_path,
                candidate_revision,
                report,
                command=command,
            )
            mutation_path = root / mutation["output"]
            evidence = root / "artifacts/release-evidence.json"
            evidence.write_text("[]\n", encoding="utf-8")
            proof = root / "artifacts/proof-map.json"

            result = cli_json(
                "proof-map",
                "--state",
                str(state_path),
                "--evidence",
                str(evidence),
                "--mutation-evidence",
                str(mutation_path),
                "--output",
                str(proof),
            )

            self.assertEqual(result["automated_total"], 1)
            self.assertEqual(result["automated_proven"], 1)
            self.assertEqual(result["automation_gaps"], [])
            self.assertEqual(result["automated"][0]["command"], command)
            self.assertEqual(result["automated"][0]["source_type"], "mutation")
            self.assertEqual(
                result["automated"][0]["candidate"]["revision"],
                candidate_revision,
            )


if __name__ == "__main__":
    unittest.main()
