"""Unified application service for phase-two optimization capabilities."""

from __future__ import annotations

from dataclasses import dataclass

from .capacity import optimize_capacity_bookings
from .contract import optimize_contract_dispatch
from .models import (
    CapacityBookingResult,
    CapacityProduct,
    NetworkEdge,
    OptimizationResult,
    RouteResult,
    SaleOption,
    SupplyResource,
)
from .resource_pool import optimize_resource_pool
from .route import find_min_cost_route


@dataclass(slots=True)
class PhaseTwoOptimizer:
    """Stable facade for route, resource, capacity, and contract optimization."""

    accessible_tsos: set[str] | None = None

    def optimize_route(
        self,
        edges: list[NetworkEdge],
        source: str,
        target: str,
        required_capacity_mwh: float,
    ) -> RouteResult:
        return find_min_cost_route(
            edges=edges,
            source=source,
            target=target,
            required_capacity_mwh=required_capacity_mwh,
            accessible_tsos=self.accessible_tsos,
        )

    def optimize_resource_pool(
        self,
        resources: list[SupplyResource],
        sale_options: list[SaleOption],
    ) -> OptimizationResult:
        return optimize_resource_pool(
            resources=resources,
            sale_options=sale_options,
            accessible_tsos=self.accessible_tsos,
        )

    def optimize_capacity(
        self,
        products: list[CapacityProduct],
        required_capacity_mwh: float,
        expected_throughput_mwh: float | None = None,
        allow_interruptible: bool = True,
    ) -> CapacityBookingResult:
        return optimize_capacity_bookings(
            products=products,
            required_capacity_mwh=required_capacity_mwh,
            expected_throughput_mwh=expected_throughput_mwh,
            allow_interruptible=allow_interruptible,
        )

    def optimize_contracts(
        self,
        resources: list[SupplyResource],
        market_price_gbp_mwh: float,
        demand_limit_mwh: float,
    ) -> OptimizationResult:
        return optimize_contract_dispatch(
            resources=resources,
            market_price_gbp_mwh=market_price_gbp_mwh,
            demand_limit_mwh=demand_limit_mwh,
        )
