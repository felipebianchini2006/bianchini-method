from __future__ import annotations

import hashlib
import fcntl
import json
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/_shared/scripts"
BM = ROOT / "skills/_shared/scripts/bm.py"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import bm_learning  # noqa: E402
from bm_learning import (  # noqa: E402
    LearningError,
    approve_learning,
    deactivate_learning,
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

    def test_python_transitions_share_the_exclusive_backend_lock(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = self.make_repo(Path(temp))
            self.write_source(repo)
            lock_path = repo / ".bianchini/.runtime/learning/transition.lock"
            lock_path.parent.mkdir(parents=True)
            with lock_path.open("a+b") as lock:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaisesRegex(LearningError, "LEARNING_BUSY"):
                    propose_learning(repo)
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def test_candidate_path_is_rejected_before_transition_target_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = self.make_repo(Path(temp))
            for candidate in ("../../outside", "/absolute", r"L123\outside", "l813bc8bd6bab"):
                for transition in (
                    lambda value=candidate: approve_learning(
                        repo, value, "0" * 64, "human:felipe"
                    ),
                    lambda value=candidate: reject_learning(repo, value, "inválido"),
                ):
                    with self.assertRaisesRegex(
                        LearningError, "LEARNING_CANDIDATE_INVALID"
                    ):
                        transition()

    def test_partial_approve_and_reject_transitions_resume_idempotently(self) -> None:
        for action in ("approve", "reject"):
            with self.subTest(action=action), tempfile.TemporaryDirectory() as temp:
                repo = self.make_repo(Path(temp))
                self.write_source(repo)
                candidate = propose_learning(repo)["candidates"][0]
                pending = repo / candidate["path"]
                if action == "approve":
                    target = repo / ".bianchini/current/lessons" / f"{candidate['id']}.json"
                    transition = lambda: approve_learning(
                        repo, candidate["id"], candidate["digest"], "human:felipe"
                    )
                else:
                    target = (
                        repo
                        / ".bianchini/.runtime/learning/rejected"
                        / f"{candidate['id']}.json"
                    )
                    transition = lambda: reject_learning(
                        repo, candidate["id"], "caso não generalizável"
                    )

                original_unlink = bm_learning._durable_unlink
                calls = 0

                def fail_once(path: Path) -> None:
                    nonlocal calls
                    calls += 1
                    if calls == 1:
                        path.unlink()
                        raise OSError("falha simulada no fsync após unlink")
                    original_unlink(path)

                with mock.patch.object(
                    bm_learning, "_durable_unlink", side_effect=fail_once
                ):
                    with self.assertRaisesRegex(OSError, "falha simulada"):
                        transition()
                    self.assertTrue(target.is_file())
                    self.assertFalse(pending.exists())
                    result = transition()

                self.assertEqual(result["id"], candidate["id"])
                self.assertTrue(target.is_file())
                self.assertFalse(pending.exists())

    def test_partial_deactivate_resumes_after_durable_replace(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = self.make_repo(Path(temp))
            self.write_source(repo)
            candidate = propose_learning(repo)["candidates"][0]
            approve_learning(repo, candidate["id"], candidate["digest"], "human:felipe")
            original_write = bm_learning._atomic_write
            calls = 0

            def fail_after_replace(path: Path, content: bytes) -> None:
                nonlocal calls
                calls += 1
                original_write(path, content)
                if calls == 1:
                    raise OSError("falha simulada após replace durável")

            transition = lambda: deactivate_learning(
                repo, candidate["id"], "contrato substituído", "human:felipe"
            )
            with mock.patch.object(
                bm_learning, "_atomic_write", side_effect=fail_after_replace
            ):
                with self.assertRaisesRegex(OSError, "falha simulada"):
                    transition()
                result = transition()

            self.assertFalse(result["active"])
            self.assertEqual(calls, 1)

    def test_learning_atomic_write_syncs_target_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "approved" / "lesson.json"
            synced: list[Path] = []
            original_sync = bm_learning._sync_directory

            def tracked(path: Path) -> None:
                synced.append(path)
                original_sync(path)

            with mock.patch.object(bm_learning, "_sync_directory", side_effect=tracked):
                bm_learning._atomic_write(target, b"{}\n")

            self.assertIn(target.parent, synced)

    def test_learning_transition_target_symlink_is_rejected_before_read(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = self.make_repo(Path(temp))
            self.write_source(repo)
            candidate = propose_learning(repo)["candidates"][0]
            target = repo / ".bianchini/current/lessons" / f"{candidate['id']}.json"
            outside = Path(temp) / "outside.json"
            outside.write_text("segredo externo\n", encoding="utf-8")
            target.symlink_to(outside)

            with self.assertRaisesRegex(LearningError, "LEARNING_PATH_INVALID"):
                approve_learning(
                    repo, candidate["id"], candidate["digest"], "human:felipe"
                )
            self.assertEqual(outside.read_text(encoding="utf-8"), "segredo externo\n")

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

    def test_forged_candidate_and_source_escape_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            repo = self.make_repo(base)
            outside = base / "outside.md"
            outside.write_text("evidência externa\n", encoding="utf-8")
            self.write_source(repo)
            candidate = propose_learning(repo)["candidates"][0]
            pending = repo / str(candidate["path"])
            value = json.loads(pending.read_text(encoding="utf-8"))
            value["source"] = "../outside.md"
            unsigned = {key: item for key, item in value.items() if key != "digest"}
            value["digest"] = hashlib.sha256(
                (json.dumps(unsigned, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
            ).hexdigest()
            pending.write_text(
                json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(LearningError, "STALE_EVIDENCE|LEARNING_PATH_INVALID"):
                approve_learning(repo, str(candidate["id"]), str(value["digest"]), "human:test")

            base_value = {
                key: item
                for key, item in value.items()
                if key not in {"id", "digest"}
            }
            base_value["source"] = "README.md"
            base_value["source_digest"] = hashlib.sha256(
                (repo / "README.md").read_bytes()
            ).hexdigest()
            base_bytes = (
                json.dumps(
                    base_value,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode()
            forged_id = "L" + hashlib.sha256(base_bytes).hexdigest()[:12].upper()
            forged = {"id": forged_id, **base_value}
            forged["digest"] = hashlib.sha256(
                (
                    json.dumps(
                        forged,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    + "\n"
                ).encode()
            ).hexdigest()
            forged_path = pending.parent / f"{forged_id}.json"
            forged_path.write_text(
                json.dumps(
                    forged,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(LearningError, "LEARNING_PATH_INVALID"):
                approve_learning(
                    repo, forged_id, str(forged["digest"]), "human:test"
                )

    def test_approved_lesson_can_be_deactivated_without_deleting_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = self.make_repo(Path(temp))
            self.write_source(repo)
            candidate = propose_learning(repo)["candidates"][0]
            approved = approve_learning(
                repo, candidate["id"], candidate["digest"], "human:felipe"
            )
            result = deactivate_learning(
                repo, candidate["id"], "contrato substituído", "human:felipe"
            )
            self.assertFalse(result["active"])
            value = json.loads((repo / approved["path"]).read_text(encoding="utf-8"))
            self.assertEqual(value["status"], "approved")
            self.assertFalse(value["active"])
            self.assertEqual(value["deactivation_reason"], "contrato substituído")
            self.assertEqual(value["approved_by"], "human:felipe")

            before_retry = (repo / approved["path"]).read_bytes()
            retried = deactivate_learning(
                repo, candidate["id"], "contrato substituído", "human:felipe"
            )
            self.assertFalse(retried["active"])
            self.assertEqual((repo / approved["path"]).read_bytes(), before_retry)

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

    def test_cli_exposes_opt_in_propose_list_approve_reject_and_deactivate(self) -> None:
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
            deactivated = self.run_bm(
                "learn",
                "deactivate",
                "--repo",
                str(repo),
                "--candidate",
                candidate["id"],
                "--reason",
                "contrato substituído",
                "--approved-by",
                "human:felipe",
            )
            self.assertEqual(deactivated.returncode, 0, deactivated.stderr)
            self.assertFalse(json.loads(deactivated.stdout)["active"])

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

            proposed = self.run_bm("learn", "propose", "--repo", str(repo))
            self.assertEqual(proposed.returncode, 0, proposed.stderr)
            self.assertEqual(json.loads(proposed.stdout)["candidates"], [])

    def test_source_discovery_rejects_symlinked_bianchini_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            repo = base / "repo"
            repo.mkdir()
            subprocess.run(
                ["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True
            )
            outside = base / "outside"
            (outside / "debug/resolved").mkdir(parents=True)
            (outside / "debug/resolved/D001-external.md").write_text(
                "conteúdo externo não governado\n", encoding="utf-8"
            )
            (repo / ".bianchini").symlink_to(outside, target_is_directory=True)

            proposed = self.run_bm("learn", "propose", "--repo", str(repo))
            self.assertNotEqual(proposed.returncode, 0)
            self.assertIn("LEARNING_PATH_INVALID", proposed.stderr)

    def test_resolved_debug_can_explicitly_nominate_pending_learning(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            repo.mkdir()
            subprocess.run(
                ["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True
            )
            subprocess.run(["git", "config", "user.name", "BM Test"], cwd=repo, check=True)
            subprocess.run(
                ["git", "config", "user.email", "test@example.invalid"],
                cwd=repo,
                check=True,
            )
            (repo / "README.md").write_text("fixture\n", encoding="utf-8")
            subprocess.run(["git", "add", "README.md"], cwd=repo, check=True)
            subprocess.run(
                ["git", "commit", "-m", "fixture"], cwd=repo, check=True, capture_output=True
            )
            initialized = self.run_bm("model", "init", "--repo", str(repo))
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            started = self.run_bm(
                "debug",
                "start",
                "--repo",
                str(repo),
                "--objective",
                "Estabilizar retry",
                "--expected",
                "Retry idempotente",
                "--actual",
                "Retry duplica efeito",
                "--environment",
                "pytest local",
            )
            self.assertEqual(started.returncode, 0, started.stderr)
            debug_id = json.loads(started.stdout)["id"]
            for event in ("reproduced", "diagnosed", "red", "fixing"):
                extra: list[str] = []
                if event == "diagnosed":
                    extra = ["--root-cause", "retry sem chave estável"]
                checkpoint = self.run_bm(
                    "debug",
                    "checkpoint",
                    "--repo",
                    str(repo),
                    "--id",
                    debug_id,
                    "--event",
                    event,
                    "--evidence",
                    f"evidência {event}",
                    *extra,
                )
                self.assertEqual(checkpoint.returncode, 0, checkpoint.stderr)
            (repo / "fix.py").write_text("IDEMPOTENT = True\n", encoding="utf-8")
            for event in ("green", "regression_checked", "documented"):
                extra = []
                if event == "regression_checked":
                    extra = ["--neighbor-regression", "retry saudável permanece válido"]
                if event == "documented":
                    extra = ["--residual-risk", "limitado ao contrato testado"]
                checkpoint = self.run_bm(
                    "debug",
                    "checkpoint",
                    "--repo",
                    str(repo),
                    "--id",
                    debug_id,
                    "--event",
                    event,
                    "--evidence",
                    f"evidência {event}",
                    *extra,
                )
                self.assertEqual(checkpoint.returncode, 0, checkpoint.stderr)

            finished = self.run_bm(
                "debug",
                "finish",
                "--repo",
                str(repo),
                "--id",
                debug_id,
                "--docviva-kind",
                "internal",
                "--docviva-outcome",
                "not_applicable",
                "--docviva-justification",
                "A correção não alterou contrato vivo.",
                "--learning-classification",
                "repeatable_procedure",
                "--learning-statement",
                "Usar chave de idempotência estável em retries.",
                "--learning-tag",
                "retry",
                "--learning-validity",
                "enquanto o contrato de retry estiver ativo",
            )
            self.assertEqual(finished.returncode, 0, finished.stderr)
            proposed = self.run_bm("learn", "propose", "--repo", str(repo))
            self.assertEqual(proposed.returncode, 0, proposed.stderr)
            payload = json.loads(proposed.stdout)
            self.assertEqual(payload["created"], 1)
            self.assertEqual(payload["candidates"][0]["classification"], "repeatable_procedure")
            self.assertFalse((repo / ".bianchini/current/lessons").exists())


if __name__ == "__main__":
    unittest.main()
