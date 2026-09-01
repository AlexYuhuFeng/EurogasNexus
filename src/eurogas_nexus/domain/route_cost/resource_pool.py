"""Portfolio resource-pool allocation and selling-option decision support.

The allocation engine is an exact minimum-cost flow over the bipartite
resource -> sale-option graph (successive shortest augmenting paths with a
Bellman-Ford shortest path pass on the residual graph). Unlike the previous
greedy marginal-PnL heuristic, an earlier allocation can be cancelled and
rerouted, so the result is optimal for the linear model.

Currency discipline (P0-3): resource costs and sale prices carry explicit
currency/unit fields. A pair whose cost currency or unit differs from the sale
price is excluded (fail-closed) — values in different currencies are never
silently mixed. Cross-currency conversion, when performed, happens at the API
boundary with as-of FX observations and explicit provenance.

本模块是组合优化（resource pool 分配）的唯一实现：求解器是精确最小费用流，
任何调用方不得退回贪心启发式；结果必须带 status/assumptions/warnings 等
决策支持字段，且永远标记 human_review_required（不执行交易或提名）。
"""

from __future__ import annotations

import math

from pydantic import BaseModel, Field, model_validator

from eurogas_nexus.domain.constraints.access import (
    inaccessible_tsos,
    tso_access_status,
)
from eurogas_nexus.domain.ontology.vocabulary import (
    AccessStatus,
    CapacityStatus,
    StatusKind,
)
from eurogas_nexus.domain.route_cost.enums import DeliveryMode, SourceResourceType

# 浮点比较容差：容量/路径成本判断统一使用，避免 1e-17 级别的噪声翻转结果。
_TOLERANCE = 1e-9
_EPSILON = 1e-9


class PortfolioResource(BaseModel):
    """One procurement resource available to the portfolio.

    Attributes:
        resource_id: Stable resource identifier.
        resource_name: Human-readable resource name.
        resource_type: Source resource type (e.g. pipeline, LNG, storage).
        delivery_mode: How the resource delivers (physical/terminal/title).
        location_point_name: Delivery point name.
        available_quantity_mwh_per_day: Daily volume available, MWh/d.
        contract_cost_gbp_mwh: Contract unit cost, in its own currency/unit.
        contract_cost_currency: ISO 4217 code of the cost currency.
        contract_cost_unit: Unit of the cost (e.g. ``GBP/MWh``).
        variable_cost_gbp_mwh: Variable unit cost in the same currency/unit.
        fuel_loss_allowance_pct: Fuel/shrinkage loss uplift applied to unit cost.
        delivery_tolerance_pct: Delivery tolerance, or None when unknown.
        nomination_tolerance_pct: Nomination tolerance, or None when unknown.
        tolerance_risk_allowance_gbp_mwh: Risk allowance for tolerances.
        upstream_payment_lag_days: Payment lag of the upstream contract.
        settlement_frequency: Settlement frequency (e.g. ``monthly``).
        required_tso_access: TSO access codes the route requires.
        accessible_tsos: Company's accessible TSOs, or None when unknown.
        pricing_method: Pricing method tag (e.g. ``FIXED_PRICE``).
        source_refs: Provenance references for the resource data.
    """

    resource_id: str
    resource_name: str
    resource_type: SourceResourceType
    delivery_mode: DeliveryMode
    location_point_name: str
    available_quantity_mwh_per_day: float
    contract_cost_gbp_mwh: float
    contract_cost_currency: str = "GBP"
    contract_cost_unit: str = "GBP/MWh"
    variable_cost_gbp_mwh: float = 0.0
    fuel_loss_allowance_pct: float = Field(default=0.0, ge=0, lt=100)
    delivery_tolerance_pct: float | None = None
    nomination_tolerance_pct: float | None = None
    tolerance_risk_allowance_gbp_mwh: float = 0.0
    upstream_payment_lag_days: int = 20
    screen_sale_cash_lag_days: int | None = Field(default=None, ge=0)
    settlement_frequency: str = "monthly"
    required_tso_access: list[str] = Field(default_factory=list)
    accessible_tsos: list[str] | None = None
    pricing_method: str = "FIXED_PRICE"
    source_refs: list[str] = Field(default_factory=list)


