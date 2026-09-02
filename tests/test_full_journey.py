"""Jornadas públicas completas do Bianchini Method 0.4.

Os cenários usam somente o CLI publicado e Git para executar o fluxo. A autoria
dos artefatos de escopo, design, SDD e homologação representa as saídas humanas
das skills correspondentes.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_method_v04_cli import (
    detailed_scope_body,
    empty_model,
    git,
    init_git,
    markdown_document,
    tree_digest,
    typed_plan,
    typed_task,
    write_text_pdf,
)


ROOT = Path(__file__).resolve().parents[1]
PYTHON_CLI = ROOT / "scripts/bm_python_oracle.py"
TRACEABLE_SCOPE_IDS = (
    "FLW-001",
    "REQ-001",
    "BR-001",
    "DAT-001",
    "ERR-001",
    "RSK-001",
)


class PublicCli:
    """Executa um backend escolhido explicitamente, sem imports do kernel."""

    def __init__(self) -> None:
        backend = os.environ.get("BM_FULL_JOURNEY_BACKEND", "python")
        if backend == "python":
            self.name = "python"
            self.command = (sys.executable, str(PYTHON_CLI))
        elif backend == "go":
            binary = os.environ.get("BM_FULL_JOURNEY_GO_BINARY")
            if not binary:
                raise AssertionError(
                    "BM_FULL_JOURNEY_BACKEND=go exige BM_FULL_JOURNEY_GO_BINARY; "
                    "não existe fallback para Python"
                )
            binary_path = Path(binary).resolve()
            if not binary_path.is_file() or not os.access(binary_path, os.X_OK):
                raise AssertionError(
                    f"BM_FULL_JOURNEY_GO_BINARY não é executável: {binary_path}"
                )
            self.name = "go"
            self.command = (str(binary_path),)
        else:
            raise AssertionError(
                f"BM_FULL_JOURNEY_BACKEND inválido: {backend}; use python ou go"
            )

    def json(self, *args: str, cwd: Path | None = None) -> dict[str, object]:
        completed = subprocess.run(
            [*self.command, *args],
            cwd=cwd or ROOT,
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise AssertionError(
                f"backend {self.name} falhou ({completed.returncode}): "
                f"{' '.join(args)}\n{completed.stderr}\n{completed.stdout}"
            )
        return json.loads(completed.stdout)


def read_frontmatter(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8").split("---", 2)[1])


def run_candidate(repo: Path) -> dict[str, object]:
    completed = subprocess.run(
        ["python3", "app.py", "--health"],
        cwd=repo,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr)
    return json.loads(completed.stdout)


class FullJourneyScenarios(unittest.TestCase):
    def setUp(self) -> None:
        self.cli = PublicCli()

    def write_managed_specs(
        self, repo: Path, change_root: Path, *scope_ids: str
    ) -> None:
        expected = change_root / "specs/expected"
        expected.mkdir(parents=True, exist_ok=True)
        requirements = []
        sections = ["# Spec do sistema"]
        for index, scope_id in enumerate(scope_ids, start=1):
            requirement_id = f"SPEC-{index:03d}"
            requirements.append({"id": requirement_id, "scope": [scope_id]})
            sections.extend(
                [
                    "",
                    f"## {requirement_id}: Contrato de {scope_id}",
                    "",
                    f"O sistema deve entregar o comportamento rastreado por {scope_id}.",
                ]
            )
        (expected / "system.md").write_text(
            "\n".join(sections).rstrip() + "\n", encoding="utf-8"
        )
        (change_root / "specs/MANIFEST.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "spec_contract": 1,
                    "specs": [
                        {
                            "id": "system",
                            "path": "system.md",
                            "requirements": requirements,
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
        self.cli.json(
            "spec-diff",
            "--root",
            str(repo),
            "--base",
            str(repo / ".bianchini/current/specs"),
            "--target",
            str(expected),
            "--output",
            str(change_root / "specs/diff.md"),
        )

    def bootstrap(self, base: Path, *, legacy_schema: bool) -> tuple[Path, str, bytes]:
        repo = base / "repo"
        init_git(repo)
        (repo / ".gitignore").write_text(
            "/.bianchini/.runtime/\n/.planning/\n", encoding="utf-8"
        )
        foreign_planning = repo / ".planning/foreign-owner.txt"
        foreign_planning.parent.mkdir()
        foreign_planning.write_bytes(b"conteudo estrangeiro: preservar byte a byte\n")
        planning_before = foreign_planning.read_bytes()

        initialized = self.cli.json("model", "init", "--repo", str(repo))
        self.assertEqual(initialized["status"], "idle")
        created = self.cli.json(
            "model", "init", "--repo", str(repo), "--change", "health journey"
        )
        change = str(created["change"])
        change_root = repo / ".bianchini/changes" / change

        if legacy_schema:
            coherence_path = change_root / "COHERENCE.md"
            coherence = read_frontmatter(coherence_path)
            coherence["schema_version"] = 1
            coherence.pop("planning_contract")
            coherence.pop("spec_contract")
            coherence_path.write_text(
                markdown_document(coherence, "Coerência legada"), encoding="utf-8"
            )
            specs = change_root / "specs"
            for path in sorted(specs.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            specs.rmdir()

        source = base / "escopo-cliente.pdf"
        write_text_pdf(source, ["Portal de suporte", "Regras e aceite"])
        draft = base / "scope-draft.md"
        draft.write_text(detailed_scope_body(), encoding="utf-8")
        sealed = self.cli.json(
            "scope",
            "seal",
            "--repo",
            str(repo),
            "--change",
            change,
            "--source",
            str(source),
            "--draft",
            str(draft),
            "--pages",
            "2",
            "--extraction",
            "native",
        )
        verified = self.cli.json(
            "scope",
            "verify",
            "--repo",
            str(repo),
            "--change",
            change,
            "--source",
            str(source),
        )
        self.assertEqual(sealed["status"], "ready_for_sdd")
        self.assertEqual(verified["scope_digest"], sealed["scope_digest"])
        self.assertEqual(foreign_planning.read_bytes(), planning_before)
        return repo, change, planning_before

    def import_design(self, repo: Path, change: str) -> str:
        change_root = repo / ".bianchini/changes" / change
        design_root = change_root / "design/imported"
        contract = design_root / "DESIGN_CONTRACT.md"
        prototype = design_root / "prototype.html"
        tokens = design_root / "tokens.css"
        screenshot = design_root / "desktop.png"
        manifest = design_root / "DESIGN_MANIFEST.json"
        design_root.mkdir(parents=True)
        contract.write_text(
            "# Design Contract\n\nDS-001 mantém o health check legível.\n",
            encoding="utf-8",
        )
        prototype.write_text(
            "<!doctype html><title>Health</title><main>Status OK</main>\n",
            encoding="utf-8",
        )
        tokens.write_text(":root { --status-ok: #087f5b; }\n", encoding="utf-8")
        screenshot.write_bytes(b"\x89PNG\r\n\x1a\nfull-journey-design")
        files = [
            path.relative_to(repo).as_posix()
            for path in (contract, prototype, tokens, screenshot)
        ]
        manifest.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "draft",
                    "source": "imported",
                    "scope_source": None,
                    "scope_digest": None,
                    "design_digest": None,
                    "contract": files[0],
                    "prototype": files[1],
                    "tokens": files[2],
                    "screenshots": [files[3]],
                    "surfaces": ["health-cli"],
                    "breakpoints": ["terminal"],
                    "files": files,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        sealed = self.cli.json(
            "design-audit",
            "seal",
            "--root",
            str(repo),
            "--scope",
            str(change_root / "SCOPE.md"),
            "--manifest",
            str(manifest),
        )
        approved = json.loads(manifest.read_text(encoding="utf-8"))
        approved["status"] = "approved"
        manifest.write_text(
            json.dumps(approved, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        verified = self.cli.json(
            "design-audit",
            "verify",
            "--root",
            str(repo),
            "--scope",
            str(change_root / "SCOPE.md"),
            "--manifest",
            str(manifest),
        )
        self.assertEqual(verified["design_digest"], sealed["design_digest"])
        return str(verified["design_digest"])

    def prepare_and_approve_planning(
        self,
        base: Path,
        repo: Path,
        change: str,
        *,
        legacy_schema: bool,
        design_digest: str | None,
    ) -> dict[str, object]:
        change_root = repo / ".bianchini/changes" / change
        (change_root / "RESEARCH.md").write_text(
            "# Pesquisa\n\nPython 3 e a interface CLI local são suficientes.\n",
            encoding="utf-8",
        )
        design_line = (
            f"\nDesign aprovado: `{design_digest}`.\n" if design_digest else "\nDesign não aplicável.\n"
        )
        (change_root / "ARCHITECTURE.md").write_text(
            "# Arquitetura global\n\nCLI sem estado externo; saída JSON determinística.\n"
            + design_line,
            encoding="utf-8",
        )

        if legacy_schema:
            plan: dict[str, object] = {
                "id": "P01",
                "acceptance": ["health check retorna status ok"],
                "verifications": ["python3 app.py --health"],
            }
            delta: dict[str, object] = {}
        else:
            delta = {"contracts": {"add": [{"id": "health_checked"}]}}
            (change_root / "SYSTEM_MODEL.md").write_text(
                markdown_document(
                    empty_model(contracts=[{"id": "health_checked"}]),
                    "Sistema final",
                ),
                encoding="utf-8",
            )
            task = typed_task("T01", covers=list(TRACEABLE_SCOPE_IDS))
            task["files"] = ["app.py"]
            task["verify"] = {
                "kind": "command",
                "run": "python3 app.py --health",
                "proves": "A interface pública do RC responde status ok.",
            }
            plan = typed_plan(
                "P01",
                requirements=list(TRACEABLE_SCOPE_IDS),
                tasks=[task],
                provides=["health_checked"],
                model_delta=delta,
            )
            self.write_managed_specs(repo, change_root, *TRACEABLE_SCOPE_IDS)

        (change_root / "plans/P01-health-journey.md").write_text(
            markdown_document(plan, "P01 — Health journey"), encoding="utf-8"
        )
        if legacy_schema:
            # O contrato 1 aceita o roadmap histórico como documento autorado;
            # o comando determinístico `roadmap sync` pertence ao contrato 2.
            (change_root / "ROADMAP.md").write_text(
                "# Roadmap\n\n## P01\n\nEntregar o health check público.\n",
                encoding="utf-8",
            )
        else:
            roadmap = self.cli.json(
                "roadmap", "sync", "--repo", str(repo), "--change", change
            )
            self.assertEqual(roadmap["phases"], ["P01"])
        validated = self.cli.json(
            "model", "validate", "--repo", str(repo), "--change", change
        )
        self.assertTrue(validated["valid"])
        structural = self.cli.json(
            "coherence",
            "check",
            "--repo",
            str(repo),
            "--change",
            change,
            "--structural-only",
        )
        self.assertEqual(structural["status"], "structurally_valid")
        semantic = base / f"semantic-{'v1' if legacy_schema else 'v2'}.json"
        semantic.write_text(
            json.dumps(
                {
                    "prompt": "revisão semântica da jornada completa",
                    "inputs": structural["review_input_digest"],
                    "sources": ["escopo selado", "contrato público"],
                    "findings": [],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        coherent = self.cli.json(
            "coherence",
            "check",
            "--repo",
            str(repo),
            "--change",
            change,
            "--semantic-report",
            str(semantic),
        )
        self.assertEqual(coherent["status"], "ready_for_approval")
        approved = self.cli.json(
            "coherence",
            "approve",
            "--repo",
            str(repo),
            "--change",
            change,
            "--digest",
            str(coherent["digest"]),
            "--approved-by",
            "human:full-journey",
        )
        self.assertEqual(approved["status"], "approved")
        return delta

    def execute_in_isolated_workspace(
        self,
        base: Path,
        repo: Path,
        change: str,
        delta: dict[str, object],
        *,
        legacy_schema: bool,
    ) -> str:
        git(repo, "add", ".")
        git(repo, "commit", "-m", "approve full journey plan")
        target = base / "execution-worktree"
        created = self.cli.json(
            "workspace",
            "create",
            "--repo",
            str(repo),
            "--change",
            change,
            "--plan",
            "P01",
            "--target",
            str(target),
        )
        self.assertEqual(created["branch"], "bm/c001-p01")
        self.assertTrue(
            self.cli.json("workspace", "check", "--repo", str(target))["valid"]
        )
        if not legacy_schema:
            wave = self.cli.json(
                "roadmap", "next-wave", "--repo", str(target), "--change", change
            )
            self.assertEqual(wave["eligible_wave"], ["C001/P01/T01"])
            self.assertEqual(
                [unit["pack_identity"] for unit in wave["parallel_units"]],
                ["C001/P01/T01"],
            )

        if not legacy_schema:
            packed = self.cli.json(
                "context", "pack", "--repo", str(target), "--unit", "C001/P01/T01"
            )

        (target / "app.py").write_text(
            """#!/usr/bin/env python3
