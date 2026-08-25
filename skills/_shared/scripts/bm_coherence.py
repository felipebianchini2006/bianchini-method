#!/usr/bin/env python3
"""Grafo, coerência estrutural, impacto e normalização semântica do método."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from bm_project_model import PLAN_ID, PlanContract, ProjectModel


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class FindingStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    ACCEPTED_WITH_JUSTIFICATION = "accepted_with_justification"


@dataclass(frozen=True)
class Finding:
    code: str
    severity: Severity
    origin: str
    evidence: str
    expected_fix: str
    phases: tuple[str, ...] = ()
    contracts: tuple[str, ...] = ()
    status: FindingStatus = FindingStatus.OPEN
    justification: str | None = None

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", self.code):
            raise ValueError(f"código de finding inválido: {self.code}")
        if self.origin not in {"structural", "semantic"}:
            raise ValueError("origin exige structural ou semantic")
        if self.origin == "semantic" and self.severity is Severity.ERROR:
            raise ValueError("finding semântico não pode ter severidade ERROR")
        if not self.evidence.strip() or not self.expected_fix.strip():
            raise ValueError("finding exige evidência e correção esperada")
        if (
            self.status is FindingStatus.ACCEPTED_WITH_JUSTIFICATION
            and not (self.justification or "").strip()
        ):
            raise ValueError("finding aceito exige justificativa")

    def accept(self, justification: str) -> "Finding":
        if not justification.strip():
            raise ValueError("finding aceito exige justificativa")
        if self.severity is Severity.ERROR:
            raise ValueError("finding ERROR não pode ser aceito por justificativa")
        return replace(
            self,
            status=FindingStatus.ACCEPTED_WITH_JUSTIFICATION,
            justification=justification.strip(),
        )

    def resolve(self) -> "Finding":
        return replace(self, status=FindingStatus.RESOLVED, justification=None)

    def to_mapping(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "origin": self.origin,
            "phases": list(self.phases),
            "contracts": list(self.contracts),
            "evidence": self.evidence,
            "expected_fix": self.expected_fix,
            "status": self.status.value,
            "justification": self.justification,
        }


class DependencyGraph:
    """Grafo determinístico com arestas declaradas e provider→consumer."""

    def __init__(self, plans: Iterable[PlanContract | Mapping[str, Any]]) -> None:
        self.plans = tuple(_plan(value) for value in plans)
        self.order = tuple(plan.id for plan in self.plans)
        self.plan_by_id: dict[str, PlanContract] = {}
        for plan in self.plans:
            self.plan_by_id.setdefault(plan.id, plan)
        self.providers: dict[str, set[str]] = {}
        self.consumers: dict[str, set[str]] = {}
        for plan in self.plans:
            for contract in plan.provides:
                self.providers.setdefault(contract, set()).add(plan.id)
            for contract in plan.consumes:
                self.consumers.setdefault(contract, set()).add(plan.id)
        self.dependencies: dict[str, set[str]] = {
            identifier: set(plan.depends_on)
            for identifier, plan in self.plan_by_id.items()
        }
        for contract, consumers in self.consumers.items():
            for consumer in consumers:
                for provider in self.providers.get(contract, set()):
                    if provider != consumer:
                        self.dependencies.setdefault(consumer, set()).add(provider)

    def topological_order(self) -> list[str]:
        unknown = sorted(
            dependency
            for dependencies in self.dependencies.values()
            for dependency in dependencies
            if dependency not in self.plan_by_id
        )
        if unknown:
            raise ValueError(f"dependência inexistente: {unknown[0]}")
        position = {identifier: index for index, identifier in enumerate(self.order)}
        remaining = {key: set(value) for key, value in self.dependencies.items()}
        result: list[str] = []
        while remaining:
            ready = sorted(
                (identifier for identifier, deps in remaining.items() if not deps),
                key=lambda identifier: (position.get(identifier, len(position)), identifier),
            )
            if not ready:
                raise ValueError("grafo contém ciclo")
            for identifier in ready:
                result.append(identifier)
                del remaining[identifier]
            for dependencies in remaining.values():
                dependencies.difference_update(ready)
        return result

    def direct_dependents(self, plan_id: str) -> set[str]:
        return {
            identifier
            for identifier, dependencies in self.dependencies.items()
            if plan_id in dependencies
        }

    def transitive_dependents(self, plan_ids: Iterable[str]) -> set[str]:
        roots = set(plan_ids)
        visited: set[str] = set()
        frontier = set(roots)
        while frontier:
            following: set[str] = set()
            for identifier in frontier:
                following.update(self.direct_dependents(identifier))
            following.difference_update(roots | visited)
            visited.update(following)
            frontier = following
        return visited

    def consumers_of(self, contracts: Iterable[str]) -> set[str]:
        result: set[str] = set()
        for contract in contracts:
            result.update(self.consumers.get(contract, set()))
        return result


class StructuralValidator:
    """Valida invariantes objetivas sem qualquer decisão de uma LLM."""

    def validate(
        self,
        current: ProjectModel,
        plans: Iterable[PlanContract | Mapping[str, Any]],
        expected: ProjectModel | None = None,
        *,
        requirements: Iterable[str] = (),
    ) -> list[Finding]:
        plan_values = tuple(_plan(value) for value in plans)
        findings: list[Finding] = []
        order = {plan.id: index for index, plan in enumerate(plan_values)}
        identifiers = [plan.id for plan in plan_values]
        identifier_set = set(identifiers)

        for identifier in sorted(set(identifiers)):
            if not PLAN_ID.fullmatch(identifier):
                findings.append(
                    self._error(
                        "INVALID_PLAN_ID",
                        f"ID de plano inválido: {identifier}",
                        "Usar P seguido por ao menos dois dígitos.",
                        phases=(identifier,),
                    )
                )
            if identifiers.count(identifier) > 1:
                findings.append(
                    self._error(
                        "DUPLICATE_PLAN_ID",
                        f"ID repetido no roadmap: {identifier}",
                        "Atribuir um ID único a cada plano.",
                        phases=(identifier,),
                    )
                )

        for plan in plan_values:
            if not plan.acceptance:
                findings.append(
                    self._error(
                        "MISSING_ACCEPTANCE",
                        f"{plan.id} não declara critérios de aceite.",
                        "Declarar ao menos um resultado observável.",
                        phases=(plan.id,),
                    )
                )
            if not plan.verifications:
                findings.append(
                    self._error(
                        "MISSING_VERIFICATION",
                        f"{plan.id} não declara verificações.",
                        "Declarar a verificação que prova o aceite.",
                        phases=(plan.id,),
                    )
                )
            for dependency in plan.depends_on:
                if dependency == plan.id:
                    findings.append(
                        self._error(
                            "SELF_DEPENDENCY",
                            f"{plan.id} depende de si mesmo.",
                            "Remover a dependência circular.",
                            phases=(plan.id,),
                        )
                    )
                elif dependency not in identifier_set:
                    findings.append(
                        self._error(
                            "UNKNOWN_DEPENDENCY",
                            f"{plan.id} depende do plano inexistente {dependency}.",
                            "Corrigir depends_on ou adicionar o plano ausente.",
                            phases=(plan.id,),
                        )
                    )
                elif order[dependency] > order[plan.id]:
                    findings.append(
                        self._error(
                            "ORDER_VIOLATION",
                            f"{plan.id} aparece antes de sua dependência {dependency}.",
                            "Reordenar o roadmap para executar o provider primeiro.",
                            phases=(plan.id, dependency),
                        )
                    )

        graph = DependencyGraph(plan_values)
        try:
            graph.topological_order()
        except ValueError as error:
            if "ciclo" in str(error):
                findings.append(
                    self._error(
                        "DEPENDENCY_CYCLE",
                        "O grafo de planos contém um ciclo.",
                        "Romper o ciclo e declarar uma ordem executável.",
                        phases=tuple(sorted(identifier_set)),
                    )
                )

        available = current.component_ids()
        for plan in plan_values:
            for contract in plan.consumes:
                providers = graph.providers.get(contract, set())
                if contract not in available and not providers:
                    findings.append(
                        self._error(
                            "MISSING_PROVIDER",
                            f"{plan.id} consome {contract}, mas nenhum estado ou plano o fornece.",
                            "Adicionar provider ou remover o consumo inválido.",
                            phases=(plan.id,),
                            contracts=(contract,),
                        )
                    )
                for provider in providers:
                    if provider != plan.id and order.get(provider, -1) > order[plan.id]:
                        findings.append(
                            self._error(
                                "ORDER_VIOLATION",
                                f"{plan.id} consome {contract} antes de {provider} fornecê-lo.",
                                "Executar o provider antes do consumer.",
                                phases=(plan.id, provider),
                                contracts=(contract,),
                            )
                        )

        for contract, providers in sorted(graph.providers.items()):
            if len(providers) > 1:
                findings.append(
                    self._error(
                        "PROVIDER_CONFLICT",
                        f"Contrato {contract} possui múltiplos providers: {', '.join(sorted(providers))}.",
                        "Definir um único provider responsável.",
                        phases=tuple(sorted(providers)),
                        contracts=(contract,),
                    )
                )

        owners: dict[str, list[str]] = {}
        for plan in plan_values:
            for resource in plan.owns:
                owners.setdefault(resource, []).append(plan.id)
        for resource, owner_plans in sorted(owners.items()):
            if len(set(owner_plans)) > 1:
                findings.append(
                    self._error(
                        "OWNERSHIP_CONFLICT",
                        f"{resource} possui ownership em {', '.join(sorted(set(owner_plans)))}.",
                        "Definir um owner único e tornar os demais consumers.",
                        phases=tuple(sorted(set(owner_plans))),
                        contracts=(resource,),
                    )
                )

        for index, plan in enumerate(plan_values):
            for removed in sorted(plan.removed_contracts()):
                consumers = [
                    later.id for later in plan_values[index + 1 :] if removed in later.consumes
                ]
                if consumers:
                    findings.append(
                        self._error(
                            "CONTRACT_REMOVED_BEFORE_CONSUMERS",
                            f"{plan.id} remove {removed} antes dos consumers {', '.join(consumers)}.",
                            "Migrar os consumers antes de remover o contrato.",
                            phases=(plan.id, *consumers),
                            contracts=(removed,),
                        )
                    )

        findings.extend(self._validate_migrations(plan_values, order))
        required = {value for value in requirements if isinstance(value, str) and value}
        covered = {requirement for plan in plan_values for requirement in plan.requirements}
        for missing in sorted(required - covered):
            findings.append(
                self._error(
                    "REQUIREMENT_WITHOUT_PLAN",
                    f"Requisito sem fase responsável: {missing}.",
                    "Associar o requisito a um plano com aceite e verificação.",
                    contracts=(missing,),
                )
            )

        findings.extend(self._validate_journeys(current, "atual"))
        if expected is not None:
            findings.extend(self._validate_journeys(expected, "final"))
        for plan in plan_values:
            for effect in plan.external_effects:
                if effect.get("guard_required", True) and not _guards(effect):
                    identifier = effect.get("id", "efeito externo")
                    findings.append(
                        self._error(
                            "MISSING_GUARD",
                            f"{plan.id} declara {identifier} sem guard de falha/recuperação.",
                            "Declarar guards verificáveis antes da execução.",
                            phases=(plan.id,),
                            contracts=(str(identifier),),
                        )
                    )

        calculated = current
        for plan in plan_values:
            try:
                calculated = calculated.apply_delta(plan.model_delta)
            except ValueError as error:
                findings.append(
                    self._error(
                        "MODEL_DELTA_INVALID",
                        f"{plan.id} possui delta inválido: {error}",
                        "Corrigir o delta para produzir um snapshot válido.",
                        phases=(plan.id,),
                    )
                )
                break
        if expected is not None and not calculated.equivalent(expected):
            difference = json.dumps(
                calculated.differences(expected), ensure_ascii=False, sort_keys=True
            )
            findings.append(
                self._error(
                    "MODEL_MISMATCH",
                    f"O modelo simulado diverge do modelo final: {difference}",
                    "Alinhar deltas dos planos e SYSTEM_MODEL.md final.",
                    phases=tuple(identifiers),
                )
            )
        return _sorted_findings(findings, order)

    @staticmethod
    def _validate_journeys(model: ProjectModel, label: str) -> list[Finding]:
        identifiers = model.component_ids()
        findings: list[Finding] = []
        for journey_id, journey in sorted(model.journeys.items()):
            path = journey.get("path", [])
            if not isinstance(path, list) or not path:
                findings.append(
                    StructuralValidator._error(
                        "JOURNEY_EMPTY",
                        f"Journey {journey_id} no modelo {label} não possui path.",
                        "Declarar o caminho ponta a ponta.",
                        contracts=(journey_id,),
                    )
                )
                continue
            for component in path:
                if not isinstance(component, str) or component not in identifiers:
                    findings.append(
                        StructuralValidator._error(
                            "JOURNEY_COMPONENT_MISSING",
                            f"Journey {journey_id} referencia componente ausente: {component}.",
                            "Adicionar o componente ao modelo ou corrigir a jornada.",
                            contracts=(journey_id, str(component)),
                        )
                    )
        return findings

    @staticmethod
    def _validate_migrations(
        plans: tuple[PlanContract, ...], order: Mapping[str, int]
    ) -> list[Finding]:
        findings: list[Finding] = []
        for plan in plans:
            for migration in plan.migrations:
                migration_id = str(migration.get("id", "migration"))
                after = migration.get("after", [])
                if isinstance(after, str):
                    after = [after]
                if not isinstance(after, Sequence):
                    findings.append(
                        StructuralValidator._error(
                            "MIGRATION_ORDER_INVALID",
                            f"{plan.id}/{migration_id} possui after inválido.",
                            "Declarar lista de planos anteriores.",
                            phases=(plan.id,),
                        )
                    )
                    continue
                for dependency in after:
                    if dependency not in order or order[dependency] >= order[plan.id]:
                        findings.append(
                            StructuralValidator._error(
                                "MIGRATION_ORDER_INVALID",
                                f"{plan.id}/{migration_id} exige {dependency} antes da migração.",
                                "Reposicionar a migração após sua dependência.",
                                phases=(plan.id, str(dependency)),
                            )
                        )
                if migration.get("destructive") and not migration.get("compatibility"):
                    findings.append(
                        StructuralValidator._error(
                            "MIGRATION_COMPATIBILITY_MISSING",
                            f"{plan.id}/{migration_id} é destrutiva sem compatibilidade declarada.",
                            "Declarar compatibilidade e rollback.",
                            phases=(plan.id,),
                        )
                    )
        return findings

    @staticmethod
    def _error(
        code: str,
        evidence: str,
        expected_fix: str,
        *,
        phases: tuple[str, ...] = (),
        contracts: tuple[str, ...] = (),
    ) -> Finding:
        return Finding(
            code=code,
            severity=Severity.ERROR,
            origin="structural",
            evidence=evidence,
            expected_fix=expected_fix,
            phases=phases,
            contracts=contracts,
        )


@dataclass(frozen=True)
class ImpactResult:
    radius: str
    changed_plan: str
    direct_plans: tuple[str, ...]
    transitive_plans: tuple[str, ...]
    stale_plans: tuple[str, ...]
    affected_journeys: tuple[str, ...]
    verifications: tuple[str, ...]

    def to_mapping(self) -> dict[str, Any]:
        return {
            "radius": self.radius,
            "changed_plan": self.changed_plan,
            "direct_plans": list(self.direct_plans),
            "transitive_plans": list(self.transitive_plans),
            "stale_plans": list(self.stale_plans),
            "affected_journeys": list(self.affected_journeys),
            "verifications": list(self.verifications),
        }


class ImpactAnalyzer:
    def __init__(self, graph: DependencyGraph, model: ProjectModel | None = None) -> None:
        self.graph = graph
        self.model = model
        self.position = {identifier: index for index, identifier in enumerate(graph.order)}

    def analyze(
        self,
        changed_plan: str,
        *,
        changed_contracts: Iterable[str] = (),
        changed_ownership: Iterable[str] = (),
        changed_interfaces: Iterable[str] = (),
        changed_data: Iterable[str] = (),
        changed_migrations: Iterable[str] = (),
        changed_journeys: Iterable[str] = (),
        changed_effects: Iterable[str] = (),
        changed_invariants: Iterable[str] = (),
        global_change: bool = False,
    ) -> ImpactResult:
        if changed_plan not in self.graph.plan_by_id:
            raise ValueError(f"plano desconhecido: {changed_plan}")
        contracts = set(changed_contracts)
        resources = (
            set(changed_ownership)
            | set(changed_interfaces)
            | set(changed_data)
            | set(changed_migrations)
            | set(changed_effects)
        )
        changed_journey_ids = set(changed_journeys)
        invariants = set(changed_invariants)
        direct = self.graph.consumers_of(contracts) if contracts else set()
        direct.discard(changed_plan)
        changed_position = self.position[changed_plan]
        direct = {
            identifier
            for identifier in direct
            if self.position.get(identifier, -1) > changed_position
        }
        for identifier, plan in self.graph.plan_by_id.items():
            if self.position.get(identifier, -1) <= changed_position:
                continue
            if resources.intersection(_plan_resources(plan)):
                direct.add(identifier)
        if not contracts and not resources and not changed_journey_ids:
            direct.update(self.graph.direct_dependents(changed_plan))
        downstream = self.graph.transitive_dependents(direct)
        downstream.discard(changed_plan)
        downstream.difference_update(direct)
        if global_change or invariants:
            direct = self.graph.direct_dependents(changed_plan)
            all_downstream = self.graph.transitive_dependents({changed_plan})
            downstream = all_downstream - direct
            radius = "global"
        elif downstream:
            radius = "transitive"
        elif direct:
            radius = "direct"
        else:
            radius = "local"
        stale = direct | downstream
        affected_journeys: set[str] = set()
        affected_journeys.update(changed_journey_ids)
        if self.model is not None:
            changed = contracts | resources | invariants
            for identifier, journey in self.model.journeys.items():
                path = journey.get("path", [])
                if isinstance(path, list) and changed.intersection(path):
                    affected_journeys.add(identifier)
        verifications = {
            verification
            for identifier in stale | {changed_plan}
            for verification in self.graph.plan_by_id[identifier].verifications
        }
        return ImpactResult(
            radius=radius,
            changed_plan=changed_plan,
            direct_plans=self._ordered(direct),
            transitive_plans=self._ordered(downstream),
            stale_plans=self._ordered(stale),
            affected_journeys=tuple(sorted(affected_journeys)),
            verifications=tuple(sorted(verifications)),
        )

    def _ordered(self, values: Iterable[str]) -> tuple[str, ...]:
        return tuple(
            sorted(values, key=lambda value: (self.position.get(value, len(self.position)), value))
        )


@dataclass(frozen=True)
class SemanticReview:
    available: bool
    findings: tuple[Finding, ...]
    prompt_digest: str
    input_digest: str
    sources_digest: str

    def has_blockers(self) -> bool:
        return any(
            finding.status is FindingStatus.OPEN
            and finding.severity in {Severity.ERROR, Severity.WARNING}
            for finding in self.findings
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "findings": [finding.to_mapping() for finding in self.findings],
            "prompt_digest": self.prompt_digest,
            "input_digest": self.input_digest,
            "sources_digest": self.sources_digest,
        }


class SemanticReviewer:
    """Normaliza saída externa sem executar nem simular uma chamada LLM."""

    def normalize(
        self,
        raw_findings: Iterable[Mapping[str, Any]],
        *,
        prompt: str = "",
        inputs: str = "",
        sources: Iterable[str] = (),
    ) -> SemanticReview:
        findings: list[Finding] = []
        for raw in raw_findings:
            if not isinstance(raw, Mapping):
                raise ValueError("finding semântico exige objeto")
            severity = _severity(raw.get("severity", "WARNING"))
            if severity is Severity.ERROR:
                severity = Severity.WARNING
            status = _status(raw.get("status", "open"))
            justification = raw.get("justification")
            expected_fix = str(raw.get("expected_fix", "")).strip()
            if not expected_fix and severity is Severity.INFO:
                expected_fix = "Nenhuma ação obrigatória."
            finding = Finding(
                code=_finding_code(raw.get("code", "SEMANTIC_FINDING")),
                severity=severity,
                origin="semantic",
                phases=_strings(raw.get("phases", []), "phases"),
                contracts=_strings(raw.get("contracts", []), "contracts"),
                evidence=str(raw.get("evidence", "")).strip(),
                expected_fix=expected_fix,
                status=status,
                justification=str(justification).strip() if justification is not None else None,
            )
            findings.append(finding)
        return SemanticReview(
            available=True,
            findings=tuple(_sorted_findings(findings, {})),
            prompt_digest=_digest_text(prompt),
            input_digest=_digest_text(inputs),
            sources_digest=_digest_text("\n".join(sorted(set(sources)))),
        )

    def unavailable(self, reason: str) -> SemanticReview:
        finding = Finding(
            code="SEMANTIC_REVIEW_UNAVAILABLE",
            severity=Severity.WARNING,
            origin="semantic",
            evidence=reason.strip() or "Revisor semântico indisponível.",
            expected_fix="Executar a revisão antes da aprovação do pacote.",
        )
        return SemanticReview(
            available=False,
            findings=(finding,),
            prompt_digest=_digest_text(""),
            input_digest=_digest_text(""),
            sources_digest=_digest_text(""),
        )


def _plan(value: PlanContract | Mapping[str, Any]) -> PlanContract:
    return value if isinstance(value, PlanContract) else PlanContract.from_mapping(value)


def _guards(effect: Mapping[str, Any]) -> tuple[str, ...]:
    raw = effect.get("guards", [])
    if isinstance(raw, str) and raw.strip():
        return (raw.strip(),)
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        return tuple(value for value in raw if isinstance(value, str) and value.strip())
    named = (
        "idempotency",
        "authenticity",
        "deduplication",
        "recovery",
        "rollback",
        "reconciliation",
    )
    return tuple(key for key in named if effect.get(key))


def _plan_resources(plan: PlanContract) -> set[str]:
    resources = set(plan.provides) | set(plan.consumes) | set(plan.owns) | set(plan.touches)
    resources.update(
        str(value["id"])
        for value in (*plan.migrations, *plan.external_effects)
        if isinstance(value.get("id"), str)
    )
    for operations in plan.model_delta.values():
        if isinstance(operations, list):
            values = operations
        elif isinstance(operations, Mapping):
            values = [
                item
                for operation in ("add", "update", "upsert", "remove")
                for item in (
                    operations.get(operation, [])
                    if isinstance(operations.get(operation, []), list)
                    else []
                )
            ]
        else:
            continue
        for value in values:
            identifier = value.get("id") if isinstance(value, Mapping) else value
            if isinstance(identifier, str):
                resources.add(identifier)
    return resources


def _severity(value: Any) -> Severity:
    try:
        return Severity(str(value).upper())
    except ValueError as error:
        raise ValueError(f"severidade inválida: {value}") from error


def _finding_code(value: Any) -> str:
    normalized = re.sub(r"[^A-Z0-9]+", "_", str(value).upper()).strip("_")
    if not normalized or not normalized[0].isalpha():
        raise ValueError(f"código de finding inválido: {value}")
    return normalized


def _status(value: Any) -> FindingStatus:
    try:
        return FindingStatus(str(value).lower())
    except ValueError as error:
        raise ValueError(f"status de finding inválido: {value}") from error


def _strings(value: Any, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        values = list(value)
    else:
        raise ValueError(f"{label} exige lista de strings")
    if not all(isinstance(item, str) and item.strip() for item in values):
        raise ValueError(f"{label} exige lista de strings")
    return tuple(dict.fromkeys(item.strip() for item in values))


def _sorted_findings(
    findings: Iterable[Finding], order: Mapping[str, int]
) -> list[Finding]:
    severity_order = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}
    return sorted(
        findings,
        key=lambda finding: (
            min((order.get(phase, len(order)) for phase in finding.phases), default=len(order)),
            severity_order[finding.severity],
            finding.code,
            finding.evidence,
        ),
    )


def _digest_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "DependencyGraph",
    "Finding",
    "FindingStatus",
    "ImpactAnalyzer",
    "ImpactResult",
    "SemanticReview",
    "SemanticReviewer",
    "Severity",
    "StructuralValidator",
]
