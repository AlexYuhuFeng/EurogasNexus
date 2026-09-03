"""SDK client for European route-cost and resource optimization APIs."""

from __future__ import annotations

from urllib.parse import urlencode

from pydantic import BaseModel, Field

from eurogas_nexus_sdk import _http


class RouteCostTariff(BaseModel):
    """One published TSO tariff row used to price a route.

    Attributes:
        tariff_id: Stable identifier of the tariff entry.
        document_id: Identifier of the source tariff document.
        country: ISO country code of the TSO.
        tso: Transmission system operator code or name.
        market_area: Market area the tariff applies to.
        gas_year: Gas year the tariff is valid for (e.g. ``2025``).
        point_id: Reference-network point the tariff is attached to.
        source_point_name: Point name as it appears in the source document.
        direction: Flow direction the tariff applies to.
        capacity_product: Capacity product code (e.g. firm/interruptible).
        firmness: Firmness grade of the capacity product.
        tariff_value: Tariff amount in ``currency`` per ``unit``.
        currency: ISO currency code of the tariff value.
        unit: Pricing unit (e.g. EUR/MWh/d).
        tariff_status: Publication status of the tariff row.
        source_refs: References to the documents backing this row.
    """

    tariff_id: str
    document_id: str
    country: str
    tso: str
    market_area: str
    gas_year: str
    point_id: str
    source_point_name: str
    direction: str
    capacity_product: str
    firmness: str
    tariff_value: float
    currency: str
    unit: str
    tariff_status: str
    source_refs: list[str] = Field(default_factory=list)


class RouteCostComponent(BaseModel):
    """One cost component contributing to a route's total cost.

    Attributes:
        component_type: Kind of cost component (e.g. entry/exit/traversal).
        amount: Component amount in ``currency`` per ``unit``; None when the
            component could not be priced.
        currency: ISO currency code of the amount.
        unit: Pricing unit of the amount.
        tariff_id: Tariff row this component was priced from.
        source_refs: References to the source documents used.
        warning: Human-readable warning for this component.
        missing_input: Input that was missing while pricing this component.
    """

    component_type: str
    amount: float | None = None
    currency: str | None = None
    unit: str | None = None
    tariff_id: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    warning: str | None = None
    missing_input: str | None = None


class RouteCostResult(BaseModel):
    """Computed cost of one route across its priced legs.

    Attributes:
        scenario_id: Identifier of the scenario the cost was computed for.
        status: Overall computation status (e.g. ``COMPLETE``/``PARTIAL``).
        total_cost: Total route cost; None when no leg could be priced.
        currency: ISO currency code of the total cost.
        unit: Pricing unit of the total cost.
        cost_breakdown: Per-leg/per-component cost breakdown.
        used_tariff_documents: Documents whose tariffs were actually applied.
        missing_inputs: Inputs that were absent during the computation.
        warnings: Human-readable computation warnings.
        tariff_status_summary: Count of tariffs by status used in the run.
        required_tso_access: TSOs whose data was needed for this route.
        company_accessible_tsos: TSOs the company can access; None when the
            access check itself could not be performed.
        inaccessible_tsos: TSOs needed but not accessible to the company.
        research_only: True when the payload is a research-only envelope.
        human_review_required: True when output needs human review before use.
    """

    scenario_id: str
    # 状态用字符串而非枚举：状态值由后端契约定义并会随业务演进扩展，
    # 用枚举会让 SDK 在遇到未知新状态时校验失败，字符串保持向前兼容。
    status: str
    total_cost: float | None = None
    currency: str | None = None
    unit: str | None = None
    cost_breakdown: list[RouteCostComponent] = Field(default_factory=list)
    used_tariff_documents: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    tariff_status_summary: dict[str, int] = Field(default_factory=dict)
    # 同时给出可访问与不可访问的 TSO 清单：让调用方区分"缺授权/缺数据"
    # 与"市场确实不可达"，避免把权限问题误判为商业不可行。
    required_tso_access: list[str] = Field(default_factory=list)
    company_accessible_tsos: list[str] | None = None
    inaccessible_tsos: list[str] = Field(default_factory=list)
    # research_only 是共享信封 meta 的临时兼容字段（见 AGENTS.md）：
    # 只保留在既有结果载荷中，新业务数据载荷不得新增该字段。
    research_only: bool
    human_review_required: bool


