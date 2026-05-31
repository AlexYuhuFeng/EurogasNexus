"""Research-only route-cost calculation service."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from eurogas_nexus.domain.route_cost.capacity_requirement import build_capacity_requirement
from eurogas_nexus.domain.route_cost.enums import (
    CostComponentType,
    TariffDirection,
)
from eurogas_nexus.domain.route_cost.schemas import (
    RouteCostComponent,
    RouteCostResult,
    RouteCostScenario,
)
from eurogas_nexus.domain.route_cost.tariff_models import CapacityTariff
from eurogas_nexus.domain.route_cost.tariff_selection import select_latest_tariff


def calculate_route_cost(
    scenario: RouteCostScenario,
    tariffs: Sequence[CapacityTariff],
) -> RouteCostResult:
    """Calculate a traceable tariff cost without unit conversion or trading semantics."""

    requirement = build_capacity_requirement(scenario)
    components: list[RouteCostComponent] = []
    missing_inputs = list(requirement.missing_inputs)
    warnings = list(requirement.warnings)
    used_documents: set[str] = set()
    tariff_statuses: Counter[str] = Counter()
    human_review_required = requirement.human_review_required
    inaccessible_tsos = _inaccessible_tsos(
        scenario.required_tso_access,
        scenario.company_accessible_tsos,
    )
    if inaccessible_tsos:
        missing_inputs.extend(f"TSO_ACCESS_MISSING:{tso}" for tso in inaccessible_tsos)
        warnings.append("ROUTE_BLOCKED_BY_TSO_ACCESS")
        human_review_required = True

    for required_component in requirement.required_components:
        point_name = _point_name_for_component(required_component, requirement)
        if point_name is None:
            continue
        selection = select_latest_tariff(
            tariffs,
            country="UK",
            tso="National Gas NTS",
            point_name=point_name,
            direction=_direction_for_component(required_component),
            gas_year=scenario.gas_year,
            capacity_product=scenario.capacity_product,
            firmness=scenario.firmness,
        )
        warnings.extend(selection.warnings)
        human_review_required = human_review_required or selection.human_review_required
        if selection.selected_tariff is None:
            missing_inputs.append(_missing_code_for_component(required_component))
            components.append(
                RouteCostComponent(
                    component_type=required_component,
                    missing_input=_missing_code_for_component(required_component),
                )
            )
            continue

        tariff = selection.selected_tariff
        used_documents.add(tariff.document_id)
        tariff_statuses[tariff.tariff_status.value] += 1
        components.append(
            RouteCostComponent(
                component_type=required_component,
                amount=tariff.tariff_value,
                currency=tariff.currency,
                unit=tariff.unit,
                tariff_id=tariff.tariff_id,
                source_refs=tariff.source_refs,
            )
        )

    total_cost, currency, unit, unit_warnings = _sum_compatible_components(components)
    warnings.extend(unit_warnings)

    status = "SUCCESS"
    if missing_inputs or unit_warnings:
        has_priced_components = any(component.amount is not None for component in components)
        status = "PARTIAL" if has_priced_components else "BLOCKED"
        human_review_required = True
    if inaccessible_tsos:
        status = "BLOCKED"

    return RouteCostResult(
        scenario_id=scenario.scenario_id,
        status=status,
        total_cost=total_cost,
        currency=currency,
        unit=unit,
        cost_breakdown=components,
        used_tariff_documents=sorted(used_documents),
        missing_inputs=_unique(missing_inputs),
        warnings=_unique(warnings),
        tariff_status_summary=dict(tariff_statuses),
        required_tso_access=scenario.required_tso_access,
        company_accessible_tsos=scenario.company_accessible_tsos,
        inaccessible_tsos=inaccessible_tsos,
        research_only=True,
        human_review_required=human_review_required,
    )


def _point_name_for_component(
    component: CostComponentType,
    requirement,
) -> str | None:
    if component is CostComponentType.ENTRY_CAPACITY:
        return requirement.entry_point_id
    if component is CostComponentType.EXIT_CAPACITY:
        return requirement.exit_point_id
    return None


def _direction_for_component(component: CostComponentType) -> TariffDirection:
    if component is CostComponentType.EXIT_CAPACITY:
        return TariffDirection.EXIT
    return TariffDirection.ENTRY


def _missing_code_for_component(component: CostComponentType) -> str:
    if component is CostComponentType.EXIT_CAPACITY:
        return "EXIT_TARIFF_MISSING"
    if component is CostComponentType.ENTRY_CAPACITY:
        return "ENTRY_TARIFF_MISSING"
    return "TARIFF_MISSING"


def _sum_compatible_components(
    components: Sequence[RouteCostComponent],
) -> tuple[float | None, str | None, str | None, list[str]]:
    priced = [component for component in components if component.amount is not None]
    if not priced:
        return None, None, None, []

    currencies = {component.currency for component in priced}
    units = {component.unit for component in priced}
    if len(currencies) != 1 or len(units) != 1:
        return None, None, None, ["UNIT_CONVERSION_NOT_IMPLEMENTED"]

    currency = next(iter(currencies))
    unit = next(iter(units))
    return round(sum(component.amount or 0.0 for component in priced), 4), currency, unit, []


def _unique(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _inaccessible_tsos(
    required_tso_access: Sequence[str],
    company_accessible_tsos: Sequence[str] | None,
) -> list[str]:
    if company_accessible_tsos is None:
        return []
    allowed = {item.strip().lower() for item in company_accessible_tsos if item.strip()}
    return [
        tso
        for tso in required_tso_access
        if tso.strip() and tso.strip().lower() not in allowed
    ]
