"""Testes unitários dos módulos centrais do Bianchini Method 0.4."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "_shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from bm_coherence import (  # noqa: E402
    DependencyGraph,
    Finding,
    FindingStatus,
    ImpactAnalyzer,
    SemanticReviewer,
    Severity,
    StructuralValidator,
    TaskDependencyGraph,
)
from bm_project_model import PlanContract, ProjectModel, TaskContract  # noqa: E402
from bm_workspace import MethodWorkspace  # noqa: E402


def model_mapping() -> dict[str, object]:
    return {
        "modules": [
            {"id": "checkout", "owns": ["checkout_session"]},
            {"id": "payments", "owns": ["payment_intent"]},
        ],
        "interfaces": [
            {
                "id": "payment_gateway",
                "provider": "payments",
                "consumers": ["checkout"],
            }
        ],
        "capabilities": [{"id": "start_payment", "owner": "payments"}],
        "contracts": [{"id": "payment_created", "owner": "payments"}],
        "ownership": [{"id": "payment_status", "owner": "payments"}],
        "data": [{"id": "payment_intent", "owner": "payments"}],
        "integrations": [
            {
                "id": "gateway_webhook",
                "authenticity": "required",
                "deduplication": "provider_event_id",
            }
        ],
        "journeys": [
            {
                "id": "checkout_confirmation",
                "path": [
                    "checkout",
                    "payment_gateway",
                    "payment_intent",
                    "gateway_webhook",
                    "payment_created",
                ],
            }
        ],
        "invariants": [{"id": "single_payment_owner", "value": "payments"}],
        "effects": [{"id": "charge_customer", "owner": "payments"}],
    }


def typed_task(
    identifier: str,
    *,
    covers: list[str],
    depends_on: list[str] | None = None,
    files: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": identifier,
        "name": f"Entregar {identifier}",
        "result": f"Resultado observável de {identifier}",
        "covers": covers,
        "depends_on": depends_on or [],
        "files": files or [f"src/{identifier.lower()}.py"],
        "action": "Implementar pelo seam público já definido.",
        "verify": {
            "kind": "command",
            "run": f"python3 -m unittest tests.test_{identifier.lower()}",
            "proves": f"{identifier} entrega o comportamento declarado.",
        },
        "done": f"{identifier} passa pela interface pública.",
        "risk_seam": "checkout-payment",
    }


def typed_plan(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema_version": 2,
        "id": "P01",
        "status": "planned",
        "result": "Pagamento persistido e observável.",
        "requirements": ["REQ-001"],
        "acceptance": ["Pagamento aprovado fica persistido."],
        "depends_on": [],
        "provides": ["payment_created"],
        "consumes": ["payment_gateway"],
        "modules": ["payments"],
        "interfaces": ["payment_gateway"],
        "ownership": ["payment_status"],
        "data": ["payment_intent"],
        "model_delta": {},
        "migrations": [],
        "effects": [],
        "rollback": "Reverter o commit e preservar as intenções existentes.",
        "verifications": ["python3 -m unittest tests.test_payment"],
        "future_constraints": [],
        "execution": "slice",
        "review": "per_slice",
        "tasks": [typed_task("T01", covers=["REQ-001"])],
    }
    value.update(overrides)
    return value


class MethodWorkspaceTests(unittest.TestCase):
    def test_initialize_creates_only_bianchini_layout_and_preserves_planning(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            planning = root / ".planning"
            planning.mkdir()
            sentinel = planning / "STATE.md"
            sentinel.write_bytes(b"foreign-state\n")

            workspace = MethodWorkspace(root)
            workspace.initialize()

            self.assertEqual(sentinel.read_bytes(), b"foreign-state\n")
            self.assertTrue(workspace.state_file.is_file())
            self.assertTrue(workspace.current_specs.is_dir())
            self.assertTrue(workspace.debug_active.is_dir())
            self.assertTrue(workspace.runtime_dir.is_dir())
            self.assertFalse((root / "docs").exists())

    def test_resolve_confines_absolute_relative_and_symlink_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            unresolved_root = Path(temp)
            workspace = MethodWorkspace(unresolved_root)
            workspace.initialize()

            absolute = unresolved_root / ".bianchini" / "STATE.md"
            self.assertEqual(workspace.resolve(absolute), workspace.state_file)
            self.assertEqual(
                workspace.resolve("current/SYSTEM_MODEL.md"),
                workspace.current_system_model,
            )
            with self.assertRaisesRegex(ValueError, "fora de .bianchini"):
                workspace.resolve("../outside.md")

            outside = unresolved_root / "outside"
            outside.mkdir()
            link = workspace.bianchini_dir / "escape"
            link.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "fora de .bianchini"):
                workspace.resolve("escape/file.md")

    def test_atomic_write_replaces_content_without_leaving_temporary_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = MethodWorkspace(Path(temp))
            workspace.initialize()
            target = workspace.resolve("current/ARCHITECTURE.md")

            workspace.atomic_write(target, "primeiro\n")
            workspace.atomic_write(target, "segundo\n")

            self.assertEqual(target.read_text(encoding="utf-8"), "segundo\n")
            self.assertEqual(list(target.parent.glob(f".{target.name}.*.tmp")), [])

    def test_state_is_compact_round_trippable_and_rejects_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = MethodWorkspace(Path(temp))
            workspace.initialize()
            state = {
                "schema_version": 1,
                "method": "0.4",
                "active_work": "C001-checkout",
                "current_unit": "P01",
                "status": "planning",
                "blockers": [],
                "next_action": "Validar o modelo",
                "last_completed": "Q003-fix-copy",
                "pointers": {
                    "architecture": ".bianchini/current/ARCHITECTURE.md",
                    "system_model": ".bianchini/current/SYSTEM_MODEL.md",
                },
                "digest": "abc123",
                "updated_at": "2026-08-24T12:00:00Z",
            }

            workspace.write_state(state, "# Estado atual\n")

            self.assertEqual(workspace.read_state(), state)
            self.assertLess(workspace.state_file.stat().st_size, 64 * 1024)
            with self.assertRaisesRegex(ValueError, "campo de histórico proibido"):
                workspace.write_state({**state, "history": ["C000"]})
            with self.assertRaisesRegex(ValueError, "64 KiB"):
                workspace.write_state({**state, "next_action": "x" * (64 * 1024)})
            with self.assertRaisesRegex(ValueError, "pointer fora"):
                workspace.write_state(
                    {
                        **state,
                        "pointers": {
                            "system_model": ".planning/SYSTEM_MODEL.md"
                        },
                    }
                )

    def test_state_reader_rejects_symlink_that_escapes_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ".bianchini").mkdir()
            outside = root / "foreign-state.md"
            outside.write_text(
                '---\n{"schema_version":1,"method":"0.4"}\n---\n',
                encoding="utf-8",
            )
            (root / ".bianchini/STATE.md").symlink_to(outside)

            with self.assertRaisesRegex(ValueError, "fora de .bianchini"):
                MethodWorkspace(root).read_state()

    def test_allocate_id_is_monotonic_and_observes_existing_entries(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            workspace = MethodWorkspace(Path(temp))
            workspace.initialize()
            workspace.resolve("quick/Q007-existing").mkdir()

            self.assertEqual(workspace.allocate_id("change"), "C001")
            self.assertEqual(workspace.allocate_id("change"), "C002")
            self.assertEqual(workspace.allocate_id("quick"), "Q008")
            self.assertEqual(workspace.allocate_id("plan"), "P01")
            with self.assertRaisesRegex(ValueError, "tipo de ID"):
                workspace.allocate_id("unknown")


class ProjectModelTests(unittest.TestCase):
    def test_reads_yaml_frontmatter_with_nested_lists(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "SYSTEM_MODEL.md"
            path.write_text(
                "---\n"
                "modules:\n"
                "  - id: payments\n"
                "    owns: [payment_intent, payment_status]\n"
                "interfaces:\n"
                "  - id: payment_gateway\n"
                "    provider: payments\n"
                "    consumers: [checkout, reconciliation]\n"
                "capabilities: []\n"
                "contracts: []\n"
                "ownership: []\n"
                "data:\n"
                "  - id: payment_intent\n"
                "    owner: payments\n"
                "    durable_before: provider_request\n"
                "integrations:\n"
                "  - id: gateway_webhook\n"
                "    authenticity: required\n"
                "    deduplication: provider_event_id\n"
                "journeys:\n"
                "  - id: checkout_confirmation\n"
                "    path:\n"
                "      - checkout\n"
                "      - payment_gateway\n"
                "      - payment_intent\n"
                "invariants: []\n"
                "effects: []\n"
                "---\n"
                "# Modelo do sistema\n",
                encoding="utf-8",
            )

            model = ProjectModel.from_system_model(path)

            self.assertEqual(model.modules["payments"]["owns"], ["payment_intent", "payment_status"])
            self.assertEqual(model.interfaces["payment_gateway"]["provider"], "payments")
            self.assertEqual(
                model.journeys["checkout_confirmation"]["path"],
                ["checkout", "payment_gateway", "payment_intent"],
            )

    def test_reads_json_frontmatter_and_has_order_independent_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "SYSTEM_MODEL.md"
            first = model_mapping()
            second = {key: first[key] for key in reversed(first)}
            path.write_text(
                "---\n" + __import__("json").dumps(first) + "\n---\n# Model\n",
                encoding="utf-8",
            )

            from_file = ProjectModel.from_system_model(path)
            reordered = ProjectModel.from_mapping(second)

            self.assertTrue(from_file.equivalent(reordered))
            self.assertEqual(from_file.digest(), reordered.digest())

            rendered = Path(temp) / "RENDERED_MODEL.md"
            rendered.write_text(
                from_file.to_markdown("# Modelo renderizado\n"), encoding="utf-8"
            )
            self.assertTrue(
                from_file.equivalent(ProjectModel.from_system_model(rendered))
            )
            self.assertIn("# Modelo renderizado", rendered.read_text(encoding="utf-8"))

    def test_rejects_duplicate_and_malformed_model_identifiers(self) -> None:
        mapping = model_mapping()
        mapping["modules"] = [{"id": "payments"}, {"id": "payments"}]
        with self.assertRaisesRegex(ValueError, "ID duplicado"):
            ProjectModel.from_mapping(mapping)

        mapping = model_mapping()
        mapping["modules"] = [{"name": "payments"}]
        with self.assertRaisesRegex(ValueError, "id"):
            ProjectModel.from_mapping(mapping)

    def test_applies_add_update_upsert_and_remove_without_mutating_source(self) -> None:
        current = ProjectModel.from_mapping(model_mapping())
        updated = current.apply_delta(
            {
                "modules": {
                    "add": [{"id": "reconciliation", "owns": ["reconciliation_job"]}],
                    "update": [{"id": "payments", "owns": ["payment_intent", "payment_status"]}],
                },
                "contracts": {
                    "remove": ["payment_created"],
                    "upsert": [{"id": "payment_confirmed", "owner": "payments"}],
                },
            }
        )

        self.assertIn("payment_created", current.contracts)
        self.assertNotIn("payment_created", updated.contracts)
        self.assertIn("payment_confirmed", updated.contracts)
        self.assertIn("reconciliation", updated.modules)
        self.assertEqual(updated.modules["payments"]["owns"], ["payment_intent", "payment_status"])
        with self.assertRaisesRegex(ValueError, "já existe"):
            current.apply_delta({"modules": {"add": [{"id": "payments"}]}})
        with self.assertRaisesRegex(ValueError, "não existe"):
            current.apply_delta({"modules": {"update": [{"id": "missing"}]}})

    def test_plan_contract_reads_frontmatter_and_applies_sequence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "P01.md"
            path.write_text(
                "---\n"
                '{"id":"P01","depends_on":[],"provides":["refund_created"],'
                '"consumes":["payment_created"],"owns":["refund"],'
                '"acceptance":["refund persistido"],"verifications":["unit"],'
                '"model_delta":{"contracts":{"add":[{"id":"refund_created"}]}}}\n'
                "---\n# P01\n",
                encoding="utf-8",
            )

            plan = PlanContract.from_markdown(path)
            final = ProjectModel.simulate(
                ProjectModel.from_mapping(model_mapping()), [plan]
            )

            self.assertEqual(plan.id, "P01")
            self.assertIn("refund_created", final.contracts)

    def test_plan_contract_v2_parses_typed_tasks_and_rejects_unknown_fields(self) -> None:
        plan = PlanContract.from_mapping(typed_plan())

        self.assertEqual(plan.schema_version, 2)
        self.assertEqual(plan.result, "Pagamento persistido e observável.")
        self.assertEqual(plan.execution, "slice")
        self.assertEqual(plan.tasks[0].id, "T01")
        self.assertEqual(plan.tasks[0].verification.kind, "command")
        self.assertEqual(plan.tasks[0].covers, ("REQ-001",))
        self.assertEqual(plan.to_mapping(), typed_plan())

        with self.assertRaisesRegex(ValueError, "campo desconhecido no plano v2"):
            PlanContract.from_mapping({**typed_plan(), "surprise": True})
        with self.assertRaisesRegex(ValueError, "combinação execution/review"):
            PlanContract.from_mapping(typed_plan(review="per_task"))
        with self.assertRaisesRegex(ValueError, "campo desconhecido na tarefa"):
            TaskContract.from_mapping(
                {**typed_task("T01", covers=["REQ-001"]), "surprise": True}
            )
        with self.assertRaisesRegex(ValueError, "caminho inseguro"):
            TaskContract.from_mapping(
                typed_task("T01", covers=["REQ-001"], files=["../outside.py"])
            )
        with self.assertRaisesRegex(ValueError, "namespace estrangeiro"):
            TaskContract.from_mapping(
                typed_task("T01", covers=["REQ-001"], files=[".planning/STATE.md"])
            )


class CoherenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.current = ProjectModel.from_mapping(model_mapping())

    def valid_plans(self) -> list[PlanContract]:
        return [
            PlanContract.from_mapping(
                {
                    "id": "P01",
                    "provides": ["refund_created"],
                    "consumes": ["payment_created"],
                    "owns": ["refund"],
                    "acceptance": ["refund registrado"],
                    "verifications": ["test_refund"],
                    "model_delta": {
                        "contracts": {"add": [{"id": "refund_created", "owner": "payments"}]}
                    },
                }
            ),
            PlanContract.from_mapping(
                {
                    "id": "P02",
                    "depends_on": ["P01"],
                    "provides": ["refund_notified"],
                    "consumes": ["refund_created"],
                    "owns": ["notification"],
                    "acceptance": ["cliente notificado"],
                    "verifications": ["test_notification"],
                    "model_delta": {
                        "contracts": {"add": [{"id": "refund_notified"}]}
                    },
                }
            ),
            PlanContract.from_mapping(
                {
                    "id": "P03",
                    "depends_on": ["P02"],
                    "provides": ["audit_complete"],
                    "consumes": ["refund_notified"],
                    "owns": ["audit"],
                    "acceptance": ["auditoria completa"],
                    "verifications": ["test_audit"],
                    "model_delta": {
                        "contracts": {"add": [{"id": "audit_complete"}]}
                    },
                }
            ),
        ]

    def test_dependency_graph_combines_declared_and_contract_edges(self) -> None:
        plans = self.valid_plans()
        plans[1] = PlanContract.from_mapping(
            {**plans[1].to_mapping(), "depends_on": []}
        )
        graph = DependencyGraph(plans)

        self.assertEqual(graph.topological_order(), ["P01", "P02", "P03"])
        self.assertEqual(graph.direct_dependents("P01"), {"P02"})
        self.assertEqual(graph.transitive_dependents({"P01"}), {"P02", "P03"})

    def test_task_graph_builds_waves_and_validator_enforces_scope_coverage(self) -> None:
        tasks = [
            TaskContract.from_mapping(typed_task("T01", covers=["REQ-001"])),
            TaskContract.from_mapping(
                typed_task("T02", covers=["NFR-001"], depends_on=["T01"])
            ),
            TaskContract.from_mapping(typed_task("T03", covers=["ERR-001"])),
        ]
        graph = TaskDependencyGraph(tasks)

        self.assertEqual(graph.topological_order(), ["T01", "T02", "T03"])
        self.assertEqual(graph.execution_waves(), [["T01", "T03"], ["T02"]])

        cyclic = [
            TaskContract.from_mapping(
                typed_task("T01", covers=["REQ-001"], depends_on=["T02"])
            ),
            TaskContract.from_mapping(
                typed_task("T02", covers=["REQ-001"], depends_on=["T01"])
            ),
        ]
        with self.assertRaisesRegex(ValueError, "ciclo"):
            TaskDependencyGraph(cyclic).execution_waves()

        plan = PlanContract.from_mapping(
            typed_plan(
                requirements=["REQ-001", "NFR-001", "ERR-001", "INT-001"],
                tasks=[task.to_mapping() for task in tasks],
            )
        )
        findings = StructuralValidator().validate(
            self.current,
            [plan],
            requirements=["REQ-001", "NFR-001", "ERR-001", "INT-001"],
            require_typed_tasks=True,
        )
        codes = {item.code for item in findings}

        self.assertIn("TASK_REQUIREMENT_UNCOVERED", codes)

        invalid = PlanContract.from_mapping(
            typed_plan(
                requirements=["REQ-001"],
                modules=["missing_module"],
                tasks=[typed_task("T01", covers=["REQ-999"], depends_on=["T02"])],
            )
        )
        invalid_findings = StructuralValidator().validate(
            self.current,
            [invalid],
            requirements=["REQ-001"],
            require_typed_tasks=True,
        )
        invalid_codes = {item.code for item in invalid_findings}

        self.assertIn("TASK_COVERS_UNKNOWN_REQUIREMENT", invalid_codes)
        self.assertIn("UNKNOWN_TASK_DEPENDENCY", invalid_codes)
        self.assertIn("UNKNOWN_MODEL_REFERENCE", invalid_codes)

    def test_structural_validator_is_deterministic_for_valid_package(self) -> None:
        plans = self.valid_plans()
        expected = ProjectModel.simulate(self.current, plans)
        validator = StructuralValidator()

        first = validator.validate(self.current, plans, expected)
        second = validator.validate(self.current, plans, expected)

        self.assertEqual([item.to_mapping() for item in first], [item.to_mapping() for item in second])
        self.assertEqual([item for item in first if item.severity is Severity.ERROR], [])

    def test_structural_validator_reports_cycle_order_provider_and_ownership(self) -> None:
        plans = [
            PlanContract.from_mapping(
                {
                    "id": "P02",
                    "depends_on": ["P01"],
                    "provides": ["shared"],
                    "consumes": ["missing_contract"],
                    "owns": ["orders"],
                    "acceptance": ["ok"],
                    "verifications": ["test"],
                }
            ),
            PlanContract.from_mapping(
                {
                    "id": "P01",
                    "depends_on": ["P02"],
                    "provides": ["other"],
                    "owns": ["orders"],
                    "acceptance": ["ok"],
                    "verifications": ["test"],
                }
            ),
        ]

        findings = StructuralValidator().validate(self.current, plans)
        codes = {item.code for item in findings}

        self.assertTrue({"DEPENDENCY_CYCLE", "ORDER_VIOLATION", "MISSING_PROVIDER", "OWNERSHIP_CONFLICT"} <= codes)
        self.assertTrue(all(item.origin == "structural" for item in findings))

    def test_validator_checks_acceptance_verification_journey_guard_and_model(self) -> None:
        broken_model = ProjectModel.from_mapping(
            {
                **model_mapping(),
                "journeys": [{"id": "broken", "path": ["checkout", "missing_component"]}],
            }
        )
        plan = PlanContract.from_mapping(
            {
                "id": "P01",
                "external_effects": [{"id": "send_money", "guard_required": True}],
            }
        )

        findings = StructuralValidator().validate(
            broken_model, [plan], ProjectModel.from_mapping(model_mapping())
        )
        codes = {item.code for item in findings}

        self.assertTrue(
            {
                "MISSING_ACCEPTANCE",
                "MISSING_VERIFICATION",
                "JOURNEY_COMPONENT_MISSING",
                "MISSING_GUARD",
                "MODEL_MISMATCH",
            }
            <= codes
        )

    def test_validator_checks_requirement_contract_removal_and_migration_safety(self) -> None:
        plans = [
            PlanContract.from_mapping(
                {
                    "id": "P01",
                    "acceptance": ["legado removido"],
                    "verifications": ["test_removal"],
                    "model_delta": {"contracts": {"remove": ["payment_created"]}},
                    "migrations": [
                        {
                            "id": "drop_payment_created",
                            "after": ["P02"],
                            "destructive": True,
                        }
                    ],
                }
            ),
            PlanContract.from_mapping(
                {
                    "id": "P02",
                    "consumes": ["payment_created"],
                    "acceptance": ["consumer migrado"],
                    "verifications": ["test_consumer"],
                }
            ),
        ]

        findings = StructuralValidator().validate(
            self.current, plans, requirements=["PAY-001"]
        )
        codes = {item.code for item in findings}

        self.assertTrue(
            {
                "CONTRACT_REMOVED_BEFORE_CONSUMERS",
                "MIGRATION_ORDER_INVALID",
                "MIGRATION_COMPATIBILITY_MISSING",
                "REQUIREMENT_WITHOUT_PLAN",
            }
            <= codes
        )

    def test_impact_analyzer_classifies_local_direct_transitive_and_global(self) -> None:
        graph = DependencyGraph(self.valid_plans())
        analyzer = ImpactAnalyzer(graph, self.current)

        local = analyzer.analyze("P03", changed_contracts=["audit_complete"])
        direct_graph = DependencyGraph(self.valid_plans()[:2])
        direct = ImpactAnalyzer(direct_graph, self.current).analyze(
            "P01", changed_contracts=["refund_created"]
        )
        transitive = analyzer.analyze("P01", changed_contracts=["refund_created"])
        global_result = analyzer.analyze(
            "P01", changed_invariants=["single_payment_owner"]
        )

        self.assertEqual(local.radius, "local")
        self.assertEqual(direct.radius, "direct")
        self.assertEqual(direct.stale_plans, ("P02",))
        self.assertEqual(transitive.radius, "transitive")
        self.assertEqual(transitive.stale_plans, ("P02", "P03"))
        self.assertEqual(global_result.radius, "global")
        self.assertEqual(global_result.stale_plans, ("P02", "P03"))

    def test_impact_analyzer_uses_interfaces_data_migrations_journeys_and_effects(self) -> None:
        plans = [
            PlanContract.from_mapping(
                {
                    "id": "P01",
                    "provides": ["payment_created"],
                    "acceptance": ["ok"],
                    "verifications": ["test_p01"],
                }
            ),
            PlanContract.from_mapping(
                {
                    "id": "P02",
                    "touches": ["payment_gateway", "payment_intent"],
                    "migrations": [{"id": "payment_backfill"}],
                    "external_effects": [{"id": "charge_customer", "guards": ["idempotency"]}],
                    "acceptance": ["ok"],
                    "verifications": ["test_p02"],
                }
            ),
            PlanContract.from_mapping(
                {
                    "id": "P03",
                    "depends_on": ["P02"],
                    "acceptance": ["ok"],
                    "verifications": ["test_p03"],
                }
            ),
        ]
        analyzer = ImpactAnalyzer(DependencyGraph(plans), self.current)

        result = analyzer.analyze(
            "P01",
            changed_interfaces=["payment_gateway"],
            changed_data=["payment_intent"],
            changed_migrations=["payment_backfill"],
            changed_effects=["charge_customer"],
            changed_journeys=["checkout_confirmation"],
        )

        self.assertEqual(result.radius, "transitive")
        self.assertEqual(result.direct_plans, ("P02",))
        self.assertEqual(result.transitive_plans, ("P03",))
        self.assertEqual(result.affected_journeys, ("checkout_confirmation",))

    def test_semantic_reviewer_normalizes_without_turning_opinion_into_error(self) -> None:
        reviewer = SemanticReviewer()
        review = reviewer.normalize(
            [
                {
                    "code": "SPECULATIVE_ABSTRACTION",
                    "severity": "ERROR",
                    "phases": ["P02"],
                    "evidence": "Não existe consumidor aprovado.",
                    "expected_fix": "Remover ou justificar.",
                },
                {
                    "code": "STACK_NOTE",
                    "severity": "INFO",
                    "evidence": "SDK oficial disponível.",
                },
            ],
            prompt="revise o pacote",
            inputs="digest-do-pacote",
            sources=["https://example.test/docs"],
        )

        self.assertEqual(review.findings[0].severity, Severity.WARNING)
        self.assertTrue(review.available)
        self.assertEqual(len(review.prompt_digest), 64)
        self.assertNotIn("revise o pacote", review.to_mapping().values())
        self.assertTrue(review.has_blockers())

        accepted = review.findings[0].accept("Decisão aprovada pelo owner.")
        self.assertEqual(accepted.status, FindingStatus.ACCEPTED_WITH_JUSTIFICATION)
        with self.assertRaisesRegex(ValueError, "justificativa"):
            review.findings[0].accept("  ")

        normalized_code = reviewer.normalize(
            [
                {
                    "code": "responsibility-mismatch",
                    "severity": "warning",
                    "evidence": "Responsabilidade no módulo errado.",
                    "expected_fix": "Mover para o owner.",
                }
            ]
        )
        self.assertEqual(normalized_code.findings[0].code, "RESPONSIBILITY_MISMATCH")

    def test_unavailable_semantic_review_never_looks_like_a_pass(self) -> None:
        review = SemanticReviewer().unavailable("provider indisponível")

        self.assertFalse(review.available)
        self.assertTrue(review.has_blockers())
        self.assertEqual(review.findings[0].code, "SEMANTIC_REVIEW_UNAVAILABLE")
        self.assertEqual(review.findings[0].severity, Severity.WARNING)

    def test_finding_rejects_semantic_error_and_invalid_accepted_status(self) -> None:
        with self.assertRaisesRegex(ValueError, "semântico"):
            Finding(
                code="BAD",
                severity=Severity.ERROR,
                origin="semantic",
                evidence="opinião",
                expected_fix="corrigir",
            )
        with self.assertRaisesRegex(ValueError, "justificativa"):
            Finding(
                code="WARN",
                severity=Severity.WARNING,
                origin="semantic",
                evidence="risco",
                expected_fix="justificar",
                status=FindingStatus.ACCEPTED_WITH_JUSTIFICATION,
            )


if __name__ == "__main__":
    unittest.main()
