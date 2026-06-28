"""Route-cost calculation service."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from eurogas_nexus.domain.route_cost.schemas import (
    RouteCostComponent,
    RouteCostResult,
    RouteCostScenario,
    RouteTariffLeg,
)
from eurogas_nexus.domain.route_cost.tariff_models import CapacityTariff
from eurogas_nexus.domain.route_cost.tariff_selection import select_latest_tariff


def calculate_route_cost(
    scenario: RouteCostScenario,
    tariffs: Sequence[CapacityTariff],
) -> RouteCostResult:
    """Calculate a traceable tariff cost without unit conversion or trading semantics."""

    if not scenario.tariff_legs:
        return RouteCostResult(
            scenario_id=scenario.scenario_id,
            status="BLOCKED",
            total_cost=None,
            currency=None,
            unit=None,
            missing_inputs=["ROUTE_TARIFF_LEGS_REQUIRED"],
            warnings=["ROUTE_COST_REQUIRES_EXPLICIT_TSO_LEGS"],
            required_tso_access=scenario.required_tso_access,
            company_accessible_tsos=scenario.company_accessible_tsos,
            research_only=True,
            human_review_required=True,
        )
    return _calculate_tariff_legs(scenario, tariffs, scenario.tariff_legs)


def _calculate_tariff_legs(
    scenario: RouteCostScenario,
    tariffs: Sequence[CapacityTariff],
    tariff_legs: Sequence[RouteTariffLeg],
) -> RouteCostResult:
    components: list[RouteCostComponent] = []
    missing_inputs: list[str] = []
    warnings: list[str] = []
    used_documents: set[str] = set()
    tariff_statuses: Counter[str] = Counter()
    human_review_required = False
    inaccessible_tsos = _inaccessible_tsos(
        scenario.required_tso_access,
        scenario.company_accessible_tsos,
    )
    if inaccessible_tsos:
        missing_inputs.extend(f"TSO_ACCESS_MISSING:{tso}" for tso in inaccessible_tsos)
        warnings.append("ROUTE_BLOCKED_BY_TSO_ACCESS")
        human_review_required = True

    for leg in tariff_legs:
        selection = _select_tariff_for_leg(leg, scenario, tariffs)
        warnings.extend(selection.warnings)
        human_review_required = human_review_required or selection.human_review_required
        if selection.selected_tariff is None:
            missing_code = f"TARIFF_MISSING:{leg.leg_id}"
            missing_inputs.append(missing_code)
            components.append(
                RouteCostComponent(
                    component_type=leg.component_type,
                    missing_input=missing_code,
                )
            )
            continue

        tariff = selection.selected_tariff
        used_documents.add(tariff.document_id)
        tariff_statuses[tariff.tariff_status.value] += 1
        components.append(
            RouteCostComponent(
                component_type=leg.component_type,
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


def _select_tariff_for_leg(
    leg: RouteTariffLeg,
    scenario: RouteCostScenario,
    tariffs: Sequence[CapacityTariff],
):
    eligible_tariffs = tariffs
    if leg.market_area:
        eligible_tariffs = [
            tariff for tariff in eligible_tariffs if tariff.market_area == leg.market_area
        ]
    return select_latest_tariff(
        eligible_tariffs,
        country=leg.country,
        tso=leg.tso,
        point_name=leg.point_name,
        direction=leg.direction,
        gas_year=leg.gas_year or scenario.gas_year,
        capacity_product=leg.capacity_product or scenario.capacity_product,
        firmness=leg.firmness or scenario.firmness,
    )


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
