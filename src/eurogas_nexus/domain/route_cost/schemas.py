"""Route-cost scenario and result schemas."""

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
)


class RouteCostScenario(BaseModel):
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
    required_tso_access: list[str] = Field(default_factory=lambda: ["National Gas NTS"])
    company_accessible_tsos: list[str] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    research_only: bool = True


class CapacityRequirement(BaseModel):
    scenario_id: str
    required_components: list[CostComponentType] = Field(default_factory=list)
    entry_point_id: str | None = None
    exit_point_id: str | None = None
    missing_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    human_review_required: bool = False


class RouteCostComponent(BaseModel):
    component_type: CostComponentType
    amount: float | None = None
    currency: str | None = None
    unit: str | None = None
    tariff_id: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    warning: str | None = None
    missing_input: str | None = None


class RouteCostResult(BaseModel):
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
