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
        """Find the minimum-cost capacity-feasible route.

        最小成本可行路线：委托 route.find_min_cost_route 并施加本实例
        的 TSO 白名单。

        Args:
            edges: Candidate network edges.
            source: Source node.
            target: Target node.
            required_capacity_mwh: Volume to route, MWh.

        Returns:
            A RouteResult with edges, cost and bottleneck capacity.
        """

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
        """Optimize resource-to-sale allocation.

        资源池优化：把可用资源按边际分配到销售选项。

        Args:
            resources: Supply resources.
            sale_options: Sale options.

        Returns:
            An OptimizationResult with allocations and PnL.
        """

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
        """Select the best capacity product combination.

        容量组合优化：在容量产品中选出覆盖需求量且成本最低的组合。

        Args:
            products: Candidate capacity products.
            required_capacity_mwh: Volume to cover, MWh.
            expected_throughput_mwh: Expected throughput, or None.
            allow_interruptible: Whether interruptible products may be used.

        Returns:
            A CapacityBookingResult with selected products and cost.
        """

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
        """Optimize daily take under upstream contracts against a market.

        合约提气优化：在需求上限内按边际选择最优提气组合。

        Args:
            resources: Supply resources (with take bounds).
            market_price_gbp_mwh: Market price, GBP/MWh.
            demand_limit_mwh: Demand cap, MWh.

        Returns:
            An OptimizationResult with dispatches and PnL.
        """

        return optimize_contract_dispatch(
            resources=resources,
            market_price_gbp_mwh=market_price_gbp_mwh,
            demand_limit_mwh=demand_limit_mwh,
        )