class PortfolioSaleOption(BaseModel):
    """One selling option the portfolio may allocate volume into.

    Attributes:
        option_id: Stable option identifier.
        label: Human-readable option label.
        delivery_mode: Required delivery mode of the sale.
        target_point_name: Sale target point.
        sale_price_gbp_mwh: Sale price, in its own currency/unit.
        sale_price_currency: ISO 4217 code of the price currency.
        sale_price_unit: Unit of the price (e.g. ``GBP/MWh``).
        route_cost_gbp_mwh: Route cost in the same currency/unit.
        capacity_limit_mwh_per_day: Network capacity limit, or None.
        capacity_status: Capacity state; see the validator below.
        screen_sale_cash_lag_days: Cash receipt lag of the sale.
        required_tso_access: TSO access codes the route requires.
        eligible_resource_ids: Resource ids allowed to use this option; empty means all.
        source_refs: Provenance references for the option data.
    """

    option_id: str
    label: str
    delivery_mode: DeliveryMode
    target_point_name: str
    sale_price_gbp_mwh: float
    sale_price_currency: str = "GBP"
    sale_price_unit: str = "GBP/MWh"
    route_cost_gbp_mwh: float = 0.0
    capacity_limit_mwh_per_day: float | None = None
    capacity_status: CapacityStatus = CapacityStatus.UNKNOWN
    screen_sale_cash_lag_days: int = 1
    required_tso_access: list[str] = Field(default_factory=list)
    eligible_resource_ids: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _infer_capacity_status(self) -> PortfolioSaleOption:
        """A supplied capacity limit implies KNOWN status.

        ``None`` capacity with UNKNOWN status must fail closed in the solver;
        only explicit NOT_REQUIRED means no network capacity is needed.

        校验规则：给了容量值就自动推断为 KNOWN；声明 KNOWN 却无容量值
        直接报错，防止求解器拿到自相矛盾的输入。
        """

        if self.capacity_limit_mwh_per_day is not None:
            self.capacity_status = CapacityStatus.KNOWN
        if self.capacity_status is CapacityStatus.KNOWN and (
            self.capacity_limit_mwh_per_day is None
        ):
            raise ValueError(
                f"Sale option {self.option_id!r} declares KNOWN capacity "
                "without a capacity_limit_mwh_per_day value."
            )
        return self


class PortfolioOptimizationScenario(BaseModel):
    """Input scenario: resources, sale options and financing assumptions.

    Attributes:
        portfolio_id: Portfolio identifier the result is attributed to.
        resources: Available procurement resources.
        sale_options: Candidate selling options.
        annual_financing_rate_pct: Annual financing rate for early-cash
            valuation (default 6.0).
        objective: Objective key (only ``MAX_DAILY_PNL`` is implemented).
        research_only: Compatibility flag; the result is always research-only.
    """

    portfolio_id: str
    resources: list[PortfolioResource]
    sale_options: list[PortfolioSaleOption]
    annual_financing_rate_pct: float = 6.0
    objective: str = "MAX_DAILY_PNL"
    research_only: bool = True


class PortfolioAllocation(BaseModel):
    """One optimal resource -> option allocation slice.

    Attributes:
        resource_id: Allocated resource.
        option_id: Target option.
        allocated_quantity_mwh_per_day: Allocated volume, MWh/d.
        gross_sale_price_gbp_mwh: Gross sale price (same currency/unit).
        total_cost_gbp_mwh: Total unit cost incl. early-cash credit.
        early_cash_value_gbp_mwh: Early-cash financing value per MWh.
        net_margin_gbp_mwh: Unit margin (price - total cost).
        net_pnl_gbp_per_day: Daily PnL of this slice.
        warnings: Slice-level warnings (TSO/capacity/currency issues).
    """

    resource_id: str
    option_id: str
    allocated_quantity_mwh_per_day: float
    gross_sale_price_gbp_mwh: float
    total_cost_gbp_mwh: float
    early_cash_value_gbp_mwh: float
    net_margin_gbp_mwh: float
    net_pnl_gbp_per_day: float
    warnings: list[str] = Field(default_factory=list)


