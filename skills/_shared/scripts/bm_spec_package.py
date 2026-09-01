#!/usr/bin/env python3
"""Validação determinística do pacote de specs do COHERENCE schema 2."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping


SPEC_CONTRACT_VERSION = 1
MANIFEST_SCHEMA_VERSION = 1
TRACEABLE_SCOPE_PREFIXES = frozenset(
    {"FLW", "REQ", "NFR", "BR", "DAT", "INT", "ERR", "RSK"}
)
MANDATORY_SPEC_PREFIXES = frozenset(
    {"FLW", "REQ", "NFR", "BR", "DAT", "INT", "ERR"}
)
SCOPE_ITEM = re.compile(r"(?m)^### ([A-Z]+-[0-9]{3})\b")
SPEC_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
REQUIREMENT_IDENTIFIER = re.compile(r"^[A-Z][A-Z0-9_-]*-[0-9]{3,}$")
REQUIREMENT_HEADING = re.compile(
    r"(?m)^(#{2,6})\s+\[?([A-Z][A-Z0-9_-]*-[0-9]{3,})\]?"
    r"(?:\s*[:—-]\s*|\s+)([^\n]+)$"
)
TOP_LEVEL_KEYS = frozenset({"schema_version", "spec_contract", "specs", "risk_coverage"})
SPEC_KEYS = frozenset({"id", "path", "requirements"})
REQUIREMENT_KEYS = frozenset({"id", "scope"})
RISK_KEYS = frozenset({"scope", "kind", "target"})
RISK_KINDS = frozenset({"spec", "guard", "plan_gate"})


class SpecPackageError(ValueError):
    """Falha fechada com código estável para o coordenador do CLI."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def _fail(code: str, message: str) -> None:
    raise SpecPackageError(code, message)


def _exact_int(value: Any, expected: int) -> bool:
    return type(value) is int and value == expected


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _stable_digest(value: Any) -> str:
    return _sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    )


def _unknown_keys(value: Mapping[str, Any], allowed: frozenset[str]) -> list[str]:
    return sorted(set(value) - allowed)


def reject_foreign_namespace(path: Path, label: str) -> None:
    """Rejeita o namespace estrangeiro só pela forma do path, antes de I/O."""

    if any(part.casefold() == ".planning" for part in path.parts):
        _fail("SPEC_PATH_INVALID", f"{label} usa namespace estrangeiro")


def confined_no_symlink(root: Path, path: Path, label: str) -> Path:
    """Confina lexical e fisicamente, rejeitando symlink abaixo da raiz confiável."""

    reject_foreign_namespace(path, label)
    if ".." in path.parts:
        _fail("SPEC_PATH_INVALID", f"{label} contém traversal")
    trusted = root.absolute()
    candidate = path.absolute() if path.is_absolute() else (trusted / path).absolute()
    try:
        relative = candidate.relative_to(trusted)
    except ValueError as error:
        _fail("SPEC_PATH_INVALID", f"{label} fora da raiz confiável")
        raise AssertionError from error
    cursor = trusted
    if cursor.is_symlink():
        _fail("SPEC_SYMLINK", f"raiz confiável não pode ser symlink: {cursor}")
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            _fail("SPEC_SYMLINK", f"symlink ancestral não permitido: {cursor}")
    resolved_root = trusted.resolve()
    resolved_candidate = candidate.resolve()
    try:
        resolved_relative = resolved_candidate.relative_to(resolved_root)
    except ValueError as error:
        _fail("SPEC_PATH_INVALID", f"{label} escapou da raiz confiável")
        raise AssertionError from error
    reject_foreign_namespace(resolved_relative, label)
    return candidate


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        _fail("SPEC_MANIFEST_INVALID", f"{label} deve ser objeto")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        _fail("SPEC_MANIFEST_INVALID", f"{label} deve ser lista")
    return value


