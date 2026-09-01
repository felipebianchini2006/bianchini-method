"""Cenários comportamentais do atualizador do Bianchini Method."""

from __future__ import annotations

import io
import os
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "_shared" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from bm_update import (  # noqa: E402
    MANAGED_SKILL_DIRS,
    UpdateError,
    parse_version,
    update_bianchini_method,
)


def git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=False
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr)
    return completed.stdout.strip()


def write_installation(skills_root: Path, version: str, marker: str) -> None:
    for name in MANAGED_SKILL_DIRS:
        directory = skills_root / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "PACKAGE.txt").write_text(marker + "\n", encoding="utf-8")
    shared = skills_root / "_shared"
    shared.mkdir(parents=True, exist_ok=True)
    (shared / "VERSION").write_text(version + "\n", encoding="utf-8")


def package_archive(version: str, marker: str = "remote") -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        def add(relative: str, content: bytes) -> None:
            info = tarfile.TarInfo(
                name=f"bianchini-method-main/skills/{relative}"
            )
            info.size = len(content)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(content))

        add("_shared/VERSION", (version + "\n").encode())
        for name in MANAGED_SKILL_DIRS:
            add(f"{name}/PACKAGE.txt", (marker + "\n").encode())
    return stream.getvalue()


def fetcher(version: str, archive: bytes | None = None):
    calls: list[str] = []

    def fetch(url: str, timeout: float) -> bytes:
        calls.append(url)
        if url.endswith("/skills/_shared/VERSION"):
            return (version + "\n").encode()
        if "codeload.github.com" in url and archive is not None:
            return archive
        raise AssertionError(f"URL inesperada: {url}")

    return fetch, calls


