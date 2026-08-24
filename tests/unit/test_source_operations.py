"""R33 source-operation policy tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from eurogas_nexus.application.source_operations import (
    SourceOperationPolicy,
    evaluate_source_sla,
    policy_for_source,
    run_with_retry,
)
from eurogas_nexus.domain.monitoring.freshness import FreshnessStatus


def test_retry_succeeds_after_transient_failure() -> None:
    calls: list[int] = []

    def operation() -> bool:
        calls.append(1)
        return len(calls) >= 2

    result = run_with_retry(
        "ENTSOG",
        operation,
        is_success=lambda value: value is True,
        sleeper=lambda seconds: None,
    )

    assert result.succeeded is True
    assert result.attempts == 2


def test_retry_stops_at_bounded_maximum() -> None:
    calls: list[int] = []

    def operation() -> bool:
        calls.append(1)
        return False

    result = run_with_retry(
        "ENTSOG",
        operation,
        is_success=lambda value: value is True,
        policy=SourceOperationPolicy("ENTSOG", retry_max=2),
        sleeper=lambda seconds: None,
    )

    assert result.succeeded is False
    assert result.attempts == 3
    assert result.last_error_type == "unsuccessful_result"


def test_backoff_uses_injected_sleep_sequence() -> None:
    slept: list[float] = []
    attempts: list[int] = []

    def operation() -> bool:
        attempts.append(1)
        return False

    run_with_retry(
        "ENTSOG",
        operation,
        is_success=lambda value: value is True,
        policy=SourceOperationPolicy(
            "ENTSOG", retry_max=3, retry_backoff_seconds=5.0
        ),
        sleeper=slept.append,
    )

    assert slept == [5.0, 10.0, 20.0]


def test_exception_is_captured_without_terminating_supervision() -> None:
    def operation() -> bool:
        raise TimeoutError("provider timeout")

    result = run_with_retry(
        "ENTSOG",
        operation,
        is_success=lambda value: value is True,
        sleeper=lambda seconds: None,
    )

    assert result.succeeded is False
    assert result.last_error_type == "TimeoutError"
    assert "provider timeout" in result.last_error_message


def test_policy_lookup_returns_default_for_unknown_source() -> None:
    known = policy_for_source("entsog")
    assert known.source_system == "ENTSOG"
    assert known.freshness_sla_minutes == 60

    unknown = policy_for_source("UnknownVendor")
    assert unknown.source_system == "UnknownVendor"
    assert unknown.retry_max == 3


def test_source_sla_evaluation_uses_declared_policy() -> None:
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    assert (
        evaluate_source_sla("ENTSOG", now - timedelta(minutes=10), now_utc=now)
        is FreshnessStatus.LIVE
    )
    assert (
        evaluate_source_sla("ENTSOG", now - timedelta(minutes=90), now_utc=now)
        is FreshnessStatus.STALE
    )
    assert evaluate_source_sla("ENTSOG", None, now_utc=now) is FreshnessStatus.UNKNOWN