class PortfolioOptimizationResult(BaseModel):
    """Decision-support result envelope of one optimization run.

    Attributes:
        portfolio_id: Portfolio the result belongs to.
        status: SUCCESS / PARTIAL / BLOCKED (see StatusKind).
        algorithm: Solver algorithm tag (``MIN_COST_FLOW``).
        optimality: Optimality statement for the supplied linear model.
        total_allocated_mwh_per_day: Total allocated volume, MWh/d.
        total_unallocated_mwh_per_day: Volume not allocated, MWh/d.
        total_net_pnl_gbp_per_day: Total daily PnL of allocations.
        allocations: Per-slice allocation breakdown.
        missing_inputs: Inputs absent from the scenario (e.g. tolerances).
        assumptions: Explicit modelling assumptions.
        warnings: Aggregated warnings across the run.
        source_refs: Provenance of all inputs used.
        research_only: Always True — decision support only.
        human_review_required: Always True — never auto-executes anything.
    """

    portfolio_id: str
    status: str
    algorithm: str = "MIN_COST_FLOW"
    optimality: str = "OPTIMAL_FOR_LINEAR_MODEL"
    total_allocated_mwh_per_day: float
    total_unallocated_mwh_per_day: float
    total_net_pnl_gbp_per_day: float
    allocations: list[PortfolioAllocation] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    research_only: bool = True
    human_review_required: bool = True


class _Bid(BaseModel):
    """One eligible resource -> option pairing (margin > 0, same currency).

    内部模型：只有正边际、币种/单位一致、访问与容量均确认的组合才会
    进入求解器；任何被排除的组合都以 warning 而非静默方式上报。
    """

    resource: PortfolioResource
    option: PortfolioSaleOption
    margin: float
    total_cost: float
    early_cash: float
    warnings: list[str] = Field(default_factory=list)


