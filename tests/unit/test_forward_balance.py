"""Forward balance: golden cases for the method, its error and its what-ifs."""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from eurogas_nexus.domain.fundamentals.balance import BalanceHistoryDay, forecast_balance
from eurogas_nexus.domain.fundamentals.forward_balance import (
    HddReference,
    Overrides,
    SupplyOutage,
    backtest_daily,
    build_forward_balance,
    fit_demand,
    hdd_change,
    weakest,
)
from eurogas_nexus.reference_data import network_bundle

# A winter-peaking region: 12 HDD a day in January, none in July.
SEASON_HDD = {1: 12.0, 2: 11.0, 3: 9.0, 4: 6.0, 5: 3.0, 6: 1.0, 7: 0.0, 8: 0.0, 9: 2.0,
              10: 5.0, 11: 9.0, 12: 11.0}
A, B = 2000.0, 150.0  # demand = 2000 + 150 GWh/d per HDD


def _reference(first_year=2020, last_year=2026) -> HddReference:
    per_day = {f"{y}-{m:02d}": SEASON_HDD[m] for y in range(first_year, last_year + 1)
               for m in range(1, 13)}
    return HddReference(per_day=per_day, first_month=f"{first_year}-01",
                        last_month=f"{last_year}-12")


def _history(last: date, days: int = 800) -> list[BalanceHistoryDay]:
    rows = []
    for k in range(days, 0, -1):
        day = last - timedelta(days=k - 1)
        call = A + B * SEASON_HDD[day.month]
        norway, lng = 3200.0, 1100.0
        rows.append(BalanceHistoryDay(day=day, norway_gwh=norway, lng_gwh=lng,
                                      storage_net_withdrawal_gwh=call - norway - lng))
    return rows


def _base(history, start, days=14, outages=()):
    from eurogas_nexus.domain.fundamentals.balance import Outage

    forecast = forecast_balance(
        history, start=start, days=days,
        norway_outages=[Outage(o.start, o.end, o.gwh_d) for o in outages if o.line == "norway"],
        inventory_twh=600.0, working_capacity_twh=1000.0,
    )
    return [d.as_dict() for d in forecast.days]


LAST = date(2026, 11, 15)


def test_the_monthly_fit_recovers_the_demand_rule():
    fit = fit_demand(_history(LAST), _reference())
    assert fit is not None and fit.months >= 20
    assert fit.slope_per_hdd == pytest.approx(B, rel=1e-6)
    assert fit.intercept == pytest.approx(A, rel=1e-6)
    assert fit.r2 == pytest.approx(1.0)


def test_a_normal_season_reads_about_normal_with_its_error():
    history = _history(LAST)
    result = build_forward_balance(
        history, _base(history, LAST + timedelta(days=1)), hdd=_reference(),
    )
    assert len(result.daily) == 14 and len(result.monthly) == 3
    assert result.headline["direction"] == "about_normal"
    assert [m["month"] for m in result.monthly] == ["2026-12", "2027-01", "2027-02"]
    january = result.monthly[1]
    assert january["demand_gwh_d"] == pytest.approx(A + B * 12.0, abs=0.5)
    # Supply minus demand is minus the storage draw.
    assert january["gap_gwh_d"] == pytest.approx(-january["storage_gwh_d"], abs=0.2)
    # Every daily figure carries an error from the backtest.
    assert all(row["demand_error_gwh_d"] is not None for row in result.daily)
    assert result.backtest["daily"]["origins"] > 0
    assert result.overridden == []


