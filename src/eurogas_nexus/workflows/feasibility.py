"""Route feasibility check — research-only, no execution semantics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class FeasibilityStatus(StrEnum):
    """Feasibility classification of a route scenario."""

    FEASIBLE = "feasible"
    INFEASIBLE = "infeasible"
    CONDITIONAL = "conditional"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FeasibilityInput:
    """Feasibility check input.

    Attributes:
        route_name: Route display name.
        from_node_id / to_node_id: Route endpoints.
        capacity_available_mcm_d: Available capacity, mcm/d.
        required_capacity_mcm_d: Required capacity, mcm/d.
        route_eligible: Whether the route is eligible.
        contract_active: Whether the contract is active.
        constraints: Extra constraint tags.
    """

    route_name: str
    from_node_id: str
    to_node_id: str
    capacity_available_mcm_d: float = 0.0
    required_capacity_mcm_d: float = 0.0
    route_eligible: bool = True
    contract_active: bool = True
    constraints: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FeasibilityOutput:
    """Feasibility check output (research-only envelope).

    Attributes:
        route_name / from_node_id / to_node_id: Echoed identity.
        status: Feasibility classification.
        blockers: Blocking conditions.
        conditions: Conditional requirements.
        assumptions / missing_inputs / warnings: Transparency fields.
        source_references / lineage: Provenance.
        research_only / human_review_required: Always True.
        generated_at_utc: Generation time (ISO).
    """

    route_name: str
    from_node_id: str
    to_node_id: str
    status: FeasibilityStatus = FeasibilityStatus.UNKNOWN
    blockers: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_references: list[str] = field(default_factory=list)
    lineage: list[str] = field(default_factory=list)
    research_only: bool = True
    human_review_required: bool = True
    generated_at_utc: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )

    @property
    def is_partial(self) -> bool:
        """Whether any input is missing (partial result)."""

        return bool(self.missing_inputs)


def check_feasibility(input_: FeasibilityInput) -> FeasibilityOutput:
    """Check route feasibility against capacity, eligibility, and contracts."""

    missing: list[str] = []
    warnings: list[str] = []
    blockers: list[str] = []
    conditions: list[str] = []
    assumptions: list[str] = [
        "Capacity figures are supplied operator/runtime inputs.",
        "Feasibility is a research assessment, not an operational commitment.",
    ]

    if not input_.route_name:
        missing.append("route_name is required.")
    if not input_.from_node_id:
        missing.append("from_node_id is required.")
    if not input_.to_node_id:
        missing.append("to_node_id is required.")

    if not input_.route_eligible:
        blockers.append("Route is not eligible (eligibility not confirmed).")

    if not input_.contract_active:
        blockers.append("No active capacity contract for this route.")

    if input_.required_capacity_mcm_d > input_.capacity_available_mcm_d:
        blockers.append(
            f"Required capacity ({input_.required_capacity_mcm_d} mcm/d) "
            f"exceeds available ({input_.capacity_available_mcm_d} mcm/d)."
        )

    if input_.capacity_available_mcm_d <= 0 and not blockers:
        warnings.append("Capacity data is zero or missing; feasibility is conditional.")
        conditions.append("Verify capacity availability with operator data.")

    for constraint in input_.constraints:
        if constraint:
            conditions.append(constraint)

    if blockers:
        status = FeasibilityStatus.INFEASIBLE
    elif conditions:
        status = FeasibilityStatus.CONDITIONAL
    elif missing:
        status = FeasibilityStatus.UNKNOWN
    else:
        status = FeasibilityStatus.FEASIBLE

    return FeasibilityOutput(
        route_name=input_.route_name,
        from_node_id=input_.from_node_id,
        to_node_id=input_.to_node_id,
        status=status,
        blockers=blockers,
        conditions=conditions,
        assumptions=assumptions,
        missing_inputs=missing,
        warnings=warnings,
        source_references=["operator-input"],
        lineage=["feasibility-check"],
        human_review_required=bool(blockers or conditions or missing),
    )
