"""A cargo in transit: berth, boil-off, send-out by gas day, hedge months and suggestions."""

from datetime import UTC, date, datetime

import pytest

from eurogas_nexus.domain.lng.in_transit import (
    CargoInTransit,
    HedgeLeg,
    InTransitError,
    SlotWindow,
    build_plan,
    compare,
    last_trading_day,
)

NOW = datetime(2026, 11, 20, 9, tzinfo=UTC)
LOADED = datetime(2026, 12, 8, 0, tzinfo=UTC)


def _slot(**overrides) -> SlotWindow:
    values = {
        "slot_id": "zee-2026-12",
        "terminal": "Zeebrugge",
        "hub": "TTF",
        "window_start_utc": datetime(2026, 12, 1, tzinfo=UTC),
        "window_end_utc": datetime(2026, 12, 31, tzinfo=UTC),
        "send_out_mwh_per_day": 100_000.0,
        "gas_in_kind_pct": 1.3,
    }
    values.update(overrides)
    return SlotWindow(**values)


def _cargo(eta: datetime, *, slot: SlotWindow | None = None, hedges=None, **extra):
    return CargoInTransit(
        cargo_id="sabine-0412",
        loaded_mwh=1_000_000.0,
        loaded_at_utc=LOADED,
        eta_utc=eta,
        boil_off_pct_per_day=0.085,
        slot=_slot() if slot is None else slot,
        hedges=tuple(hedges or (HedgeLeg(hub="TTF", month="2026-12", mwh=-950_000.0),)),
        **extra,
    )


def test_energy_chain_balances_and_boil_off_runs_to_berth():
    plan = build_plan(_cargo(datetime(2026, 12, 20, 12, tzinfo=UTC)), now=NOW)

    assert plan.slot_status == "on_time"
    assert plan.days_to_berth == pytest.approx(12.5)
    assert plan.boil_off_mwh == pytest.approx(1_000_000 * 0.00085 * 12.5)
    at_berth = 1_000_000 - plan.boil_off_mwh
    assert plan.gas_in_kind_mwh == pytest.approx(at_berth * 0.013)
    assert plan.delivered_mwh == pytest.approx(at_berth - plan.gas_in_kind_mwh)
    assert sum(mwh for _day, mwh in plan.send_out) == pytest.approx(plan.delivered_mwh)
    # All of it leaves in December; the hedge leaves about 26.5 GWh to sell.
    december = plan.month("TTF", "2026-12")
    assert december.physical_mwh == pytest.approx(plan.delivered_mwh)
    assert [item.kind for item in plan.suggestions][:1] == ["sell"]
    assert plan.suggestions[0].mwh == pytest.approx(plan.delivered_mwh - 950_000)


def test_send_out_is_allocated_by_gas_day_not_calendar_day():
    # Berth on 31 Dec 20:00 UTC: gas sent before 1 Jan 05:00 UTC (06:00 CET) is December's.
    slot = _slot(window_end_utc=datetime(2027, 1, 10, tzinfo=UTC), send_out_mwh_per_day=24_000)
    cargo = CargoInTransit(
        cargo_id="small",
        loaded_mwh=48_000.0,
        loaded_at_utc=datetime(2026, 12, 31, 20, tzinfo=UTC),
        eta_utc=datetime(2026, 12, 31, 20, tzinfo=UTC),
        boil_off_pct_per_day=0.0,
        slot=_slot(
            window_start_utc=slot.window_start_utc,
            window_end_utc=slot.window_end_utc,
            send_out_mwh_per_day=24_000,
            gas_in_kind_pct=0.0,
        ),
    )
    plan = build_plan(cargo, now=NOW)

    assert plan.send_out[0] == ("2026-12-31", pytest.approx(9_000.0))
    assert plan.month("TTF", "2026-12").physical_mwh == pytest.approx(9_000.0)
    assert plan.month("TTF", "2027-01").physical_mwh == pytest.approx(39_000.0)


def test_eta_slip_into_next_month_suggests_a_roll_not_two_trades():
    before = build_plan(_cargo(datetime(2026, 12, 20, 12, tzinfo=UTC)), now=NOW)
    after = build_plan(_cargo(datetime(2026, 12, 25, 12, tzinfo=UTC)), now=NOW)
    change = compare(before, after)

    december = after.month("TTF", "2026-12")
    january = after.month("TTF", "2027-01")
    # Send-out from 25 Dec 12:00 UTC to the 1 Jan 05:00 UTC gas-day boundary is December's.
    hours_in_december = datetime(2027, 1, 1, 5, tzinfo=UTC) - datetime(
        2026, 12, 25, 12, tzinfo=UTC
    )
    assert december.physical_mwh == pytest.approx(
        100_000 * hours_in_december.total_seconds() / 86400
    )
    assert january.physical_mwh == pytest.approx(after.delivered_mwh - december.physical_mwh)

    rolls = [item for item in after.suggestions if item.kind == "roll"]
    assert len(rolls) == 1
    roll = rolls[0]
    assert (roll.from_month, roll.to_month) == ("2026-12", "2027-01")
    assert roll.mwh == pytest.approx(950_000 - december.physical_mwh)
    assert roll.due_utc == datetime(2026, 11, 28, tzinfo=UTC)  # Dec stops trading Fri 27 Nov
    leftover = [item for item in after.suggestions if item.kind == "sell"]
    assert leftover[0].from_month == "2027-01"
    assert leftover[0].mwh == pytest.approx(january.physical_mwh - roll.mwh)

    assert change.boil_off_change_mwh == pytest.approx(1_000_000 * 0.00085 * 5)
    assert change.delivered_change_mwh < 0
    assert change.headline().endswith("moves into TTF 2027-01.")


