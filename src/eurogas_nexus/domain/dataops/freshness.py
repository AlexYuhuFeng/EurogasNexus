"""Backend-owned freshness SLA evaluation for CR-09.

Freshness is never inferred by the frontend. This module decides
FRESH/LATE/STALE/MISSING/NOT_EXPECTED/UNKNOWN/RESTRICTED from the typed
source definition, calendar expectation and timestamp evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from eurogas_nexus.domain.dataops.contracts import (
    FreshnessEvaluation,
    FreshnessState,
    SourceDefinition,
    as_utc,
)
from eurogas_nexus.domain.dataops.schedule import update_expected


@dataclass(frozen=True, slots=True)
class FreshnessEvidence:
    """Timestamps and access state needed for one freshness decision."""

    observed_at_utc: datetime | None = None
    available_at_utc: datetime | None = None
    ingested_at_utc: datetime | None = None
    last_success_at_utc: datetime | None = None
    last_attempt_at_utc: datetime | None = None
    access_granted: bool = True


def evaluate_source_freshness(
    definition: SourceDefinition,
    evidence: FreshnessEvidence,
    *,
    now_utc: datetime | None = None,
) -> FreshnessEvaluation:
    """Evaluate one source against its backend-owned freshness policy."""

    now = as_utc(now_utc or datetime.now(UTC))
    policy = definition.freshness_policy
    reason_parts: list[str] = []

    if definition.calendar is not None and not update_expected(
        definition, now_utc=now
    ):
        return FreshnessEvaluation(
            source_id=definition.source_id,
            state=FreshnessState.NOT_EXPECTED,
            reason="calendar_closed:no_update_expected",
            evaluated_at_utc=now.isoformat(),
        )

    if not evidence.access_granted:
        return FreshnessEvaluation(
            source_id=definition.source_id,
            state=FreshnessState.RESTRICTED,
            reason="access_restricted:credential_or_certification_missing",
            evaluated_at_utc=now.isoformat(),
        )

    observed = evidence.observed_at_utc or evidence.available_at_utc
    if observed is None:
        if evidence.last_success_at_utc is None:
            return FreshnessEvaluation(
                source_id=definition.source_id,
                state=FreshnessState.MISSING,
                reason="missing:no_successful_observation",
                evaluated_at_utc=now.isoformat(),
            )
        observed = evidence.last_success_at_utc

    observed_utc = as_utc(observed)
    age_seconds = max(0.0, (now - observed_utc).total_seconds())
    age_minutes = age_seconds / 60.0

    normal = int(policy.normal_max_age_minutes)
    stale = int(policy.stale_after_minutes)
    if normal <= 0:
        return FreshnessEvaluation(
            source_id=definition.source_id,
            state=FreshnessState.UNKNOWN,
            source_age_seconds=age_seconds,
            threshold_minutes=None,
            reason="unknown:no_freshness_threshold_declared",
            evaluated_at_utc=now.isoformat(),
        )

    if age_minutes <= normal:
        return FreshnessEvaluation(
            source_id=definition.source_id,
            state=FreshnessState.FRESH,
            source_age_seconds=age_seconds,
            threshold_minutes=normal,
            reason="within_normal_max_age",
            evaluated_at_utc=now.isoformat(),
        )
    if age_minutes <= stale:
        reason_parts.append("late_between_normal_and_stale_thresholds")
        return FreshnessEvaluation(
            source_id=definition.source_id,
            state=FreshnessState.LATE,
            source_age_seconds=age_seconds,
            threshold_minutes=stale,
            reason=";".join(reason_parts),
            evaluated_at_utc=now.isoformat(),
        )

    return FreshnessEvaluation(
        source_id=definition.source_id,
        state=FreshnessState.STALE,
        source_age_seconds=age_seconds,
        threshold_minutes=stale,
        reason="stale:older_than_stale_threshold",
        evaluated_at_utc=now.isoformat(),
    )


def source_age_seconds(
    observed_at_utc: datetime | None,
    *,
    now_utc: datetime | None = None,
) -> float | None:
    """Provider observation age (now - observed/publication)."""

    if observed_at_utc is None:
        return None
    now = as_utc(now_utc or datetime.now(UTC))
    return round(max(0.0, (now - as_utc(observed_at_utc)).total_seconds()), 3)


def ingestion_lag_seconds(
    available_at_utc: datetime | None,
    persisted_at_utc: datetime | None,
) -> float | None:
    """Provider availability to first persistence lag."""

    if available_at_utc is None or persisted_at_utc is None:
        return None
    return round(max(0.0, (as_utc(persisted_at_utc) - as_utc(available_at_utc)).total_seconds()), 3)


def pipeline_lag_seconds(
    started_at_utc: datetime | None,
    completed_at_utc: datetime | None,
) -> float | None:
    """Run duration (persisted ingestion start to completion)."""

    if started_at_utc is None or completed_at_utc is None:
        return None
    return round(max(0.0, (as_utc(completed_at_utc) - as_utc(started_at_utc)).total_seconds()), 3)
