"""SDK client for the phase-two optimization and evidence APIs.

Covers ``/api/optimization/route|resource-pool|capacity|contracts`` and the
``/api/optimization/runs/{run_id}`` evidence endpoint. All requests go
through the release-profile auth headers (``sdk._http``); runtime-decision
contexts are passed through verbatim.
"""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, Field

from eurogas_nexus_sdk import _http
from eurogas_nexus_sdk._transport import ResponseMeta, SdkResult

DecisionContext = Literal["SANDBOX_SCENARIO", "RUNTIME_DECISION"]


class SupplyResourceInput(BaseModel):
    """Input describing one available upstream supply resource.

    Attributes:
        resource_id: Unique identifier of the resource.
        available_mwh: Total volume available from the resource.
        unit_cost_gbp_mwh: Marginal cost per MWh of using the resource.
        minimum_take_mwh: Minimum volume that must be taken if used.
        maximum_take_mwh: Maximum volume that can be taken; None when unlimited.
        source_node: Network node the resource is connected to; None when
            unknown.
        required_tso_access: TSOs whose access the resource requires.
    """

    resource_id: str
    available_mwh: float
    unit_cost_gbp_mwh: float
    minimum_take_mwh: float = 0
    maximum_take_mwh: float | None = None
    source_node: str | None = None
    required_tso_access: list[str] = Field(default_factory=list)


class SaleOptionInput(BaseModel):
    """Input describing one possible sale destination for allocated volume.

    Attributes:
        option_id: Unique identifier of the sale option.
        destination_node: Network node the volume is delivered to.
        sale_price_gbp_mwh: Selling price per MWh at the destination.
        capacity_mwh: Volume capacity of the sale option.
        variable_cost_gbp_mwh: Variable cost per MWh of selling there.
        required_tso_access: TSOs whose access the sale option requires.
    """

    option_id: str
    destination_node: str
    sale_price_gbp_mwh: float
    capacity_mwh: float
    variable_cost_gbp_mwh: float = 0
    required_tso_access: list[str] = Field(default_factory=list)


class NetworkEdgeInput(BaseModel):
    """Input describing one transport edge of the network graph.

    Attributes:
        edge_id: Unique identifier of the edge.
        source: Source node of the edge.
        target: Target node of the edge.
        tariff_gbp_mwh: Transport tariff per MWh on the edge.
        available_capacity_mwh: Remaining transport capacity on the edge.
        tso: TSO operating the edge; None when unknown.
        enabled: Whether the edge may be used by the optimizer.
    """

    edge_id: str
    source: str
    target: str
    tariff_gbp_mwh: float
    available_capacity_mwh: float
    tso: str | None = None
    enabled: bool = True


class CapacityProductInput(BaseModel):
    """Input describing one capacity product offered by a TSO.

    Attributes:
        product_id: Unique identifier of the capacity product.
        capacity_mwh: Capacity volume of the product.
        fixed_cost_gbp: Fixed cost of acquiring the product.
        variable_cost_gbp_mwh: Variable cost per MWh of using the product.
        firmness: Firmness of the product (``firm`` or ``interruptible``).
    """

    product_id: str
    capacity_mwh: float
    fixed_cost_gbp: float
    variable_cost_gbp_mwh: float = 0
    firmness: Literal["firm", "interruptible"] = "firm"


class RouteResultDTO(BaseModel):
    """Output of a minimum-cost route optimization.

    Attributes:
        status: Completion status of the optimization.
        edge_ids: Ordered edge identifiers of the chosen route.
        nodes: Ordered nodes traversed by the chosen route.
        total_cost_gbp_mwh: Total transport cost per MWh; None when infeasible.
        bottleneck_capacity_mwh: Capacity limiting the route; None when unknown.
        warnings: Non-blocking warnings about the result.
        human_review_required: Whether the result needs human review.
    """

    status: str
    edge_ids: list[str] = Field(default_factory=list)
    nodes: list[str] = Field(default_factory=list)
    total_cost_gbp_mwh: float | None = None
    bottleneck_capacity_mwh: float | None = None
    warnings: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class ResourcePoolResultDTO(BaseModel):
    """Output of a resource-pool allocation optimization.

    Attributes:
        status: Completion status of the optimization.
        objective_value_gbp: Value of the objective at the solution.
        allocations: Allocation decisions produced by the optimizer.
        dispatches: Dispatch decisions produced by the optimizer.
        unmet_minimum_take_mwh: Volume of minimum-take obligations unmet.
        unsold_volume_mwh: Volume that could not be sold.
        warnings: Non-blocking warnings about the result.
        diagnostics: Diagnostic details of the run.
        human_review_required: Whether the result needs human review.
    """

    status: str
    objective_value_gbp: float = 0.0
    allocations: list[dict] = Field(default_factory=list)
    dispatches: list[dict] = Field(default_factory=list)
    unmet_minimum_take_mwh: float = 0.0
    unsold_volume_mwh: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    diagnostics: dict = Field(default_factory=dict)
    human_review_required: bool = True


