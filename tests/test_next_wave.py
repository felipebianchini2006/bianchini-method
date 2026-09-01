"""Fixtures determinísticas da projeção somente leitura de próxima onda."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "_shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import bm_spec_package  # noqa: E402
from bm_project_model import PlanContract, ProjectModel  # noqa: E402
from bm_wave import WaveError, next_wave  # noqa: E402


def document(value: dict[str, object], title: str) -> str:
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


def task(identifier: str, *, depends_on: list[str] | None = None) -> dict[str, object]:
    return {
        "id": identifier,
        "name": f"Entregar {identifier}",
        "result": f"Resultado {identifier}",
        "covers": ["REQ-001"],
        "depends_on": depends_on or [],
        "files": [f"src/{identifier.lower()}.py"],
        "action": "Implementar pelo seam aprovado.",
        "verify": {
            "kind": "command",
            "run": f"python3 -m unittest tests.test_{identifier.lower()}",
            "proves": f"{identifier} entregue",
        },
        "done": f"{identifier} observável",
        "risk_seam": "wave",
    }


def plan(
    identifier: str,
    *,
    depends_on: list[str] | None = None,
    tasks: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": 2,
        "id": identifier,
        "status": "planned",
        "result": f"Resultado {identifier}",
        "requirements": ["REQ-001"],
        "acceptance": [f"Aceite {identifier}"],
        "depends_on": depends_on or [],
        "provides": [],
        "consumes": [],
        "modules": [],
        "interfaces": [],
        "ownership": [],
        "data": [],
        "model_delta": {},
        "migrations": [],
        "effects": [],
        "rollback": f"Reverter {identifier}",
        "verifications": [f"verify-{identifier}"],
        "future_constraints": [],
        "execution": "slice",
        "review": "per_slice",
        "tasks": tasks or [task("T01")],
    }


def empty_model() -> dict[str, object]:
    return {
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


def stable_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def read_payload(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8").split("---", 2)[1])


def write_payload(path: Path, payload: dict[str, object]) -> None:
    path.write_text(document(payload, path.stem), encoding="utf-8")


def task_result_payload(
    change_id: str,
    plan_id: str,
    task_value: dict[str, object],
    *,
    result: str = "Entrega comprovada",
    verification: list[str] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "change": change_id,
        "plan": plan_id,
        "task": task_value["id"],
        "status": "completed",
        "expected_result": task_value["result"],
        "result": result,
        "covers": task_value["covers"],
        "verification": verification or ["fixture verification"],
        "completed_at": "2026-09-01T12:30:00+00:00",
    }


def write_task_result(
    change: Path,
    plan_value: dict[str, object],
    task_value: dict[str, object],
    *,
    result: str = "Entrega comprovada",
    verification: list[str] | None = None,
) -> None:
    destination = (
        change
        / "results/tasks"
        / str(plan_value["id"])
        / f"{task_value['id']}.md"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        document(
            task_result_payload(
                change.name,
                str(plan_value["id"]),
                task_value,
                result=result,
                verification=verification,
            ),
            str(task_value["id"]),
        ),
        encoding="utf-8",
    )


def write_plan_result(change: Path, plan_value: dict[str, object]) -> None:
    evidence = ["fixture verification"]
    summary = "Entrega comprovada"
    for task_value in plan_value["tasks"]:
        write_task_result(
            change,
            plan_value,
            task_value,
            result=summary,
            verification=evidence,
        )
    delta = plan_value["model_delta"]
    model_digest = ProjectModel.from_mapping(empty_model()).digest()
    payload = {
        "schema_version": 1,
        "change": change.name,
        "plan": plan_value["id"],
        "status": "completed",
        "result": summary,
        "promised_delta_digest": stable_digest(delta),
        "actual_delta": delta,
        "actual_delta_digest": stable_digest(delta),
        "model_before_digest": model_digest,
        "model_after_digest": model_digest,
        "verification": evidence,
        "completed_tasks": [item["id"] for item in plan_value["tasks"]],
        "impact": {
            "radius": "local",
            "stale_plans": [],
            "reason": "entrega equivalente ao delta aprovado",
        },
        "completed_at": "2026-09-01T12:30:00+00:00",
    }
    (change / f"results/{plan_value['id']}.md").write_text(
        document(payload, str(plan_value["id"])), encoding="utf-8"
    )


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        digest.update(relative.encode())
        if path.is_symlink():
            digest.update(b"SYMLINK")
            digest.update(str(path.readlink()).encode())
        elif path.is_file():
            digest.update(path.read_bytes())
    return digest.hexdigest()


class NextWaveScenarios(unittest.TestCase):
    def make_repo(self, base: Path) -> tuple[Path, Path]:
        root = base / "repo"
        root.mkdir()
        git(root, "init", "-b", "main")
        git(root, "config", "user.name", "BM Test")
        git(root, "config", "user.email", "test@example.invalid")
        bianchini = root / ".bianchini"
        change = bianchini / "changes/C001-wave"
        (change / "plans").mkdir(parents=True)
        (change / "results/tasks").mkdir(parents=True)

        current = bianchini / "current"
        current_specs = current / "specs"
        current_specs.mkdir(parents=True)
        (current / "SYSTEM_MODEL.md").write_text(
            document(empty_model(), "Modelo atual"), encoding="utf-8"
        )
        (current_specs / "MANIFEST.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "spec_contract": 1,
                    "specs": [],
                    "risk_coverage": [],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        (change / "SCOPE.md").write_text(
            "# Escopo\n\n### REQ-001 — Onda\n\nExecutar onda aprovada.\n",
            encoding="utf-8",
        )
        (change / "RESEARCH.md").write_text("# Pesquisa\n\nFixture.\n", encoding="utf-8")
        (change / "ARCHITECTURE.md").write_text(
            "# Arquitetura\n\nFixture.\n", encoding="utf-8"
        )
        (change / "SYSTEM_MODEL.md").write_text(
            document(empty_model(), "Modelo esperado"), encoding="utf-8"
        )

        values = [
            plan(
                "P01",
                tasks=[task("T01"), task("T02"), task("T03", depends_on=["T01"])],
            ),
            plan("P02"),
            plan("P03", depends_on=["P01"]),
            plan("P04"),
            plan("P05"),
            plan("P06"),
        ]
        for value in values:
            (change / f"plans/{value['id']}.md").write_text(
                document(value, str(value["id"])), encoding="utf-8"
            )

        roadmap = {
            "schema_version": 1,
            "planning_contract": 2,
            "phases": [
                {
                    "id": value["id"],
                    "result": value["result"],
                    "depends_on": value["depends_on"],
                    "requirements": value["requirements"],
                    "execution": value["execution"],
                    "tasks": [item["id"] for item in value["tasks"]],
                }
                for value in values
            ],
        }
        (change / "ROADMAP.md").write_text(
            document(roadmap, "Roadmap"), encoding="utf-8"
        )
        expected_specs = change / "specs/expected"
        expected_specs.mkdir(parents=True)
        (expected_specs / "system.md").write_text(
            "# Sistema\n\n## SPEC-001: Onda\n\nExecutar REQ-001.\n",
            encoding="utf-8",
        )
        manifest_path = change / "specs/MANIFEST.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "spec_contract": 1,
                    "specs": [
                        {
                            "id": "system",
                            "path": "system.md",
                            "requirements": [
                                {"id": "SPEC-001", "scope": ["REQ-001"]}
                            ],
                        }
                    ],
                    "risk_coverage": [],
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        _, rendered_diff = bm_spec_package.derive_directory_diff(
            root=root,
            base=current_specs,
            target=expected_specs,
            manifest_path=manifest_path,
        )
        (change / "specs/diff.md").write_text(rendered_diff, encoding="utf-8")
        artifact_manifest = {
            relative: hashlib.sha256((change / relative).read_bytes()).hexdigest()
            for relative in [
                "SCOPE.md",
                "RESEARCH.md",
                "ARCHITECTURE.md",
                "SYSTEM_MODEL.md",
                "ROADMAP.md",
                *(f"plans/{value['id']}.md" for value in values),
            ]
        }
        findings = [
            {
                "code": "P05_BLOCKED",
                "severity": "WARNING",
                "status": "open",
                "phases": ["P05"],
                "evidence": "guard pendente",
            },
            {
                "code": "P02_RESOLVED",
                "severity": "ERROR",
                "status": "resolved",
                "phases": ["P02"],
            },
        ]
        semantic = {"available": True, "findings": []}
        coherence_contract = {
            "schema_version": 2,
            "planning_contract": 2,
            "spec_contract": 1,
        }
        spec_package = bm_spec_package.load_spec_package(
            change_dir=change,
            current_specs=current_specs,
            scope_path=change / "SCOPE.md",
            coherence=coherence_contract,
        )
        spec_digest_payload = {
            "spec_contract": spec_package["spec_contract"],
            "spec_base_digest": spec_package["base_digest"],
            "spec_target_digest": spec_package["target_digest"],
            "spec_manifest_digest": spec_package["manifest_digest"],
            "spec_diff_digest": spec_package["diff_digest"],
        }
        review_input_digest = stable_digest(
            {
                "planning_contract": 2,
                "artifact_manifest": artifact_manifest,
                "spec_package": spec_digest_payload,
            }
        )
        plan_contracts = [PlanContract.from_mapping(value) for value in values]
        package_digest = stable_digest(
            {
                "current": ProjectModel.from_mapping(empty_model()).to_mapping(),
                "expected": ProjectModel.from_mapping(empty_model()).to_mapping(),
                "plans": [contract.to_mapping() for contract in plan_contracts],
                "findings": findings,
                "semantic": semantic,
                "planning_contract": 2,
                "artifact_manifest": artifact_manifest,
                "spec_package": spec_digest_payload,
            }
        )
        coherence = {
            "schema_version": 2,
            "planning_contract": 2,
            "spec_contract": 1,
            "change": "C001-wave",
            "status": "approved_with_stale",
            "digest": package_digest,
            "approval": {
                "digest": package_digest,
                "approved_by": "human:test",
                "approved_at": "2026-09-01T12:00:00Z",
            },
            "artifact_manifest": artifact_manifest,
            "review_input_digest": review_input_digest,
            "stale_plans": ["P04"],
            "findings": findings,
            "semantic": semantic,
            **spec_digest_payload,
        }
        (change / "COHERENCE.md").write_text(
            document(coherence, "Coerência"), encoding="utf-8"
        )
        state = {
            "schema_version": 1,
            "method": "0.4",
            "active_work": {"kind": "change", "id": "C001-wave", "status": "approved"},
            "current_unit": "P01",
            "status": "approved",
            "blockers": [],
            "next_action": "Executar próxima onda.",
            "last_completed": None,
            "pointers": {
                "architecture": ".bianchini/current/ARCHITECTURE.md",
                "system_model": ".bianchini/current/SYSTEM_MODEL.md",
                "specs": ".bianchini/current/specs",
                "coherence": ".bianchini/changes/C001-wave/COHERENCE.md",
            },
            "digest": package_digest,
            "updated_at": "2026-09-01T12:00:00Z",
        }
        (bianchini / "STATE.md").write_text(document(state, "Estado"), encoding="utf-8")
        write_plan_result(change, values[-1])
        git(root, "add", ".")
        git(root, "commit", "-m", "fixture wave")
        return root, change

    def test_next_wave_is_deterministic_parallel_and_excludes_stale_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root, change = self.make_repo(Path(temp))
            before = tree_digest(root)
            first = next_wave(root, "C001")
            second = next_wave(root, "C001-wave")
            after = tree_digest(root)

            self.assertEqual(first, second)
            self.assertEqual(before, after)
            self.assertEqual(first["change"], "C001-wave")
            self.assertEqual(
                first["package_digest"], read_payload(change / "COHERENCE.md")["digest"]
            )
            self.assertEqual(
                first["roadmap_digest"],
                hashlib.sha256((change / "ROADMAP.md").read_bytes()).hexdigest(),
            )
            self.assertEqual(
                first["eligible_wave"],
                ["C001/P01/T01", "C001/P01/T02", "C001/P02/T01"],
            )
            self.assertEqual(
                [item["pack_identity"] for item in first["parallel_units"]],
                first["eligible_wave"],
            )
            self.assertTrue(
                all(item["dependencies_satisfied"] == [] for item in first["parallel_units"])
            )
            self.assertEqual(
                first["stale_units"],
                [{"identity": "C001/P04/T01", "reason": "plan_stale"}],
            )
            self.assertEqual(
                first["blocked_units"],
                [
                    {
                        "identity": "C001/P05/T01",
                        "reason": "open_finding",
                        "details": ["P05_BLOCKED"],
                    }
                ],
            )
            self.assertEqual(
                first["waiting_units"],
                [
                    {
                        "identity": "C001/P01/T03",
                        "reason": "task_dependencies_pending",
                        "pending": ["C001/P01/T01"],
                    },
                    {
                        "identity": "C001/P03/T01",
                        "reason": "plan_dependencies_pending",
                        "pending": ["C001/P01"],
                    },
                ],
            )
            self.assertEqual(first["completed_units"], ["C001/P06"])

    def test_completed_task_advances_local_wave_and_records_satisfied_dependency(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root, change = self.make_repo(Path(temp))
            p01 = plan(
                "P01",
                tasks=[task("T01"), task("T02"), task("T03", depends_on=["T01"])],
            )
            write_task_result(change, p01, p01["tasks"][0])

            projected = next_wave(root, "C001")
            self.assertEqual(
                projected["eligible_wave"],
                ["C001/P01/T02", "C001/P01/T03", "C001/P02/T01"],
            )
            t03 = next(
                item
                for item in projected["parallel_units"]
                if item["identity"] == "C001/P01/T03"
            )
            self.assertEqual(t03["dependencies_satisfied"], ["C001/P01/T01"])
            self.assertIn("C001/P01/T01", projected["completed_units"])

    def test_completed_plan_unlocks_dependent_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root, change = self.make_repo(Path(temp))
            p01 = plan(
                "P01",
                tasks=[task("T01"), task("T02"), task("T03", depends_on=["T01"])],
            )
            write_plan_result(change, p01)

            projected = next_wave(root, "C001")
            self.assertEqual(
                projected["eligible_wave"], ["C001/P02/T01", "C001/P03/T01"]
            )
            p03 = next(
                item
                for item in projected["parallel_units"]
                if item["identity"] == "C001/P03/T01"
            )
            self.assertEqual(p03["dependencies_satisfied"], ["C001/P01"])

    def test_any_approved_artifact_or_spec_digest_drift_fails_closed(self) -> None:
        drift_targets = [
            "SCOPE.md",
            "RESEARCH.md",
            "ARCHITECTURE.md",
            "SYSTEM_MODEL.md",
            "ROADMAP.md",
            "plans/P01.md",
            "specs/expected/system.md",
            "specs/MANIFEST.json",
            "specs/diff.md",
        ]
        for relative in drift_targets:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temp:
                root, change = self.make_repo(Path(temp))
                path = change / relative
                path.write_bytes(path.read_bytes() + b"\n")
                before = tree_digest(root)

                with self.assertRaises(WaveError):
                    next_wave(root, "C001")

                self.assertEqual(before, tree_digest(root))

        with tempfile.TemporaryDirectory() as temp:
            root, _ = self.make_repo(Path(temp))
            manifest = root / ".bianchini/current/specs/MANIFEST.json"
            manifest.write_bytes(manifest.read_bytes() + b"\n")
            before = tree_digest(root)
            with self.assertRaises(WaveError):
                next_wave(root, "C001")
            self.assertEqual(before, tree_digest(root))

        with tempfile.TemporaryDirectory() as temp:
            root, _ = self.make_repo(Path(temp))
            model = root / ".bianchini/current/SYSTEM_MODEL.md"
            payload = read_payload(model)
            payload["modules"] = [{"id": "module.drift"}]
            write_payload(model, payload)
            before = tree_digest(root)
            with self.assertRaises(WaveError):
                next_wave(root, "C001")
            self.assertEqual(before, tree_digest(root))

    def test_package_digest_and_state_approval_must_match_current_package(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root, change = self.make_repo(Path(temp))
            coherence_path = change / "COHERENCE.md"
            coherence = read_payload(coherence_path)
            forged = "b" * 64
            coherence["digest"] = forged
            coherence["approval"]["digest"] = forged
            write_payload(coherence_path, coherence)
            state_path = root / ".bianchini/STATE.md"
            state = read_payload(state_path)
            state["digest"] = forged
            write_payload(state_path, state)

            with self.assertRaises(WaveError):
                next_wave(root, "C001")

        with tempfile.TemporaryDirectory() as temp:
            root, _ = self.make_repo(Path(temp))
            state_path = root / ".bianchini/STATE.md"
            state = read_payload(state_path)
            state["digest"] = "b" * 64
            write_payload(state_path, state)

            with self.assertRaises(WaveError):
                next_wave(root, "C001")

        with tempfile.TemporaryDirectory() as temp:
            root, _ = self.make_repo(Path(temp))
            state_path = root / ".bianchini/STATE.md"
            state = read_payload(state_path)
            state["status"] = "ready_for_approval"
            state["active_work"]["status"] = "ready_for_approval"
            write_payload(state_path, state)

            with self.assertRaisesRegex(WaveError, "WAVE_NOT_APPROVED"):
                next_wave(root, "C001")

    def test_minimal_forged_task_result_does_not_unlock_wave(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root, change = self.make_repo(Path(temp))
            result = change / "results/tasks/P01/T01.md"
            result.parent.mkdir(parents=True, exist_ok=True)
            write_payload(
                result,
                {
                    "schema_version": 1,
                    "plan": "P01",
                    "task": "T01",
                    "status": "completed",
                },
            )

            with self.assertRaises(WaveError):
                next_wave(root, "C001")

    def test_minimal_forged_plan_result_does_not_unlock_dependents(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root, change = self.make_repo(Path(temp))
            write_payload(
                change / "results/P01.md",
                {
                    "schema_version": 1,
                    "plan": "P01",
                    "status": "completed",
                    "completed_tasks": ["T01", "T02", "T03"],
                },
            )

            with self.assertRaises(WaveError):
                next_wave(root, "C001")

    def test_task_result_requires_canonical_evidence_and_contract_fields(self) -> None:
        mutations = {
            "verification": lambda value: value.update(verification=[]),
            "covers": lambda value: value.update(covers=[]),
            "expected_result": lambda value: value.update(expected_result="forjado"),
            "result": lambda value: value.update(result=""),
        }
        for label, mutate in mutations.items():
            with self.subTest(field=label), tempfile.TemporaryDirectory() as temp:
                root, change = self.make_repo(Path(temp))
                p01 = plan(
                    "P01",
                    tasks=[
                        task("T01"),
                        task("T02"),
                        task("T03", depends_on=["T01"]),
                    ],
                )
                write_task_result(change, p01, p01["tasks"][0])
                result = change / "results/tasks/P01/T01.md"
                payload = read_payload(result)
                mutate(payload)
                write_payload(result, payload)

                with self.assertRaises(WaveError):
                    next_wave(root, "C001")

    def test_plan_result_requires_canonical_evidence_and_delta(self) -> None:
        mutations = {
            "verification": lambda value: value.update(verification=[]),
            "actual_delta": lambda value: value.update(
                actual_delta={"contracts": {"add": ["forged"]}}
            ),
            "actual_delta_digest": lambda value: value.update(
                actual_delta_digest="0" * 64
            ),
            "promised_delta_digest": lambda value: value.update(
                promised_delta_digest="0" * 64
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(field=label), tempfile.TemporaryDirectory() as temp:
                root, change = self.make_repo(Path(temp))
                p01 = plan(
                    "P01",
                    tasks=[
                        task("T01"),
                        task("T02"),
                        task("T03", depends_on=["T01"]),
                    ],
                )
                write_plan_result(change, p01)
                result = change / "results/P01.md"
                payload = read_payload(result)
                mutate(payload)
                write_payload(result, payload)

                with self.assertRaises(WaveError):
                    next_wave(root, "C001")

    def test_state_blocker_removes_otherwise_eligible_units(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root, _ = self.make_repo(Path(temp))
            state_path = root / ".bianchini/STATE.md"
            state = json.loads(state_path.read_text(encoding="utf-8").split("---", 2)[1])
            state["blockers"] = ["ambiente indisponível"]
            state_path.write_text(document(state, "Estado"), encoding="utf-8")

            projected = next_wave(root, "C001")
            self.assertEqual(projected["eligible_wave"], [])
            blocked = {
                item["identity"]: item for item in projected["blocked_units"]
            }
            self.assertEqual(blocked["C001/P01/T01"]["reason"], "state_blocker")
            self.assertEqual(blocked["C001/P02/T01"]["details"], ["ambiente indisponível"])

    def test_malformed_or_unapproved_package_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root, change = self.make_repo(Path(temp))
            for reference in ("../C001", ".planning/C001", "C999", "Q001"):
                with self.subTest(reference=reference), self.assertRaises(WaveError):
                    next_wave(root, reference)

            coherence_path = change / "COHERENCE.md"
            coherence = json.loads(
                coherence_path.read_text(encoding="utf-8").split("---", 2)[1]
            )
            coherence["status"] = "ready_for_approval"
            coherence_path.write_text(document(coherence, "Coerência"), encoding="utf-8")
            with self.assertRaisesRegex(WaveError, "WAVE_NOT_APPROVED"):
                next_wave(root, "C001")

    def test_symlinked_plan_is_rejected_without_following_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root, change = self.make_repo(base)
            plan_path = change / "plans/P01.md"
            outside = base / "outside.md"
            outside.write_text(plan_path.read_text(encoding="utf-8"), encoding="utf-8")
            plan_path.unlink()
            plan_path.symlink_to(outside)

            with self.assertRaisesRegex(WaveError, "PATH_UNSAFE"):
                next_wave(root, "C001")


if __name__ == "__main__":
    unittest.main()
