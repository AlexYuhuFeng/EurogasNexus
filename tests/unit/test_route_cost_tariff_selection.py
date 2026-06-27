"""Tariff selection tests for UK route-cost modelling."""

from eurogas_nexus.domain.route_cost.enums import (
    CapacityProduct,
    Firmness,
    TariffDirection,
    TariffStatus,
)
from eurogas_nexus.domain.route_cost.tariff_selection import select_latest_tariff
from eurogas_nexus.domain.route_cost.uk_public_tariffs import published_uk_capacity_tariffs


def test_selects_final_2025_26_easington_entry_tariff() -> None:
    tariffs = published_uk_capacity_tariffs()

    selection = select_latest_tariff(
        tariffs,
        country="UK",
        tso="National Gas NTS",
        point_name="Easington Beach Terminal",
        direction=TariffDirection.ENTRY,
        gas_year="2025/26",
        capacity_product=CapacityProduct.DAILY,
        firmness=Firmness.FIRM,
    )

    assert selection.status == "SELECTED"
    assert selection.selected_tariff is not None
    assert selection.selected_tariff.tariff_value == 0.1086
    assert selection.selected_tariff.tariff_status is TariffStatus.FINAL
    assert selection.human_review_required is False


def test_selects_indicative_2026_27_and_requires_human_review() -> None:
    tariffs = published_uk_capacity_tariffs()

    selection = select_latest_tariff(
        tariffs,
        country="UK",
        tso="National Gas NTS",
        point_name="Easington Beach Terminal",
        direction=TariffDirection.ENTRY,
        gas_year="2026/27",
        capacity_product=CapacityProduct.DAILY,
        firmness=Firmness.FIRM,
    )

    assert selection.status == "SELECTED"
    assert selection.selected_tariff is not None
    assert selection.selected_tariff.tariff_value == 0.1157
    assert selection.selected_tariff.tariff_status is TariffStatus.INDICATIVE
    assert selection.human_review_required is True


def test_selection_never_substitutes_another_gas_year() -> None:
    tariffs = published_uk_capacity_tariffs()

    selection = select_latest_tariff(
        tariffs,
        country="UK",
        tso="National Gas NTS",
        point_name="Easington Beach Terminal",
        direction=TariffDirection.ENTRY,
        gas_year="2030/31",
        capacity_product=CapacityProduct.DAILY,
        firmness=Firmness.FIRM,
    )

    assert selection.status == "MISSING"
    assert selection.selected_tariff is None
    assert "TARIFF_MISSING" in selection.missing_inputs