class RouteAllocation(BaseModel):
    """Allocation of requested demand to one candidate route.

    Attributes:
        route_id: Reference-network identifier of the allocated route.
        route_name: Display name of the allocated route.
        destination_market: Destination market of the route, when known.
        allocated_mwh_per_day: Energy volume allocated to this route per day.
        route_cost: Cost per MWh for this route; None when not priced.
        currency: ISO currency code of the route cost.
        unit: Pricing unit of the route cost.
        sale_price: Expected sale price at destination, when provided.
        netback: Netback value (sale price minus route cost), when priced.
        rationale: Ordered reasons for choosing this route.
    """

    route_id: str
    route_name: str
    destination_market: str | None = None
    allocated_mwh_per_day: float
    route_cost: float | None = None
    currency: str | None = None
    unit: str | None = None
    sale_price: float | None = None
    netback: float | None = None
    rationale: list[str] = Field(default_factory=list)


class RouteRecommendationResult(BaseModel):
    """Recommendation for splitting requested demand across candidate routes.

    Attributes:
        request_id: Identifier of the allocation request.
        status: Overall recommendation status.
        total_requested_mwh_per_day: Total demand requested by the operator.
        total_allocated_mwh_per_day: Demand that could be allocated.
        unallocated_mwh_per_day: Demand left unallocated.
        allocations: Per-route allocations in priority order.
        excluded_routes: Candidate routes excluded, with exclusion reasons.
        warnings: Human-readable recommendation warnings.
        assumptions: Assumptions the recommendation relies on.
        research_only: True when the payload is a research-only envelope.
        human_review_required: True when output needs human review before use.
    """

    request_id: str
    status: str
    total_requested_mwh_per_day: float
    total_allocated_mwh_per_day: float
    unallocated_mwh_per_day: float
    allocations: list[RouteAllocation] = Field(default_factory=list)
    excluded_routes: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    research_only: bool
    human_review_required: bool


class LngRegasReadinessResult(BaseModel):
    """Readiness assessment for one LNG cargo regasification at a terminal.

    Attributes:
        contract_id: Identifier of the LNG contract the cargo belongs to.
        cargo_id: Identifier of the assessed cargo.
        terminal_id: Reference-network identifier of the regas terminal.
        terminal_name: Display name of the terminal.
        terminal_access_status: Whether the terminal is accessible.
        delivery_mode: Delivery mode of the cargo (e.g. FOB/DES).
        physical_entry_delivery_required: Whether physical entry delivery is
            required for this cargo.
        physical_entry_point_name: Entry point for physical delivery, when known.
        required_tso_access: TSOs whose data was needed for the assessment.
        inaccessible_tsos: TSOs needed but not accessible to the company.
        pricing_basis_status: Status of the cargo pricing basis.
        estimated_regas_duration_days: Estimated days needed for regas.
        available_slot_days: Slot days available at the terminal, when known.
        slot_capacity_mwh: Slot capacity available in MWh, when known.
        slot_capacity_shortfall_mwh: Shortfall versus cargo size, when positive.
        crosses_month: True when the window crosses a calendar month boundary.
        month_allocations: Per-month allocation of the slot window.
        missing_inputs: Inputs that were absent during the assessment.
        warnings: Human-readable assessment warnings.
        source_refs: References to the source documents used.
        research_only: True when the payload is a research-only envelope.
        human_review_required: True when output needs human review before use.
    """

    contract_id: str
    cargo_id: str
    terminal_id: str
    terminal_name: str
    terminal_access_status: str
    delivery_mode: str
    physical_entry_delivery_required: bool
    physical_entry_point_name: str | None = None
    required_tso_access: list[str] = Field(default_factory=list)
    inaccessible_tsos: list[str] = Field(default_factory=list)
    pricing_basis_status: str
    estimated_regas_duration_days: float | None = None
    available_slot_days: float | None = None
    slot_capacity_mwh: float | None = None
    slot_capacity_shortfall_mwh: float | None = None
    crosses_month: bool = False
    month_allocations: list[dict] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    research_only: bool
    human_review_required: bool


class PortfolioOptimizationResult(BaseModel):
    """Optimal allocation of a resource pool across candidate destinations.

    Attributes:
        portfolio_id: Identifier of the optimized resource pool.
        status: Overall optimization status.
        algorithm: Optimization algorithm used (default ``MIN_COST_FLOW``).
        optimality: Optimality certificate of the solution.
        total_allocated_mwh_per_day: Volume allocated per day.
        total_unallocated_mwh_per_day: Volume left unallocated per day.
        total_net_pnl_gbp_per_day: Net PnL of the allocation per day in GBP.
        allocations: Per-route/per-destination allocations.
        missing_inputs: Inputs that were absent during the optimization.
        assumptions: Assumptions the optimization relies on.
        warnings: Human-readable optimization warnings.
        source_refs: References to the source documents used.
        research_only: True when the payload is a research-only envelope.
        human_review_required: True when output needs human review before use.
    """

    portfolio_id: str
    status: str
    algorithm: str = "MIN_COST_FLOW"
    optimality: str = "OPTIMAL_FOR_LINEAR_MODEL"
    total_allocated_mwh_per_day: float
    total_unallocated_mwh_per_day: float
    total_net_pnl_gbp_per_day: float
    allocations: list[dict] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    research_only: bool
    human_review_required: bool