class CapacityResultDTO(BaseModel):
    """Output of a capacity product selection optimization.

    Attributes:
        status: Completion status of the optimization.
        selected_product_ids: Identifiers of the selected products.
        total_capacity_mwh: Total capacity acquired.
        total_cost_gbp: Total cost of the selection; None when not computed.
        excess_capacity_mwh: Capacity acquired beyond the requirement.
        warnings: Non-blocking warnings about the result.
        human_review_required: Whether the result needs human review.
    """

    status: str
    selected_product_ids: list[str] = Field(default_factory=list)
    total_capacity_mwh: float = 0.0
    total_cost_gbp: float | None = None
    excess_capacity_mwh: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class ContractResultDTO(BaseModel):
    """Output of a daily contract take recommendation.

    Attributes:
        status: Completion status of the optimization.
        objective_value_gbp: Value of the objective at the solution.
        allocations: Allocation decisions produced by the optimizer.
        dispatches: Dispatch decisions produced by the optimizer.
        unmet_minimum_take_mwh: Volume of minimum-take obligations unmet.
        unsold_volume_mwh: Volume that could not be sold.
        warnings: Non-blocking warnings about the result.
        diagnostics: Diagnostic details of the run.
        human_review_required: Whether the result needs human review.
    """

    status: str
    objective_value_gbp: float = 0.0
    allocations: list[dict] = Field(default_factory=list)
    dispatches: list[dict] = Field(default_factory=list)
    unmet_minimum_take_mwh: float = 0.0
    unsold_volume_mwh: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    diagnostics: dict = Field(default_factory=dict)
    human_review_required: bool = True


class StoragePeriodInput(BaseModel):
    """One storage dispatch period.

    Attributes:
        period_id: Stable period id.
        market_price_gbp_mwh: Market price, GBP/MWh.
    """

    period_id: str
    market_price_gbp_mwh: float


class StorageFacilityInput(BaseModel):
    """Storage facility parameters for dispatch assessment."""

    initial_inventory_mwh: float
    minimum_inventory_mwh: float
    maximum_inventory_mwh: float
    maximum_injection_mwh: float
    maximum_withdrawal_mwh: float
    injection_efficiency: float = 1.0
    withdrawal_efficiency: float = 1.0
    injection_cost_gbp_mwh: float = 0.0
    withdrawal_cost_gbp_mwh: float = 0.0
    terminal_inventory_mwh: float | None = None


class StorageDispatchResultDTO(BaseModel):
    """Output of the multi-period storage dispatch assessment."""

    status: str
    objective_value_gbp: float = 0.0
    decisions: list[dict] = Field(default_factory=list)
    terminal_inventory_mwh: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class NominationWindowInput(BaseModel):
    """One nomination/renomination window rule."""

    window_id: str
    opens_at: time
    closes_at: time
    maximum_change_mwh: float | None = None
    maximum_change_pct: float | None = None


class NominationInstructionInput(BaseModel):
    """One nomination/renomination instruction under assessment."""

    submitted_at: datetime
    requested_quantity_mwh: float


class NominationWindowResultDTO(BaseModel):
    """Output of the nomination-window assessment.

    This is an assessment result only; no submission action is represented.
    """

    status: str
    final_quantity_mwh: float = 0.0
    decisions: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    human_review_required: bool = True


class PortfolioNetworkResultDTO(BaseModel):
    """Output of the DB-composed portfolio network optimization.

    Attributes:
        status: Completion status of the optimization.
        objective_value_gbp: Portfolio objective value, GBP.
        served_demand_mwh: Volume allocated to sale options.
        unserved_demand_mwh: Remaining unsold sale-option capacity.
        total_revenue_gbp: Gross sale revenue of the final allocation.
        total_supply_cost_gbp: Acquisition cost of the used contract volume.
        total_network_cost_gbp: Tariff cost of the used route edges.
        edge_flows: Final flow on each used route edge.
        allocations: Source-to-sale path allocations.
        contract_attributions: PnL attribution per upstream contract.
        warnings: Non-blocking warnings about the run.
        diagnostics: Diagnostic details of the run.
        human_review_required: Whether the result needs human review.
    """

    status: str
    objective_value_gbp: float = 0.0
    served_demand_mwh: float = 0.0
    unserved_demand_mwh: float = 0.0
    total_revenue_gbp: float = 0.0
    total_supply_cost_gbp: float = 0.0
    total_network_cost_gbp: float = 0.0
    edge_flows: list[dict] = Field(default_factory=list)
    allocations: list[dict] = Field(default_factory=list)
    contract_attributions: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    diagnostics: dict = Field(default_factory=dict)
    human_review_required: bool = True


