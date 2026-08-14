#!/usr/bin/env python3
"""Instalador atômico e exclusivo do overlay Codex."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path


OWNER = "bianchini-method:executar-plano-codex"
OWNER_FILE = ".bianchini-codex-overlay.json"
MANIFEST_FILE = ".bianchini-codex-manifest.json"
POLICY_OWNER_FILE = ".bianchini-codex-openai.sha256"
LEGACY_REQUIRED = {
    "SKILL.md",
    "agents/openai.yaml",
    "references/CODEX_CONVERGENCE.md",
    "references/plan-reviewer-codex.md",
    "scripts/review_guard.py",
}


class InstallError(RuntimeError):
    """Erro seguro de instalação."""


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def files(root: Path, *, metadata: bool = False) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise InstallError(f"symlink não permitido no pacote: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if not metadata and relative in {OWNER_FILE, MANIFEST_FILE}:
            continue
        result[relative] = digest(path)
    return result


def read_json(path: Path, label: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise InstallError(f"{label} inválido: {path}") from error


def legacy_overlay(target: Path, source_files: set[str]) -> bool:
    actual = set(files(target))
    if not LEGACY_REQUIRED.issubset(actual):
        return False
    if not actual.issubset(source_files):
        raise InstallError(f"instalação legado contém arquivos alheios: {target}")
    skill = (target / "SKILL.md").read_text(encoding="utf-8")
    return "name: executar-plano-codex" in skill


def classify(target: Path, source_files: set[str]) -> str | None:
    if not target.exists() and not target.is_symlink():
        return None
    if target.is_symlink():
        raise InstallError(f"target não pode ser symlink: {target}")
    if not target.is_dir():
        raise InstallError(f"target existente não é diretório: {target}")
    owner_path = target / OWNER_FILE
    manifest_path = target / MANIFEST_FILE
    if owner_path.is_file() and manifest_path.is_file():
        owner = read_json(owner_path, "owner marker")
        manifest = read_json(manifest_path, "manifest")
        if not isinstance(owner, dict) or owner.get("owner") != OWNER:
            raise InstallError(f"owner marker desconhecido: {target}")
        if not isinstance(manifest, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in manifest.items()
        ):
            raise InstallError(f"manifest inválido: {target}")
        current = files(target)
        if current != manifest:
            raise InstallError(
                f"instalação gerenciada foi alterada ou contém arquivos alheios: {target}"
            )
        return "managed"
    if owner_path.exists() or manifest_path.exists():
        raise InstallError(f"metadados parciais no target: {target}")
    if legacy_overlay(target, source_files):
        return "legacy"
    raise InstallError(f"target existente não pertence ao overlay: {target}")


def fsync_tree(root: Path) -> None:
    for path in sorted(root.rglob("*")):
        if path.is_file():
            descriptor = os.open(path, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    for path in sorted(
        (item for item in root.rglob("*") if item.is_dir()),
        key=lambda item: len(item.parts),
        reverse=True,
    ):
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    descriptor = os.open(root, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if temporary.exists():
            temporary.unlink()


def reject_descendant_symlinks(root: Path, path: Path, label: str) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise InstallError(f"{label} escapa da raiz esperada: {path}") from error
    current = root
    for part in relative.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise InstallError(f"{label} contém symlink: {current}")


def select_skills_dir(home: Path, source_files: set[str]) -> Path:
    agents = home / ".agents" / "skills"
    legacy = home / ".codex" / "skills"
    override_raw = os.environ.get("CODEX_SKILLS_DIR")
    candidates = [agents, legacy]
    recognized: list[Path] = []
    occupied: list[Path] = []
    for skills_dir in candidates:
        reject_descendant_symlinks(home, skills_dir, "skills dir")
        target = skills_dir / "executar-plano-codex"
        kind = classify(target, source_files)
        if kind is not None:
            recognized.append(skills_dir.resolve())
            occupied.append(skills_dir.resolve())
    if len(set(occupied)) > 1:
        raise InstallError("conflito ambíguo: múltiplas instalações ativas")
    if override_raw:
        override = Path(override_raw)
        if not override.is_absolute():
            raise InstallError("CODEX_SKILLS_DIR deve ser caminho absoluto")
        if override.is_symlink():
            raise InstallError("CODEX_SKILLS_DIR não pode ser symlink")
        selected = override.resolve()
        if recognized and recognized[0] != selected:
            raise InstallError(
                "CODEX_SKILLS_DIR conflita com instalação existente identificada"
            )
        return selected
    if recognized:
        return recognized[0]
    return agents.resolve()


def preflight_policy(skills_dir: Path, desired: bytes) -> tuple[Path, Path] | None:
    base = skills_dir / "executar-plano"
    if skills_dir.is_symlink() or base.is_symlink():
        raise InstallError(f"executar-plano não pode usar symlink: {base}")
    if not (base / "SKILL.md").is_file():
        return None
    if not base.is_dir() or base.resolve().parent != skills_dir.resolve():
        raise InstallError(f"executar-plano escapa do diretório de skills: {base}")
    agents = base / "agents"
    if agents.is_symlink():
        raise InstallError(f"agents do executar-plano não pode ser symlink: {agents}")
    destination = agents / "openai.yaml"
    owner = agents / POLICY_OWNER_FILE
    if destination.is_symlink() or owner.is_symlink():
        raise InstallError("configuração Codex do executar-plano não pode ser symlink")
    desired_hash = hashlib.sha256(desired).hexdigest()
    if destination.exists() and destination.read_bytes() != desired:
        if not owner.is_file() or owner.read_text(encoding="utf-8").strip() != digest(destination):
            raise InstallError(
                "agents/openai.yaml do executar-plano é alheio; instalação recusada"
            )
    if owner.exists() and owner.read_text(encoding="utf-8").strip() not in {
        desired_hash,
        digest(destination) if destination.exists() else "",
    }:
        raise InstallError("marker da política Codex não corresponde ao arquivo instalado")
    return destination, owner


def install() -> Path:
    script_dir = Path(__file__).resolve().parent
    source = script_dir / "skills" / "executar-plano-codex"
    policy_source = script_dir / "skills" / "executar-plano" / "agents" / "openai.yaml"
    if not source.is_dir() or not policy_source.is_file():
        raise InstallError("pacote fonte do overlay incompleto")
    source_manifest = files(source)
    home_raw = os.environ.get("HOME")
    if not home_raw:
        raise InstallError("HOME não definido")
    home = Path(home_raw).resolve()
    skills_dir = select_skills_dir(home, set(source_manifest))
    if skills_dir.is_symlink():
        raise InstallError(f"skills dir não pode ser symlink: {skills_dir}")
    skills_dir.mkdir(parents=True, exist_ok=True)
    target = skills_dir / "executar-plano-codex"
    classify(target, set(source_manifest))
    desired_policy = policy_source.read_bytes()
    policy_paths: list[tuple[Path, Path]] = []
    policy_roots: list[Path] = []
    for candidate in (
        skills_dir,
        home / ".agents" / "skills",
        home / ".codex" / "skills",
    ):
        if candidate.is_symlink():
            raise InstallError(f"skills dir não pode ser symlink: {candidate}")
        resolved_candidate = candidate.resolve()
        if resolved_candidate in policy_roots:
            continue
        policy_roots.append(resolved_candidate)
        policy = preflight_policy(resolved_candidate, desired_policy)
        if policy is not None:
            policy_paths.append(policy)

    stage = Path(
        tempfile.mkdtemp(prefix=".executar-plano-codex.stage.", dir=skills_dir)
    )
    backup: Path | None = None
    old_policies: dict[tuple[Path, Path], tuple[bytes | None, bytes | None]] = {}
    installed = False
    try:
        shutil.copytree(source, stage, dirs_exist_ok=True)
        manifest = files(stage)
        (stage / OWNER_FILE).write_text(
            json.dumps({"owner": OWNER, "version": 1}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (stage / MANIFEST_FILE).write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        fsync_tree(stage)
        if target.exists():
            backup = Path(
                tempfile.mkdtemp(prefix=".executar-plano-codex.backup.", dir=skills_dir)
            )
            backup.rmdir()
            os.replace(target, backup)
        os.replace(stage, target)
        installed = True
        for destination, owner in policy_paths:
            old_policy = destination.read_bytes() if destination.exists() else None
            old_policy_owner = owner.read_bytes() if owner.exists() else None
            old_policies[(destination, owner)] = (old_policy, old_policy_owner)
            atomic_write(destination, desired_policy)
            atomic_write(
                owner, (hashlib.sha256(desired_policy).hexdigest() + "\n").encode("utf-8")
            )
        directory_descriptor = os.open(skills_dir, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        for destination, owner in reversed(list(old_policies)):
            old_policy, old_policy_owner = old_policies[(destination, owner)]
            if old_policy is not None:
                atomic_write(destination, old_policy)
            elif destination.exists():
                destination.unlink()
            if old_policy_owner is not None:
                atomic_write(owner, old_policy_owner)
            elif owner.exists():
                owner.unlink()
        if installed and target.exists():
            shutil.rmtree(target)
        if backup is not None and backup.exists():
            os.replace(backup, target)
        raise
    finally:
        if stage.exists():
            shutil.rmtree(stage)
        if backup is not None and backup.exists():
            shutil.rmtree(backup)
    return target


def main() -> int:
    try:
        target = install()
    except InstallError as error:
        print(f"erro: {error}", file=sys.stderr)
        return 2
    print(f"Instalado em {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
