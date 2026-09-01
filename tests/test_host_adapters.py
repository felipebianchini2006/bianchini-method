"""Goldens e instalação segura dos adapters finos de host."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "_shared" / "scripts"
FIXTURES = ROOT / "tests" / "fixtures" / "host_adapters"
SOURCE = ROOT / "skills" / "_shared" / "host-adapters" / "adapters.json"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from bm_host_adapters import (  # noqa: E402
    HostAdapterError,
    install_adapter,
    render_adapter,
)


HOSTS = ("generic", "codex", "claude-compatible")


def common_contract(rendered: str) -> str:
    return rendered.split("### Contrato comum\n", 1)[1].split(
        "### Política do host\n", 1
    )[0]


class HostAdapterScenarios(unittest.TestCase):
    def test_render_is_reproducible_and_matches_all_goldens(self) -> None:
        for host in HOSTS:
            with self.subTest(host=host):
                expected = (FIXTURES / f"{host}.md").read_text(encoding="utf-8")
                first = render_adapter(host)
                second = render_adapter(host)
                self.assertEqual(first, expected)
                self.assertEqual(second, expected)

    def test_common_rules_have_one_source_and_same_pack_contract(self) -> None:
        source = json.loads(SOURCE.read_text(encoding="utf-8"))
        self.assertIn("common_rules", source)
        for adapter in source["adapters"].values():
            self.assertNotIn("common_rules", adapter)

        generic = common_contract(render_adapter("generic"))
        codex = common_contract(render_adapter("codex"))
        self.assertEqual(generic, codex)
        self.assertIn("pack_identity", generic)
        self.assertIn("pack_digest", generic)
        self.assertIn("package_digest", generic)
        self.assertNotIn("contract_digest", generic)

    def test_codex_adds_smallest_diff_without_changing_common_contract(self) -> None:
        codex = render_adapter("codex")
        generic = render_adapter("generic")

        self.assertIn("menor diff compatível", codex)
        self.assertIn("Não crie abstrações especulativas", codex)
        self.assertNotIn("abstrações especulativas", generic)
        self.assertEqual(common_contract(codex), common_contract(generic))

    def test_two_generic_installs_preserve_foreign_file_and_skill_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            instruction = root / "AGENTS.md"
            foreign_instruction = b"# Regras da equipe\n\nNunca alterar este bloco.\n"
            instruction.write_bytes(foreign_instruction)
            foreign_skill = root / ".agents" / "skills" / "custom" / "SKILL.md"
            foreign_skill.parent.mkdir(parents=True)
            foreign_skill.write_bytes(b"# Skill estrangeira\n")

            first = install_adapter(root, "generic")
            first_bytes = instruction.read_bytes()
            first_mtime = instruction.stat().st_mtime_ns
            second = install_adapter(root, "generic")

            self.assertTrue(first["changed"])
            self.assertFalse(second["changed"])
            self.assertTrue(first_bytes.startswith(foreign_instruction))
            self.assertEqual(instruction.read_bytes(), first_bytes)
            self.assertEqual(instruction.stat().st_mtime_ns, first_mtime)
            self.assertEqual(foreign_skill.read_bytes(), b"# Skill estrangeira\n")

    def test_two_claude_installs_preserve_foreign_file_and_skill_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            instruction = root / "CLAUDE.md"
            foreign_instruction = b"# Claude local\n\nRegra estrangeira.\n"
            instruction.write_bytes(foreign_instruction)
            foreign_skill = root / ".claude" / "skills" / "custom" / "SKILL.md"
            foreign_skill.parent.mkdir(parents=True)
            foreign_skill.write_bytes(b"# Skill Claude estrangeira\n")

            first = install_adapter(root, "claude-compatible")
            first_bytes = instruction.read_bytes()
            second = install_adapter(root, "claude-compatible")

            self.assertTrue(first["changed"])
            self.assertFalse(second["changed"])
            self.assertTrue(first_bytes.startswith(foreign_instruction))
            self.assertEqual(instruction.read_bytes(), first_bytes)
            self.assertEqual(
                foreign_skill.read_bytes(), b"# Skill Claude estrangeira\n"
            )

    def test_adapter_replacement_requires_explicit_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            instruction = root / "AGENTS.md"
            foreign = b"# Regras estrangeiras\n"
            instruction.write_bytes(foreign)
            install_adapter(root, "generic")
            before = instruction.read_bytes()

            with self.assertRaisesRegex(
                HostAdapterError, "HOST_ADAPTER_OVERWRITE_REQUIRED"
            ):
                install_adapter(root, "codex")
            self.assertEqual(instruction.read_bytes(), before)

            replaced = install_adapter(root, "codex", overwrite=True)
            self.assertTrue(replaced["changed"])
            self.assertTrue(instruction.read_bytes().startswith(foreign))
            self.assertIn(b"menor diff compat\xc3\xadvel", instruction.read_bytes())

    def test_install_rejects_symlink_target_without_touching_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            outside = root / "outside.md"
            outside.write_bytes(b"fora\n")
            (root / "AGENTS.md").symlink_to(outside)

            with self.assertRaisesRegex(HostAdapterError, "HOST_ADAPTER_SYMLINK"):
                install_adapter(root, "generic")
            self.assertEqual(outside.read_bytes(), b"fora\n")

    def test_install_rejects_foreign_namespace_before_io(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(HostAdapterError, "HOST_ADAPTER_PATH_INVALID"):
                install_adapter(root / ".planning" / "foreign", "generic")


if __name__ == "__main__":
    unittest.main()
