"""Fixtures de comportamento do context pack operacional 0.4."""

from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "_shared" / "scripts"
import sys

sys.path.insert(0, str(SCRIPTS))

from bm_context import (  # noqa: E402
    DEFAULT_MAX_BYTES,
    ContextPackError,
    compile_context_pack,
    verify_context_pack,
)


def frontmatter(value: dict[str, object], title: str) -> str:
    return (
        "---\n"
        + json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        + f"\n---\n# {title}\n"
    )


def git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=False
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr)
    return completed.stdout.strip()


def task(identifier: str, *, covers: list[str], depends_on: list[str]) -> dict[str, object]:
    return {
        "id": identifier,
        "name": f"Entregar {identifier}",
        "result": f"Resultado {identifier}",
        "covers": covers,
        "depends_on": depends_on,
        "files": [f"src/{identifier.lower()}.py"],
        "action": "Aplicar D-001 pelo contrato session.",
        "verify": {
            "kind": "command",
            "run": f"python3 -m unittest tests.test_{identifier.lower()}",
            "proves": f"{identifier} entregue",
        },
        "done": f"{identifier} observável",
        "risk_seam": "session-state",
    }


def plan(
    identifier: str,
    *,
    requirements: list[str],
    depends_on: list[str] | None = None,
    provides: list[str] | None = None,
    consumes: list[str] | None = None,
    tasks: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": 2,
        "id": identifier,
        "status": "planned",
        "result": f"Resultado {identifier}",
        "requirements": requirements,
        "acceptance": [f"Aceite {identifier}"],
        "depends_on": depends_on or [],
        "provides": provides or [],
        "consumes": consumes or [],
        "modules": ["auth"] if identifier == "P01" else [],
        "interfaces": [],
        "ownership": [],
        "data": [],
        "model_delta": (
            {"contracts": {"add": [{"id": "order"}]}}
            if identifier == "P01"
            else {}
        ),
        "migrations": [],
        "effects": [],
        "rollback": f"Reverter {identifier}",
        "verifications": [f"python3 -m unittest tests.test_{identifier.lower()}"],
        "future_constraints": ["Respeitar D-001"] if identifier == "P01" else [],
        "execution": "slice",
        "review": "per_slice",
        "tasks": tasks or [task("T01", covers=requirements, depends_on=[])],
    }