def test_an_outage_tightens_the_balance_and_is_named_the_cause():
    history = _history(LAST)
    start = LAST + timedelta(days=1)
    outage = SupplyOutage("norway", start, start + timedelta(days=30), 600.0)
    result = build_forward_balance(
        history, _base(history, start, outages=[outage]), hdd=_reference(), outages=[outage],
    )
    headline = result.headline
    assert headline["direction"] == "tighter"
    # The rest is the step in demand at the month boundary that the ±3-day normal smooths.
    assert headline["gwh_d"] == pytest.approx(600.0, abs=40.0)
    assert headline["main_driver"] == "norway"
    assert headline["contributions_gwh_d"]["norway"] == pytest.approx(600.0, abs=1.0)
    assert result.daily[0]["norway_outage_gwh_d"] == pytest.approx(600.0)
    # The December month carries the outage on the days it runs.
    december = result.monthly[0]
    assert 0 < december["norway_outage_gwh_d"] < 600.0


def test_a_colder_what_if_raises_demand_by_the_fitted_slope_and_is_named():
    history = _history(LAST)
    base = _base(history, LAST + timedelta(days=1))
    normal = build_forward_balance(history, base, hdd=_reference())
    colder = build_forward_balance(
        history, base, hdd=_reference(), overrides=Overrides(temperature_shift_c=-2.0),
        backtest=normal.backtest["daily"],
    )
    assert colder.overridden == ["temperature_shift_c"]
    assert colder.daily[0]["demand_gwh_d"] - normal.daily[0]["demand_gwh_d"] == pytest.approx(
        2 * B, abs=0.2)
    assert colder.monthly[1]["storage_gwh_d"] > normal.monthly[1]["storage_gwh_d"]
    # Storage takes the extra demand: the inventory ends lower.
    assert colder.monthly[-1]["inventory_twh_end"] < normal.monthly[-1]["inventory_twh_end"]


def test_warming_never_takes_hdd_below_zero():
    assert hdd_change(1.5, 3.0) == -1.5
    assert hdd_change(10.0, 3.0) == -3.0
    assert hdd_change(0.0, -2.0) == 2.0


def test_an_added_outage_and_a_typed_lng_rate_are_overrides():
    history = _history(LAST)
    start = LAST + timedelta(days=1)
    added = SupplyOutage("lng", start, start + timedelta(days=3), 200.0, source="manual")
    result = build_forward_balance(
        history, _base(history, start), hdd=_reference(),
        overrides=Overrides(lng_gwh_d=900.0, added_outage=added),
    )
    assert result.overridden == ["lng_gwh_d", "added_outage"]
    assert result.daily[0]["lng_gwh_d"] == pytest.approx(700.0)
    assert result.daily[5]["lng_gwh_d"] == pytest.approx(900.0)


def test_backtest_measures_the_daily_method_against_outturn():
    report = backtest_daily(_history(LAST))
    horizons = {row["horizon_days"]: row for row in report["horizons"]}
    assert set(horizons) == {1, 7, 14}
    # On a history that repeats itself exactly, the seasonal method is near perfect except
    # where a month boundary moves the level (the normal uses ±3 days).
    assert all(row["n"] > 30 for row in horizons.values())
    assert horizons[1]["mae_gwh_d"] < 200


def test_the_weakest_input_sets_the_class():
    assert weakest(["observed", "forecast"]) == "forecast"
    assert weakest(["observed", "manual", "assumption"]) == "manual"
    assert weakest([]) == "assumption"


def test_the_shipped_eurostat_reference_is_whole_and_weighted():
    path = network_bundle.bundle_path().with_name("nwe_hdd_eurostat.json")
    table = json.loads(path.read_text(encoding="utf-8"))
    assert set(table["weights"]) == {"GB", "NL", "BE", "DE", "FR", "DK", "LU"}
    assert sum(table["weights"].values()) == pytest.approx(1.0, abs=1e-5)
    assert all(len(v) == len(table["months"]) for v in table["monthly_hdd"].values())
    reference = HddReference.from_table(table)
    january, spread, years = reference.normal(1)
    july = reference.normal(7)[0]
    assert years == 30 and january > 10 > july and spread > 0
    assert "Eurostat" in table["attribution"] and table["licence"] == "CC BY 4.0"
