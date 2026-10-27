"""Before/after regressions for explicit tariff applicability dates.

The synthetic rows here are deliberately ordered so the pre-fix
``select_latest_tariff`` (status priority, first row wins, dates ignored)
chooses a different row or returns a priced route where the fixed selector
refuses. They do not use live provider data or production money values.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from pydantic import ValidationError

from eurogas_nexus.domain.route_cost.enums import (
    BusinessModel,
    CapacityProduct,
    DeliveryMode,
    Firmness,
    SourceResourceType,
    TariffDirection,
    TariffStatus,
)
from eurogas_nexus.domain.route_cost.route_cost_service import calculate_route_cost
from eurogas_nexus.domain.route_cost.schemas import RouteCostScenario, RouteTariffLeg
from eurogas_nexus.domain.route_cost.tariff_models import CapacityTariff
from eurogas_nexus.domain.route_cost.tariff_selection import (
    TARIFF_APPLICABILITY_AMBIGUOUS,
    TARIFF_APPLICABILITY_DATE_INVALID,
    TARIFF_APPLICABILITY_NOT_ASSESSED,
    TARIFF_DUPLICATE_ID_CONFLICT,
    TARIFF_EFFECTIVE_BOUNDS_INVALID,
    TARIFF_NOT_EFFECTIVE_ON_DATE,
    select_latest_tariff,
)

JAN_FIRST = date(2026, 1, 1)
JAN_LAST = date(2026, 1, 31)
FEB_FIRST = date(2026, 2, 1)
FEB_LAST = date(2026, 2, 28)
MAR_FIRST = date(2026, 3, 1)
MAR_LAST = date(2026, 3, 31)


def _tariff(
    *,
    tariff_id: str = "tariff",
    point_name: str = "POINT",
    effective_from: date = JAN_FIRST,
    effective_to: date | None = JAN_LAST,
    tariff_value: float = 1.0,
    tariff_status: TariffStatus = TariffStatus.FINAL,
    market_area: str = "BBL",
) -> CapacityTariff:
    """Build one synthetic tariff row with an explicit effective interval."""

    return CapacityTariff(
        tariff_id=tariff_id,
        document_id=f"doc-{tariff_id}",
        country="NL",
        tso="TSO",
        market_area=market_area,
        gas_year="2025+",
        point_id=f"point-{point_name}",
        source_point_name=point_name,
        direction=TariffDirection.EXIT,
        capacity_product=CapacityProduct.ANNUAL,
        firmness=Firmness.FIRM,
        tariff_value=tariff_value,
        currency="EUR",
        unit="EUR/MWh",
        effective_from=effective_from,
        effective_to=effective_to,
        tariff_status=tariff_status,
        source_table="synthetic applicability test table",
        source_refs=["test:synthetic-tariff"],
        manual_review_required=False,
    )


def _select(
    tariffs: list[CapacityTariff],
    applicability_date: date | None,
):
    """Call the exact selector with one fixed synthetic key."""

    return select_latest_tariff(
        tariffs,
        country="NL",
        tso="TSO",
        point_name="POINT",
        direction=TariffDirection.EXIT,
        gas_year="2025+",
        capacity_product=CapacityProduct.ANNUAL,
        firmness=Firmness.FIRM,
        applicability_date=applicability_date,
    )


def _leg(
    leg_id: str = "leg-1",
    *,
    point_name: str = "POINT",
    market_area: str = "BBL",
) -> RouteTariffLeg:
    """Build one explicit tariff leg matching the synthetic tariff key."""

    return RouteTariffLeg(
        leg_id=leg_id,
        country="NL",
        tso="TSO",
        market_area=market_area,
        point_name=point_name,
        direction=TariffDirection.EXIT,
    )


def _scenario(
    *,
    legs: list[RouteTariffLeg],
    applicability_date: date | None,
    created_at: datetime | None = None,
) -> RouteCostScenario:
    """Build a route scenario whose created_at is audit metadata only."""

    return RouteCostScenario(
        scenario_id="scenario-applicability",
        source_resource_type=SourceResourceType.PIPELINE_IMPORT,
        start_point_id="TTF",
        target_hub_or_point_id="NBP",
        business_model=BusinessModel.CROSS_BORDER_TRANSFER,
        delivery_mode=DeliveryMode.BORDER_TRANSFER,
        gas_year="2025+",
        tariff_applicability_date=applicability_date,
        capacity_product=CapacityProduct.ANNUAL,
        firmness=Firmness.FIRM,
        tariff_legs=legs,
        created_at=created_at or datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
    )


def test_explicit_date_is_inclusive_on_first_and_last_effective_day() -> None:
    january = _tariff(
        tariff_id="jan",
        effective_from=JAN_FIRST,
        effective_to=JAN_LAST,
        tariff_value=2.0,
    )
    february = _tariff(
        tariff_id="feb",
        effective_from=FEB_FIRST,
        effective_to=FEB_LAST,
        tariff_value=3.0,
    )
    tariffs = [january, february]

    for day in (JAN_FIRST, JAN_LAST):
        selection = _select(tariffs, day)
        assert selection.status == "SELECTED"
        assert selection.selected_tariff is not None
        assert selection.selected_tariff.tariff_id == "jan"

    for day in (FEB_FIRST, FEB_LAST):
        selection = _select(tariffs, day)
        assert selection.status == "SELECTED"
        assert selection.selected_tariff is not None
        assert selection.selected_tariff.tariff_id == "feb"


def test_explicit_date_before_and_after_an_effective_period_blocks() -> None:
    tariffs = [_tariff(tariff_id="jan")]

    for day in (date(2025, 12, 31), FEB_FIRST):
        selection = _select(tariffs, day)
        assert selection.status == "MISSING"
        assert selection.selected_tariff is None
        assert selection.missing_inputs == [TARIFF_NOT_EFFECTIVE_ON_DATE]
        assert selection.human_review_required is True


def test_explicit_date_in_a_gap_blocks_instead_of_selecting_a_neighbour() -> None:
    tariffs = [
        _tariff(tariff_id="jan", effective_from=JAN_FIRST, effective_to=JAN_LAST),
        _tariff(tariff_id="mar", effective_from=MAR_FIRST, effective_to=MAR_LAST),
    ]

    selection = _select(tariffs, date(2026, 2, 15))

    assert selection.status == "MISSING"
    assert selection.selected_tariff is None
    assert selection.missing_inputs == [TARIFF_NOT_EFFECTIVE_ON_DATE]


def test_explicit_date_overlapping_final_rows_are_ambiguous() -> None:
    tariffs = [
        _tariff(
            tariff_id="final-a",
            effective_from=JAN_FIRST,
            effective_to=JAN_LAST,
            tariff_value=1.0,
        ),
        _tariff(
            tariff_id="final-b",
            effective_from=date(2026, 1, 15),
            effective_to=FEB_LAST,
            tariff_value=2.0,
        ),
    ]

    selection = _select(tariffs, date(2026, 1, 20))

    assert selection.status == "MISSING"
    assert selection.selected_tariff is None
    assert selection.missing_inputs == [TARIFF_APPLICABILITY_AMBIGUOUS]


def test_explicit_date_keeps_status_priority_within_eligible_rows() -> None:
    old_final_out_of_period = _tariff(
        tariff_id="old-final",
        effective_from=date(2025, 12, 1),
        effective_to=date(2025, 12, 31),
        tariff_value=1.0,
    )
    new_indicative = _tariff(
        tariff_id="new-indicative",
        effective_from=JAN_FIRST,
        effective_to=JAN_LAST,
        tariff_value=2.0,
        tariff_status=TariffStatus.INDICATIVE,
    )

    selection = _select([old_final_out_of_period, new_indicative], date(2026, 1, 15))

    assert selection.status == "SELECTED"
    assert selection.selected_tariff is not None
    assert selection.selected_tariff.tariff_id == "new-indicative"
    assert selection.warnings == ["TARIFF_STATUS_INDICATIVE"]
    assert selection.human_review_required is True

    new_final = _tariff(
        tariff_id="new-final",
        effective_from=JAN_FIRST,
        effective_to=JAN_LAST,
        tariff_value=3.0,
    )
    selection = _select([new_indicative, new_final], date(2026, 1, 15))

    assert selection.selected_tariff is not None
    assert selection.selected_tariff.tariff_id == "new-final"
    assert selection.warnings == []
    assert selection.human_review_required is False


def test_explicit_date_inverted_bounds_block_even_with_a_valid_row() -> None:
    valid = _tariff(tariff_id="valid", effective_from=JAN_FIRST, effective_to=JAN_LAST)
    inverted = _tariff(
        tariff_id="inverted",
        effective_from=FEB_FIRST,
        effective_to=JAN_LAST,
    )

    selection = _select([valid, inverted], date(2026, 1, 15))

    assert selection.status == "MISSING"
    assert selection.selected_tariff is None
    assert selection.missing_inputs == [TARIFF_EFFECTIVE_BOUNDS_INVALID]


def test_same_id_duplicates_collapse_but_conflicting_content_blocks() -> None:
    original = _tariff(tariff_id="same-id", tariff_value=1.0)

    identical = _select([original, original.model_copy()], date(2026, 1, 15))
    assert identical.status == "SELECTED"
    assert identical.selected_tariff is not None
    assert identical.selected_tariff.tariff_id == "same-id"

    conflicting = original.model_copy(update={"tariff_value": 9.0})
    selection = _select([original, conflicting], date(2026, 1, 15))
    assert selection.status == "MISSING"
    assert selection.selected_tariff is None
    assert selection.missing_inputs == [TARIFF_DUPLICATE_ID_CONFLICT]


def test_datetime_is_not_accepted_as_a_plain_applicability_date() -> None:
    selection = _select([_tariff()], datetime(2026, 1, 15, 12, 0))

    assert selection.status == "MISSING"
    assert selection.selected_tariff is None
    assert selection.missing_inputs == [TARIFF_APPLICABILITY_DATE_INVALID]


def test_no_date_preserves_legacy_choice_but_discloses_not_assessed() -> None:
    february = _tariff(
        tariff_id="feb",
        effective_from=FEB_FIRST,
        effective_to=FEB_LAST,
        tariff_value=3.0,
    )
    january = _tariff(
        tariff_id="jan",
        effective_from=JAN_FIRST,
        effective_to=JAN_LAST,
        tariff_value=2.0,
    )

    selection = _select([february, january], None)

    assert selection.status == "SELECTED"
    assert selection.selected_tariff is not None
    # Legacy row order is preserved on purpose, but never claimed as verified.
    assert selection.selected_tariff.tariff_id == "feb"
    assert selection.warnings == [TARIFF_APPLICABILITY_NOT_ASSESSED]
    assert selection.human_review_required is True

    missing = _select([], None)
    assert missing.status == "MISSING"
    assert missing.missing_inputs == ["TARIFF_MISSING"]
    assert missing.warnings == [TARIFF_APPLICABILITY_NOT_ASSESSED]
    assert missing.human_review_required is True


def test_calculate_route_cost_selects_by_explicit_date_and_echoes_it() -> None:
    tariffs = [
        _tariff(
            tariff_id="feb",
            effective_from=FEB_FIRST,
            effective_to=FEB_LAST,
            tariff_value=3.0,
        ),
        _tariff(
            tariff_id="jan",
            effective_from=JAN_FIRST,
            effective_to=JAN_LAST,
            tariff_value=2.0,
        ),
    ]
    scenario = _scenario(
        legs=[_leg()],
        applicability_date=JAN_LAST,
        created_at=datetime(2030, 1, 1, tzinfo=UTC),
    )

    result = calculate_route_cost(scenario, tariffs)

    assert result.status == "SUCCESS"
    assert result.tariff_applicability_date == JAN_LAST
    assert result.total_cost == 2.0
    assert result.cost_breakdown[0].tariff_id == "jan"
    assert result.missing_inputs == []
    assert TARIFF_APPLICABILITY_NOT_ASSESSED not in result.warnings
    assert result.human_review_required is False


def test_calculate_route_cost_explicit_gap_blocks_with_leg_code_and_no_charge() -> None:
    tariffs = [
        _tariff(tariff_id="jan", effective_from=JAN_FIRST, effective_to=JAN_LAST),
        _tariff(tariff_id="mar", effective_from=MAR_FIRST, effective_to=MAR_LAST),
    ]
    scenario = _scenario(legs=[_leg("gap-leg")], applicability_date=date(2026, 2, 15))

    result = calculate_route_cost(scenario, tariffs)

    code = f"{TARIFF_NOT_EFFECTIVE_ON_DATE}:gap-leg"
    assert result.status == "BLOCKED"
    assert result.total_cost is None
    assert result.currency is None
    assert result.unit is None
    assert result.missing_inputs == [code]
    assert "ROUTE_BLOCKED_BY_TARIFF_APPLICABILITY" in result.warnings
    assert result.cost_breakdown[0].missing_input == code
    assert result.cost_breakdown[0].tariff_id is None
    assert result.cost_breakdown[0].amount is None


def test_calculate_route_cost_ambiguous_final_blocks_with_leg_code() -> None:
    tariffs = [
        _tariff(tariff_id="final-a", effective_from=JAN_FIRST, effective_to=JAN_LAST),
        _tariff(
            tariff_id="final-b",
            effective_from=date(2026, 1, 15),
            effective_to=FEB_LAST,
        ),
    ]
    scenario = _scenario(legs=[_leg("ambiguous-leg")], applicability_date=date(2026, 1, 20))

    result = calculate_route_cost(scenario, tariffs)

    code = f"{TARIFF_APPLICABILITY_AMBIGUOUS}:ambiguous-leg"
    assert result.status == "BLOCKED"
    assert result.total_cost is None
    assert result.missing_inputs == [code]
    assert result.cost_breakdown[0].missing_input == code


def test_calculate_route_cost_multi_leg_applicability_failure_blocks_partial_total() -> None:
    tariffs = [
        _tariff(
            tariff_id="point-a-row",
            point_name="POINT-A",
            effective_from=JAN_FIRST,
            effective_to=FEB_LAST,
            tariff_value=2.0,
        ),
        _tariff(
            tariff_id="point-b-row",
            point_name="POINT-B",
            effective_from=MAR_FIRST,
            effective_to=MAR_LAST,
            tariff_value=5.0,
        ),
    ]
    scenario = _scenario(
        legs=[
            _leg("leg-a", point_name="POINT-A"),
            _leg("leg-b", point_name="POINT-B"),
        ],
        applicability_date=date(2026, 2, 15),
    )

    result = calculate_route_cost(scenario, tariffs)

    code = f"{TARIFF_NOT_EFFECTIVE_ON_DATE}:leg-b"
    assert result.status == "BLOCKED"
    assert result.total_cost is None
    assert result.missing_inputs == [code]
    assert [component.tariff_id for component in result.cost_breakdown] == [
        "point-a-row",
        None,
    ]
    assert result.cost_breakdown[0].amount == 2.0
    assert result.cost_breakdown[1].missing_input == code


def test_calculate_route_cost_market_area_filter_is_applied_before_selection() -> None:
    tariffs = [
        _tariff(
            tariff_id="other-area",
            market_area="OTHER",
            effective_from=JAN_FIRST,
            effective_to=JAN_LAST,
            tariff_value=9.0,
        ),
        _tariff(
            tariff_id="bbl-area",
            market_area="BBL",
            effective_from=JAN_FIRST,
            effective_to=JAN_LAST,
            tariff_value=2.0,
        ),
    ]
    scenario = _scenario(
        legs=[_leg(market_area="BBL")],
        applicability_date=date(2026, 1, 15),
    )

    result = calculate_route_cost(scenario, tariffs)

    assert result.status == "SUCCESS"
    assert result.total_cost == 2.0
    assert result.cost_breakdown[0].tariff_id == "bbl-area"


def test_calculate_route_cost_without_date_discloses_legacy_selection() -> None:
    tariffs = [
        _tariff(
            tariff_id="feb",
            effective_from=FEB_FIRST,
            effective_to=FEB_LAST,
            tariff_value=3.0,
        ),
        _tariff(
            tariff_id="jan",
            effective_from=JAN_FIRST,
            effective_to=JAN_LAST,
            tariff_value=2.0,
        ),
    ]
    scenario = _scenario(
        legs=[_leg()],
        applicability_date=None,
        created_at=datetime(2030, 1, 1, tzinfo=UTC),
    )

    result = calculate_route_cost(scenario, tariffs)

    assert result.status == "SUCCESS"
    assert result.tariff_applicability_date is None
    # Legacy wire result and row order are preserved, and never claimed verified.
    assert result.total_cost == 3.0
    assert result.cost_breakdown[0].tariff_id == "feb"
    assert TARIFF_APPLICABILITY_NOT_ASSESSED in result.warnings
    assert result.human_review_required is True


@pytest.mark.parametrize(
    "value", [0, True, "20260101", "2026-01-01T00:00:00Z", datetime(2026, 1, 1, tzinfo=UTC)]
)
def test_scenario_never_coerces_timestamp_to_applicability_date(value) -> None:
    with pytest.raises(ValidationError, match="explicit YYYY-MM-DD"):
        RouteCostScenario.model_validate({"tariff_applicability_date": value})
