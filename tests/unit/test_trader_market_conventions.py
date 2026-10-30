"""Trader conventions: product calendar, unit conversion and storage trajectory."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from eurogas_nexus.domain.market.products import (
    STANDARD_STRIP,
    ProductCodeError,
    resolve_product,
    standard_strip,
)
from eurogas_nexus.domain.market.storage_targets import (
    StorageDay,
    StorageTrajectoryError,
    storage_trajectory,
)
from eurogas_nexus.domain.market.units import (
    UnitConversionError,
    canonical_price_unit,
    convert_energy,
    convert_price,
    volume_to_mwh,
)

FRIDAY = date(2026, 10, 30)


def _span(code: str, trade: date = FRIDAY) -> tuple[str, str, str]:
    period = resolve_product(code, trade)
    return period.label, period.first_gas_day.isoformat(), period.last_gas_day.isoformat()


def test_friday_day_ahead_delivers_monday_and_weekend_is_sat_sun():
    assert _span("DA") == ("2026-11-02", "2026-11-02", "2026-11-02")
    assert _span("WE")[1:] == ("2026-10-31", "2026-11-01")
    assert _span("WD")[1:] == ("2026-10-30", "2026-10-30")


def test_day_ahead_skips_explicit_holidays():
    period = resolve_product("DA", FRIDAY, holidays=[date(2026, 11, 2)])
    assert period.first_gas_day == date(2026, 11, 3)


def test_bom_runs_to_month_end_and_is_absent_on_last_day():
    assert _span("BOM") == ("BOM Oct-26", "2026-10-31", "2026-10-31")
    with pytest.raises(ProductCodeError):
        resolve_product("BOM", date(2026, 10, 31))
    assert "BOM" not in [p.code for p in standard_strip(date(2026, 10, 31))]


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("M+1", ("Nov-26", "2026-11-01", "2026-11-30")),
        ("MA", ("Nov-26", "2026-11-01", "2026-11-30")),
        ("M+3", ("Jan-27", "2027-01-01", "2027-01-31")),
        ("Q+1", ("Q1-27", "2027-01-01", "2027-03-31")),
        ("S+1", ("Sum-27", "2027-04-01", "2027-09-30")),
        ("S+2", ("Win-27", "2027-10-01", "2028-03-31")),
        ("GY+1", ("GY-27", "2027-10-01", "2028-09-30")),
        ("Cal+1", ("Cal-27", "2027-01-01", "2027-12-31")),
        ("cal-27", ("Cal-27", "2027-01-01", "2027-12-31")),
        ("Win-26", ("Win-26", "2026-10-01", "2027-03-31")),
        ("Q1-27", ("Q1-27", "2027-01-01", "2027-03-31")),
        ("Dec-26", ("Dec-26", "2026-12-01", "2026-12-31")),
    ],
)
def test_relative_and_absolute_codes(code, expected):
    assert _span(code) == expected


def test_season_ahead_from_summer_and_from_early_year():
    assert _span("S+1", date(2026, 6, 15))[0] == "Win-26"
    assert _span("S+1", date(2027, 2, 1))[0] == "Sum-27"
    assert _span("GY+1", date(2027, 2, 1))[0] == "GY-27"


def test_delivery_hours_follow_dst_and_gas_day_boundaries():
    october = resolve_product("Oct-27", date(2027, 9, 1))
    # Clocks go back on 31 Oct 2027: the month carries 31*24 + 1 hours.
    assert october.hours == 31 * 24 + 1
    march = resolve_product("Mar-27", date(2027, 2, 1))
    assert march.hours == 31 * 24 - 1
    assert october.delivery_start_utc == datetime(2027, 10, 1, 4, tzinfo=UTC)
    assert october.delivery_end_utc == datetime(2027, 11, 1, 5, tzinfo=UTC)


def test_unknown_and_fully_delivered_codes_are_refused():
    for code in ("XYZ", "M+0", "M+99", "Sep-26"):
        with pytest.raises(ProductCodeError):
            resolve_product(code, FRIDAY)


def test_standard_strip_is_ordered_and_complete_mid_month():
    strip = standard_strip(date(2026, 10, 15))
    assert [p.code for p in strip] == list(STANDARD_STRIP)
    assert strip[0].as_dict()["kind"] == "within_day"


def test_energy_factors():
    assert convert_energy(1, "MWh", "therm") == pytest.approx(34.1214163, rel=1e-8)
    assert convert_energy(1, "MWh", "MMBtu") == pytest.approx(3.41214163, rel=1e-8)
    assert convert_energy(1, "TWh", "GWh") == pytest.approx(1000)
    assert volume_to_mwh(1_000_000, 10.55) == pytest.approx(10_550)
    with pytest.raises(UnitConversionError):
        volume_to_mwh(1, 0)


def test_price_conversion_between_hub_quotations():
    rates = {"GBP": 0.85, "USD": 1.10}
    # 35 EUR/MWh -> 35 * 0.85 * 100 / 34.1214 = 87.19 p/th
    assert convert_price(35, "EUR/MWh", "p/th", eur_rates=rates) == pytest.approx(87.1889, 1e-4)
    assert convert_price(35, "EUR/MWh", "USD/MMBtu", eur_rates=rates) == pytest.approx(
        35 * 1.10 / 3.41214163, 1e-9
    )
    round_trip = convert_price(
        convert_price(80, "GBp/th", "EUR/MWh", eur_rates=rates),
        "EUR/MWh",
        "GBp/th",
        eur_rates=rates,
    )
    assert round_trip == pytest.approx(80)
    assert convert_price(10, "EUR/MWh", "EUR/GJ") == pytest.approx(10 / 3.6)
    assert canonical_price_unit("gbp/th") == "GBp/th"


def test_price_conversion_requires_explicit_fx():
    with pytest.raises(UnitConversionError):
        convert_price(35, "EUR/MWh", "GBp/th")
    with pytest.raises(UnitConversionError):
        convert_price(35, "EUR/MWh", "JPY/MWh", eur_rates={"GBP": 0.85})


def _series(start: date, days: int, start_twh: float, per_day: float, capacity=1000.0):
    return [
        StorageDay(
            gas_day=start + timedelta(days=i),
            inventory_twh=start_twh + per_day * i,
            working_capacity_twh=capacity,
            injection_twh_d=per_day,
            withdrawal_twh_d=0.0,
        )
        for i in range(days)
    ]


def test_trajectory_on_track_and_behind():
    series = _series(date(2026, 8, 1), 10, 700.0, 3.0)
    latest = series[-1]
    on_track = storage_trajectory("eu", series)
    assert on_track.code == "EU"
    assert on_track.as_of_gas_day == latest.gas_day
    assert on_track.fill_pct == pytest.approx(72.7)
    assert on_track.deadline == date(2026, 12, 1)
    assert on_track.window_open == date(2026, 10, 1)
    assert on_track.gap_twh == pytest.approx(900 - 727)
    assert on_track.required_net_injection_to_window_twh_d == pytest.approx(173 / 52)
    assert on_track.recent_net_injection_twh_d == pytest.approx(3.0)
    assert on_track.status == "on_track"

    slow = storage_trajectory("EU", _series(date(2026, 8, 1), 10, 600.0, 1.0))
    assert slow.status == "behind"
    assert slow.projected_fill_at_deadline_pct < 90


def test_trajectory_deviation_and_target_met():
    series = _series(date(2026, 9, 1), 5, 860.0, 1.0)
    relaxed = storage_trajectory("DE", series, deviation_pp=5)
    assert relaxed.effective_target_pct == 85
    assert relaxed.status == "target_met"
    assert relaxed.required_net_injection_to_deadline_twh_d == 0.0


def test_trajectory_in_winter_is_withdrawal_season_and_falls_back_to_deltas():
    series = [
        StorageDay(date(2027, 1, 10) + timedelta(days=i), 600.0 - 5 * i, 1000.0)
        for i in range(4)
    ]
    result = storage_trajectory("NL", series)
    assert result.deadline == date(2027, 12, 1)
    assert result.status == "withdrawal_season"
    assert result.projected_fill_at_deadline_pct is None
    assert result.recent_net_injection_twh_d == pytest.approx(-5.0)
    assert result.pace_days_used == 3


def test_trajectory_refuses_bad_inputs():
    with pytest.raises(StorageTrajectoryError):
        storage_trajectory("EU", [])
    with pytest.raises(StorageTrajectoryError):
        storage_trajectory("EU", _series(date(2026, 8, 1), 2, 1.0, 1.0, capacity=0.0))
    with pytest.raises(StorageTrajectoryError):
        storage_trajectory("EU", _series(date(2026, 8, 1), 2, 1.0, 1.0), target_pct=120)


# --- FX benchmark fixings (ECB / WM/Reuters / BFIX) -------------------------------

from eurogas_nexus.domain.market.fx_fixings import (  # noqa: E402
    FxFixingError,
    eur_rates_from_pairs,
    parse_fixing_export,
    resolve_fixing,
    select_fixing_rates,
)

WMR_EXPORT = """Date,RIC,Mid
2026-10-27,EURUSDFIXM=WM,1.0800
2026-10-27,GBPUSDFIXM=WM,1.2700
2026-10-28,EURUSDFIXM=WM,1.0900
2026-10-28,GBPUSDFIXM=WM,1.2800
"""


def test_fixing_resolution_and_instants():
    wmr = resolve_fixing("wmr")
    assert wmr.fixing_id == "WMR_1600_LDN" and wmr.licensed
    # 4pm London is 15:00 UTC in BST and 16:00 UTC in GMT.
    assert wmr.fixing_instant_utc(date(2026, 10, 23)).hour == 15
    assert wmr.fixing_instant_utc(date(2026, 10, 26)).hour == 16
    assert resolve_fixing(None).source_system == "ECB"
    assert resolve_fixing("BFIX", "BFIX_1400_CET").label.startswith("Bloomberg")
    for source, fixing in (("XYZ", None), ("WMR", "BFIX_1600_LDN"), ("WMR", "nope")):
        with pytest.raises(FxFixingError):
            resolve_fixing(source, fixing)


def test_usd_quoted_pairs_are_crossed_to_eur_base():
    rates = eur_rates_from_pairs({"EURUSD": 1.08, "GBPUSD": 1.27, "USDJPY": 150.0})
    assert rates["USD"] == pytest.approx(1.08)
    assert rates["GBP"] == pytest.approx(1.08 / 1.27)
    assert rates["JPY"] == pytest.approx(1.08 * 150.0)
    assert eur_rates_from_pairs({"EURGBP": 0.85, "GBPUSD": 1.3})["GBP"] == 0.85


def test_parse_export_reads_rics_and_refuses_bad_rows():
    rows = parse_fixing_export(WMR_EXPORT, resolve_fixing("WMR"), source_reference="t")
    assert [row.pair for row in rows] == ["EURUSD", "GBPUSD", "EURUSD", "GBPUSD"]
    record = rows[0].as_record()
    assert record["source_system"] == "WMR"
    assert record["rate_type"] == "WMR_1600_LDN"
    assert record["observed_at_utc"] == datetime(2026, 10, 27, 16, tzinfo=UTC)
    for bad in (
        "date,pair\n2026-10-27,EURUSD\n",
        "date,pair,rate\n27/10/2026,EURUSD,1.08\n",
        "date,pair,rate\n2026-10-27,EURUSD,-1\n",
        "date,pair,rate\n2026-10-27,EURUSD,1.08\n2026-10-27,EURUSD,1.09\n",
        "date,pair,rate\n",
    ):
        with pytest.raises(FxFixingError):
            parse_fixing_export(bad, resolve_fixing("WMR"), source_reference="t")


def test_select_latest_dated_and_period_average():
    fixing = resolve_fixing("WMR")
    rows = [
        row.as_record()
        for row in parse_fixing_export(WMR_EXPORT, fixing, source_reference="t")
    ]
    rows.append({**rows[0], "source_system": "BFIX", "rate": 9.9})  # other source ignored
    latest = select_fixing_rates(rows, fixing)
    assert latest["value_dates"] == ["2026-10-28"]
    assert latest["eur_rates"]["USD"] == pytest.approx(1.09)
    dated = select_fixing_rates(rows, fixing, on=date(2026, 10, 27))
    assert dated["eur_rates"]["GBP"] == pytest.approx(1.08 / 1.27)
    avg = select_fixing_rates(
        rows, fixing, average_from=date(2026, 10, 1), average_to=date(2026, 10, 31)
    )
    assert avg["fixings_used"] == 2
    assert avg["eur_rates"]["USD"] == pytest.approx(1.085)
    assert avg["eur_rates"]["GBP"] == pytest.approx(1.085 / 1.275)
    assert select_fixing_rates(rows, fixing, on=date(2026, 1, 1))["eur_rates"] == {}
    with pytest.raises(FxFixingError):
        select_fixing_rates(rows, fixing, average_from=date(2026, 10, 1))
