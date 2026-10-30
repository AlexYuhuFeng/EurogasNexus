"""ENTSO-E Transparency documents parse into point-in-time power observations."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from eurogas_nexus.ingestion.entsoe_transparency import (
    EntsoeParseError,
    parse_document,
    request_url,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "entsoe"


def _parse(name):
    return parse_document((FIXTURES / name).read_bytes(), source_reference=name)


def test_day_ahead_prices_repeat_values_for_a03_blocks():
    rows = _parse("a44_nl_prices.xml")
    assert [(r.zone, r.metric, r.unit) for r in rows[:1]] == [("NL", "day_ahead_price", "EUR/MWh")]
    # Position 3 is absent; curve type A03 repeats position 2 until position 4.
    assert [r.value for r in rows] == [92.10, 88.40, 88.40, 85.00]
    assert rows[0].period_start_utc == datetime(2026, 10, 29, 23, tzinfo=UTC)
    assert rows[-1].period_end_utc == datetime(2026, 10, 30, 3, tzinfo=UTC)
    # Created 11:58 UTC; the deadline (12:00 Brussels = 11:00 UTC the day before) is earlier.
    assert rows[0].published_at_utc == datetime(2026, 10, 29, 11, 0, tzinfo=UTC)


def test_load_keeps_gaps_for_a01_curves():
    rows = _parse("a65_gb_load.xml")
    assert {r.metric for r in rows} == {"load_actual"}
    assert [r.value for r in rows] == [24510, 23980, 23100]  # position 3 stays missing
    assert rows[1].period_start_utc == datetime(2026, 10, 30, 0, 30, tzinfo=UTC)


def test_generation_by_fuel_skips_consumption_and_unmapped_types():
    rows = _parse("a75_gb_generation.xml")
    by_metric = {}
    for row in rows:
        by_metric.setdefault(row.metric, []).append(row.value)
    assert by_metric == {"gas_generation": [8200, 8050], "wind_onshore_generation": [6400, 6650]}
    assert len({row.observation_id for row in rows}) == len(rows)


def test_acknowledgement_is_empty_and_unknown_documents_fail():
    assert _parse("acknowledgement.xml") == []
    with pytest.raises(EntsoeParseError):
        parse_document(
            b"<Other><type>A11</type><createdDateTime>2026-10-30T00:00Z</createdDateTime></Other>"
        )
    with pytest.raises(EntsoeParseError):
        parse_document(b"not xml")


def test_request_url_names_the_zone_and_window_without_logging_needs():
    url = request_url(
        "TOKEN", "A65", "GB", datetime(2026, 10, 29, tzinfo=UTC), datetime(2026, 10, 30, tzinfo=UTC)
    )
    assert "outBiddingZone_Domain=10YGB----------A" in url
    assert "periodStart=202610290000" in url and "processType=A16" in url


def test_backfilled_actuals_are_available_an_hour_after_the_period_not_at_download():
    rows = _parse("a65_gb_load.xml")  # document created 02:05 on 30 Oct
    assert rows[0].period_end_utc == datetime(2026, 10, 30, 0, 30, tzinfo=UTC)
    assert rows[0].published_at_utc == datetime(2026, 10, 30, 1, 30, tzinfo=UTC)
    assert rows[-1].published_at_utc == datetime(2026, 10, 30, 2, 5, tzinfo=UTC)  # created earlier