class ContextPackScenarios(unittest.TestCase):
    def make_repo(self, base: Path) -> Path:
        root = base / "repo"
        root.mkdir()
        git(root, "init", "-b", "main")
        git(root, "config", "user.name", "BM Test")
        git(root, "config", "user.email", "test@example.invalid")

        bianchini = root / ".bianchini"
        change = bianchini / "changes/C001-context"
        current = bianchini / "current"
        for directory in (
            change / "plans",
            change / "specs/expected",
            change / "results/tasks/P01",
            current / "specs",
            bianchini / "quick/Q012-small",
            bianchini / "debug/active",
            bianchini / "archive/C000-old",
        ):
            directory.mkdir(parents=True, exist_ok=True)

        state = {
            "schema_version": 1,
            "method": "0.4",
            "active_work": {"kind": "change", "id": "C001-context"},
            "current_unit": "P01/T01",
            "status": "active",
            "blockers": ["aguardar ambiente real"],
            "next_action": "Executar T01",
            "last_completed": {"kind": "plan", "id": "P00"},
            "pointers": {
                "architecture": ".bianchini/current/ARCHITECTURE.md",
                "system_model": ".bianchini/current/SYSTEM_MODEL.md",
                "specs": ".bianchini/current/specs",
                "coherence": ".bianchini/changes/C001-context/COHERENCE.md",
            },
            "digest": None,
            "updated_at": "2026-09-01T12:00:00Z",
        }
        (bianchini / "STATE.md").write_text(
            frontmatter(state, "Estado atual"), encoding="utf-8"
        )
        (change / "SCOPE.md").write_text(
            "# Escopo\n\n"
            "## REQ-001 — Criar pedido\n\nFluxo obrigatório.\n\n"
            "## RSK-001 — Concorrência\n\nExige guard de escrita.\n\n"
            "## REQ-002 — Relatório irrelevante\n\nNão pertence à unidade.\n",
            encoding="utf-8",
        )
        (change / "ARCHITECTURE.md").write_text(
            "# Arquitetura\n\n"
            "## D-001 — Persistência\n\nUsar escrita durável.\n\n"
            "## D-999 — Irrelevante\n\nNão carregar.\n",
            encoding="utf-8",
        )
        model = {
            "schema_version": 1,
            "modules": [{"id": "auth", "contracts": ["session"]}, {"id": "other"}],
            "interfaces": [],
            "capabilities": [],
            "contracts": [{"id": "session"}, {"id": "order"}, {"id": "other"}],
            "ownership": [],
            "data": [],
            "integrations": [],
            "journeys": [],
            "invariants": [],
            "effects": [],
        }
        (change / "SYSTEM_MODEL.md").write_text(
            frontmatter(model, "Modelo final"), encoding="utf-8"
        )
        (current / "SYSTEM_MODEL.md").write_text(
            frontmatter(model, "Modelo atual"), encoding="utf-8"
        )
        (current / "ARCHITECTURE.md").write_text("# Atual\n", encoding="utf-8")

        plans = [
            plan("P00", requirements=["REQ-001"], provides=["session"]),
            plan(
                "P01",
                requirements=["REQ-001", "RSK-001"],
                depends_on=["P00"],
                provides=["order"],
                consumes=["session"],
                tasks=[
                    task("T00", covers=["REQ-001"], depends_on=[]),
                    task("T01", covers=["REQ-001", "RSK-001"], depends_on=["T00"]),
                    task("T02", covers=["REQ-001"], depends_on=[]),
                ],
            ),
            plan("P02", requirements=["REQ-002"], consumes=["order"]),
            plan("P99", requirements=["REQ-002"]),
        ]
        for value in plans:
            (change / f"plans/{value['id']}.md").write_text(
                frontmatter(value, str(value["id"])), encoding="utf-8"
            )
        (change / "ROADMAP.md").write_text(
            frontmatter(
                {
                    "schema_version": 1,
                    "phases": ["P00", "P01", "P02", "P99"],
                    "status": {"P00": "completed", "P01": "active"},
                },
                "Roadmap",
            ),
            encoding="utf-8",
        )
        (change / "COHERENCE.md").write_text(
            frontmatter(
                {
                    "schema_version": 2,
                    "planning_contract": 2,
                    "spec_contract": 1,
                    "findings": [
                        {
                            "code": "OPEN_P01",
                            "status": "open",
                            "phases": ["P01"],
                            "evidence": "guard pendente",
                        },
                        {
                            "code": "RESOLVED_P01",
                            "status": "resolved",
                            "phases": ["P01"],
                        },
                        {
                            "code": "OPEN_P99",
                            "status": "open",
                            "phases": ["P99"],
                        },
                    ],
                },
                "Coerência",
            ),
            encoding="utf-8",
        )

        spec_text = (
            "# Contratos\n\n"
            "## SPEC-001: Pedido\n\nContrato necessário para REQ-001.\n\n"
            "## SPEC-002: Relatório\n\nCONTEUDO_IRRELEVANTE_SPEC.\n"
        )
        (change / "specs/expected/system.md").write_text(spec_text, encoding="utf-8")
        manifest = {
            "schema_version": 1,
            "spec_contract": 1,
            "specs": [
                {
                    "id": "system",
                    "path": "system.md",
                    "requirements": [
                        {"id": "SPEC-001", "scope": ["REQ-001"]},
                        {"id": "SPEC-002", "scope": ["REQ-002"]},
                    ],
                }
            ],
            "risk_coverage": [
                {
                    "scope": "RSK-001",
                    "kind": "guard",
                    "target": "optimistic-lock",
                }
            ],
        }
        (change / "specs/MANIFEST.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (current / "specs/MANIFEST.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (current / "specs/system.md").write_text(spec_text, encoding="utf-8")

        for relative, label in (
            ("results/P00.md", "PROVIDER_RESULT_REQUIRED"),
            ("results/P99.md", "IRRELEVANT_RESULT_MUST_NOT_LOAD"),
            ("results/tasks/P01/T00.md", "TASK_DEPENDENCY_REQUIRED"),
            ("results/tasks/P01/T02.md", "IRRELEVANT_TASK_RESULT"),
        ):
            path = change / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(frontmatter({"status": "completed", "label": label}, label), encoding="utf-8")
        ledger = change / "results/LEDGER.jsonl"
        ledger.write_text(
            "".join(json.dumps({"event": index}) + "\n" for index in range(25)),
            encoding="utf-8",
        )

        quick = bianchini / "quick/Q012-small"
        (quick / "BRIEF.md").write_text(
            frontmatter(
                {
                    "id": "Q012-small",
                    "objective": "Ajuste pequeno",
                    "gates": ["python3 -m unittest tests.test_small"],
                    "scope": ["REQ-001"],
                    "blockers": [],
                },
                "Quick",
            ),
            encoding="utf-8",
        )
        (quick / "PROGRESS.md").write_text(
            frontmatter({"events": [{"summary": "em andamento"}]}, "Progresso"),
            encoding="utf-8",
        )
        (bianchini / "debug/active/D004-login.md").write_text(
            frontmatter(
                {
                    "id": "D004-login",
                    "stage": "diagnosed",
                    "objective": "Corrigir login",
                    "root_cause": "cache",
                    "events": [{"event": "reproduced", "evidence": "teste"}],
                    "blockers": ["aguardar fixture"],
                },
                "Debug",
            ),
            encoding="utf-8",
        )
        (bianchini / "archive/C000-old/SECRET.md").write_text(
            "ARCHIVE_MUST_NOT_LOAD\n", encoding="utf-8"
        )

        git(root, "add", ".")
        git(root, "commit", "-m", "fixture context pack")
        return root

    def test_task_pack_is_minimal_complete_and_dependency_aware(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = self.make_repo(Path(temp))
            result = compile_context_pack(root, "C001/P01/T01")
            payload = json.loads((root / str(result["path"])).read_text(encoding="utf-8"))
            context = payload["context"]

            self.assertEqual(DEFAULT_MAX_BYTES, 16_384)
            self.assertEqual(payload["unit"], "C001/P01/T01")
            self.assertEqual(context["plan"]["id"], "P01")
            self.assertEqual(context["task"]["id"], "T01")
            self.assertEqual(
                [item["id"] for item in context["scope"]], ["REQ-001", "RSK-001"]
            )
            self.assertEqual(
                [item["id"] for item in context["spec_requirements"]], ["SPEC-001"]
            )
            self.assertEqual(
                context["risk_coverage"],
                [
                    {
                        "scope": "RSK-001",
                        "kind": "guard",
                        "target": "optimistic-lock",
                    }
                ],
            )
            self.assertIn("PROVIDER_RESULT_REQUIRED", json.dumps(context))
            self.assertIn("TASK_DEPENDENCY_REQUIRED", json.dumps(context))
            self.assertNotIn("IRRELEVANT_RESULT_MUST_NOT_LOAD", json.dumps(context))
            self.assertNotIn("IRRELEVANT_TASK_RESULT", json.dumps(context))
            self.assertNotIn("CONTEUDO_IRRELEVANTE_SPEC", json.dumps(context))
            self.assertEqual([item["id"] for item in context["affected_consumers"]], ["P02"])
            self.assertEqual([item["id"] for item in context["architecture_decisions"]], ["D-001"])
            self.assertEqual(context["open_findings"][0]["code"], "OPEN_P01")
            self.assertEqual(context["ledger_tail"][0], {"event": 5})
            self.assertEqual(len(context["ledger_tail"]), 20)
            self.assertIn("task:C001/P01/T01", payload["required_refs"])
            self.assertNotIn("METHOD_CONTRACT", json.dumps(payload))
            self.assertNotIn("ARCHIVE_MUST_NOT_LOAD", json.dumps(payload))
            self.assertFalse(any(".planning" in source for source in payload["sources"]))

    def test_plan_quick_debug_and_rc_have_behavior_fixtures(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = self.make_repo(Path(temp))
            plan_pack = compile_context_pack(root, "C001/P01")
            quick_pack = compile_context_pack(root, "Q012")
            debug_pack = compile_context_pack(root, "D004")
            for result, unit in (
                (plan_pack, "C001/P01"),
                (quick_pack, "Q012"),
                (debug_pack, "D004"),
            ):
                self.assertEqual(verify_context_pack(root, root / str(result["path"]))["unit"], unit)

            with self.assertRaisesRegex(ContextPackError, "PACK_INCOMPLETE"):
                compile_context_pack(root, "RC:build-a")

            homologation = root / ".bianchini/changes/C001-context/results/HOMOLOGATION.md"
            homologation.write_text(
                frontmatter(
                    {
                        "schema_version": 1,
                        "fingerprint": "build-a",
                        "change": "C001-context",
                        "status": "running",
                        "gates": ["release-tests"],
                        "blockers": [],
                        "findings": [{"id": "visual-review", "status": "open"}],
                        "required_refs": [
                            ".bianchini/changes/C001-context/results/P00.md"
                        ],
                    },
                    "Homologação",
                ),
                encoding="utf-8",
            )
            rc_pack = compile_context_pack(root, "RC:build-a")
            rc_payload = json.loads((root / str(rc_pack["path"])).read_text(encoding="utf-8"))
            self.assertEqual(rc_payload["context"]["release_candidate"]["fingerprint"], "build-a")
            self.assertIn("release-candidate:build-a", rc_payload["required_refs"])

    def test_cache_and_verify_bind_identity_head_and_source_digests(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = self.make_repo(Path(temp))
            first = compile_context_pack(root, "C001/P01/T01")
            second = compile_context_pack(root, "C001/P01/T01")
            self.assertFalse(first["cache_hit"])
            self.assertTrue(second["cache_hit"])
            self.assertEqual(first["digest"], second["digest"])
            self.assertEqual(first["bytes"], second["bytes"])

            scope = root / ".bianchini/changes/C001-context/SCOPE.md"
            scope.write_text(scope.read_text(encoding="utf-8") + "\nDrift.\n", encoding="utf-8")
            with self.assertRaisesRegex(ContextPackError, "STALE_EVIDENCE"):
                verify_context_pack(root, root / str(first["path"]))
            rebuilt = compile_context_pack(root, "C001/P01/T01")
            self.assertFalse(rebuilt["cache_hit"])
            self.assertNotEqual(rebuilt["digest"], first["digest"])

            git(root, "add", ".bianchini/changes/C001-context/SCOPE.md")
            git(root, "commit", "-m", "change head")
            with self.assertRaisesRegex(ContextPackError, "STALE_EVIDENCE"):
                verify_context_pack(root, root / str(rebuilt["path"]))
            after_head = compile_context_pack(root, "C001/P01/T01")
            self.assertFalse(after_head["cache_hit"])

    def test_only_relevant_approved_lesson_enters_pack_and_conflict_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = self.make_repo(Path(temp))
            lessons = root / ".bianchini/current/lessons"
            lessons.mkdir()
            relevant = {
                "id": "L001",
                "status": "approved",
                "active": True,
                "tags": {"seams": ["session-state"]},
                "lesson": "Usar escrita durável.",
                "conflicts": [],
            }
            irrelevant = {
                "id": "L002",
                "status": "approved",
                "tags": {"paths": ["src/other.py"]},
                "lesson": "Não deve entrar.",
                "conflicts": [],
            }
            pending = {
                "id": "L003",
                "status": "pending",
                "tags": ["session-state"],
                "lesson": "Não aprovado.",
                "conflicts": [],
            }
            for value in (relevant, irrelevant, pending):
                (lessons / f"{value['id']}.json").write_text(
                    json.dumps(value, sort_keys=True) + "\n", encoding="utf-8"
                )
            result = compile_context_pack(root, "C001/P01/T01")
            payload = json.loads((root / str(result["path"])).read_text(encoding="utf-8"))
            self.assertEqual(
                [item["id"] for item in payload["context"]["approved_lessons"]],
                ["L001"],
            )

            conflicting = {
                "id": "L004",
                "status": "approved",
                "tags": ["session-state"],
                "lesson": "Conflito explícito.",
                "conflicts": ["L001"],
            }
            (lessons / "L004.json").write_text(
                json.dumps(conflicting, sort_keys=True) + "\n", encoding="utf-8"
            )
            with self.assertRaisesRegex(ContextPackError, "PACK_INCOMPLETE"):
                compile_context_pack(root, "C001/P01/T01")

    def test_large_pack_fails_without_output_or_truncation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = self.make_repo(Path(temp))
            output = root / ".bianchini/.runtime/context/too-small.json"
            with self.assertRaisesRegex(
                ContextPackError, r"PACK_TOO_LARGE.*largest_consumers"
            ):
                compile_context_pack(
                    root, "C001/P01/T01", output=output, max_bytes=256
                )
            self.assertFalse(output.exists())

    def test_output_is_confined_and_rejects_symlink_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = self.make_repo(base)
            with self.assertRaisesRegex(ContextPackError, "PATH_UNSAFE"):
                compile_context_pack(root, "C001/P01", output=base / "escape.json")

            internal = root / ".bianchini/context-real"
            internal.mkdir()
            internal_link = root / ".bianchini/context-link"
            internal_link.symlink_to(internal, target_is_directory=True)
            with self.assertRaisesRegex(ContextPackError, "PATH_UNSAFE"):
                compile_context_pack(
                    root, "C001/P01", output=internal_link / "pack.json"
                )

            outside = base / "outside"
            outside.mkdir()
            link = root / ".bianchini/.runtime"
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ContextPackError, "PATH_UNSAFE"):
                compile_context_pack(root, "C001/P01")

    def test_unknown_or_incomplete_units_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = self.make_repo(Path(temp))
            for unit in (
                "C001",
                "C001/P1",
                "C001/P01/T1",
                "Q12",
                "D04",
                "RC:",
                "../C001/P01",
                "C999/P01",
                "C001/P99/T99",
            ):
                with self.subTest(unit=unit), self.assertRaises(ContextPackError):
                    compile_context_pack(root, unit)


if __name__ == "__main__":
    unittest.main()
