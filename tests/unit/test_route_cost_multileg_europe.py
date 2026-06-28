"""Generic European multi-leg route-cost calculation tests."""

from eurogas_nexus.domain.route_cost.enums import (
    BusinessModel,
    CapacityProduct,
    DeliveryMode,
    Firmness,
    SourceResourceType,
    TariffDirection,
)
from eurogas_nexus.domain.route_cost.european_public_tariffs import (
    published_european_corridor_tariffs,
)
from eurogas_nexus.domain.route_cost.route_cost_service import calculate_route_cost
from eurogas_nexus.domain.route_cost.schemas import RouteCostScenario, RouteTariffLeg


def test_calculates_bbl_forward_and_reverse_when_units_are_compatible() -> None:
    scenario = RouteCostScenario(
        scenario_id="bbl-forward-reverse-eur",
        source_resource_type=SourceResourceType.PIPELINE_IMPORT,
        start_point_id="TTF",
        target_hub_or_point_id="NBP",
        business_model=BusinessModel.CROSS_BORDER_TRANSFER,
        delivery_mode=DeliveryMode.BORDER_TRANSFER,
        gas_year="2025+",
        capacity_product=CapacityProduct.ANNUAL,
        firmness=Firmness.FIRM,
        required_tso_access=["BBL Company"],
        company_accessible_tsos=["BBL Company"],
        tariff_legs=[
            RouteTariffLeg(
                leg_id="bbl-forward",
                country="NL",
                tso="BBL Company",
                market_area="BBL",
                point_name="BBL Forward Flow NL to GB",
                direction=TariffDirection.EXIT,
            ),
            RouteTariffLeg(
                leg_id="bbl-reverse",
                country="GB",
                tso="BBL Company",
                market_area="BBL",
                point_name="BBL Reverse Flow GB to NL",
                direction=TariffDirection.ENTRY,
            ),
        ],
    )

    result = calculate_route_cost(scenario, published_european_corridor_tariffs())

    assert result.status == "SUCCESS"
    assert result.total_cost == 2.0
    assert result.currency == "EUR"
    assert result.unit == "EUR/MWh"
    assert result.missing_inputs == []
    assert result.required_tso_access == ["BBL Company"]
    assert [component.tariff_id for component in result.cost_breakdown] == [
        "bbl-2025-plus-forward-annual-firm",
        "bbl-2025-plus-reverse-annual-firm",
    ]


def test_mixed_bbl_and_iuk_units_are_not_summed_without_conversion() -> None:
    scenario = RouteCostScenario(
        scenario_id="bbl-iuk-mixed-units",
        source_resource_type=SourceResourceType.PIPELINE_IMPORT,
        start_point_id="TTF",
        target_hub_or_point_id="NBP",
        business_model=BusinessModel.CROSS_BORDER_TRANSFER,
        delivery_mode=DeliveryMode.BORDER_TRANSFER,
        gas_year="2026/27",
        capacity_product=CapacityProduct.ANNUAL,
        firmness=Firmness.FIRM,
        required_tso_access=["BBL Company", "Interconnector UK"],
        company_accessible_tsos=["BBL Company", "Interconnector UK"],
        tariff_legs=[
            RouteTariffLeg(
                leg_id="iuk-bacton-entry",
                country="GB",
                tso="Interconnector UK",
                market_area="IUK",
                point_name="IUK Bacton Entry",
                direction=TariffDirection.ENTRY,
            ),
            RouteTariffLeg(
                leg_id="bbl-forward",
                country="NL",
                tso="BBL Company",
                market_area="BBL",
                point_name="BBL Forward Flow NL to GB",
                direction=TariffDirection.EXIT,
                gas_year="2025+",
            ),
        ],
    )

    result = calculate_route_cost(scenario, published_european_corridor_tariffs())

    assert result.status == "PARTIAL"
    assert result.total_cost is None
    assert "UNIT_CONVERSION_NOT_IMPLEMENTED" in result.warnings
    assert result.human_review_required is True


def test_multileg_route_is_blocked_when_operator_lacks_tso_access() -> None:
    scenario = RouteCostScenario(
        scenario_id="iuk-access-blocked",
        source_resource_type=SourceResourceType.PIPELINE_IMPORT,
        start_point_id="NBP",
        target_hub_or_point_id="ZTP",
        business_model=BusinessModel.CROSS_BORDER_TRANSFER,
        delivery_mode=DeliveryMode.BORDER_TRANSFER,
        gas_year="2026/27",
        capacity_product=CapacityProduct.ANNUAL,
        firmness=Firmness.FIRM,
        required_tso_access=["Interconnector UK"],
        company_accessible_tsos=["BBL Company"],
        tariff_legs=[
            RouteTariffLeg(
                leg_id="iuk-zeebrugge-entry",
                country="BE",
                tso="Interconnector UK",
                market_area="IUK",
                point_name="IUK Zeebrugge Entry",
                direction=TariffDirection.ENTRY,
            )
        ],
    )

    result = calculate_route_cost(scenario, published_european_corridor_tariffs())

    assert result.status == "BLOCKED"
    assert result.inaccessible_tsos == ["Interconnector UK"]
    assert "TSO_ACCESS_MISSING:Interconnector UK" in result.missing_inputs
