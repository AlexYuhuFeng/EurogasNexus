"""Tariff selection tests for European route-cost modelling."""

from eurogas_nexus.domain.route_cost.enums import (
    CapacityProduct,
    Firmness,
    TariffDirection,
    TariffStatus,
)
from eurogas_nexus.domain.route_cost.european_public_tariffs import (
    published_european_corridor_tariffs,
)
from eurogas_nexus.domain.route_cost.tariff_selection import select_latest_tariff


def test_selects_final_bbl_forward_flow_tariff() -> None:
    tariffs = published_european_corridor_tariffs()

    selection = select_latest_tariff(
        tariffs,
        country="NL",
        tso="BBL Company",
        point_name="BBL Forward Flow NL to GB",
        direction=TariffDirection.EXIT,
        gas_year="2025+",
        capacity_product=CapacityProduct.ANNUAL,
        firmness=Firmness.FIRM,
    )

    assert selection.status == "SELECTED"
    assert selection.selected_tariff is not None
    assert selection.selected_tariff.tariff_value == 1.0
    assert selection.selected_tariff.tariff_status is TariffStatus.FINAL
    assert selection.human_review_required is False


def test_selects_final_iuk_annual_firm_tariff() -> None:
    tariffs = published_european_corridor_tariffs()

    selection = select_latest_tariff(
        tariffs,
        country="GB",
        tso="Interconnector UK",
        point_name="IUK Bacton Entry",
        direction=TariffDirection.ENTRY,
        gas_year="2026/27",
        capacity_product=CapacityProduct.ANNUAL,
        firmness=Firmness.FIRM,
    )

    assert selection.status == "SELECTED"
    assert selection.selected_tariff is not None
    assert selection.selected_tariff.tariff_value == 0.035827
    assert selection.selected_tariff.tariff_status is TariffStatus.FINAL
    assert selection.human_review_required is False


def test_selection_never_substitutes_another_gas_year() -> None:
    tariffs = published_european_corridor_tariffs()

    selection = select_latest_tariff(
        tariffs,
        country="NL",
        tso="BBL Company",
        point_name="BBL Forward Flow NL to GB",
        direction=TariffDirection.EXIT,
        gas_year="2030/31",
        capacity_product=CapacityProduct.ANNUAL,
        firmness=Firmness.FIRM,
    )

    assert selection.status == "MISSING"
    assert selection.selected_tariff is None
    assert "TARIFF_MISSING" in selection.missing_inputs
