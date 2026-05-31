"""UK Easington route-cost example tests."""

from datetime import UTC, datetime

from eurogas_nexus.domain.route_cost.enums import (
    BusinessModel,
    CapacityProduct,
    Firmness,
    SourceResourceType,
)
from eurogas_nexus.domain.route_cost.route_cost_service import calculate_route_cost
from eurogas_nexus.domain.route_cost.schemas import RouteCostScenario
from eurogas_nexus.domain.route_cost.uk_demo_data import demo_uk_capacity_tariffs

FORBIDDEN_WORDS = ("BUY", "SELL", "HOLD", "execute", "order", "nominate", "recommendation")


def _scenario(business_model: BusinessModel, gas_year: str = "2025/26") -> RouteCostScenario:
    return RouteCostScenario(
        scenario_id=f"uk-easington-{business_model.value.lower()}-{gas_year.replace('/', '-')}",
        source_resource_type=SourceResourceType.BEACH_DELIVERY,
        start_point_id="Easington Beach Terminal",
        target_hub_or_point_id="NBP",
        business_model=business_model,
        gas_year=gas_year,
        capacity_product=CapacityProduct.DAILY,
        firmness=Firmness.FIRM,
        created_at=datetime.now(UTC),
    )


def test_easington_virtual_nbp_sale_cost_uses_entry_tariff_only() -> None:
    tariffs = demo_uk_capacity_tariffs()

    result = calculate_route_cost(
        _scenario(BusinessModel.VIRTUAL_HUB_SALE),
        tariffs,
    )

    assert result.status == "SUCCESS"
    assert result.total_cost == 0.1086
    assert result.currency == "GBP"
    assert result.unit == "p/kWh/day"
    assert len(result.cost_breakdown) == 1
    assert result.cost_breakdown[0].tariff_id is not None
    assert result.used_tariff_documents == ["uk_ng_nts_transportation_charges_oct_2025"]
    assert result.research_only is True


def test_easington_2026_27_indicative_result_requires_review() -> None:
    tariffs = demo_uk_capacity_tariffs()

    result = calculate_route_cost(
        _scenario(BusinessModel.VIRTUAL_HUB_SALE, "2026/27"),
        tariffs,
    )

    assert result.status == "SUCCESS"
    assert result.total_cost == 0.1157
    assert result.tariff_status_summary == {"INDICATIVE": 1}
    assert result.human_review_required is True


def test_physical_delivery_with_bacton_exit_tariff_sums_entry_and_exit() -> None:
    tariffs = demo_uk_capacity_tariffs()
    scenario = _scenario(BusinessModel.PHYSICAL_DELIVERY)
    scenario.target_hub_or_point_id = "Bacton GDN (EA)"

    result = calculate_route_cost(scenario, tariffs)

    assert result.status == "SUCCESS"
    assert result.total_cost == 0.1385
    assert len(result.cost_breakdown) == 2


def test_physical_delivery_without_known_exit_tariff_is_partial() -> None:
    tariffs = demo_uk_capacity_tariffs()
    scenario = _scenario(BusinessModel.PHYSICAL_DELIVERY)
    scenario.target_hub_or_point_id = "Unknown Physical Exit"

    result = calculate_route_cost(scenario, tariffs)

    assert result.status == "PARTIAL"
    assert result.total_cost == 0.1086
    assert "EXIT_TARIFF_MISSING" in result.missing_inputs


def test_route_cost_output_has_no_execution_or_recommendation_language() -> None:
    tariffs = demo_uk_capacity_tariffs()
    result = calculate_route_cost(_scenario(BusinessModel.VIRTUAL_HUB_SALE), tariffs)
    payload = result.model_dump_json()

    for word in FORBIDDEN_WORDS:
        assert word not in payload


def test_any_uk_nts_entry_and_exit_can_calculate_when_tariffs_exist() -> None:
    tariffs = demo_uk_capacity_tariffs()
    scenario = RouteCostScenario(
        scenario_id="uk-any-nts-entry-exit",
        source_resource_type=SourceResourceType.PIPELINE_IMPORT,
        start_point_id="Easington Beach Terminal",
        target_hub_or_point_id="Bacton GDN (EA)",
        business_model=BusinessModel.CROSS_BORDER_TRANSFER,
        gas_year="2025/26",
        capacity_product=CapacityProduct.DAILY,
        firmness=Firmness.FIRM,
    )

    result = calculate_route_cost(scenario, tariffs)

    assert result.status == "SUCCESS"
    assert result.total_cost == 0.1385
    assert result.missing_inputs == []


def test_route_cost_blocks_when_company_lacks_required_tso_access() -> None:
    scenario = _scenario(BusinessModel.VIRTUAL_HUB_SALE)
    scenario.company_accessible_tsos = ["Fluxys Belgium"]

    result = calculate_route_cost(scenario, demo_uk_capacity_tariffs())

    assert result.status == "BLOCKED"
    assert result.inaccessible_tsos == ["National Gas NTS"]
    assert "TSO_ACCESS_MISSING:National Gas NTS" in result.missing_inputs
    assert "ROUTE_BLOCKED_BY_TSO_ACCESS" in result.warnings
