from __future__ import annotations

import fcntl
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/_shared/scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from bm_close import (  # noqa: E402
    CLOSE_PHASES,
    CloseRecoveryError,
    SimulatedCloseCrash,
    crash_recoverable_close,
    pending_close,
    recover_pending_close,
)
from bm_workspace import MethodWorkspace  # noqa: E402


class CloseRecoveryScenarios(unittest.TestCase):
    def _workspace(self, root: Path, change: str = "C001-billing") -> dict[str, object]:
        workspace = MethodWorkspace(root)
        workspace.initialize()
        workspace.atomic_write(workspace.current_architecture, b"# Architecture before\n")
        workspace.atomic_write(workspace.current_system_model, b"# Model before\n")
        workspace.atomic_write(workspace.current_specs / "billing.md", b"# BILL-001 before\n")
        workspace.atomic_write(workspace.current_dir / "KEEP.md", b"keep byte-for-byte\n")
        workspace.atomic_write(workspace.state_file, b"state-before\n")

        change_dir = workspace.changes_dir / change
        change_dir.mkdir(parents=True)
        workspace.atomic_write(change_dir / "ARCHITECTURE.md", b"# Architecture after\n")
        workspace.atomic_write(change_dir / "SYSTEM_MODEL.md", b"# Model after\n")
        specs = change_dir / "specs/target"
        specs.mkdir(parents=True)
        workspace.atomic_write(specs / "billing.md", b"# BILL-001 after\n")
        workspace.atomic_write(specs / "audit.md", b"# AUDIT-001 added\n")
        workspace.atomic_write(change_dir / "COHERENCE.md", b"approved\n")
        return {
            "workspace": workspace,
            "change": change,
            "change_dir": change_dir,
            "specs": specs,
            "summary": b"summary-completed\n",
            "next_state": b"state-after\n",
        }

    def _close(self, root: Path, fixture: dict[str, object], **kwargs: object) -> dict[str, object]:
        return crash_recoverable_close(
            root,
            str(fixture["change"]),
            specs_source=Path(fixture["specs"]),
            summary=bytes(fixture["summary"]),
            next_state=bytes(fixture["next_state"]),
            **kwargs,
        )

    def _assert_closed(self, fixture: dict[str, object]) -> None:
        workspace = fixture["workspace"]
        self.assertIsInstance(workspace, MethodWorkspace)
        assert isinstance(workspace, MethodWorkspace)
        change = str(fixture["change"])
        archive = workspace.archive_dir / change
        self.assertFalse(Path(fixture["change_dir"]).exists())
        self.assertEqual((archive / "SUMMARY.md").read_bytes(), fixture["summary"])
        self.assertEqual(workspace.current_architecture.read_bytes(), b"# Architecture after\n")
        self.assertEqual(workspace.current_system_model.read_bytes(), b"# Model after\n")
        self.assertEqual((workspace.current_specs / "billing.md").read_bytes(), b"# BILL-001 after\n")
        self.assertEqual((workspace.current_specs / "audit.md").read_bytes(), b"# AUDIT-001 added\n")
        self.assertEqual((workspace.current_dir / "KEEP.md").read_bytes(), b"keep byte-for-byte\n")
        self.assertEqual(workspace.state_file.read_bytes(), fixture["next_state"])
        self.assertIsNone(pending_close(workspace.root))
        self.assertFalse((workspace.runtime_dir / f"cycle-close-{change}").exists())

    def test_crash_after_every_durable_phase_recovers_idempotently(self) -> None:
        for phase in CLOSE_PHASES:
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                fixture = self._workspace(root)
                with self.assertRaises(SimulatedCloseCrash) as raised:
                    self._close(root, fixture, failpoint=phase)
                self.assertEqual(raised.exception.phase, phase)
                journal = pending_close(root)
                self.assertIsNotNone(journal)
                assert journal is not None
                self.assertEqual(journal["phase"], phase)

                recovered = self._close(root, fixture)

                self.assertEqual(recovered["status"], "completed")
                self.assertTrue(recovered["recovered"])
                self._assert_closed(fixture)
                self.assertIsNone(recover_pending_close(root))

    def test_staged_tree_and_journal_record_before_and_after_digests(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = self._workspace(root)
            with self.assertRaises(SimulatedCloseCrash):
                self._close(root, fixture, failpoint="STAGED")

            journal = pending_close(root)
            self.assertIsNotNone(journal)
            assert journal is not None
            self.assertEqual(set(journal["digests"]), {"before", "after"})
            for moment in ("before", "after"):
                self.assertEqual(
                    set(journal["digests"][moment]), {"current", "change", "state"}
                )
                for digest in journal["digests"][moment].values():
                    self.assertRegex(digest, r"^[0-9a-f]{64}$")
            stage = root / journal["paths"]["transaction"] / "staged-current"
            self.assertEqual((stage / "KEEP.md").read_bytes(), b"keep byte-for-byte\n")
            self.assertEqual((stage / "specs/audit.md").read_bytes(), b"# AUDIT-001 added\n")

    def test_concurrent_lock_fails_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = self._workspace(root)
            workspace = fixture["workspace"]
            assert isinstance(workspace, MethodWorkspace)
            workspace.runtime_dir.mkdir(parents=True, exist_ok=True)
            lock_path = workspace.runtime_dir / "cycle-close.lock"
            descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                with self.assertRaisesRegex(CloseRecoveryError, "CLOSE_LOCKED"):
                    self._close(root, fixture)
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
                os.close(descriptor)
            self.assertEqual(Path(fixture["change_dir"]).is_dir(), True)
            self.assertEqual(workspace.state_file.read_bytes(), b"state-before\n")

    def test_truncated_journal_blocks_without_guessing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = self._workspace(root)
            workspace = fixture["workspace"]
            assert isinstance(workspace, MethodWorkspace)
            workspace.runtime_dir.mkdir(parents=True, exist_ok=True)
            (workspace.runtime_dir / "cycle-close.json").write_bytes(b'{"phase":')

            with self.assertRaisesRegex(CloseRecoveryError, "JOURNAL_CORRUPT"):
                recover_pending_close(root)

            self.assertTrue(Path(fixture["change_dir"]).is_dir())
            self.assertEqual(workspace.state_file.read_bytes(), b"state-before\n")

    def test_unrecognized_digest_drift_blocks_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = self._workspace(root)
            with self.assertRaises(SimulatedCloseCrash):
                self._close(root, fixture, failpoint="CURRENT_PROMOTED")
            workspace = fixture["workspace"]
            assert isinstance(workspace, MethodWorkspace)
            workspace.atomic_write(workspace.current_dir / "intruder.md", b"drift\n")

            with self.assertRaisesRegex(CloseRecoveryError, "RECOVERY_AMBIGUOUS"):
                recover_pending_close(root)

            self.assertIsNotNone(pending_close(root))

    def test_partial_rename_inside_transition_is_resumed(self) -> None:
        for starting_phase, source_key, backup_name in (
            ("STAGED", "current", "previous-current"),
            ("CURRENT_PROMOTED", "change", "previous-change"),
        ):
            with self.subTest(phase=starting_phase), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                fixture = self._workspace(root)
                with self.assertRaises(SimulatedCloseCrash):
                    self._close(root, fixture, failpoint=starting_phase)
                journal = pending_close(root)
                assert journal is not None
                source = root / journal["paths"][source_key]
                transaction = root / journal["paths"]["transaction"]
                os.replace(source, transaction / backup_name)

                recovered = recover_pending_close(root)

                self.assertEqual(recovered["status"], "completed")
                self._assert_closed(fixture)

    def test_tampered_input_blocks_before_visible_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = self._workspace(root)
            with self.assertRaises(SimulatedCloseCrash):
                self._close(root, fixture, failpoint="PREPARED")
            journal = pending_close(root)
            assert journal is not None
            transaction = root / journal["paths"]["transaction"]
            (transaction / "inputs/specs/billing.md").write_bytes(b"tampered\n")

            with self.assertRaisesRegex(CloseRecoveryError, "RECOVERY_AMBIGUOUS"):
                recover_pending_close(root)

            workspace = fixture["workspace"]
            assert isinstance(workspace, MethodWorkspace)
            self.assertEqual(workspace.current_architecture.read_bytes(), b"# Architecture before\n")
            self.assertTrue(Path(fixture["change_dir"]).is_dir())

    def test_journal_cannot_redirect_cleanup_outside_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = self._workspace(root)
            protected = root / "protected"
            protected.mkdir()
            (protected / "evidence.txt").write_text("keep\n", encoding="utf-8")
            with self.assertRaises(SimulatedCloseCrash):
                self._close(root, fixture, failpoint="PREPARED")
            journal_path = root / ".bianchini/.runtime/cycle-close.json"
            value = json.loads(journal_path.read_text(encoding="utf-8"))
            value["paths"]["transaction"] = "protected"
            journal_path.write_text(json.dumps(value), encoding="utf-8")

            with self.assertRaisesRegex(CloseRecoveryError, "JOURNAL_CORRUPT"):
                recover_pending_close(root)

            self.assertEqual((protected / "evidence.txt").read_text(encoding="utf-8"), "keep\n")

    def test_specs_source_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = self._workspace(root)
            source = Path(fixture["specs"])
            shutil.rmtree(source)
            outside = root / "outside-specs"
            outside.mkdir()
            (outside / "billing.md").write_text("outside\n", encoding="utf-8")
            source.symlink_to(outside, target_is_directory=True)

            with self.assertRaisesRegex(CloseRecoveryError, "PATH_UNSAFE"):
                self._close(root, fixture)

            self.assertIsNone(pending_close(root))

    def test_restore_strategy_returns_known_partial_close_to_before_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = self._workspace(root)
            with self.assertRaises(SimulatedCloseCrash):
                self._close(root, fixture, failpoint="CHANGE_ARCHIVED")

            restored = recover_pending_close(root, strategy="restore")

            self.assertEqual(restored["status"], "restored")
            workspace = fixture["workspace"]
            assert isinstance(workspace, MethodWorkspace)
            self.assertTrue(Path(fixture["change_dir"]).is_dir())
            self.assertFalse((workspace.archive_dir / str(fixture["change"])).exists())
            self.assertEqual(workspace.current_architecture.read_bytes(), b"# Architecture before\n")
            self.assertEqual(workspace.state_file.read_bytes(), b"state-before\n")
            self.assertIsNone(pending_close(root))


if __name__ == "__main__":
    unittest.main()
