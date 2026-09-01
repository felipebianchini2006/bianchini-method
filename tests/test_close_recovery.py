from __future__ import annotations

import fcntl
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/_shared/scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import bm_close  # noqa: E402
import bm_v04_planning  # noqa: E402
from bm_close import (  # noqa: E402
    CLOSE_PHASES,
    CloseRecoveryError,
    SimulatedCloseCrash,
    crash_recoverable_close,
    pending_close,
    recover_pending_close,
)
from bm_project_model import ProjectModel  # noqa: E402
from bm_workspace import MethodWorkspace  # noqa: E402


class CloseRecoveryScenarios(unittest.TestCase):
    def _workspace(
        self,
        root: Path,
        change: str = "C001-billing",
        *,
        typed_model: bool = False,
    ) -> dict[str, object]:
        workspace = MethodWorkspace(root)
        workspace.initialize()
        model_before = b"# Model before\n"
        model_after = b"# Model after\n"
        if typed_model:
            empty_sections = {
                "schema_version": 1,
                "modules": [],
                "interfaces": [],
                "capabilities": [],
                "contracts": [],
                "ownership": [],
                "data": [],
                "integrations": [],
                "journeys": [],
                "invariants": [],
                "effects": [],
            }
            model_before = (
                "---\n"
                + json.dumps(empty_sections, sort_keys=True)
                + "\n---\n# Model before\n"
            ).encode()
            after_sections = {**empty_sections, "contracts": [{"id": "closed"}]}
            model_after = (
                "---\n"
                + json.dumps(after_sections, sort_keys=True)
                + "\n---\n# Model after\n"
            ).encode()
        workspace.atomic_write(workspace.current_architecture, b"# Architecture before\n")
        workspace.atomic_write(workspace.current_system_model, model_before)
        workspace.atomic_write(workspace.current_specs / "billing.md", b"# BILL-001 before\n")
        workspace.atomic_write(workspace.current_dir / "KEEP.md", b"keep byte-for-byte\n")
        workspace.atomic_write(workspace.state_file, b"state-before\n")

        change_dir = workspace.changes_dir / change
        change_dir.mkdir(parents=True)
        workspace.atomic_write(change_dir / "ARCHITECTURE.md", b"# Architecture after\n")
        workspace.atomic_write(change_dir / "SYSTEM_MODEL.md", model_after)
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
            "system_model_after": model_after,
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
        self.assertEqual(
            workspace.current_system_model.read_bytes(), fixture["system_model_after"]
        )
        self.assertEqual((workspace.current_specs / "billing.md").read_bytes(), b"# BILL-001 after\n")
        self.assertEqual((workspace.current_specs / "audit.md").read_bytes(), b"# AUDIT-001 added\n")
        self.assertEqual((workspace.current_dir / "KEEP.md").read_bytes(), b"keep byte-for-byte\n")
        self.assertEqual(workspace.state_file.read_bytes(), fixture["next_state"])
        self.assertIsNone(pending_close(workspace.root))
        self.assertFalse((workspace.runtime_dir / f"cycle-close-{change}").exists())

    def _crash_during_input_materialization(
        self, root: Path, fixture: dict[str, object]
    ) -> None:
        original_atomic_write = bm_close._atomic_write
        crashed = False

        def crash_during_inputs(path: Path, content: bytes) -> None:
            nonlocal crashed
            original_atomic_write(path, content)
            if (
                not crashed
                and path.parent.name == "inputs"
                and path.name == "SYSTEM_MODEL.md"
            ):
                crashed = True
                raise SimulatedCloseCrash("INPUTS_MATERIALIZED")

        with mock.patch.object(
            bm_close, "_atomic_write", side_effect=crash_during_inputs
        ):
            with self.assertRaises(SimulatedCloseCrash):
                self._close(root, fixture)

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

    def test_public_close_recovery_returns_managed_contract_for_every_phase(self) -> None:
        for phase in CLOSE_PHASES:
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                fixture = self._workspace(root, typed_model=True)
                with self.assertRaises(SimulatedCloseCrash):
                    self._close(root, fixture, failpoint=phase)

                recovered = bm_v04_planning.close_change(
                    root, str(fixture["change"])
                )

                expected_model_digest = ProjectModel.from_system_model(
                    Path(fixture["workspace"].current_system_model)
                ).digest()
                self.assertEqual(recovered["status"], "completed")
                self.assertEqual(recovered["model_digest"], expected_model_digest)
                self.assertTrue(recovered["specs_promoted"])
                self.assertEqual(recovered["specs_status"], "managed")
                self._assert_closed(fixture)

    def test_crash_while_materializing_inputs_has_durable_intent_and_retries(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = self._workspace(root)
            self._crash_during_input_materialization(root, fixture)

            workspace = fixture["workspace"]
            assert isinstance(workspace, MethodWorkspace)
            transaction = workspace.runtime_dir / f"cycle-close-{fixture['change']}"
            self.assertTrue(transaction.is_dir())
            journal = pending_close(root)
            self.assertIsNotNone(journal)
            assert journal is not None
            self.assertEqual(journal["phase"], "PREPARING")

            recovered = self._close(root, fixture)

            self.assertEqual(recovered["status"], "completed")
            self.assertTrue(recovered["recovered"])
            self._assert_closed(fixture)

    def test_preparing_retry_checks_visible_digests_before_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = self._workspace(root)
            self._crash_during_input_materialization(root, fixture)
            workspace = fixture["workspace"]
            assert isinstance(workspace, MethodWorkspace)
            workspace.atomic_write(workspace.current_dir / "KEEP.md", b"drift\n")

            with self.assertRaisesRegex(CloseRecoveryError, "RECOVERY_AMBIGUOUS"):
                self._close(root, fixture)

            journal = pending_close(root)
            self.assertIsNotNone(journal)
            assert journal is not None
            self.assertEqual(journal["phase"], "PREPARING")

    def test_preparing_cleanup_rejects_symlink_without_touching_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = self._workspace(root)
            self._crash_during_input_materialization(root, fixture)
            journal = pending_close(root)
            assert journal is not None
            transaction = root / journal["paths"]["transaction"]
            protected = root / "protected.txt"
            protected.write_bytes(b"keep\n")
            (transaction / "inputs/external-link").symlink_to(protected)

            with self.assertRaisesRegex(CloseRecoveryError, "PATH_UNSAFE"):
                self._close(root, fixture)

            self.assertEqual(protected.read_bytes(), b"keep\n")
            self.assertEqual(pending_close(root)["phase"], "PREPARING")

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

    def test_recovery_rejects_symlinked_transaction_root_before_visible_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = self._workspace(root)
            with self.assertRaises(SimulatedCloseCrash):
                self._close(root, fixture, failpoint="PREPARED")

            workspace = fixture["workspace"]
            assert isinstance(workspace, MethodWorkspace)
            journal = pending_close(root)
            assert journal is not None
            transaction = root / journal["paths"]["transaction"]
            protected = root / "protected-transaction"
            transaction.rename(protected)
            transaction.symlink_to(protected, target_is_directory=True)
            protected_digest = bm_close._tree_digest(protected)
            current_digest = bm_close._tree_digest(workspace.current_dir)
            change_digest = bm_close._tree_digest(Path(fixture["change_dir"]))
            state_before = workspace.state_file.read_bytes()

            with self.assertRaisesRegex(CloseRecoveryError, "PATH_UNSAFE"):
                recover_pending_close(root)

            self.assertEqual(bm_close._tree_digest(protected), protected_digest)
            self.assertEqual(bm_close._tree_digest(workspace.current_dir), current_digest)
            self.assertEqual(
                bm_close._tree_digest(Path(fixture["change_dir"])), change_digest
            )
            self.assertEqual(workspace.state_file.read_bytes(), state_before)
            self.assertFalse((workspace.archive_dir / str(fixture["change"])).exists())
            self.assertEqual(
                json.loads(
                    (workspace.runtime_dir / "cycle-close.json").read_text(
                        encoding="utf-8"
                    )
                )["phase"],
                "PREPARED",
            )

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

    def test_unchanged_current_documents_preserve_bytes_and_mtime(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = self._workspace(root)
            workspace = fixture["workspace"]
            assert isinstance(workspace, MethodWorkspace)
            change_dir = Path(fixture["change_dir"])
            specs = Path(fixture["specs"])
            (change_dir / "ARCHITECTURE.md").write_bytes(
                workspace.current_architecture.read_bytes()
            )
            (specs / "billing.md").write_bytes(
                (workspace.current_specs / "billing.md").read_bytes()
            )
            architecture_before = workspace.current_architecture.read_bytes()
            architecture_mtime = workspace.current_architecture.stat().st_mtime_ns
            spec_before = (workspace.current_specs / "billing.md").read_bytes()
            spec_mtime = (workspace.current_specs / "billing.md").stat().st_mtime_ns

            self._close(root, fixture)

            self.assertEqual(workspace.current_architecture.read_bytes(), architecture_before)
            self.assertEqual(workspace.current_architecture.stat().st_mtime_ns, architecture_mtime)
            self.assertEqual((workspace.current_specs / "billing.md").read_bytes(), spec_before)
            self.assertEqual(
                (workspace.current_specs / "billing.md").stat().st_mtime_ns,
                spec_mtime,
            )

    def test_casefold_planning_is_rejected_before_visible_mutation(self) -> None:
        for location in ("current", "change"):
            with self.subTest(location=location), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                fixture = self._workspace(root)
                workspace = fixture["workspace"]
                assert isinstance(workspace, MethodWorkspace)
                base = (
                    workspace.current_dir
                    if location == "current"
                    else Path(fixture["change_dir"])
                )
                foreign = base / ".PLANNING"
                foreign.mkdir()
                (foreign / "keep.md").write_text("foreign\n", encoding="utf-8")
                architecture_before = workspace.current_architecture.read_bytes()
                coherence_before = (
                    Path(fixture["change_dir"]) / "COHERENCE.md"
                ).read_bytes()
                state_before = workspace.state_file.read_bytes()

                with self.assertRaisesRegex(CloseRecoveryError, "PATH_UNSAFE"):
                    self._close(root, fixture)

                self.assertEqual(
                    workspace.current_architecture.read_bytes(), architecture_before
                )
                self.assertEqual(
                    (Path(fixture["change_dir"]) / "COHERENCE.md").read_bytes(),
                    coherence_before,
                )
                self.assertEqual(workspace.state_file.read_bytes(), state_before)
                self.assertEqual((foreign / "keep.md").read_text(encoding="utf-8"), "foreign\n")
                self.assertFalse(
                    (workspace.runtime_dir / f"cycle-close-{fixture['change']}").exists()
                )

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixture = self._workspace(root)
            workspace = fixture["workspace"]
            assert isinstance(workspace, MethodWorkspace)
            with self.assertRaises(SimulatedCloseCrash):
                self._close(root, fixture, failpoint="PREPARED")
            journal = pending_close(root)
            assert journal is not None
            transaction = root / journal["paths"]["transaction"]
            foreign = transaction / "inputs/specs/.PLANNING"
            foreign.mkdir()
            (foreign / "keep.md").write_text("foreign\n", encoding="utf-8")
            current_before = bm_close._tree_digest(workspace.current_dir)
            change_before = bm_close._tree_digest(Path(fixture["change_dir"]))
            state_before = workspace.state_file.read_bytes()

            with self.assertRaisesRegex(CloseRecoveryError, "PATH_UNSAFE"):
                recover_pending_close(root)

            self.assertEqual(bm_close._tree_digest(workspace.current_dir), current_before)
            self.assertEqual(
                bm_close._tree_digest(Path(fixture["change_dir"])), change_before
            )
            self.assertEqual(workspace.state_file.read_bytes(), state_before)

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

    def test_specs_manifest_symlink_is_rejected_before_staging(self) -> None:
        for target_kind in ("internal", "external"):
            with self.subTest(target_kind=target_kind), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                fixture = self._workspace(root)
                change_dir = Path(fixture["change_dir"])
                if target_kind == "internal":
                    target = change_dir / "manifest-real.json"
                else:
                    target = root / "manifest-external.json"
                target.write_text("{}\n", encoding="utf-8")
                manifest = change_dir / "specs/MANIFEST.json"
                manifest.symlink_to(target)

                with self.assertRaisesRegex(CloseRecoveryError, "PATH_UNSAFE"):
                    self._close(root, fixture, specs_manifest=manifest)

                self.assertIsNone(pending_close(root))
                self.assertFalse(
                    (root / f".bianchini/.runtime/cycle-close-{fixture['change']}").exists()
                )
                self.assertEqual(target.read_text(encoding="utf-8"), "{}\n")

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
