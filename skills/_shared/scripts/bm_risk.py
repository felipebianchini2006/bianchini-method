#!/usr/bin/env python3
"""Piso estrutural e explicável de risco para quick/direct."""

from __future__ import annotations

import unicodedata
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from bm_project_model import ProjectModel


RISK_CONTRACT = "quick-risk-floor-v1"
MAX_SCORE = 10
PROTECTED_THRESHOLD = 3
DIMENSION_FLAGS = frozenset(
    {"scope", "external_effect", "migration", "concurrency", "money"}
)
BOOLEAN_FLAGS = frozenset(
    {
        "payment",
        "webhook",
        "irreversible",
        "multiple_objectives",
        "destructive_migration",
        "uncontrolled_concurrency",
        "undefined_ownership",
        "ambiguous_financial_rule",
        "new_material_architecture",
        "contract_change",
        "integration_change",
        "dependency_change",
    }
)
ALLOWED_FLAGS = DIMENSION_FLAGS | BOOLEAN_FLAGS
DEPENDENCY_MANIFESTS = frozenset(
    {
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
        "pyproject.toml",
        "poetry.lock",
        "requirements.txt",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "go.mod",
        "go.sum",
        "cargo.toml",
        "cargo.lock",
        "gemfile",
        "gemfile.lock",
        "composer.json",
        "composer.lock",
    }
)
IGNORED_DOMAIN_ROOTS = frozenset(
    {"doc", "docs", "note", "notes", "test", "tests", "example", "examples", "fixtures"}
)
PAYMENT_DIRECTORIES = frozenset(
    {"billing", "ledger", "money", "payment", "payments", "financial"}
)
WEBHOOK_DIRECTORIES = frozenset({"webhook", "webhooks"})
MIGRATION_DIRECTORIES = frozenset({"migration", "migrations", "migrate"})
CONTRACT_DIRECTORIES = frozenset({"contract", "contracts", "schema", "schemas"})
CONTRACT_SUFFIXES = frozenset({".proto", ".graphql", ".gql", ".avsc"})
CONTRACT_FILENAMES = frozenset(
    {
        "openapi.json",
        "openapi.yaml",
        "openapi.yml",
        "swagger.json",
        "swagger.yaml",
        "swagger.yml",
    }
)
STRUCTURED_KIND_FIELDS = (
    "kind",
    "domain",
    "category",
    "effect_type",
    "integration_type",
    "contract_type",
)


