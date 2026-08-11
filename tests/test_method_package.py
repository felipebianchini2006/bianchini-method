"""Cenários comportamentais e integridade do Bianchini Method v2."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "bm.py"
FIXTURES = ROOT / "tests" / "fixtures"
PROJECT_FIXTURES = FIXTURES / "projects"
SKILL_NAMES = (
    "sdd-planning",
    "executar-plano",
    "auditar-arquitetura",
    "status-projeto",
    "corrigir-bug",
    "homologar-sistema",
)
SKILLS = {name: ROOT / "skills" / name / "SKILL.md" for name in SKILL_NAMES}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.run(
        ["python3", str(CLI), *args],
        cwd=cwd or ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def cli_json(*args: str, cwd: Path | None = None) -> dict[str, object]:
    result = cli(*args, cwd=cwd)
    if result.returncode != 0:
        raise AssertionError(f"CLI falhou ({result.returncode}): {result.stderr}")
    return json.loads(result.stdout)


def git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=False
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


def init_repo(path: Path) -> str:
    path.mkdir(parents=True)
    git(path, "init", "-b", "main")
    git(path, "config", "user.name", "Bianchini Test")
    git(path, "config", "user.email", "test@example.invalid")
    (path / "app.txt").write_text("base\n", encoding="utf-8")
    (path / ".gitignore").write_text("/.superpowers/\n", encoding="utf-8")
    git(path, "add", "app.txt", ".gitignore")
    git(path, "commit", "-m", "initial")
    return git(path, "rev-parse", "HEAD")


def commit_approved_package(repo: Path, planning_version: str = "v1") -> Path:
    state_path = repo / "docs/living/PROJECT_STATE.md"
    plan_path = repo / "docs/plans/P01.md"
    scope_path = repo / "docs/scope.md"
    spec_path = repo / "docs/spec.md"
    review_path = repo / "docs/review.md"
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    scope_path.write_text("approved scope\n", encoding="utf-8")
    spec_path.write_text("approved spec\n", encoding="utf-8")
    review_path.write_text("planning review passed\n", encoding="utf-8")
    plan_path.write_text(
        "# P01\n\n### Tarefa 1 — Entrega\n\n**Execution:** grouped\n",
        encoding="utf-8",
    )
    state = json.loads(read(FIXTURES / "project-state-v2.json"))
    state["planning_version"] = planning_version
    state["plans"][0]["path"] = "docs/plans/P01.md"
    state["planning"] = {"spec": "docs/spec.md", "review": "docs/review.md"}
    state["approval"]["package"]["files"] = [
        "docs/scope.md",
        "docs/spec.md",
        "docs/review.md",
        "docs/plans/P01.md",
    ]
    state["approval"]["package"]["manifest_path"] = "artifacts/approval/manifest.sha256"
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    created = cli_json("snapshot", "create", str(state_path), "--root", str(repo))
    state["approval"]["package"]["manifest_digest"] = created["digest"]
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    git(repo, "add", "docs", "artifacts/approval/manifest.sha256")
    git(repo, "commit", "-m", f"plan: approve {planning_version} P01")
    return state_path


def frontmatter(markdown: str) -> dict[str, str]:
    match = re.match(r"\A---\n(.*?)\n---\n", markdown, flags=re.DOTALL)
    if not match:
        return {}
    values: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, separator, value = line.partition(":")
        if separator:
            values[key.strip()] = value.strip()
    return values


class PackageIntegrityTests(unittest.TestCase):
    LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")

    def test_six_public_skills_have_valid_frontmatter(self) -> None:
        for name, path in SKILLS.items():
            with self.subTest(skill=name):
                metadata = frontmatter(read(path))
                self.assertEqual(metadata.get("name"), name)
                self.assertIn("Use ", metadata.get("description", ""))
                self.assertLessEqual(len(read(path).splitlines()), 250)

    def test_relative_links_resolve(self) -> None:
        failures: list[str] = []
        for markdown in ROOT.rglob("*.md"):
            for target in self.LINK.findall(read(markdown)):
                target = target.strip().strip("<>").split("#", 1)[0]
                if not target or "://" in target or target.startswith("mailto:"):
                    continue
                if not (markdown.parent / target).resolve().exists():
                    failures.append(f"{markdown.relative_to(ROOT)} -> {target}")
        self.assertEqual(failures, [])

    def test_schema_copy_is_identical_to_packaged_schema(self) -> None:
        root_schema = ROOT / "schemas" / "project-state.schema.json"
        packaged = ROOT / "skills" / "_shared" / "schemas" / "project-state.schema.json"
        self.assertEqual(root_schema.read_bytes(), packaged.read_bytes())

    def test_cli_has_no_third_party_imports(self) -> None:
        content = read(ROOT / "skills" / "_shared" / "scripts" / "bm.py")
        for dependency in ("yaml", "jsonschema", "click", "pydantic"):
            self.assertNotRegex(content, rf"(?m)^(?:from|import)\s+{dependency}\b")

    def test_sharded_runner_covers_every_test_class(self) -> None:
        runner = read(ROOT / "scripts/run_test_shards.py")
        for class_name in (
            "PackageIntegrityTests",
            "RoutingAndStateScenarios",
            "SnapshotScenarios",
            "PlanningQualityScenarios",
            "AdaptivePolicyScenarios",
            "WorkspaceAndArtifactScenarios",
            "BehavioralProjectScenarios",
            "SkillBehaviorContracts",
        ):
            self.assertIn(f'"{class_name}"', runner)
        self.assertIn("scripts/run_test_shards.py", read(ROOT / "README.md"))


class RoutingAndStateScenarios(unittest.TestCase):
    def test_new_project_without_state_bootstraps_v2(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = cli_json("route", "--repo", temp, "--new-project")
            self.assertEqual(result["route"], "v2-new")
            self.assertFalse(result["superpowers_required"])

    def test_explicit_migration_overrides_provisional_v1_route(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "docs/superpowers/plans").mkdir(parents=True)
            result = cli_json(
                "route",
                "--repo",
                str(root),
                "--new-project",
                "--migrate-to-v2",
            )
            self.assertEqual(result["route"], "v2-migration")
            self.assertTrue(result["legacy_detected"])
            self.assertFalse(result["superpowers_required"])

    def test_in_progress_bootstrap_allows_zero_plans_only_until_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = json.loads(read(FIXTURES / "project-state-v2.json"))
            state["planning_status"] = "in_progress"
            state["approval"]["status"] = "pending"
            state["approval"]["approved_at"] = None
            state["approval"]["approved_by"] = None
            state["approval"]["approved_plans"] = []
            state["approval"]["package"]["manifest_digest"] = None
            state["plans"] = []
            state_path = root / "PROJECT_STATE.md"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            valid = cli("validate-state", str(state_path))
            self.assertEqual(valid.returncode, 0, valid.stderr)

            state["planning_status"] = "pending_approval"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            invalid = cli("validate-state", str(state_path))
            self.assertEqual(invalid.returncode, 2)
            self.assertIn("ao menos um plano", invalid.stderr)

    def test_idle_state_is_valid_only_without_scope_plan_or_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            state_path = repo / "docs/living/PROJECT_STATE.md"
            state_path.parent.mkdir(parents=True)
            state_path.write_text("method_version: 1\nstatus: completed\n", encoding="utf-8")
            git(repo, "add", "docs/living/PROJECT_STATE.md")
            git(repo, "commit", "-m", "complete legacy phase")

            transitioned = cli_json(
                "legacy-transition",
                "--repo",
                str(repo),
                "--state",
                "docs/living/PROJECT_STATE.md",
                "--completed",
            )
            self.assertTrue(transitioned["transitioned"])
            valid = cli("validate-state", str(state_path))
            self.assertEqual(valid.returncode, 0, valid.stderr)

            state = json.loads(read(state_path))
            state["approval"]["package"]["files"] = ["docs/old-plan.md"]
            state["release"]["homologation"] = "accepted"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            invalid = cli("validate-state", str(state_path))
            self.assertEqual(invalid.returncode, 2)
            self.assertIn("idle exige lista vazia", invalid.stderr)
            self.assertIn("idle exige release reinicializado", invalid.stderr)

    def test_v1_with_superpowers_uses_legacy_route(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            superpowers = Path(temp) / "superpowers"
            for skill in (
                "brainstorming",
                "writing-plans",
                "subagent-driven-development",
                "systematic-debugging",
                "verification-before-completion",
            ):
                marker = superpowers / "skills" / skill / "SKILL.md"
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text(f"# {skill}\n", encoding="utf-8")
            result = cli_json(
                "route",
                str(FIXTURES / "project-state-v1.md"),
                "--superpowers-path",
                str(superpowers),
            )
            self.assertEqual(result["route"], "v1-superpowers")

    def test_v1_rejects_unrelated_directory_as_superpowers(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            result = cli(
                "route",
                str(FIXTURES / "project-state-v1.md"),
                "--superpowers-path",
                temp,
            )
            self.assertEqual(result.returncode, 3)

    def test_v1_without_superpowers_blocks(self) -> None:
        result = cli("route", str(FIXTURES / "project-state-v1.md"))
        self.assertEqual(result.returncode, 3)
        self.assertIn("exige Superpowers", result.stderr)

    def test_v2_without_superpowers_is_standalone(self) -> None:
        result = cli_json("route", str(FIXTURES / "project-state-v2.json"))
        self.assertEqual(result["route"], "v2-standalone")
        self.assertFalse(result["superpowers_required"])

    def test_v2_state_validates_and_status_is_structured(self) -> None:
        validated = cli_json("validate-state", str(FIXTURES / "project-state-v2.json"))
        status = cli_json("status", str(FIXTURES / "project-state-v2.json"))
        self.assertTrue(validated["valid"])
        self.assertEqual(status["method_mode"], "standalone-adaptive")
        self.assertEqual(status["assurance_profile"], "lean")
        self.assertEqual(status["planning_version"], "v1")
        self.assertEqual(status["plans"], {"P01": "approved"})
        self.assertEqual(status["approval"], "approved")
        self.assertEqual(status["approval_digest"], "a" * 64)
        self.assertEqual(status["architecture_audit"], "optional")
        self.assertEqual(status["architecture_audit_status"], "not_run")
        self.assertEqual(status["manual_pdf"], "scope")
        self.assertIsNone(status["active_execution"]["plan"])
        self.assertIn("release", status)

    def test_invalid_state_reports_schema_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            invalid = Path(temp) / "state.json"
            invalid.write_text('{"method_version": 2}', encoding="utf-8")
            result = cli("validate-state", str(invalid))
            self.assertEqual(result.returncode, 2)
            self.assertIn("campo obrigatório ausente", result.stderr)

    def test_manual_architecture_report_does_not_block_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state = json.loads(read(FIXTURES / "project-state-v2.json"))
            state["architecture_audit"] = "required"
            state["architecture_audit_status"] = "blocked"
            path = Path(temp) / "state.json"
            path.write_text(json.dumps(state), encoding="utf-8")
            result = cli("validate-state", str(path))
            self.assertEqual(result.returncode, 0)

    def test_v1_without_method_version_uses_legacy_route(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "project"
            root.mkdir()
            state = root / "PROJECT_STATE.md"
            state.write_text("# Estado legado\nstatus: em_andamento\n", encoding="utf-8")
            (root / "docs" / "superpowers" / "v3").mkdir(parents=True)
            superpowers = root / "superpowers"
            for skill in (
                "brainstorming",
                "writing-plans",
                "subagent-driven-development",
                "systematic-debugging",
                "verification-before-completion",
            ):
                marker = superpowers / "skills" / skill / "SKILL.md"
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text(f"# {skill}\n", encoding="utf-8")
            result = cli_json(
                "route",
                str(state),
                "--repo",
                str(root),
                "--superpowers-path",
                str(superpowers),
            )
            self.assertEqual(result["route"], "v1-superpowers")

    def test_approved_state_rejects_planned_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state = json.loads(read(FIXTURES / "project-state-v2.json"))
            state["plans"][0]["status"] = "planned"
            path = Path(temp) / "state.json"
            path.write_text(json.dumps(state), encoding="utf-8")
            result = cli("validate-state", str(path))
            self.assertEqual(result.returncode, 2)
            self.assertIn("não pode permanecer planned", result.stderr)

    def test_approved_package_must_contain_spec_review_and_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state = json.loads(read(FIXTURES / "project-state-v2.json"))
            state["approval"]["package"]["files"] = ["docs/scope.md"]
            path = Path(temp) / "state.json"
            path.write_text(json.dumps(state), encoding="utf-8")
            result = cli("validate-state", str(path))
            self.assertEqual(result.returncode, 2)
            self.assertIn("pacote aprovado não contém", result.stderr)
            self.assertIn("P01-crud.md", result.stderr)

    def test_missing_and_cyclic_plan_dependencies_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            missing = json.loads(read(FIXTURES / "project-state-v2.json"))
            missing["plans"][0]["depends_on"] = ["P99"]
            missing_path = root / "missing.json"
            missing_path.write_text(json.dumps(missing), encoding="utf-8")
            missing_result = cli("validate-state", str(missing_path))
            self.assertEqual(missing_result.returncode, 2)
            self.assertIn("plano inexistente", missing_result.stderr)

            cyclic = json.loads(read(FIXTURES / "project-state-v2.json"))
            second = json.loads(json.dumps(cyclic["plans"][0]))
            cyclic["plans"][0]["depends_on"] = ["P02"]
            second["id"] = "P02"
            second["path"] = "docs/bianchini/v1/plans/P02.md"
            second["ledger"] = "artifacts/bianchini/v1/ledgers/P02.md"
            second["depends_on"] = ["P01"]
            cyclic["plans"].append(second)
            cyclic["approval"]["approved_plans"] = ["P01", "P02"]
            cyclic_path = root / "cyclic.json"
            cyclic_path.write_text(json.dumps(cyclic), encoding="utf-8")
            cyclic_result = cli("validate-state", str(cyclic_path))
            self.assertEqual(cyclic_result.returncode, 2)
            self.assertIn("ciclo de dependências", cyclic_result.stderr)

    def test_release_candidate_requires_complete_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state = json.loads(read(FIXTURES / "project-state-v2.json"))
            state["release"]["candidate"] = {
                "revision": "abc123",
                "build": "build-42",
                "checksum": "sha256:release-42",
            }
            state["release"]["status"] = "candidate"
            path = Path(temp) / "state.json"
            path.write_text(json.dumps(state), encoding="utf-8")
            result = cli("validate-state", str(path))
            self.assertEqual(result.returncode, 2)
            self.assertIn("candidate.id", result.stderr)

    def test_status_reports_active_plan_unit_mode_and_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            state = json.loads(read(FIXTURES / "project-state-v2.json"))
            state["plans"][0]["status"] = "in_progress"
            state["active_execution"] = {
                "plan_id": "P01",
                "unit": "Tarefas 1-2",
                "gate": "verification.fast",
                "workspace": "/tmp/bm-p01",
            }
            path = Path(temp) / "state.json"
            path.write_text(json.dumps(state), encoding="utf-8")
            status = cli_json("status", str(path))
            self.assertEqual(
                status["active_execution"],
                {
                    "plan": "P01",
                    "unit": "Tarefas 1-2",
                    "mode": "grouped",
                    "gate": "verification.fast",
                    "workspace": "/tmp/bm-p01",
                },
            )
            self.assertEqual(status["active_plan"], "P01")
            self.assertEqual(status["active_unit"], "Tarefas 1-2")
            self.assertEqual(status["execution_mode"], "grouped")
            self.assertEqual(status["current_gate"], "verification.fast")


class SnapshotScenarios(unittest.TestCase):
    def test_snapshot_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            docs = root / "docs"
            docs.mkdir()
            (docs / "scope.md").write_text("approved scope\n", encoding="utf-8")
            state = json.loads(read(FIXTURES / "project-state-v2.json"))
            state["approval"]["package"]["files"] = ["docs/scope.md"]
            state["approval"]["package"]["manifest_path"] = "artifacts/manifest.sha256"
            state["approval"]["package"]["manifest_digest"] = None
            state["approval"]["status"] = "pending"
            state["approval"]["approved_at"] = None
            state["approval"]["approved_by"] = None
            state["approval"]["approved_plans"] = []
            state["planning_status"] = "pending_approval"
            state["plans"][0]["status"] = "planned"
            state_path = root / "PROJECT_STATE.md"
            state_path.write_text(json.dumps(state), encoding="utf-8")

            created = cli_json("snapshot", "create", str(state_path), "--root", str(root))
            state["approval"]["package"]["manifest_digest"] = created["digest"]
            state_path.write_text(json.dumps(state), encoding="utf-8")
            verified = cli_json("snapshot", "verify", str(state_path), "--root", str(root))
            self.assertEqual(verified["digest"], created["digest"])

            (docs / "scope.md").write_text("tampered\n", encoding="utf-8")
            failed = cli("snapshot", "verify", str(state_path), "--root", str(root))
            self.assertEqual(failed.returncode, 3)

    def test_snapshot_rejects_manifest_path_escape_and_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "workspace" / "repo"
            root.mkdir(parents=True)
            (root / "scope.md").write_text("scope\n", encoding="utf-8")
            state = json.loads(read(FIXTURES / "project-state-v2.json"))
            state["approval"]["status"] = "pending"
            state["approval"]["approved_plans"] = []
            state["approval"]["package"]["manifest_digest"] = None
            state["approval"]["package"]["files"] = ["scope.md"]
            state["planning_status"] = "pending_approval"
            state["plans"][0]["status"] = "planned"
            state["approval"]["package"]["manifest_path"] = "../../arquivo"
            state_path = root / "state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            escaped = base / "arquivo"
            result = cli("snapshot", "create", str(state_path), "--root", str(root))
            self.assertEqual(result.returncode, 2)
            self.assertFalse(escaped.exists())

            outside = base / "outside"
            outside.mkdir()
            (root / "artifacts").symlink_to(outside, target_is_directory=True)
            state["approval"]["package"]["manifest_path"] = "artifacts/manifest.sha256"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            symlink_result = cli(
                "snapshot", "create", str(state_path), "--root", str(root)
            )
            self.assertEqual(symlink_result.returncode, 2)
            self.assertFalse((outside / "manifest.sha256").exists())


class PlanningQualityScenarios(unittest.TestCase):
    def make_project(self, root: Path, plan_count: int = 1) -> Path:
        scope = root / "docs/bianchini/v1/inputs/APPROVED_SCOPE.md"
        research = root / "docs/bianchini/v1/STACK_RESEARCH.md"
        spec = root / "docs/bianchini/v1/specs/system.md"
        review = root / "docs/bianchini/v1/PLANNING_REVIEW.md"
        for path in (scope, research, spec, review):
            path.parent.mkdir(parents=True, exist_ok=True)
        scope.write_text("# Escopo aprovado\n\nEntregar API de registros.\n", encoding="utf-8")
        research.write_text(
            "# Stack Research — v1\n\n"
            "## Stack detectada\n\n- Python 3.13 e pytest.\n\n"
            "## Fontes primárias\n\n"
            "- Fonte primária: Python 3.13 documentation\n"
            "  URL: https://docs.python.org/3.13/\n"
            "  Acessado em: 2026-08-11\n"
            "  Aplicação: manter biblioteca padrão no CLI.\n\n"
            "## Decisões aplicadas\n\n- Reusar unittest e contratos públicos.\n\n"
            "## Alternativas rejeitadas\n\n- Framework adicional — custo sem benefício no ciclo.\n\n"
            "## Riscos e lacunas\n\n- Nenhum conhecido.\n",
            encoding="utf-8",
        )
        spec.write_text(
            "# System Design\n\n## API pública\n\nCriar e consultar registros.\n",
            encoding="utf-8",
        )
        review.write_text(
            "# Planning Review\n\nSpec e qualidade aprovadas; menor ciclo entregável.\n",
            encoding="utf-8",
        )
        state = json.loads(read(FIXTURES / "project-state-v2.json"))
        state["planning_status"] = "pending_approval"
        state["scope"] = {
            "status": "approved",
            "source": "docs/bianchini/v1/inputs/APPROVED_SCOPE.md",
            "approved_at": "2026-08-11T00:00:00Z",
        }
        state["planning"] = {
            "quality_version": 1,
            "research": "docs/bianchini/v1/STACK_RESEARCH.md",
            "spec": "docs/bianchini/v1/specs/system.md",
            "review": "docs/bianchini/v1/PLANNING_REVIEW.md",
        }
        state["complexity_review"] = {
            "decision": "within_budget",
            "justification": None,
            "deferred_scope": [],
            "scope_split_approved": False,
            "scope_split_approved_by": None,
            "scope_split_approved_at": None,
        }
        state["approval"].update(
            {
                "status": "pending",
                "approved_at": None,
                "approved_by": None,
                "approved_plans": [],
            }
        )
        state["approval"]["package"]["manifest_digest"] = None
        package_files = [
            state["scope"]["source"],
            state["planning"]["research"],
            state["planning"]["spec"],
            state["planning"]["review"],
        ]
        plans = []
        for number in range(1, plan_count + 1):
            plan_id = f"P{number:02d}"
            relative = f"docs/bianchini/v1/plans/{plan_id}-api.md"
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                f"---\nplan_id: {plan_id}\nmethod_version: 2\nrisk: low\n"
                "execution: grouped\nreview: plan_gate\ndepends_on: []\n---\n\n"
                f"# {plan_id} API\n\n### Tarefa 1 — Entregar comportamento {number}\n\n"
                "**Execution:** grouped\n"
                "**Review:** plan_gate\n"
                "**Test seams:** HTTP API pública\n"
                "**Spec refs:** specs/system.md#api-pública\n"
                "**Files:** src/api.py, tests/test_api.py\n"
                "**Contract:** entrada JSON; saída 201; ID persistido\n"
                "**Verification:** `python3 -m unittest tests.test_api` retorna 0\n"
                "**Done when:** contrato público passa no gate do plano\n",
                encoding="utf-8",
            )
            plan = json.loads(json.dumps(state["plans"][0]))
            plan.update(
                {
                    "id": plan_id,
                    "path": relative,
                    "status": "planned",
                    "depends_on": [],
                    "ledger": f"artifacts/bianchini/v1/ledgers/{plan_id}.md",
                }
            )
            plans.append(plan)
            package_files.append(relative)
        state["plans"] = plans
        state["approval"]["package"]["files"] = package_files
        state["verification"] = {
            "fast": {"commands": ["python3 -m unittest tests.test_api"], "status": "pending"},
            "plan": {"commands": ["python3 -m unittest discover -s tests"], "status": "pending"},
            "release": {"commands": ["python3 -m unittest discover -s tests"], "status": "pending"},
        }
        state_path = root / "docs/living/PROJECT_STATE.md"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return state_path

    def test_strict_audit_accepts_researched_compact_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = self.make_project(root)
            result = cli_json("planning-audit", str(state), "--root", str(root), "--strict")
            self.assertTrue(result["valid"])
            self.assertEqual(result["quality_contract"], "planning-quality-v1")
            self.assertEqual(result["metrics"]["plans"], 1)
            self.assertEqual(result["metrics"]["execution_units"], 1)

    def test_strict_audit_rejects_unverifiable_research(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = self.make_project(root)
            research = root / "docs/bianchini/v1/STACK_RESEARCH.md"
            research.write_text("# opinião sem fontes\n", encoding="utf-8")
            result = cli("planning-audit", str(state), "--root", str(root), "--strict")
            self.assertEqual(result.returncode, 2)
            self.assertIn("Fonte primária", result.stderr)
            self.assertIn("URL HTTPS", result.stderr)

    def test_strict_audit_rejects_placeholders_prose_and_legacy_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_project(root)
            state = json.loads(read(state_path))
            state["verification"]["fast"]["commands"] = ["Executar testes dos alvos <alvo>"]
            state_path.write_text(json.dumps(state), encoding="utf-8")
            plan = root / state["plans"][0]["path"]
            plan.write_text(
                read(plan).replace(
                    "**Spec refs:** specs/system.md#api-pública",
                    "**Spec refs:** inputs/APPROVED_SCOPE.md, PLANO Task 7",
                ),
                encoding="utf-8",
            )
            result = cli("planning-audit", str(state_path), "--root", str(root), "--strict")
            self.assertEqual(result.returncode, 2)
            self.assertIn("referência operacional", result.stderr)
            self.assertIn("comando vazio, vago ou com placeholder", result.stderr)

    def test_snapshot_cannot_bypass_quality_audit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_project(root)
            state = json.loads(read(state_path))
            state["verification"]["plan"]["commands"] = ["Validar tudo depois"]
            state_path.write_text(json.dumps(state), encoding="utf-8")
            result = cli("snapshot", "create", str(state_path), "--root", str(root))
            self.assertEqual(result.returncode, 2)
            self.assertIn("não é comando reproduzível", result.stderr)
            manifest = root / state["approval"]["package"]["manifest_path"]
            self.assertFalse(manifest.exists())

    def test_budget_escalates_profile_without_reducing_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_project(root, plan_count=9)
            blocked = cli("planning-audit", str(state_path), "--root", str(root), "--strict")
            self.assertEqual(blocked.returncode, 2)
            self.assertIn("preserve todo o escopo e escale para standard", blocked.stderr)

            state = json.loads(read(state_path))
            state["assurance_profile"] = "standard"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            accepted = cli_json(
                "planning-audit", str(state_path), "--root", str(root), "--strict"
            )
            self.assertEqual(accepted["budget_exceeded"], [])
            self.assertEqual(accepted["profile"], "standard")
            self.assertEqual(accepted["recommended_profile"], "standard")
            self.assertEqual(state["complexity_review"]["deferred_scope"], [])

    def test_lean_is_small_and_seven_is_ceiling_not_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            seven = self.make_project(root, plan_count=7)
            accepted = cli_json(
                "planning-audit", str(seven), "--root", str(root), "--strict"
            )
            self.assertEqual(accepted["profile"], "lean")
            self.assertEqual(accepted["limits"]["plans"], 7)
            self.assertIn("1–4 planos", accepted["warnings"][0])

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            eight = self.make_project(root, plan_count=8)
            blocked = cli(
                "planning-audit", str(eight), "--root", str(root), "--strict"
            )
            self.assertEqual(blocked.returncode, 2)
            self.assertIn("escale para standard", blocked.stderr)

    def test_full_profile_accepts_broad_scope_without_deferral(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_project(root, plan_count=20)
            state = json.loads(read(state_path))
            for plan in state["plans"]:
                path = root / plan["path"]
                extra_units = ""
                for unit in (2, 3):
                    extra_units += (
                        f"\n### Tarefa {unit} — Entregar comportamento adicional {unit}\n\n"
                        "**Execution:** grouped\n"
                        "**Review:** plan_gate\n"
                        "**Test seams:** HTTP API pública\n"
                        "**Spec refs:** specs/system.md#api-pública\n"
                        "**Files:** src/api.py, tests/test_api.py\n"
                        "**Contract:** entrada JSON; saída observável; estado persistido\n"
                        "**Verification:** `python3 -m unittest tests.test_api` retorna 0\n"
                        "**Done when:** contrato público passa no gate do plano\n"
                    )
                path.write_text(read(path) + extra_units, encoding="utf-8")
            state["assurance_profile"] = "full"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            accepted = cli_json(
                "planning-audit", str(state_path), "--root", str(root), "--strict"
            )
            self.assertEqual(accepted["profile"], "full")
            self.assertEqual(accepted["recommended_profile"], "full")
            self.assertEqual(accepted["metrics"]["plans"], 20)
            self.assertEqual(accepted["metrics"]["execution_units"], 60)
            self.assertEqual(accepted["budget_exceeded"], [])

    def test_critical_risk_escalates_profile_even_for_small_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_project(root)
            state = json.loads(read(state_path))
            state["plans"][0].update(
                {"risk": "critical", "execution": "strict", "review": "per_task"}
            )
            state_path.write_text(json.dumps(state), encoding="utf-8")
            blocked = cli(
                "planning-audit", str(state_path), "--root", str(root), "--strict"
            )
            self.assertEqual(blocked.returncode, 2)
            self.assertIn("escale para full", blocked.stderr)

            state["assurance_profile"] = "full"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            accepted = cli_json(
                "planning-audit", str(state_path), "--root", str(root), "--strict"
            )
            self.assertEqual(accepted["recommended_profile"], "full")

    def test_deferred_scope_requires_explicit_owner_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_project(root)
            state = json.loads(read(state_path))
            state["complexity_review"].update(
                {
                    "decision": "split",
                    "deferred_scope": ["Pix Automático"],
                }
            )
            state_path.write_text(json.dumps(state), encoding="utf-8")
            blocked = cli(
                "planning-audit", str(state_path), "--root", str(root), "--strict"
            )
            self.assertEqual(blocked.returncode, 2)
            self.assertIn("não pode ser adiado para caber no orçamento", blocked.stderr)

            state["complexity_review"].update(
                {
                    "scope_split_approved": True,
                    "scope_split_approved_by": "owner@example.invalid",
                    "scope_split_approved_at": "2026-08-11T12:00:00Z",
                }
            )
            state_path.write_text(json.dumps(state), encoding="utf-8")
            accepted = cli_json(
                "planning-audit", str(state_path), "--root", str(root), "--strict"
            )
            self.assertTrue(accepted["valid"])

    def test_old_v2_state_remains_compatible_but_cannot_claim_new_quality(self) -> None:
        valid = cli("validate-state", str(FIXTURES / "project-state-v2.json"))
        self.assertEqual(valid.returncode, 0, valid.stderr)
        with tempfile.TemporaryDirectory() as temp:
            compatible = cli_json(
                "planning-audit",
                str(FIXTURES / "project-state-v2.json"),
                "--root",
                temp,
            )
            self.assertEqual(compatible["quality_contract"], "legacy-compatible")
            strict = cli(
                "planning-audit",
                str(FIXTURES / "project-state-v2.json"),
                "--root",
                temp,
                "--strict",
            )
            self.assertEqual(strict.returncode, 2)
            self.assertIn("quality_version", strict.stderr)


class AdaptivePolicyScenarios(unittest.TestCase):
    def policy(self, *args: str) -> dict[str, object]:
        return cli_json("policy", *args)

    def test_crud_lean_is_grouped_with_two_fix_rounds(self) -> None:
        value = self.policy("--profile", "lean", "--risk", "low", "--change", "crud")
        self.assertEqual((value["execution"], value["review"]), ("grouped", "plan_gate"))
        self.assertEqual(value["max_fix_rounds"], 2)
        self.assertFalse(value["architecture_audit_required"])

    def test_integration_standard_is_vertical_slice(self) -> None:
        value = self.policy("--profile", "standard", "--risk", "medium", "--change", "integration")
        self.assertEqual((value["execution"], value["review"]), ("slice", "per_slice"))
        self.assertEqual(value["max_fix_rounds"], 3)

    def test_payment_full_is_strict_and_architecture_audit_stays_manual(self) -> None:
        value = self.policy("--profile", "full", "--risk", "critical", "--change", "payment")
        self.assertEqual((value["execution"], value["review"]), ("strict", "per_task"))
        self.assertEqual(value["max_fix_rounds"], 5)
        self.assertFalse(value["architecture_audit_required"])
        self.assertEqual(value["architecture_audit_mode"], "manual_report_only")

    def test_fix_round_breaker_varies_by_profile(self) -> None:
        lean = self.policy("--profile", "lean", "--risk", "low", "--round", "2")
        standard = self.policy("--profile", "standard", "--risk", "medium", "--round", "2")
        full = self.policy("--profile", "full", "--risk", "high", "--round", "5")
        self.assertTrue(lean["breaker"])
        self.assertFalse(standard["breaker"])
        self.assertTrue(full["breaker"])

    def test_visual_bug_uses_visual_evidence(self) -> None:
        value = self.policy("--profile", "lean", "--risk", "low", "--change", "visual")
        self.assertEqual(value["visual_validation"], "screenshot_or_visual_regression")

    def test_manual_out_of_scope_is_not_required(self) -> None:
        value = self.policy(
            "--profile", "lean", "--risk", "low", "--manual-pdf", "scope"
        )
        self.assertFalse(value["manual_required"])
        required = self.policy(
            "--profile", "lean", "--risk", "low", "--manual-pdf", "scope", "--manual-in-scope"
        )
        self.assertTrue(required["manual_required"])

    def test_manual_policy_supports_none_quick_start_and_full(self) -> None:
        none = self.policy(
            "--profile", "lean", "--risk", "low", "--manual-pdf", "none"
        )
        quick = self.policy(
            "--profile", "lean", "--risk", "low", "--manual-pdf", "quick_start"
        )
        full = self.policy(
            "--profile", "lean", "--risk", "low", "--manual-pdf", "full"
        )
        self.assertFalse(none["manual_required"])
        self.assertEqual(none["manual_level"], "none")
        self.assertTrue(quick["manual_required"])
        self.assertEqual(quick["manual_level"], "quick_start")
        self.assertTrue(full["manual_required"])

    def test_homologation_is_automation_first(self) -> None:
        value = self.policy("--profile", "standard", "--risk", "medium")
        self.assertEqual(
            value["homologation_order"],
            ["automated_regression", "coded_e2e", "proof_map", "manual_gaps"],
        )

    def test_homologation_maps_real_e2e_evidence_before_manual_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = json.loads(read(FIXTURES / "project-state-v2.json"))
            state["release"]["candidate"] = {
                "id": "rc-1",
                "revision": "abc123",
                "build": "build-42",
                "checksum": "sha256:release-42",
            }
            state_path = root / "state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            output = root / "proof-map.json"
            proof = cli_json(
                "proof-map",
                "--state",
                str(state_path),
                "--evidence",
                str(FIXTURES / "release-evidence.json"),
                "--output",
                str(output),
            )
            self.assertEqual(proof["automated_proven"], 2)
            self.assertEqual(proof["automation_gaps"], [])
            self.assertEqual(proof["manual_gaps"], ["contraste visual mobile"])
            self.assertTrue(output.is_file())

    def test_proof_map_rejects_evidence_from_old_candidate_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = json.loads(read(FIXTURES / "project-state-v2.json"))
            state["release"]["candidate"] = {
                "id": "rc-1",
                "revision": "new-revision",
                "build": "build-42",
                "checksum": "sha256:release-42",
            }
            state_path = root / "state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            output = root / "proof-map.json"
            proof = cli_json(
                "proof-map",
                "--state",
                str(state_path),
                "--evidence",
                str(FIXTURES / "release-evidence.json"),
                "--output",
                str(output),
            )
            self.assertEqual(proof["automated_proven"], 0)
            self.assertEqual(len(proof["automation_gaps"]), 2)


class WorkspaceAndArtifactScenarios(unittest.TestCase):
    def test_completed_legacy_phase_transitions_to_idle_v2_and_archives_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            legacy = b"method_version: 1\nstatus: completed\ncycle: legacy-final\n"
            state_path = repo / "docs/living/PROJECT_STATE.md"
            state_path.parent.mkdir(parents=True)
            state_path.write_bytes(legacy)
            root_artifact = repo / ".superpowers/sdd/final-report.md"
            root_artifact.parent.mkdir(parents=True)
            root_artifact.write_text("legacy evidence\n", encoding="utf-8")
            git(repo, "add", "docs/living/PROJECT_STATE.md")
            git(repo, "add", "-f", ".superpowers/sdd/final-report.md")
            git(repo, "commit", "-m", "complete legacy delivery")

            refused = cli(
                "legacy-transition",
                "--repo",
                str(repo),
                "--state",
                "docs/living/PROJECT_STATE.md",
            )
            self.assertEqual(refused.returncode, 3)
            self.assertIn("--completed é obrigatório", refused.stderr)
            self.assertEqual(state_path.read_bytes(), legacy)

            result = cli_json(
                "legacy-transition",
                "--repo",
                str(repo),
                "--state",
                "docs/living/PROJECT_STATE.md",
                "--completed",
            )
            archive = repo / "docs/bianchini/legacy/transitions/PROJECT_STATE-v1-final.md"
            moved_artifact = (
                repo
                / "docs/bianchini/legacy/root-superpowers/sdd/final-report.md"
            )
            state = json.loads(read(state_path))
            self.assertTrue(result["transitioned"])
            self.assertEqual(result["route"], "v2-standalone")
            self.assertEqual(state["method_version"], 2)
            self.assertEqual(state["planning_status"], "idle")
            self.assertEqual(state["planning_version"], "v1")
            self.assertEqual(state["plans"], [])
            self.assertEqual(state["scope"]["status"], "pending")
            self.assertIsNone(state["scope"]["source"])
            self.assertEqual(archive.read_bytes(), legacy)
            self.assertEqual(moved_artifact.read_text(encoding="utf-8"), "legacy evidence\n")
            self.assertFalse(root_artifact.exists())
            self.assertEqual(
                cli_json("route", str(state_path))["route"], "v2-standalone"
            )
            self.assertEqual(cli_json("status", str(state_path))["planning_status"], "idle")
            self.assertTrue(
                cli_json("repo-hygiene", "check", "--repo", str(repo))["valid"]
            )
            staged = git(repo, "diff", "--cached", "--name-only").splitlines()
            self.assertIn("docs/living/PROJECT_STATE.md", staged)
            self.assertIn(
                "docs/bianchini/legacy/transitions/PROJECT_STATE-v1-final.md", staged
            )

            repeated = cli_json(
                "legacy-transition",
                "--repo",
                str(repo),
                "--state",
                "docs/living/PROJECT_STATE.md",
                "--completed",
            )
            self.assertTrue(repeated["already_transitioned"])
            self.assertFalse(repeated["transitioned"])

    def test_legacy_transition_blocks_dirty_repository_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            legacy = b"method_version: 1\nstatus: completed\n"
            state_path = repo / "docs/living/PROJECT_STATE.md"
            state_path.parent.mkdir(parents=True)
            state_path.write_bytes(legacy)
            git(repo, "add", "docs/living/PROJECT_STATE.md")
            git(repo, "commit", "-m", "complete legacy phase")
            (repo / "uncommitted.txt").write_text("user work\n", encoding="utf-8")

            result = cli(
                "legacy-transition",
                "--repo",
                str(repo),
                "--state",
                str(state_path),
                "--completed",
            )
            self.assertEqual(result.returncode, 3)
            self.assertIn("árvore limpa", result.stderr)
            self.assertEqual(state_path.read_bytes(), legacy)
            self.assertFalse(
                (repo / "docs/bianchini/legacy/transitions/PROJECT_STATE-v1-final.md").exists()
            )

    def test_repo_hygiene_archives_tracked_root_artifacts_and_adds_ignore(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            (repo / ".gitignore").write_text("", encoding="utf-8")
            report = repo / ".superpowers/sdd/cycle/task-1-report.md"
            report.parent.mkdir(parents=True)
            report.write_text("evidence bytes\n", encoding="utf-8")
            git(repo, "add", ".gitignore", ".superpowers")
            git(repo, "commit", "-m", "track legacy root artifact")

            blocked = cli("repo-hygiene", "check", "--repo", str(repo))
            self.assertEqual(blocked.returncode, 3)
            self.assertIn("ainda rastreado", blocked.stderr)
            self.assertIn("ausente do .gitignore", blocked.stderr)

            migrated = cli_json("repo-hygiene", "migrate", "--repo", str(repo))
            archived = (
                repo
                / "docs/bianchini/legacy/root-superpowers/sdd/cycle/task-1-report.md"
            )
            self.assertEqual(archived.read_text(encoding="utf-8"), "evidence bytes\n")
            self.assertFalse(report.exists())
            self.assertTrue(migrated["staged"])
            self.assertTrue(migrated["ignore_added"])
            self.assertIn("/.superpowers/", read(repo / ".gitignore"))
            self.assertIn("R", git(repo, "diff", "--cached", "--name-status"))
            checked = cli_json("repo-hygiene", "check", "--repo", str(repo))
            self.assertTrue(checked["valid"])

    def test_repo_hygiene_migration_blocks_unrelated_dirty_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            report = repo / ".superpowers/sdd/task.md"
            report.parent.mkdir(parents=True)
            report.write_text("tracked\n", encoding="utf-8")
            git(repo, "add", "-f", ".superpowers/sdd/task.md")
            git(repo, "commit", "-m", "track legacy artifact")
            (repo / "user-work.txt").write_text("do not touch\n", encoding="utf-8")

            result = cli("repo-hygiene", "migrate", "--repo", str(repo))
            self.assertEqual(result.returncode, 3)
            self.assertIn("mudanças alheias", result.stderr)
            self.assertTrue(report.is_file())

    def test_workspace_target_inside_repository_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            state = commit_approved_package(repo)
            result = cli(
                "workspace",
                "create",
                "--repo",
                str(repo),
                "--plan",
                "P01",
                "--planning-version",
                "v1",
                "--state",
                str(state),
                "--target",
                str(repo / ".worktrees" / "p01"),
            )
            self.assertEqual(result.returncode, 4)
            self.assertIn("fora do repositório", result.stderr)

    def test_primary_main_is_blocked_and_linked_worktree_is_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            state = commit_approved_package(repo)
            blocked = cli("workspace", "check", "--repo", str(repo))
            self.assertEqual(blocked.returncode, 4)
            self.assertIn("branch main", blocked.stderr)

            created = cli_json(
                "workspace",
                "create",
                "--repo",
                str(repo),
                "--plan",
                "P01",
                "--planning-version",
                "v1",
                "--state",
                str(state.relative_to(repo)),
            )
            workspace = Path(str(created["workspace"]))
            safe = cli_json("workspace", "check", "--repo", str(workspace))
            self.assertTrue(safe["safe"])
            self.assertEqual(safe["branch"], "bm/v1-p01")
            self.assertTrue((workspace / "docs/living/PROJECT_STATE.md").is_file())
            self.assertTrue((workspace / "docs/plans/P01.md").is_file())
            self.assertTrue((workspace / "artifacts/approval/manifest.sha256").is_file())

    def test_workspace_create_is_idempotent_and_locate_resume_reuse_it(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            state = commit_approved_package(repo)
            base_args = (
                "--repo",
                str(repo),
                "--plan",
                "P01",
                "--planning-version",
                "v1",
            )
            created = cli_json(
                "workspace", "create", *base_args, "--state", str(state)
            )
            created_again = cli_json(
                "workspace", "create", *base_args, "--state", str(state)
            )
            located = cli_json(
                "workspace", "locate", *base_args
            )
            resumed = cli_json(
                "workspace", "resume", *base_args
            )
            self.assertFalse(created["reused"])
            self.assertTrue(created_again["reused"])
            self.assertEqual(created["workspace"], located["workspace"])
            self.assertEqual(created["workspace"], resumed["workspace"])
            self.assertTrue(resumed["safe"])

    def test_workspace_create_blocks_uncommitted_planning_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            source = PROJECT_FIXTURES / "v2-low-grouped"
            shutil.copytree(source / "docs", repo / "docs")
            state = repo / "docs/living/PROJECT_STATE.md"
            result = cli(
                "workspace",
                "create",
                "--repo",
                str(repo),
                "--plan",
                "P01",
                "--planning-version",
                "v1",
                "--state",
                str(state),
            )
            self.assertEqual(result.returncode, 3)
            self.assertIn("alterações não commitadas", result.stderr)
            self.assertIn("commit local", result.stderr)
            self.assertFalse((Path(temp) / ".bianchini-worktrees").exists())

    def test_workspace_identity_separates_planning_cycles(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            state_path = commit_approved_package(repo, "v1")
            first = cli_json(
                "workspace",
                "create",
                "--repo",
                str(repo),
                "--plan",
                "P01",
                "--planning-version",
                "v1",
                "--state",
                str(state_path),
            )
            state = json.loads(read(state_path))
            state["planning_version"] = "v2"
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            git(repo, "add", str(state_path.relative_to(repo)))
            git(repo, "commit", "-m", "plan: approve v2 P01")
            second = cli_json(
                "workspace",
                "create",
                "--repo",
                str(repo),
                "--plan",
                "P01",
                "--planning-version",
                "v2",
                "--state",
                str(state_path),
            )
            self.assertEqual(first["branch"], "bm/v1-p01")
            self.assertEqual(second["branch"], "bm/v2-p01")
            self.assertNotEqual(first["workspace"], second["workspace"])

    def test_workspace_create_rejects_ignored_uncommitted_package_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            (repo / ".gitignore").write_text(
                "/.superpowers/\ndocs/ignored-plan.md\n", encoding="utf-8"
            )
            git(repo, "add", ".gitignore")
            git(repo, "commit", "-m", "chore: ignore generated plan")
            state_path = commit_approved_package(repo)
            ignored = repo / "docs/ignored-plan.md"
            ignored.write_text("# Approved but ignored\n", encoding="utf-8")
            state = json.loads(read(state_path))
            state["approval"]["package"]["files"].append("docs/ignored-plan.md")
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            snapshot_value = cli_json(
                "snapshot", "create", str(state_path), "--root", str(repo)
            )
            state["approval"]["package"]["manifest_digest"] = snapshot_value["digest"]
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            git(repo, "add", "docs/living/PROJECT_STATE.md", "artifacts/approval/manifest.sha256")
            git(repo, "commit", "-m", "plan: update approved package")
            self.assertEqual(git(repo, "status", "--porcelain"), "")
            result = cli(
                "workspace",
                "create",
                "--repo",
                str(repo),
                "--plan",
                "P01",
                "--planning-version",
                "v1",
                "--state",
                str(state_path),
            )
            self.assertEqual(result.returncode, 3)
            self.assertIn("não está commitado: docs/ignored-plan.md", result.stderr)

    def test_two_task_plan_generates_second_brief_without_minimum_pressure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "brief.md"
            cli_json(
                "task-brief",
                "--plan",
                str(FIXTURES / "two-task-plan.md"),
                "--task",
                "2",
                "--output",
                str(output),
            )
            content = read(output)
            self.assertIn("Listar registros", content)
            self.assertNotIn("Criar registro", content)

    def test_grouped_brief_accepts_task_list_range_and_explicit_heading(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            output = root / "grouped.md"
            result = cli_json(
                "task-brief",
                "--plan",
                str(FIXTURES / "two-task-plan.md"),
                "--tasks",
                "1-2",
                "--output",
                str(output),
            )
            content = read(output)
            self.assertEqual(result["tasks"], ["1", "2"])
            self.assertEqual(len(result["unit_digests"]), 2)
            self.assertEqual(result["kind"], "group")
            self.assertRegex(str(result["group_id"]), r"^group-[0-9a-f]{12}$")
            self.assertRegex(str(result["group_digest"]), r"^[0-9a-f]{64}$")
            self.assertLess(content.index("Criar registro"), content.index("Listar registros"))

            grouped_plan = root / "group-plan.md"
            grouped_plan.write_text(
                "# Plano\n\n### Grupo API pública\n\nAlterar POST e GET no mesmo seam.\n\n"
                "### Grupo UI\n\nAlterar tela.\n",
                encoding="utf-8",
            )
            group_output = root / "heading.md"
            group_result = cli_json(
                "task-brief",
                "--plan",
                str(grouped_plan),
                "--group",
                "Grupo API pública",
                "--output",
                str(group_output),
            )
            self.assertEqual(group_result["tasks"], ["Grupo API pública"])
            self.assertIn("Alterar POST e GET", read(group_output))
            self.assertNotIn("Alterar tela", read(group_output))

    def test_grouped_brief_rejects_mixed_execution_modes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            mixed = root / "mixed.md"
            mixed.write_text(
                "# Plano\n\n### Tarefa 1 — Baixa\n\n**Execution:** grouped\n\n"
                "### Tarefa 2 — Crítica\n\n**Execution:** strict\n",
                encoding="utf-8",
            )
            result = cli(
                "task-brief",
                "--plan",
                str(mixed),
                "--tasks",
                "1-2",
                "--output",
                str(root / "brief.md"),
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("Execution: grouped", result.stderr)

    def test_report_review_package_and_checkpoint_are_persistent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / "repo"
            base = init_repo(repo)
            git(repo, "switch", "-c", "bm/artifacts")
            (repo / "app.txt").write_text("changed\n", encoding="utf-8")
            git(repo, "add", "app.txt")
            git(repo, "commit", "-m", "change")

            brief = root / "brief.md"
            report = root / "report.md"
            review = root / "review.md"
            cli_json("task-brief", "--plan", str(FIXTURES / "two-task-plan.md"), "--task", "1", "--output", str(brief))
            cli_json("report", "--brief", str(brief), "--output", str(report))
            cli_json(
                "review-package",
                "--cwd",
                str(repo),
                "--base",
                base,
                "--brief",
                str(brief),
                "--report",
                str(report),
                "--output",
                str(review),
            )
            self.assertIn("changed", read(review))

            state = root / "state.json"
            shutil.copy(FIXTURES / "project-state-v2.json", state)
            ledger = root / "ledger.md"
            ledger.write_text("Task 1 completed\n", encoding="utf-8")
            checkpoint = root / "checkpoint.json"
            cli_json(
                "checkpoint",
                "--state",
                str(state),
                "--ledger",
                str(ledger),
                "--cwd",
                str(repo),
                "--output",
                str(checkpoint),
            )
            checkpoint_value = json.loads(read(checkpoint))
            self.assertEqual(checkpoint_value["git"]["branch"], "bm/artifacts")
            self.assertEqual(checkpoint_value["workspace"], str(repo.resolve()))
            self.assertIn("Task 1 completed", checkpoint_value["ledger_tail"])

    def test_review_package_redacts_secrets_and_personal_email(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / "repo"
            base = init_repo(repo)
            git(repo, "switch", "-c", "bm/redaction")
            (repo / "app.txt").write_text(
                "API_KEY=super-secret-value\nowner=person@example.com\n",
                encoding="utf-8",
            )
            git(repo, "add", "app.txt")
            git(repo, "commit", "-m", "sensitive fixture")
            brief = root / "brief.md"
            report = root / "report.md"
            brief.write_text("brief\n", encoding="utf-8")
            report.write_text("report\n", encoding="utf-8")
            review = root / "review.md"
            result = cli_json(
                "review-package",
                "--cwd",
                str(repo),
                "--base",
                base,
                "--brief",
                str(brief),
                "--report",
                str(report),
                "--output",
                str(review),
            )
            content = read(review)
            self.assertGreaterEqual(result["redactions"], 2)
            self.assertNotIn("super-secret-value", content)
            self.assertNotIn("person@example.com", content)
            self.assertIn("Security notice", content)

    def test_common_input_errors_are_clean_and_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            missing = cli(
                "report",
                "--brief",
                str(root / "missing-brief.md"),
                "--output",
                str(root / "out.md"),
            )
            self.assertEqual(missing.returncode, 2)
            self.assertNotIn("Traceback", missing.stderr)
            self.assertFalse((root / "out.md").exists())

            invalid_evidence = root / "evidence.json"
            invalid_evidence.write_text("{invalid", encoding="utf-8")
            result = cli(
                "proof-map",
                "--state",
                str(FIXTURES / "project-state-v2.json"),
                "--evidence",
                str(invalid_evidence),
                "--output",
                str(root / "proof.json"),
            )
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("Traceback", result.stderr)


class BehavioralProjectScenarios(unittest.TestCase):
    def test_real_v1_fixture_without_marker_stays_on_superpowers(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            project = root / "project"
            shutil.copytree(PROJECT_FIXTURES / "v1-real", project)
            superpowers = root / "superpowers"
            for skill in (
                "brainstorming",
                "writing-plans",
                "subagent-driven-development",
                "systematic-debugging",
                "verification-before-completion",
            ):
                marker = superpowers / "skills" / skill / "SKILL.md"
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text(f"# {skill}\n", encoding="utf-8")
            route = cli_json(
                "route",
                str(project / "docs/living/PROJECT_STATE.md"),
                "--repo",
                str(project),
                "--superpowers-path",
                str(superpowers),
            )
            self.assertEqual(route["route"], "v1-superpowers")

    def test_real_low_risk_project_runs_snapshot_group_status_and_telemetry(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "project"
            shutil.copytree(PROJECT_FIXTURES / "v2-low-grouped", project)
            state_path = project / "docs/living/PROJECT_STATE.md"
            plan_path = project / "docs/bianchini/v1/plans/P01-api.md"
            validated = cli_json("validate-state", str(state_path))
            self.assertTrue(validated["valid"])

            snapshot = cli_json(
                "snapshot", "create", str(state_path), "--root", str(project)
            )
            state = json.loads(read(state_path))
            state["planning_status"] = "approved"
            state["approval"].update(
                {
                    "status": "approved",
                    "approved_at": "2026-08-11T10:00:00Z",
                    "approved_by": "owner",
                    "approved_plans": ["P01"],
                }
            )
            state["approval"]["package"]["manifest_digest"] = snapshot["digest"]
            state["plans"][0]["status"] = "in_progress"
            state["active_execution"] = {
                "plan_id": "P01",
                "unit": "Tarefas 1-3",
                "gate": "verification.fast",
                "workspace": str((project.parent / "p01-worktree").resolve()),
            }
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            verified = cli_json(
                "snapshot", "verify", str(state_path), "--root", str(project)
            )
            self.assertEqual(verified["digest"], snapshot["digest"])

            brief_path = project / "artifacts/bianchini/v1/briefs/P01-group.md"
            brief = cli_json(
                "task-brief",
                "--plan",
                str(plan_path),
                "--tasks",
                "1-3",
                "--output",
                str(brief_path),
            )
            self.assertEqual(brief["kind"], "group")
            self.assertEqual(brief["tasks"], ["1", "2", "3"])
            self.assertEqual(len(brief["unit_digests"]), 3)

            cli_json(
                "telemetry",
                "record",
                "--state",
                str(state_path),
                "--root",
                str(project),
                "--plan",
                "P01",
                "--phase",
                "execution",
                "--at",
                "2026-08-11T10:01:00Z",
                "--input-tokens",
                "800",
                "--output-tokens",
                "300",
                "--duration-ms",
                "1200",
                "--fix-rounds",
                "1",
            )
            cli_json(
                "telemetry",
                "record",
                "--state",
                str(state_path),
                "--root",
                str(project),
                "--plan",
                "P01",
                "--phase",
                "homologation",
                "--at",
                "2026-08-11T10:02:00Z",
                "--duration-ms",
                "500",
                "--gate-failures",
                "1",
                "--homologation-bugs",
                "2",
            )
            metrics = cli_json(
                "telemetry",
                "summary",
                "--state",
                str(state_path),
                "--root",
                str(project),
            )
            self.assertEqual(metrics["records"], 2)
            self.assertEqual(metrics["totals"]["input_tokens"], 800)
            self.assertEqual(metrics["totals"]["output_tokens"], 300)
            self.assertEqual(metrics["totals"]["duration_ms"], 1700)
            self.assertEqual(metrics["totals"]["fix_rounds"], 1)
            self.assertEqual(metrics["totals"]["gate_failures"], 1)
            self.assertEqual(metrics["totals"]["homologation_bugs"], 2)
            self.assertEqual(metrics["plans"]["P01"]["duration_ms"], 1700)

            status = cli_json("status", str(state_path), "--root", str(project))
            self.assertEqual(status["method_mode"], "standalone-adaptive")
            self.assertEqual(status["assurance_profile"], "lean")
            self.assertEqual(status["active_plan"], "P01")
            self.assertEqual(status["execution_mode"], "grouped")
            self.assertEqual(status["current_gate"], "verification.fast")
            self.assertEqual(status["telemetry"]["records"], 2)
            visual = cli(
                "status",
                str(state_path),
                "--root",
                str(project),
                "--format",
                "text",
            )
            self.assertEqual(visual.returncode, 0)
            for label in (
                "Método:",
                "Perfil:",
                "Plano ativo:",
                "modo grouped",
                "Gate atual:",
                "Release:",
                "Auditoria:",
                "Manual:",
                "Telemetria:",
                "Bloqueios:",
            ):
                self.assertIn(label, visual.stdout)

    def test_real_high_risk_fixture_enforces_strict_mode(self) -> None:
        state_path = PROJECT_FIXTURES / "v2-high-strict/docs/living/PROJECT_STATE.md"
        validated = cli_json("validate-state", str(state_path))
        status = cli_json("status", str(state_path))
        policy = cli_json(
            "policy", "--profile", "full", "--risk", "high", "--change", "payment"
        )
        self.assertTrue(validated["valid"])
        self.assertEqual(status["plans"], {"P01": "approved"})
        self.assertEqual(status["next_plan"], "P01")
        self.assertEqual(status["next_execution_mode"], "strict")
        self.assertEqual(policy["execution"], "strict")
        self.assertEqual(policy["review"], "per_task")

    def test_old_release_fixture_cannot_prove_current_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = json.loads(read(FIXTURES / "project-state-v2.json"))
            state["release"]["candidate"] = {
                "id": "rc-1",
                "revision": "new-revision",
                "build": "build-42",
                "checksum": "sha256:release-42",
            }
            state_path = root / "state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            proof = cli_json(
                "proof-map",
                "--state",
                str(state_path),
                "--evidence",
                str(FIXTURES / "release-evidence-old.json"),
                "--output",
                str(root / "proof.json"),
            )
            self.assertEqual(proof["automated_proven"], 0)
            self.assertEqual(proof["automation_gaps"], ["pytest -q", "playwright test"])

    def test_disabled_telemetry_creates_no_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = root / "state.json"
            shutil.copy(FIXTURES / "project-state-v2.json", state_path)
            result = cli_json(
                "telemetry",
                "record",
                "--state",
                str(state_path),
                "--root",
                str(root),
                "--plan",
                "P01",
                "--duration-ms",
                "10",
            )
            self.assertFalse(result["enabled"])
            self.assertFalse(result["recorded"])
            self.assertEqual(list(root.glob("**/*.jsonl")), [])

    def test_telemetry_path_escape_is_rejected_by_state_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            root = base / "project"
            root.mkdir()
            state = json.loads(read(FIXTURES / "project-state-v2.json"))
            state["telemetry"] = {"enabled": True, "path": "../escaped.jsonl"}
            state_path = root / "state.json"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            result = cli("validate-state", str(state_path))
            self.assertEqual(result.returncode, 2)
            self.assertIn("state.telemetry.path", result.stderr)
            self.assertFalse((base / "escaped.jsonl").exists())


class SkillBehaviorContracts(unittest.TestCase):
    def test_executor_has_no_branch_fallback_or_task_minimum(self) -> None:
        executor = read(SKILLS["executar-plano"])
        planning = read(SKILLS["sdd-planning"])
        self.assertIn("Não existe fallback para branch atual", executor)
        self.assertIn("Não há mínimo ou alvo de tarefas", planning)
        self.assertNotIn("4–10 tarefas", planning)

    def test_planning_commit_and_versioned_workspace_are_mandatory(self) -> None:
        executor = read(SKILLS["executar-plano"])
        planning = read(SKILLS["sdd-planning"])
        contract = read(ROOT / "skills/_shared/METHOD_CONTRACT.md")
        self.assertIn("commit local atômico", planning)
        self.assertIn("git status --porcelain", planning)
        self.assertIn("--planning-version v1", executor)
        self.assertIn("Mudança preexistente bloqueia", executor)
        self.assertIn("bm/v1-p01", contract)
        self.assertIn("bm/v2-p01", contract)

    def test_planning_research_and_simplification_are_enforced(self) -> None:
        planning = read(SKILLS["sdd-planning"])
        contract = read(ROOT / "skills/_shared/METHOD_CONTRACT.md")
        research = read(ROOT / "skills/sdd-planning/references/stack-research.md")
        for expected in (
            "STACK_RESEARCH.md",
            "fontes primárias",
            "deferred_scope",
            "planning-audit",
            "Preservar 100%",
            "scope_split_approved: true",
            "PLANO Task N",
        ):
            self.assertIn(expected, planning)
        self.assertIn("Standard 16/40/6/24.000", contract)
        self.assertIn("teto de 7 planos/16 unidades", contract)
        self.assertIn("nunca reduzir escopo automaticamente", contract)
        self.assertIn("Acessado em: YYYY-MM-DD", research)
        self.assertIn("documentação oficial", research)

    def test_root_superpowers_is_ignored_and_persistent_docs_are_versioned(self) -> None:
        planning = read(SKILLS["sdd-planning"])
        executor = read(SKILLS["executar-plano"])
        contract = read(ROOT / "skills/_shared/METHOD_CONTRACT.md")
        self.assertIn("repo-hygiene migrate", planning)
        self.assertIn("repo-hygiene check", executor)
        self.assertIn("/.superpowers/", contract)
        self.assertIn("docs/bianchini/legacy/root-superpowers/", contract)
        self.assertIn("/.superpowers/", read(ROOT / ".gitignore"))

    def test_completed_legacy_execution_requires_automatic_idle_v2_transition(self) -> None:
        planning = read(SKILLS["sdd-planning"])
        executor = read(SKILLS["executar-plano"])
        contract = read(ROOT / "skills/_shared/METHOD_CONTRACT.md")
        self.assertIn("legacy-transition --repo", executor)
        self.assertIn("--completed", executor)
        self.assertIn("não pedir nova aprovação de migração", executor)
        self.assertIn("planning_status: idle", planning)
        self.assertIn("Não chamar `writing-plans`", planning)
        self.assertIn("Encerramento definitivo do legado", contract)
        self.assertIn("árvore limpa", contract)

    def test_homologation_and_manual_contracts_are_explicit(self) -> None:
        homologation = read(SKILLS["homologar-sistema"])
        self.assertIn("## 2. Automação primeiro", homologation)
        self.assertIn("manual_pdf: none", homologation)
        self.assertIn("manual_pdf: quick_start", homologation)
        self.assertIn("manual_pdf: full", homologation)
        self.assertIn("Não repetir manualmente", homologation)

    def test_architecture_and_status_skills_exist_in_readme(self) -> None:
        readme = read(ROOT / "README.md")
        self.assertIn("/auditar-arquitetura", readme)
        self.assertIn("/status-projeto", readme)

    def test_skill_activation_is_explicit_or_scoped_to_method_v2(self) -> None:
        for name, path in SKILLS.items():
            with self.subTest(skill=name):
                description = frontmatter(read(path))["description"]
                self.assertTrue(
                    f"/{name}" in description or "method_version 2" in description
                )
        audit_description = frontmatter(read(SKILLS["auditar-arquitetura"]))["description"]
        self.assertIn("somente", audit_description)
        self.assertIn("não ativa por risco", audit_description)

    def test_architecture_audit_is_manual_hotspot_report_only(self) -> None:
        audit = read(SKILLS["auditar-arquitetura"])
        for expected in (
            "git log --stat",
            "git diff --name-only",
            "Strong",
            "Worth exploring",
            "Speculative",
            "Problema",
            "Proposta",
            "Benefício",
            "Risco",
            "Prioridade",
            "HTML é opcional",
            "Defeitos funcionais diretos",
            "REPORT_ONLY",
        ):
            self.assertIn(expected, audit)
        planning = read(SKILLS["sdd-planning"])
        self.assertIn("não a executar automaticamente", planning)


if __name__ == "__main__":
    unittest.main()
