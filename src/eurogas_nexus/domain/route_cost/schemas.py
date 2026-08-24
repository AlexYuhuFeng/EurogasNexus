"""Route-cost scenario and result schemas.

路由成本链路的 Pydantic 数据契约：费率腿、场景、容量需求、成本组件
与结果信封。全部携带溯源与人工复核标记，禁止绕过契约传递裸 dict。
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

from eurogas_nexus.domain.route_cost.enums import (
    BusinessModel,
    CapacityProduct,
    CostComponentType,
    DeliveryMode,
    Firmness,
    SourceResourceType,
    TariffDirection,
)


class RouteTariffLeg(BaseModel):
    """One explicit TSO tariff leg of a route.

    Attributes:
        leg_id: Stable leg id (used in missing-input codes).
        country: Country of the leg.
        tso: TSO charging the leg.
        market_area: Market area filter, or None.
        point_name: Tariff point name.
        direction: Entry or exit direction.
        component_type: Cost component this leg contributes.
        gas_year: Leg gas year; falls back to the scenario when None.
        capacity_product: Leg product; falls back to the scenario.
        firmness: Leg firmness; falls back to the scenario.
    """

    leg_id: str
    country: str
    tso: str
    market_area: str | None = None
    point_name: str
    direction: TariffDirection
    component_type: CostComponentType = CostComponentType.ENTRY_CAPACITY
    gas_year: str | None = None
    capacity_product: CapacityProduct | None = None
    firmness: Firmness | None = None


class RouteCostScenario(BaseModel):
    """Input scenario for one route-cost calculation.

    Attributes:
        scenario_id: Stable scenario id.
        source_resource_type: Type of the source resource.
        start_point_id: Source point of the route.
        target_hub_or_point_id: Target hub/point.
        business_model: Commercial model.
        delivery_mode: Delivery mode, or None.
        gas_year: Gas year of the valuation.
        flow_quantity: Flow quantity, or None.
        flow_unit: Flow unit, or None.
        capacity_product: Capacity product requested.
        firmness: Firmness requested.
        requires_entry_capacity: Explicit entry-capacity override, or None.
        requires_exit_capacity: Explicit exit-capacity override, or None.
        required_tso_access: TSO access codes required.
        company_accessible_tsos: Company's accessible TSOs, or None.
        tariff_legs: Explicit tariff legs of the route.
        created_at: Scenario creation time.
        research_only: Always True — decision support only.
    """

    scenario_id: str
    source_resource_type: SourceResourceType
    start_point_id: str
    target_hub_or_point_id: str
    business_model: BusinessModel
    delivery_mode: DeliveryMode | None = None
    gas_year: str
    flow_quantity: float | None = None
    flow_unit: str | None = None
    capacity_product: CapacityProduct
    firmness: Firmness
    requires_entry_capacity: bool | None = None
    requires_exit_capacity: bool | None = None
    required_tso_access: list[str] = Field(default_factory=list)
    company_accessible_tsos: list[str] | None = None
    tariff_legs: list[RouteTariffLeg] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    research_only: bool = True


class CapacityRequirement(BaseModel):
    """Required capacity components derived from a scenario.

    Attributes:
        scenario_id: Owning scenario.
        required_components: Required cost-component types.
        entry_point_id: Entry point when entry capacity is required.
        exit_point_id: Exit point when exit capacity is required.
        missing_inputs: Inputs that blocked full derivation.
        warnings: Non-blocking issues.
        human_review_required: True when anything is missing/warned.
    """

    scenario_id: str
    required_components: list[CostComponentType] = Field(default_factory=list)
    entry_point_id: str | None = None
    exit_point_id: str | None = None
    missing_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    human_review_required: bool = False


class RouteCostComponent(BaseModel):
    """One cost component of the route-cost breakdown.

    Attributes:
        component_type: Kind of cost component.
        amount: Amount when priced, or None.
        currency: ISO 4217 code when priced.
        unit: Unit when priced.
        tariff_id: Selected tariff id, or None.
        source_refs: Provenance references.
        warning: Warning attached to this component, or None.
        missing_input: Missing-input code when not priced, or None.
    """

    component_type: CostComponentType
    amount: float | None = None
    currency: str | None = None
    unit: str | None = None
    tariff_id: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    warning: str | None = None
    missing_input: str | None = None


class RouteCostResult(BaseModel):
    """Result envelope of one route-cost calculation.

    Attributes:
        scenario_id: Owning scenario.
        status: SUCCESS / PARTIAL / BLOCKED.
        total_cost: Summed cost when computable, or None.
        currency: Uniform currency of the sum, or None.
        unit: Uniform unit of the sum, or None.
        cost_breakdown: Per-component breakdown.
        used_tariff_documents: Document ids actually used.
        missing_inputs: Inputs that blocked/limited the calculation.
        warnings: Aggregated warnings.
        tariff_status_summary: Count of tariff statuses used.
        required_tso_access: Echoed access requirement.
        company_accessible_tsos: Echoed access list.
        inaccessible_tsos: TSOs not accessible (fail-closed).
        research_only: Always True.
        human_review_required: True when anything needs review.
    """

    scenario_id: str
    status: str
    total_cost: float | None = None
    currency: str | None = None
    unit: str | None = None
    cost_breakdown: list[RouteCostComponent] = Field(default_factory=list)
    used_tariff_documents: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    tariff_status_summary: dict[str, int] = Field(default_factory=dict)
    required_tso_access: list[str] = Field(default_factory=list)
    company_accessible_tsos: list[str] | None = None
    inaccessible_tsos: list[str] = Field(default_factory=list)
    research_only: bool = True
    human_review_required: bool = False
