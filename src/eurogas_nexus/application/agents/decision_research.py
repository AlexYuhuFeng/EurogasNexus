"""Offline research spike for evidence-gated route assessment.

The caller supplies synthetic scenario inputs and a trusted invocation context.
This module is intentionally unwired from API, worker, registry and MCP entry points.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from math import isfinite
from time import perf_counter
from typing import Annotated, Generic, Literal, TypeVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints

from eurogas_nexus.application.agents.runtime import CapabilityRuntime
from eurogas_nexus.domain.agents.contracts import (
    ActionPolicy,
    AgentInvocationContext,
    CapabilityExecutionMetadata,
    DeterminismClass,
    SideEffectClass,
)
from eurogas_nexus.domain.research.feasibility import FeasibilityStatus

Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
Capacity = Annotated[float, Field(strict=True, ge=0, allow_inf_nan=False)]
Requirement = Annotated[float, Field(strict=True, gt=0, allow_inf_nan=False)]
T = TypeVar("T")


class Task(StrEnum):
    ROUTE_COST = "route_cost"
    ROUTE_INVESTIGATION = "route_investigation"


class EvidenceIssue(StrEnum):
    UNKNOWN = "UNKNOWN"
    CONFLICTED = "CONFLICTED"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    OUTSIDE_VALIDITY = "OUTSIDE_VALIDITY"


class ResearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FixtureEvidence(ResearchInput, Generic[T]):
    """Synthetic proposition with a source version and a bounded validity interval."""

    value: T
    reference: Identifier
    version: Identifier
    available_at: AwareDatetime
    valid_from: AwareDatetime
    valid_until: AwareDatetime
    conflicted: bool = Field(default=False, strict=True)


class Cost(ResearchInput):
    component_type: Identifier
    amount: Annotated[float, Field(strict=True, allow_inf_nan=False, ge=-1e9, le=1e9)]
    unit: Literal["EUR/MWh"]
    currency: Literal["EUR"]


class RouteStudy(ResearchInput):
    task: Task
    as_of: AwareDatetime
    delivery_at: AwareDatetime
    route_name: Identifier
    from_node_id: Identifier
    to_node_id: Identifier
    capacity: FixtureEvidence[Capacity] | None = None
    demand: FixtureEvidence[Requirement] | None = None
    eligible: FixtureEvidence[Annotated[bool, Field(strict=True)]] | None = None
    contract_active: FixtureEvidence[Annotated[bool, Field(strict=True)]] | None = None
    costs: Annotated[tuple[FixtureEvidence[Cost], ...], Field(max_length=32)] = ()


class InvocationTrace(BaseModel):
    capability: str
    status: str
    elapsed_ms: float
    metadata: CapabilityExecutionMetadata


class Assessment(BaseModel):
    path: Literal["DETERMINISTIC_ENGINE", "DETERMINISTIC_WORKFLOW"]
    source_class: Literal["SYNTHETIC"] = "SYNTHETIC"
    evidence_authority: Literal["INDICATIVE"] = "INDICATIVE"
    commercial_status: Literal["NOT_ASSESSED"] = "NOT_ASSESSED"
    feasibility: FeasibilityStatus = FeasibilityStatus.UNKNOWN
    total_cost_eur_mwh: float | None = None
    issues: dict[str, EvidenceIssue] = Field(default_factory=dict)
    evidence: dict[str, tuple[str, str]] = Field(default_factory=dict)
    blockers: list[str] = Field(default_factory=list)
    trace: list[InvocationTrace] = Field(default_factory=list)
    duration_ms: float = 0


class RouteDecisionResearch:
    """Compose existing read-only capabilities with explicit fixture evidence gates."""

    def __init__(self, runtime: CapabilityRuntime) -> None:
        self.runtime = runtime

    def assess(self, study: RouteStudy, context: AgentInvocationContext) -> Assessment:
        started = perf_counter()
        result = self._assess(study, context)
        result.duration_ms = (perf_counter() - started) * 1000
        return result

    def _assess(self, study: RouteStudy, context: AgentInvocationContext) -> Assessment:
        investigate = study.task is Task.ROUTE_INVESTIGATION
        result = Assessment(
            path="DETERMINISTIC_WORKFLOW" if investigate else "DETERMINISTIC_ENGINE"
        )
        cost_evidence = {f"costs[{i}]": item for i, item in enumerate(study.costs)}
        evidence = dict(cost_evidence) if cost_evidence else {"costs": None}
        if investigate:
            evidence.update(
                capacity=study.capacity,
                demand=study.demand,
                eligible=study.eligible,
                contract_active=study.contract_active,
            )
        for key, item in evidence.items():
            if item is not None:
                result.evidence[key] = (item.reference, item.version)
            if issue := _issue(item, study):
                result.issues[key] = issue
        if result.issues:
            return result

        route = study.model_dump(include={"route_name", "from_node_id", "to_node_id"})
        cost_result = self._invoke(
            "route.calculate_economics",
            {**route, "components": [item.value.model_dump() for item in study.costs]},
            context,
            result,
        )
        if cost_result is None:
            return result
        amount = cost_result.get("total_cost_eur_mwh")
        if (
            type(amount) not in (int, float)
            or not isfinite(amount)
            or cost_result.get("missing_inputs")
            or cost_result.get("warnings")
        ):
            result.blockers.append("route.calculate_economics: unusable result")
            return result
        if investigate:
            feasibility = self._invoke(
                "route.check_feasibility",
                {
                    **route,
                    "capacity_available_mcm_d": study.capacity.value,
                    "required_capacity_mcm_d": study.demand.value,
                    "route_eligible": study.eligible.value,
                    "contract_active": study.contract_active.value,
                },
                context,
                result,
            )
            if feasibility is None:
                return result
            status = feasibility.get("status")
            blockers = feasibility.get("blockers")
            if (
                status not in list(FeasibilityStatus)
                or not isinstance(blockers, list)
                or any(not isinstance(item, str) for item in blockers)
            ):
                result.blockers.append("route.check_feasibility: unusable result")
                return result
            result.feasibility = FeasibilityStatus(status)
            result.blockers.extend(blockers)
        result.total_cost_eur_mwh = amount
        return result

    def _invoke(
        self,
        capability: str,
        arguments: dict,
        context: AgentInvocationContext,
        assessment: Assessment,
    ) -> dict | None:
        definition = self.runtime.registry.get(capability)
        if (
            definition is None
            or definition.side_effect_class != SideEffectClass.READ_ONLY
            or definition.action_policy != ActionPolicy.AUTO_ALLOWED
            or definition.determinism_class != DeterminismClass.DETERMINISTIC
        ):
            assessment.blockers.append(f"{capability}: unsupported capability policy")
            return None
        started = perf_counter()
        response = self.runtime.invoke(capability, arguments, context)
        assessment.trace.append(
            InvocationTrace(
                capability=capability,
                status=response.status,
                elapsed_ms=(perf_counter() - started) * 1000,
                metadata=response.execution_metadata,
            )
        )
        if response.status != "SUCCESS" or not isinstance(response.data, Mapping):
            reason = response.failure.code.value if response.failure else "UNEXPECTED_RESULT"
            assessment.blockers.append(f"{capability}: {reason}")
            return None
        return dict(response.data)


def _issue(item: FixtureEvidence | None, study: RouteStudy) -> EvidenceIssue | None:
    if item is None:
        return EvidenceIssue.UNKNOWN
    if item.conflicted:
        return EvidenceIssue.CONFLICTED
    if item.available_at > study.as_of:
        return EvidenceIssue.NOT_AVAILABLE
    if not item.valid_from <= study.delivery_at < item.valid_until:
        return EvidenceIssue.OUTSIDE_VALIDITY
    return None
