#!/usr/bin/env python3
"""Atualização determinística e atômica do Bianchini Method."""

from __future__ import annotations

import io
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Callable


OFFICIAL_REPOSITORY = "felipebianchini2006/bianchini-method"
OFFICIAL_BRANCH = "main"
MAX_VERSION_BYTES = 128
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MANAGED_SKILL_DIRS = (
    "_shared",
    "design-projeto",
    "sdd-planning",
    "executar-plano",
    "executar-direto",
    "auditar-arquitetura",
    "status-projeto",
    "corrigir-bug",
    "homologar-sistema",
    "update-bm",
)


class UpdateError(RuntimeError):
    """Falha segura durante consulta ou atualização."""

    def __init__(self, message: str, exit_code: int = 2):
        super().__init__(message)
        self.exit_code = exit_code


def parse_version(value: str) -> tuple[int, int, int]:
    text = value.strip()
    match = re.fullmatch(r"([0-9]+)\.([0-9]+)\.([0-9]+)", text)
    if not match:
        raise UpdateError(f"versão inválida: {text or '<vazia>'}")
    return tuple(int(part) for part in match.groups())


def version_urls(
    repository: str = OFFICIAL_REPOSITORY,
    branch: str = OFFICIAL_BRANCH,
) -> tuple[str, str]:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise UpdateError("repositório de atualização inválido")
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", branch) or ".." in branch:
        raise UpdateError("branch de atualização inválida")
    version = (
        f"https://raw.githubusercontent.com/{repository}/{branch}/"
        "skills/_shared/VERSION"
    )
    archive = f"https://codeload.github.com/{repository}/tar.gz/refs/heads/{branch}"
    return version, archive