def optimize_resource_pool(
    scenario: PortfolioOptimizationScenario,
) -> PortfolioOptimizationResult:
    """Allocate portfolio resources to sale options by exact min-cost flow.

    组合分配的唯一入口：构造二分图后调用精确最小费用流求解器。

    The bipartite graph is super-source -> resources -> sale options ->
    super-sink. Resource arcs carry available quantity, option arcs carry sale
    capacity (or total volume for NOT_REQUIRED options), and resource->option
    arcs carry the negative unit margin. The solver augments along shortest
    residual paths while the path cost stays negative (positive margin), so an
    earlier allocation may be cancelled and rerouted when that improves the
    portfolio result.

    Args:
        scenario: Portfolio scenario with resources, sale options and
            financing assumptions.

    Returns:
        A PortfolioOptimizationResult with status, allocations, warnings,
        missing inputs, assumptions and provenance. Status is SUCCESS only
        when everything available was allocated with no missing inputs;
        otherwise PARTIAL (some allocation) or BLOCKED (none).

    Raises:
        RuntimeError: When the residual graph becomes inconsistent (negative
            cycle or broken predecessor chain) — never returns a wrong
            allocation silently.
    """

    missing_inputs: list[str] = []
    warnings: list[str] = []
    source_refs = _unique(
        [
            *[ref for resource in scenario.resources for ref in resource.source_refs],
            *[ref for option in scenario.sale_options for ref in option.source_refs],
        ]
    )

    # 先做资格过滤：不满足访问/容量/币种/单位约束的组合一律排除并告警。
    bids: list[_Bid] = []
    for resource in scenario.resources:
        resource_warnings = _resource_warnings(resource)
        missing_inputs.extend(_resource_missing_inputs(resource))
        for option in scenario.sale_options:
            pair_warnings = [*resource_warnings]
            if (
                option.eligible_resource_ids
                and resource.resource_id not in option.eligible_resource_ids
            ):
                continue
            required_access = _unique(
                [*resource.required_tso_access, *option.required_tso_access]
            )
            access_status = tso_access_status(required_access, resource.accessible_tsos)
            if access_status is AccessStatus.UNKNOWN:
                # 访问状态未知：fail-closed，该组合不可用。
                warnings.append("TSO_ACCESS_UNKNOWN:" + ",".join(required_access))
                continue
            if access_status is AccessStatus.DENIED:
                denied = inaccessible_tsos(required_access, resource.accessible_tsos)
                warnings.append("TSO_ACCESS_MISSING:" + ",".join(denied))
                continue
            if (
                option.capacity_status is CapacityStatus.UNKNOWN
                and option.capacity_limit_mwh_per_day is None
            ):
                # 容量未知且未声明 NOT_REQUIRED：不可放量。
                warnings.append(f"ROUTE_CAPACITY_UNKNOWN:{option.option_id}")
                continue
            if not _delivery_modes_compatible(resource.delivery_mode, option.delivery_mode):
                continue
            if not _currencies_compatible(resource, option):
                # 币种不一致：宁可排除也不做静默混算（P0-3）。
                warnings.append(
                    f"PRICE_COST_CURRENCY_MISMATCH:{resource.resource_id}:{option.option_id}"
                )
                continue
            if not _units_compatible(resource, option):
                warnings.append(
                    f"PRICE_COST_UNIT_MISMATCH:{resource.resource_id}:{option.option_id}"
                )
                continue
            early_cash = _early_cash_value_gbp_mwh(
                resource,
                option,
                annual_financing_rate_pct=scenario.annual_financing_rate_pct,
            )
            total_cost = (
                resource.contract_cost_gbp_mwh
                + resource.variable_cost_gbp_mwh
                + _fuel_loss_cost_gbp_mwh(resource)
                + resource.tolerance_risk_allowance_gbp_mwh
                + option.route_cost_gbp_mwh
                - early_cash
            )
            margin = round(option.sale_price_gbp_mwh - total_cost, 4)
            bids.append(
                _Bid(
                    resource=resource,
                    option=option,
                    margin=margin,
                    total_cost=total_cost,
                    early_cash=early_cash,
                    warnings=_unique(pair_warnings),
                )
            )

    # 非正边际的组合不进入流网络（流网络只承载盈利的增量）。
    positive_bids = [bid for bid in bids if bid.margin > 0]
    if len(positive_bids) != len(bids):
        warnings.append("NON_POSITIVE_MARGIN_OPTION_SKIPPED")

    allocations = _solve_min_cost_flow(scenario, positive_bids)

    total_available = round(
        sum(resource.available_quantity_mwh_per_day for resource in scenario.resources),
        4,
    )
    total_allocated = round(sum(item.allocated_quantity_mwh_per_day for item in allocations), 4)
    total_pnl = round(sum(item.net_pnl_gbp_per_day for item in allocations), 4)
    total_unallocated = round(max(total_available - total_allocated, 0.0), 4)
    if total_unallocated > 0:
        warnings.append("PORTFOLIO_VOLUME_UNALLOCATED")

    # 三态状态机：全部售出且无缺项=SUCCESS；有成交=PARTIAL；否则=BLOCKED。
    if allocations and total_unallocated == 0 and not missing_inputs:
        status = StatusKind.SUCCESS.value
    elif allocations:
        status = StatusKind.PARTIAL.value
    else:
        status = StatusKind.BLOCKED.value

    return PortfolioOptimizationResult(
        portfolio_id=scenario.portfolio_id,
        status=status,
        total_allocated_mwh_per_day=total_allocated,
        total_unallocated_mwh_per_day=total_unallocated,
        total_net_pnl_gbp_per_day=total_pnl,
        allocations=allocations,
        missing_inputs=_unique(missing_inputs),
        assumptions=[
            "The allocation model is linear and separable; the min-cost flow "
            "solver returns the exact optimum for the supplied inputs.",
            "Resource costs and sale prices are compared only within the same "
            "currency and unit; mismatched pairs are excluded (fail-closed).",
            "Cross-zone routes require confirmed TSO access and known capacity; "
            "unknown access or capacity blocks the pair.",
            "The result is decision support only; it does not execute trades "
            "or nominations.",
        ],
        warnings=_unique(warnings),
        source_refs=_unique(source_refs),
        research_only=True,
        human_review_required=True,
    )