class OptimizationRunDTO(BaseModel):
    """Evidence record of one persisted optimization run.

    Attributes:
        run_id: Unique identifier of the run.
        optimization_type: Type of optimization that was executed.
        decision_context: Context the run was executed in (sandbox or runtime).
        status: Completion status of the run.
        input_snapshot: Snapshot of the run's inputs.
        output_snapshot: Snapshot of the run's outputs.
        source_refs: References to the underlying source records.
        warnings: Non-blocking warnings about the run.
        created_at_utc: Creation time of the run (ISO 8601).
        research_only: Whether the run is restricted to research use.
        human_review_required: Whether the run needs human review.
    """

    run_id: str
    optimization_type: str
    decision_context: str
    status: str
    input_snapshot: dict = Field(default_factory=dict)
    output_snapshot: dict = Field(default_factory=dict)
    source_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at_utc: str
    research_only: bool = True
    human_review_required: bool = True


def _post_envelope(
    url: str,
    body: dict,
    *,
    timeout: float = 15.0,
) -> tuple[dict, ResponseMeta]:
    """POST and split the public envelope (data + meta)."""

    response = _http.post(url, json=body, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    # 同时返回 data 与 meta：优化结果的 meta 携带 warnings/source_references，
    # 是证据重建与人工复核链路的一部分，调用方按需取用。
    return payload["data"], ResponseMeta.model_validate(payload["meta"])


def optimize_route(
    base_url: str,
    *,
    source: str,
    target: str,
    required_capacity_mwh: float,
    edges: list[NetworkEdgeInput] | list[dict],
    accessible_tsos: list[str] | None = None,
    decision_context: DecisionContext = "SANDBOX_SCENARIO",
) -> SdkResult[RouteResultDTO]:
    """Return a minimum-cost route satisfying capacity and TSO constraints."""

    data, meta = _post_envelope(
        _url(base_url, "optimization/route"),
        {
            "source": source,
            "target": target,
            "required_capacity_mwh": required_capacity_mwh,
            "accessible_tsos": accessible_tsos,
            "edges": [_as_dict(edge) for edge in edges],
            # 默认沙箱场景：RUNTIME_DECISION 只应在调用方显式要求时使用，
            # 避免日常调用意外进入运行时决策语义。
            "decision_context": decision_context,
        },
    )
    return SdkResult(data=RouteResultDTO.model_validate(data), meta=meta)


def optimize_resource_pool(
    base_url: str,
    *,
    resources: list[SupplyResourceInput] | list[dict],
    sale_options: list[SaleOptionInput] | list[dict],
    accessible_tsos: list[str] | None = None,
    decision_context: DecisionContext = "SANDBOX_SCENARIO",
    portfolio_id: str | None = None,
) -> SdkResult[ResourcePoolResultDTO]:
    """Allocate upstream resources across sale options (sandbox or DB snapshot)."""

    data, meta = _post_envelope(
        _url(base_url, "optimization/resource-pool"),
        {
            "portfolio_id": portfolio_id,
            "accessible_tsos": accessible_tsos,
            "resources": [_as_dict(resource) for resource in resources],
            "sale_options": [_as_dict(option) for option in sale_options],
            "decision_context": decision_context,
        },
    )
    return SdkResult(data=ResourcePoolResultDTO.model_validate(data), meta=meta)


def optimize_capacity(
    base_url: str,
    *,
    products: list[CapacityProductInput] | list[dict],
    required_capacity_mwh: float,
    expected_throughput_mwh: float | None = None,
    allow_interruptible: bool = True,
    decision_context: DecisionContext = "SANDBOX_SCENARIO",
) -> SdkResult[CapacityResultDTO]:
    """Choose the lowest-cost capacity product combination."""

    data, meta = _post_envelope(
        _url(base_url, "optimization/capacity"),
        {
            "products": [_as_dict(product) for product in products],
            "required_capacity_mwh": required_capacity_mwh,
            "expected_throughput_mwh": expected_throughput_mwh,
            "allow_interruptible": allow_interruptible,
            "decision_context": decision_context,
        },
    )
    return SdkResult(data=CapacityResultDTO.model_validate(data), meta=meta)


def optimize_contracts(
    base_url: str,
    *,
    resources: list[SupplyResourceInput] | list[dict],
    market_price_gbp_mwh: float,
    demand_limit_mwh: float,
    decision_context: DecisionContext = "SANDBOX_SCENARIO",
) -> SdkResult[ContractResultDTO]:
    """Recommend mandatory and discretionary daily contract takes."""

    data, meta = _post_envelope(
        _url(base_url, "optimization/contracts"),
        {
            "resources": [_as_dict(resource) for resource in resources],
            "market_price_gbp_mwh": market_price_gbp_mwh,
            "demand_limit_mwh": demand_limit_mwh,
            "decision_context": decision_context,
        },
    )
    return SdkResult(data=ContractResultDTO.model_validate(data), meta=meta)


def optimize_storage_dispatch(
    base_url: str,
    *,
    facility: StorageFacilityInput | dict | None = None,
    periods: list[StoragePeriodInput] | list[dict] | None = None,
    inventory_step_mwh: float = 1.0,
    decision_context: DecisionContext = "SANDBOX_SCENARIO",
    facility_id: str | None = None,
    gas_day: date | str | None = None,
    max_periods: int = 5,
) -> SdkResult[StorageDispatchResultDTO]:
    """Assess multi-period storage dispatch (no booking action)."""

    body: dict = {
        "inventory_step_mwh": inventory_step_mwh,
        "decision_context": decision_context,
        "max_periods": max_periods,
    }
    if facility is not None:
        body["facility"] = _as_dict(facility)
    if periods is not None:
        body["periods"] = [_as_dict(period) for period in periods]
    if facility_id is not None:
        body["facility_id"] = facility_id
    if gas_day is not None:
        body["gas_day"] = gas_day.isoformat() if isinstance(gas_day, date) else gas_day
    data, meta = _post_envelope(
        _url(base_url, "optimization/storage-dispatch"),
        body,
    )
    return SdkResult(data=StorageDispatchResultDTO.model_validate(data), meta=meta)


def optimize_nomination_window(
    base_url: str,
    *,
    initial_quantity_mwh: float,
    instructions: list[NominationInstructionInput] | list[dict],
    windows: list[NominationWindowInput] | list[dict] | None = None,
    decision_context: DecisionContext = "SANDBOX_SCENARIO",
    gas_day: date | str | None = None,
) -> SdkResult[NominationWindowResultDTO]:
    """Assess nomination windows; returns accepted quantities only."""

    body: dict = {
        "initial_quantity_mwh": initial_quantity_mwh,
        "instructions": [_as_dict(instruction) for instruction in instructions],
        "decision_context": decision_context,
    }
    if windows is not None:
        body["windows"] = [_as_dict(window) for window in windows]
    if gas_day is not None:
        body["gas_day"] = gas_day.isoformat() if isinstance(gas_day, date) else gas_day
    data, meta = _post_envelope(
        _url(base_url, "optimization/nomination-window"),
        body,
    )
    return SdkResult(data=NominationWindowResultDTO.model_validate(data), meta=meta)


def optimize_portfolio_network(
    base_url: str,
    *,
    portfolio_id: str,
    gas_day: date | str,
    capacity_product: str = "ANNUAL",
    firmness: str = "FIRM",
    max_market_price_age_hours: float = 72.0,
) -> SdkResult[PortfolioNetworkResultDTO]:
    """Optimize all DB-owned contracts and routes over a shared network.

    The client sends decision metadata only. Contracts, route topology,
    tariffs, capacities, TSO access, market prices, and FX rows are assembled
    by the backend from PostgreSQL.
    """

    data, meta = _post_envelope(
        _url(base_url, "optimization/portfolio-network"),
        {
            "portfolio_id": portfolio_id,
            "gas_day": gas_day.isoformat() if isinstance(gas_day, date) else gas_day,
            "capacity_product": capacity_product,
            "firmness": firmness,
            "max_market_price_age_hours": max_market_price_age_hours,
            # 固定 RUNTIME_DECISION：该端点只接受后端组装的事实快照，
            # 不允许 SDK 调用方传入网络、费率、管容或价格。
            "decision_context": "RUNTIME_DECISION",
        },
        timeout=30.0,
    )
    return SdkResult(data=PortfolioNetworkResultDTO.model_validate(data), meta=meta)


def fetch_optimization_run(
    base_url: str,
    run_id: str,
) -> SdkResult[OptimizationRunDTO]:
    """Return one persisted optimization run for evidence reconstruction."""

    response = _http.get(_url(base_url, f"optimization/runs/{run_id}"), timeout=10)
    response.raise_for_status()
    payload = response.json()
    return SdkResult(
        data=OptimizationRunDTO.model_validate(payload["data"]),
        meta=ResponseMeta.model_validate(payload["meta"]),
    )


def _as_dict(value: object) -> dict:
    """Serialize a raw dict or pydantic model to a JSON object."""

    # 兼容 dict 与 pydantic 输入 DTO：调用方两种写法都合法，
    # 统一序列化为 JSON 对象提交给后端契约。
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    raise TypeError(f"expected dict or pydantic model, got {type(value).__name__}")


def _url(base_url: str, path: str) -> str:
    """Join a base URL with a canonical ``/api`` path."""

    return f"{base_url.rstrip('/')}/api/{path.lstrip('/')}"
