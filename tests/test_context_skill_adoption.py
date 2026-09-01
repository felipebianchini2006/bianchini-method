from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ContextSkillAdoptionScenarios(unittest.TestCase):
    SKILLS = (
        "executar-plano",
        "executar-direto",
        "corrigir-bug",
        "homologar-sistema",
        "status-projeto",
    )

    def test_operational_skills_use_context_pack_as_primary_interface(self) -> None:
        for name in self.SKILLS:
            with self.subTest(skill=name):
                content = (ROOT / "skills" / name / "SKILL.md").read_text(
                    encoding="utf-8"
                )
                self.assertIn("bm.py context pack", content)
                self.assertIn("PACK_INCOMPLETE", content)
                self.assertNotRegex(content, r"Leia \[.*METHOD_CONTRACT\.md")

    def test_execution_skills_reject_stale_pack_instead_of_full_contract_fallback(self) -> None:
        for name in ("executar-plano", "executar-direto", "corrigir-bug"):
            with self.subTest(skill=name):
                content = (ROOT / "skills" / name / "SKILL.md").read_text(
                    encoding="utf-8"
                )
                self.assertIn("STALE_EVIDENCE", content)
                self.assertIn("sem reler o contrato completo", content)


if __name__ == "__main__":
    unittest.main()