def test_a_month_that_stopped_trading_needs_short_notice_cover():
    # On 30 Nov the December contract has expired (last trade Fri 27 Nov).
    late = datetime(2026, 11, 30, 9, tzinfo=UTC)
    after = build_plan(_cargo(datetime(2026, 12, 25, 12, tzinfo=UTC)), now=late)

    kinds = {item.kind: item for item in after.suggestions}
    assert "roll" not in kinds
    assert kinds["short_notice"].from_month == "2026-12"
    assert kinds["short_notice"].mwh < 0  # the short futures delivers more than the gas
    assert "day-ahead" in kinds["short_notice"].text
    assert after.month("TTF", "2026-12").trading is False
    assert after.month("TTF", "2027-01").trading is True


def test_missed_slot_has_no_send_out_and_flags_the_orphaned_hedge():
    plan = build_plan(_cargo(datetime(2027, 1, 2, tzinfo=UTC)), now=NOW)

    assert plan.slot_status == "missed"
    assert plan.berth_utc is None
    assert plan.send_out == ()
    first = plan.suggestions[0]
    assert first.kind == "find_slot"
    assert "950,000 MWh of hedges no longer has gas behind it" in first.text
    # The December short is now all over-hedged.
    assert any(
        item.kind == "buy_back" and item.from_month == "2026-12" for item in plan.suggestions
    )
    assert compare(
        build_plan(_cargo(datetime(2026, 12, 20, tzinfo=UTC)), now=NOW), plan
    ).headline() == "The new ETA misses the slot window."


def test_a_missed_slot_adds_up_with_no_gas_in_kind_and_names_the_energy_at_eta():
    # QA-L-06. No berth: nothing is unloaded, so the terminal keeps nothing and nothing is
    # delivered; the energy aboard at the ETA is its own figure, and the chain adds up.
    eta = datetime(2027, 1, 2, tzinfo=UTC)
    plan = build_plan(_cargo(eta), now=NOW)
    assert plan.gas_in_kind_mwh == 0 and plan.delivered_mwh == 0
    days = (eta - LOADED).total_seconds() / 86400
    assert plan.boil_off_mwh == pytest.approx(1_000_000 * 0.085 / 100 * days)
    assert plan.energy_at_eta_mwh == pytest.approx(1_000_000 - plan.boil_off_mwh)
    assert plan.boil_off_mwh + plan.gas_in_kind_mwh + plan.energy_at_eta_mwh == pytest.approx(
        1_000_000)
    assert plan.as_dict()["energy_at_eta_mwh"] == round(plan.energy_at_eta_mwh, 1)
    # Missing the slot loses the delivery; it never gains energy.
    on_time = build_plan(_cargo(datetime(2026, 12, 20, tzinfo=UTC)), now=NOW)
    assert compare(on_time, plan).delivered_change_mwh == pytest.approx(-on_time.delivered_mwh)
    # With a berth the chain is unchanged: loaded = boil-off + gas in kind + delivered.
    assert on_time.boil_off_mwh + on_time.gas_in_kind_mwh + on_time.delivered_mwh == (
        pytest.approx(1_000_000))
    assert on_time.energy_at_eta_mwh >= on_time.delivered_mwh


def test_early_arrival_waits_for_the_window_and_boils_off_meanwhile():
    slot = _slot(window_start_utc=datetime(2026, 12, 22, tzinfo=UTC))
    plan = build_plan(_cargo(datetime(2026, 12, 20, tzinfo=UTC), slot=slot), now=NOW)

    assert plan.slot_status == "waiting"
    assert plan.berth_utc == datetime(2026, 12, 22, tzinfo=UTC)
    assert plan.wait_hours == pytest.approx(48)
    assert plan.days_to_berth == pytest.approx(14)


def test_berth_delay_past_laytime_costs_demurrage():
    plan = build_plan(
        _cargo(
            datetime(2026, 12, 20, tzinfo=UTC),
            berth_delay_hours=60,
            laytime_hours=36,
            demurrage_per_day=80_000,
        ),
        now=NOW,
    )

    assert plan.demurrage_hours == pytest.approx(24)
    assert plan.demurrage_cost == pytest.approx(80_000)
    assert any(item.kind == "demurrage" for item in plan.suggestions)


@pytest.mark.parametrize(
    ("month", "expected"),
    [
        ("2026-12", date(2026, 11, 27)),  # Tue 1 Dec: Mon 30, Fri 27
        ("2027-01", date(2026, 12, 30)),  # Fri 1 Jan: Thu 31, Wed 30
        ("2027-03", date(2027, 2, 25)),  # Mon 1 Mar: Fri 26, Thu 25
    ],
)
def test_last_trading_day_is_two_business_days_before_the_month(month, expected):
    assert last_trading_day(month) == expected


def test_holidays_push_the_last_trading_day_earlier():
    assert last_trading_day("2027-01", holidays=[date(2026, 12, 31)]) == date(2026, 12, 29)


def test_inputs_are_refused_when_they_cannot_describe_a_cargo():
    with pytest.raises(InTransitError):
        _cargo(datetime(2026, 12, 1))  # naive ETA
    with pytest.raises(InTransitError):
        _cargo(datetime(2026, 12, 1, tzinfo=UTC))  # ETA before loading
    with pytest.raises(InTransitError):
        HedgeLeg(hub="TTF", month="Dec-26", mwh=-1)
