"""Route cost computation — research-only, no execution semantics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class CostComponent:
    """A single cost element on a route."""

    component_type: str  # "tariff", "fuel", "transport", "regas", "storage", "fx", "other"
    amount: float
    unit: str = "EUR/MWh"
    currency: str = "EUR"
    description: str = ""


@dataclass(frozen=True)
class RouteCostInput:
    """Input for route cost computation."""

    route_name: str
    from_node_id: str
    to_node_id: str
    components: list[CostComponent] = field(default_factory=list)
    route_km: float | None = None


@dataclass(frozen=True)
class RouteCostOutput:
    """Computed route cost with required research metadata."""

    route_name: str
    from_node_id: str
    to_node_id: str
    total_cost_eur_mwh: float
    total_cost_boe: float
    components: list[CostComponent]
    route_km: float | None = None
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
        return bool(self.missing_inputs or self.warnings)


def compute_route_cost(input_: RouteCostInput) -> RouteCostOutput:
    """Compute the total cost for a route from its components.

    Sums all component amounts to produce total_cost_eur_mwh.
    Converts to boe-equivalent using 1 MWh ≈ 0.1706 boe.
    """
    missing: list[str] = []
    warnings: list[str] = []
    assumptions: list[str] = [
        "Cost components are additive.",
        "1 MWh ≈ 0.1706 boe (approximate energy equivalence).",
        "FX components are applied at the rate provided.",
    ]

    if not input_.route_name:
        missing.append("route_name is required.")
    if not input_.from_node_id:
        missing.append("from_node_id is required.")
    if not input_.to_node_id:
        missing.append("to_node_id is required.")
    if not input_.components:
        warnings.append("No cost components provided; total cost is zero.")

    total_eur_mwh = sum(c.amount for c in input_.components)
    total_boe = total_eur_mwh * 0.1706

    return RouteCostOutput(
        route_name=input_.route_name,
        from_node_id=input_.from_node_id,
        to_node_id=input_.to_node_id,
        total_cost_eur_mwh=round(total_eur_mwh, 4),
        total_cost_boe=round(total_boe, 4),
        components=input_.components,
        route_km=input_.route_km,
        assumptions=assumptions,
        missing_inputs=missing,
        warnings=warnings,
        source_references=["synthetic-input"],
        lineage=["route-cost-computation"],
        research_only=True,
        human_review_required=bool(missing or warnings),
    )
