"""Integridade do pacote público do Bianchini Method."""

from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"


def frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return {}
    result: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, separator, value = line.partition(":")
        if separator:
            result[key.strip()] = value.strip()
    return result


class PackageIntegrityTests(unittest.TestCase):
    LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")

    def test_public_skills_have_valid_frontmatter(self) -> None:
        skill_files = sorted(path for path in SKILLS.glob("*/SKILL.md") if not path.parent.name.startswith("_"))
        self.assertTrue(skill_files)
        for path in skill_files:
            with self.subTest(skill=path.parent.name):
                metadata = frontmatter(path)
                self.assertEqual(metadata.get("name"), path.parent.name)
                self.assertTrue(metadata.get("description"))

    def test_relative_links_resolve_inside_the_package(self) -> None:
        failures: list[str] = []
        markdown_files = [ROOT / "README.md", *SKILLS.rglob("*.md")]
        for markdown in markdown_files:
            for target in self.LINK.findall(markdown.read_text(encoding="utf-8")):
                target = target.strip().strip("<>").split("#", 1)[0]
                if not target or "://" in target or target.startswith("mailto:"):
                    continue
                if not (markdown.parent / target).resolve().exists():
                    failures.append(f"{markdown.relative_to(ROOT)} -> {target}")
        self.assertEqual(failures, [])

    def test_distribution_has_one_go_backend(self) -> None:
        self.assertTrue((ROOT / "cmd/bm/main.go").is_file())
        self.assertTrue((ROOT / "scripts/bm.py").is_file())
        self.assertFalse((ROOT / "scripts/bm_python_oracle.py").exists())
        self.assertFalse((SKILLS / "_shared/scripts").exists())
        self.assertFalse((ROOT / "codex").exists())


if __name__ == "__main__":
    unittest.main()
