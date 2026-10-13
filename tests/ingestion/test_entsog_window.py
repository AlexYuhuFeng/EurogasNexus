"""Deterministic calendar, overlap and refusal tests; no providers or database."""

from datetime import UTC, datetime, timedelta

import pytest

from eurogas_nexus.ingestion.entsog_transport import EntsogWindowError
from eurogas_nexus.ingestion.entsog_window import EntsogWindowPolicy


@pytest.mark.parametrize(
    "instant,label",
    [
        ("2026-01-02T04:59:59+00:00", "2026-01-01"),
        ("2026-01-02T05:00:00+00:00", "2026-01-02"),
        ("2026-07-02T03:59:59+00:00", "2026-07-01"),
        ("2026-07-02T04:00:00+00:00", "2026-07-02"),
        ("2026-01-02T00:00:00+00:00", "2026-01-01"),
        ("2026-01-01T04:59:59+00:00", "2025-12-31"),
        ("2028-03-01T04:59:59+00:00", "2028-02-29"),
        ("2026-07-02T06:00:00+02:00", "2026-07-02"),
    ],
)
def test_exact_existing_calendar_rollover_and_utc_conversion(instant, label):
    window = EntsogWindowPolicy(lookback_gas_days=2).select(datetime.fromisoformat(instant))
    assert window.open_gas_day_label == label
    assert window.anchor_utc.tzinfo is UTC
    assert window.metadata()["calendar"] == "EU-CAM-UTC-2025"
    assert not window.metadata()["provider_date_envelope_is_exact_utc_filter"]
    assert not window.metadata()["snapshot_consistent"]


@pytest.mark.parametrize(
    "instant,hours", [("2026-03-29T04:00:00+00:00", 47), ("2026-10-25T05:00:00+00:00", 49)]
)
def test_dst_overlap_uses_calendar_days_with_23_and_25_hour_boundaries(instant, hours):
    window = EntsogWindowPolicy(lookback_gas_days=1).select(datetime.fromisoformat(instant))
    assert window.target_end_utc - window.target_start_utc == timedelta(hours=hours)


def test_daily_rollover_replays_overlap_with_bounded_maximum_span():
    policy = EntsogWindowPolicy(lookback_gas_days=30)
    first = policy.select(datetime(2026, 1, 2, 5, tzinfo=UTC))
    second = policy.select(datetime(2026, 1, 3, 5, tzinfo=UTC))
    assert first.from_date == "2025-12-03" and first.to_date == "2026-01-03"
    assert second.from_date == "2025-12-04" and second.to_date == "2026-01-04"
    assert first.target_end_utc > second.target_start_utc


@pytest.mark.parametrize("days", [-1, 0, 31, True, 1.5, "2"])
def test_invalid_rolling_bounds_refused_before_calendar_selection(days):
    with pytest.raises(EntsogWindowError):
        EntsogWindowPolicy(lookback_gas_days=days)


@pytest.mark.parametrize(
    "start,end", [("2026-01-01", None), (None, "2026-01-02"), ("2026-01-01", "2026-01-02")]
)
def test_mixed_rolling_and_explicit_policy_is_refused(start, end):
    with pytest.raises(EntsogWindowError):
        EntsogWindowPolicy(start, end, 2)


@pytest.mark.parametrize("anchor", [None, datetime(2026, 1, 2), "bad", "2026-01-02T05:00:00"])
def test_naive_or_invalid_anchor_never_assumed_utc(anchor):
    with pytest.raises(EntsogWindowError):
        EntsogWindowPolicy(lookback_gas_days=2).select(anchor)


def test_historical_window_remains_explicit_without_current_day_metadata():
    window = EntsogWindowPolicy("2020-01-01", "2020-01-02").select()
    assert not window.rolling and window.anchor_utc is None
    assert window.open_gas_day_label is None
    assert window.from_date == "2020-01-01" and window.to_date == "2020-01-02"