def validate_spec_path(value: Any, label: str = "spec path") -> str:
    """Valida um path POSIX relativo sem resolver nem tocar no namespace indicado."""

    if not isinstance(value, str) or not value:
        _fail("SPEC_PATH_INVALID", f"{label} vazio")
    if "\\" in value:
        _fail("SPEC_PATH_INVALID", f"{label} contém barra invertida: {value}")
    candidate = PurePosixPath(value)
    if candidate.is_absolute():
        _fail("SPEC_PATH_INVALID", f"{label} absoluto: {value}")
    if value != candidate.as_posix() or value in {".", ".."}:
        _fail("SPEC_PATH_INVALID", f"{label} não está normalizado: {value}")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        _fail("SPEC_PATH_INVALID", f"{label} contém traversal: {value}")
    if any(part.casefold() == ".planning" for part in candidate.parts):
        _fail("SPEC_PATH_INVALID", f"{label} usa namespace estrangeiro: {value}")
    if candidate.suffix != ".md":
        _fail("SPEC_PATH_INVALID", f"{label} deve terminar em .md: {value}")
    if unicodedata.normalize("NFC", value) != value:
        _fail("SPEC_PATH_INVALID", f"{label} não está em NFC: {value}")
    return value


def _collision_key(path: str) -> str:
    return unicodedata.normalize("NFC", path).casefold()


def _validate_path_collisions(paths: Iterable[str], label: str) -> None:
    seen: dict[str, str] = {}
    for path in paths:
        key = _collision_key(path)
        previous = seen.get(key)
        if previous is not None:
            _fail(
                "SPEC_PATH_COLLISION",
                f"colisão de {label} por normalização/case: {previous} e {path}",
            )
        seen[key] = path


def _decode_markdown(content: bytes, path: str) -> str:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        _fail("SPEC_BINARY", f"spec binário ou UTF-8 inválido: {path}")
        raise AssertionError from error
    if not text.strip():
        _fail("SPEC_EMPTY", f"spec vazio: {path}")
    if any(
        unicodedata.category(character) == "Cc" and character not in "\n\r\t"
        for character in text
    ):
        _fail("SPEC_BINARY", f"spec binário contém controle inválido: {path}")
    return text


def parse_spec_requirements(content: str, path: str) -> dict[str, str]:
    matches = list(REQUIREMENT_HEADING.finditer(content))
    if not matches:
        _fail(
            "SPEC_REQUIREMENTS_MISSING",
            f"spec {path} não contém requisito com ID estável em heading",
        )
    headings = list(re.finditer(r"(?m)^(#{1,6})\s+([^\n]+)$", content))
    positions = {match.start(): index for index, match in enumerate(headings)}
    parsed: dict[str, str] = {}
    for match in matches:
        identifier = match.group(2)
        if identifier in parsed:
            _fail("SPEC_REQUIREMENT_DUPLICATE", f"ID duplicado em {path}: {identifier}")
        level = len(match.group(1))
        end = len(content)
        for following in headings[positions[match.start()] + 1 :]:
            if len(following.group(1)) <= level:
                end = following.start()
                break
        parsed[identifier] = re.sub(
            r"[ \t]+$", "", content[match.start() : end].strip(), flags=re.MULTILINE
        )
    return parsed


