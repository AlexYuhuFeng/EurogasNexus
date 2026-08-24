"""Freshness evaluation tests (audit item 3)."""

from datetime import UTC, datetime, timedelta

from eurogas_nexus.domain.monitoring.freshness import (
    FreshnessStatus,
    evaluate_freshness,
)

NOW = datetime(2026, 7, 1, 12, 0, tzinfo=UTC)


def test_fresh_within_expectation_is_live() -> None:
    observed = NOW - timedelta(minutes=5)
    assert (
        evaluate_freshness(10, observed, now_utc=NOW) is FreshnessStatus.LIVE
    )


def test_older_than_expectation_is_stale() -> None:
    observed = NOW - timedelta(minutes=30)
    assert (
        evaluate_freshness(10, observed, now_utc=NOW) is FreshnessStatus.STALE
    )


def test_boundary_exactly_at_expectation_is_live() -> None:
    observed = NOW - timedelta(minutes=10)
    assert (
        evaluate_freshness(10, observed, now_utc=NOW) is FreshnessStatus.LIVE
    )


def test_no_observation_is_unknown() -> None:
    assert evaluate_freshness(10, None, now_utc=NOW) is FreshnessStatus.UNKNOWN


def test_no_expectation_declared_is_unknown() -> None:
    observed = NOW - timedelta(minutes=5)
    assert (
        evaluate_freshness(0, observed, now_utc=NOW) is FreshnessStatus.UNKNOWN
    )


def test_future_observation_counts_as_live() -> None:
    observed = NOW + timedelta(minutes=3)
    assert (
        evaluate_freshness(10, observed, now_utc=NOW) is FreshnessStatus.LIVE
    )


def test_naive_timestamp_treated_as_utc() -> None:
    observed = datetime(2026, 7, 1, 11, 55)
    assert (
        evaluate_freshness(10, observed, now_utc=NOW) is FreshnessStatus.LIVE
    )
