"""Transição segura da linhagem numérica antiga para SemVer compacto."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "_shared" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from bm_update import MANAGED_SKILL_DIRS, UpdateError, update_bianchini_method  # noqa: E402


RESET_VERSION = "0.4.0"
MANIFEST_PATH = "_shared/releases/0.4.0.json"


def valid_manifest(*, authorized: bool = True, majors: list[int] | None = None) -> bytes:
    return (
        json.dumps(
            {
                "schema_version": 1,
                "release_version": RESET_VERSION,
                "lineage_reset": {
                    "authorized": authorized,
                    "from_major_versions": majors if majors is not None else [1, 2, 3],
                    "to_version": RESET_VERSION,
                },
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def write_installation(skills_root: Path, version: str, marker: str) -> None:
    for name in MANAGED_SKILL_DIRS:
        directory = skills_root / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "PACKAGE.txt").write_text(marker + "\n", encoding="utf-8")
    (skills_root / "_shared/VERSION").write_text(version + "\n", encoding="utf-8")


def package_archive(
    version: str,
    *,
    manifest: bytes | None = None,
    marker: str = "remote",
) -> bytes:
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode="w:gz") as archive:
        def add(relative: str, content: bytes) -> None:
            info = tarfile.TarInfo(name=f"bianchini-method-main/skills/{relative}")
            info.size = len(content)
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(content))

        add("_shared/VERSION", (version + "\n").encode("utf-8"))
        if manifest is not None:
            add(MANIFEST_PATH, manifest)
        for name in MANAGED_SKILL_DIRS:
            add(f"{name}/PACKAGE.txt", (marker + "\n").encode("utf-8"))
    return stream.getvalue()


def fetcher(
    version: str,
    *,
    manifest: bytes | Exception | None = None,
    archive: bytes | None = None,
):
    calls: list[str] = []

    def fetch(url: str, timeout: float) -> bytes:
        calls.append(url)
        if url.endswith("/skills/_shared/VERSION"):
            return (version + "\n").encode("utf-8")
        if url.endswith("/skills/_shared/releases/0.4.0.json"):
            if isinstance(manifest, Exception):
                raise manifest
            if manifest is not None:
                return manifest
            raise UpdateError("manifesto de reset ausente")
        if "codeload.github.com" in url and archive is not None:
            return archive
        raise AssertionError(f"URL inesperada: {url}")

    return fetch, calls


def git(cwd: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=False
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stderr)
    return completed.stdout.strip()


class LineageResetPackageScenarios(unittest.TestCase):
    def test_repository_versions_the_exact_0_4_0_reset_manifest(self) -> None:
        self.assertEqual(
            (ROOT / "skills" / MANIFEST_PATH).read_bytes(),
            valid_manifest(),
        )

    def test_check_allows_old_numeric_lineage_only_with_explicit_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            skills = Path(temp) / "skills"
            write_installation(skills, "3.2.0", "local")
            fetch, calls = fetcher(RESET_VERSION, manifest=valid_manifest())

            result = update_bianchini_method(
                skills_root=skills,
                check_only=True,
                fetch_bytes=fetch,
            )

            self.assertEqual(result["status"], "update_available")
            self.assertEqual(result["installed_version"], "3.2.0")
            self.assertEqual(result["latest_version"], RESET_VERSION)
            self.assertEqual(len(calls), 2)
            self.assertTrue(calls[1].endswith("/skills/_shared/releases/0.4.0.json"))
            self.assertEqual((skills / "_shared/VERSION").read_text().strip(), "3.2.0")

    def test_package_reset_requires_same_manifest_in_official_archive(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            skills = Path(temp) / "skills"
            write_installation(skills, "3.2.0", "local")
            manifest = valid_manifest()
            fetch, _ = fetcher(
                RESET_VERSION,
                manifest=manifest,
                archive=package_archive(RESET_VERSION, manifest=manifest),
            )

            result = update_bianchini_method(skills_root=skills, fetch_bytes=fetch)

            self.assertEqual(result["status"], "updated")
            self.assertEqual((skills / "_shared/VERSION").read_text().strip(), RESET_VERSION)
            self.assertEqual(
                (skills / MANIFEST_PATH).read_bytes(),
                manifest,
            )

    def test_missing_or_invalid_manifest_blocks_without_downloading_archive(self) -> None:
        cases = (
            (None, "manifesto"),
            (b"not-json\n", "manifesto"),
            (valid_manifest(authorized=False), "autoriza"),
            (valid_manifest(majors=[1, 2]), "linhagem instalada"),
            (
                valid_manifest().replace(b'"to_version": "0.4.0"', b'"to_version": "0.5.0"'),
                "destino diferente",
            ),
        )
        for manifest, message in cases:
            with self.subTest(message=message), tempfile.TemporaryDirectory() as temp:
                skills = Path(temp) / "skills"
                write_installation(skills, "3.2.0", "local")
                fetch, calls = fetcher(
                    RESET_VERSION,
                    manifest=manifest,
                    archive=package_archive(RESET_VERSION, manifest=valid_manifest()),
                )

                with self.assertRaisesRegex((UpdateError, AssertionError), message):
                    update_bianchini_method(skills_root=skills, fetch_bytes=fetch)

                self.assertFalse(any("codeload.github.com" in call for call in calls))
                self.assertEqual(
                    (skills / "_shared/VERSION").read_text().strip(),
                    "3.2.0",
                )

    def test_archive_manifest_mismatch_blocks_before_installation(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            skills = Path(temp) / "skills"
            write_installation(skills, "3.2.0", "local")
            fetched_manifest = valid_manifest()
            archive_manifest = valid_manifest(majors=[1, 2, 3, 4])
            fetch, _ = fetcher(
                RESET_VERSION,
                manifest=fetched_manifest,
                archive=package_archive(RESET_VERSION, manifest=archive_manifest),
            )

            with self.assertRaisesRegex(UpdateError, "manifesto.*diverge"):
                update_bianchini_method(skills_root=skills, fetch_bytes=fetch)

            self.assertEqual((skills / "_shared/VERSION").read_text().strip(), "3.2.0")
            self.assertEqual((skills / "_shared/PACKAGE.txt").read_text().strip(), "local")

    def test_reset_exception_is_only_for_0_4_0(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            skills = Path(temp) / "skills"
            write_installation(skills, "3.2.0", "local")
            fetch, calls = fetcher("0.5.0", manifest=valid_manifest())

            result = update_bianchini_method(skills_root=skills, fetch_bytes=fetch)

            self.assertEqual(result["status"], "ahead")
            self.assertEqual(len(calls), 1)

    def test_semver_is_normal_before_and_after_reset(self) -> None:
        cases = (
            ("0.3.9", "0.4.0", "update_available"),
            ("0.4.0", "0.4.1", "update_available"),
            ("0.5.0", "0.4.0", "ahead"),
        )
        for installed, remote, expected in cases:
            with self.subTest(installed=installed, remote=remote), tempfile.TemporaryDirectory() as temp:
                skills = Path(temp) / "skills"
                write_installation(skills, installed, "local")
                fetch, calls = fetcher(remote)

                result = update_bianchini_method(
                    skills_root=skills,
                    check_only=True,
                    fetch_bytes=fetch,
                )

                self.assertEqual(result["status"], expected)
                self.assertEqual(len(calls), 1)

    def test_reset_rejects_non_official_repository_or_branch(self) -> None:
        for kwargs in (
            {"repository": "example/fork"},
            {"branch": "release"},
        ):
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as temp:
                skills = Path(temp) / "skills"
                write_installation(skills, "3.2.0", "local")
                fetch, calls = fetcher(RESET_VERSION, manifest=valid_manifest())

                with self.assertRaisesRegex(UpdateError, "fonte oficial"):
                    update_bianchini_method(
                        skills_root=skills,
                        check_only=True,
                        fetch_bytes=fetch,
                        **kwargs,
                    )

                self.assertEqual(len(calls), 1)


class LineageResetGitScenarios(unittest.TestCase):
    def make_checkout(self, root: Path, *, include_remote_manifest: bool) -> tuple[Path, bytes]:
        remote = root / "remote.git"
        seed = root / "seed"
        local = root / "local"
        git(root, "init", "--bare", str(remote))
        seed.mkdir()
        git(seed, "init", "-b", "main")
        git(seed, "config", "user.name", "BM Test")
        git(seed, "config", "user.email", "test@example.invalid")
        write_installation(seed / "skills", "3.2.0", "old")
        git(seed, "add", "skills")
        git(seed, "commit", "-m", "old lineage")
        git(seed, "remote", "add", "origin", str(remote))
        git(seed, "push", "-u", "origin", "main")
        git(root, "clone", "--branch", "main", str(remote), str(local))
        official = "https://github.com/felipebianchini2006/bianchini-method.git"
        git(local, "remote", "set-url", "origin", official)
        git(local, "config", f"url.file://{remote.resolve()}/.insteadOf", official)

        write_installation(seed / "skills", RESET_VERSION, "new")
        manifest = valid_manifest()
        if include_remote_manifest:
            target = seed / "skills" / MANIFEST_PATH
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(manifest)
        git(seed, "add", "skills")
        git(seed, "commit", "-m", "compact semver")
        git(seed, "push", "origin", "main")
        return local, manifest

    def test_git_reset_validates_origin_branch_and_versioned_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            local, manifest = self.make_checkout(
                Path(temp), include_remote_manifest=True
            )
            fetch, _ = fetcher(RESET_VERSION, manifest=manifest)

            result = update_bianchini_method(
                skills_root=local / "skills",
                fetch_bytes=fetch,
            )

            self.assertEqual(result["status"], "updated")
            self.assertEqual((local / "skills/_shared/VERSION").read_text().strip(), RESET_VERSION)
            self.assertEqual((local / "skills" / MANIFEST_PATH).read_bytes(), manifest)

    def test_git_reset_blocks_when_origin_branch_lacks_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            local, manifest = self.make_checkout(
                Path(temp), include_remote_manifest=False
            )
            original_head = git(local, "rev-parse", "HEAD")
            fetch, _ = fetcher(RESET_VERSION, manifest=manifest)

            with self.assertRaisesRegex(UpdateError, "manifesto"):
                update_bianchini_method(
                    skills_root=local / "skills",
                    fetch_bytes=fetch,
                )

            self.assertEqual(git(local, "rev-parse", "HEAD"), original_head)
            self.assertEqual((local / "skills/_shared/VERSION").read_text().strip(), "3.2.0")


if __name__ == "__main__":
    unittest.main()