def inspect_spec_tree(
    directory: Path,
    *,
    trusted_root: Path,
    required: bool,
    allow_root_manifest: bool = False,
) -> dict[str, Any]:
    """Lê uma árvore sem seguir symlinks e produz digest recursivo ordenado."""

    directory = confined_no_symlink(trusted_root, directory, "árvore de specs")
    if directory.is_symlink():
        _fail("SPEC_SYMLINK", f"symlink não permitido: {directory}")
    if not directory.exists():
        if required:
            _fail("SPEC_TARGET_MISSING", f"target de specs ausente: {directory}")
        empty: dict[str, bytes] = {}
        return {
            "files": empty,
            "requirements": {},
            "digest": _stable_digest({}),
        }
    if not directory.is_dir():
        _fail("SPEC_TARGET_INVALID", f"árvore de specs não é diretório: {directory}")

    files: dict[str, bytes] = {}
    requirements: dict[str, dict[str, str]] = {}
    for candidate in sorted(directory.rglob("*"), key=lambda item: item.as_posix()):
        if candidate.is_symlink():
            _fail("SPEC_SYMLINK", f"symlink não permitido: {candidate}")
        relative = candidate.relative_to(directory).as_posix()
        if candidate.is_dir():
            if any(part.casefold() == ".planning" for part in PurePosixPath(relative).parts):
                _fail("SPEC_PATH_INVALID", f"path usa namespace estrangeiro: {relative}")
            continue
        if not candidate.is_file():
            _fail("SPEC_PATH_INVALID", f"entrada de spec inválida: {relative}")
        if allow_root_manifest and relative == "MANIFEST.json":
            files[relative] = candidate.read_bytes()
            continue
        validate_spec_path(relative)
        content = candidate.read_bytes()
        text = _decode_markdown(content, relative)
        files[relative] = content
        requirements[relative] = parse_spec_requirements(text, relative)

    markdown_paths = sorted(requirements)
    _validate_path_collisions(markdown_paths, "path")
    if required and not markdown_paths:
        _fail("SPEC_TARGET_EMPTY", "target de specs não possui Markdown")
    digest_payload = {path: _sha256(files[path]) for path in sorted(files)}
    return {
        "files": files,
        "requirements": requirements,
        "digest": _stable_digest(digest_payload),
    }


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            _fail("SPEC_MANIFEST_INVALID", f"chave JSON duplicada: {key}")
        value[key] = item
    return value