class RiskInputError(ValueError):
    """Entrada estrutural inválida para o cálculo de risco."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code


def _fail(code: str, message: str) -> None:
    raise RiskInputError(code, message)


def _validate_score(value: Any) -> int:
    if type(value) is not int or not 0 <= value <= MAX_SCORE:
        _fail("RISK_SCORE_INVALID", "declared_score deve estar entre 0 e 10")
    return value


def _validate_path(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value:
        _fail("RISK_PATH_INVALID", f"{label} vazio")
    if "\\" in value:
        _fail("RISK_PATH_INVALID", f"{label} contém barra invertida: {value}")
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or value != candidate.as_posix():
        _fail("RISK_PATH_INVALID", f"{label} deve ser POSIX relativo: {value}")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        _fail("RISK_PATH_INVALID", f"{label} contém traversal: {value}")
    if any(part.casefold() == ".planning" for part in candidate.parts):
        _fail("RISK_PATH_INVALID", f"{label} usa namespace estrangeiro")
    if unicodedata.normalize("NFC", value) != value:
        _fail("RISK_PATH_INVALID", f"{label} não está em NFC: {value}")
    return value


def _path_values(raw: Iterable[str], label: str) -> tuple[str, ...]:
    if isinstance(raw, (str, bytes, bytearray)):
        _fail("RISK_PATH_INVALID", f"{label} exige coleção de paths")
    try:
        values = tuple(raw)
    except TypeError as error:
        _fail("RISK_PATH_INVALID", f"{label} exige coleção de paths")
        raise AssertionError from error
    return tuple(sorted({_validate_path(value, label) for value in values}))


def _flag_values(raw: Mapping[str, Any] | None) -> dict[str, int | bool]:
    if raw is None:
        return {}
    if not isinstance(raw, Mapping):
        _fail("RISK_FLAGS_INVALID", "flags exige objeto")
    unknown = sorted(set(raw) - ALLOWED_FLAGS)
    if unknown:
        _fail("RISK_FLAGS_INVALID", f"flag desconhecida: {unknown[0]}")
    result: dict[str, int | bool] = {}
    for name in sorted(raw):
        value = raw[name]
        if name in DIMENSION_FLAGS:
            if type(value) is not int or value not in {0, 1, 2}:
                _fail("RISK_FLAGS_INVALID", f"{name} deve estar entre 0 e 2")
            result[name] = value
        else:
            if type(value) is not bool:
                _fail("RISK_FLAGS_INVALID", f"{name} deve ser booleano")
            result[name] = value
    return result


def _coerce_model(value: ProjectModel | Mapping[str, Any], label: str) -> ProjectModel:
    if isinstance(value, ProjectModel):
        return value
    if isinstance(value, Mapping):
        try:
            return ProjectModel.from_mapping(value)
        except ValueError as error:
            _fail("RISK_MODEL_INVALID", f"{label}: {error}")
            raise AssertionError from error
    _fail("RISK_MODEL_INVALID", f"{label} exige ProjectModel ou objeto")
    raise AssertionError


def _migration_values(raw: Iterable[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    if isinstance(raw, (str, bytes, bytearray)):
        _fail("RISK_MIGRATION_INVALID", "migrations exige lista de objetos")
    try:
        values = tuple(raw)
    except TypeError as error:
        _fail("RISK_MIGRATION_INVALID", "migrations exige lista de objetos")
        raise AssertionError from error
    normalized: list[dict[str, Any]] = []
    identifiers: set[str] = set()
    for index, raw_item in enumerate(values):
        if not isinstance(raw_item, Mapping):
            _fail("RISK_MIGRATION_INVALID", f"migrations[{index}] exige objeto")
        item = dict(raw_item)
        identifier = item.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            _fail("RISK_MIGRATION_INVALID", f"migrations[{index}].id é obrigatório")
        identifier = identifier.strip()
        if identifier in identifiers:
            _fail("RISK_MIGRATION_INVALID", f"migration duplicada: {identifier}")
        identifiers.add(identifier)
        item["id"] = identifier
        if "path" in item:
            item["path"] = _validate_path(item["path"], f"migration {identifier}")
        for field in ("destructive", "irreversible", "reversible"):
            if field in item and type(item[field]) is not bool:
                _fail("RISK_MIGRATION_INVALID", f"{identifier}.{field} deve ser booleano")
        normalized.append(item)
    return tuple(sorted(normalized, key=lambda item: item["id"]))


def _guards_for(kind: str) -> set[str]:
    guards = {
        "external_effect": {"official_docs", "timeout_recovery", "rollback", "sandbox"},
        "migration": {"rollback", "backup_restore", "migration_verify"},
        "concurrency": {"idempotency", "deduplication", "replay_order"},
        "money": {
            "source_of_truth",
            "idempotency",
            "persistence",
            "reconciliation",
            "sandbox",
        },
        "payment": {
            "source_of_truth",
            "idempotency",
            "timeout_recovery",
            "persistence",
            "reconciliation",
        },
        "webhook": {"authenticity", "deduplication", "replay_order", "persistence"},
        "contract": {"local_contract", "contract_tests"},
        "integration": {"official_docs", "timeout_recovery", "sandbox"},
        "dependency_manifest": {"dependency_audit", "lockfile_consistency"},
        "ownership": {"owner_approval", "local_contract"},
        "irreversible": {"human_checkpoint", "backup_restore", "rollback"},
        "architecture": {"local_contract", "architecture_review"},
        "multiple_objectives": {"local_contract"},
    }
    return set(guards.get(kind, set()))


def _dimension_floor(name: str, value: int) -> int:
    if not value:
        return 0
    if value == 1:
        return 1
    if name == "scope":
        return 3
    if name == "external_effect":
        return 3
    if name in {"migration", "concurrency", "money"}:
        return 5
    return value


def _boolean_policy(name: str) -> tuple[int, str]:
    policies = {
        "payment": (3, "payment"),
        "webhook": (3, "webhook"),
        "irreversible": (5, "irreversible"),
        "multiple_objectives": (3, "multiple_objectives"),
        "destructive_migration": (5, "migration"),
        "uncontrolled_concurrency": (5, "concurrency"),
        "undefined_ownership": (3, "ownership"),
        "ambiguous_financial_rule": (4, "money"),
        "new_material_architecture": (4, "architecture"),
        "contract_change": (3, "contract"),
        "integration_change": (3, "integration"),
        "dependency_change": (3, "dependency_manifest"),
    }
    return policies[name]


def _path_signals(path: str, source: str) -> list[tuple[int, str, str]]:
    candidate = PurePosixPath(path)
    parts = tuple(part.casefold() for part in candidate.parts)
    directories = parts[:-1]
    basename = parts[-1]
    suffix = candidate.suffix.casefold()
    ignored_domain = bool(parts and parts[0] in IGNORED_DOMAIN_ROOTS)
    signals: list[tuple[int, str, str]] = []

    if any(part in MIGRATION_DIRECTORIES for part in directories):
        signals.append((3, f"{source}:migration:{path}", "migration"))
    if basename in DEPENDENCY_MANIFESTS:
        signals.append(
            (3, f"{source}:dependency_manifest:{path}", "dependency_manifest")
        )
    if (
        any(part in CONTRACT_DIRECTORIES for part in directories)
        or suffix in CONTRACT_SUFFIXES
        or basename in CONTRACT_FILENAMES
    ):
        signals.append((3, f"{source}:contract:{path}", "contract"))
    if not ignored_domain and any(part in PAYMENT_DIRECTORIES for part in directories):
        signals.append((3, f"{source}:payment:{path}", "payment"))
    if not ignored_domain and any(part in WEBHOOK_DIRECTORIES for part in directories):
        signals.append((3, f"{source}:webhook:{path}", "webhook"))
    return signals


def _structured_kinds(entry: Mapping[str, Any]) -> set[str]:
    values: set[str] = set()
    for field in STRUCTURED_KIND_FIELDS:
        value = entry.get(field)
        if isinstance(value, str):
            values.add(value.strip().casefold())
    return values


def _entry_signals(
    section: str, identifier: str, entry: Mapping[str, Any]
) -> list[tuple[int, str, str]]:
    signals: list[tuple[int, str, str]] = []
    kinds = _structured_kinds(entry)
    if kinds & {"money", "financial", "finance"}:
        signals.append((3, f"model:money:{section}:{identifier}", "money"))
    if kinds & {"payment", "payments", "billing"}:
        signals.append((3, f"model:payment:{section}:{identifier}", "payment"))
    if kinds & {"webhook", "event_callback"}:
        signals.append((3, f"model:webhook:{section}:{identifier}", "webhook"))
    if kinds & {"concurrency", "concurrent", "queue"}:
        signals.append((3, f"model:concurrency:{section}:{identifier}", "concurrency"))
    if kinds & {"migration", "database_migration", "schema_migration", "destructive_migration"}:
        signals.append((3, f"model:migration:{section}:{identifier}", "migration"))
    if "destructive_migration" in kinds:
        signals.append(
            (5, f"model:destructive_migration:{identifier}", "irreversible")
        )
    irreversible = (
        entry.get("irreversible") is True
        or entry.get("destructive") is True
        or entry.get("reversible") is False
    )
    if irreversible:
        label = "irreversible_effect" if section == "effects" else "irreversible"
        signals.append((5, f"model:{label}:{identifier}", "irreversible"))
    return signals


def _model_signals(
    current: ProjectModel, expected: ProjectModel
) -> list[tuple[int, str, str]]:
    differences = current.differences(expected)
    section_policy = {
        "modules": (2, "architecture"),
        "interfaces": (3, "contract"),
        "capabilities": (2, "contract"),
        "contracts": (3, "contract"),
        "ownership": (3, "ownership"),
        "data": (3, "contract"),
        "integrations": (3, "integration"),
        "journeys": (2, "contract"),
        "invariants": (3, "contract"),
        "effects": (3, "external_effect"),
    }
    signals: list[tuple[int, str, str]] = []
    affected_modules = 0
    for section in sorted(differences):
        floor, guard_kind = section_policy[section]
        current_entries = getattr(current, section)
        expected_entries = getattr(expected, section)
        for operation in ("added", "changed", "removed"):
            for identifier in differences[section][operation]:
                signals.append(
                    (floor, f"model:{section}:{operation}={identifier}", guard_kind)
                )
                entry = (
                    current_entries[identifier]
                    if operation == "removed"
                    else expected_entries[identifier]
                )
                signals.extend(_entry_signals(section, identifier, entry))
                if section == "modules":
                    affected_modules += 1
    if affected_modules > 1:
        signals.append((3, "model:multiple_modules", "architecture"))
    return signals


def _migration_signals(
    migrations: Sequence[Mapping[str, Any]],
) -> list[tuple[int, str, str]]:
    signals: list[tuple[int, str, str]] = []
    for item in migrations:
        identifier = str(item["id"])
        signals.append((3, f"migration:{identifier}", "migration"))
        irreversible = (
            item.get("destructive") is True
            or item.get("irreversible") is True
            or item.get("reversible") is False
        )
        if irreversible:
            signals.append(
                (5, f"migration:irreversible:{identifier}", "irreversible")
            )
    return signals


def assess_quick_risk(
    declared_score: int,
    *,
    flags: Mapping[str, Any] | None = None,
    declared_paths: Iterable[str] = (),
    diff_paths: Iterable[str] = (),
    current_model: ProjectModel | Mapping[str, Any] | None = None,
    expected_model: ProjectModel | Mapping[str, Any] | None = None,
    migrations: Iterable[Mapping[str, Any]] = (),
    phase: str = "start",
) -> dict[str, Any]:
    """Calcula piso estrutural sem alterar a rota humana quick/direct."""

    declared = _validate_score(declared_score)
    if phase not in {"start", "finish"}:
        _fail("RISK_PHASE_INVALID", "phase exige start ou finish")
    structured_flags = _flag_values(flags)
    initial_paths = _path_values(declared_paths, "declared_paths")
    actual_paths = _path_values(diff_paths, "diff_paths")
    migration_values = _migration_values(migrations)
    if (current_model is None) != (expected_model is None):
        _fail("RISK_MODEL_INVALID", "current_model e expected_model são inseparáveis")

    initial_signals: list[tuple[int, str, str]] = []
    dimension_total = sum(
        int(structured_flags.get(name, 0)) for name in DIMENSION_FLAGS
    )
    for name in sorted(structured_flags):
        value = structured_flags[name]
        if not value:
            continue
        if name in DIMENSION_FLAGS:
            floor = _dimension_floor(name, int(value))
            initial_signals.append((floor, f"flag:{name}={value}", name))
        else:
            floor, guard_kind = _boolean_policy(name)
            initial_signals.append((floor, f"flag:{name}=true", guard_kind))
    if dimension_total:
        initial_signals.append(
            (min(MAX_SCORE, dimension_total), f"flags:dimension_total={dimension_total}", "")
        )
    for path in initial_paths:
        initial_signals.extend(_path_signals(path, "declared_path"))
    initial_signals.extend(_migration_signals(migration_values))
    if current_model is not None and expected_model is not None:
        current = _coerce_model(current_model, "current_model")
        expected = _coerce_model(expected_model, "expected_model")
        initial_signals.extend(_model_signals(current, expected))

    diff_signals: list[tuple[int, str, str]] = []
    for path in actual_paths:
        diff_signals.extend(_path_signals(path, "diff_path"))
    initial_floor = min(
        MAX_SCORE, max((floor for floor, _reason, _kind in initial_signals), default=0)
    )
    diff_floor = min(
        MAX_SCORE, max((floor for floor, _reason, _kind in diff_signals), default=0)
    )
    derived_floor = max(initial_floor, diff_floor)
    effective_score = max(declared, derived_floor)

    initial_guards = {
        guard
        for _floor, _reason, kind in initial_signals
        for guard in _guards_for(kind)
    }
    diff_guards = {
        guard
        for _floor, _reason, kind in diff_signals
        for guard in _guards_for(kind)
    }
    reasons = {
        reason for _floor, reason, _kind in initial_signals + diff_signals
    }
    if declared < derived_floor:
        reasons.add(f"declared_below_floor:{declared}<{derived_floor}")
    reclassified = bool(
        phase == "finish"
        and (diff_floor > initial_floor or bool(diff_guards - initial_guards))
    )
    return {
        "schema_version": 1,
        "risk_contract": RISK_CONTRACT,
        "workflow": "quick",
        "phase": phase,
        "declared_score": declared,
        "initial_floor": initial_floor,
        "diff_floor": diff_floor,
        "derived_floor": derived_floor,
        "effective_score": effective_score,
        "route": "protected" if effective_score >= PROTECTED_THRESHOLD else "normal",
        "reclassified": reclassified,
        "reasons": sorted(reasons),
        "additional_guards": sorted(initial_guards | diff_guards),
    }


derive_quick_risk = assess_quick_risk
