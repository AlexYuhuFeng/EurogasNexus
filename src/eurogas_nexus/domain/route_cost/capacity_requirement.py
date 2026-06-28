"""Capacity requirement rules for route-cost scenarios."""

from __future__ import annotations

from eurogas_nexus.domain.route_cost.enums import (
    BusinessModel,
    CostComponentType,
    DeliveryMode,
    SourceResourceType,
)
from eurogas_nexus.domain.route_cost.schemas import CapacityRequirement, RouteCostScenario

ENTRY_RESOURCE_TYPES = {
    SourceResourceType.BEACH_DELIVERY,
    SourceResourceType.LNG_REGAS,
    SourceResourceType.PIPELINE_IMPORT,
    SourceResourceType.STORAGE,
    SourceResourceType.CONTRACT_POOL,
}
VIRTUAL_HUBS = {
    "CEGH",
    "NBP",
    "PEG",
    "PSV",
    "PVB",
    "THE",
    "TTF",
    "ZTP",
}


def build_capacity_requirement(scenario: RouteCostScenario) -> CapacityRequirement:
    """Return required capacity components without performing optimization."""

    missing: list[str] = []
    warnings: list[str] = []
    components: list[CostComponentType] = []
    entry_point_id: str | None = None
    exit_point_id: str | None = None

    if _requires_entry_capacity(scenario):
        entry_point_id = scenario.start_point_id
        components.append(CostComponentType.ENTRY_CAPACITY)
    elif scenario.source_resource_type not in ENTRY_RESOURCE_TYPES:
        missing.append("UNSUPPORTED_SOURCE_RESOURCE_TYPE")

    if _is_terminal_title_transfer(scenario):
        return CapacityRequirement(
            scenario_id=scenario.scenario_id,
            required_components=components,
            entry_point_id=entry_point_id,
            exit_point_id=exit_point_id,
            missing_inputs=missing,
            warnings=warnings,
            human_review_required=bool(missing or warnings),
        )

    if scenario.business_model is BusinessModel.VIRTUAL_HUB_SALE:
        if scenario.target_hub_or_point_id.upper() not in VIRTUAL_HUBS:
            warnings.append("VIRTUAL_HUB_TARGET_NOT_RECOGNIZED")
    elif _requires_exit_capacity(scenario):
        components.append(CostComponentType.EXIT_CAPACITY)
        if (
            not scenario.target_hub_or_point_id
            or scenario.target_hub_or_point_id.upper() in VIRTUAL_HUBS
        ):
            missing.append("EXIT_POINT_MAPPING_MISSING")
        else:
            exit_point_id = scenario.target_hub_or_point_id
    else:
        missing.append("UNSUPPORTED_BUSINESS_MODEL")

    return CapacityRequirement(
        scenario_id=scenario.scenario_id,
        required_components=components,
        entry_point_id=entry_point_id,
        exit_point_id=exit_point_id,
        missing_inputs=missing,
        warnings=warnings,
        human_review_required=bool(missing or warnings),
    )


def _is_terminal_title_transfer(scenario: RouteCostScenario) -> bool:
    return scenario.delivery_mode is DeliveryMode.TERMINAL_TITLE_TRANSFER


def _requires_entry_capacity(scenario: RouteCostScenario) -> bool:
    if scenario.requires_entry_capacity is not None:
        return scenario.requires_entry_capacity
    if scenario.delivery_mode is DeliveryMode.TERMINAL_TITLE_TRANSFER:
        return False
    if scenario.source_resource_type is SourceResourceType.LNG_REGAS:
        return scenario.delivery_mode in {
            DeliveryMode.VIRTUAL_HUB_SALE,
            DeliveryMode.PHYSICAL_ENTRY_DELIVERY,
            DeliveryMode.DOWNSTREAM_PHYSICAL_DELIVERY,
        }
    return scenario.source_resource_type in ENTRY_RESOURCE_TYPES


def _requires_exit_capacity(scenario: RouteCostScenario) -> bool:
    if scenario.requires_exit_capacity is not None:
        return scenario.requires_exit_capacity
    if scenario.delivery_mode in {
        DeliveryMode.DOWNSTREAM_PHYSICAL_DELIVERY,
        DeliveryMode.BORDER_TRANSFER,
    }:
        return True
    return scenario.business_model in {
        BusinessModel.PHYSICAL_DELIVERY,
        BusinessModel.CROSS_BORDER_TRANSFER,
    }
