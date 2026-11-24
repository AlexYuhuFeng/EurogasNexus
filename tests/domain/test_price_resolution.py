"""The one price per hub, period and instant (P-08, QA-T-02): precedence of the resolver."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from eurogas_nexus.domain.market.price_resolution import (
    BASIS_DERIVED,
    BASIS_FIRM_MARK,
    BASIS_MARKET,
    BASIS_NOTHING_IN_DATE,
    DERIVED,
    FIRM_MARK,
    LIVE_TICK,
    SETTLEMENT,
    PriceCandidate,
    judge,
    month_window,
    resolve_price,
)

# Tuesday 24 November 2026, 10:00 UTC; TTF Dec-26 is the front month.
NOW = datetime(2026, 11, 24, 10, tzinfo=UTC)
DEC = (date(2026, 12, 1), date(2027, 1, 1))


def tick(minutes_old: float, mid: float, *, source="EEX", spread=0.1, state=None, **kw):
    return PriceCandidate(
        hub="TTF", period_start=DEC[0], period_end=DEC[1], kind=LIVE_TICK, value=mid,
        unit="EUR/MWh", source_system=source,
        as_of_utc=NOW - timedelta(minutes=minutes_old), reference=f"tick-{minutes_old}",
        bid=mid - spread / 2, ask=mid + spread / 2, state=state,
        current_within=timedelta(minutes=1), stale_after=timedelta(minutes=30), **kw,
    )


def close(observed: datetime, value: float, *, source="EEX", kind=SETTLEMENT, **kw):
    return PriceCandidate(
        hub="TTF", period_start=DEC[0], period_end=DEC[1], kind=kind, value=value,
        unit="EUR/MWh", source_system=source, as_of_utc=observed,
        reference=f"{kind}-{observed:%d%H}", **kw,
    )


def resolve(candidates, **kw):
    return resolve_price(candidates, hub="TTF", period_start=DEC[0], period_end=DEC[1],
                         now=NOW, **kw)


YESTERDAY_CLOSE = datetime(2026, 11, 23, 17, 30, tzinfo=UTC)


def test_a_fresh_tick_beats_an_older_close():
    answer = resolve([close(YESTERDAY_CLOSE, 31.20), tick(0.5, 31.75)])
    assert answer.kind == LIVE_TICK and answer.value == pytest.approx(31.75)
    assert answer.state == "current" and answer.basis == BASIS_MARKET
    assert answer.considered == 2


def test_a_late_tick_within_its_maximum_age_still_beats_the_older_close():
    answer = resolve([close(YESTERDAY_CLOSE, 31.20), tick(20, 31.75)])
    assert answer.kind == LIVE_TICK and answer.state == "late"


def test_a_stale_tick_loses_to_a_settlement_published_since():
    # The feed stopped before the evening settlement: the old tick is stale and the
    # settlement in date, so the settlement wins although both are "market prices".
    stale_tick = tick(18 * 60, 30.10)
    answer = resolve([stale_tick, close(YESTERDAY_CLOSE, 31.20)])
    assert answer.kind == SETTLEMENT and answer.value == pytest.approx(31.20)
    assert answer.state == "current" and answer.basis == BASIS_MARKET


def test_a_stale_tick_loses_to_a_fresh_settlement_even_if_newer_in_time():
    # A tick stamped after the close but past its source's maximum age does not beat it.
    early_close = datetime(2026, 11, 24, 8, tzinfo=UTC)
    answer = resolve([tick(45, 30.10), close(early_close - timedelta(hours=1), 31.20)])
    assert answer.kind == SETTLEMENT


def test_the_freshest_of_two_in_date_closes_wins():
    older = close(datetime(2026, 11, 23, 7, tzinfo=UTC), 30.0, source="ICE_ENDEX")
    newer = close(datetime(2026, 11, 24, 9, tzinfo=UTC), 31.0)
    assert resolve([older, newer]).value == pytest.approx(31.0)
    assert resolve([newer, older]).value == pytest.approx(31.0)


def test_on_an_exact_tie_the_tick_wins():
    at = NOW - timedelta(seconds=20)
    same = close(at, 30.0)
    answer = resolve([same, tick(1 / 3, 31.0)])
    assert answer.kind == LIVE_TICK


def test_a_side_is_read_from_ticks_and_a_settlement_serves_any_side():
    live = tick(0.5, 31.0, spread=0.2)
    assert resolve([live], side="bid").value == pytest.approx(30.9)
    assert resolve([live], side="ask").value == pytest.approx(31.1)
    assert resolve([close(YESTERDAY_CLOSE, 30.5)], side="bid").value == pytest.approx(30.5)
    one_sided = PriceCandidate(
        hub="TTF", period_start=DEC[0], period_end=DEC[1], kind=LIVE_TICK, value=None,
        unit="EUR/MWh", source_system="EEX", as_of_utc=NOW, bid=30.0, state="current",
    )
    # A one-sided tick has no mid: the close answers the mid, the tick the bid.
    assert resolve([one_sided, close(YESTERDAY_CLOSE, 30.5)]).kind == SETTLEMENT
    assert resolve([one_sided, close(YESTERDAY_CLOSE, 30.5)], side="bid").kind == LIVE_TICK
    with pytest.raises(ValueError):
        resolve([live], side="last")


# ------------------------------------------------------------------------- firm marks


def mark(entered: datetime, value: float) -> PriceCandidate:
    return close(entered, value, source="operator-input", kind=FIRM_MARK)


def test_a_firm_mark_never_beats_an_in_date_market_price():
    # Entered after the close, still not a market price: the close wins.
    answer = resolve([close(YESTERDAY_CLOSE, 31.2), mark(NOW - timedelta(minutes=5), 33.0)])
    assert answer.kind == SETTLEMENT


def test_a_firm_mark_prices_a_month_whose_market_prices_are_stale():
    old_close = close(datetime(2026, 11, 16, 17, tzinfo=UTC), 29.0)  # a week old: stale
    answer = resolve([old_close, tick(3 * 60, 30.0), mark(YESTERDAY_CLOSE, 31.5)])
    assert answer.kind == FIRM_MARK and answer.value == pytest.approx(31.5)
    assert answer.basis == BASIS_FIRM_MARK and answer.state == "current"


def test_the_newest_firm_mark_wins_and_a_mark_beats_a_derived_price():
    derived = close(NOW - timedelta(hours=1), 30.0, kind=DERIVED, source="curve")
    answer = resolve([derived, mark(YESTERDAY_CLOSE, 31.0), mark(NOW - timedelta(hours=2), 32)])
    assert answer.kind == FIRM_MARK and answer.value == 32


def test_a_stale_firm_mark_is_not_preferred_over_a_fresher_stale_price():
    old_mark = mark(datetime(2026, 11, 2, 9, tzinfo=UTC), 35.0)
    old_close = close(datetime(2026, 11, 16, 17, tzinfo=UTC), 29.0)
    answer = resolve([old_mark, old_close])
    assert answer.kind == SETTLEMENT and answer.state == "stale"
    assert answer.basis == BASIS_NOTHING_IN_DATE


# ------------------------------------------------------------------------- derived


def test_a_derived_price_is_used_only_when_no_direct_price_is_in_date():
    derived = close(NOW - timedelta(hours=1), 30.0, kind=DERIVED, source="curve")
    assert resolve([derived, close(YESTERDAY_CLOSE, 31.0)]).kind == SETTLEMENT
    stale_close = close(datetime(2026, 11, 13, 17, tzinfo=UTC), 31.0)
    answer = resolve([derived, stale_close])
    assert answer.kind == DERIVED and answer.basis == BASIS_DERIVED


# ------------------------------------------------------------------------- entitlement


def test_a_source_the_caller_does_not_hold_is_never_used():
    licensed = tick(0.5, 31.75, source="EEX")
    public = close(YESTERDAY_CLOSE, 31.2, source="ICE_ENDEX")

    def entitled(source: str) -> bool:
        return source != "EEX"

    answer = resolve([licensed, public], entitled=entitled)
    assert answer.source_system == "ICE_ENDEX" and answer.considered == 1
    assert resolve([licensed], entitled=entitled) is None


def test_a_real_price_always_wins_over_a_simulated_one():
    demo = tick(0.5, 40.0, source="EEX_Sim", simulated=True)
    stale_real = close(datetime(2026, 11, 13, 17, tzinfo=UTC), 31.0)
    answer = resolve([demo, stale_real])
    assert not answer.simulated and answer.state == "stale"
    # Simulated prices only where allowed, and then labelled.
    assert resolve([demo], allow_simulated=False) is None
    assert resolve([demo]).simulated


# ------------------------------------------------------------------------- the frame


def test_other_hubs_periods_and_future_prices_are_ignored():
    jan = PriceCandidate(
        hub="TTF", period_start=date(2027, 1, 1), period_end=date(2027, 2, 1),
        kind=SETTLEMENT, value=35.0, unit="EUR/MWh", source_system="EEX",
        as_of_utc=YESTERDAY_CLOSE,
    )
    nbp = PriceCandidate(
        hub="NBP", period_start=DEC[0], period_end=DEC[1], kind=SETTLEMENT, value=28.0,
        unit="GBP/MWh", source_system="EEX", as_of_utc=YESTERDAY_CLOSE,
    )
    future = close(NOW + timedelta(minutes=5), 50.0)
    assert resolve([jan, nbp, future]) is None
    inclusive = PriceCandidate(
        hub="ttf", period_start=DEC[0], period_end=date(2026, 12, 31), kind=SETTLEMENT,
        value=31.0, unit="EUR/MWh", source_system="EEX", as_of_utc=YESTERDAY_CLOSE,
    )
    assert resolve([inclusive]).value == 31.0


def test_judging_ticks_and_closes():
    assert judge(tick(0.5, 1.0), NOW) == "current"
    assert judge(tick(10, 1.0), NOW) == "late"
    assert judge(tick(31, 1.0), NOW) == "stale"
    assert judge(tick(31, 1.0, state="late"), NOW) == "late"  # the caller's judgement holds
    undeclared = PriceCandidate(
        hub="TTF", period_start=DEC[0], period_end=DEC[1], kind=LIVE_TICK, value=1.0,
        unit="EUR/MWh", source_system="X", as_of_utc=NOW,
    )
    assert judge(undeclared, NOW) == "stale"  # no declared cadence: never fresh
    assert judge(close(YESTERDAY_CLOSE, 1.0), NOW) == "current"
    assert judge(close(datetime(2026, 11, 20, 17, tzinfo=UTC), 1.0), NOW) == "late"
    assert judge(close(datetime(2026, 11, 19, 17, tzinfo=UTC), 1.0), NOW) == "stale"


def test_month_window_normalises_inclusive_and_gas_day_ends():
    assert month_window(date(2026, 12, 1), date(2026, 12, 31)) == DEC
    assert month_window(date(2026, 2, 1), date(2026, 2, 28)) == (
        date(2026, 2, 1), date(2026, 3, 1))
    assert month_window(date(2026, 11, 25), date(2026, 11, 26)) == (
        date(2026, 11, 25), date(2026, 11, 26))


def test_the_answer_is_plain_data():
    data = resolve([tick(0.5, 31.75)]).as_dict()
    assert data["kind"] == "live_tick" and data["period_start"] == "2026-12-01"
    assert data["as_of_utc"].startswith("2026-11-24T09:59")
