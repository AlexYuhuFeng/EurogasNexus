"""Data-operations application runtime.

This service owns scheduler scanning, run claiming, failure-category-aware
retry execution, operator run requests and runtime health aggregation. It
performs no provider calls itself: the caller injects the runner (the
production runner wraps the existing public-source ingestor subprocess).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from eurogas_nexus.db.models import (
    DataOperationsHeartbeatRecord,
    IngestionRunRecord,
    SourceRuntimeStateRecord,
)
from eurogas_nexus.db.repositories import dataops as dataops_repository
from eurogas_nexus.domain.dataops.contracts import (
    CircuitState,
    FailureCategory,
    FailureClassification,
    IngestionRunStatus,
    IngestionTriggerType,
    QualityIssue,
    QualityResult,
    SourceDefinition,
    as_utc,
)
from eurogas_nexus.domain.dataops.freshness import FreshnessEvidence, evaluate_source_freshness
from eurogas_nexus.domain.dataops.registry import source_definitions
from eurogas_nexus.domain.dataops.retry import classify_failure, retry_decision
from eurogas_nexus.domain.dataops.schedule import next_scheduled_instant

RunAttempt = Callable[[dict[str, Any], int], "IngestionAttemptResult"]


@dataclass(frozen=True, slots=True)
class IngestionAttemptResult:
    """One adapter/ingestor attempt result."""

    succeeded: bool
    classification: FailureCategory | None = None
    error_message: str = ""
    rows_received: int = 0
    rows_accepted: int = 0
    rows_rejected: int = 0
    rows_inserted: int = 0
    rows_updated: int = 0
    duplicate_count: int = 0
    fallback_used: bool = False
    lineage_refs: list[str] = field(default_factory=list)
    quality_issues: list[QualityIssue] = field(default_factory=list)
    retry_after_seconds: float | None = None


def successful_attempt(**counts: Any) -> IngestionAttemptResult:
    """Build a successful attempt with row counters."""

    return IngestionAttemptResult(succeeded=True, **counts)


def scan_scheduler(
    session: Session,
    *,
    now_utc: datetime | None = None,
    limit: int = 10,
    definitions: tuple[SourceDefinition, ...] | None = None,
    stale_after_seconds: int = 900,
) -> dict:
    """Reconcile state, recover stale runs, claim due scheduled runs."""

    now = as_utc(now_utc or datetime.now(UTC))
    resolved = definitions or source_definitions()
    dataops_repository.reconcile_source_runtime_states(session, resolved, now_utc=now)
    recovered = dataops_repository.recover_stale_runs(session, now_utc=now)
    claims = dataops_repository.claim_due_sources(
        session, resolved, now_utc=now, limit=limit
    )
    states = _ordered_states(session)
    health = _aggregate_health(session, states, now)
    heartbeat = dataops_repository.record_heartbeat(
        session,
        now_utc=now,
        sources_scheduled=sum(1 for state in states if state.enabled),
        sources_healthy=health["healthy"],
        sources_late=health["late"],
        sources_stale=health["stale"],
        sources_failed=health["failed"],
        certification_gaps=health["certification_gaps"],
        entitlement_failures=health["entitlement_failures"],
        backlog_depth=health["backlog_depth"],
        oldest_overdue_seconds=health["oldest_overdue_seconds"],
        due_count=health["due_count"],
        claimed_count=len(claims),
        run_count=_active_run_count(session, now),
    )
    session.flush()
    return {
        "scan_at_utc": now.isoformat(),
        "recovered_stale_runs": recovered,
        "claimed_runs": [run.run_id for _, run in claims],
        "heartbeat": dataops_repository.heartbeat_payload(heartbeat),
        "health": health,
    }


def execute_claimed_runs(
    session: Session,
    *,
    runner: RunAttempt,
    now_utc: datetime | None = None,
    limit: int = 10,
    definitions: tuple[SourceDefinition, ...] | None = None,
    sleeper: Callable[[float], None] | None = None,
) -> dict:
    """Execute QUEUED runs with failure-category-aware retry."""

    now = as_utc(now_utc or datetime.now(UTC))
    resolved = definitions or source_definitions()
    definitions_by_id = {definition.source_id: definition for definition in resolved}
    runs = dataops_repository.claim_queued_runs(session, now_utc=now, limit=limit)
    sleep = sleeper or _default_sleep
    outcomes: list[dict[str, Any]] = []
    for run in runs:
        definition = definitions_by_id.get(run.source_id)
        if definition is None:
            run.status = IngestionRunStatus.FAILED.value
            run.error_category = FailureCategory.CONFIGURATION.value
            run.error_code = "UNKNOWN_SOURCE_DEFINITION"
            run.completed_at_utc = now
            outcomes.append({"run_id": run.run_id, "status": run.status})
            continue
        outcomes.append(
            _execute_one(
                session,
                run=run,
                definition=definition,
                runner=runner,
                now_utc=now,
                sleeper=sleep,
            )
        )
    session.flush()
    return {
        "executed_at_utc": now.isoformat(),
        "claimed_count": len(runs),
        "outcomes": outcomes,
    }


def _execute_one(
    session: Session,
    *,
    run: IngestionRunRecord,
    definition: SourceDefinition,
    runner: RunAttempt,
    now_utc: datetime,
    sleeper: Callable[[float], None],
) -> dict:
    policy = definition.retry_policy
    payload = dataops_repository.ingestion_run_payload(run)
    last_attempt: IngestionAttemptResult | None = None
    classification: FailureClassification | None = None
    attempts = 0
    for attempt in range(max(0, policy.retry_max) + 1):
        attempts += 1
        run.attempt_number = attempts
        try:
            result = runner(payload, attempts)
        except Exception as exc:
            result = IngestionAttemptResult(
                succeeded=False,
                classification=classify_failure(error=exc).category,
                error_message=str(exc),
            )
        last_attempt = result
        if result.succeeded:
            classification = None
            break
        classification = (
            classify_failure(
                error=None,
                message=f"{result.classification.value} {result.error_message}",
            )
            if result.classification is not None
            else classify_failure(error=None, message=result.error_message)
        )
        decision = retry_decision(
            classification,
            attempt=attempt,
            policy=policy,
            retry_after_seconds=result.retry_after_seconds,
        )
        if not decision.retry:
            break
        sleeper(decision.delay_seconds)

    success = bool(last_attempt and last_attempt.succeeded)
    issues = tuple(last_attempt.quality_issues) if last_attempt else ()
    warning_count = sum(issue.severity.value == "WARNING" for issue in issues)
    error_count = sum(issue.severity.value == "ERROR" for issue in issues)
    quality_result = (
        QualityResult.FAILED
        if error_count
        else QualityResult.PASSED_WITH_WARNINGS
        if warning_count
        else QualityResult.PASSED
    )
    dataops_repository.finalize_run(
        session,
        run,
        definition,
        classification=classification,
        quality_result=quality_result,
        quality_warning_count=warning_count,
        quality_error_count=error_count,
        rows_received=last_attempt.rows_received if last_attempt else 0,
        rows_accepted=last_attempt.rows_accepted if last_attempt else 0,
        rows_rejected=last_attempt.rows_rejected if last_attempt else 0,
        rows_inserted=last_attempt.rows_inserted if last_attempt else 0,
        rows_updated=last_attempt.rows_updated if last_attempt else 0,
        duplicate_count=last_attempt.duplicate_count if last_attempt else 0,
        fallback_used=last_attempt.fallback_used if last_attempt else False,
        lineage_refs=last_attempt.lineage_refs if last_attempt else None,
        now_utc=now_utc,
        succeeded=success,
    )
    if issues:
        dataops_repository.record_quality_issues(session, run.run_id, issues, now_utc=now_utc)
    return {
        "run_id": run.run_id,
        "source_id": run.source_id,
        "status": run.status,
        "attempts": attempts,
        "error_category": run.error_category,
    }


def request_operator_run(
    session: Session,
    *,
    source_id: str,
    trigger_type: IngestionTriggerType,
    now_utc: datetime | None = None,
    window_start_utc: datetime | None = None,
    window_end_utc: datetime | None = None,
    reason: str = "",
    retry_of_run_id: str | None = None,
) -> dict:
    """Create an operator-requested ingestion run (never executes it)."""

    now = as_utc(now_utc or datetime.now(UTC))
    definition = next(
        (item for item in source_definitions() if item.source_id == source_id),
        None,
    )
    if definition is None:
        raise ValueError(f"Unknown source: {source_id}")
    run = dataops_repository.create_operator_run(
        session,
        definition,
        trigger_type=trigger_type,
        now_utc=now,
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        reason=reason,
        retry_of_run_id=retry_of_run_id,
    )
    return dataops_repository.ingestion_run_payload(run)


def set_source_enabled(
    session: Session,
    *,
    source_id: str,
    enabled: bool,
    now_utc: datetime | None = None,
    definitions: tuple[SourceDefinition, ...] | None = None,
) -> dict:
    """Enable or disable a source's scheduler participation (audited by API)."""

    now = as_utc(now_utc or datetime.now(UTC))
    resolved = definitions or source_definitions()
    definition = next(
        (item for item in resolved if item.source_id == source_id),
        None,
    )
    if definition is None:
        raise ValueError(f"Unknown source: {source_id}")
    state = dataops_repository.ensure_source_runtime_state(
        session, definition, now_utc=now, activate_new=False
    )
    state.enabled = bool(enabled)
    if enabled and state.next_run_at_utc is None:
        state.activated_at_utc = state.activated_at_utc or now
        state.next_run_at_utc = next_scheduled_instant(
            definition, activated_at=state.activated_at_utc, after=now
        )
    if not enabled:
        state.circuit_state = CircuitState.DISABLED.value
        state.next_run_at_utc = None
    else:
        state.circuit_state = CircuitState.HEALTHY.value
        state.consecutive_failures = 0
    state.updated_at_utc = now
    session.flush()
    return dataops_repository.source_runtime_payload(state)


