"""Failure-category-aware retry, backoff and circuit policy.

Retry decisions are made **before** a retry: authentication, entitlement,
schema and configuration failures are terminal. Transient network, rate-limit
and provider-unavailable failures use bounded exponential backoff with full
jitter and honor provider rate-limit policy.
"""

from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta

from eurogas_nexus.domain.dataops.contracts import (
    CircuitPolicy,
    CircuitState,
    FailureCategory,
    FailureClassification,
    RetryDecision,
    RetryPolicy,
    as_utc,
)

_TRANSIENT_ERROR_NAMES = {
    "timeouterror",
    "connectionerror",
    "connecttimeout",
    "readtimeout",
    "remotedisconnected",
    "proxyerror",
}


def classify_failure(
    *,
    error: BaseException | None = None,
    status_code: int | None = None,
    message: str = "",
) -> FailureClassification:
    """Classify one ingestion failure into its stable category."""

    error_text = str(error) if error else ""
    text = f"{message} {error.__class__.__name__ if error else ''} {error_text}".lower()
    if any(token in text for token in ("credential", "unauthorized", "forbidden", "401", "403")):
        return FailureClassification(
            FailureCategory.AUTHENTICATION,
            retryable=False,
            code="authentication_failed",
            message="Credential or authorization failure is terminal.",
        )
    if "entitlement" in text or "license" in text or "subscription" in text:
        return FailureClassification(
            FailureCategory.ENTITLEMENT,
            retryable=False,
            code="entitlement_failed",
            message="Entitlement failure is terminal.",
        )
    if "schema" in text or "validation error" in text or "unknown field" in text:
        return FailureClassification(
            FailureCategory.SCHEMA_CHANGED,
            retryable=False,
            code="schema_changed",
            message="Provider schema changed; operator review required.",
        )
    if "quality" in text and "rejected" in text:
        return FailureClassification(
            FailureCategory.QUALITY_REJECTED,
            retryable=False,
            code="quality_rejected",
            message="Data quality rejection is terminal until corrected.",
        )
    if "configuration" in text or "misconfigured" in text:
        return FailureClassification(
            FailureCategory.CONFIGURATION,
            retryable=False,
            code="configuration_error",
            message="Configuration failure is terminal.",
        )

    if status_code in {401, 403}:
        return FailureClassification(
            FailureCategory.AUTHENTICATION,
            retryable=False,
            code=f"http_{status_code}",
            message="Credential or authorization failure is terminal.",
        )
    if status_code == 429:
        return FailureClassification(
            FailureCategory.RATE_LIMITED,
            retryable=True,
            code="rate_limited",
            message="Provider rate limit reached.",
        )
    if status_code in {500, 502, 503, 504}:
        return FailureClassification(
            FailureCategory.PROVIDER_UNAVAILABLE,
            retryable=True,
            code=f"http_{status_code}",
            message="Provider is temporarily unavailable.",
        )
    if status_code is not None and status_code >= 400:
        return FailureClassification(
            FailureCategory.BAD_RESPONSE,
            retryable=True,
            code=f"http_{status_code}",
            message="Provider returned an unsuccessful response.",
        )

    error_name = (error.__class__.__name__ if error else "").lower()
    if error_name in _TRANSIENT_ERROR_NAMES:
        return FailureClassification(
            FailureCategory.NETWORK_TRANSIENT,
            retryable=True,
            code=error_name,
            message="Transient network failure.",
        )
    if "timed out" in text or "timeout" in text or "connection" in text:
        return FailureClassification(
            FailureCategory.NETWORK_TRANSIENT,
            retryable=True,
            code="network_transient",
            message="Transient network failure.",
        )
    if error is not None:
        return FailureClassification(
            FailureCategory.INTERNAL,
            retryable=True,
            code=error_name or "internal_error",
            message="Unclassified adapter failure; bounded retry applies.",
        )
    return FailureClassification(
        FailureCategory.INTERNAL,
        retryable=True,
        code="internal_error",
        message="Unclassified ingestion failure; bounded retry applies.",
    )


def retry_decision(
    classification: FailureClassification,
    *,
    attempt: int,
    policy: RetryPolicy,
    retry_after_seconds: float | None = None,
    rng: random.Random | None = None,
) -> RetryDecision:
    """Return whether to retry and the delay before the next attempt."""

    if not classification.retryable:
        return RetryDecision(
            retry=False,
            category=classification.category,
            reason=f"{classification.category.value}:terminal",
        )
    if attempt >= max(0, policy.retry_max):
        return RetryDecision(
            retry=False,
            category=classification.category,
            reason="retry_max_exhausted",
        )
    if classification.category == FailureCategory.RATE_LIMITED and retry_after_seconds is not None:
        delay = max(0.0, float(retry_after_seconds))
    else:
        delay = float(policy.backoff_seconds) * (2.0 ** max(0, attempt))
        delay = min(delay, float(policy.max_delay_seconds))
        if policy.jitter:
            generator = rng or random.Random()
            delay = generator.uniform(delay / 2.0, delay)
    return RetryDecision(
        retry=True,
        category=classification.category,
        delay_seconds=round(max(0.0, delay), 3),
        reason="retryable_failure",
    )


def circuit_after_failure(
    state: CircuitState,
    consecutive_failures: int,
    *,
    policy: CircuitPolicy,
) -> tuple[CircuitState, int]:
    """Return the next circuit state after one classified failure."""

    failures = max(0, consecutive_failures) + 1
    if state == CircuitState.DISABLED:
        return CircuitState.DISABLED, failures
    if failures >= max(1, policy.open_after_failures):
        return CircuitState.OPEN_CIRCUIT, failures
    if failures >= max(1, policy.degraded_after_failures):
        return CircuitState.DEGRADED, failures
    return CircuitState.HEALTHY, failures


def circuit_after_success(state: CircuitState) -> tuple[CircuitState, int]:
    """A successful run resets the failure counter and restores HEALTHY."""

    if state == CircuitState.DISABLED:
        return CircuitState.DISABLED, 0
    return CircuitState.HEALTHY, 0


def recovery_probe_due(
    *,
    state: CircuitState,
    opened_at_utc: datetime | None,
    now_utc: datetime | None = None,
    policy: CircuitPolicy | None = None,
) -> bool:
    """Return whether an OPEN_CIRCUIT source is due a recovery probe."""

    if state != CircuitState.OPEN_CIRCUIT:
        return False
    if opened_at_utc is None:
        return True
    probe_seconds = int(policy.recovery_probe_after_seconds if policy else 900)
    now = as_utc(now_utc or datetime.now(UTC))
    return as_utc(opened_at_utc) + timedelta(seconds=probe_seconds) <= now


def retry_delay_seconds(
    classification: FailureClassification,
    *,
    attempt: int,
    policy: RetryPolicy,
) -> float:
    """Compatibility wrapper returning the deterministic delay part only."""

    return retry_decision(
        classification,
        attempt=attempt,
        policy=policy,
        rng=random.Random(0),
    ).delay_seconds