# ---------------------------------------------------------------------------
# Exact min-cost flow solver (bipartite, successive shortest paths)
# ---------------------------------------------------------------------------


class _ResidualArc:
    """One directed arc of the residual graph (adjacency list cell).

    残量图弧：记录对偶反向弧的下标，增广时 O(1) 更新双向容量。
    """

    __slots__ = ("target", "reverse_index", "capacity", "unit_cost")

    def __init__(self, target: int, reverse_index: int, capacity: float, unit_cost: float):
        self.target = target
        self.reverse_index = reverse_index
        self.capacity = capacity
        self.unit_cost = unit_cost


def _solve_min_cost_flow(
    scenario: PortfolioOptimizationScenario,
    bids: list[_Bid],
) -> list[PortfolioAllocation]:
    """Return optimal allocations for the given positive-margin bids.

    精确最小费用流求解（successive shortest augmenting path + Bellman-Ford）。

    Args:
        scenario: Scenario supplying capacities and node ids.
        bids: Eligible (positive-margin, validated) resource->option bids.

    Returns:
        List of PortfolioAllocation slices, sorted by (option_id, resource_id).
        Empty when no bids or nothing is augmentable.

    Raises:
        RuntimeError: On inconsistent residual state (see callers).
    """

    if not bids:
        return []

    resource_ids = [resource.resource_id for resource in scenario.resources]
    option_ids = [option.option_id for option in scenario.sale_options]
    resource_index = {resource_id: index for index, resource_id in enumerate(resource_ids)}
    option_index = {option_id: index for index, option_id in enumerate(option_ids)}

    # 节点编号布局：0=超级源，1=超级汇，其后依次是资源节点与期权节点。
    total_volume = max(
        sum(max(resource.available_quantity_mwh_per_day, 0.0) for resource in scenario.resources),
        0.0,
    )
    resource_capacity = {
        resource.resource_id: max(resource.available_quantity_mwh_per_day, 0.0)
        for resource in scenario.resources
    }
    option_capacity: dict[str, float] = {}
    for option in scenario.sale_options:
        if option.capacity_status is CapacityStatus.NOT_REQUIRED:
            # NOT_REQUIRED 期权：容量视为不限（无显式上限时用总体积）。
            option_capacity[option.option_id] = (
                option.capacity_limit_mwh_per_day
                if option.capacity_limit_mwh_per_day is not None
                else total_volume
            )
        else:
            option_capacity[option.option_id] = option.capacity_limit_mwh_per_day or 0.0

    super_source = 0
    super_sink = 1
    node_count = 2 + len(resource_ids) + len(option_ids)
    graph: list[list[_ResidualArc]] = [[] for _ in range(node_count)]

    def resource_node(resource_id: str) -> int:
        return 2 + resource_index[resource_id]

    def option_node(option_id: str) -> int:
        return 2 + len(resource_ids) + option_index[option_id]

    # 建图：超级源 -> 资源（容量=可用量，费用 0）
    for resource in scenario.resources:
        _add_arc(
            graph,
            super_source,
            resource_node(resource.resource_id),
            resource_capacity[resource.resource_id],
            0.0,
        )
    # 资源 -> 期权（容量=双方较小值，费用=-边际）；期权 -> 超级汇（容量=期权容量）。
    arc_references: list[tuple[_Bid, int, int, float]] = []
    for bid in bids:
        capacity = min(
            resource_capacity[bid.resource.resource_id],
            option_capacity[bid.option.option_id],
        )
        if capacity <= _TOLERANCE:
            continue
        source_node = resource_node(bid.resource.resource_id)
        target_node = option_node(bid.option.option_id)
        arc_index = _add_arc(graph, source_node, target_node, capacity, -bid.margin)
        arc_references.append((bid, source_node, arc_index, capacity))
    for option in scenario.sale_options:
        _add_arc(
            graph,
            option_node(option.option_id),
            super_sink,
            option_capacity[option.option_id],
            0.0,
        )

    # 迭代增广：每次取残量图上"最便宜"的增广路（路径费用为负即边际为正）；
    # 找不到负费用路时已达到最优（线性模型下无环负费用路可再增广）。
    while True:
        path = _shortest_residual_path(graph, super_source, super_sink)
        if path is None:
            break
        path_cost, predecessors = path
        if path_cost >= -_EPSILON:
            break
        quantity = _path_capacity(graph, predecessors, super_source, super_sink)
        if quantity <= _TOLERANCE:
            raise RuntimeError("Residual path has no augmentable capacity")
        _augment_path(graph, predecessors, super_source, super_sink, quantity)

    # 从"初始容量 - 剩余容量"反推每条资源->期权弧的实际流量。
    allocations: list[PortfolioAllocation] = []
    for bid, source_node, arc_index, initial_capacity in arc_references:
        quantity = initial_capacity - graph[source_node][arc_index].capacity
        if quantity <= _TOLERANCE:
            continue
        pnl = round(bid.margin * quantity, 4)
        allocations.append(
            PortfolioAllocation(
                resource_id=bid.resource.resource_id,
                option_id=bid.option.option_id,
                allocated_quantity_mwh_per_day=round(quantity, 4),
                gross_sale_price_gbp_mwh=bid.option.sale_price_gbp_mwh,
                total_cost_gbp_mwh=round(bid.total_cost, 4),
                early_cash_value_gbp_mwh=round(bid.early_cash, 4),
                net_margin_gbp_mwh=bid.margin,
                net_pnl_gbp_per_day=pnl,
                warnings=_unique(bid.warnings),
            )
        )
    allocations.sort(key=lambda item: (item.option_id, item.resource_id))
    return allocations