class SelfUpdateScenarios(unittest.TestCase):
    def test_semantic_version_is_strict_and_ordered(self) -> None:
        self.assertEqual(parse_version("3.2.0\n"), (3, 2, 0))
        self.assertLess(parse_version("3.1.9"), parse_version("3.2.0"))
        for invalid in ("3.2", "v3.2.0-beta", "latest", "3.2.0.1"):
            with self.subTest(value=invalid), self.assertRaises(UpdateError):
                parse_version(invalid)

    def test_check_reports_update_without_downloading_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            skills = Path(temp) / "skills"
            write_installation(skills, "3.1.0", "local")
            fetch, calls = fetcher("3.2.0")

            result = update_bianchini_method(
                skills_root=skills,
                check_only=True,
                fetch_bytes=fetch,
            )

            self.assertEqual(result["status"], "update_available")
            self.assertEqual(result["installed_version"], "3.1.0")
            self.assertEqual(result["latest_version"], "3.2.0")
            self.assertFalse(result["updated"])
            self.assertEqual(len(calls), 1)
            self.assertEqual((skills / "_shared/VERSION").read_text().strip(), "3.1.0")

    def test_equal_or_newer_installation_is_never_replaced(self) -> None:
        for installed, expected in (("3.2.0", "up_to_date"), ("4.0.0", "ahead")):
            with self.subTest(installed=installed), tempfile.TemporaryDirectory() as temp:
                skills = Path(temp) / "skills"
                write_installation(skills, installed, "local")
                fetch, calls = fetcher("3.2.0")
                result = update_bianchini_method(
                    skills_root=skills,
                    fetch_bytes=fetch,
                )
                self.assertEqual(result["status"], expected)
                self.assertFalse(result["updated"])
                self.assertEqual(len(calls), 1)
                self.assertEqual(
                    (skills / "_shared/PACKAGE.txt").read_text().strip(), "local"
                )

    def test_installed_package_updates_atomically_and_preserves_foreign_skills(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            skills = root / "skills"
            write_installation(skills, "3.1.0", "local")
            foreign = skills / "foreign-skill" / "SKILL.md"
            foreign.parent.mkdir(parents=True)
            foreign.write_text("foreign\n", encoding="utf-8")
            archive = package_archive("3.2.0")
            fetch, calls = fetcher("3.2.0", archive)

            result = update_bianchini_method(
                skills_root=skills,
                fetch_bytes=fetch,
            )

            self.assertEqual(result["status"], "updated")
            self.assertEqual(result["mode"], "installed_package")
            self.assertTrue(result["updated"])
            self.assertEqual((skills / "_shared/VERSION").read_text().strip(), "3.2.0")
            self.assertEqual(
                (skills / "sdd-planning/PACKAGE.txt").read_text().strip(), "remote"
            )
            self.assertEqual(foreign.read_text().strip(), "foreign")
            backup = Path(result["backup"])
            self.assertTrue(backup.is_dir())
            self.assertEqual(
                (backup / "_shared/PACKAGE.txt").read_text().strip(), "local"
            )
            self.assertEqual(len(calls), 2)

    def test_archive_path_traversal_is_blocked_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            skills = root / "skills"
            write_installation(skills, "3.1.0", "local")
            stream = io.BytesIO()
            with tarfile.open(fileobj=stream, mode="w:gz") as archive:
                version = b"3.2.0\n"
                version_info = tarfile.TarInfo(
                    "bianchini-method-main/skills/_shared/VERSION"
                )
                version_info.size = len(version)
                archive.addfile(version_info, io.BytesIO(version))
                payload = b"escape"
                malicious = tarfile.TarInfo("../../escape.txt")
                malicious.size = len(payload)
                archive.addfile(malicious, io.BytesIO(payload))
            fetch, _ = fetcher("3.2.0", stream.getvalue())

            with self.assertRaisesRegex(UpdateError, "arquivo inseguro"):
                update_bianchini_method(
                    skills_root=skills,
                    fetch_bytes=fetch,
                )

            self.assertFalse((root / "escape.txt").exists())
            self.assertEqual((skills / "_shared/VERSION").read_text().strip(), "3.1.0")

    def test_failed_replace_restores_complete_previous_installation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            skills = Path(temp) / "skills"
            write_installation(skills, "3.1.0", "local")
            fetch, _ = fetcher("3.2.0", package_archive("3.2.0"))
            real_replace = os.replace
            counter = {"value": 0}

            def flaky_replace(source, destination):
                counter["value"] += 1
                if counter["value"] == 4:
                    raise OSError("falha simulada")
                return real_replace(source, destination)

            with mock.patch("bm_update.os.replace", side_effect=flaky_replace):
                with self.assertRaisesRegex(UpdateError, "rollback"):
                    update_bianchini_method(
                        skills_root=skills,
                        fetch_bytes=fetch,
                    )

            self.assertEqual((skills / "_shared/VERSION").read_text().strip(), "3.1.0")
            for name in MANAGED_SKILL_DIRS:
                self.assertEqual(
                    (skills / name / "PACKAGE.txt").read_text().strip(), "local"
                )

    def test_git_checkout_fast_forwards_main_without_archive_download(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            remote = root / "remote.git"
            seed = root / "seed"
            local = root / "local"
            git(root, "init", "--bare", str(remote))
            seed.mkdir()
            git(seed, "init", "-b", "main")
            git(seed, "config", "user.name", "BM Test")
            git(seed, "config", "user.email", "test@example.invalid")
            write_installation(seed / "skills", "3.1.0", "old")
            git(seed, "add", "skills")
            git(seed, "commit", "-m", "v3.1")
            git(seed, "remote", "add", "origin", str(remote))
            git(seed, "push", "-u", "origin", "main")
            git(root, "clone", "--branch", "main", str(remote), str(local))
            official = "https://github.com/felipebianchini2006/bianchini-method.git"
            git(local, "remote", "set-url", "origin", official)
            git(
                local,
                "config",
                f"url.file://{remote.resolve()}/.insteadOf",
                official,
            )

            write_installation(seed / "skills", "3.2.0", "new")
            git(seed, "add", "skills")
            git(seed, "commit", "-m", "v3.2")
            git(seed, "push", "origin", "main")
            expected_head = git(seed, "rev-parse", "HEAD")
            fetch, calls = fetcher("3.2.0")

            result = update_bianchini_method(
                skills_root=local / "skills",
                fetch_bytes=fetch,
            )

            self.assertEqual(result["status"], "updated")
            self.assertEqual(result["mode"], "git_checkout")
            self.assertEqual(git(local, "rev-parse", "HEAD"), expected_head)
            self.assertEqual((local / "skills/_shared/VERSION").read_text().strip(), "3.2.0")
            self.assertEqual(len(calls), 1)

    def test_git_checkout_rejects_non_official_origin(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            root.mkdir(parents=True)
            git(root, "init", "-b", "main")
            git(root, "config", "user.name", "BM Test")
            git(root, "config", "user.email", "test@example.invalid")
            write_installation(root / "skills", "3.1.0", "local")
            git(root, "add", "skills")
            git(root, "commit", "-m", "base")
            git(root, "remote", "add", "origin", "https://github.com/example/fake.git")
            fetch, _ = fetcher("3.2.0")

            with self.assertRaisesRegex(UpdateError, "repositório oficial"):
                update_bianchini_method(
                    skills_root=root / "skills",
                    fetch_bytes=fetch,
                )

            self.assertEqual((root / "skills/_shared/VERSION").read_text().strip(), "3.1.0")

    def test_dirty_git_checkout_blocks_before_fetch_or_merge(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            root.mkdir(parents=True)
            git(root, "init", "-b", "main")
            git(root, "config", "user.name", "BM Test")
            git(root, "config", "user.email", "test@example.invalid")
            write_installation(root / "skills", "3.1.0", "local")
            git(root, "add", "skills")
            git(root, "commit", "-m", "base")
            (root / "untracked.txt").write_text("dirty\n", encoding="utf-8")
            fetch, _ = fetcher("3.2.0")

            with self.assertRaisesRegex(UpdateError, "alterações locais"):
                update_bianchini_method(
                    skills_root=root / "skills",
                    fetch_bytes=fetch,
                )

            self.assertEqual((root / "skills/_shared/VERSION").read_text().strip(), "3.1.0")

    def test_public_skill_and_cli_expose_explicit_update(self) -> None:
        skill = ROOT / "skills" / "update-bm" / "SKILL.md"
        self.assertTrue(skill.is_file())
        content = skill.read_text(encoding="utf-8")
        self.assertIn("name: update-bm", content)
        self.assertIn("disable-model-invocation: true", content)
        self.assertIn("update-bm --check", content)
        self.assertTrue((ROOT / "skills/_shared/VERSION").is_file())
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/bm_python_oracle.py"),
                "update-bm",
                "--help",
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--check", completed.stdout)
        self.assertIn("--skills-root", completed.stdout)


if __name__ == "__main__":
    unittest.main()
