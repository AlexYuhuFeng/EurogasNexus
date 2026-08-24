"""Production-shaped source operation controls (R33).

This module is the single policy owner for retry, backoff, and freshness-SLA
evaluation used by ingestion supervision. It performs no provider calls and no
database writes; connectors/scripts remain the only code that contacts a
source.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypeVar

from eurogas_nexus.domain.monitoring.freshness import (
    FreshnessStatus,
    evaluate_freshness,
)

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class SourceOperationPolicy:
    """Retry and freshness policy for one source family.

    Attributes:
        source_system: Source family name (e.g. ENTSOG, GIE, ECB).
        retry_max: Maximum retries after the first attempt.
        retry_backoff_seconds: Backoff for the first retry; doubles per retry.
        timeout_seconds: Upper bound for one attempt (advisory for subprocess
            or HTTP callers).
        freshness_sla_minutes: Maximum age for LIVE freshness evaluation.
    """

    source_system: str
    retry_max: int = 3
    retry_backoff_seconds: float = 30.0
    timeout_seconds: float = 120.0
    freshness_sla_minutes: int = 1440


@dataclass(frozen=True, slots=True)
class SourceOperationResult:
    """Outcome of one supervised source operation."""

    source_system: str
    succeeded: bool
    attempts: int
    last_error_type: str | None = None
    last_error_message: str = ""
    elapsed_seconds: float = 0.0


PUBLIC_SOURCE_POLICIES: tuple[SourceOperationPolicy, ...] = (
    SourceOperationPolicy(
        "ENTSOG", retry_max=3, retry_backoff_seconds=30, freshness_sla_minutes=60
    ),
    SourceOperationPolicy(
        "GIE", retry_max=3, retry_backoff_seconds=60, freshness_sla_minutes=360
    ),
    SourceOperationPolicy(
        "ECB", retry_max=3, retry_backoff_seconds=300, freshness_sla_minutes=1440
    ),
    SourceOperationPolicy(
        "NationalGasNTS",
        retry_max=2,
        retry_backoff_seconds=60,
        freshness_sla_minutes=43200,
    ),
    SourceOperationPolicy(
        "BBL", retry_max=2, retry_backoff_seconds=60, freshness_sla_minutes=43200
    ),
    SourceOperationPolicy(
        "IUK", retry_max=2, retry_backoff_seconds=60, freshness_sla_minutes=43200
    ),
    SourceOperationPolicy(
        "Weather", retry_max=3, retry_backoff_seconds=60, freshness_sla_minutes=360
    ),
)


def policy_for_source(source_system: str) -> SourceOperationPolicy:
    """Return the production policy for a source, or a safe default."""

    for policy in PUBLIC_SOURCE_POLICIES:
        if policy.source_system.casefold() == (source_system or "").strip().casefold():
            return policy
    return SourceOperationPolicy(source_system=(source_system or "").strip() or "UNKNOWN")


def run_with_retry(
    source_system: str,
    operation: Callable[[], T],
    *,
    is_success: Callable[[T], bool],
    policy: SourceOperationPolicy | None = None,
    sleeper: Callable[[float], None] | None = None,
    clock: Callable[[], datetime] | None = None,
) -> SourceOperationResult:
    """Run ``operation`` with bounded exponential retry.

    Args:
        source_system: Source family label for the result/diagnostics.
        operation: Zero-argument operation that contacts the source or its
            ingestion script.
        is_success: Predicate over the operation result; False schedules a
            retry.
        policy: Retry policy; defaults to ``policy_for_source``.
        sleeper: Injectable sleep; defaults to ``time.sleep``.
        clock: Injectable monotonic-ish clock; defaults to ``datetime.now``.

    Returns:
        SourceOperationResult with attempts and last error. Exceptions are
        captured and retried; the final exception is not re-raised so worker
        supervision continues.
    """

    resolved_policy = policy or policy_for_source(source_system)
    sleep = sleeper or _default_sleep
    now = clock or (lambda: datetime.now(UTC))
    started = now()
    last_error_type: str | None = None
    last_error_message = ""
    attempts = 0

    for attempt in range(resolved_policy.retry_max + 1):
        attempts += 1
        try:
            result = operation()
        except Exception as exc:
            last_error_type = exc.__class__.__name__
            last_error_message = str(exc)
        else:
            if is_success(result):
                return SourceOperationResult(
                    source_system=source_system,
                    succeeded=True,
                    attempts=attempts,
                    elapsed_seconds=(now() - started).total_seconds(),
                )
            last_error_type = "unsuccessful_result"
            last_error_message = "operation completed but reported failure"
        if attempt >= resolved_policy.retry_max:
            break
        delay = resolved_policy.retry_backoff_seconds * (2**attempt)
        sleep(delay)

    return SourceOperationResult(
        source_system=source_system,
        succeeded=False,
        attempts=attempts,
        last_error_type=last_error_type,
        last_error_message=last_error_message,
        elapsed_seconds=(now() - started).total_seconds(),
    )


def evaluate_source_sla(
    source_system: str,
    last_success_at_utc: datetime | None,
    *,
    now_utc: datetime | None = None,
) -> FreshnessStatus:
    """Evaluate freshness SLA for a source family.

    Sources without a declared policy return UNKNOWN; no observation returns
    UNKNOWN; an observation older than the declared SLA returns STALE.
    """

    policy = policy_for_source(source_system)
    return evaluate_freshness(
        policy.freshness_sla_minutes,
        last_success_at_utc,
        now_utc=now_utc,
    )


def _default_sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)
