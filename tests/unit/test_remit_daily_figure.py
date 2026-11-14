"""REMIT unavailable capacity as a daily figure: one conversion, through the unit authority."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from eurogas_nexus.domain.observations.remit_umm import (
    daily_figure,
    gas_day_hours,
    outage_unit_summary,
    outage_view,
    parse_umm_export,
)

START = datetime(2026, 11, 16, 5, tzinfo=UTC)
STOP = datetime(2026, 11, 28, 5, tzinfo=UTC)


@pytest.mark.parametrize(
    ("at", "hours"),
    [
        (datetime(2026, 11, 16, 12, tzinfo=UTC), 24.0),
        (datetime(2027, 3, 27, 12, tzinfo=UTC), 23.0),  # clocks go forward on 28 Mar
        (datetime(2026, 10, 24, 12, tzinfo=UTC), 25.0),  # clocks go back on 25 Oct
    ],
)
def test_gas_day_length_follows_the_clock_changes(at, hours):
    assert gas_day_hours(at) == hours


def test_hourly_rate_times_the_gas_days_hours():
    # Gas Storage Denmark, live: 2,370,000 kWh/h unavailable.
    figure = daily_figure("kWh/h", 2_370_000, technical=6_500_000, asset_type="storage",
                          start=START, stop=STOP)
    assert figure.basis == "per_hour_x_24h"
    assert figure.gwh_d == pytest.approx(56.88)
    assert figure.gwh_h == pytest.approx(2.37)
    long_day = daily_figure("kWh/h", 2_370_000, start=START, stop=STOP,
                            at=datetime(2026, 10, 24, 12, tzinfo=UTC))
    assert long_day.basis == "per_hour_x_25h"
    assert long_day.gwh_d == pytest.approx(59.25)


@pytest.mark.parametrize(
    ("unit", "value", "gwh_d", "mcm_d"),
    [
        ("GWh/d", 31.2, 31.2, None),
        ("kWh/d", 5_000_000, 5.0, None),
        ("MWh/d", 1_500, 1.5, None),
        ("mcm/d", 3.0, None, 3.0),
        ("MSm3/d", 2.5, None, 2.5),
        ("GWh/day", 10.0, 10.0, None),
    ],
)
def test_daily_units_convert_directly(unit, value, gwh_d, mcm_d):
    figure = daily_figure(unit, value, start=START, stop=STOP)
    assert figure.basis == "per_day"
    assert figure.gwh_d == (pytest.approx(gwh_d) if gwh_d is not None else None)
    assert figure.mcm_d == (pytest.approx(mcm_d) if mcm_d is not None else None)


def test_storage_energy_without_rate_is_working_volume_not_a_daily_rate():
    # Gas Storage Denmark, live: technical 8,590 GWh (its working volume), 400 unavailable.
    figure = daily_figure("GWh", 400, technical=8_590, asset_type="storage",
                          start=START, stop=STOP)
    assert not figure.converted
    assert figure.basis == "unconverted:working_volume_not_rate"
    assert figure.total_gwh == 400
    assert daily_figure("TWh", 2.751595, asset_type="storage").total_gwh == pytest.approx(
        2751.595
    )


def test_energy_over_a_known_event_is_an_average_labelled_as_such():
    figure = daily_figure("GWh", 120, asset_type="production", start=START, stop=STOP)
    assert figure.basis == "event_average"
    assert figure.gwh_d == pytest.approx(10.0)  # 120 GWh over 12 days
    no_end = daily_figure("GWh", 120, asset_type="production", start=START)
    assert no_end.basis == "unconverted:total_without_duration"


def test_an_implausible_facility_rate_is_refused_as_a_unit_error():
    # EPE-H, live: 469.2 "GWh/h" technical is 11 TWh/d for one storage site.
    figure = daily_figure("GWh/h", 70.38, technical=469.2, start=START, stop=STOP)
    assert not figure.converted
    assert figure.basis == "unconverted:implausible_for_unit:GWh/h"


def test_unknown_units_are_named():
    assert daily_figure("bananas", 1.0).basis == "unconverted:unknown_unit:bananas"
    assert daily_figure("", 1.0).basis == "unconverted:unknown_unit:-"
    assert daily_figure("GWh/d", None).basis == "unconverted:no_unavailable_capacity"


def _export(*messages):
    return json.dumps([
        {"messageId": f"M{i}", "version": 1, "eventStart": "2026-11-16T05:00:00Z",
         "eventStop": "2026-11-28T05:00:00Z", "assetName": f"A{i}",
         "assetType": "storage", "unitMeasure": unit, "unavailableCapacity": value}
        for i, (unit, value) in enumerate(messages)
    ])


def test_import_and_read_agree_and_unconverted_are_counted():
    messages = parse_umm_export(
        _export(("kWh/h", 1_000_000), ("GWh/d", 20), ("GWh", 400), ("GWh/h", 500)),
        source_reference="test",
    )
    assert [m.unavailable_gwh_d for m in messages] == [pytest.approx(24.0), 20, None, None]
    rows = outage_view(messages, now=datetime(2026, 11, 14, tzinfo=UTC))
    assert sorted(r["unavailable_gwh_d"] or 0 for r in rows) == [0, 0, 20, pytest.approx(24)]
    summary = outage_unit_summary(rows)
    assert summary["with_daily_figure"] == 2
    assert summary["unconverted_count"] == 2
    assert summary["unconverted_units"] == {"GWh": 1, "GWh/h": 1}
    assert summary["unconverted_reasons"] == {
        "implausible_for_unit": 1,
        "working_volume_not_rate": 1,
    }


def test_stored_rows_without_a_figure_are_re_derived_on_read():
    message = parse_umm_export(_export(("kWh/h", 1_000_000)), source_reference="t")[0]
    from dataclasses import replace

    old = replace(message, unavailable_gwh_d=None)  # stored before kWh/h converted
    row = outage_view([old], now=datetime(2026, 11, 20, tzinfo=UTC))[0]
    assert row["unavailable_gwh_d"] == pytest.approx(24.0)
    assert row["daily_basis"] == "per_hour_x_24h"
