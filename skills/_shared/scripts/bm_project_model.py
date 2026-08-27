#!/usr/bin/env python3
"""Modelo tipado e determinístico do sistema planejado pelo Bianchini Method."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


MODEL_SECTIONS = (
    "modules",
    "interfaces",
    "capabilities",
    "contracts",
    "ownership",
    "data",
    "integrations",
    "journeys",
    "invariants",
    "effects",
)
MODEL_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]*$")
PLAN_ID = re.compile(r"^P[0-9]{2,}$")
TASK_ID = re.compile(r"^T[0-9]{2,}$")
PLAN_V2_FIELDS = frozenset(
    {
        "schema_version",
        "id",
        "status",
        "result",
        "requirements",
        "acceptance",
        "depends_on",
        "provides",
        "consumes",
        "modules",
        "interfaces",
        "ownership",
        "data",
        "model_delta",
        "migrations",
        "effects",
        "rollback",
        "verifications",
        "future_constraints",
        "execution",
        "review",
        "tasks",
    }
)
TASK_FIELDS = frozenset(
    {
        "id",
        "name",
        "result",
        "covers",
        "depends_on",
        "files",
        "action",
        "verify",
        "done",
        "risk_seam",
    }
)
EXECUTION_REVIEWS = {
    "grouped": "plan_gate",
    "slice": "per_slice",
    "strict": "per_task",
}


def read_frontmatter(path: str | Path) -> dict[str, Any]:
    """Lê frontmatter JSON ou um subconjunto seguro e suficiente de YAML."""

    source = Path(path)
    if not source.is_file():
        raise ValueError(f"documento ausente: {source}")
    text = source.read_text(encoding="utf-8")
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|\Z)", text, re.DOTALL)
    if match is None:
        raise ValueError(f"frontmatter ausente: {source}")
    raw = match.group(1).strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = _parse_yaml_subset(raw)
    if not isinstance(parsed, dict):
        raise ValueError(f"frontmatter exige objeto: {source}")
    return parsed


@dataclass(frozen=True)
class ProjectModel:
    """Snapshot normalizado do sistema em um ponto da sequência de planos."""

    schema_version: int = 1
    modules: dict[str, dict[str, Any]] = field(default_factory=dict)
    interfaces: dict[str, dict[str, Any]] = field(default_factory=dict)
    capabilities: dict[str, dict[str, Any]] = field(default_factory=dict)
    contracts: dict[str, dict[str, Any]] = field(default_factory=dict)
    ownership: dict[str, dict[str, Any]] = field(default_factory=dict)
    data: dict[str, dict[str, Any]] = field(default_factory=dict)
    integrations: dict[str, dict[str, Any]] = field(default_factory=dict)
    journeys: dict[str, dict[str, Any]] = field(default_factory=dict)
    invariants: dict[str, dict[str, Any]] = field(default_factory=dict)
    effects: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def from_system_model(cls, path: str | Path) -> "ProjectModel":
        return cls.from_mapping(read_frontmatter(path))

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "ProjectModel":
        if not isinstance(mapping, Mapping):
            raise ValueError("ProjectModel exige objeto")
        unknown = sorted(set(mapping) - set(MODEL_SECTIONS) - {"schema_version"})
        if unknown:
            raise ValueError(f"seção desconhecida no ProjectModel: {unknown[0]}")
        schema_version = mapping.get("schema_version", 1)
        if schema_version != 1:
            raise ValueError("ProjectModel exige schema_version 1")
        values = {
            section: _normalize_section(section, mapping.get(section, []))
            for section in MODEL_SECTIONS
        }
        return cls(schema_version=1, **values)

    def to_mapping(self) -> dict[str, Any]:
        result: dict[str, Any] = {"schema_version": self.schema_version}
        for section in MODEL_SECTIONS:
            collection = getattr(self, section)
            result[section] = [copy.deepcopy(collection[key]) for key in sorted(collection)]
        return result

    def digest(self) -> str:
        encoded = json.dumps(
            self.to_mapping(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def to_markdown(self, body: str = "# Modelo do sistema\n") -> str:
        """Renderiza um SYSTEM_MODEL legível e reprocessável sem perda semântica."""

        frontmatter = json.dumps(
            self.to_mapping(), ensure_ascii=False, sort_keys=True, indent=2
        )
        return f"---\n{frontmatter}\n---\n{body.rstrip()}\n"

    def equivalent(self, other: "ProjectModel") -> bool:
        return isinstance(other, ProjectModel) and self.to_mapping() == other.to_mapping()

    def differences(self, other: "ProjectModel") -> dict[str, dict[str, list[str]]]:
        """Retorna diferenças por seção sem depender de ordem textual."""

        differences: dict[str, dict[str, list[str]]] = {}
        for section in MODEL_SECTIONS:
            current = getattr(self, section)
            expected = getattr(other, section)
            added = sorted(set(expected) - set(current))
            removed = sorted(set(current) - set(expected))
            changed = sorted(
                identifier
                for identifier in set(current) & set(expected)
                if current[identifier] != expected[identifier]
            )
            if added or removed or changed:
                differences[section] = {
                    "added": added,
                    "removed": removed,
                    "changed": changed,
                }
        return differences

    def apply_delta(self, delta: Mapping[str, Any] | None) -> "ProjectModel":
        if not delta:
            return self
        if not isinstance(delta, Mapping):
            raise ValueError("model_delta exige objeto")
        unknown = sorted(set(delta) - set(MODEL_SECTIONS))
        if unknown:
            raise ValueError(f"seção desconhecida em model_delta: {unknown[0]}")
        result = self.to_mapping()
        indexed = {
            section: {entry["id"]: entry for entry in result[section]}
            for section in MODEL_SECTIONS
        }
        for section, operations in delta.items():
            target = indexed[section]
            if isinstance(operations, list):
                operation_map: Mapping[str, Any] = {"upsert": operations}
            elif isinstance(operations, Mapping):
                operation_map = operations
            else:
                raise ValueError(f"model_delta.{section} exige lista ou objeto")
            invalid = sorted(set(operation_map) - {"add", "update", "upsert", "remove"})
            if invalid:
                raise ValueError(f"operação desconhecida em model_delta.{section}: {invalid[0]}")
            for raw in _as_sequence(operation_map.get("add", []), f"{section}.add"):
                entry = _normalize_entry(section, raw)
                identifier = entry["id"]
                if identifier in target:
                    raise ValueError(f"{section}.{identifier} já existe")
                target[identifier] = entry
            for raw in _as_sequence(operation_map.get("update", []), f"{section}.update"):
                entry = _normalize_entry(section, raw)
                identifier = entry["id"]
                if identifier not in target:
                    raise ValueError(f"{section}.{identifier} não existe")
                target[identifier] = {**target[identifier], **entry}
            for raw in _as_sequence(operation_map.get("upsert", []), f"{section}.upsert"):
                entry = _normalize_entry(section, raw)
                identifier = entry["id"]
                target[identifier] = {**target.get(identifier, {}), **entry}
            for raw in _as_sequence(operation_map.get("remove", []), f"{section}.remove"):
                identifier = raw.get("id") if isinstance(raw, Mapping) else raw
                if not isinstance(identifier, str) or not identifier:
                    raise ValueError(f"{section}.remove exige IDs")
                if identifier not in target:
                    raise ValueError(f"{section}.{identifier} não existe")
                del target[identifier]
        return ProjectModel.from_mapping(
            {
                section: [indexed[section][key] for key in sorted(indexed[section])]
                for section in MODEL_SECTIONS
            }
        )

    @staticmethod
    def simulate(initial: "ProjectModel", plans: Iterable["PlanContract"]) -> "ProjectModel":
        model = initial
        for plan in plans:
            model = model.apply_delta(plan.model_delta)
        return model

    def component_ids(self) -> set[str]:
        identifiers: set[str] = set()
        for section in MODEL_SECTIONS:
            identifiers.update(getattr(self, section))
        return identifiers


@dataclass(frozen=True)
class TaskVerification:
    kind: str
    run: str
    proves: str

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "TaskVerification":
        if not isinstance(mapping, Mapping):
            raise ValueError("verify exige objeto")
        unknown = sorted(set(mapping) - {"kind", "run", "proves"})
        missing = sorted({"kind", "run", "proves"} - set(mapping))
        if unknown:
            raise ValueError(f"campo desconhecido em verify: {unknown[0]}")
        if missing:
            raise ValueError(f"campo obrigatório ausente em verify: {missing[0]}")
        kind = mapping.get("kind")
        if kind not in {"command", "procedure"}:
            raise ValueError("verify.kind exige command ou procedure")
        run = _required_text(mapping.get("run"), "verify.run")
        proves = _required_text(mapping.get("proves"), "verify.proves")
        return cls(kind=str(kind), run=run, proves=proves)

    def to_mapping(self) -> dict[str, str]:
        return {"kind": self.kind, "run": self.run, "proves": self.proves}


@dataclass(frozen=True)
class TaskContract:
    id: str
    name: str
    result: str
    covers: tuple[str, ...]
    depends_on: tuple[str, ...]
    files: tuple[str, ...]
    action: str
    verification: TaskVerification
    done: str
    risk_seam: str

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "TaskContract":
        if not isinstance(mapping, Mapping):
            raise ValueError("tarefa exige objeto")
        unknown = sorted(set(mapping) - TASK_FIELDS)
        missing = sorted(TASK_FIELDS - set(mapping))
        if unknown:
            raise ValueError(f"campo desconhecido na tarefa: {unknown[0]}")
        if missing:
            raise ValueError(f"campo obrigatório ausente na tarefa: {missing[0]}")
        identifier = _required_text(mapping.get("id"), "tarefa.id")
        files = _string_tuple(mapping.get("files"), f"{identifier}.files")
        if not files:
            raise ValueError(f"{identifier}.files exige ao menos um caminho provável")
        for value in files:
            candidate = Path(value)
            if (
                candidate.is_absolute()
                or "\\" in value
                or ".." in candidate.parts
                or value.startswith("./")
            ):
                raise ValueError(f"{identifier}.files contém caminho inseguro: {value}")
            if candidate.parts and candidate.parts[0] == ".planning":
                raise ValueError(
                    f"{identifier}.files referencia namespace estrangeiro: {value}"
                )
        covers = _string_tuple(mapping.get("covers"), f"{identifier}.covers")
        if not covers:
            raise ValueError(f"{identifier}.covers exige ao menos um item de escopo")
        return cls(
            id=identifier,
            name=_required_text(mapping.get("name"), f"{identifier}.name"),
            result=_required_text(mapping.get("result"), f"{identifier}.result"),
            covers=covers,
            depends_on=_string_tuple(
                mapping.get("depends_on"), f"{identifier}.depends_on"
            ),
            files=files,
            action=_required_text(mapping.get("action"), f"{identifier}.action"),
            verification=TaskVerification.from_mapping(mapping.get("verify", {})),
            done=_required_text(mapping.get("done"), f"{identifier}.done"),
            risk_seam=_required_text(
                mapping.get("risk_seam"), f"{identifier}.risk_seam"
            ),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "result": self.result,
            "covers": list(self.covers),
            "depends_on": list(self.depends_on),
            "files": list(self.files),
            "action": self.action,
            "verify": self.verification.to_mapping(),
            "done": self.done,
            "risk_seam": self.risk_seam,
        }


@dataclass(frozen=True)
class PlanContract:
    """Contrato estrutural mínimo de uma fase/plano."""

    id: str
    schema_version: int = 1
    status: str | None = None
    result: str | None = None
    depends_on: tuple[str, ...] = ()
    provides: tuple[str, ...] = ()
    consumes: tuple[str, ...] = ()
    owns: tuple[str, ...] = ()
    touches: tuple[str, ...] = ()
    requirements: tuple[str, ...] = ()
    acceptance: tuple[str, ...] = ()
    verifications: tuple[str, ...] = ()
    model_delta: dict[str, Any] = field(default_factory=dict)
    migrations: tuple[dict[str, Any], ...] = ()
    external_effects: tuple[dict[str, Any], ...] = ()
    future_constraints: tuple[str, ...] = ()
    modules: tuple[str, ...] = ()
    interfaces: tuple[str, ...] = ()
    data: tuple[str, ...] = ()
    rollback: str | None = None
    execution: str | None = None
    review: str | None = None
    tasks: tuple[TaskContract, ...] = ()

    @classmethod
    def from_markdown(cls, path: str | Path) -> "PlanContract":
        return cls.from_mapping(read_frontmatter(path))

    @classmethod
    def from_mapping(cls, mapping: Mapping[str, Any]) -> "PlanContract":
        if not isinstance(mapping, Mapping):
            raise ValueError("plano exige objeto")
        identifier = mapping.get("id")
        if not isinstance(identifier, str) or not identifier.strip():
            raise ValueError("plano exige id")
        delta = mapping.get("model_delta", {})
        if not isinstance(delta, Mapping):
            raise ValueError(f"plano {identifier}: model_delta exige objeto")
        schema_version = mapping.get("schema_version", 1)
        if schema_version not in {1, 2}:
            raise ValueError(f"plano {identifier}: schema_version exige 1 ou 2")
        if schema_version == 2:
            unknown = sorted(set(mapping) - PLAN_V2_FIELDS)
            missing = sorted(PLAN_V2_FIELDS - set(mapping))
            if unknown:
                raise ValueError(f"campo desconhecido no plano v2: {unknown[0]}")
            if missing:
                raise ValueError(f"campo obrigatório ausente no plano v2: {missing[0]}")
            if mapping.get("status") != "planned":
                raise ValueError(f"plano {identifier}: status exige planned")
            execution = mapping.get("execution")
            review = mapping.get("review")
            if execution not in EXECUTION_REVIEWS:
                raise ValueError(f"plano {identifier}: execution inválido")
            if EXECUTION_REVIEWS[execution] != review:
                raise ValueError(
                    f"plano {identifier}: combinação execution/review incompatível"
                )
            raw_tasks = mapping.get("tasks")
            if not isinstance(raw_tasks, Sequence) or isinstance(
                raw_tasks, (str, bytes, bytearray)
            ):
                raise ValueError(f"plano {identifier}: tasks exige lista")
            tasks = tuple(TaskContract.from_mapping(value) for value in raw_tasks)
            requirements = _string_tuple(
                mapping.get("requirements"), "requirements"
            )
            if not requirements:
                raise ValueError(f"plano {identifier}: requirements não pode ser vazio")
            acceptance = _string_tuple(mapping.get("acceptance"), "acceptance")
            if not acceptance:
                raise ValueError(f"plano {identifier}: acceptance não pode ser vazio")
            verifications = _string_tuple(
                mapping.get("verifications"), "verifications"
            )
            if not verifications:
                raise ValueError(f"plano {identifier}: verifications não pode ser vazio")
            return cls(
                id=identifier.strip(),
                schema_version=2,
                status="planned",
                result=_required_text(mapping.get("result"), f"plano {identifier}.result"),
                depends_on=_string_tuple(mapping.get("depends_on"), "depends_on"),
                provides=_string_tuple(mapping.get("provides"), "provides"),
                consumes=_string_tuple(mapping.get("consumes"), "consumes"),
                owns=_string_tuple(mapping.get("ownership"), "ownership"),
                requirements=requirements,
                acceptance=acceptance,
                verifications=verifications,
                model_delta=copy.deepcopy(dict(delta)),
                migrations=_mapping_tuple(mapping.get("migrations"), "migrations"),
                external_effects=_mapping_tuple(mapping.get("effects"), "effects"),
                future_constraints=_string_tuple(
                    mapping.get("future_constraints"), "future_constraints"
                ),
                modules=_string_tuple(mapping.get("modules"), "modules"),
                interfaces=_string_tuple(mapping.get("interfaces"), "interfaces"),
                data=_string_tuple(mapping.get("data"), "data"),
                rollback=_required_text(
                    mapping.get("rollback"), f"plano {identifier}.rollback"
                ),
                execution=str(execution),
                review=str(review),
                tasks=tasks,
            )
        return cls(
            id=identifier.strip(),
            schema_version=1,
            depends_on=_string_tuple(mapping.get("depends_on", []), "depends_on"),
            provides=_string_tuple(mapping.get("provides", []), "provides"),
            consumes=_string_tuple(mapping.get("consumes", []), "consumes"),
            owns=_string_tuple(mapping.get("owns", mapping.get("ownership", [])), "owns"),
            touches=_string_tuple(mapping.get("touches", []), "touches"),
            requirements=_string_tuple(mapping.get("requirements", []), "requirements"),
            acceptance=_string_tuple(mapping.get("acceptance", []), "acceptance"),
            verifications=_string_tuple(mapping.get("verifications", []), "verifications"),
            model_delta=copy.deepcopy(dict(delta)),
            migrations=_mapping_tuple(mapping.get("migrations", []), "migrations"),
            external_effects=_mapping_tuple(
                mapping.get("external_effects", mapping.get("effects", [])),
                "external_effects",
            ),
            future_constraints=_string_tuple(
                mapping.get("future_constraints", []), "future_constraints"
            ),
        )

    def to_mapping(self) -> dict[str, Any]:
        if self.schema_version == 2:
            return {
                "schema_version": 2,
                "id": self.id,
                "status": self.status,
                "result": self.result,
                "requirements": list(self.requirements),
                "acceptance": list(self.acceptance),
                "depends_on": list(self.depends_on),
                "provides": list(self.provides),
                "consumes": list(self.consumes),
                "modules": list(self.modules),
                "interfaces": list(self.interfaces),
                "ownership": list(self.owns),
                "data": list(self.data),
                "model_delta": copy.deepcopy(self.model_delta),
                "migrations": [copy.deepcopy(value) for value in self.migrations],
                "effects": [copy.deepcopy(value) for value in self.external_effects],
                "rollback": self.rollback,
                "verifications": list(self.verifications),
                "future_constraints": list(self.future_constraints),
                "execution": self.execution,
                "review": self.review,
                "tasks": [task.to_mapping() for task in self.tasks],
            }
        return {
            "id": self.id,
            "depends_on": list(self.depends_on),
            "provides": list(self.provides),
            "consumes": list(self.consumes),
            "owns": list(self.owns),
            "touches": list(self.touches),
            "requirements": list(self.requirements),
            "acceptance": list(self.acceptance),
            "verifications": list(self.verifications),
            "model_delta": copy.deepcopy(self.model_delta),
            "migrations": [copy.deepcopy(value) for value in self.migrations],
            "external_effects": [copy.deepcopy(value) for value in self.external_effects],
            "future_constraints": list(self.future_constraints),
        }

    def removed_contracts(self) -> set[str]:
        operations = self.model_delta.get("contracts", {})
        if not isinstance(operations, Mapping):
            return set()
        removed = operations.get("remove", [])
        if not isinstance(removed, Sequence) or isinstance(removed, (str, bytes)):
            return set()
        return {
            value.get("id") if isinstance(value, Mapping) else value
            for value in removed
            if isinstance(value, str)
            or (isinstance(value, Mapping) and isinstance(value.get("id"), str))
        }


def _normalize_section(section: str, raw: Any) -> dict[str, dict[str, Any]]:
    if isinstance(raw, Mapping):
        entries = []
        for identifier, value in raw.items():
            if not isinstance(value, Mapping):
                raise ValueError(f"{section}.{identifier} exige objeto")
            entries.append({"id": identifier, **dict(value)})
    elif isinstance(raw, list):
        entries = raw
    else:
        raise ValueError(f"ProjectModel.{section} exige lista")
    normalized: dict[str, dict[str, Any]] = {}
    for raw_entry in entries:
        entry = _normalize_entry(section, raw_entry)
        identifier = entry["id"]
        if identifier in normalized:
            raise ValueError(f"ID duplicado em {section}: {identifier}")
        normalized[identifier] = entry
    return normalized


def _normalize_entry(section: str, raw: Any) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise ValueError(f"{section} exige itens com id")
    identifier = raw.get("id")
    if not isinstance(identifier, str) or not MODEL_ID.fullmatch(identifier):
        raise ValueError(f"{section} exige id válido")
    try:
        entry = json.loads(json.dumps(dict(raw), ensure_ascii=False))
    except (TypeError, ValueError) as error:
        raise ValueError(f"{section}.{identifier} exige valores serializáveis") from error
    entry["id"] = identifier
    return entry


def _string_tuple(raw: Any, label: str) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        values = [raw]
    elif isinstance(raw, Sequence) and not isinstance(raw, (bytes, bytearray)):
        values = list(raw)
    else:
        raise ValueError(f"{label} exige lista de strings")
    if not all(isinstance(value, str) and value.strip() for value in values):
        raise ValueError(f"{label} exige lista de strings")
    return tuple(dict.fromkeys(value.strip() for value in values))


def _required_text(raw: Any, label: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{label} exige texto")
    return raw.strip()


def _mapping_tuple(raw: Any, label: str) -> tuple[dict[str, Any], ...]:
    if raw is None:
        return ()
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        raise ValueError(f"{label} exige lista de objetos")
    if not all(isinstance(value, Mapping) for value in raw):
        raise ValueError(f"{label} exige lista de objetos")
    return tuple(copy.deepcopy(dict(value)) for value in raw)


def _as_sequence(raw: Any, label: str) -> list[Any]:
    if raw is None:
        return []
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        raise ValueError(f"{label} exige lista")
    return list(raw)


def _parse_yaml_subset(raw: str) -> dict[str, Any]:
    lines: list[tuple[int, str, int]] = []
    for number, source_line in enumerate(raw.splitlines(), start=1):
        if not source_line.strip() or source_line.lstrip().startswith("#"):
            continue
        prefix = source_line[: len(source_line) - len(source_line.lstrip(" "))]
        if "\t" in prefix:
            raise ValueError(f"YAML inválido na linha {number}: tab não suportado")
        lines.append((len(prefix), source_line.strip(), number))
    if not lines:
        return {}
    if lines[0][0] != 0:
        raise ValueError("YAML inválido: primeiro campo deve iniciar na coluna zero")
    value, index = _parse_yaml_block(lines, 0, 0)
    if index != len(lines) or not isinstance(value, dict):
        number = lines[index][2] if index < len(lines) else lines[-1][2]
        raise ValueError(f"YAML inválido próximo da linha {number}")
    return value


def _parse_yaml_block(
    lines: list[tuple[int, str, int]], index: int, indent: int
) -> tuple[Any, int]:
    if index >= len(lines) or lines[index][0] != indent:
        raise ValueError("YAML inválido: indentação inesperada")
    is_list = lines[index][1].startswith("- ") or lines[index][1] == "-"
    if is_list:
        values: list[Any] = []
        while index < len(lines) and lines[index][0] == indent:
            text = lines[index][1]
            number = lines[index][2]
            if not (text.startswith("- ") or text == "-"):
                break
            remainder = text[1:].strip()
            index += 1
            if not remainder:
                if index >= len(lines) or lines[index][0] <= indent:
                    raise ValueError(f"YAML inválido na linha {number}: item vazio")
                value, index = _parse_yaml_block(lines, index, lines[index][0])
                values.append(value)
                continue
            inline_mapping = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*)$", remainder)
            if inline_mapping:
                item: dict[str, Any] = {}
                key, raw_value = inline_mapping.groups()
                if raw_value:
                    item[key] = _yaml_scalar(raw_value)
                elif index < len(lines) and lines[index][0] > indent:
                    item[key], index = _parse_yaml_block(lines, index, lines[index][0])
                else:
                    item[key] = None
                if index < len(lines) and lines[index][0] > indent:
                    continuation_indent = lines[index][0]
                    continuation, index = _parse_yaml_block(lines, index, continuation_indent)
                    if not isinstance(continuation, dict):
                        raise ValueError(
                            f"YAML inválido na linha {lines[index - 1][2]}: esperado objeto"
                        )
                    duplicate = set(item) & set(continuation)
                    if duplicate:
                        raise ValueError(f"YAML contém chave duplicada: {sorted(duplicate)[0]}")
                    item.update(continuation)
                values.append(item)
            else:
                values.append(_yaml_scalar(remainder))
        return values, index

    result: dict[str, Any] = {}
    while index < len(lines) and lines[index][0] == indent:
        text = lines[index][1]
        number = lines[index][2]
        if text.startswith("-"):
            break
        key, separator, raw_value = text.partition(":")
        key = key.strip()
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", key):
            raise ValueError(f"YAML inválido na linha {number}: chave inválida")
        if key in result:
            raise ValueError(f"YAML contém chave duplicada: {key}")
        index += 1
        raw_value = raw_value.strip()
        if raw_value:
            result[key] = _yaml_scalar(raw_value)
        elif index < len(lines) and lines[index][0] > indent:
            result[key], index = _parse_yaml_block(lines, index, lines[index][0])
        else:
            result[key] = None
    return result, index


def _yaml_scalar(raw: str) -> Any:
    value = raw.strip()
    lowered = value.lower()
    if value == "[]":
        return []
    if value == "{}":
        return {}
    if lowered in {"null", "~"}:
        return None
    if lowered in {"true", "yes"}:
        return True
    if lowered in {"false", "no"}:
        return False
    if value.startswith("[") and value.endswith("]"):
        body = value[1:-1].strip()
        if not body:
            return []
        return [_yaml_scalar(part) for part in _split_flow_list(body)]
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        try:
            return ast.literal_eval(value)
        except (ValueError, SyntaxError) as error:
            raise ValueError(f"string YAML inválida: {value}") from error
    if re.fullmatch(r"[-+]?[0-9]+", value):
        return int(value)
    if re.fullmatch(r"[-+]?(?:[0-9]+\.[0-9]*|[0-9]*\.[0-9]+)", value):
        return float(value)
    return value


def _split_flow_list(value: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    quote: str | None = None
    for char in value:
        if char in {'"', "'"}:
            quote = None if quote == char else char if quote is None else quote
        if char == "," and quote is None:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    parts.append("".join(current).strip())
    if not all(parts):
        raise ValueError("lista YAML contém item vazio")
    return parts


__all__ = [
    "MODEL_SECTIONS",
    "PLAN_ID",
    "PlanContract",
    "ProjectModel",
    "TASK_ID",
    "TaskContract",
    "TaskVerification",
    "read_frontmatter",
]