def _add_arc(
    graph: list[list[_ResidualArc]],
    source: int,
    target: int,
    capacity: float,
    unit_cost: float,
) -> int:
    """Add a directed arc plus its reverse residual arc.

    成对添加正向弧与反向弧；返回正向弧在 source 邻接表中的下标，供
    增广后按"初始容量-剩余容量"反推流量使用。

    Args:
        graph: Residual adjacency list.
        source: Tail node index.
        target: Head node index.
        capacity: Forward capacity.
        unit_cost: Forward unit cost (negative margin for bid arcs).

    Returns:
        Index of the forward arc within ``graph[source]``.
    """

    forward_index = len(graph[source])
    reverse_index = len(graph[target])
    graph[source].append(
        _ResidualArc(target, reverse_index, capacity, unit_cost)
    )
    graph[target].append(
        _ResidualArc(source, forward_index, 0.0, -unit_cost)
    )
    return forward_index


def _shortest_residual_path(
    graph: list[list[_ResidualArc]],
    source: int,
    target: int,
) -> tuple[float, list[tuple[int, int] | None]] | None:
    """Bellman-Ford shortest path on the residual graph (negative costs OK).

    残量图可能含负费用弧（-margin），因此用 Bellman-Ford 而不是 Dijkstra；
    负费用环意味着模型定义有误，直接抛错而非给出错误分配。

    Args:
        graph: Residual adjacency list.
        source: Super-source node index.
        target: Super-sink node index.

    Returns:
        Tuple ``(path_cost, predecessors)`` where each predecessor entry is
        ``(previous_node, arc_index)``; None when target is unreachable.

    Raises:
        RuntimeError: When a negative-cost residual cycle is detected.
    """

    distances = [float("inf")] * len(graph)
    predecessors: list[tuple[int, int] | None] = [None] * len(graph)
    distances[source] = 0.0

    # 至多 V-1 轮松弛；一轮无更新即提前收敛。
    for _ in range(len(graph) - 1):
        changed = False
        for node, arcs in enumerate(graph):
            if math.isinf(distances[node]):
                continue
            for arc_index, arc in enumerate(arcs):
                if arc.capacity <= _TOLERANCE:
                    continue
                candidate = distances[node] + arc.unit_cost
                if candidate < distances[arc.target] - _EPSILON:
                    distances[arc.target] = candidate
                    predecessors[arc.target] = (node, arc_index)
                    changed = True
        if not changed:
            break

    # 第 V 轮检查：仍能松弛即存在负费用环（线性模型下不应出现）。
    for node, arcs in enumerate(graph):
        if math.isinf(distances[node]):
            continue
        for arc in arcs:
            if arc.capacity <= _TOLERANCE:
                continue
            if distances[node] + arc.unit_cost < distances[arc.target] - _EPSILON:
                raise RuntimeError("Negative residual cycle detected")

    if math.isinf(distances[target]):
        return None
    return distances[target], predecessors