def _get(url: str) -> dict:
    """GET one route-cost endpoint and return the full response envelope."""

    response = _http.get(url, timeout=10)
    response.raise_for_status()
    # 与其余 SDK 模块统一：_get/_post 只负责返回信封本身，不假设载荷形状，
    # data 解包放在各 fetch 函数内（不同端点 data 形状不同）。
    return response.json()


def _post(url: str, json_body: dict) -> dict:
    """POST one route-cost payload and return the full response envelope."""

    response = _http.post(url, json=json_body, timeout=15)
    response.raise_for_status()
    # 同 _get：返回完整信封，调用方按端点形状解包 data。
    return response.json()


def fetch_tso_tariffs(
    base_url: str,
    *,
    country: str | None = None,
    tso: str | None = None,
    market_area: str | None = None,
    point_name: str | None = None,
    direction: str | None = None,
    gas_year: str | None = None,
) -> list[RouteCostTariff]:
    """Fetch published TSO tariffs, optionally filtered by the given criteria.

    Args:
        base_url: Base URL of the backend server.
        country: Only tariffs for this ISO country code.
        tso: Only tariffs from this TSO.
        market_area: Only tariffs for this market area.
        point_name: Only tariffs at this point name.
        direction: Only tariffs for this flow direction.
        gas_year: Only tariffs for this gas year.

    Returns:
        List of matching tariff rows; empty when none match.
    """

    params = [
        (key, value)
        for key, value in {
            "country": country,
            "tso": tso,
            "market_area": market_area,
            "point_name": point_name,
            "direction": direction,
            "gas_year": gas_year,
        }.items()
        if value is not None
    ]
    query = f"?{urlencode(params)}" if params else ""
    data = _get(f"{base_url}/api/route-cost/tso-tariffs{query}")["data"]
    return [RouteCostTariff(**row) for row in data["tariffs"]]


def fetch_route_candidates(base_url: str) -> list[dict]:
    """Fetch the candidate routes the route-cost service can price.

    Args:
        base_url: Base URL of the backend server.

    Returns:
        List of raw candidate-route records.
    """

    data = _get(f"{base_url}/api/route-cost/route-candidates")["data"]
    # 候选路由是后端动态生成的结构且字段随版本演进，SDK 不强行套 DTO，
    # 原样透传让调用方按需取用，避免字段漂移导致强类型解析失败。
    return data["route_candidates"]


def calculate_route_cost(base_url: str, **kwargs) -> RouteCostResult:
    """Compute the cost of a route from the given scenario inputs.

    Args:
        base_url: Base URL of the backend server.
        **kwargs: Scenario fields forwarded to the route-cost API.

    Returns:
        Computed route cost with breakdown, access and warning summary.
    """

    # 请求体以 **kwargs 原样透传：字段由后端 pydantic schema 定义并校验，
    # SDK 不重复声明，避免字段清单双份维护导致漂移。
    data = _post(f"{base_url}/api/route-cost/calculate", kwargs)["data"]
    return RouteCostResult(**data)


def recommend_route_allocation(base_url: str, **kwargs) -> RouteRecommendationResult:
    """Recommend how to split requested demand across candidate routes.

    Args:
        base_url: Base URL of the backend server.
        **kwargs: Request fields forwarded to the recommend API.

    Returns:
        Recommendation with per-route allocations and exclusions.
    """

    data = _post(f"{base_url}/api/route-cost/recommend", kwargs)["data"]
    return RouteRecommendationResult(**data)


def assess_lng_regas(base_url: str, **kwargs) -> LngRegasReadinessResult:
    """Assess regasification readiness for one LNG cargo at a terminal.

    Args:
        base_url: Base URL of the backend server.
        **kwargs: Cargo and terminal fields forwarded to the assess API.

    Returns:
        Readiness assessment with slot, access and pricing status.
    """

    data = _post(f"{base_url}/api/route-cost/lng-regas/assess", kwargs)["data"]
    return LngRegasReadinessResult(**data)


def optimize_resource_pool(base_url: str, **kwargs) -> PortfolioOptimizationResult:
    """Optimize the allocation of a resource pool across destinations.

    Args:
        base_url: Base URL of the backend server.
        **kwargs: Pool and destination fields forwarded to the optimize API.

    Returns:
        Optimal allocation with PnL, assumptions and warnings.
    """

    data = _post(f"{base_url}/api/route-cost/resource-pool/optimize", kwargs)["data"]
    return PortfolioOptimizationResult(**data)
