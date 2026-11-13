"""Elexon (GB power) parsing: gas is CCGT plus OCGT, the index is not a day-ahead price."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from eurogas_nexus.ingestion.elexon_insights import (
    ElexonParseError,
    parse_demand,
    parse_generation,
    parse_market_index,
    request_urls,
)

T0 = "2026-11-10T00:00:00Z"
T1 = "2026-11-10T00:30:00Z"


def _fuel(fuel: str, start: str, value: float | None) -> dict:
    return {"fuelType": fuel, "startTime": start, "publishTime": start, "generation": value}


def test_gas_generation_is_ccgt_plus_ocgt_per_period() -> None:
    rows = parse_generation(
        {
            "data": [
                _fuel("CCGT", T0, 9000),
                _fuel("OCGT", T0, 12),
                _fuel("CCGT", T1, 8000),
                _fuel("WIND", T0, 5000),
                _fuel("NUCLEAR", T0, 4000),
                _fuel("CCGT", "2026-11-10T01:00:00Z", None),
            ]
        }
    )
    by_key = {(row.metric, row.period_start_utc.isoformat()): row for row in rows}
    assert by_key[("gas_generation", "2026-11-10T00:00:00+00:00")].value == 9012
    assert by_key[("gas_generation", "2026-11-10T00:30:00+00:00")].value == 8000
    assert by_key[("wind_generation", "2026-11-10T00:00:00+00:00")].value == 5000
    assert len(rows) == 3  # nuclear is not kept; a period with no value is absent, not zero
    assert {row.zone for row in rows} == {"GB"} and {row.unit for row in rows} == {"MW"}
    assert all(row.observation_id.startswith("elexon:") for row in rows)
    first = rows[0]
    assert (first.period_end_utc - first.period_start_utc).total_seconds() == 1800


def test_demand_is_initial_national_demand_outturn() -> None:
    rows = parse_demand(
        [
            {"startTime": T0, "publishTime": T1, "initialDemandOutturn": 27000},
            {"startTime": T1, "initialDemandOutturn": None},
        ]
    )
    assert [(row.metric, row.value) for row in rows] == [("load_actual", 27000.0)]
    assert rows[0].published_at_utc == datetime(2026, 11, 10, 0, 30, tzinfo=UTC)


def test_market_index_keeps_traded_apx_periods_under_its_own_metric() -> None:
    rows = parse_market_index(
        {
            "data": [
                {"dataProvider": "APXMIDP", "startTime": T0, "price": 82.5, "volume": 410.0},
                {"dataProvider": "APXMIDP", "startTime": T1, "price": 0.0, "volume": 0.0},
                {"dataProvider": "N2EXMIDP", "startTime": T0, "price": 0.0, "volume": 0.0},
            ]
        }
    )
    assert len(rows) == 1
    assert (rows[0].metric, rows[0].value, rows[0].unit) == ("market_index_price", 82.5, "GBP/MWh")


def test_a_response_of_another_shape_is_an_error_not_an_empty_day() -> None:
    with pytest.raises(ElexonParseError):
        parse_generation({"data": "unavailable"})
    with pytest.raises(ElexonParseError):
        parse_generation({"data": [_fuel("CCGT", "yesterday", 1.0)]})


def test_requests_name_the_public_host_and_carry_no_key() -> None:
    urls = request_urls(date(2026, 11, 10), date(2026, 11, 10))
    assert set(urls) == {"generation", "demand", "market_index"}
    for url in urls.values():
        assert url.startswith("https://data.elexon.co.uk/bmrs/api/v1/")
        assert "key" not in url.lower()
    assert "to=2026-11-11T00%3A00Z" in urls["market_index"]
