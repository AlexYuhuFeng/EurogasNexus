"""Capacity requirement tests for European route-cost scenarios."""

from datetime import UTC, datetime

from eurogas_nexus.domain.route_cost.capacity_requirement import (
    build_capacity_requirement,
)
from eurogas_nexus.domain.route_cost.enums import (
    BusinessModel,
    CapacityProduct,
    CostComponentType,
    DeliveryMode,
    Firmness,
    SourceResourceType,
)
from eurogas_nexus.domain.route_cost.schemas import RouteCostScenario


def _scenario(business_model: BusinessModel, target: str) -> RouteCostScenario:
    return RouteCostScenario(
        scenario_id=f"scenario-{business_model.value.lower()}",
        source_resource_type=SourceResourceType.LNG_REGAS,
        start_point_id="GATE LNG",
        target_hub_or_point_id=target,
        business_model=business_model,
        delivery_mode=DeliveryMode.VIRTUAL_HUB_SALE
        if business_model is BusinessModel.VIRTUAL_HUB_SALE
        else DeliveryMode.DOWNSTREAM_PHYSICAL_DELIVERY,
        gas_year="2025/26",
        capacity_product=CapacityProduct.DAILY,
        firmness=Firmness.FIRM,
        created_at=datetime.now(UTC),
    )


def test_virtual_ttf_sale_requires_entry_capacity_only() -> None:
    requirement = build_capacity_requirement(
        _scenario(BusinessModel.VIRTUAL_HUB_SALE, "TTF")
    )

    assert requirement.required_components == [CostComponentType.ENTRY_CAPACITY]
    assert requirement.entry_point_id == "GATE LNG"
    assert requirement.exit_point_id is None
    assert requirement.missing_inputs == []


def test_physical_delivery_requires_entry_and_exit_capacity() -> None:
    requirement = build_capacity_requirement(
        _scenario(BusinessModel.PHYSICAL_DELIVERY, "Balzand BBL")
    )

    assert requirement.required_components == [
        CostComponentType.ENTRY_CAPACITY,
        CostComponentType.EXIT_CAPACITY,
    ]
    assert requirement.entry_point_id == "GATE LNG"
    assert requirement.exit_point_id == "Balzand BBL"
    assert requirement.missing_inputs == []


def test_physical_delivery_without_exit_mapping_reports_missing_input() -> None:
    requirement = build_capacity_requirement(
        _scenario(BusinessModel.PHYSICAL_DELIVERY, "TTF")
    )

    assert CostComponentType.EXIT_CAPACITY in requirement.required_components
    assert "EXIT_POINT_MAPPING_MISSING" in requirement.missing_inputs
    assert requirement.human_review_required is True

