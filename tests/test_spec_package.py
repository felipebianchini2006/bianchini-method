"""Contrato do pacote de specs gerenciado pelo COHERENCE schema 2."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
import unicodedata
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "_shared" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import bm_spec_package  # noqa: E402
from bm_spec_diff import spec_diff  # noqa: E402
from bm_spec_package import SpecPackageError, load_spec_package  # noqa: E402


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def spec(text: str, *requirements: tuple[str, list[str]]) -> str:
    sections = [f"# {text}"]
    for identifier, _scope in requirements:
        sections.extend(("", f"## {identifier}: {text}", "", f"Contrato {identifier}."))
    return "\n".join(sections) + "\n"


class SpecPackageScenarios(unittest.TestCase):
    def make_package(self, root: Path) -> tuple[Path, Path, Path]:
        change = root / ".bianchini" / "changes" / "C001-auth"
        current = root / ".bianchini" / "current" / "specs"
        expected = change / "specs" / "expected"
        current.mkdir(parents=True)
        expected.mkdir(parents=True)
        scope = change / "SCOPE.md"
        scope.write_text(
            "# Escopo\n\n"
            "### FLW-001 — Autenticar\n\n"
            "### REQ-001 — Criar sessão\n\n"
            "### NFR-001 — Responder rápido\n\n"
            "### BR-001 — Bloquear tentativas\n\n"
            "### DAT-001 — Guardar sessão\n\n"
            "### INT-001 — Consultar identidade\n\n"
            "### ERR-001 — Rejeitar credencial\n\n"
            "### RSK-001 — Abuso de credencial\n",
            encoding="utf-8",
        )
        (current / "auth.md").write_text(
            spec("Autenticação anterior", ("AUTH-001", ["REQ-001"])),
            encoding="utf-8",
        )
        write_json(
            current / "MANIFEST.json",
            {
                "schema_version": 1,
                "spec_contract": 1,
                "specs": [
                    {
                        "id": "auth",
                        "path": "auth.md",
                        "requirements": [
                            {"id": "AUTH-001", "scope": ["REQ-001"]}
                        ],
                    }
                ],
                "risk_coverage": [],
            },
        )
        (expected / "auth.md").write_text(
            spec(
                "Autenticação",
                (
                    "AUTH-001",
                    [
                        "FLW-001",
                        "REQ-001",
                        "NFR-001",
                        "BR-001",
                        "DAT-001",
                        "INT-001",
                        "ERR-001",
                        "RSK-001",
                    ],
                ),
            ),
            encoding="utf-8",
        )
        write_json(
            change / "specs" / "MANIFEST.json",
            {
                "schema_version": 1,
                "spec_contract": 1,
                "specs": [
                    {
                        "id": "auth",
                        "path": "auth.md",
                        "requirements": [
                            {
                                "id": "AUTH-001",
                                "scope": [
                                    "FLW-001",
                                    "REQ-001",
                                    "NFR-001",
                                    "BR-001",
                                    "DAT-001",
                                    "INT-001",
                                    "ERR-001",
                                    "RSK-001",
                                ],
                            }
                        ],
                    }
                ],
                "risk_coverage": [],
            },
        )
        return change, current, scope

    def coherence(self, **overrides: object) -> dict[str, object]:
        value: dict[str, object] = {
            "schema_version": 2,
            "planning_contract": 2,
            "spec_contract": 1,
        }
        value.update(overrides)
        return value

    def render_diff(self, root: Path, change: Path, current: Path) -> dict[str, object]:
        return spec_diff(
            root=root,
            base=current,
            target=change / "specs" / "expected",
            output=change / "specs" / "diff.md",
            manifest=change / "specs" / "MANIFEST.json",
        )

    def load(self, root: Path, change: Path, current: Path, scope: Path) -> dict[str, object]:
        return load_spec_package(
            change_dir=change,
            current_specs=current,
            scope_path=scope,
            coherence=self.coherence(),
        )

    def test_schema1_is_legacy_unmanaged_without_touching_spec_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            result = load_spec_package(
                change_dir=root / "ausente",
                current_specs=root / "tambem-ausente",
                scope_path=root / "SCOPE.md",
                coherence={"schema_version": 1, "planning_contract": 2},
            )
            self.assertEqual(result["specs_status"], "legacy_unmanaged")
            self.assertFalse(result["managed"])
            self.assertNotIn("spec_contract", result)

    def test_schema2_requires_known_spec_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for value in (None, 0, 2):
                coherence = self.coherence(spec_contract=value)
                if value is None:
                    coherence.pop("spec_contract")
                with self.subTest(value=value), self.assertRaisesRegex(
                    SpecPackageError, "spec_contract"
                ):
                    load_spec_package(
                        change_dir=root,
                        current_specs=root / "current",
                        scope_path=root / "SCOPE.md",
                        coherence=coherence,
                    )

    def test_schema2_rejects_foreign_namespace_before_filesystem_access(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(SpecPackageError, "namespace estrangeiro"):
                load_spec_package(
                    change_dir=root / "change",
                    current_specs=root / ".planning" / "specs",
                    scope_path=root / "SCOPE.md",
                    coherence=self.coherence(),
                )

    def test_valid_package_has_deterministic_recursive_digests_and_complete_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            change, current, scope = self.make_package(root)
            generated = self.render_diff(root, change, current)
            first = self.load(root, change, current, scope)
            second = self.load(root, change, current, scope)
            self.assertEqual(first, second)
            self.assertTrue(first["managed"])
            self.assertEqual(first["spec_contract"], 1)
            self.assertEqual(first["diff_digest"], generated["output_digest"])
            for field in (
                "base_digest",
                "target_digest",
                "manifest_digest",
                "diff_digest",
            ):
                self.assertRegex(str(first[field]), r"^[0-9a-f]{64}$")
            self.assertEqual(
                first["scope_coverage"]["RSK-001"], ["spec:AUTH-001"]
            )

    def test_risk_can_be_covered_by_explicit_guard_or_plan_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            change, current, scope = self.make_package(root)
            manifest_path = change / "specs" / "MANIFEST.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["specs"][0]["requirements"][0]["scope"].remove("RSK-001")
            manifest["risk_coverage"] = [
                {"scope": "RSK-001", "kind": "guard", "target": "rate-limit"}
            ]
            write_json(manifest_path, manifest)
            self.render_diff(root, change, current)
            package = self.load(root, change, current, scope)
            self.assertEqual(package["scope_coverage"]["RSK-001"], ["guard:rate-limit"])

    def test_missing_unknown_duplicate_or_empty_coverage_blocks(self) -> None:
        cases = ("missing", "unknown", "duplicate", "empty_scope", "risk_target")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                change, current, scope = self.make_package(root)
                manifest_path = change / "specs" / "MANIFEST.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                requirement = manifest["specs"][0]["requirements"][0]
                if case == "missing":
                    requirement["scope"].remove("ERR-001")
                elif case == "unknown":
                    requirement["scope"].append("REQ-999")
                elif case == "duplicate":
                    manifest["specs"].append(
                        {
                            "id": "copia",
                            "path": "copia.md",
                            "requirements": [
                                {"id": "AUTH-001", "scope": ["REQ-001"]}
                            ],
                        }
                    )
                    (change / "specs" / "expected" / "copia.md").write_text(
                        spec("Cópia", ("AUTH-001", ["REQ-001"])), encoding="utf-8"
                    )
                elif case == "empty_scope":
                    requirement["scope"] = []
                else:
                    requirement["scope"].remove("RSK-001")
                    manifest["risk_coverage"] = [
                        {
                            "scope": "RSK-001",
                            "kind": "spec",
                            "target": "MISSING-001",
                        }
                    ]
                write_json(manifest_path, manifest)
                with self.assertRaisesRegex(
                    SpecPackageError, "cobertura|inexistente|duplicado|vazio|target"
                ):
                    self.render_diff(root, change, current)
                    self.load(root, change, current, scope)

    def test_target_rejects_empty_binary_symlink_and_path_collision(self) -> None:
        cases = ("empty", "binary", "symlink", "collision")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                change, current, scope = self.make_package(root)
                expected = change / "specs" / "expected"
                manifest_path = change / "specs" / "MANIFEST.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if case == "empty":
                    (expected / "auth.md").write_bytes(b"")
                elif case == "binary":
                    (expected / "auth.md").write_bytes(b"\x00\x01\x02")
                elif case == "symlink":
                    (expected / "auth.md").unlink()
                    outside = root / "outside.md"
                    outside.write_text("## AUTH-001: Fora\n", encoding="utf-8")
                    (expected / "auth.md").symlink_to(outside)
                else:
                    manifest["specs"].append(
                        {
                            "id": "collision",
                            "path": "AUTH.md",
                            "requirements": [
                                {"id": "OTHER-001", "scope": ["REQ-001"]}
                            ],
                        }
                    )
                    write_json(manifest_path, manifest)
                with self.assertRaisesRegex(
                    SpecPackageError, "vazio|binário|symlink|colisão"
                ):
                    self.render_diff(root, change, current)
                    self.load(root, change, current, scope)

    def test_manifest_rejects_absolute_traversal_backslash_and_foreign_namespace(self) -> None:
        invalid_paths = (
            "/tmp/spec.md",
            "../spec.md",
            "nested/../../spec.md",
            "nested\\spec.md",
            ".planning/spec.md",
            unicodedata.normalize("NFD", "ação.md"),
        )
        for invalid in invalid_paths:
            with self.subTest(path=invalid), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                change, current, scope = self.make_package(root)
                manifest_path = change / "specs" / "MANIFEST.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest["specs"][0]["path"] = invalid
                write_json(manifest_path, manifest)
                with self.assertRaisesRegex(SpecPackageError, "path"):
                    self.render_diff(root, change, current)
                    self.load(root, change, current, scope)

    def test_manual_diff_change_blocks_until_regenerated(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            change, current, scope = self.make_package(root)
            self.render_diff(root, change, current)
            diff_path = change / "specs" / "diff.md"
            diff_path.write_text(
                diff_path.read_text(encoding="utf-8") + "edição manual\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SpecPackageError, "regener"):
                self.load(root, change, current, scope)
            self.render_diff(root, change, current)
            self.assertTrue(self.load(root, change, current, scope)["managed"])

    def test_manifest_rejects_duplicate_json_keys_at_any_level(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            change, current, _scope = self.make_package(root)
            (change / "specs" / "MANIFEST.json").write_text(
                '{"schema_version":1,"spec_contract":1,"specs":['
                '{"id":"auth","path":"auth.md","path":"other.md",'
                '"requirements":[{"id":"AUTH-001","scope":["REQ-001"]}]}],'
                '"risk_coverage":[]}\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SpecPackageError, "chave JSON duplicada: path"):
                self.render_diff(root, change, current)

    def test_load_uses_one_target_and_manifest_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            change, current, scope = self.make_package(root)
            self.render_diff(root, change, current)
            manifest_path = change / "specs" / "MANIFEST.json"
            calls: list[Path] = []
            original = bm_spec_package.validate_manifest

            def tracked(path: Path, *, trusted_root: Path) -> dict[str, object]:
                calls.append(path)
                return original(path, trusted_root=trusted_root)

            with mock.patch.object(bm_spec_package, "validate_manifest", side_effect=tracked):
                self.load(root, change, current, scope)
            self.assertEqual(calls.count(manifest_path), 1)

    def test_directory_diff_rejects_symlink_in_ancestor_before_reading_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            sandbox = Path(temp)
            root = sandbox / "repo"
            outside = sandbox / "outside"
            root.mkdir()
            outside.mkdir()
            (outside / "base").mkdir()
            (root / "alias").symlink_to(outside, target_is_directory=True)
            target = root / "target"
            target.mkdir()
            (target / "auth.md").write_text(
                spec("Auth", ("AUTH-001", ["REQ-001"])), encoding="utf-8"
            )
            write_json(
                root / "MANIFEST.json",
                {
                    "schema_version": 1,
                    "spec_contract": 1,
                    "specs": [
                        {
                            "id": "auth",
                            "path": "auth.md",
                            "requirements": [
                                {"id": "AUTH-001", "scope": ["REQ-001"]}
                            ],
                        }
                    ],
                    "risk_coverage": [],
                },
            )
            with self.assertRaisesRegex(SpecPackageError, "symlink ancestral"):
                spec_diff(
                    root=root,
                    base=root / "alias" / "base",
                    target=target,
                    output=root / "diff.md",
                    manifest=root / "MANIFEST.json",
                )

    def test_directory_diff_derives_add_modify_remove_and_rename_by_stable_spec_id(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base = root / "base"
            target = root / "target"
            base.mkdir()
            target.mkdir()
            (base / "old-auth.md").write_text(
                spec("Auth antiga", ("AUTH-001", ["REQ-001"])), encoding="utf-8"
            )
            (base / "removed.md").write_text(
                spec("Removida", ("OLD-001", ["REQ-001"])), encoding="utf-8"
            )
            pure_rename = spec("Rename puro", ("PURE-001", ["REQ-001"]))
            (base / "pure-old.md").write_text(pure_rename, encoding="utf-8")
            write_json(
                base / "MANIFEST.json",
                {
                    "schema_version": 1,
                    "spec_contract": 1,
                    "specs": [
                        {
                            "id": "auth",
                            "path": "old-auth.md",
                            "requirements": [
                                {"id": "AUTH-001", "scope": ["REQ-001"]}
                            ],
                        },
                        {
                            "id": "pure",
                            "path": "pure-old.md",
                            "requirements": [
                                {"id": "PURE-001", "scope": ["REQ-001"]}
                            ],
                        },
                        {
                            "id": "removed",
                            "path": "removed.md",
                            "requirements": [
                                {"id": "OLD-001", "scope": ["REQ-001"]}
                            ],
                        },
                    ],
                    "risk_coverage": [],
                },
            )
            (target / "auth.md").write_text(
                spec("Auth nova", ("AUTH-001", ["REQ-001"])), encoding="utf-8"
            )
            (target / "added.md").write_text(
                spec("Adicionada", ("NEW-001", ["REQ-001"])), encoding="utf-8"
            )
            (target / "pure-new.md").write_text(pure_rename, encoding="utf-8")
            target_manifest = root / "MANIFEST.json"
            write_json(
                target_manifest,
                {
                    "schema_version": 1,
                    "spec_contract": 1,
                    "specs": [
                        {
                            "id": "added",
                            "path": "added.md",
                            "requirements": [
                                {"id": "NEW-001", "scope": ["REQ-001"]}
                            ],
                        },
                        {
                            "id": "auth",
                            "path": "auth.md",
                            "requirements": [
                                {"id": "AUTH-001", "scope": ["REQ-001"]}
                            ],
                        },
                        {
                            "id": "pure",
                            "path": "pure-new.md",
                            "requirements": [
                                {"id": "PURE-001", "scope": ["REQ-001"]}
                            ],
                        },
                    ],
                    "risk_coverage": [],
                },
            )
            output = root / "diff.md"
            result = spec_diff(
                root=root,
                base=base,
                target=target,
                output=output,
                manifest=target_manifest,
            )
            self.assertEqual(result["added"], [{"id": "added", "path": "added.md"}])
            self.assertEqual(result["removed"], [{"id": "removed", "path": "removed.md"}])
            self.assertEqual(result["modified"], [{"id": "auth", "path": "auth.md"}])
            self.assertEqual(
                result["renamed"],
                [
                    {"from": "old-auth.md", "id": "auth", "to": "auth.md"},
                    {"from": "pure-old.md", "id": "pure", "to": "pure-new.md"},
                ],
            )
            self.assertNotIn("pure", [item["id"] for item in result["modified"]])
            self.assertEqual(result["mode"], "directory")
            self.assertIn("## RENAMED", output.read_text(encoding="utf-8"))

    def test_legacy_file_diff_shape_remains_compatible(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base = root / "base.md"
            target = root / "target.md"
            output = root / "diff.md"
            base.write_text(
                "## AUTH-001: Antes\n\nA.\n\n## AUTH-003: Removido\n\nC.\n",
                encoding="utf-8",
            )
            target.write_text(
                "## AUTH-001: Depois\n\nB.\n\n## AUTH-002: Adicionado\n\nD.\n",
                encoding="utf-8",
            )
            result = spec_diff(root=root, base=base, target=target, output=output)
            metadata = {
                "schema_version": 1,
                "base": "base.md",
                "base_digest": hashlib.sha256(base.read_bytes()).hexdigest(),
                "target": "target.md",
                "target_digest": hashlib.sha256(target.read_bytes()).hexdigest(),
                "added": ["AUTH-002"],
                "modified": ["AUTH-001"],
                "removed": ["AUTH-003"],
            }
            expected_text = (
                "# Spec Diff\n\n"
                "Esta é uma projeção derivada. A spec target completa permanece a fonte de verdade.\n\n"
                "```json\n"
                + json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True)
                + "\n```\n\n"
                "## ADDED\n\n"
                "### AUTH-002\n\n"
                "## AUTH-002: Adicionado\n\nD.\n\n\n"
                "## MODIFIED\n\n"
                "### AUTH-001\n\n"
                "## AUTH-001: Depois\n\nB.\n\n\n"
                "## REMOVED\n\n"
                "### AUTH-003\n\n"
                "## AUTH-003: Removido\n\nC.\n"
            )
            self.assertEqual(result["added"], ["AUTH-002"])
            self.assertEqual(result["modified"], ["AUTH-001"])
            self.assertEqual(result["removed"], ["AUTH-003"])
            self.assertEqual(result["schema_version"], 1)
            self.assertEqual(result["base"], "base.md")
            self.assertEqual(result["target"], "target.md")
            self.assertEqual(result["output"], "diff.md")
            self.assertEqual(output.read_text(encoding="utf-8"), expected_text)
            self.assertEqual(
                result["output_digest"],
                hashlib.sha256(expected_text.encode("utf-8")).hexdigest(),
            )
            self.assertNotIn("mode", result)
            self.assertNotIn("renamed", result)


if __name__ == "__main__":
    unittest.main()