def runtime_source_operations(
    session: Session,
    *,
    now_utc: datetime | None = None,
    definitions: tuple[SourceDefinition, ...] | None = None,
) -> dict:
    """Aggregate data-operations health for runtime/source-center surfaces."""

    now = as_utc(now_utc or datetime.now(UTC))
    resolved = definitions or source_definitions()
    dataops_repository.reconcile_source_runtime_states(session, resolved, now_utc=now)
    states = _ordered_states(session)
    heartbeat = session.get(DataOperationsHeartbeatRecord, "primary")
    health = _aggregate_health(session, states, now)
    return {
        "generated_at_utc": now.isoformat(),
        "heartbeat": dataops_repository.heartbeat_payload(heartbeat),
        "sources": [dataops_repository.source_runtime_payload(state) for state in states],
        "totals": {
            "registered_sources": len(resolved),
            "sources_scheduled": sum(1 for state in states if state.enabled),
            "sources_healthy": health["healthy"],
            "sources_late": health["late"],
            "sources_stale": health["stale"],
            "sources_failed": health["failed"],
            "certification_gaps": health["certification_gaps"],
            "entitlement_failures": health["entitlement_failures"],
            "backlog_depth": health["backlog_depth"],
            "oldest_overdue_seconds": health["oldest_overdue_seconds"],
        },
    }