def _default_fetch_bytes(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Bianchini-Method-Updater/1"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read(MAX_ARCHIVE_BYTES + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as error:
        raise UpdateError(f"não foi possível consultar a atualização: {error}") from error


def _fetch_limited(
    fetch_bytes: Callable[[str, float], bytes],
    url: str,
    timeout: float,
    limit: int,
    label: str,
) -> bytes:
    try:
        content = fetch_bytes(url, timeout)
    except UpdateError:
        raise
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as error:
        raise UpdateError(f"não foi possível baixar {label}: {error}") from error
    if not isinstance(content, bytes):
        raise UpdateError(f"{label} retornou conteúdo inválido")
    if len(content) > limit:
        raise UpdateError(f"{label} excede o limite seguro de tamanho")
    return content


def read_installed_version(skills_root: Path) -> str:
    version_file = skills_root / "_shared" / "VERSION"
    if not version_file.is_file() or version_file.is_symlink():
        return "0.0.0"
    try:
        value = version_file.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as error:
        raise UpdateError(f"não foi possível ler a versão instalada: {error}") from error
    parse_version(value)
    return value


def _run_git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or "comando Git falhou"
        raise UpdateError(message, 3)
    return completed


def _git_root(skills_root: Path) -> Path | None:
    completed = _run_git(
        skills_root,
        "rev-parse",
        "--show-toplevel",
        check=False,
    )
    if completed.returncode != 0:
        return None
    root = Path(completed.stdout.strip()).resolve()
    expected = (root / "skills").resolve()
    return root if expected == skills_root.resolve() else None


def _base_result(
    *,
    installed: str,
    latest: str,
    skills_root: Path,
    mode: str,
    status: str,
    updated: bool,
    repository: str,
    branch: str,
    backup: Path | None = None,
) -> dict[str, object]:
    return {
        "installed_version": installed,
        "latest_version": latest,
        "status": status,
        "updated": updated,
        "mode": mode,
        "skills_root": str(skills_root),
        "backup": str(backup) if backup is not None else None,
        "repository": repository,
        "branch": branch,
    }


def _update_git_checkout(
    repo: Path,
    skills_root: Path,
    installed: str,
    latest: str,
    repository: str,
    branch: str,
) -> dict[str, object]:
    current_branch = _run_git(repo, "branch", "--show-current").stdout.strip()
    if current_branch != branch:
        raise UpdateError(
            f"checkout Git deve estar na branch {branch}; atual: {current_branch or 'detached'}",
            3,
        )
    dirty = _run_git(
        repo,
        "status",
        "--porcelain=v1",
        "--untracked-files=all",
    ).stdout.strip()
    if dirty:
        raise UpdateError(
            "checkout Git possui alterações locais; commit ou guarde antes de atualizar",
            3,
        )
    _run_git(repo, "fetch", "origin", branch)
    remote_version_result = _run_git(
        repo,
        "show",
        f"origin/{branch}:skills/_shared/VERSION",
    )
    remote_version = remote_version_result.stdout.strip()
    parse_version(remote_version)
    if remote_version != latest:
        raise UpdateError(
            "origin/main não corresponde à versão oficial consultada; atualização recusada",
            3,
        )
    _run_git(repo, "merge", "--ff-only", f"origin/{branch}")
    final_version = read_installed_version(skills_root)
    if final_version != latest:
        raise UpdateError(
            f"Git atualizou, mas a versão final é {final_version}; esperado {latest}",
            3,
        )
    return _base_result(
        installed=installed,
        latest=latest,
        skills_root=skills_root,
        mode="git_checkout",
        status="updated",
        updated=True,
        repository=repository,
        branch=branch,
    )


def _safe_member_path(name: str) -> PurePosixPath:
    if not name or "\\" in name:
        raise UpdateError(f"arquivo inseguro no pacote: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise UpdateError(f"arquivo inseguro no pacote: {name}")
    return path


def _extract_archive(content: bytes, destination: Path) -> Path:
    total = 0
    try:
        archive = tarfile.open(fileobj=io.BytesIO(content), mode="r:gz")
    except (tarfile.TarError, OSError) as error:
        raise UpdateError(f"archive de atualização inválido: {error}") from error
    with archive:
        members = archive.getmembers()
        if not members:
            raise UpdateError("archive de atualização vazio")
        for member in members:
            relative = _safe_member_path(member.name)
            if member.issym() or member.islnk() or member.isdev() or member.isfifo():
                raise UpdateError(f"arquivo inseguro no pacote: {member.name}")
            if not (member.isdir() or member.isfile()):
                raise UpdateError(f"tipo de arquivo não suportado no pacote: {member.name}")
            total += max(member.size, 0)
            if total > MAX_ARCHIVE_BYTES:
                raise UpdateError("conteúdo extraído excede o limite seguro")
            target = destination.joinpath(*relative.parts)
            resolved = target.resolve()
            try:
                resolved.relative_to(destination.resolve())
            except ValueError as error:
                raise UpdateError(f"arquivo inseguro no pacote: {member.name}") from error
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            source = archive.extractfile(member)
            if source is None:
                raise UpdateError(f"arquivo inválido no pacote: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with source, target.open("wb") as output:
                shutil.copyfileobj(source, output)
            target.chmod(member.mode & 0o777 or 0o644)
    candidates = list(destination.glob("*/skills/_shared/VERSION"))
    if len(candidates) != 1:
        raise UpdateError("archive não contém uma única raiz válida do Bianchini Method")
    return candidates[0].parent.parent


def _reject_tree_symlinks(root: Path, label: str) -> None:
    if root.is_symlink() or not root.is_dir():
        raise UpdateError(f"{label} deve ser diretório regular: {root}")
    for path in root.rglob("*"):
        if path.is_symlink():
            raise UpdateError(f"{label} contém symlink: {path}")


def _validate_remote_skills(remote_skills: Path, latest: str) -> None:
    if read_installed_version(remote_skills) != latest:
        raise UpdateError("versão do archive diverge da versão consultada")
    for name in MANAGED_SKILL_DIRS:
        _reject_tree_symlinks(remote_skills / name, f"pacote {name}")


def _unique_backup_path(skills_root: Path, installed: str) -> Path:
    backup_root = skills_root.parent / ".bianchini-method-backups"
    if backup_root.is_symlink():
        raise UpdateError(f"diretório de backup não pode ser symlink: {backup_root}")
    backup_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    candidate = backup_root / f"{stamp}-v{installed}"
    suffix = 1
    while candidate.exists():
        candidate = backup_root / f"{stamp}-v{installed}-{suffix}"
        suffix += 1
    candidate.mkdir()
    return candidate


def _prune_backups(backup: Path, keep: int = 3) -> None:
    siblings = sorted(
        (path for path in backup.parent.iterdir() if path.is_dir() and not path.is_symlink()),
        key=lambda path: path.name,
        reverse=True,
    )
    for old in siblings[keep:]:
        shutil.rmtree(old)


def _install_skills_atomically(
    skills_root: Path,
    remote_skills: Path,
    installed: str,
) -> Path:
    if skills_root.is_symlink() or not skills_root.is_dir():
        raise UpdateError(f"raiz de skills deve ser diretório regular: {skills_root}")
    stage = Path(
        tempfile.mkdtemp(prefix=".bianchini-method-stage.", dir=skills_root.parent)
    )
    backup = _unique_backup_path(skills_root, installed)
    completed: list[tuple[str, bool]] = []
    current_name: str | None = None
    current_old_moved = False
    try:
        for name in MANAGED_SKILL_DIRS:
            shutil.copytree(remote_skills / name, stage / name)
        for name in MANAGED_SKILL_DIRS:
            current_name = name
            current_old_moved = False
            target = skills_root / name
            if target.is_symlink():
                raise UpdateError(f"target gerenciado não pode ser symlink: {target}")
            if target.exists() and not target.is_dir():
                raise UpdateError(f"target gerenciado não é diretório: {target}")
            if target.exists():
                os.replace(target, backup / name)
                current_old_moved = True
            os.replace(stage / name, target)
            completed.append((name, current_old_moved))
            current_name = None
            current_old_moved = False
    except BaseException as error:
        rollback_errors: list[str] = []
        if current_name is not None and current_old_moved:
            try:
                target = skills_root / current_name
                if target.exists():
                    shutil.rmtree(target)
                os.replace(backup / current_name, target)
            except BaseException as rollback_error:
                rollback_errors.append(f"{current_name}: {rollback_error}")
        for name, had_old in reversed(completed):
            try:
                target = skills_root / name
                if target.exists():
                    shutil.rmtree(target)
                if had_old and (backup / name).exists():
                    os.replace(backup / name, target)
            except BaseException as rollback_error:
                rollback_errors.append(f"{name}: {rollback_error}")
        detail = "rollback concluído"
        if rollback_errors:
            detail = "rollback incompleto: " + "; ".join(rollback_errors)
        raise UpdateError(f"falha na atualização; {detail}; causa: {error}", 3) from error
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    _prune_backups(backup)
    return backup


def update_bianchini_method(
    *,
    skills_root: Path,
    check_only: bool = False,
    fetch_bytes: Callable[[str, float], bytes] | None = None,
    repository: str = OFFICIAL_REPOSITORY,
    branch: str = OFFICIAL_BRANCH,
    timeout: float = 15.0,
) -> dict[str, object]:
    if timeout <= 0:
        raise UpdateError("timeout deve ser positivo")
    root = skills_root.expanduser().resolve()
    if not root.is_dir() or root.is_symlink():
        raise UpdateError(f"raiz de skills não encontrada ou insegura: {root}")
    installed = read_installed_version(root)
    installed_tuple = parse_version(installed)
    version_url, archive_url = version_urls(repository, branch)
    fetch = fetch_bytes or _default_fetch_bytes
    latest_bytes = _fetch_limited(
        fetch,
        version_url,
        timeout,
        MAX_VERSION_BYTES,
        "versão remota",
    )
    try:
        latest = latest_bytes.decode("utf-8").strip()
    except UnicodeError as error:
        raise UpdateError("versão remota não está em UTF-8") from error
    latest_tuple = parse_version(latest)
    git_root = _git_root(root)
    mode = "git_checkout" if git_root is not None else "installed_package"
    if installed_tuple == latest_tuple:
        return _base_result(
            installed=installed,
            latest=latest,
            skills_root=root,
            mode=mode,
            status="up_to_date",
            updated=False,
            repository=repository,
            branch=branch,
        )
    if installed_tuple > latest_tuple:
        return _base_result(
            installed=installed,
            latest=latest,
            skills_root=root,
            mode=mode,
            status="ahead",
            updated=False,
            repository=repository,
            branch=branch,
        )
    if check_only:
        return _base_result(
            installed=installed,
            latest=latest,
            skills_root=root,
            mode=mode,
            status="update_available",
            updated=False,
            repository=repository,
            branch=branch,
        )
    if git_root is not None:
        return _update_git_checkout(
            git_root,
            root,
            installed,
            latest,
            repository,
            branch,
        )
    archive_bytes = _fetch_limited(
        fetch,
        archive_url,
        timeout,
        MAX_ARCHIVE_BYTES,
        "archive oficial",
    )
    extraction = Path(tempfile.mkdtemp(prefix="bianchini-method-download."))
    try:
        remote_skills = _extract_archive(archive_bytes, extraction)
        _validate_remote_skills(remote_skills, latest)
        backup = _install_skills_atomically(root, remote_skills, installed)
    finally:
        if extraction.exists():
            shutil.rmtree(extraction)
    final_version = read_installed_version(root)
    if final_version != latest:
        raise UpdateError(
            f"atualização terminou com versão {final_version}; esperado {latest}",
            3,
        )
    return _base_result(
        installed=installed,
        latest=latest,
        skills_root=root,
        mode="installed_package",
        status="updated",
        updated=True,
        repository=repository,
        branch=branch,
        backup=backup,
    )


def render_update_result(result: dict[str, object]) -> str:
    installed = result["installed_version"]
    latest = result["latest_version"]
    status = result["status"]
    if status == "up_to_date":
        return f"Bianchini Method já está atualizado na versão {installed}.\n"
    if status == "ahead":
        return (
            f"Versão instalada {installed} é mais nova que a versão oficial {latest}; "
            "nenhuma alteração foi feita.\n"
        )
    if status == "update_available":
        return f"Atualização disponível: {installed} -> {latest}.\n"
    if status == "updated":
        backup = result.get("backup")
        suffix = f" Backup: {backup}." if backup else ""
        return f"Bianchini Method atualizado: {installed} -> {latest}.{suffix}\n"
    return f"Estado de atualização desconhecido: {status}.\n"
