from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/_shared/scripts"
BM = ROOT / "skills/_shared/scripts/bm.py"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from bm_learning import (  # noqa: E402
    LearningError,
    approve_learning,
    list_learning,
    propose_learning,
    reject_learning,
)


def frontmatter(value: dict[str, object], title: str = "Fonte") -> str:
    return (
        "---\n"
        + json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        + f"\n---\n# {title}\n"
    )


class GovernedLearningScenarios(unittest.TestCase):
    def run_bm(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(BM), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def make_repo(self, base: Path) -> Path:
        repo = base / "repo"
        (repo / ".bianchini/debug/resolved").mkdir(parents=True)
        (repo / ".bianchini/current/lessons").mkdir(parents=True)
        subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "BM Test"], cwd=repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.invalid"], cwd=repo, check=True
        )
        (repo / "README.md").write_text("fixture\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "fixture"], cwd=repo, check=True, capture_output=True)
        return repo

    def write_source(self, repo: Path, *, evidence: bool = True) -> Path:
        source = repo / ".bianchini/debug/resolved/D001-retry.md"
        payload: dict[str, object] = {
            "schema_version": 1,
            "id": "D001-retry",
            "status": "resolved",
            "root_cause": "retry sem chave estável",
            "green": "teste de contrato aprovado",
            "learning_candidate": {
                "classification": "repeatable_procedure",
                "statement": "Usar chave de idempotência estável no retry do checkout.",
                "tags": ["payments", "checkout", "src/payments.py"],
                "validity": "enquanto o contrato checkout-v1 estiver ativo",
                "conflicts": [],
            },
        }
        if evidence:
            payload["evidence"] = ["tests/test_checkout.py::test_retry_idempotent"]
        source.write_text(frontmatter(payload, "Debug resolvido"), encoding="utf-8")
        return source

    def test_proposal_requires_explicit_success_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = self.make_repo(Path(temp))
            self.write_source(repo, evidence=False)
            with self.assertRaisesRegex(LearningError, "LEARNING_EVIDENCE_REQUIRED"):
                propose_learning(repo)
            self.assertEqual(list((repo / ".bianchini/.runtime/learning/pending").glob("*")), [])

    def test_candidate_is_pending_and_does_not_change_current_behavior(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = self.make_repo(Path(temp))
            self.write_source(repo)
            result = propose_learning(repo)
            self.assertEqual(result["created"], 1)
            self.assertEqual(list((repo / ".bianchini/current/lessons").glob("*")), [])
            listed = list_learning(repo)
            self.assertEqual(len(listed["pending"]), 1)
            self.assertEqual(listed["approved"], [])

    def test_approval_requires_human_and_current_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = self.make_repo(Path(temp))
            self.write_source(repo)
            candidate = propose_learning(repo)["candidates"][0]
            with self.assertRaisesRegex(LearningError, "HUMAN_APPROVAL_REQUIRED"):
                approve_learning(repo, candidate["id"], candidate["digest"], "agent:codex")
            pending = repo / candidate["path"]
            pending.write_text(pending.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaisesRegex(LearningError, "STALE_EVIDENCE"):
                approve_learning(repo, candidate["id"], candidate["digest"], "human:felipe")

    def test_human_approval_promotes_only_governed_project_lesson(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = self.make_repo(Path(temp))
            self.write_source(repo)
            candidate = propose_learning(repo)["candidates"][0]
            approved = approve_learning(
                repo, candidate["id"], candidate["digest"], "human:felipe"
            )
            target = repo / approved["path"]
            self.assertTrue(target.is_file())
            value = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(value["status"], "approved")
            self.assertEqual(value["approved_by"], "human:felipe")
            self.assertEqual(value["classification"], "repeatable_procedure")
            self.assertFalse((repo / "skills").exists())
            self.assertFalse((repo / "schemas").exists())

    def test_rejection_preserves_history_without_active_lesson(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = self.make_repo(Path(temp))
            self.write_source(repo)
            candidate = propose_learning(repo)["candidates"][0]
            rejected = reject_learning(repo, candidate["id"], "caso isolado")
            self.assertEqual(rejected["status"], "rejected")
            self.assertFalse((repo / candidate["path"]).exists())
            self.assertTrue((repo / rejected["path"]).is_file())
            self.assertEqual(list((repo / ".bianchini/current/lessons").glob("*")), [])

    def test_cli_exposes_opt_in_propose_list_approve_and_reject(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = self.make_repo(Path(temp))
            self.write_source(repo)
            proposed = self.run_bm("learn", "propose", "--repo", str(repo))
            self.assertEqual(proposed.returncode, 0, proposed.stderr)
            candidate = json.loads(proposed.stdout)["candidates"][0]
            listed = self.run_bm("learn", "list", "--repo", str(repo))
            self.assertEqual(listed.returncode, 0, listed.stderr)
            self.assertEqual(len(json.loads(listed.stdout)["pending"]), 1)
            approved = self.run_bm(
                "learn",
                "approve",
                "--repo",
                str(repo),
                "--candidate",
                candidate["id"],
                "--digest",
                candidate["digest"],
                "--approved-by",
                "human:felipe",
            )
            self.assertEqual(approved.returncode, 0, approved.stderr)
            self.assertEqual(json.loads(approved.stdout)["status"], "approved")

    def test_normal_workspace_initialization_creates_no_approved_lesson(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            repo.mkdir()
            subprocess.run(
                ["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True
            )
            initialized = self.run_bm("model", "init", "--repo", str(repo))
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            lessons = repo / ".bianchini/current/lessons"
            self.assertFalse(lessons.exists())


if __name__ == "__main__":
    unittest.main()