def source_health(
    session: Session,
    *,
    source_id: str,
    now_utc: datetime | None = None,
) -> dict | None:
    """Return one source's operational health payload."""

    now = as_utc(now_utc or datetime.now(UTC))
    definition = next(
        (item for item in source_definitions() if item.source_id == source_id),
        None,
    )
    if definition is None:
        return None
    state = dataops_repository.ensure_source_runtime_state(
        session, definition, now_utc=now, activate_new=True
    )
    observed = _latest_observation_for(session, definition.provider)
    access_granted = bool(state.enabled)
    if definition.certification_required and state.certification_state not in {
        "CERTIFIED",
        "NOT_REQUIRED",
        "SIMULATION_MATCHED",
        "live_validated",
    }:
        access_granted = False
    evaluation = evaluate_source_freshness(
        definition,
        FreshnessEvidence(
            observed_at_utc=observed,
            available_at_utc=None,
            ingested_at_utc=state.last_success_at_utc,
            last_success_at_utc=state.last_success_at_utc,
            last_attempt_at_utc=state.last_attempt_at_utc,
            access_granted=access_granted,
        ),
        now_utc=now,
    )
    payload = dataops_repository.source_runtime_payload(state)
    payload.update(
        {
            "freshness_state": evaluation.state.value,
            "source_age_seconds": evaluation.source_age_seconds,
            "last_observed_at_utc": _iso(observed),
            "definition": {
                "source_class": definition.source_class.value,
                "datasets": list(definition.datasets),
                "freshness_policy": asdict(definition.freshness_policy),
            },
        }
    )
    return payload


