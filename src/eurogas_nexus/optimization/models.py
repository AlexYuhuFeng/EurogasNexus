"""Domain models shared by the phase-two optimization engines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

OptimizationStatus = Literal["optimal", "feasible", "infeasible"]


@dataclass(frozen=True, slots=True)
class SupplyResource:
    """Daily gas resource available to the commercial optimizer."""

    resource_id: str
    available_mwh: float
    unit_cost_gbp_mwh: float
    minimum_take_mwh: float = 0.0
    maximum_take_mwh: float | None = None
    source_node: str | None = None
    required_tso_access: tuple[str, ...] = ()

    @property
    def effective_maximum_mwh(self) -> float:
        configured = self.maximum_take_mwh
        return min(self.available_mwh, configured) if configured is not None else self.available_mwh


@dataclass(frozen=True, slots=True)
class SaleOption:
    """Destination sale opportunity available to the optimizer."""

    option_id: str
    destination_node: str
    sale_price_gbp_mwh: float
    capacity_mwh: float
    variable_cost_gbp_mwh: float = 0.0
    required_tso_access: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ResourceAllocation:
    """A recommended allocation from one resource to one sale option."""

    resource_id: str
    option_id: str
    quantity_mwh: float
    unit_margin_gbp_mwh: float
    pnl_gbp: float


@dataclass(frozen=True, slots=True)
class NetworkEdge:
    """Directed gas-network edge used by the route optimizer."""

    edge_id: str
    source: str
    target: str
    tariff_gbp_mwh: float
    available_capacity_mwh: float
    tso: str | None = None
    enabled: bool = True


@dataclass(frozen=True, slots=True)
class RouteResult:
    """Capacity-feasible route recommendation."""

    status: OptimizationStatus
    edge_ids: tuple[str, ...]
    nodes: tuple[str, ...]
    total_cost_gbp_mwh: float | None
    bottleneck_capacity_mwh: float | None
    warnings: tuple[str, ...] = ()
    human_review_required: bool = True


@dataclass(frozen=True, slots=True)
class CapacityProduct:
    """Bookable transport-capacity product."""

    product_id: str
    capacity_mwh: float
    fixed_cost_gbp: float
    variable_cost_gbp_mwh: float = 0.0
    firmness: Literal["firm", "interruptible"] = "firm"


@dataclass(frozen=True, slots=True)
class CapacityBookingResult:
    """Recommended capacity product combination."""

    status: OptimizationStatus
    selected_product_ids: tuple[str, ...]
    total_capacity_mwh: float
    total_cost_gbp: float | None
    excess_capacity_mwh: float
    warnings: tuple[str, ...] = ()
    human_review_required: bool = True


@dataclass(frozen=True, slots=True)
class ContractDispatch:
    """Recommended daily take under one upstream contract."""

    resource_id: str
    quantity_mwh: float
    mandatory_quantity_mwh: float
    discretionary_quantity_mwh: float
    unit_margin_gbp_mwh: float
    pnl_gbp: float


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    """Portfolio-level optimization result."""

    status: OptimizationStatus
    objective_value_gbp: float
    allocations: tuple[ResourceAllocation, ...] = ()
    dispatches: tuple[ContractDispatch, ...] = ()
    unmet_minimum_take_mwh: float = 0.0
    unsold_volume_mwh: float = 0.0
    warnings: tuple[str, ...] = ()
    diagnostics: dict[str, float | int | str] = field(default_factory=dict)
    human_review_required: bool = True