def _path_capacity(
    graph: list[list[_ResidualArc]],
    predecessors: list[tuple[int, int] | None],
    source: int,
    target: int,
) -> float:
    """Return the bottleneck capacity along the predecessor chain.

    Args:
        graph: Residual adjacency list.
        predecessors: Predecessor chain from Bellman-Ford.
        source: Super-source node index.
        target: Super-sink node index.

    Returns:
        Minimum residual capacity along the path (positive).

    Raises:
        RuntimeError: When the chain is cyclic or incomplete.
    """

    capacity = float("inf")
    cursor = target
    visited: set[int] = set()
    while cursor != source:
        if cursor in visited:
            raise RuntimeError("Residual predecessor chain contains a cycle")
        visited.add(cursor)
        predecessor = predecessors[cursor]
        if predecessor is None:
            raise RuntimeError("Residual predecessor chain is incomplete")
        previous, arc_index = predecessor
        capacity = min(capacity, graph[previous][arc_index].capacity)
        cursor = previous
    return capacity


def _augment_path(
    graph: list[list[_ResidualArc]],
    predecessors: list[tuple[int, int] | None],
    source: int,
    target: int,
    quantity: float,
) -> None:
    """Push ``quantity`` along the path, updating forward and reverse arcs.

    沿增广路推送流量：正向弧容量减少、反向弧容量增加（允许后续迭代
    取消本次分配并改道，这是与贪心算法的本质区别）。

    Args:
        graph: Residual adjacency list (mutated in place).
        predecessors: Predecessor chain from Bellman-Ford.
        source: Super-source node index.
        target: Super-sink node index.
        quantity: Amount to push (positive).

    Raises:
        RuntimeError: When the chain is incomplete.
    """

    cursor = target
    while cursor != source:
        predecessor = predecessors[cursor]
        if predecessor is None:
            raise RuntimeError("Residual predecessor chain is incomplete")
        previous, arc_index = predecessor
        arc = graph[previous][arc_index]
        reverse = graph[arc.target][arc.reverse_index]
        arc.capacity = max(arc.capacity - quantity, 0.0)
        reverse.capacity += quantity
        cursor = previous


# ---------------------------------------------------------------------------
# Compatibility and valuation helpers
# ---------------------------------------------------------------------------


def _currencies_compatible(resource: PortfolioResource, option: PortfolioSaleOption) -> bool:
    """Whether the cost and sale price currencies match (normalised)."""

    return _normalise_currency(resource.contract_cost_currency) == _normalise_currency(
        option.sale_price_currency
    )


def _units_compatible(resource: PortfolioResource, option: PortfolioSaleOption) -> bool:
    """Whether the cost and sale price units match (normalised)."""

    return _normalise_unit(resource.contract_cost_unit) == _normalise_unit(
        option.sale_price_unit
    )


def _normalise_currency(value: str) -> str:
    """Normalise a currency code for comparison (trim + uppercase)."""

    return (value or "").strip().upper()


def _normalise_unit(value: str) -> str:
    """Normalise a unit string for comparison (trim + uppercase)."""

    return (value or "").strip().upper()