def _ordered_states(session: Session) -> list[SourceRuntimeStateRecord]:
    return (
        session.query(SourceRuntimeStateRecord)
        .order_by(SourceRuntimeStateRecord.source_id)
        .all()
    )


def _aggregate_health(
    session: Session,
    states: list[SourceRuntimeStateRecord],
    now: datetime,
) -> dict:
    healthy = sum(
        1 for state in states if state.freshness_state in {"FRESH", "NOT_EXPECTED"}
    )
    late = sum(1 for state in states if state.freshness_state == "LATE")
    stale = sum(
        1 for state in states if state.freshness_state in {"STALE", "MISSING"}
    )
    failed = sum(
        1
        for state in states
        if state.last_error_category is not None
        and state.circuit_state in {"DEGRADED", "OPEN_CIRCUIT"}
    )
    certification_gaps = sum(
        1
        for state in states
        if state.certification_state not in {"CERTIFIED", "NOT_REQUIRED"}
        and state.certification_state not in {"live_validated", "SIMULATION_MATCHED"}
    )
    overdue_states = [
        state
        for state in states
        if state.enabled
        and state.next_run_at_utc is not None
        and as_utc(state.next_run_at_utc) <= now
    ]
    backlog_depth = len(overdue_states)
    oldest_overdue_seconds = (
        round(
            max(
                0.0,
                (
                    now
                    - min(
                        as_utc(state.next_run_at_utc)
                        for state in overdue_states
                    )
                ).total_seconds(),
            ),
            1,
        )
        if overdue_states
        else None
    )
    return {
        "healthy": healthy,
        "late": late,
        "stale": stale,
        "failed": failed,
        "certification_gaps": certification_gaps,
        "entitlement_failures": sum(
            1
            for state in states
            if state.entitlement_state in {"DENIED", "MISSING"}
        ),
        "backlog_depth": backlog_depth,
        "oldest_overdue_seconds": oldest_overdue_seconds,
        "due_count": backlog_depth,
    }


def _active_run_count(session: Session, now: datetime) -> int:
    cutoff = now - timedelta(hours=24)
    return (
        session.query(IngestionRunRecord)
        .filter(IngestionRunRecord.started_at_utc >= cutoff)
        .count()
    )


def _latest_observation_for(session: Session, provider: str) -> datetime | None:
    from sqlalchemy import func

    from eurogas_nexus.db.models import (
        CapacityObservationRecord,
        FlowObservationRecord,
        FxObservationRecord,
        LngObservationRecord,
        MarketObservationRecord,
        ScreenOrderObservationRecord,
        StorageObservationRecord,
    )

    tables = (
        (
            MarketObservationRecord,
            MarketObservationRecord.source_system,
            MarketObservationRecord.observed_at_utc,
        ),
        (
            FxObservationRecord,
            FxObservationRecord.source_system,
            FxObservationRecord.observed_at_utc,
        ),
        (
            FlowObservationRecord,
            FlowObservationRecord.source_system,
            FlowObservationRecord.observed_at_utc,
        ),
        (
            CapacityObservationRecord,
            CapacityObservationRecord.source_system,
            CapacityObservationRecord.observed_at_utc,
        ),
        (
            StorageObservationRecord,
            StorageObservationRecord.source_system,
            StorageObservationRecord.observed_at_utc,
        ),
        (
            LngObservationRecord,
            LngObservationRecord.source_system,
            LngObservationRecord.observed_at_utc,
        ),
        (
            ScreenOrderObservationRecord,
            ScreenOrderObservationRecord.source_system,
            ScreenOrderObservationRecord.observed_at_utc,
        ),
    )
    latest: datetime | None = None
    for _model, source_column, time_column in tables:
        value = (
            session.query(func.max(time_column))
            .filter(source_column == provider)
            .scalar()
        )
        if value is None:
            continue
        value_utc = as_utc(value)
        if latest is None or value_utc > latest:
            latest = value_utc
    return latest


def _default_sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return as_utc(value).isoformat()
