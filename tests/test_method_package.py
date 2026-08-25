"""Cenários comportamentais e integridade do Bianchini Method."""

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
    "design-projeto",
    "sdd-planning",
    "executar-plano",
    "executar-direto",
    "auditar-arquitetura",
    "status-projeto",
    "corrigir-bug",
    "migrar-bianchini",
    "homologar-sistema",
    "update-bm",
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
                if name in {"executar-direto", "migrar-bianchini", "update-bm"}:
                    agent = read(path.parent / "agents/openai.yaml")
                    self.assertIn("allow_implicit_invocation: false", agent)

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
        scripts = ROOT / "skills" / "_shared" / "scripts"
        content = "\n".join(read(path) for path in sorted(scripts.glob("bm*.py")))
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
            "StateValidationScenarios",
            "SnapshotScenarios",
            "PlanningQualityScenarios",
            "PlanningStabilityScenarios",
            "ContextEfficiencyScenarios",
            "SelfUpdateScenarios",
            "AdaptivePolicyScenarios",
            "BehavioralProjectScenarios",
            "AgentContractScenarios",
            "SkillBehaviorContracts",
            "CodexOverlayPackageTests",
            "ReviewGuardScenarios",
            "CodexInstallerScenarios",
        ):
            self.assertIn(f'"{class_name}"', runner)
        self.assertIn("scripts/run_test_shards.py", read(ROOT / "README.md"))



class StateValidationScenarios(unittest.TestCase):
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