def _delivery_modes_compatible(
    resource_mode: DeliveryMode,
    option_mode: DeliveryMode,
) -> bool:
    """Whether a resource's delivery mode can serve an option's mode.

    兼容规则：同模式必然兼容；物理入场交付可供应虚拟枢纽销售与下游
    物理交付；终端所有权转移只与同类兼容（其余组合一律排除）。
    """

    if resource_mode == option_mode:
        return True
    if resource_mode is DeliveryMode.PHYSICAL_ENTRY_DELIVERY and option_mode in {
        DeliveryMode.VIRTUAL_HUB_SALE,
        DeliveryMode.DOWNSTREAM_PHYSICAL_DELIVERY,
    }:
        return True
    if resource_mode is DeliveryMode.TERMINAL_TITLE_TRANSFER:
        return option_mode is DeliveryMode.TERMINAL_TITLE_TRANSFER
    return False


def _resource_missing_inputs(resource: PortfolioResource) -> list[str]:
    """List missing required inputs of a resource (tolerance fields).

    交付/提名容差缺失不阻断分配，但必须在 missing_inputs 中显式上报，
    用于结果的状态判定（有缺项时最高只能 PARTIAL）。
    """

    missing: list[str] = []
    if resource.delivery_tolerance_pct is None:
        missing.append(f"DELIVERY_TOLERANCE_MISSING:{resource.resource_id}")
    if resource.nomination_tolerance_pct is None:
        missing.append(f"NOMINATION_TOLERANCE_MISSING:{resource.resource_id}")
    return missing


def _resource_warnings(resource: PortfolioResource) -> list[str]:
    """Warnings for a resource (e.g. unknown pricing method)."""

    warnings: list[str] = []
    if resource.pricing_method.upper() not in {
        "FIXED_PRICE",
        "DAILY_INDEX",
        "MONTHLY_INDEX",
        "TTF",
        "NBP",
        "BRENT",
        "ICIS",
        "PLATTS",
        "FORMULA",
    }:
        # 未识别的定价方法：结果仍可用，但必须告警提示人工核对。
        warnings.append(f"UNKNOWN_PRICING_METHOD:{resource.resource_id}")
    return warnings


def _early_cash_value_gbp_mwh(
    resource: PortfolioResource,
    option: PortfolioSaleOption,
    *,
    annual_financing_rate_pct: float,
) -> float:
    """Financing value of earlier cash receipt per MWh.

    早收现金价值：上游付款滞后与销售回款滞后之差（天）乘以融资利率，
    折算为每 MWh 的成本抵减；滞后差为负时取 0（不产生负抵减）。

    Args:
        resource: The upstream resource.
        option: The selling option.
        annual_financing_rate_pct: Annual financing rate in percent.

    Returns:
        Round(4) early-cash credit per MWh in the cost currency/unit.
    """

    screen_lag_days = (
        resource.screen_sale_cash_lag_days
        if resource.screen_sale_cash_lag_days is not None
        else option.screen_sale_cash_lag_days
    )
    lag_days = max(resource.upstream_payment_lag_days - screen_lag_days, 0)
    annual_rate = annual_financing_rate_pct / 100
    base_cost = (
        resource.contract_cost_gbp_mwh
        + resource.variable_cost_gbp_mwh
        + _fuel_loss_cost_gbp_mwh(resource)
    )
    return round(base_cost * annual_rate * lag_days / 365, 4)


def _fuel_loss_cost_gbp_mwh(resource: PortfolioResource) -> float:
    """Uplift delivered-unit cost for contractual fuel/shrinkage loss."""

    loss_fraction = resource.fuel_loss_allowance_pct / 100
    if loss_fraction <= 0:
        return 0.0
    base_cost = resource.contract_cost_gbp_mwh + resource.variable_cost_gbp_mwh
    return round(base_cost / (1 - loss_fraction) - base_cost, 4)


def _unique(values: list[str]) -> list[str]:
    """Deduplicate preserving first-seen order."""

    return list(dict.fromkeys(values))