import json
import sys

if sys.argv[1:] != [\"--health\"]:
    raise SystemExit(2)
print(json.dumps({\"status\": \"ok\", \"surface\": \"public-cli\"}, sort_keys=True))
""",
            encoding="utf-8",
        )
        self.assertEqual(run_candidate(target), {"status": "ok", "surface": "public-cli"})
        if not legacy_schema:
            task = self.cli.json(
                "plan",
                "complete",
                "--repo",
                str(target),
                "--change",
                change,
                "--plan",
                "P01",
                "--task",
                "T01",
                "--context-pack",
                str(target / str(packed["path"])),
                "--result",
                "health check implementado",
                "--verification",
                "python3 app.py --health => status ok",
            )
            self.assertEqual(task["status"], "completed")
        actual_delta = base / f"actual-delta-{'v1' if legacy_schema else 'v2'}.json"
        actual_delta.write_text(json.dumps(delta), encoding="utf-8")
        completed = self.cli.json(
            "plan",
            "complete",
            "--repo",
            str(target),
            "--change",
            change,
            "--plan",
            "P01",
            "--actual-delta",
            str(actual_delta),
            "--result",
            "release candidate executável entregue",
            "--verification",
            "python3 app.py --health => status ok",
        )
        self.assertEqual(completed["status"], "completed")
        git(target, "add", ".")
        git(target, "commit", "-m", "execute full journey plan")
        execution_revision = git(target, "rev-parse", "HEAD")
        git(repo, "merge", "--ff-only", "bm/c001-p01")
        git(repo, "worktree", "remove", str(target))
        return execution_revision

    def close_homologate_and_assert_ready(
        self,
        repo: Path,
        change: str,
        execution_revision: str,
        planning_before: bytes,
        *,
        managed_specs: bool,
    ) -> None:
        closed = self.cli.json("cycle-close", "--repo", str(repo), "--change", change)
        self.assertEqual(closed["status"], "completed")
        if managed_specs:
            self.assertTrue(closed["specs_promoted"])
            self.assertEqual(closed["specs_status"], "managed")
        archive = repo / ".bianchini/archive" / change
        self.assertTrue((archive / "SUMMARY.md").is_file())
        self.assertFalse((repo / ".bianchini/changes" / change).exists())

        checksum = hashlib.sha256((repo / "app.py").read_bytes()).hexdigest()
        candidate = {
            "id": f"RC-{change}",
            "revision": execution_revision,
            "build": "full-journey-1",
            "checksum": checksum,
        }
        fingerprint = hashlib.sha256(
            json.dumps(candidate, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        homologation = archive / "results/HOMOLOGATION.md"
        payload: dict[str, object] = {
            "schema_version": 1,
            "fingerprint": fingerprint,
            "rc": candidate,
            "change": change,
            "status": "running",
            "gates": ["python3 app.py --health"],
            "blockers": [],
            "findings": [],
            "required_refs": [f".bianchini/archive/{change}/results/P01.md"],
        }
        homologation.write_text(
            markdown_document(payload, "Homologação\n\nExecução real pendente."),
            encoding="utf-8",
        )
        running_pack = self.cli.json(
            "context",
            "pack",
            "--repo",
            str(repo),
            "--unit",
            f"RC:{fingerprint}",
        )
        self.assertEqual(
            self.cli.json(
                "context",
                "verify",
                "--repo",
                str(repo),
                "--path",
                str(repo / str(running_pack["path"])),
            )["unit"],
            f"RC:{fingerprint}",
        )
        self.assertEqual(run_candidate(repo), {"status": "ok", "surface": "public-cli"})
        payload["status"] = "accepted"
        homologation.write_text(
            markdown_document(
                payload,
                "Homologação\n\n"
                "| Plataforma | Perfil | Jornada | Execução real | Resultado |\n"
                "|---|---|---|---|---|\n"
                "| CLI | operador | `app.py --health` | RC sem mock | passed |",
            ),
            encoding="utf-8",
        )
        git(repo, "add", ".")
        git(repo, "commit", "-m", "accept full journey release candidate")
        accepted_pack = self.cli.json(
            "context",
            "pack",
            "--repo",
            str(repo),
            "--unit",
            f"RC:{fingerprint}",
        )
        verified_pack = self.cli.json(
            "context",
            "verify",
            "--repo",
            str(repo),
            "--path",
            str(repo / str(accepted_pack["path"])),
        )

        state = read_frontmatter(repo / ".bianchini/STATE.md")
        accepted = read_frontmatter(homologation)
        self.assertEqual(state["status"], "idle")
        self.assertEqual(state["blockers"], [])
        self.assertEqual(accepted["status"], "accepted")
        self.assertEqual(accepted["rc"], candidate)
        self.assertEqual(accepted["blockers"], [])
        self.assertEqual(accepted["findings"], [])
        self.assertRegex(str(candidate["revision"]), r"^[0-9a-f]{40}$")
        self.assertRegex(str(candidate["checksum"]), r"^[0-9a-f]{64}$")
        self.assertEqual(
            hashlib.sha256((repo / "app.py").read_bytes()).hexdigest(),
            candidate["checksum"],
        )
        self.assertEqual(verified_pack["unit"], f"RC:{fingerprint}")
        self.assertEqual(
            (repo / ".planning/foreign-owner.txt").read_bytes(), planning_before
        )

    def test_schema2_full_journey_with_imported_design_and_task_pack(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            repo, change, planning_before = self.bootstrap(base, legacy_schema=False)
            design_digest = self.import_design(repo, change)
            delta = self.prepare_and_approve_planning(
                base,
                repo,
                change,
                legacy_schema=False,
                design_digest=design_digest,
            )
            execution_revision = self.execute_in_isolated_workspace(
                base, repo, change, delta, legacy_schema=False
            )
            self.close_homologate_and_assert_ready(
                repo,
                change,
                execution_revision,
                planning_before,
                managed_specs=True,
            )
            archived_manifest = (
                repo
                / ".bianchini/archive"
                / change
                / "design/imported/DESIGN_MANIFEST.json"
            )
            self.assertEqual(
                json.loads(archived_manifest.read_text(encoding="utf-8"))["status"],
                "approved",
            )
            self.assertEqual(
                (
                    repo / ".bianchini/current/specs/system.md"
                ).read_bytes(),
                (
                    repo
                    / ".bianchini/archive"
                    / change
                    / "specs/expected/system.md"
                ).read_bytes(),
            )

    def test_schema1_full_journey_without_design_preserves_legacy_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            repo, change, planning_before = self.bootstrap(base, legacy_schema=True)
            specs_before = tree_digest(repo / ".bianchini/current/specs")
            delta = self.prepare_and_approve_planning(
                base,
                repo,
                change,
                legacy_schema=True,
                design_digest=None,
            )
            execution_revision = self.execute_in_isolated_workspace(
                base, repo, change, delta, legacy_schema=True
            )
            self.close_homologate_and_assert_ready(
                repo,
                change,
                execution_revision,
                planning_before,
                managed_specs=False,
            )
            self.assertEqual(tree_digest(repo / ".bianchini/current/specs"), specs_before)
            self.assertFalse((repo / "docs/design").exists())
            self.assertFalse((repo / ".bianchini/archive" / change / "design").exists())


if __name__ == "__main__":
    unittest.main()
