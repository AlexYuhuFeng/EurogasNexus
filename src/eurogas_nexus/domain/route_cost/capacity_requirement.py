"""Capacity requirement rules for route-cost scenarios.

容量需求推导规则：给定路由成本场景，判定需要哪些容量组件（入口/出口），
并在无法推导时上报 missing_inputs（不猜测）。终端所有权转移（title
transfer）场景不经过网络容量，直接短路返回。
"""

from __future__ import annotations

from eurogas_nexus.domain.route_cost.enums import (
    BusinessModel,
    CostComponentType,
    DeliveryMode,
    SourceResourceType,
)
from eurogas_nexus.domain.route_cost.schemas import CapacityRequirement, RouteCostScenario

# 需要入口容量的资源类型集合：海滩交付、LNG 再气化、管道进口、储气、合约池。
ENTRY_RESOURCE_TYPES = {
    SourceResourceType.BEACH_DELIVERY,
    SourceResourceType.LNG_REGAS,
    SourceResourceType.PIPELINE_IMPORT,
    SourceResourceType.STORAGE,
    SourceResourceType.CONTRACT_POOL,
}
# 已知虚拟枢纽代码：用于判定"目标是否为枢纽"（枢纽目标不需要出口点位映射）。
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
    """Return required capacity components without performing optimization.

    推导场景所需的容量组件清单（不执行优化）。

    Args:
        scenario: Route-cost scenario with resource type, delivery mode,
            business model and explicit capacity overrides.

    Returns:
        A CapacityRequirement listing required components, entry/exit point
        ids, missing inputs and warnings; ``human_review_required`` is True
        whenever anything is missing or warned.

    Raises:
        No exceptions; all derivation failures are reported in the result
        instead.
    """

    missing: list[str] = []
    warnings: list[str] = []
    components: list[CostComponentType] = []
    entry_point_id: str | None = None
    exit_point_id: str | None = None

    if _requires_entry_capacity(scenario):
        entry_point_id = scenario.start_point_id
        components.append(CostComponentType.ENTRY_CAPACITY)
    elif scenario.source_resource_type not in ENTRY_RESOURCE_TYPES:
        # 资源类型既不需要入口容量也不在已知集合：无法推导，显式上报缺失。
        missing.append("UNSUPPORTED_SOURCE_RESOURCE_TYPE")

    if _is_terminal_title_transfer(scenario):
        # 终端所有权转移：不涉及网络容量，直接返回当前结论。
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
            # 虚拟枢纽销售但目标不在已知枢纽清单：告警但继续（可能是新枢纽）。
            warnings.append("VIRTUAL_HUB_TARGET_NOT_RECOGNIZED")
    elif _requires_exit_capacity(scenario):
        components.append(CostComponentType.EXIT_CAPACITY)
        if (
            not scenario.target_hub_or_point_id
            or scenario.target_hub_or_point_id.upper() in VIRTUAL_HUBS
        ):
            # 需要出口容量但目标是空值或虚拟枢纽：缺出口点位映射。
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
    """Whether the scenario is a terminal title transfer (no network capacity)."""

    return scenario.delivery_mode is DeliveryMode.TERMINAL_TITLE_TRANSFER


def _requires_entry_capacity(scenario: RouteCostScenario) -> bool:
    """Whether the scenario needs an entry-capacity component.

    显式覆盖优先；否则按交付模式与资源类型推导：LNG 再气化仅在面向
    虚拟枢纽/物理交付时要求入口容量。
    """

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
    """Whether the scenario needs an exit-capacity component.

    显式覆盖优先；否则下游物理交付/边境转移必然需要出口容量，物理或
    跨境商业模型同理。
    """

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
