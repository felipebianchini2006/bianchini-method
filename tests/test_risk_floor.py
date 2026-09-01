"""Fixtures do piso estrutural de risco para quick/direct."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "_shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from bm_project_model import ProjectModel  # noqa: E402
from bm_risk import RiskInputError, assess_quick_risk  # noqa: E402


class RiskFloorScenarios(unittest.TestCase):
    def test_declared_score_can_increase_but_never_reduce_derived_floor(self) -> None:
        below = assess_quick_risk(1, flags={"money": 2})
        above = assess_quick_risk(8, flags={"money": 1})

        self.assertEqual(below["declared_score"], 1)
        self.assertEqual(below["derived_floor"], 5)
        self.assertEqual(below["effective_score"], 5)
        self.assertIn("declared_below_floor:1<5", below["reasons"])
        self.assertEqual(above["derived_floor"], 1)
        self.assertEqual(above["effective_score"], 8)

    def test_structured_dimensions_preserve_existing_additive_boundary(self) -> None:
        normal = assess_quick_risk(
            0,
            flags={
                "scope": 0,
                "external_effect": 1,
                "migration": 0,
                "concurrency": 0,
                "money": 1,
            },
        )
        protected = assess_quick_risk(
            0,
            flags={
                "scope": 0,
                "external_effect": 1,
                "migration": 1,
                "concurrency": 0,
                "money": 1,
            },
        )

        self.assertEqual((normal["derived_floor"], normal["route"]), (2, "normal"))
        self.assertEqual((protected["derived_floor"], protected["route"]), (3, "protected"))
        self.assertEqual(protected["workflow"], "quick")

    def test_isolated_words_in_docs_or_filenames_do_not_decide_risk(self) -> None:
        result = assess_quick_risk(
            0,
            declared_paths=(
                "docs/payment.md",
                "notes/webhook.txt",
                "tests/money_test.py",
                "README-payment.md",
            ),
        )

        self.assertEqual(result["derived_floor"], 0)
        self.assertEqual(result["route"], "normal")
        self.assertEqual(result["reasons"], [])

    def test_structural_paths_derive_migration_manifest_contract_and_domain_risk(self) -> None:
        result = assess_quick_risk(
            0,
            declared_paths=(
                "db/migrations/0001_create_ledger.sql",
                "package-lock.json",
                "src/contracts/payments.proto",
                "src/payments/service.py",
                "src/webhooks/handler.py",
            ),
        )

        self.assertEqual(result["derived_floor"], 3)
        self.assertEqual(result["route"], "protected")
        self.assertIn("declared_path:migration:db/migrations/0001_create_ledger.sql", result["reasons"])
        self.assertIn("declared_path:dependency_manifest:package-lock.json", result["reasons"])
        self.assertIn("declared_path:contract:src/contracts/payments.proto", result["reasons"])
        self.assertIn("declared_path:payment:src/payments/service.py", result["reasons"])
        self.assertIn("declared_path:webhook:src/webhooks/handler.py", result["reasons"])
        self.assertTrue(
            {
                "rollback",
                "dependency_audit",
                "contract_tests",
                "source_of_truth",
                "authenticity",
            }.issubset(result["additional_guards"])
        )

    def test_project_model_diff_derives_contract_integration_ownership_and_effects(self) -> None:
        current = ProjectModel.from_mapping({})
        expected = ProjectModel.from_mapping(
            {
                "contracts": [{"id": "charge_contract", "kind": "payment"}],
                "ownership": [{"id": "payment_status", "owner": "payments"}],
                "integrations": [{"id": "gateway_events", "kind": "webhook"}],
                "effects": [
                    {
                        "id": "capture_charge",
                        "kind": "money",
                        "reversible": False,
                    }
                ],
            }
        )
        result = assess_quick_risk(
            0, current_model=current, expected_model=expected
        )

        self.assertEqual(result["derived_floor"], 5)
        self.assertIn("model:contracts:added=charge_contract", result["reasons"])
        self.assertIn("model:integrations:added=gateway_events", result["reasons"])
        self.assertIn("model:ownership:added=payment_status", result["reasons"])
        self.assertIn("model:effects:added=capture_charge", result["reasons"])
        self.assertIn("model:irreversible_effect:capture_charge", result["reasons"])
        self.assertIn("human_checkpoint", result["additional_guards"])

    def test_structured_destructive_migration_sets_high_floor_and_recovery_guards(self) -> None:
        result = assess_quick_risk(
            0,
            migrations=(
                {
                    "id": "M001",
                    "path": "db/migrations/0001_drop_legacy.sql",
                    "destructive": True,
                    "reversible": False,
                },
            ),
        )

        self.assertEqual(result["derived_floor"], 5)
        self.assertIn("migration:M001", result["reasons"])
        self.assertIn("migration:irreversible:M001", result["reasons"])
        self.assertTrue(
            {"rollback", "backup_restore", "human_checkpoint"}.issubset(
                result["additional_guards"]
            )
        )

    def test_payment_and_webhook_remain_quick_but_protected(self) -> None:
        result = assess_quick_risk(
            0,
            flags={"payment": True, "webhook": True},
        )

        self.assertEqual(result["workflow"], "quick")
        self.assertEqual(result["route"], "protected")
        self.assertNotIn(result["route"], {"planning", "sdd", "redirect"})
        self.assertTrue(
            {
                "source_of_truth",
                "idempotency",
                "authenticity",
                "deduplication",
            }.issubset(result["additional_guards"])
        )

    def test_critical_risk_never_changes_the_human_route(self) -> None:
        result = assess_quick_risk(
            10,
            flags={"irreversible": True, "uncontrolled_concurrency": True},
        )

        self.assertEqual(result["effective_score"], 10)
        self.assertEqual(result["workflow"], "quick")
        self.assertEqual(result["route"], "protected")

    def test_finish_reclassifies_upward_from_real_diff_and_adds_guards(self) -> None:
        initial = assess_quick_risk(
            0, phase="start", declared_paths=("src/core/format.py",)
        )
        finished = assess_quick_risk(
            0,
            phase="finish",
            declared_paths=("src/core/format.py",),
            diff_paths=("db/migrations/0002_add_index.sql",),
        )

        self.assertEqual((initial["derived_floor"], initial["route"]), (0, "normal"))
        self.assertEqual((finished["derived_floor"], finished["route"]), (3, "protected"))
        self.assertEqual(finished["diff_floor"], 3)
        self.assertTrue(finished["reclassified"])
        self.assertIn(
            "diff_path:migration:db/migrations/0002_add_index.sql",
            finished["reasons"],
        )
        self.assertIn("rollback", finished["additional_guards"])

    def test_finish_does_not_lower_a_previous_structural_floor(self) -> None:
        result = assess_quick_risk(
            1,
            phase="finish",
            flags={"money": 2},
            diff_paths=("src/ui/button.css",),
        )

        self.assertEqual(result["initial_floor"], 5)
        self.assertEqual(result["diff_floor"], 0)
        self.assertEqual(result["derived_floor"], 5)
        self.assertFalse(result["reclassified"])

    def test_reasons_and_guards_are_deterministic_and_deduplicated(self) -> None:
        first = assess_quick_risk(
            0,
            flags={"webhook": True, "payment": True},
            declared_paths=("src/webhooks/a.py", "src/payments/b.py"),
        )
        second = assess_quick_risk(
            0,
            flags={"payment": True, "webhook": True},
            declared_paths=("src/payments/b.py", "src/webhooks/a.py"),
        )

        self.assertEqual(first, second)
        self.assertEqual(first["reasons"], sorted(set(first["reasons"])))
        self.assertEqual(
            first["additional_guards"], sorted(set(first["additional_guards"]))
        )

    def test_invalid_scores_flags_models_migrations_and_paths_fail_closed(self) -> None:
        invalid_calls = (
            lambda: assess_quick_risk(-1),
            lambda: assess_quick_risk(11),
            lambda: assess_quick_risk(True),
            lambda: assess_quick_risk(0, phase="unknown"),
            lambda: assess_quick_risk(0, flags={"unknown": True}),
            lambda: assess_quick_risk(0, flags={"money": 3}),
            lambda: assess_quick_risk(0, declared_paths=("../escape.py",)),
            lambda: assess_quick_risk(0, migrations=("M001",)),
            lambda: assess_quick_risk(0, current_model=ProjectModel.from_mapping({})),
        )
        for call in invalid_calls:
            with self.subTest(call=call), self.assertRaises(RiskInputError):
                call()


if __name__ == "__main__":
    unittest.main()
