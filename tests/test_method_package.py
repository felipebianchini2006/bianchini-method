"""Cenários comportamentais e integridade do Bianchini Method v2."""

from __future__ import annotations

import json
import hashlib
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
    "executar-direto",
    "auditar-arquitetura",
    "status-projeto",
    "corrigir-bug",
    "homologar-sistema",
)
SKILLS = {name: ROOT / "skills" / name / "SKILL.md" for name in SKILL_NAMES}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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

    def test_public_skills_have_valid_frontmatter(self) -> None:
        for name, path in SKILLS.items():
            with self.subTest(skill=name):
                metadata = frontmatter(read(path))
                self.assertEqual(metadata.get("name"), name)
                self.assertIn("Use ", metadata.get("description", ""))
                self.assertLessEqual(len(read(path).splitlines()), 250)
                if name == "executar-direto":
                    self.assertEqual(metadata.get("disable-model-invocation"), "true")

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

    def test_operational_planning_limits_live_only_in_cli(self) -> None:
        documentation = "\n".join(
            read(path)
            for path in (
                ROOT / "README.md",
                ROOT / "CHANGELOG.md",
                ROOT / "skills/_shared/METHOD_CONTRACT.md",
                ROOT / "skills/sdd-planning/SKILL.md",
            )
        )
        for duplicated_limits in (
            "7 planos/16 unidades",
            "Standard 16/40",
            "Full 32/80",
            "8.000 palavras",
            "24.000",
            "48.000",
            "Lean 2, Standard 3, Full 5",
            "`lean` | 2",
        ):
            self.assertNotIn(duplicated_limits, documentation)

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
            "DirectExecutionScenarios",
            "AgentContractScenarios",
            "SkillBehaviorContracts",
            "CodexOverlayPackageTests",
            "ReviewGuardScenarios",
            "CodexInstallerScenarios",
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

    def test_corrupted_v2_json_never_falls_back_to_legacy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = root / "PROJECT_STATE.md"
            state.write_text('{"method_version": 2, BROKEN', encoding="utf-8")
            result = cli("route", str(state), "--repo", str(root))
            self.assertEqual(result.returncode, 3)
            self.assertIn("PROJECT_STATE inválido", result.stderr)
            self.assertNotIn("Superpowers indisponível", result.stderr)

    def test_unknown_state_without_legacy_evidence_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = root / "PROJECT_STATE.md"
            state.write_text("# arquivo desconhecido\nstatus geral indefinido\n", encoding="utf-8")
            result = cli("route", str(state), "--repo", str(root))
            self.assertEqual(result.returncode, 3)
            self.assertIn("não foi possível determinar method_version com segurança", result.stderr)

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
    def make_project(
        self,
        root: Path,
        plan_count: int = 1,
        research_mode: str = "targeted_web",
    ) -> Path:
        scope = root / "docs/bianchini/v1/inputs/APPROVED_SCOPE.md"
        research = root / "docs/bianchini/v1/STACK_RESEARCH.md"
        spec = root / "docs/bianchini/v1/specs/system.md"
        review = root / "docs/bianchini/v1/PLANNING_REVIEW.md"
        for path in (scope, research, spec, review):
            path.parent.mkdir(parents=True, exist_ok=True)
        scope.write_text("# Escopo aprovado\n\nEntregar API de registros.\n", encoding="utf-8")
        research.write_text(
            "# Stack Research — v1\n\n"
            f"Research mode: {research_mode}\n"
            "Motivo: menor modo suficiente para as decisões do ciclo.\n\n"
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
            "research_mode": research_mode,
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

    def test_repo_only_research_is_valid_without_external_url(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = self.make_project(root, research_mode="repo_only")
            research = root / "docs/bianchini/v1/STACK_RESEARCH.md"
            research.write_text(
                "# Stack Research — v1\n\n"
                "Research mode: repo_only\n"
                "Motivo: stack estabelecida e nenhuma integração nova.\n\n"
                "## Stack detectada\n\n- Python 3.13 já fixado no repositório.\n\n"
                "## Inventário local\n\n"
                "- Manifests: pyproject.toml.\n"
                "- Lockfiles: nenhum.\n"
                "- CI: workflow existente.\n"
                "- Testes: unittest.\n"
                "- Padrões locais: CLI somente stdlib.\n\n"
                "## Decisões aplicadas\n\n- Reusar o CLI existente.\n\n"
                "## Riscos e lacunas\n\n- Nenhum conhecido.\n",
                encoding="utf-8",
            )
            result = cli_json(
                "planning-audit", str(state), "--root", str(root), "--strict"
            )
            self.assertEqual(result["research_mode"], "repo_only")

    def test_full_research_requires_critical_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_project(root, research_mode="full")
            state = json.loads(read(state_path))
            state["assurance_profile"] = "full"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            result = cli(
                "planning-audit", str(state_path), "--root", str(root), "--strict"
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("seção obrigatória do modo full", result.stderr)

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

    def test_isolated_critical_unit_uses_strict_without_promoting_project_to_full(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_project(root, plan_count=3)
            state = json.loads(read(state_path))
            state["plans"][2].update(
                {"risk": "critical", "execution": "strict", "review": "per_task"}
            )
            state["assurance_profile"] = "standard"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            accepted = cli_json(
                "planning-audit", str(state_path), "--root", str(root), "--strict"
            )
            self.assertEqual(accepted["recommended_profile"], "standard")
            self.assertNotEqual(accepted["recommended_profile"], "full")
            self.assertEqual(state["plans"][2]["execution"], "strict")

    def test_interdependent_critical_plans_recommend_full(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_project(root, plan_count=2, research_mode="full")
            state = json.loads(read(state_path))
            state["assurance_profile"] = "full"
            for plan in state["plans"]:
                plan.update({"risk": "critical", "execution": "strict", "review": "per_task"})
            state["plans"][1]["depends_on"] = [state["plans"][0]["id"]]
            state_path.write_text(json.dumps(state), encoding="utf-8")
            research = root / "docs/bianchini/v1/STACK_RESEARCH.md"
            research.write_text(
                read(research)
                + "\n## Escopo da pesquisa\n\n- Dois subsistemas críticos.\n"
                + "\n## Decisões críticas\n\n- Ordem e isolamento dos gates.\n",
                encoding="utf-8",
            )
            accepted = cli_json(
                "planning-audit", str(state_path), "--root", str(root), "--strict"
            )
            self.assertEqual(accepted["recommended_profile"], "full")

    def test_package_size_alone_does_not_promote_assurance_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_project(root)
            research = root / "docs/bianchini/v1/STACK_RESEARCH.md"
            research.write_text(read(research) + ("contexto informativo " * 30_000), encoding="utf-8")
            accepted = cli_json(
                "planning-audit", str(state_path), "--root", str(root), "--strict"
            )
            self.assertEqual(accepted["recommended_profile"], "lean")
            self.assertGreater(accepted["metrics"]["package_words"], 48_000)
            self.assertNotIn("active_context_words", accepted["metrics"])
            self.assertIn("shared_context_words", accepted["metrics"])
            self.assertIn("max_plan_words", accepted["metrics"])
            self.assertIn("max_execution_unit_words", accepted["metrics"])

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

    def test_approved_quality_package_without_research_mode_remains_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_project(root)
            state = json.loads(read(state_path))
            state["planning"].pop("research_mode")
            state["planning_status"] = "approved"
            state["approval"].update(
                {
                    "status": "approved",
                    "approved_at": "2026-08-11T00:01:00Z",
                    "approved_by": "owner",
                    "approved_plans": [state["plans"][0]["id"]],
                }
            )
            state["approval"]["package"]["manifest_digest"] = "a" * 64
            state["plans"][0]["status"] = "approved"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            research = root / "docs/bianchini/v1/STACK_RESEARCH.md"
            research.write_text(
                re.sub(r"(?m)^(?:Research mode|Motivo):.*\n", "", read(research)),
                encoding="utf-8",
            )
            accepted = cli_json(
                "planning-audit", str(state_path), "--root", str(root), "--strict"
            )
            self.assertEqual(accepted["research_mode"], "targeted_web")
            self.assertIn("somente para compatibilidade", accepted["warnings"][0])


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

    def test_seam_budget_survives_task_rename(self) -> None:
        value = self.policy(
            "--profile", "full", "--risk", "high", "--round", "1",
            "--risk-seam", "financial-migration-recovery", "--seam-round", "5",
        )
        self.assertTrue(value["breaker"])
        self.assertEqual(value["breaker_scope"], "risk_seam")
        self.assertEqual(value["risk_seam"], "financial-migration-recovery")
        self.assertEqual(value["effective_fix_round"], 5)
        self.assertFalse(value["hypothesis_invalidated"])

    def test_structural_finding_invalidates_hypothesis_immediately(self) -> None:
        value = self.policy(
            "--profile", "full", "--risk", "critical", "--round", "1",
            "--structural-finding", "crash_window",
            "--structural-finding", "toctou",
        )
        self.assertTrue(value["breaker"])
        self.assertTrue(value["hypothesis_invalidated"])
        self.assertTrue(value["redesign_required"])
        self.assertEqual(value["structural_findings"], ["crash_window", "toctou"])

    def test_two_consecutive_seam_findings_trip_early_breaker(self) -> None:
        tripped = self.policy(
            "--profile", "standard", "--risk", "medium", "--round", "1",
            "--risk-seam", "payments-ledger", "--consecutive-seam-findings", "2",
        )
        self.assertTrue(tripped["breaker"])
        self.assertTrue(tripped["redesign_required"])
        single = self.policy(
            "--profile", "standard", "--risk", "medium", "--round", "1",
            "--risk-seam", "payments-ledger", "--consecutive-seam-findings", "1",
        )
        self.assertFalse(single["breaker"])
        self.assertFalse(single["redesign_required"])

    def test_seam_counters_require_named_seam(self) -> None:
        result = cli("policy", "--profile", "full", "--risk", "high", "--seam-round", "3")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--risk-seam", result.stderr)

    def test_epistemic_breaker_is_documented_in_contracts(self) -> None:
        contract = read(ROOT / "skills/_shared/METHOD_CONTRACT.md")
        for text in (
            "risk_seam",
            "não zera a contagem do mesmo seam",
            "crash window",
            "TOCTOU",
            "máquina de estados",
            "matriz de falhas",
            "não é mudança mínima",
        ):
            self.assertIn(text, contract)
        executor = read(SKILLS["executar-plano"])
        self.assertIn("Fix round é hipótese, não entrega", executor)
        self.assertIn("--consecutive-seam-findings", executor)
        bugfix = read(SKILLS["corrigir-bug"])
        self.assertIn("crash window", bugfix)
        self.assertIn("renomear a tarefa não zera o seam", bugfix)
        reviewer = read(ROOT / "skills/_shared/agents/plan-reviewer.md")
        self.assertIn("Espaço negativo", reviewer)
        self.assertIn("estado durável de retomada", reviewer)
        self.assertIn("entre inspeção e ação", reviewer)

    def test_visual_bug_uses_visual_evidence(self) -> None:
        value = self.policy("--profile", "lean", "--risk", "low", "--change", "visual")
        self.assertEqual(value["visual_validation"], "screenshot_or_visual_regression")

    def test_quality_strategy_keeps_unit_execution_focused(self) -> None:
        value = self.policy(
            "--profile", "standard", "--risk", "medium", "--change", "business-rule"
        )
        strategy = value["test_strategy"]
        self.assertEqual(
            strategy["fast"],
            [
                "targeted_unit_if_logic_changed",
                "targeted_integration_if_boundary_changed",
                "related_regression",
            ],
        )
        self.assertNotIn("critical_journey_e2e", strategy["fast"])
        self.assertNotIn("selective_mutation", strategy["fast"])
        self.assertIn("critical_journey_e2e", strategy["plan"])
        self.assertIn("selective_mutation_if_required", strategy["plan"])
        self.assertIn("full_regression", strategy["release"])
        self.assertIn("current_mutation_evidence_if_required", strategy["release"])

    def test_mutation_policy_is_selective_and_never_uses_global_score(self) -> None:
        visual = self.policy(
            "--profile", "lean", "--risk", "low", "--change", "visual"
        )
        business = self.policy(
            "--profile", "standard", "--risk", "medium", "--change", "business-rule"
        )
        payment = self.policy(
            "--profile", "full", "--risk", "critical", "--change", "payment"
        )
        self.assertEqual(visual["mutation_policy"]["mode"], "not_required")
        self.assertEqual(business["mutation_policy"]["mode"], "selective")
        self.assertEqual(payment["mutation_policy"]["mode"], "required_selective")
        for value in (visual, business, payment):
            self.assertFalse(value["mutation_policy"]["global_score_gate"])
            self.assertEqual(
                value["mutation_policy"]["blocking_rule"],
                "survivor_changes_approved_high_or_critical_behavior",
            )

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

    def test_homologation_combines_automation_with_real_system_acceptance(self) -> None:
        value = self.policy("--profile", "standard", "--risk", "medium")
        self.assertEqual(
            value["homologation_order"],
            [
                "automated_regression",
                "coded_e2e",
                "proof_map",
                "real_system_pass",
                "visual_sweep",
            ],
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

    def test_legacy_transition_completed_flag_blocks_in_progress_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            state_path = repo / "docs/living/PROJECT_STATE.md"
            state_path.parent.mkdir(parents=True)
            legacy = b"method_version: 1\nstatus: in_progress\n"
            state_path.write_bytes(legacy)
            git(repo, "add", "docs/living/PROJECT_STATE.md")
            git(repo, "commit", "-m", "legacy phase active")
            result = cli(
                "legacy-transition", "--repo", str(repo), "--state",
                "docs/living/PROJECT_STATE.md", "--completed",
            )
            self.assertEqual(result.returncode, 3)
            self.assertIn("estado legado ainda está", result.stderr)
            self.assertEqual(state_path.read_bytes(), legacy)

    def test_legacy_transition_requires_marker_or_completion_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            state_path = repo / "docs/living/PROJECT_STATE.md"
            state_path.parent.mkdir(parents=True)
            state_path.write_text("method_version: 1\ncycle: final\n", encoding="utf-8")
            git(repo, "add", "docs/living/PROJECT_STATE.md")
            git(repo, "commit", "-m", "legacy state without completion marker")
            result = cli(
                "legacy-transition", "--repo", str(repo), "--state",
                "docs/living/PROJECT_STATE.md", "--completed",
            )
            self.assertEqual(result.returncode, 3)
            self.assertIn("--completion-proof", result.stderr)

    def test_legacy_transition_rejects_untracked_completion_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            state_path = repo / "docs/living/PROJECT_STATE.md"
            state_path.parent.mkdir(parents=True)
            state_path.write_text("method_version: 1\ncycle: final\n", encoding="utf-8")
            (repo / ".gitignore").write_text(
                "/.superpowers/\n/proof.md\n", encoding="utf-8"
            )
            git(repo, "add", ".gitignore", "docs/living/PROJECT_STATE.md")
            git(repo, "commit", "-m", "legacy state without completion marker")
            (repo / "proof.md").write_text(
                "Entrega concluída; gates passed e aceite registrado.\n", encoding="utf-8"
            )
            result = cli(
                "legacy-transition", "--repo", str(repo), "--state",
                "docs/living/PROJECT_STATE.md", "--completed",
                "--completion-proof", "proof.md",
            )
            self.assertEqual(result.returncode, 3)
            self.assertIn("proof deve estar rastreado e commitado", result.stderr)

    def test_legacy_transition_accepts_committed_completion_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            state_path = repo / "docs/living/PROJECT_STATE.md"
            state_path.parent.mkdir(parents=True)
            state_path.write_text("method_version: 1\ncycle: final\n", encoding="utf-8")
            proof = repo / "proof.md"
            proof.write_text(
                "Entrega concluída; gates passed e aceite registrado.\n", encoding="utf-8"
            )
            git(repo, "add", "docs/living/PROJECT_STATE.md", "proof.md")
            git(repo, "commit", "-m", "record legacy completion proof")
            result = cli_json(
                "legacy-transition", "--repo", str(repo), "--state",
                "docs/living/PROJECT_STATE.md", "--completed",
                "--completion-proof", "proof.md",
            )
            self.assertEqual(result["completion_proof"]["path"], "proof.md")
            self.assertEqual(result["completion_proof"]["sha256"], file_sha256(proof))

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

    def test_repo_hygiene_conflict_is_transactional(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            source_a = repo / ".superpowers/sdd/a.txt"
            source_b = repo / ".superpowers/sdd/b.txt"
            source_a.parent.mkdir(parents=True)
            source_a.write_text("a source\n", encoding="utf-8")
            source_b.write_text("b source\n", encoding="utf-8")
            git(repo, "add", "-f", ".superpowers/sdd/a.txt", ".superpowers/sdd/b.txt")
            git(repo, "commit", "-m", "track two legacy artifacts")
            destination = repo / "docs/bianchini/legacy/root-superpowers/sdd/b.txt"
            destination.parent.mkdir(parents=True)
            destination.write_text("conflict\n", encoding="utf-8")
            git(repo, "add", destination.relative_to(repo).as_posix())
            git(repo, "commit", "-m", "create conflicting destination")

            result = cli("repo-hygiene", "migrate", "--repo", str(repo))
            self.assertEqual(result.returncode, 3)
            self.assertIn("conteúdo diferente", result.stderr)
            self.assertEqual(source_a.read_text(encoding="utf-8"), "a source\n")
            self.assertEqual(source_b.read_text(encoding="utf-8"), "b source\n")
            self.assertFalse(
                (repo / "docs/bianchini/legacy/root-superpowers/sdd/a.txt").exists()
            )

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


class DirectExecutionScenarios(unittest.TestCase):
    def start(
        self,
        repo: Path,
        slug: str = "small-dashboard",
        risk: str = "low",
        change_kind: str = "behavioral",
        *extra: str,
    ) -> subprocess.CompletedProcess[str]:
        return cli(
            "direct",
            "start",
            "--repo",
            str(repo),
            "--slug",
            slug,
            "--objective",
            "Entregar painel pequeno e coeso",
            "--scope",
            "Um painel com um fluxo principal",
            "--current-state",
            "App base com app.txt versionado e sem painel implementado",
            "--acceptance",
            "O fluxo principal funciona",
            "--verification",
            "python3 -m unittest",
            "--risk",
            risk,
            "--change-kind",
            change_kind,
            *extra,
        )

    def test_low_risk_small_project_starts_direct_on_local_branch(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            base = init_repo(repo)
            result = self.start(repo)
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["mode"], "direct")
            self.assertEqual(payload["status"], "active")
            self.assertEqual(git(repo, "branch", "--show-current"), "bm/direct/small-dashboard")
            self.assertEqual(payload["base_commit"], base)
            scratch = repo / ".superpowers/bianchini/direct/small-dashboard"
            for name in ("BRIEF.md", "PROGRESS.md", "RESULT.md"):
                self.assertTrue((scratch / name).is_file())
            self.assertFalse((repo / "docs/living/PROJECT_STATE.md").exists())
            self.assertFalse((repo / "docs/bianchini").exists())
            self.assertEqual(git(repo, "status", "--porcelain"), "")

    def test_medium_cohesive_feature_stays_direct(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            payload = json.loads(self.start(repo, risk="medium").stdout)
            self.assertEqual(payload["mode"], "direct")
            self.assertEqual(payload["risk"], "medium")

    def test_bug_requires_red_green_and_visual_accepts_visual_evidence(self) -> None:
        for kind, expected in (("bug", "red_green"), ("visual", "visual_evidence")):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                repo = Path(temp) / "repo"
                init_repo(repo)
                payload = json.loads(self.start(repo, change_kind=kind).stdout)
                self.assertEqual(payload["verification_strategy"], expected)

    def test_high_risk_triggers_escalate_to_sdd(self) -> None:
        scenarios = (
            (
                "payment",
                (
                    "--hazard",
                    "new-payment",
                    "--command",
                    "npm test -- billing",
                    "--result-entry",
                    "Padrão atual não cobre cobrança nova",
                ),
            ),
            ("authentication", ("--hazard", "new-auth")),
            ("two-subsystems", ("--subsystems", "2")),
        )
        for slug, extra in scenarios:
            with self.subTest(slug=slug), tempfile.TemporaryDirectory() as temp:
                repo = Path(temp) / "repo"
                init_repo(repo)
                result = self.start(repo, slug, "medium", "behavioral", *extra)
                self.assertEqual(result.returncode, 0, result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual(payload["mode"], "escalated")
                self.assertEqual(payload["next_step"], "/sdd-planning")
                self.assertEqual(git(repo, "branch", "--show-current"), "main")
                result_file = Path(payload["result"])
                self.assertIn("Status: escalado", read(result_file))
                self.assertIn(payload["blockers"][0], read(result_file))
                if slug == "payment":
                    self.assertIn("npm test -- billing", read(result_file))
                    self.assertIn("Padrão atual não cobre cobrança nova", read(result_file))

    def test_dirty_main_and_detached_head_are_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "dirty"
            init_repo(repo)
            (repo / "unrelated.txt").write_text("user work\n", encoding="utf-8")
            dirty = self.start(repo)
            self.assertEqual(dirty.returncode, 3)
            self.assertIn("alterações não relacionadas", dirty.stderr)
            self.assertEqual(git(repo, "branch", "--show-current"), "main")

        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "related"
            init_repo(repo)
            (repo / "feature.txt").write_text("valid partial work\n", encoding="utf-8")
            related = self.start(
                repo,
                "related-change",
                "low",
                "behavioral",
                "--related-change",
                "feature.txt",
            )
            self.assertEqual(related.returncode, 0, related.stderr)
            self.assertEqual(git(repo, "branch", "--show-current"), "bm/direct/related-change")
            progress = repo / ".superpowers/bianchini/direct/related-change/PROGRESS.md"
            self.assertIn("feature.txt", read(progress))

        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "detached"
            init_repo(repo)
            git(repo, "checkout", "--detach")
            detached = self.start(repo)
            self.assertEqual(detached.returncode, 4)
            self.assertIn("detached HEAD", detached.stderr)

    def test_checkpoint_is_resumable_and_status_reports_direct_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            started = json.loads(self.start(repo).stdout)
            checkpoint = cli_json(
                "direct",
                "checkpoint",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--checkpoint",
                "Implementação principal concluída",
                "--changed-file",
                "src/dashboard.ts",
                "--command",
                "npm test -- dashboard",
                "--evidence",
                self.EVIDENCE_PASSED,
                "--verification",
                "passed",
                "--next-action",
                "Executar build",
            )
            status = cli_json(
                "direct", "status", "--repo", str(repo), "--slug", "small-dashboard"
            )
            self.assertEqual(status["mode"], "direct")
            self.assertEqual(status["last_checkpoint"], checkpoint["last_checkpoint"])
            self.assertEqual(status["verification"], "passed")
            self.assertEqual(status["branch"], started["branch"])
            second_status = cli_json(
                "direct", "status", "--repo", str(repo), "--slug", "small-dashboard"
            )
            self.assertEqual(status, second_status)

            git(repo, "switch", "main")
            wrong_branch = cli(
                "direct", "status", "--repo", str(repo), "--slug", "small-dashboard"
            )
            self.assertEqual(wrong_branch.returncode, 4)
            self.assertIn("pertence à branch", wrong_branch.stderr)

    EVIDENCE_PASSED = json.dumps(
        {
            "kind": "command",
            "command": "python3 -m unittest",
            "exit_code": 0,
            "status": "passed",
            "summary": "mypy: Found 0 errors in 10 source files; suite verde",
        }
    )

    def checkpoint_passed(self, repo: Path, slug: str = "small-dashboard") -> None:
        cli_json(
            "direct",
            "checkpoint",
            "--repo",
            str(repo),
            "--slug",
            slug,
            "--checkpoint",
            "Implementação e verificação concluídas",
            "--command",
            "python3 -m unittest",
            "--result-entry",
            "Suite passou",
            "--evidence",
            self.EVIDENCE_PASSED,
            "--verification",
            "passed",
            "--next-action",
            "Concluir",
        )

    def test_finish_writes_result_without_project_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            self.start(repo)
            self.checkpoint_passed(repo)
            finished = cli_json(
                "direct",
                "finish",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--status",
                "completed",
                "--behavior",
                "Painel entregue",
                "--verification",
                "testes e build passaram",
                "--next-action",
                "Revisar e commitar",
            )
            self.assertEqual(finished["status"], "completed")
            self.assertIn("Status: concluído", read(Path(finished["result"])))
            self.assertFalse((repo / "docs/living/PROJECT_STATE.md").exists())

    def test_discovered_structural_risk_finishes_with_sdd_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            self.start(repo)
            finished = cli_json(
                "direct",
                "finish",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--status",
                "escalated",
                "--limitation",
                "Autorização nova descoberta",
                "--next-action",
                "Executar /sdd-planning",
            )
            self.assertEqual(finished["mode"], "escalated")
            self.assertEqual(finished["next_step"], "/sdd-planning")
            self.assertIn("Status: escalado", read(Path(finished["result"])))

    def test_scratch_path_traversal_and_symlink_escape_are_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / "repo"
            init_repo(repo)
            escaped = self.start(repo, "../escape")
            self.assertEqual(escaped.returncode, 2)
            self.assertFalse((root / "escape").exists())

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / "repo"
            outside = root / "outside"
            init_repo(repo)
            outside.mkdir()
            (repo / ".superpowers").symlink_to(outside, target_is_directory=True)
            escaped = self.start(repo)
            self.assertEqual(escaped.returncode, 2)
            self.assertFalse((outside / "bianchini").exists())

    def test_scratch_is_excluded_via_git_info_without_touching_gitignore(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            repo.mkdir(parents=True)
            git(repo, "init", "-b", "main")
            git(repo, "config", "user.name", "Bianchini Test")
            git(repo, "config", "user.email", "test@example.invalid")
            (repo / "app.txt").write_text("base\n", encoding="utf-8")
            git(repo, "add", "app.txt")
            git(repo, "commit", "-m", "initial")
            result = self.start(repo)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(git(repo, "status", "--porcelain"), "")
            exclude = repo / ".git/info/exclude"
            self.assertIn("/.superpowers/", read(exclude))
            self.assertFalse((repo / ".gitignore").exists())
            scratch = repo / ".superpowers/bianchini/direct/small-dashboard"
            for name in ("BRIEF.md", "PROGRESS.md", "RESULT.md", ".state.json"):
                self.assertTrue((scratch / name).is_file())

    def test_completed_requires_structured_passed_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            self.start(repo)
            finish_args = (
                "direct",
                "finish",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--status",
                "completed",
                "--behavior",
                "Painel entregue",
                "--next-action",
                "Revisar",
            )
            pending = cli(*finish_args, "--verification", "testes passaram")
            self.assertEqual(pending.returncode, 3)
            self.assertIn("conclusão sem verificação suficiente", pending.stderr)
            self.assertIn("evidência estruturada", pending.stderr)

            no_proof = cli(
                "direct",
                "checkpoint",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--checkpoint",
                "Tentativa sem prova",
                "--verification",
                "passed",
                "--next-action",
                "Concluir",
            )
            self.assertEqual(no_proof.returncode, 3)
            self.assertIn("exige ao menos uma evidência estruturada aprovada", no_proof.stderr)

            self.checkpoint_passed(repo)
            free_text_only = cli_json(
                *finish_args, "--verification", "narrativa livre não decide o gate"
            )
            self.assertEqual(free_text_only["status"], "completed")
            result_text = read(Path(free_text_only["result"]))
            self.assertIn("command: python3 -m unittest — passed", result_text)
            self.assertIn("0 errors", result_text)

    def test_structured_evidence_rejects_inconsistent_or_failed_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            self.start(repo)
            checkpoint_args = (
                "direct",
                "checkpoint",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--checkpoint",
                "Verificação executada",
                "--next-action",
                "Continuar",
            )
            inconsistent = cli(
                *checkpoint_args,
                "--evidence",
                json.dumps(
                    {
                        "kind": "command",
                        "command": "pytest",
                        "exit_code": 1,
                        "status": "passed",
                        "summary": "pytest exit code 1",
                    }
                ),
            )
            self.assertEqual(inconsistent.returncode, 2)
            self.assertIn("exit_code 0", inconsistent.stderr)

            malformed = cli(*checkpoint_args, "--evidence", "não é json")
            self.assertEqual(malformed.returncode, 2)
            self.assertIn("JSON válido", malformed.stderr)

            missing_ref = cli(
                *checkpoint_args,
                "--evidence",
                json.dumps(
                    {"kind": "browser", "status": "passed", "summary": "smoke ok"}
                ),
            )
            self.assertEqual(missing_ref.returncode, 2)
            self.assertIn("campo evidence", missing_ref.stderr)

            failed_run = cli_json(
                *checkpoint_args,
                "--evidence",
                json.dumps(
                    {
                        "kind": "command",
                        "command": "python3 -m unittest",
                        "exit_code": 1,
                        "status": "failed",
                        "summary": "2 falhas na suite",
                    }
                ),
            )
            self.assertEqual(failed_run["verification"], "pending")
            blocked = cli(
                "direct",
                "finish",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--status",
                "completed",
                "--behavior",
                "Painel entregue",
                "--next-action",
                "Revisar",
            )
            self.assertEqual(blocked.returncode, 3)
            self.assertIn("evidência atual não aprovada", blocked.stderr)
            self.checkpoint_passed(repo)
            recovered = cli_json(
                "direct",
                "finish",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--status",
                "completed",
                "--behavior",
                "Painel entregue",
                "--next-action",
                "Revisar",
            )
            self.assertEqual(recovered["status"], "completed")

    def test_planned_commands_must_be_proven_or_waived(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            self.start(repo)
            cli_json(
                "direct",
                "checkpoint",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--checkpoint",
                "Smoke visual executado",
                "--evidence",
                json.dumps(
                    {
                        "kind": "browser",
                        "status": "passed",
                        "evidence": "artifacts/smoke/dashboard.png",
                        "summary": "Jornada principal concluída",
                    }
                ),
                "--verification",
                "passed",
                "--next-action",
                "Concluir",
            )
            finish_args = (
                "direct",
                "finish",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--status",
                "completed",
                "--behavior",
                "Painel entregue",
                "--next-action",
                "Revisar",
            )
            unproven = cli(*finish_args)
            self.assertEqual(unproven.returncode, 3)
            self.assertIn("comando de verificação planejado sem evidência", unproven.stderr)
            self.assertIn("python3 -m unittest", unproven.stderr)

            wrong_waiver = cli(
                *finish_args, "--waive-verification", "npm test: não existe no plano"
            )
            self.assertEqual(wrong_waiver.returncode, 3)
            self.assertIn("dispensa não corresponde", wrong_waiver.stderr)

            waived = cli_json(
                *finish_args,
                "--waive-verification",
                "python3 -m unittest: coberto pelo smoke de browser registrado",
            )
            self.assertEqual(waived["status"], "completed")
            result_text = read(Path(waived["result"]))
            self.assertIn("Comando de verificação dispensado", result_text)
            self.assertIn("artifacts/smoke/dashboard.png", result_text)

    def test_completed_blocks_unrecorded_changes_until_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            self.start(repo)
            (repo / "app.txt").write_text("base\npainel\n", encoding="utf-8")
            (repo / "extra.txt").write_text("sobrou\n", encoding="utf-8")
            cli_json(
                "direct",
                "checkpoint",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--checkpoint",
                "Painel implementado",
                "--changed-file",
                "app.txt",
                "--command",
                "python3 -m unittest",
                "--result-entry",
                "Suite passou",
                "--evidence",
                self.EVIDENCE_PASSED,
                "--verification",
                "passed",
                "--next-action",
                "Concluir",
            )
            finish_args = (
                "direct",
                "finish",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--status",
                "completed",
                "--behavior",
                "Painel entregue",
                "--verification",
                "testes e build passaram",
                "--next-action",
                "Revisar",
            )
            blocked = cli(*finish_args)
            self.assertEqual(blocked.returncode, 3)
            self.assertIn("alterações não registradas", blocked.stderr)
            self.assertIn("extra.txt", blocked.stderr)

            malformed = cli(*finish_args, "--accept-unrecorded", "extra.txt")
            self.assertEqual(malformed.returncode, 2)
            self.assertIn("caminho: justificativa", malformed.stderr)

            wrong_path = cli(
                *finish_args, "--accept-unrecorded", "outro.txt: não existe"
            )
            self.assertEqual(wrong_path.returncode, 3)
            self.assertIn("aceite não corresponde", wrong_path.stderr)

            accepted = cli_json(
                *finish_args,
                "--accept-unrecorded",
                "extra.txt: artefato local de build, fora do escopo",
            )
            self.assertEqual(accepted["status"], "completed")
            result_text = read(Path(accepted["result"]))
            self.assertIn("extra.txt", result_text)
            self.assertIn("artefato local de build", result_text)

    def test_finish_records_blocker_reason(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            self.start(repo)
            missing_reason = cli(
                "direct",
                "finish",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--status",
                "blocked",
                "--next-action",
                "Aguardar",
            )
            self.assertEqual(missing_reason.returncode, 3)
            self.assertIn("exige motivo", missing_reason.stderr)

            finished = cli_json(
                "direct",
                "finish",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--status",
                "blocked",
                "--blocker",
                "credencial externa ausente",
                "--next-action",
                "Aguardar credencial",
            )
            self.assertEqual(finished["status"], "blocked")
            self.assertIn("credencial externa ausente", finished["blockers"])
            self.assertIn("credencial externa ausente", read(Path(finished["result"])))

    def test_terminal_states_are_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            self.start(repo)
            self.checkpoint_passed(repo)
            cli_json(
                "direct",
                "finish",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--status",
                "completed",
                "--behavior",
                "Painel entregue",
                "--verification",
                "testes e build passaram",
                "--next-action",
                "Revisar",
            )
            again = cli(
                "direct",
                "finish",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--status",
                "blocked",
                "--next-action",
                "Nada",
            )
            self.assertEqual(again.returncode, 3)
            self.assertIn("estado terminal", again.stderr)
            resumed = self.start(repo)
            self.assertEqual(resumed.returncode, 3)
            self.assertIn("estado terminal", resumed.stderr)
            reopened = cli(
                "direct",
                "reopen",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--next-action",
                "Retomar",
            )
            self.assertEqual(reopened.returncode, 3)
            self.assertIn("imutável", reopened.stderr)

    def test_escalated_execution_cannot_become_completed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            self.start(repo)
            cli_json(
                "direct",
                "finish",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--status",
                "escalated",
                "--blocker",
                "complexidade estrutural descoberta",
                "--next-action",
                "Executar /sdd-planning",
            )
            completed = cli(
                "direct",
                "finish",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--status",
                "completed",
                "--behavior",
                "Painel entregue",
                "--verification",
                "testes passaram",
                "--next-action",
                "Revisar",
            )
            self.assertEqual(completed.returncode, 3)
            self.assertIn("estado terminal", completed.stderr)
            reopened = cli(
                "direct",
                "reopen",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--next-action",
                "Retomar",
            )
            self.assertEqual(reopened.returncode, 3)
            self.assertIn("escalada", reopened.stderr)

    def test_blocked_execution_reopens_preserving_previous_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            self.start(repo)
            cli_json(
                "direct",
                "finish",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--status",
                "blocked",
                "--limitation",
                "Aguardando credencial",
                "--next-action",
                "Aguardar credencial",
            )
            reopened = cli_json(
                "direct",
                "reopen",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--next-action",
                "Retomar com credencial",
            )
            self.assertEqual(reopened["status"], "active")
            scratch = repo / ".superpowers/bianchini/direct/small-dashboard"
            self.assertTrue((scratch / "RESULT-01-blocked.md").is_file())
            self.checkpoint_passed(repo)
            finished = cli_json(
                "direct",
                "finish",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--status",
                "completed",
                "--behavior",
                "Painel entregue",
                "--verification",
                "testes e build passaram",
                "--next-action",
                "Revisar",
            )
            self.assertEqual(finished["status"], "completed")

    def test_brief_identity_change_invalidates_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            self.start(repo)
            same = self.start(repo)
            self.assertEqual(same.returncode, 0, same.stderr)
            self.assertTrue(json.loads(same.stdout)["resumed"])
            changed = self.start(repo, "small-dashboard", "medium")
            self.assertEqual(changed.returncode, 3)
            self.assertIn("digest do brief divergente", changed.stderr)
            self.assertIn("novo slug", changed.stderr)
            updated = self.start(
                repo, "small-dashboard", "medium", "behavioral", "--update-brief"
            )
            self.assertEqual(updated.returncode, 0, updated.stderr)
            payload = json.loads(updated.stdout)
            self.assertTrue(payload["resumed"])
            self.assertEqual(payload["risk"], "medium")
            self.assertEqual(payload["verification"], "pending")

    def test_update_brief_invalidates_previous_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            self.start(repo)
            self.checkpoint_passed(repo)
            updated = self.start(
                repo, "small-dashboard", "medium", "behavioral", "--update-brief"
            )
            self.assertEqual(updated.returncode, 0, updated.stderr)
            blocked = cli(
                "direct",
                "finish",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--status",
                "completed",
                "--behavior",
                "Painel entregue",
                "--next-action",
                "Revisar",
            )
            self.assertEqual(blocked.returncode, 3)
            self.assertIn("evidência estruturada", blocked.stderr)
            self.checkpoint_passed(repo)
            recovered = cli_json(
                "direct",
                "finish",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--status",
                "completed",
                "--behavior",
                "Painel entregue",
                "--next-action",
                "Revisar",
            )
            self.assertEqual(recovered["status"], "completed")

    def test_code_changed_after_evidence_blocks_completion(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            self.start(repo)
            self.checkpoint_passed(repo)
            (repo / "app.txt").write_text("base\nalterado depois do teste\n", encoding="utf-8")
            cli_json(
                "direct",
                "checkpoint",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--checkpoint",
                "Ajuste tardio registrado",
                "--changed-file",
                "app.txt",
                "--verification",
                "passed",
                "--next-action",
                "Concluir",
            )
            stale = cli(
                "direct",
                "finish",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--status",
                "completed",
                "--behavior",
                "Painel entregue",
                "--next-action",
                "Revisar",
            )
            self.assertEqual(stale.returncode, 3)
            self.assertIn("evidência obsoleta", stale.stderr)
            self.checkpoint_passed(repo)
            recovered = cli_json(
                "direct",
                "finish",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--status",
                "completed",
                "--behavior",
                "Painel entregue",
                "--next-action",
                "Revisar",
            )
            self.assertEqual(recovered["status"], "completed")

    def test_visual_retry_with_check_id_replaces_previous_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            self.start(repo)
            cli_json(
                "direct",
                "checkpoint",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--checkpoint",
                "Primeira tentativa visual",
                "--evidence",
                json.dumps(
                    {
                        "kind": "screenshot",
                        "check_id": "dashboard-smoke",
                        "status": "failed",
                        "evidence": "artifacts/smoke/tentativa-a.png",
                        "summary": "Layout quebrado na tentativa A",
                    }
                ),
                "--next-action",
                "Corrigir layout",
            )
            cli_json(
                "direct",
                "checkpoint",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--checkpoint",
                "Segunda tentativa visual",
                "--evidence",
                json.dumps(
                    {
                        "kind": "screenshot",
                        "check_id": "dashboard-smoke",
                        "status": "passed",
                        "evidence": "artifacts/smoke/tentativa-b.png",
                        "summary": "Jornada principal concluída",
                    }
                ),
                "--verification",
                "passed",
                "--next-action",
                "Concluir",
            )
            finished = cli_json(
                "direct",
                "finish",
                "--repo",
                str(repo),
                "--slug",
                "small-dashboard",
                "--status",
                "completed",
                "--behavior",
                "Painel entregue",
                "--waive-verification",
                "python3 -m unittest: coberto pelo smoke visual dashboard-smoke",
                "--next-action",
                "Revisar",
            )
            self.assertEqual(finished["status"], "completed")
            result_text = read(Path(finished["result"]))
            self.assertIn("tentativa-b.png", result_text)
            self.assertNotIn("tentativa-a.png", result_text)

    def test_current_state_is_mandatory_and_rejects_generic_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            init_repo(repo)
            missing = cli(
                "direct",
                "start",
                "--repo",
                str(repo),
                "--slug",
                "sem-estado",
                "--objective",
                "Entregar algo",
                "--scope",
                "Escopo coeso",
                "--acceptance",
                "Funciona",
                "--verification",
                "python3 -m unittest",
            )
            self.assertEqual(missing.returncode, 2)
            self.assertIn("--current-state", missing.stderr)
        for generic in (
            "Arquitetura existente a confirmar por leitura localizada.",
            "Estado não analisado ainda",
            "Arquitetura a verificar depois",
        ):
            with self.subTest(generic=generic), tempfile.TemporaryDirectory() as temp:
                repo = Path(temp) / "repo"
                init_repo(repo)
                rejected = cli(
                    "direct",
                    "start",
                    "--repo",
                    str(repo),
                    "--slug",
                    "generico",
                    "--objective",
                    "Entregar algo",
                    "--scope",
                    "Escopo coeso",
                    "--current-state",
                    generic,
                    "--acceptance",
                    "Funciona",
                    "--verification",
                    "python3 -m unittest",
                )
                self.assertEqual(rejected.returncode, 2)
                self.assertIn("síntese factual", rejected.stderr)

    def test_skill_contract_is_explicit_lightweight_and_has_no_external_agents(self) -> None:
        direct = read(SKILLS["executar-direto"])
        metadata = frontmatter(direct)
        self.assertEqual(metadata["disable-model-invocation"], "true")
        for expected in (
            "zero subagentes",
            "menor diff correto",
            "RED/GREEN",
            "browser",
            "screenshot",
            "/sdd-planning",
            "BRIEF.md",
            "PROGRESS.md",
            "RESULT.md",
        ):
            self.assertIn(expected, direct)
        for forbidden in (
            "invocar Superpowers",
            "Agency Agents",
            "spec central",
            "PLANNING_REVIEW",
            "manual PDF",
        ):
            self.assertIn(forbidden, direct)
        self.assertFalse((ROOT / "skills/agency-agents").exists())
        agent_config = read(ROOT / "skills/executar-direto/agents/openai.yaml")
        self.assertNotIn("subagent", agent_config.lower())
        self.assertIn("allow_implicit_invocation: false", agent_config)
        self.assertIn("Não faça push", direct)
        self.assertIn("instalação global", direct)

    def test_status_skill_checks_direct_execution_before_project_state(self) -> None:
        status_skill = read(SKILLS["status-projeto"])
        self.assertIn("bm.py direct status", status_skill)
        self.assertIn("Modo: direto", status_skill)
        self.assertIn("antes de exigir `PROJECT_STATE.md`", status_skill)


class AgentContractScenarios(unittest.TestCase):
    NAMES = (
        "repo-cartographer",
        "implementation-worker",
        "plan-reviewer",
        "security-reviewer",
        "ui-finish-reviewer",
    )
    CONTRACTS = {
        name: ROOT / "skills/_shared/agents" / f"{name}.md" for name in NAMES
    }

    def test_contracts_exist_are_lean_and_generic(self) -> None:
        for name, path in self.CONTRACTS.items():
            with self.subTest(contract=name):
                self.assertTrue(path.is_file())
                content = read(path)
                for section in (
                    "## Gatilho",
                    "## Entradas",
                    "## Responsabilidade",
                    "## Proibições",
                    "## Saída",
                    "## Critério de conclusão",
                ):
                    self.assertIn(section, content)
                words = len(re.findall(r"\b[\wÀ-ÿ-]+\b", content))
                self.assertLessEqual(words, 350, f"{name}: {words} palavras")
                for forbidden in ("vibe", "personalidade", "emoji", "🧠", "🎯"):
                    self.assertNotIn(forbidden, content.lower())

    def test_direct_mode_keeps_zero_subagents_and_no_catalog(self) -> None:
        direct = read(SKILLS["executar-direto"])
        self.assertIn("zero subagentes", direct)
        self.assertIn("o modo direto não os carrega", direct)
        self.assertIn("não usa o catálogo Agency Agents", direct)

    def test_architecture_audit_requires_explicit_invocation(self) -> None:
        metadata = frontmatter(read(SKILLS["auditar-arquitetura"]))
        self.assertEqual(metadata.get("disable-model-invocation"), "true")
        agent_config = read(ROOT / "skills/auditar-arquitetura/agents/openai.yaml")
        self.assertIn("allow_implicit_invocation: false", agent_config)

    def test_cartographer_scoped_to_planning_with_head_cache(self) -> None:
        planning = read(SKILLS["sdd-planning"])
        self.assertIn("../_shared/agents/repo-cartographer.md", planning)
        self.assertIn("Não usar em projeto novo ou pequeno", planning)
        self.assertIn("legado relevante", planning)
        self.assertIn("hash-do-HEAD", planning)
        self.assertIn("digest-do-escopo", planning)
        self.assertIn("`HEAD` diferente invalida o cache", planning)
        contract = read(self.CONTRACTS["repo-cartographer"])
        self.assertIn("Somente leitura", contract)
        self.assertIn("Não usar em projeto novo ou pequeno", contract)
        self.assertIn("hash do `HEAD`", contract)
        self.assertIn("digest-do-escopo", contract)
        self.assertIn("propor refatoração", contract)

    def test_reviewer_cadence_matches_execution_modes(self) -> None:
        executor = read(SKILLS["executar-plano"])
        self.assertIn("../_shared/agents/implementation-worker.md", executor)
        self.assertIn("../_shared/agents/plan-reviewer.md", executor)
        self.assertIn("nunca por microtarefa", executor)
        contract = read(self.CONTRACTS["plan-reviewer"])
        self.assertIn("`grouped`: uma revisão no gate do plano", contract)
        self.assertIn("`slice`: uma revisão por slice", contract)
        self.assertIn("`strict`: revisão independente por tarefa", contract)
        self.assertIn("caminho do arquivo de saída da revisão", contract)
        self.assertIn("contagem por severidade", contract)
        self.assertIn("o caminho do arquivo de saída da revisão", executor)
        self.assertIn("caminho do arquivo de saída do parecer", executor)
        self.assertIn("menor diff correto", read(self.CONTRACTS["implementation-worker"]))
        for name in self.NAMES:
            self.assertIn("Retorno ao orquestrador", read(self.CONTRACTS[name]))
        for risk, review in (("low", "plan_gate"), ("medium", "per_slice"), ("high", "per_task")):
            with self.subTest(risk=risk):
                policy = cli_json("policy", "--profile", "standard", "--risk", risk)
                self.assertEqual(policy["review"], review)

    def test_security_reviewer_only_for_high_risk_sensitive_domains(self) -> None:
        executor = read(SKILLS["executar-plano"])
        self.assertIn("../_shared/agents/security-reviewer.md", executor)
        self.assertIn("risco alto ou crítico", executor)
        self.assertIn("Não executá-la em tarefa comum", executor)
        contract = read(self.CONTRACTS["security-reviewer"])
        self.assertIn("risco alto ou crítico", contract)
        self.assertIn("Não roda em tarefa comum", contract)
        for domain in ("autenticação", "pagamentos", "webhooks", "RLS", "segredos"):
            self.assertIn(domain, contract)
        self.assertIn("somente leitura", contract)
        self.assertIn("fix loop existente", contract)

    def test_homologation_has_self_contained_real_ui_gate(self) -> None:
        homologation = read(SKILLS["homologar-sistema"])
        for expected in (
            "abrir e operar o release candidate",
            "não substitui a execução real",
            "todos os fluxos críticos",
            "todas as ações primárias",
            "Varredura visual obrigatória",
            "console e rede",
            "não há lacuna manual",
        ):
            self.assertIn(expected, homologation)
        self.assertNotIn("aplicar o gate de acabamento do contrato", homologation)

    def test_no_global_install_and_no_extra_public_skill(self) -> None:
        expected = {*SKILL_NAMES, "_shared"}
        actual = {
            child.name
            for child in (ROOT / "skills").iterdir()
            if child.is_dir()
        }
        self.assertEqual(actual, expected)
        self.assertFalse((ROOT / "skills/agency-agents").exists())
        for path in self.CONTRACTS.values():
            content = read(path)
            self.assertNotIn("~/.claude", content)
            self.assertNotIn("~/.codex", content)
        notices = read(ROOT / "THIRD_PARTY_NOTICES.md")
        self.assertIn("Agency Agents", notices)
        self.assertIn("MIT License", notices)


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
        self.assertIn("limites e a recomendação retornados por `planning-audit`", contract)
        self.assertIn("fonte executável única no CLI", contract)
        self.assertIn("nunca reduzir escopo automaticamente", contract)
        self.assertIn("Research mode: repo_only", research)
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
        self.assertIn("repositório Git limpo", contract)
        self.assertIn("--completion-proof", contract)
        self.assertIn("Nunca editar conteúdo livre de `AGENTS.md`", contract)

    def test_homologation_and_manual_contracts_are_explicit(self) -> None:
        homologation = read(SKILLS["homologar-sistema"])
        self.assertIn("## 2. Baseline automatizada", homologation)
        self.assertIn("## 4. Execução real obrigatória", homologation)
        self.assertIn("## 5. Varredura visual obrigatória", homologation)
        self.assertIn("manual_pdf: none", homologation)
        self.assertIn("manual_pdf: quick_start", homologation)
        self.assertIn("manual_pdf: full", homologation)
        self.assertNotIn("Executar apenas lacunas", homologation)
        self.assertNotIn("Não repetir manualmente", homologation)

    def test_adaptive_test_layers_are_distributed_without_per_task_campaigns(self) -> None:
        gates = read(ROOT / "skills/_shared/ADAPTIVE_GATES.md")
        contract = read(ROOT / "skills/_shared/METHOD_CONTRACT.md")
        planning = read(SKILLS["sdd-planning"])
        executor = read(SKILLS["executar-plano"])
        bugfix = read(SKILLS["corrigir-bug"])
        homologation = read(SKILLS["homologar-sistema"])
        for expected in (
            "Regressão é uma estratégia transversal",
            "não são tarefas independentes",
            "score global de mutação",
            "mutante sobrevivente",
        ):
            self.assertIn(expected, contract)
        for expected in (
            "`fast`: unitários",
            "`plan`: suítes afetadas",
            "`release`: suíte unitária completa",
            "mutation",
        ):
            self.assertIn(expected, gates)
        self.assertIn("não criar tarefa por camada de teste", planning)
        self.assertIn("não executar E2E completo ou mutação por unidade", executor)
        self.assertIn("menor nível capaz de reproduzir", bugfix)
        self.assertIn("não iniciar uma nova campanha unitária", homologation)

    def test_architecture_and_status_skills_exist_in_readme(self) -> None:
        readme = read(ROOT / "README.md")
        self.assertIn("/auditar-arquitetura", readme)
        self.assertIn("/status-projeto", readme)

    def test_skill_activation_is_explicit_or_scoped_to_method_v2(self) -> None:
        for name, path in SKILLS.items():
            with self.subTest(skill=name):
                metadata = frontmatter(read(path))
                description = metadata["description"]
                if name == "executar-direto":
                    self.assertEqual(
                        description,
                        "Use quando o usuário solicitar a implementação estruturada de um projeto pequeno ou de uma entrega coesa sem planejamento SDD completo.",
                    )
                    self.assertEqual(metadata["disable-model-invocation"], "true")
                else:
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
