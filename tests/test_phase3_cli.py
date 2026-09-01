from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BM = ROOT / "skills/_shared/scripts/bm.py"
TESTS = Path(__file__).resolve().parent
if str(TESTS) not in sys.path:
    sys.path.insert(0, str(TESTS))

from test_next_wave import NextWaveScenarios, tree_digest  # noqa: E402


class Phase3CliScenarios(unittest.TestCase):
    def run_bm(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(BM), *args],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def json_bm(self, *args: str) -> dict[str, object]:
        result = self.run_bm(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def init_repo(self, root: Path) -> None:
        root.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "BM Test"], cwd=root, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.invalid"], cwd=root, check=True
        )

    def test_direct_classify_preserves_boundary_and_exposes_derived_floor(self) -> None:
        boundary = self.json_bm(
            "direct",
            "classify",
            "--external-effect-score",
            "1",
            "--money-score",
            "1",
        )
        self.assertEqual((boundary["score"], boundary["route"]), (2, "normal"))
        self.assertEqual(boundary["declared_score"], 2)
        self.assertEqual(boundary["effective_score"], 2)

        structural = self.json_bm(
            "direct", "classify", "--changed-file", "src/payments/service.py"
        )
        self.assertEqual(structural["declared_score"], 0)
        self.assertEqual(structural["derived_floor"], 3)
        self.assertEqual((structural["score"], structural["route"]), (3, "protected"))
        self.assertEqual(structural["workflow"], "quick")

    def test_finish_reclassifies_real_diff_and_requires_checkpoint_guards(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            self.init_repo(repo)
            self.json_bm("model", "init", "--repo", str(repo))
            started = self.json_bm(
                "direct",
                "start",
                "--repo",
                str(repo),
                "--objective",
                "Ajustar persistência interna",
                "--scope",
                "Mudança localizada",
                "--acceptance",
                "Persistência verificada",
                "--verification",
                "python3 -m unittest",
            )
            quick = str(started["id"])
            migration = repo / "db/migrations/0001_add_index.sql"
            migration.parent.mkdir(parents=True)
            migration.write_text("CREATE INDEX idx_fixture ON fixture(id);\n", encoding="utf-8")
            checkpoint = self.json_bm(
                "direct",
                "checkpoint",
                "--repo",
                str(repo),
                "--slug",
                quick,
                "--checkpoint",
                "Migração verificada",
                "--next-action",
                "Finalizar",
                "--changed-file",
                "db/migrations/0001_add_index.sql",
                "--evidence",
                "teste local passou",
                "--guard",
                "rollback",
                "--guard",
                "backup_restore",
                "--guard",
                "migration_verify",
            )
            self.assertEqual(checkpoint["risk"]["route"], "protected")

            finished = self.json_bm(
                "direct",
                "finish",
                "--repo",
                str(repo),
                "--slug",
                quick,
                "--status",
                "completed",
                "--next-action",
                "Concluído",
                "--verification",
                "teste local passou",
                "--docviva-kind",
                "internal",
                "--docviva-outcome",
                "not_applicable",
                "--docviva-justification",
                "A migração da fixture não altera contrato observável do método.",
            )
            self.assertTrue(finished["risk"]["reclassified"])
            self.assertEqual(finished["risk"]["effective_score"], 3)

    def test_finish_reclassifies_changes_committed_after_quick_start(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp) / "repo"
            self.init_repo(repo)
            self.json_bm("model", "init", "--repo", str(repo))
            subprocess.run(
                ["git", "add", "."], cwd=repo, check=True, capture_output=True
            )
            subprocess.run(
                ["git", "commit", "-m", "baseline"],
                cwd=repo,
                check=True,
                capture_output=True,
            )
            started = self.json_bm(
                "direct",
                "start",
                "--repo",
                str(repo),
                "--objective",
                "Criar migração pequena",
                "--scope",
                "Mudança localizada",
                "--acceptance",
                "Migração verificada",
                "--verification",
                "python3 -m unittest",
            )
            quick = str(started["id"])
            migration = repo / "db/migrations/0002_committed.sql"
            migration.parent.mkdir(parents=True)
            migration.write_text("ALTER TABLE fixture ADD COLUMN name TEXT;\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "db/migrations/0002_committed.sql"],
                cwd=repo,
                check=True,
            )
            subprocess.run(
                ["git", "commit", "-m", "add migration"],
                cwd=repo,
                check=True,
                capture_output=True,
            )
            checkpoint = self.json_bm(
                "direct",
                "checkpoint",
                "--repo",
                str(repo),
                "--slug",
                quick,
                "--checkpoint",
                "Migração commitada verificada",
                "--next-action",
                "Finalizar",
                "--evidence",
                "teste local passou",
                "--guard",
                "rollback",
                "--guard",
                "backup_restore",
                "--guard",
                "migration_verify",
            )
            self.assertEqual(checkpoint["risk"]["route"], "protected")
            self.assertIn(
                "diff_path:migration:db/migrations/0002_committed.sql",
                checkpoint["risk"]["reasons"],
            )

    def test_next_wave_is_public_read_only_projection(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            repo, _change = NextWaveScenarios().make_repo(Path(temp))
            before = tree_digest(repo / ".bianchini")
            result = self.json_bm(
                "roadmap",
                "next-wave",
                "--repo",
                str(repo),
                "--change",
                "C001",
                "--format",
                "json",
            )
            self.assertTrue(result["eligible_wave"])
            self.assertEqual(tree_digest(repo / ".bianchini"), before)

    def test_adapter_render_and_explicit_install_are_public(self) -> None:
        rendered = self.json_bm("adapter", "render", "--host", "codex")
        self.assertIn("menor diff compatível", rendered["content"])
        with tempfile.TemporaryDirectory() as temp:
            repo = Path(temp)
            (repo / "AGENTS.md").write_text("# Regra estrangeira\n", encoding="utf-8")
            installed = self.json_bm(
                "adapter", "install", "--repo", str(repo), "--host", "generic"
            )
            self.assertTrue(installed["changed"])
            self.assertTrue(
                (repo / "AGENTS.md").read_text(encoding="utf-8").startswith(
                    "# Regra estrangeira\n"
                )
            )


if __name__ == "__main__":
    unittest.main()