class PlanningStabilityScenarios(unittest.TestCase):
    def make_project(
        self,
        root: Path,
        *,
        design: bool = False,
        initialize_git: bool = False,
    ) -> Path:
        repository_revision = init_repo(root) if initialize_git else "new-project"
        change_root = root / "docs/bianchini/changes/v1"
        current_specs = root / "docs/bianchini/current/specs"
        scope = change_root / "inputs/APPROVED_SCOPE.md"
        research = change_root / "STACK_RESEARCH.md"
        readiness = change_root / "READINESS.md"
        user_actions = change_root / "USER_ACTIONS.md"
        spec = change_root / "specs/system-change.md"
        delta = change_root / "spec-deltas/system.md"
        review = change_root / "PLANNING_REVIEW.md"
        plan = change_root / "plans/P01-system.md"
        state_path = root / "docs/living/PROJECT_STATE.md"
        for path in (
            scope,
            research,
            readiness,
            user_actions,
            spec,
            delta,
            review,
            plan,
            state_path,
        ):
            path.parent.mkdir(parents=True, exist_ok=True)
        scope.write_text(
            "# Escopo aprovado\n\nCriar painel web com autenticação e cadastro.\n",
            encoding="utf-8",
        )
        research.write_text(
            "# Stack Research\n\n"
            "Research mode: repo_only\n"
            "Motivo: stack local estabelecida e sem integração externa nova.\n\n"
            "## Stack detectada\n\n- Python e HTML.\n\n"
            "## Inventário local\n\n"
            "- Manifests: nenhum.\n"
            "- Lockfiles: nenhum.\n"
            "- CI: unittest.\n"
            "- Testes: unittest.\n"
            "- Padrões locais: biblioteca padrão.\n\n"
            "## Decisões aplicadas\n\n- D-001 mantém o menor fluxo robusto.\n\n"
            "## Riscos e lacunas\n\n- P-001 cobre recuperação da sessão.\n- S-001 validou a persistência local.\n",
            encoding="utf-8",
        )
        spec.write_text(
            "# Change Spec\n\n"
            "## Contratos\n\n"
            "D-001 define autenticação por sessão. A-001 foi limitada por evidência local.\n"
            "P-001 exige recuperação após reinício. U-001 deve existir antes do gate P01.\n"
            "SD-001 substitui o contrato atual do domínio."
            + (" DS-001 fixa o app shell e o fluxo principal.\n" if design else "\n"),
            encoding="utf-8",
        )
        delta.write_text(
            "# Sistema atual após v1\n\n"
            "SD-001. D-001: sessão autenticada, recuperação P-001 e ação U-001.\n",
            encoding="utf-8",
        )
        plan.write_text(
            "---\nplan_id: P01\nmethod_version: 2\nrisk: medium\n"
            "execution: slice\nreview: per_slice\ndepends_on: []\n---\n\n"
            "# P01 Sistema\n\n"
            "### Slice 1 — Entregar autenticação e painel\n\n"
            "**Execution:** slice\n"
            "**Review:** per_slice\n"
            "**Change:** state-machine\n"
            "**Readiness refs:** D-001, A-001, P-001, U-001, SD-001"
            + (", DS-001\n" if design else "\n")
            + "**Test seams:** sessão pública e navegação\n"
            "**Spec refs:** specs/system-change.md#contratos\n"
            "**Files:** src/auth.py, web/index.html, tests/test_auth.py\n"
            "**Contract:** login cria sessão; reinício preserva estado válido\n"
            "**Verification:** `python3 -m unittest tests.test_auth` retorna 0\n"
            "**Done when:** jornada crítica e recuperação passam\n",
            encoding="utf-8",
        )
        user_actions.write_text(
            "# User Actions\n\n"
            "## U-001\n\n"
            "- Ação: fornecer credencial de sandbox.\n"
            "- Necessário até: P01.\n"
            "- Pode continuar sem: sim, usando fixture local.\n"
            "- Evidência: segredo presente no ambiente de homologação.\n",
            encoding="utf-8",
        )
        design_manifest = None
        design_files: list[str] = []
        if design:
            design_root = root / "docs/design/v1"
            prototype = design_root / "prototype/index.html"
            contract = design_root / "DESIGN_CONTRACT.md"
            tokens = design_root / "tokens.css"
            screenshot = design_root / "screenshots/desktop.png"
            manifest = design_root / "DESIGN_MANIFEST.json"
            for path in (prototype, contract, tokens, screenshot, manifest):
                path.parent.mkdir(parents=True, exist_ok=True)
            prototype.write_text("<!doctype html><title>Prototype</title><main>App shell</main>\n", encoding="utf-8")
            contract.write_text("# Design Contract\n\nDS-001 app shell e fluxo principal.\n", encoding="utf-8")
            tokens.write_text(":root { --space-1: 4px; }\n", encoding="utf-8")
            screenshot.write_bytes(b"\x89PNG\r\n\x1a\nBM-test-evidence")
            files = [
                "docs/design/v1/DESIGN_CONTRACT.md",
                "docs/design/v1/prototype/index.html",
                "docs/design/v1/tokens.css",
                "docs/design/v1/screenshots/desktop.png",
            ]
            manifest.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "status": "draft",
                        "source": "generated",
                        "scope_source": "docs/bianchini/changes/v1/inputs/APPROVED_SCOPE.md",
                        "scope_digest": None,
                        "design_digest": None,
                        "contract": files[0],
                        "prototype": files[1],
                        "tokens": files[2],
                        "screenshots": [files[3]],
                        "surfaces": ["app-shell", "primary-flow"],
                        "breakpoints": ["desktop", "mobile"],
                        "files": files,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            sealed = cli_json(
                "design-audit",
                "seal",
                "--root",
                str(root),
                "--scope",
                str(scope),
                "--manifest",
                str(manifest),
            )
            value = json.loads(read(manifest))
            value["status"] = "approved"
            manifest.write_text(json.dumps(value, indent=2), encoding="utf-8")
            verified = cli_json(
                "design-audit",
                "verify",
                "--root",
                str(root),
                "--scope",
                str(scope),
                "--manifest",
                str(manifest),
            )
            self.assertEqual(sealed["design_digest"], verified["design_digest"])
            design_manifest = "docs/design/v1/DESIGN_MANIFEST.json"
            design_files = [design_manifest, *files]

        readiness_data = {
            "schema_version": 1,
            "status": "ready",
            "scope_digest": file_sha256(scope),
            "repository_revision": repository_revision,
            "design_required": design,
            "impact_map": {
                "applications": ["web"],
                "modules": ["auth"],
                "contracts": ["session"],
                "data": ["users"],
                "platforms": ["browser"],
            },
            "decisions": [
                {
                    "id": "D-001",
                    "statement": "Usar sessão autenticada.",
                    "evidence": "APPROVED_SCOPE.md",
                    "destinations": [
                        "docs/bianchini/changes/v1/specs/system-change.md",
                        "docs/bianchini/changes/v1/plans/P01-system.md",
                    ],
                }
            ],
            "assumptions": [
                {
                    "id": "A-001",
                    "statement": "Sessão local atende o ciclo.",
                    "impact": "high",
                    "status": "bounded",
                    "evidence": "STACK_RESEARCH.md#Inventário local",
                    "fallback": "Bloquear publicação externa.",
                    "destinations": [
                        "docs/bianchini/changes/v1/specs/system-change.md",
                        "docs/bianchini/changes/v1/plans/P01-system.md",
                    ],
                }
            ],
            "pitfalls": [
                {
                    "id": "P-001",
                    "statement": "Sessão inválida após reinício.",
                    "impact": "high",
                    "prevention": "Persistir estado mínimo.",
                    "recovery": "Invalidar e voltar ao login.",
                    "verification": "Teste de reinício controlado.",
                    "destinations": [
                        "docs/bianchini/changes/v1/specs/system-change.md",
                        "docs/bianchini/changes/v1/plans/P01-system.md",
                    ],
                }
            ],
            "user_actions": [
                {
                    "id": "U-001",
                    "action": "Fornecer credencial de sandbox.",
                    "needed_by": "P01",
                    "can_continue_without": True,
                    "fallback": "Fixture local.",
                    "evidence_required": "Credencial presente no ambiente.",
                    "destinations": [
                        "docs/bianchini/changes/v1/USER_ACTIONS.md",
                        "docs/bianchini/changes/v1/plans/P01-system.md",
                    ],
                }
            ],
            "spikes": [
                {
                    "id": "S-001",
                    "question": "Persistência local funciona no runner?",
                    "status": "passed",
                    "evidence": "STACK_RESEARCH.md#Inventário local",
                    "decision": "Usar fixture determinística.",
                    "destinations": ["docs/bianchini/changes/v1/STACK_RESEARCH.md"],
                }
            ],
            "design_surfaces": (
                [
                    {
                        "id": "DS-001",
                        "surface": "App shell e fluxo principal.",
                        "manifest_ref": design_manifest,
                        "required": True,
                        "destinations": [
                            "docs/design/v1/DESIGN_CONTRACT.md",
                            "docs/bianchini/changes/v1/specs/system-change.md",
                            "docs/bianchini/changes/v1/plans/P01-system.md",
                        ],
                    }
                ]
                if design
                else []
            ),
            "spec_deltas": [
                {
                    "id": "SD-001",
                    "domain": "system",
                    "source": "docs/bianchini/changes/v1/spec-deltas/system.md",
                    "target": "docs/bianchini/current/specs/system.md",
                    "destinations": [
                        "docs/bianchini/changes/v1/specs/system-change.md",
                        "docs/bianchini/changes/v1/plans/P01-system.md",
                        "docs/bianchini/changes/v1/spec-deltas/system.md",
                    ],
                }
            ],
        }
        readiness.write_text(
            "# Planning Readiness\n\n```json\n"
            + json.dumps(readiness_data, ensure_ascii=False, indent=2)
            + "\n```\n",
            encoding="utf-8",
        )
        review.write_text(
            "# Planning Review\n\n```json\n"
            + json.dumps({"verdict": "passed", "findings": []}, indent=2)
            + "\n```\n",
            encoding="utf-8",
        )
        state = json.loads(read(FIXTURES / "project-state-v2.json"))
        state["planning_status"] = "in_progress"
        state["assurance_profile"] = "standard"
        state["scope"] = {
            "status": "approved",
            "source": "docs/bianchini/changes/v1/inputs/APPROVED_SCOPE.md",
            "approved_at": "2026-08-17T12:00:00Z",
        }
        state["planning"] = {
            "quality_version": 2,
            "research_mode": "repo_only",
            "research": "docs/bianchini/changes/v1/STACK_RESEARCH.md",
            "readiness": "docs/bianchini/changes/v1/READINESS.md",
            "user_actions": "docs/bianchini/changes/v1/USER_ACTIONS.md",
            "spec": "docs/bianchini/changes/v1/specs/system-change.md",
            "review": "docs/bianchini/changes/v1/PLANNING_REVIEW.md",
            "checker": {
                "status": "pending",
                "rounds": 0,
                "history_path": "artifacts/bianchini/v1/planning/checker.jsonl",
                "package_digest": None,
                "report_digest": None,
            },
            "design_manifest": design_manifest,
            "change_root": "docs/bianchini/changes/v1",
            "current_specs": "docs/bianchini/current/specs",
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
        state["approval"]["package"]["manifest_path"] = (
            "artifacts/bianchini/v1/approval/manifest.sha256"
        )
        state["plans"] = [
            {
                "id": "P01",
                "path": "docs/bianchini/changes/v1/plans/P01-system.md",
                "status": "planned",
                "risk": "medium",
                "execution": "slice",
                "review": "per_slice",
                "test_seams": ["session", "navigation"],
                "depends_on": [],
                "ledger": "artifacts/bianchini/v1/ledgers/P01.md",
                "gates": ["test", "e2e"],
            }
        ]
        package_files = [
            state["scope"]["source"],
            state["planning"]["research"],
            state["planning"]["readiness"],
            state["planning"]["user_actions"],
            state["planning"]["spec"],
            "docs/bianchini/changes/v1/spec-deltas/system.md",
            state["planning"]["review"],
            state["plans"][0]["path"],
            *design_files,
        ]
        state["approval"]["package"]["files"] = package_files
        state["verification"] = {
            "fast": {
                "commands": ["python3 -m unittest tests.test_auth"],
                "status": "pending",
            },
            "plan": {
                "commands": ["python3 -m unittest discover -s tests"],
                "status": "pending",
            },
            "release": {
                "commands": ["python3 -m unittest discover -s tests"],
                "status": "pending",
            },
        }
        state["release"].update(
            {
                "status": "pending",
                "platforms": ["web"],
                "profiles": ["admin"],
                "candidate": None,
                "homologation": "pending",
                "final_review": "pending",
                "delivery": "pending",
            }
        )
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        return state_path

    def pass_checker(self, state_path: Path, root: Path) -> dict[str, object]:
        result = cli_json(
            "planning-check",
            "record",
            "--state",
            str(state_path),
            "--root",
            str(root),
            "--report",
            str(root / json.loads(read(state_path))["planning"]["review"]),
        )
        return result

    def test_design_can_be_sealed_and_verified_before_project_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = self.make_project(root, design=True)
            manifest = root / json.loads(read(state))["planning"]["design_manifest"]
            verified = cli_json(
                "design-audit",
                "verify",
                "--root",
                str(root),
                "--scope",
                str(root / "docs/bianchini/changes/v1/inputs/APPROVED_SCOPE.md"),
                "--manifest",
                str(manifest),
            )
            self.assertTrue(verified["valid"])
            self.assertEqual(verified["status"], "approved")

    def test_design_requires_observable_screenshot_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = self.make_project(root, design=True)
            manifest_path = root / json.loads(read(state))["planning"]["design_manifest"]
            manifest = json.loads(read(manifest_path))
            manifest["status"] = "draft"
            manifest["screenshots"] = []
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            result = cli(
                "design-audit",
                "seal",
                "--root",
                str(root),
                "--scope",
                str(root / "docs/bianchini/changes/v1/inputs/APPROVED_SCOPE.md"),
                "--manifest",
                str(manifest_path),
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("screenshots", result.stderr)

    def test_design_rejects_empty_contract_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = self.make_project(root, design=True)
            manifest_path = root / json.loads(read(state))["planning"]["design_manifest"]
            manifest = json.loads(read(manifest_path))
            (root / manifest["contract"]).write_bytes(b"")
            result = cli(
                "design-audit",
                "verify",
                "--root",
                str(root),
                "--scope",
                str(root / "docs/bianchini/changes/v1/inputs/APPROVED_SCOPE.md"),
                "--manifest",
                str(manifest_path),
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("arquivo vazio", result.stderr)

    def test_design_rejects_manifest_metadata_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = self.make_project(root, design=True)
            manifest_path = root / json.loads(read(state))["planning"]["design_manifest"]
            manifest = json.loads(read(manifest_path))
            manifest["surfaces"].append("unauthorized-surface")
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
            result = cli(
                "design-audit",
                "verify",
                "--root",
                str(root),
                "--scope",
                str(root / "docs/bianchini/changes/v1/inputs/APPROVED_SCOPE.md"),
                "--manifest",
                str(manifest_path),
            )
            self.assertEqual(result.returncode, 3)
            self.assertIn("design_digest", result.stderr)

    def test_design_rejects_stale_scope_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = self.make_project(root, design=True)
            scope = root / json.loads(read(state))["scope"]["source"]
            scope.write_text(read(scope) + "mudança material\n", encoding="utf-8")
            result = cli(
                "design-audit",
                "verify",
                "--root",
                str(root),
                "--scope",
                str(scope),
                "--manifest",
                str(root / json.loads(read(state))["planning"]["design_manifest"]),
            )
            self.assertEqual(result.returncode, 3)
            self.assertIn("scope_digest", result.stderr)

    def test_quality_v2_requires_readiness_coverage_and_checker(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_project(root)
            pending = cli(
                "planning-audit", str(state_path), "--root", str(root), "--strict"
            )
            self.assertEqual(pending.returncode, 2)
            self.assertIn("checker", pending.stderr)
            passed = self.pass_checker(state_path, root)
            self.assertEqual(passed["status"], "passed")
            state = json.loads(read(state_path))
            state["planning_status"] = "pending_approval"
            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
            audited = cli_json(
                "planning-audit", str(state_path), "--root", str(root), "--strict"
            )
            self.assertEqual(audited["quality_contract"], "planning-quality-v2")
            self.assertEqual(audited["readiness"]["coverage_gaps"], [])

    def test_readiness_is_invalidated_when_repository_head_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            state_path = self.make_project(root, initialize_git=True)
            (root / "app.txt").write_text("changed after readiness\n", encoding="utf-8")
            git(root, "add", "app.txt")
            git(root, "commit", "-m", "change repository after readiness")
            result = cli(
                "planning-audit", str(state_path), "--root", str(root), "--strict"
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("repository_revision", result.stderr)

    def test_high_impact_assumption_requires_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_project(root)
            state = json.loads(read(state_path))
            readiness_path = root / state["planning"]["readiness"]
            fenced = re.search(r"```json\s*(.*?)\s*```", read(readiness_path), re.S)
            data = json.loads(fenced.group(1))
            data["assumptions"][0]["evidence"] = ""
            readiness_path.write_text(
                "# Planning Readiness\n\n```json\n"
                + json.dumps(data, indent=2)
                + "\n```\n",
                encoding="utf-8",
            )
            result = cli(
                "planning-audit", str(state_path), "--root", str(root), "--strict"
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("A-001", result.stderr)
            self.assertIn("evidência", result.stderr)

    def test_planning_checker_allows_one_correction_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_project(root)
            state = json.loads(read(state_path))
            review = root / state["planning"]["review"]
            review.write_text(
                "# Planning Review\n\n```json\n"
                + json.dumps(
                    {
                        "verdict": "changes_requested",
                        "findings": [
                            {
                                "id": "C-001",
                                "severity": "important",
                                "summary": "Clarificar recuperação.",
                                "evidence": "P-001",
                            }
                        ],
                    },
                    indent=2,
                )
                + "\n```\n",
                encoding="utf-8",
            )
            first = self.pass_checker(state_path, root)
            self.assertEqual(first["round"], 1)
            self.assertEqual(first["status"], "changes_requested")
            spec = root / state["planning"]["spec"]
            spec.write_text(read(spec) + "\nCorreção única do checker.\n", encoding="utf-8")
            review.write_text(
                "# Planning Review\n\n```json\n"
                + json.dumps({"verdict": "passed", "findings": []}, indent=2)
                + "\n```\n",
                encoding="utf-8",
            )
            second = self.pass_checker(state_path, root)
            self.assertEqual(second["round"], 2)
            self.assertEqual(second["status"], "passed")
            third = cli(
                "planning-check",
                "record",
                "--state",
                str(state_path),
                "--root",
                str(root),
                "--report",
                str(review),
            )
            self.assertEqual(third.returncode, 3)
            self.assertIn("máximo de duas revisões", third.stderr)

    def test_checker_allows_one_factual_amendment_after_first_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_project(root)
            first = self.pass_checker(state_path, root)
            self.assertEqual(first["status"], "passed")
            state = json.loads(read(state_path))
            spec = root / state["planning"]["spec"]
            spec.write_text(read(spec) + "\nAjuste factual final.\n", encoding="utf-8")
            review = root / state["planning"]["review"]
            review.write_text(
                "```json\n"
                + json.dumps({
                    "verdict": "passed",
                    "findings": [],
                    "review_note": "pacote corrigido revisado novamente",
                })
                + "\n```\n",
                encoding="utf-8",
            )
            second = self.pass_checker(state_path, root)
            self.assertEqual(second["round"], 2)
            self.assertEqual(second["status"], "passed")
            third = cli(
                "planning-check",
                "record",
                "--state",
                str(state_path),
                "--root",
                str(root),
                "--report",
                str(root / state["planning"]["review"]),
            )
            self.assertEqual(third.returncode, 3)
            self.assertIn("máximo de duas revisões", third.stderr)

    def test_checker_uses_canonical_review_and_rejects_empty_correction_loop(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_project(root)
            alternative = root / "alternative-review.md"
            alternative.write_text(
                "```json\n" + json.dumps({"verdict": "passed", "findings": []}) + "\n```\n",
                encoding="utf-8",
            )
            wrong_path = cli(
                "planning-check",
                "record",
                "--state",
                str(state_path),
                "--root",
                str(root),
                "--report",
                str(alternative),
            )
            self.assertEqual(wrong_path.returncode, 3)
            self.assertIn("planning.review", wrong_path.stderr)

            state = json.loads(read(state_path))
            review = root / state["planning"]["review"]
            review.write_text(
                "```json\n"
                + json.dumps(
                    {
                        "verdict": "changes_requested",
                        "findings": [
                            {
                                "id": "N-001",
                                "severity": "note",
                                "summary": "Preferência sem impacto.",
                                "evidence": "estilo",
                            }
                        ],
                    }
                )
                + "\n```\n",
                encoding="utf-8",
            )
            empty_loop = cli(
                "planning-check",
                "record",
                "--state",
                str(state_path),
                "--root",
                str(root),
                "--report",
                str(review),
            )
            self.assertEqual(empty_loop.returncode, 2)
            self.assertIn("critical/important", empty_loop.stderr)

    def test_checker_binds_the_approved_review_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_project(root)
            self.pass_checker(state_path, root)
            state = json.loads(read(state_path))
            review = root / state["planning"]["review"]
            review.write_text(
                "```json\n"
                + json.dumps({
                    "verdict": "passed",
                    "findings": [{
                        "id": "N-999",
                        "severity": "note",
                        "summary": "alteração posterior",
                        "evidence": "sem revisão",
                    }],
                })
                + "\n```\n",
                encoding="utf-8",
            )
            result = cli(
                "planning-audit", str(state_path), "--root", str(root), "--strict"
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("report_digest", result.stderr)

    def test_change_policy_prevents_redesign_for_internal_adjustments(self) -> None:
        internal = cli_json("change-policy")
        bounded = cli_json("change-policy", "--plan-command")
        material = cli_json("change-policy", "--public-contract-change")
        self.assertEqual(internal["classification"], "implementation_detail")
        self.assertEqual(bounded["classification"], "bounded_amendment")
        self.assertEqual(material["classification"], "material_change")
        self.assertFalse(internal["reapproval_required"])
        self.assertFalse(bounded["plan_files_mutable"])
        self.assertTrue(material["reapproval_required"])
        self.assertTrue(material["plan_invalidating"])
        self.assertTrue(material["redesign_allowed"])
        cost = cli_json("change-policy", "--new-cost")
        self.assertEqual(cost["classification"], "material_change")
        self.assertTrue(cost["reapproval_required"])
        self.assertFalse(cost["plan_invalidating"])
        self.assertFalse(cost["redesign_allowed"])

    def test_quality_v2_requires_change_artifacts_inside_change_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_project(root)
            state = json.loads(read(state_path))
            original = root / state["plans"][0]["path"]
            external = root / "docs/plans/P01-system.md"
            external.parent.mkdir(parents=True, exist_ok=True)
            external.write_bytes(original.read_bytes())
            state["approval"]["package"]["files"].remove(state["plans"][0]["path"] )
            state["plans"][0]["path"] = "docs/plans/P01-system.md"
            state["approval"]["package"]["files"].append(state["plans"][0]["path"] )
            state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
            result = cli(
                "planning-audit", str(state_path), "--root", str(root), "--strict"
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("planning.change_root", result.stderr)

    def test_readiness_rejects_duplicate_current_spec_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_project(root)
            state = json.loads(read(state_path))
            readiness_path = root / state["planning"]["readiness"]
            match = re.search(r"```json\s*(.*?)\s*```", read(readiness_path), re.S)
            readiness = json.loads(match.group(1))
            duplicate = dict(readiness["spec_deltas"][0])
            duplicate["id"] = "SD-002"
            duplicate["destinations"] = list(duplicate["destinations"])
            for destination in duplicate["destinations"]:
                path = root / destination
                path.write_text(read(path) + "\nSD-002\n", encoding="utf-8")
            readiness["spec_deltas"].append(duplicate)
            readiness_path.write_text(
                "# Planning Readiness\n\n```json\n"
                + json.dumps(readiness, indent=2)
                + "\n```\n",
                encoding="utf-8",
            )
            result = cli(
                "planning-audit", str(state_path), "--root", str(root), "--strict"
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("target duplicado", result.stderr)



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



class BehavioralProjectScenarios(unittest.TestCase):

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

    def test_direct_mode_allows_adaptive_subagents_without_changing_route(self) -> None:
        direct = read(SKILLS["executar-direto"])
        self.assertIn("Quick normal e quick protegido podem usar subagentes", direct)
        self.assertIn("frentes independentes", direct)
        self.assertIn("Não fixe nome, modelo, reasoning effort", direct)
        self.assertIn("Sem subagentes, cumpra a mesma responsabilidade inline", direct)
        self.assertIn("Não criar subagente por arquivo, camada de teste ou gate mecânico", direct)
        self.assertIn("nunca aciona `/sdd-planning`", direct)
        self.assertNotIn("encaminhe para `/sdd-planning`", direct)
        self.assertNotIn("`7–10`: `/sdd-planning`", direct)
        self.assertNotIn("zero subagentes", direct)

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
        self.assertIn("nunca revise por microtarefa", executor)
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
        self.assertIn("Não existe fallback para editar na branch principal", executor)
        self.assertIn("entrega rejeitável ou verificável", planning)
        self.assertNotIn("4–10 tarefas", planning)

    def test_planning_commit_and_versioned_workspace_are_mandatory(self) -> None:
        executor = read(SKILLS["executar-plano"])
        planning = read(SKILLS["sdd-planning"])
        contract = read(ROOT / "skills/_shared/METHOD_CONTRACT.md")
        self.assertIn("commit local atômico", planning)
        self.assertIn("git status --porcelain", executor)
        self.assertIn("--change C001 --plan P01", executor)
        self.assertIn("bm/c001-p01", executor)
        self.assertIn("COHERENCE.md` em `approved`", contract)
        self.assertIn("artefatos do pacote idênticos ao `HEAD`", contract)

    def test_planning_research_and_simplification_are_enforced(self) -> None:
        planning = read(SKILLS["sdd-planning"])
        contract = read(ROOT / "skills/_shared/METHOD_CONTRACT.md")
        research = read(ROOT / "skills/sdd-planning/references/stack-research.md")
        for expected in (
            "RESEARCH.md",
            "fontes primárias",
            "Preserve 100%",
            "model validate",
            "coherence check",
            "Um plano não pode parecer correto sozinho",
        ):
            self.assertIn(expected, planning)
        self.assertIn("ProjectModel` é uma representação tipada derivada", contract)
        self.assertIn("pacote inteiro é validado", contract)
        self.assertIn("aprovação do digest global", contract)
        self.assertIn("Research mode: repo_only", research)
        self.assertIn("Acessado em: YYYY-MM-DD", research)
        self.assertIn("documentação oficial", research)

    def test_planning_is_foreign_and_bianchini_docs_are_versioned(self) -> None:
        planning = read(SKILLS["sdd-planning"])
        contract = read(ROOT / "skills/_shared/METHOD_CONTRACT.md")
        migration = read(SKILLS["migrar-bianchini"])
        self.assertIn("Nunca ler `.planning/`", planning)
        self.assertIn("`.planning/` é namespace estrangeiro", contract)
        self.assertIn("`.planning/` permanece byte a byte intocado", contract)
        self.assertIn("checksums", migration)
        self.assertIn(".bianchini/archive/import-AAAA-MM-DD", migration)

    def test_completed_previous_execution_uses_explicit_migration(self) -> None:
        planning = read(SKILLS["sdd-planning"])
        executor = read(SKILLS["executar-plano"])
        contract = read(ROOT / "skills/_shared/METHOD_CONTRACT.md")
        migration = read(SKILLS["migrar-bianchini"])
        self.assertIn("/migrar-bianchini", executor)
        self.assertIn("/migrar-bianchini", planning)
        self.assertIn("Não existe adaptador permanente", contract)
        self.assertIn("projeto `idle`/concluído e Git limpo", contract)
        self.assertIn("migrate check", migration)
        self.assertIn("migrate apply", migration)

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
            "Regressão é transversal",
            "Não criar tarefa ou agente por camada de teste",
            "mutation score global",
            "mutação seletiva",
        ):
            self.assertIn(expected, contract)
        for expected in (
            "`fast`: unitários",
            "`plan`: suítes afetadas",
            "`release`: suíte unitária completa",
            "mutation",
        ):
            self.assertIn(expected, gates)
        self.assertIn("Não criar tarefa por arquivo, camada de teste", planning)
        self.assertIn("Não execute E2E completo ou mutação por microtarefa", executor)
        self.assertIn("menor interface pública", bugfix)
        self.assertIn("não iniciar uma nova campanha unitária", homologation)

    def test_architecture_and_status_skills_exist_in_readme(self) -> None:
        readme = read(ROOT / "README.md")
        self.assertIn("/auditar-arquitetura", readme)
        self.assertIn("/status-projeto", readme)

    def test_skill_activation_uses_current_method_or_explicit_policy(self) -> None:
        for name, path in SKILLS.items():
            with self.subTest(skill=name):
                metadata = frontmatter(read(path))
                description = metadata["description"]
                self.assertTrue(description.startswith("Use "))
                self.assertNotIn("method_version 2", description)
                self.assertNotRegex(description, r"\b[Vv][234]\b")
                if name in {"executar-direto", "migrar-bianchini", "update-bm"}:
                    agent = read(path.parent / "agents/openai.yaml")
                    self.assertIn("allow_implicit_invocation: false", agent)
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
class ContextEfficiencyScenarios(unittest.TestCase):
    def make_v2_project(self, root: Path, *, initialize_git: bool = False) -> Path:
        builder = PlanningStabilityScenarios(methodName="runTest")
        return builder.make_project(root, initialize_git=initialize_git)

    def test_quality_v2_requires_change_and_readiness_refs(self) -> None:
        cases = (
            ("**Change:** state-machine\n", "campo Change ausente"),
            (
                "**Readiness refs:** D-001, A-001, P-001, U-001, SD-001\n",
                "campo Readiness refs ausente",
            ),
        )
        for removed, expected in cases:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                state_path = self.make_v2_project(root)
                state = json.loads(read(state_path))
                plan = root / state["plans"][0]["path"]
                plan.write_text(read(plan).replace(removed, ""), encoding="utf-8")
                result = cli(
                    "planning-check",
                    "record",
                    "--state",
                    str(state_path),
                    "--root",
                    str(root),
                    "--report",
                    str(root / state["planning"]["review"]),
                )
                self.assertEqual(result.returncode, 2)
                self.assertIn(expected, result.stderr)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_v2_project(root)
            state = json.loads(read(state_path))
            plan = root / state["plans"][0]["path"]
            plan.write_text(
                read(plan).replace("**Change:** state-machine", "**Change:** talvez-refatorar"),
                encoding="utf-8",
            )
            result = cli(
                "planning-check",
                "record",
                "--state",
                str(state_path),
                "--root",
                str(root),
                "--report",
                str(root / state["planning"]["review"]),
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("Change inválido", result.stderr)

    def test_readiness_ref_must_exist_and_target_the_plan(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_v2_project(root)
            state = json.loads(read(state_path))
            plan = root / state["plans"][0]["path"]
            plan.write_text(
                read(plan).replace(
                    "D-001, A-001, P-001, U-001, SD-001",
                    "D-001, A-001, P-001, U-001, SD-999",
                ),
                encoding="utf-8",
            )
            result = cli(
                "planning-check",
                "record",
                "--state",
                str(state_path),
                "--root",
                str(root),
                "--report",
                str(root / state["planning"]["review"]),
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("readiness ref inexistente SD-999", result.stderr)

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_v2_project(root)
            state = json.loads(read(state_path))
            readiness_path = root / state["planning"]["readiness"]
            match = re.search(r"```json\s*(.*?)\s*```", read(readiness_path), re.DOTALL)
            self.assertIsNotNone(match)
            readiness = json.loads(match.group(1))
            readiness["decisions"][0]["destinations"] = [state["planning"]["spec"]]
            readiness_path.write_text(
                "# Planning Readiness\n\n```json\n"
                + json.dumps(readiness, ensure_ascii=False, indent=2)
                + "\n```\n",
                encoding="utf-8",
            )
            result = cli(
                "planning-check",
                "record",
                "--state",
                str(state_path),
                "--root",
                str(root),
                "--report",
                str(root / state["planning"]["review"]),
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("D-001 não declara este plano em destinations", result.stderr)

    def test_hydrated_task_brief_contains_bounded_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path = self.make_v2_project(root)
            state = json.loads(read(state_path))
            plan = root / state["plans"][0]["path"]
            ledger = root / state["plans"][0]["ledger"]
            ledger.parent.mkdir(parents=True, exist_ok=True)
            ledger.write_text("linha antiga\ncheckpoint atual\npróxima ação\n", encoding="utf-8")
            output = root / ".superpowers/bianchini/context/P01-S1.md"
            result = cli_json(
                "task-brief",
                "--plan",
                str(plan),
                "--task",
                "1",
                "--state",
                str(state_path),
                "--root",
                str(root),
                "--hydrate-context",
                "--ledger-tail-lines",
                "2",
                "--output",
                str(output),
            )
            text = read(output)
            self.assertTrue(result["hydrated"])
            self.assertRegex(result["context_digest"], r"^[0-9a-f]{64}$")
            self.assertIn("D-001", text)
            self.assertIn("P-001", text)
            self.assertIn("## Contratos", text)
            self.assertIn("### Verification.fast", text)
            self.assertNotIn("linha antiga", text)
            self.assertIn("checkpoint atual", text)
            self.assertIn("próxima ação", text)

    def test_spec_diff_generates_added_modified_and_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base = root / "docs/current/auth.md"
            target = root / "docs/changes/auth.md"
            output = root / "artifacts/auth-diff.md"
            base.parent.mkdir(parents=True)
            target.parent.mkdir(parents=True)
            base.write_text(
                "# Auth\n\n## AUTH-001: Sessão\n\nExpira em 24 horas.\n\n"
                "## AUTH-002: Usuário legado\n\nLogin por nome de usuário.\n",
                encoding="utf-8",
            )
            target.write_text(
                "# Auth\n\n## AUTH-001: Sessão\n\nExpira conforme a organização.\n\n"
                "## AUTH-003: Bloqueio\n\nBloqueia após tentativas inválidas.\n",
                encoding="utf-8",
            )
            result = cli_json(
                "spec-diff",
                "--root",
                str(root),
                "--base",
                str(base),
                "--target",
                str(target),
                "--output",
                str(output),
            )
            self.assertEqual(result["added"], ["AUTH-003"])
            self.assertEqual(result["modified"], ["AUTH-001"])
            self.assertEqual(result["removed"], ["AUTH-002"])
            self.assertRegex(result["base_digest"], r"^[0-9a-f]{64}$")
            text = read(output)
            self.assertIn("## ADDED", text)
            self.assertIn("## MODIFIED", text)
            self.assertIn("## REMOVED", text)
            self.assertIn("spec target completa permanece a fonte de verdade", text)

    def test_spec_diff_rejects_duplicate_requirement_ids(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base = root / "base.md"
            target = root / "target.md"
            output = root / "diff.md"
            base.write_text(
                "## AUTH-001: Um\n\nA.\n\n## AUTH-001: Dois\n\nB.\n",
                encoding="utf-8",
            )
            target.write_text("## AUTH-001: Um\n\nA.\n", encoding="utf-8")
            result = cli(
                "spec-diff",
                "--root",
                str(root),
                "--base",
                str(base),
                "--target",
                str(target),
                "--output",
                str(output),
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("ID duplicado", result.stderr)
            self.assertFalse(output.exists())

    def make_mutation_project(self, root: Path, report: dict[str, object]) -> tuple[Path, str]:
        root.rmdir()
        state_path = self.make_v2_project(root, initialize_git=True)
        report_path = root / "artifacts/mutation/report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        git(root, "add", ".")
        git(root, "commit", "-m", "test: prepare mutation evidence fixture")
        return state_path, git(root, "rev-parse", "HEAD")

    def test_mutation_evidence_accepts_classified_survivor(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state_path, revision = self.make_mutation_project(
                root,
                {
                    "schema_version": 1,
                    "mutants": [
                        {"id": "M1", "status": "killed"},
                        {
                            "id": "M2",
                            "status": "survived",
                            "classification": "equivalent",
                            "justification": "Operadores produzem o mesmo resultado para o domínio aprovado.",
                        },
                    ],
                },
            )
            result = cli_json(
                "mutation-evidence",
                "verify",
                "--state",
                str(state_path),
                "--root",
                str(root),
                "--plan",
                "P01",
                "--risk-seam",
                "session-state",
                "--tool",
                "normalized",
                "--command",
                "python3 mutation_runner.py",
                "--report",
                "artifacts/mutation/report.json",
                "--revision",
                revision,
                "--output",
                "artifacts/bianchini/v1/mutation/P01-session.json",
            )
            self.assertEqual(result["status"], "passed")
            self.assertEqual(result["policy"], "selective")
            self.assertEqual(result["mutants"]["killed"], 1)
            self.assertEqual(result["mutants"]["accepted_survivors"], 1)

    def test_mutation_evidence_blocks_unclassified_or_stale_results(self) -> None:
        scenarios = (
            (
                {
                    "schema_version": 1,
                    "mutants": [{"id": "M1", "status": "survived"}],
                },
                None,
                "M1",
            ),
            (
                {
                    "schema_version": 1,
                    "mutants": [{"id": "M1", "status": "killed"}],
                },
                "0" * 40,
                "revision-mismatch",
            ),
        )
        for report, forced_revision, expected in scenarios:
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                state_path, revision = self.make_mutation_project(root, report)
                output = root / "artifacts/bianchini/v1/mutation/P01-session.json"
                result = cli(
                    "mutation-evidence",
                    "verify",
                    "--state",
                    str(state_path),
                    "--root",
                    str(root),
                    "--plan",
                    "P01",
                    "--risk-seam",
                    "session-state",
                    "--tool",
                    "normalized",
                    "--command",
                    "python3 mutation_runner.py",
                    "--report",
                    "artifacts/mutation/report.json",
                    "--revision",
                    forced_revision or revision,
                    "--output",
                    str(output.relative_to(root)),
                )
                self.assertEqual(result.returncode, 3)
                self.assertIn("mutation evidence bloqueada", result.stderr)
                payload = json.loads(read(output))
                self.assertEqual(payload["status"], "blocked")
                self.assertIn(expected, payload["blocking_mutants"] or payload["unclassified_survivors"])
