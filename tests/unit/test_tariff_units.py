"""A published capacity tariff read per MWh for a stated product and load factor."""

from __future__ import annotations

from datetime import date

import pytest

from eurogas_nexus.domain.route_cost.tariff_units import parse_unit, per_mwh, period_days


def test_golden_a_yearly_reserve_price_per_kwh_h_at_full_load():
    # Gasunie Deutschland's 2026 firm yearly reserve price at VIP TTF-THE-H as published on
    # ENTSOG TP (read 19-11-2026): 7.06 EUR/(kWh/h)/y. One kWh/h for 365 days at 100 % load
    # carries 8.76 MWh, so 7.06 / 8.76 = 0.80594 EUR/MWh.
    read = per_mwh(7.06, "EUR/(kWh/h)/y", on=date(2026, 11, 19), anniversary=date(2026, 1, 1))
    assert read is not None
    assert read.value == pytest.approx(7.06 / 365 / 24 * 1000)
    assert read.value == pytest.approx(0.805936, abs=1e-6)
    assert (read.currency, read.unit) == ("EUR", "EUR/MWh")
    assert "365 days a year" in read.basis and "100% load factor" in read.basis


def test_golden_gb_pence_per_kwh_per_day():
    # National Gas's IP exit reserve price for 2026/27, 0.0356 p/kWh/d (pence per kWh/d of
    # capacity per day): 0.000356 GBP per kWh per day of flow = 0.356 GBP/MWh.
    read = per_mwh(0.0356, "p/kWh/d", on=date(2026, 11, 19))
    assert read.value == pytest.approx(0.356)
    assert read.currency == "GBP"


def test_kwh_d_capacity_and_a_gas_year_that_spans_a_leap_day():
    # 2027/28 runs over 29 February 2028: 366 days.
    read = per_mwh(0.13076854, "GBP/(kWh/d)/y", on=date(2027, 11, 1), anniversary=date(2027, 10, 1))
    assert read.value == pytest.approx(0.13076854 / 366 * 1000)
    assert period_days("y", date(2026, 11, 1), anniversary=date(2026, 10, 1)) == 365


@pytest.mark.parametrize(
    ("unit", "on", "days"),
    [
        ("EUR/(kWh/h)/q", date(2026, 11, 19), 92),  # Q4: Oct-Dec
        ("EUR/(kWh/h)/q", date(2027, 2, 1), 90),  # Q1 2027
        ("EUR/(kWh/h)/m", date(2027, 2, 10), 28),
        ("EUR/(kWh/h)/m", date(2026, 11, 19), 30),
        ("Euro/(kWh/h)/d", date(2026, 11, 19), 1),
    ],
)
def test_shorter_products_spread_their_price_over_their_own_days(unit, on, days):
    read = per_mwh(1.0, unit, on=on)
    assert read.value == pytest.approx(1.0 / days / 24 * 1000)
    assert read.currency == "EUR"


def test_within_day_price_per_hour():
    read = per_mwh(0.001, "EUR/(kWh/h)/h", on=date(2026, 11, 19))
    # Per kWh/h per hour: 1 kWh flows in that hour at full load.
    assert read.value == pytest.approx(0.001 * 1000)


def test_load_factor_spreads_the_capacity_cost_over_less_energy():
    full = per_mwh(7.06, "EUR/(kWh/h)/y", on=date(2026, 6, 1))
    half = per_mwh(7.06, "EUR/(kWh/h)/y", on=date(2026, 6, 1), load_factor=0.5)
    assert half.value == pytest.approx(2 * full.value)
    with pytest.raises(ValueError):
        per_mwh(7.06, "EUR/(kWh/h)/y", on=date(2026, 6, 1), load_factor=0)


def test_energy_units_pass_and_unknown_units_are_not_read():
    assert per_mwh(0.56, "EUR/MWh", on=date(2026, 11, 19)).value == pytest.approx(0.56)
    assert per_mwh(0.05, "p/kWh", on=date(2026, 11, 19)).value == pytest.approx(0.5)
    assert per_mwh(0.05, "p/therm", on=date(2026, 11, 19)) is None
    assert per_mwh(1.0, "EUR/(kWh/h)/w", on=date(2026, 11, 19)) is None
    assert per_mwh(1.0, "", on=date(2026, 11, 19)) is None
    # The row's currency and its unit's money disagree: not read.
    assert per_mwh(1.0, "EUR/(kWh/h)/y", on=date(2026, 11, 19), currency="GBP") is None
    assert per_mwh(1.0, "DKK/(kWh/h)/y", on=date(2026, 11, 19), currency="DKK").currency == "DKK"
    assert parse_unit("Euro/(kWh/h)/d").currency == "EUR"
