"""Allocation scenario computation — research-only, no execution semantics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class AllocationCandidate:
    candidate_id: str
    route_name: str
    from_node_id: str
    to_node_id: str
    capacity_available_boe_d: float = 0.0
    cost_eur_mwh: float = 0.0
    rank: int = 0
    eligible: bool = True


@dataclass(frozen=True)
class AllocationInput:
    scenario_name: str
    total_demand_boe_d: float = 0.0
    candidates: list[AllocationCandidate] = field(default_factory=list)


@dataclass(frozen=True)
class AllocationResult:
    candidate_id: str
    route_name: str
    allocated_boe_d: float = 0.0
    cost_eur_mwh: float = 0.0
    rank: int = 0
    note: str = ""


@dataclass(frozen=True)
class AllocationOutput:
    scenario_name: str
    total_demand_boe_d: float
    total_allocated_boe_d: float = 0.0
    unallocated_boe_d: float = 0.0
    results: list[AllocationResult] = field(default_factory=list)
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
        return bool(self.missing_inputs)


def compute_allocation(input_: AllocationInput) -> AllocationOutput:
    """Distribute demand across eligible candidates by rank order.

    Candidates are sorted by rank (ascending). Each candidate receives
    volume up to its available capacity until demand is satisfied.
    Ineligible candidates are skipped.
    """

    missing: list[str] = []
    warnings: list[str] = []

    if not input_.scenario_name:
        missing.append("scenario_name is required.")
    if input_.total_demand_boe_d <= 0:
        missing.append("total_demand_boe_d must be positive.")
    if not input_.candidates:
        missing.append("At least one candidate is required.")

    eligible = [
        c for c in input_.candidates if c.eligible
    ]
    if not eligible and input_.candidates:
        warnings.append("No eligible candidates; nothing can be allocated.")

    sorted_candidates = sorted(eligible, key=lambda c: (c.rank, -c.capacity_available_boe_d))

    remaining = input_.total_demand_boe_d
    results: list[AllocationResult] = []

    for c in sorted_candidates:
        if remaining <= 0:
            break
        allocated = min(c.capacity_available_boe_d, remaining)
        remaining -= allocated
        results.append(AllocationResult(
            candidate_id=c.candidate_id,
            route_name=c.route_name,
            allocated_boe_d=allocated,
            cost_eur_mwh=c.cost_eur_mwh,
            rank=c.rank,
        ))

    total_allocated = sum(r.allocated_boe_d for r in results)
    unallocated = input_.total_demand_boe_d - total_allocated

    if unallocated > 0:
        warnings.append(
            f"Unallocated demand: {unallocated:.1f} boe/d "
            f"({unallocated / input_.total_demand_boe_d * 100:.1f}%)."
        )

    return AllocationOutput(
        scenario_name=input_.scenario_name,
        total_demand_boe_d=input_.total_demand_boe_d,
        total_allocated_boe_d=total_allocated,
        unallocated_boe_d=unallocated,
        results=results,
        assumptions=[
            "Candidates are allocated by rank order (ascending).",
            "No price optimization — first-fit by rank and capacity.",
            "Capacity figures are synthetic research estimates.",
        ],
        missing_inputs=missing,
        warnings=warnings,
        source_references=["synthetic-input"],
        lineage=["allocation-computation"],
        human_review_required=bool(missing or warnings or unallocated > 0),
    )
