"""Contrato determinístico da atualização seletiva da DocViva."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "_shared" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from bm_docviva import (  # noqa: E402
    DocVivaError,
    snapshot_docviva,
    verify_docviva_impact,
    write_if_changed,
)


class DocVivaScenarios(unittest.TestCase):
    def make_current(self, root: Path) -> Path:
        current = root / ".bianchini" / "current"
        specs = current / "specs"
        specs.mkdir(parents=True)
        (current / "ARCHITECTURE.md").write_text(
            "# Arquitetura atual\n", encoding="utf-8"
        )
        (current / "SYSTEM_MODEL.md").write_text(
            "# Modelo atual\n", encoding="utf-8"
        )
        (specs / "auth.md").write_text(
            "# Autenticação\n\n## AUTH-001: Login\n",
            encoding="utf-8",
        )
        return current

    def test_internal_quick_accepts_proven_not_applicable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_current(root)
            before = snapshot_docviva(root)

            result = verify_docviva_impact(
                root,
                before,
                {"kind": "internal", "outcome": "not_applicable"},
                [],
                "Refatora nomes internos sem alterar comportamento observável.",
                False,
            )

            self.assertEqual(result["status"], "verified")
            self.assertEqual(result["outcome"], "not_applicable")
            self.assertEqual(result["changed"], [])
            self.assertEqual(result["before_digest"], result["after_digest"])

    def test_not_applicable_requires_internal_work_and_justification(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_current(root)
            before = snapshot_docviva(root)

            for classification, justification in (
                ({"kind": "behavioral", "outcome": "not_applicable"}, "Prova."),
                ({"kind": "internal", "outcome": "not_applicable"}, ""),
            ):
                with self.subTest(classification=classification, justification=justification):
                    with self.assertRaisesRegex(
                        DocVivaError, "DOCVIVA_NOT_APPLICABLE_INVALID"
                    ):
                        verify_docviva_impact(
                            root,
                            before,
                            classification,
                            [],
                            justification,
                            False,
                        )

    def test_required_behavioral_change_blocks_without_docviva_change(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.make_current(root)
            before = snapshot_docviva(root)

            with self.assertRaisesRegex(DocVivaError, "DOCVIVA_UPDATE_REQUIRED"):
                verify_docviva_impact(
                    root,
                    before,
                    {"kind": "behavioral", "outcome": "updated"},
                    [],
                    "O comportamento de autenticação mudou.",
                    True,
                )

    def test_no_op_requires_equal_digests_and_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            current = self.make_current(root)
            before = snapshot_docviva(root)

            verified = verify_docviva_impact(
                root,
                before,
                {"kind": "behavioral", "outcome": "no_op"},
                [],
                "Fixtures demonstram que o resultado observável permaneceu igual.",
                True,
            )
            self.assertEqual(verified["outcome"], "no_op")
            self.assertEqual(verified["changed"], [])

            (current / "specs" / "auth.md").write_text(
                "# Autenticação\n\n## AUTH-001: Login com MFA\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(DocVivaError, "DOCVIVA_NO_OP_INVALID"):
                verify_docviva_impact(
                    root,
                    before,
                    {"kind": "behavioral", "outcome": "no_op"},
                    [".bianchini/current/specs/auth.md"],
                    "Alega no-op apesar da mudança.",
                    True,
                )

    def test_declaration_must_exactly_match_changed_current_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            current = self.make_current(root)
            before = snapshot_docviva(root)
            architecture = current / "ARCHITECTURE.md"
            architecture.write_text("# Arquitetura atual\n\nNova fronteira.\n", encoding="utf-8")

            with self.assertRaisesRegex(DocVivaError, "DOCVIVA_DECLARATION_MISMATCH"):
                verify_docviva_impact(
                    root,
                    before,
                    {"kind": "architecture", "outcome": "updated"},
                    [".bianchini/current/SYSTEM_MODEL.md"],
                    "A arquitetura mudou.",
                    True,
                )

            result = verify_docviva_impact(
                root,
                before,
                {"kind": "architecture", "outcome": "updated"},
                [".bianchini/current/ARCHITECTURE.md"],
                "A arquitetura mudou.",
                True,
            )
            self.assertEqual(
                result["modified"], [".bianchini/current/ARCHITECTURE.md"]
            )
            self.assertEqual(result["created"], [])
            self.assertEqual(result["removed"], [])

    def test_required_change_needs_corresponding_current_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            current = self.make_current(root)
            before = snapshot_docviva(root)
            architecture = current / "ARCHITECTURE.md"
            architecture.write_text("# Arquitetura atual\n\nNova fronteira.\n", encoding="utf-8")

            with self.assertRaisesRegex(DocVivaError, "DOCVIVA_ARTIFACT_MISMATCH"):
                verify_docviva_impact(
                    root,
                    before,
                    {"kind": "behavioral", "outcome": "updated"},
                    [".bianchini/current/ARCHITECTURE.md"],
                    "Alega mudança comportamental sem alterar modelo ou spec.",
                    True,
                )

    def test_write_if_changed_preserves_bytes_and_mtime_when_equal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            current = self.make_current(root)
            target = current / "SYSTEM_MODEL.md"
            expected = target.read_bytes()
            old_time = 1_700_000_000_123_456_789
            os.utime(target, ns=(old_time, old_time))

            changed = write_if_changed(
                root,
                ".bianchini/current/SYSTEM_MODEL.md",
                expected,
            )

            self.assertFalse(changed)
            self.assertEqual(target.read_bytes(), expected)
            self.assertEqual(target.stat().st_mtime_ns, old_time)

    def test_history_foreign_namespace_and_symlink_do_not_count(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            current = self.make_current(root)
            before = snapshot_docviva(root)
            history = root / ".bianchini" / "quick" / "Q001" / "RESULT.md"
            history.parent.mkdir(parents=True)
            history.write_text("histórico\n", encoding="utf-8")
            self.assertEqual(snapshot_docviva(root), before)

            with self.assertRaisesRegex(DocVivaError, "DOCVIVA_PATH_INVALID"):
                verify_docviva_impact(
                    root,
                    before,
                    {"kind": "internal", "outcome": "updated"},
                    [".bianchini/quick/Q001/RESULT.md"],
                    "Histórico não é verdade atual.",
                    False,
                )
            with self.assertRaisesRegex(DocVivaError, "DOCVIVA_PATH_INVALID"):
                write_if_changed(root, ".planning/CURRENT.md", "nunca\n")

            outside = root / "outside.md"
            outside.write_text("fora\n", encoding="utf-8")
            (current / "specs" / "escape.md").symlink_to(outside)
            with self.assertRaisesRegex(DocVivaError, "DOCVIVA_SYMLINK"):
                snapshot_docviva(root)


if __name__ == "__main__":
    unittest.main()