def _read_manifest(path: Path, *, trusted_root: Path) -> tuple[dict[str, Any], bytes]:
    path = confined_no_symlink(trusted_root, path, "MANIFEST.json")
    if path.is_symlink():
        _fail("SPEC_SYMLINK", f"symlink não permitido: {path}")
    if not path.is_file():
        _fail("SPEC_MANIFEST_MISSING", f"MANIFEST.json ausente: {path}")
    content = path.read_bytes()
    try:
        value = json.loads(
            content.decode("utf-8"), object_pairs_hook=_reject_duplicate_json_keys
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail("SPEC_MANIFEST_INVALID", f"MANIFEST.json inválido: {error}")
        raise AssertionError from error
    manifest = _object(value, "MANIFEST.json")
    unknown = _unknown_keys(manifest, TOP_LEVEL_KEYS)
    if unknown:
        _fail("SPEC_MANIFEST_INVALID", f"campos desconhecidos: {', '.join(unknown)}")
    if set(manifest) != TOP_LEVEL_KEYS:
        missing = sorted(TOP_LEVEL_KEYS - set(manifest))
        _fail("SPEC_MANIFEST_INVALID", f"campos ausentes: {', '.join(missing)}")
    if not _exact_int(manifest["schema_version"], MANIFEST_SCHEMA_VERSION):
        _fail("SPEC_MANIFEST_INVALID", "schema_version deve ser 1")
    if not _exact_int(manifest["spec_contract"], SPEC_CONTRACT_VERSION):
        _fail("SPEC_CONTRACT_UNSUPPORTED", "spec_contract deve ser 1")
    _list(manifest["specs"], "specs")
    _list(manifest["risk_coverage"], "risk_coverage")
    return manifest, content


def validate_manifest(path: Path, *, trusted_root: Path) -> dict[str, Any]:
    manifest, content = _read_manifest(path, trusted_root=trusted_root)
    specs: list[dict[str, Any]] = []
    spec_ids: set[str] = set()
    paths: list[str] = []
    requirement_ids: set[str] = set()
    for index, raw_spec in enumerate(manifest["specs"]):
        item = _object(raw_spec, f"specs[{index}]")
        unknown = _unknown_keys(item, SPEC_KEYS)
        if unknown or set(item) != SPEC_KEYS:
            _fail("SPEC_MANIFEST_INVALID", f"shape inválido em specs[{index}]")
        identifier = item["id"]
        if not isinstance(identifier, str) or not SPEC_IDENTIFIER.fullmatch(identifier):
            _fail("SPEC_MANIFEST_INVALID", f"spec id inválido: {identifier}")
        if identifier in spec_ids:
            _fail("SPEC_ID_DUPLICATE", f"spec id duplicado: {identifier}")
        spec_ids.add(identifier)
        spec_path = validate_spec_path(item["path"], f"specs[{index}].path")
        paths.append(spec_path)
        requirements: list[dict[str, Any]] = []
        for requirement_index, raw_requirement in enumerate(
            _list(item["requirements"], f"specs[{index}].requirements")
        ):
            requirement = _object(
                raw_requirement, f"specs[{index}].requirements[{requirement_index}]"
            )
            if _unknown_keys(requirement, REQUIREMENT_KEYS) or set(requirement) != REQUIREMENT_KEYS:
                _fail("SPEC_MANIFEST_INVALID", "shape inválido em requirement")
            requirement_id = requirement["id"]
            if not isinstance(requirement_id, str) or not REQUIREMENT_IDENTIFIER.fullmatch(
                requirement_id
            ):
                _fail("SPEC_MANIFEST_INVALID", f"requirement id inválido: {requirement_id}")
            if requirement_id in requirement_ids:
                _fail(
                    "SPEC_REQUIREMENT_DUPLICATE",
                    f"requirement duplicado no manifesto: {requirement_id}",
                )
            requirement_ids.add(requirement_id)
            scope = _list(requirement["scope"], f"scope de {requirement_id}")
            if not scope:
                _fail("SPEC_COVERAGE_EMPTY", f"scope vazio em {requirement_id}")
            if any(not isinstance(value, str) or not value for value in scope):
                _fail("SPEC_MANIFEST_INVALID", f"scope inválido em {requirement_id}")
            if len(scope) != len(set(scope)):
                _fail("SPEC_MANIFEST_INVALID", f"scope duplicado em {requirement_id}")
            requirements.append({"id": requirement_id, "scope": list(scope)})
        specs.append(
            {"id": identifier, "path": spec_path, "requirements": requirements}
        )

    _validate_path_collisions(paths, "path")
    if paths != sorted(paths):
        _fail("SPEC_MANIFEST_INVALID", "paths de specs devem estar em ordem POSIX")
    risks: list[dict[str, str]] = []
    seen_risks: set[tuple[str, str, str]] = set()
    for index, raw_risk in enumerate(manifest["risk_coverage"]):
        risk = _object(raw_risk, f"risk_coverage[{index}]")
        if _unknown_keys(risk, RISK_KEYS) or set(risk) != RISK_KEYS:
            _fail("SPEC_MANIFEST_INVALID", f"shape inválido em risk_coverage[{index}]")
        scope_id, kind, target = risk["scope"], risk["kind"], risk["target"]
        if not all(isinstance(value, str) and value for value in (scope_id, kind, target)):
            _fail("SPEC_MANIFEST_INVALID", f"risk_coverage[{index}] inválido")
        if kind not in RISK_KINDS:
            _fail("SPEC_MANIFEST_INVALID", f"kind de risco inválido: {kind}")
        identity = (scope_id, kind, target)
        if identity in seen_risks:
            _fail("SPEC_MANIFEST_INVALID", f"risk_coverage duplicada: {scope_id}")
        seen_risks.add(identity)
        risks.append({"scope": scope_id, "kind": kind, "target": target})
    return {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "spec_contract": SPEC_CONTRACT_VERSION,
        "specs": specs,
        "risk_coverage": risks,
        "digest": _sha256(content),
    }


def _manifest_by_id(manifest: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in manifest["specs"]}


def derive_directory_diff(
    *,
    root: Path,
    base: Path,
    target: Path,
    manifest_path: Path,
    target_tree: Mapping[str, Any] | None = None,
    target_manifest: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    """Deriva add/modify/remove/rename sem escrever a projeção."""

    base_tree = inspect_spec_tree(
        base, trusted_root=root, required=False, allow_root_manifest=True
    )
    if target_tree is None:
        target_tree = inspect_spec_tree(target, trusted_root=root, required=True)
    if target_manifest is None:
        target_manifest = validate_manifest(manifest_path, trusted_root=root)
    target_paths = [item["path"] for item in target_manifest["specs"]]
    if target_paths != sorted(target_tree["requirements"]):
        _fail(
            "SPEC_MANIFEST_MISMATCH",
            "paths do manifesto não correspondem exatamente ao target",
        )

    base_manifest_path = base / "MANIFEST.json"
    if base_tree["requirements"] and not base_manifest_path.is_file():
        _fail(
            "SPEC_BASE_MANIFEST_MISSING",
            "base gerenciada possui specs sem MANIFEST.json",
        )
    if base_manifest_path.is_file():
        base_manifest = validate_manifest(base_manifest_path, trusted_root=root)
        base_paths = [item["path"] for item in base_manifest["specs"]]
        if base_paths != sorted(base_tree["requirements"]):
            _fail(
                "SPEC_BASE_MANIFEST_MISMATCH",
                "paths do manifesto da base não correspondem às specs aceitas",
            )
    else:
        base_manifest = {
            "schema_version": 1,
            "spec_contract": 1,
            "specs": [],
            "risk_coverage": [],
            "digest": None,
        }

    _validate_target_requirements(target_manifest, target_tree)
    if base_manifest["specs"]:
        _validate_target_requirements(base_manifest, base_tree)

    current = _manifest_by_id(base_manifest)
    future = _manifest_by_id(target_manifest)
    added = [
        {"id": identifier, "path": future[identifier]["path"]}
        for identifier in sorted(set(future) - set(current))
    ]
    removed = [
        {"id": identifier, "path": current[identifier]["path"]}
        for identifier in sorted(set(current) - set(future))
    ]
    renamed = [
        {
            "id": identifier,
            "from": current[identifier]["path"],
            "to": future[identifier]["path"],
        }
        for identifier in sorted(set(current) & set(future))
        if current[identifier]["path"] != future[identifier]["path"]
    ]
    modified = []
    for identifier in sorted(set(current) & set(future)):
        previous_path = current[identifier]["path"]
        next_path = future[identifier]["path"]
        if base_tree["files"][previous_path] != target_tree["files"][next_path]:
            modified.append({"id": identifier, "path": next_path})

    metadata = {
        "schema_version": 1,
        "spec_contract": 1,
        "mode": "directory",
        "base_digest": base_tree["digest"],
        "target_digest": target_tree["digest"],
        "base_manifest_digest": base_manifest["digest"],
        "target_manifest_digest": target_manifest["digest"],
        "added": added,
        "modified": modified,
        "removed": removed,
        "renamed": renamed,
    }
    lines = [
        "# Spec Diff",
        "",
        "Esta é uma projeção derivada. O target completo e o MANIFEST são a fonte de verdade.",
        "",
        "```json",
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True),
        "```",
    ]
    for title, items in (
        ("ADDED", added),
        ("MODIFIED", modified),
        ("REMOVED", removed),
        ("RENAMED", renamed),
    ):
        lines.extend(("", f"## {title}", ""))
        if not items:
            lines.append("Nenhum.")
            continue
        for item in items:
            if title == "RENAMED":
                lines.append(f"- `{item['id']}`: `{item['from']}` -> `{item['to']}`")
            else:
                lines.append(f"- `{item['id']}`: `{item['path']}`")
    return metadata, "\n".join(lines).rstrip() + "\n"


def _scope_identifiers(scope_path: Path, *, trusted_root: Path) -> list[str]:
    scope_path = confined_no_symlink(trusted_root, scope_path, "SCOPE.md")
    if scope_path.is_symlink() or not scope_path.is_file():
        _fail("SPEC_SCOPE_MISSING", f"SCOPE.md ausente ou symlink: {scope_path}")
    try:
        text = scope_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        _fail("SPEC_SCOPE_INVALID", "SCOPE.md não é UTF-8")
        raise AssertionError from error
    identifiers: list[str] = []
    for identifier in SCOPE_ITEM.findall(text):
        if identifier.split("-", 1)[0] in TRACEABLE_SCOPE_PREFIXES:
            if identifier in identifiers:
                _fail("SPEC_SCOPE_INVALID", f"ID duplicado no SCOPE.md: {identifier}")
            identifiers.append(identifier)
    if not identifiers:
        _fail("SPEC_SCOPE_INVALID", "SCOPE.md sem IDs rastreáveis")
    return identifiers


def _validate_target_requirements(
    manifest: Mapping[str, Any], target_tree: Mapping[str, Any]
) -> None:
    parsed_global: set[str] = set()
    for item in manifest["specs"]:
        parsed = target_tree["requirements"][item["path"]]
        for requirement_id in parsed:
            if requirement_id in parsed_global:
                _fail(
                    "SPEC_REQUIREMENT_DUPLICATE",
                    f"requirement duplicado no target: {requirement_id}",
                )
            parsed_global.add(requirement_id)
        declared = {requirement["id"] for requirement in item["requirements"]}
        if declared != set(parsed):
            missing = sorted(set(parsed) - declared)
            unknown = sorted(declared - set(parsed))
            details = []
            if missing:
                details.append(f"sem manifesto: {', '.join(missing)}")
            if unknown:
                details.append(f"inexistente na spec: {', '.join(unknown)}")
            _fail(
                "SPEC_REQUIREMENT_MISMATCH",
                f"requirements de {item['path']} divergem ({'; '.join(details)})",
            )


def _coverage(
    manifest: Mapping[str, Any], scope_ids: list[str]
) -> dict[str, list[str]]:
    scope_set = set(scope_ids)
    spec_targets = {
        item["id"] for item in manifest["specs"]
    } | {
        requirement["id"]
        for item in manifest["specs"]
        for requirement in item["requirements"]
    }
    coverage: dict[str, list[str]] = {identifier: [] for identifier in scope_ids}
    for spec_item in manifest["specs"]:
        for requirement in spec_item["requirements"]:
            for scope_id in requirement["scope"]:
                if scope_id not in scope_set:
                    _fail(
                        "SPEC_SCOPE_UNKNOWN",
                        f"ID de cobertura inexistente no SCOPE.md: {scope_id}",
                    )
                coverage[scope_id].append(f"spec:{requirement['id']}")
    for risk in manifest["risk_coverage"]:
        scope_id = risk["scope"]
        if scope_id not in scope_set:
            _fail(
                "SPEC_SCOPE_UNKNOWN",
                f"ID de risco inexistente no SCOPE.md: {scope_id}",
            )
        if not scope_id.startswith("RSK-"):
            _fail(
                "SPEC_RISK_INVALID",
                f"risk_coverage só aceita IDs RSK: {scope_id}",
            )
        if risk["kind"] == "spec" and risk["target"] not in spec_targets:
            _fail(
                "SPEC_RISK_TARGET_UNKNOWN",
                f"target de spec inexistente: {risk['target']}",
            )
        coverage[scope_id].append(f"{risk['kind']}:{risk['target']}")
    missing = [
        identifier
        for identifier in scope_ids
        if identifier.split("-", 1)[0] in MANDATORY_SPEC_PREFIXES
        and not coverage[identifier]
    ]
    missing.extend(
        identifier
        for identifier in scope_ids
        if identifier.startswith("RSK-") and not coverage[identifier]
    )
    if missing:
        _fail(
            "SPEC_COVERAGE_INCOMPLETE",
            f"cobertura SCOPE -> spec incompleta: {', '.join(missing)}",
        )
    return {
        identifier: sorted(set(destinations))
        for identifier, destinations in coverage.items()
    }


def load_spec_package(
    *,
    change_dir: Path,
    current_specs: Path,
    scope_path: Path,
    coherence: Mapping[str, Any],
) -> dict[str, Any]:
    """Carrega schema 2; schema 1 retorna legado sem acessar paths de specs."""

    schema_version = coherence.get("schema_version", 1)
    if _exact_int(schema_version, 1):
        return {
            "managed": False,
            "schema_version": 1,
            "specs_status": "legacy_unmanaged",
            "specs_promoted": False,
        }
    if not _exact_int(schema_version, 2):
        _fail("SPEC_SCHEMA_UNSUPPORTED", f"schema_version inválido: {schema_version}")
    if not _exact_int(coherence.get("spec_contract"), SPEC_CONTRACT_VERSION):
        _fail(
            "SPEC_CONTRACT_UNSUPPORTED",
            "COHERENCE schema 2 exige spec_contract: 1",
        )

    reject_foreign_namespace(change_dir, "change")
    reject_foreign_namespace(current_specs, "base de specs")
    reject_foreign_namespace(scope_path, "SCOPE.md")

    specs_dir = change_dir / "specs"
    expected = specs_dir / "expected"
    manifest_path = specs_dir / "MANIFEST.json"
    diff_path = specs_dir / "diff.md"
    absolute_change = change_dir.absolute()
    if (
        absolute_change.parent.name != "changes"
        or absolute_change.parent.parent.name != ".bianchini"
    ):
        _fail(
            "SPEC_PATH_INVALID",
            "change_dir deve seguir .bianchini/changes/<change>",
        )
    repository = absolute_change.parent.parent.parent
    expected_current = repository / ".bianchini" / "current" / "specs"
    if current_specs.absolute() != expected_current:
        _fail("SPEC_PATH_INVALID", "base de specs não é current/specs")
    if scope_path.absolute() != absolute_change / "SCOPE.md":
        _fail("SPEC_PATH_INVALID", "SCOPE.md não pertence ao change")
    for label, path in (
        ("change", change_dir),
        ("specs", specs_dir),
        ("target", expected),
        ("base", current_specs),
    ):
        if path.is_symlink():
            _fail("SPEC_SYMLINK", f"symlink não permitido em {label}: {path}")
        confined_no_symlink(repository, path, label)
    target_tree = inspect_spec_tree(
        expected, trusted_root=repository, required=True
    )
    manifest = validate_manifest(manifest_path, trusted_root=repository)
    if [item["path"] for item in manifest["specs"]] != sorted(
        target_tree["requirements"]
    ):
        _fail(
            "SPEC_MANIFEST_MISMATCH",
            "paths do manifesto não correspondem exatamente ao target",
        )
    _validate_target_requirements(manifest, target_tree)
    scope_ids = _scope_identifiers(scope_path, trusted_root=repository)
    scope_coverage = _coverage(manifest, scope_ids)
    diff, rendered = derive_directory_diff(
        root=repository,
        base=current_specs,
        target=expected,
        manifest_path=manifest_path,
        target_tree=target_tree,
        target_manifest=manifest,
    )
    diff_path = confined_no_symlink(repository, diff_path, "diff.md")
    if diff_path.is_symlink() or not diff_path.is_file():
        _fail(
            "SPEC_DIFF_STALE",
            "diff.md ausente; regenere com bm spec-diff antes do check",
        )
    actual_diff = diff_path.read_bytes()
    expected_diff = rendered.encode("utf-8")
    if actual_diff != expected_diff:
        _fail(
            "SPEC_DIFF_STALE",
            "diff.md divergiu da projeção; regenere com bm spec-diff",
        )
    return {
        "managed": True,
        "schema_version": 2,
        "planning_contract": coherence.get("planning_contract", 1),
        "spec_contract": SPEC_CONTRACT_VERSION,
        "specs_status": "managed",
        "specs_promoted": False,
        "base_digest": diff["base_digest"],
        "target_digest": diff["target_digest"],
        "manifest_digest": manifest["digest"],
        "diff_digest": _sha256(actual_diff),
        "requirements": sorted(
            requirement["id"]
            for item in manifest["specs"]
            for requirement in item["requirements"]
        ),
        "risk_coverage": list(manifest["risk_coverage"]),
        "scope_coverage": scope_coverage,
        "diff": diff,
    }


validate_spec_package = load_spec_package
