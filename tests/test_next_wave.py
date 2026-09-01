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
            "digest": "a" * 64,
            "updated_at": "2026-09-01T12:00:00Z",
        }
        (bianchini / "STATE.md").write_text(document(state, "Estado"), encoding="utf-8")

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
        artifact_manifest = {
            relative: hashlib.sha256((change / relative).read_bytes()).hexdigest()
            for relative in [
                "ROADMAP.md",
                *(f"plans/{value['id']}.md" for value in values),
            ]
        }
        coherence = {
            "schema_version": 2,
            "planning_contract": 2,
            "spec_contract": 1,
            "change": "C001-wave",
            "status": "approved_with_stale",
            "digest": "a" * 64,
            "approval": {
                "digest": "a" * 64,
                "approved_by": "human:test",
                "approved_at": "2026-09-01T12:00:00Z",
            },
            "artifact_manifest": artifact_manifest,
            "stale_plans": ["P04"],
            "findings": [
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
            ],
        }
        (change / "COHERENCE.md").write_text(
            document(coherence, "Coerência"), encoding="utf-8"
        )
        (change / "results/P06.md").write_text(
            document(
                {
                    "schema_version": 1,
                    "plan": "P06",
                    "status": "completed",
                    "completed_tasks": ["T01"],
                },
                "P06",
            ),
            encoding="utf-8",
        )
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
            self.assertEqual(first["package_digest"], "a" * 64)
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
            result = change / "results/tasks/P01/T01.md"
            result.parent.mkdir(parents=True, exist_ok=True)
            result.write_text(
                document(
                    {
                        "schema_version": 1,
                        "plan": "P01",
                        "task": "T01",
                        "status": "completed",
                    },
                    "T01",
                ),
                encoding="utf-8",
            )

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
            (change / "results/P01.md").write_text(
                document(
                    {
                        "schema_version": 1,
                        "plan": "P01",
                        "status": "completed",
                        "completed_tasks": ["T01", "T02", "T03"],
                    },
                    "P01",
                ),
                encoding="utf-8",
            )

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
