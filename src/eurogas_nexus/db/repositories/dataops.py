"""Data-operations persistence repository.

All scheduler truth is PostgreSQL-backed. The repository owns reconcile,
due-run claiming, queued-run claiming, run finalization, issue persistence and
heartbeat. It never contacts a provider.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from eurogas_nexus.db.models import (
    DataOperationsHeartbeatRecord,
    IngestionRunIssueRecord,
    IngestionRunRecord,
    SourceRuntimeStateRecord,
)
from eurogas_nexus.domain.dataops.contracts import (
    CircuitState,
    FailureClassification,
    FreshnessState,
    IngestionRunStatus,
    IngestionTriggerType,
    QualityIssue,
    QualityResult,
    SourceDefinition,
    as_utc,
)
from eurogas_nexus.domain.dataops.freshness import FreshnessEvidence, evaluate_source_freshness
from eurogas_nexus.domain.dataops.retry import (
    circuit_after_failure,
    circuit_after_success,
    recovery_probe_due,
)
from eurogas_nexus.domain.dataops.schedule import (
    next_scheduled_instant,
    validate_schedule,
)

STALE_RUN_SECONDS = 900
MAX_CLAIM_LIMIT = 100


def _now(value: datetime | None = None) -> datetime:
    return as_utc(value or datetime.now(UTC))


def _schedule_json(definition: SourceDefinition) -> dict:
    spec = definition.schedule
    return {
        "schedule_type": spec.schedule_type.value,
        "interval_seconds": spec.interval_seconds,
        "daily_at": spec.daily_at,
        "timezone": spec.timezone,
        "market_relative_offset_seconds": spec.market_relative_offset_seconds,
        "missed_policy": spec.missed_policy,
    }


def _policy_json(definition: SourceDefinition) -> dict:
    policy = definition.freshness_policy
    retry = definition.retry_policy
    rate = definition.rate_limit_policy
    circuit = definition.circuit_policy
    return {
        "normal_max_age_minutes": policy.normal_max_age_minutes,
        "late_after_minutes": policy.late_after_minutes,
        "stale_after_minutes": policy.stale_after_minutes,
        "basis": policy.basis,
        "retry_max": retry.retry_max,
        "backoff_seconds": retry.backoff_seconds,
        "max_delay_seconds": retry.max_delay_seconds,
        "rate_limit": {
            "max_requests_per_interval": rate.max_requests_per_interval,
            "interval_seconds": rate.interval_seconds,
            "min_spacing_seconds": rate.min_spacing_seconds,
            "max_concurrency": rate.max_concurrency,
        },
        "circuit": {
            "degraded_after_failures": circuit.degraded_after_failures,
            "open_after_failures": circuit.open_after_failures,
            "recovery_probe_after_seconds": circuit.recovery_probe_after_seconds,
        },
    }


def ensure_source_runtime_state(
    session: Session,
    definition: SourceDefinition,
    *,
    now_utc: datetime | None = None,
    activate_new: bool = True,
) -> SourceRuntimeStateRecord:
    """Upsert runtime state for one typed definition without resetting state."""

    now = _now(now_utc)
    validate_schedule(definition)
    row = session.get(SourceRuntimeStateRecord, definition.source_id)
    if row is None:
        row = SourceRuntimeStateRecord(
            source_id=definition.source_id,
            provider=definition.provider,
            dataset=definition.dataset,
            source_class=definition.source_class.value,
            enabled=bool(definition.enabled_default and activate_new),
            circuit_state=CircuitState.HEALTHY.value,
            consecutive_failures=0,
            consecutive_successes=0,
            last_attempt_at_utc=None,
            last_success_at_utc=None,
            last_failure_at_utc=None,
            last_error_category=None,
            last_error_code=None,
            last_error_message=None,
            activated_at_utc=now if activate_new and definition.enabled_default else None,
            next_run_at_utc=(
                next_scheduled_instant(definition, activated_at=now, after=now)
                if activate_new and definition.enabled_default
                else None
            ),
            recovery_probe_at_utc=None,
            freshness_state=FreshnessState.UNKNOWN.value,
            source_age_seconds=None,
            ingestion_lag_seconds=None,
            pipeline_lag_seconds=None,
            last_quality_result=QualityResult.PASSED.value,
            quality_warning_count=0,
            quality_error_count=0,
            last_quality_issue_count=0,
            entitlement_state="UNKNOWN",
            certification_state=(
                "NOT_IMPLEMENTED" if definition.certification_required else "NOT_REQUIRED"
            ),
            adapter_version=definition.adapter_version,
            schedule_json=_schedule_json(definition),
            freshness_policy_json=asdict(definition.freshness_policy),
            retry_policy_json=asdict(definition.retry_policy),
            rate_limit_policy_json=asdict(definition.rate_limit_policy),
            circuit_policy_json=asdict(definition.circuit_policy),
            calendar=definition.calendar.value,
            updated_at_utc=now,
            research_only=True,
        )
        session.add(row)
        return row

    row.provider = definition.provider
    row.dataset = definition.dataset
    row.source_class = definition.source_class.value
    row.adapter_version = definition.adapter_version
    row.schedule_json = _schedule_json(definition)
    row.freshness_policy_json = asdict(definition.freshness_policy)
    row.retry_policy_json = asdict(definition.retry_policy)
    row.rate_limit_policy_json = asdict(definition.rate_limit_policy)
    row.circuit_policy_json = asdict(definition.circuit_policy)
    row.calendar = definition.calendar.value
    row.updated_at_utc = now
    if row.enabled and row.next_run_at_utc is None:
        row.activated_at_utc = row.activated_at_utc or now
        row.next_run_at_utc = next_scheduled_instant(
            definition, activated_at=row.activated_at_utc, after=now
        )
    return row


def reconcile_source_runtime_states(
    session: Session,
    definitions: tuple[SourceDefinition, ...],
    *,
    now_utc: datetime | None = None,
) -> int:
    """Reconcile all registered definitions into runtime state rows."""

    for definition in definitions:
        ensure_source_runtime_state(session, definition, now_utc=now_utc)
    session.flush()
    return len(definitions)


def claim_due_sources(
    session: Session,
    definitions: tuple[SourceDefinition, ...],
    *,
    now_utc: datetime | None = None,
    limit: int = 10,
) -> list[tuple[SourceRuntimeStateRecord, IngestionRunRecord]]:
    """Claim due sources and create QUEUED scheduled runs, restart-safe.

    PostgreSQL uses SELECT ... FOR UPDATE SKIP LOCKED so concurrent scheduler
    processes claim disjoint rows. The partial unique index on
    ``(source_id, scheduled_for_utc) WHERE trigger_type='SCHEDULED'`` is the
    final duplicate prevention.
    """

    now = _now(now_utc)
    definitions_by_id = {definition.source_id: definition for definition in definitions}
    query = (
        session.query(SourceRuntimeStateRecord)
        .filter(SourceRuntimeStateRecord.enabled.is_(True))
        .filter(
            or_(
                SourceRuntimeStateRecord.next_run_at_utc <= now,
                and_(
                    SourceRuntimeStateRecord.circuit_state
                    == CircuitState.OPEN_CIRCUIT.value,
                    SourceRuntimeStateRecord.recovery_probe_at_utc <= now,
                ),
            )
        )
        .order_by(SourceRuntimeStateRecord.next_run_at_utc)
        .limit(max(1, min(int(limit), MAX_CLAIM_LIMIT)))
    )
    if session.get_bind().dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)

    claims: list[tuple[SourceRuntimeStateRecord, IngestionRunRecord]] = []
    for state in query.all():
        definition = definitions_by_id.get(state.source_id)
        if definition is None:
            continue
        recovery = state.circuit_state == CircuitState.OPEN_CIRCUIT.value
        if recovery and not recovery_probe_due(
            state=CircuitState(state.circuit_state),
            opened_at_utc=state.last_failure_at_utc,
            now_utc=now,
            policy=definition.circuit_policy,
        ):
            continue
        scheduled_for = as_utc(now if recovery else state.next_run_at_utc)
        trigger_type = (
            IngestionTriggerType.RECOVERY if recovery else IngestionTriggerType.SCHEDULED
        )
        if not recovery:
            existing = (
                session.query(IngestionRunRecord)
                .filter(
                    IngestionRunRecord.source_id == state.source_id,
                    IngestionRunRecord.trigger_type
                    == IngestionTriggerType.SCHEDULED.value,
                    IngestionRunRecord.scheduled_for_utc == scheduled_for,
                )
                .one_or_none()
            )
            if existing is not None:
                continue
        run = IngestionRunRecord(
            run_id=f"ingest-{uuid4().hex[:20]}",
            source_name=definition.provider,
            source_id=state.source_id,
            dataset=definition.dataset,
            trigger_type=trigger_type.value,
            requested_at_utc=now,
            scheduled_for_utc=scheduled_for,
            status=IngestionRunStatus.QUEUED.value,
            started_at_utc=now,
            finished_at_utc=None,
            completed_at_utc=None,
            attempt_number=1,
            correlation_id=f"dataops-{uuid4().hex[:12]}",
            adapter_version=definition.adapter_version,
            notes="Scheduled ingestion queued by data-operations scheduler.",
        )
        session.add(run)
        try:
            with session.begin_nested():
                session.flush()
        except IntegrityError:
            continue
        state.last_attempt_at_utc = now
        state.updated_at_utc = now
        state.next_run_at_utc = next_scheduled_instant(
            definition,
            activated_at=as_utc(state.activated_at_utc or now),
            after=scheduled_for,
        )
        claims.append((state, run))
    session.flush()
    return claims


def claim_queued_runs(
    session: Session,
    *,
    now_utc: datetime | None = None,
    limit: int = 10,
) -> list[IngestionRunRecord]:
    """Claim QUEUED runs for execution, marking them RUNNING."""

    now = _now(now_utc)
    query = (
        session.query(IngestionRunRecord)
        .filter(IngestionRunRecord.status == IngestionRunStatus.QUEUED.value)
        .order_by(IngestionRunRecord.scheduled_for_utc, IngestionRunRecord.requested_at_utc)
        .limit(max(1, min(int(limit), MAX_CLAIM_LIMIT)))
    )
    if session.get_bind().dialect.name == "postgresql":
        query = query.with_for_update(skip_locked=True)
    rows = list(query.all())
    for run in rows:
        run.status = IngestionRunStatus.RUNNING.value
        run.started_at_utc = run.started_at_utc or now
        run.attempt_number = max(1, run.attempt_number)
    session.flush()
    return rows


def recover_stale_runs(
    session: Session,
    *,
    now_utc: datetime | None = None,
    stale_after_seconds: int = STALE_RUN_SECONDS,
) -> int:
    """Mark QUEUED/RUNNING runs that outlived the stale threshold FAILED."""

    now = _now(now_utc)
    cutoff = now - timedelta(seconds=max(1, int(stale_after_seconds)))
    rows = (
        session.query(IngestionRunRecord)
        .filter(IngestionRunRecord.status.in_({"QUEUED", "RUNNING"}))
        .filter(IngestionRunRecord.started_at_utc < cutoff)
        .all()
    )
    for run in rows:
        run.status = IngestionRunStatus.FAILED.value
        run.completed_at_utc = now
        run.error_category = "INTERNAL"
        run.error_code = "STALE_RUN"
        run.notes = f"{run.notes or ''} Recovered stale run.".strip()
    session.flush()
    return len(rows)


def create_operator_run(
    session: Session,
    definition: SourceDefinition,
    *,
    trigger_type: IngestionTriggerType,
    now_utc: datetime | None = None,
    window_start_utc: datetime | None = None,
    window_end_utc: datetime | None = None,
    reason: str = "",
    retry_of_run_id: str | None = None,
) -> IngestionRunRecord:
    """Create MANUAL/BACKFILL/RECOVERY/CERTIFICATION_TEST runs."""

    now = _now(now_utc)
    state = session.get(SourceRuntimeStateRecord, definition.source_id)
    run = IngestionRunRecord(
        run_id=f"ingest-{uuid4().hex[:20]}",
        source_name=definition.provider,
        source_id=definition.source_id,
        dataset=definition.dataset,
        trigger_type=trigger_type.value,
        requested_at_utc=now,
        scheduled_for_utc=(
            window_start_utc
            if trigger_type == IngestionTriggerType.BACKFILL
            else now
        ),
        status=IngestionRunStatus.QUEUED.value,
        started_at_utc=now,
        window_start_utc=window_start_utc,
        window_end_utc=window_end_utc,
        attempt_number=1,
        correlation_id=f"dataops-{uuid4().hex[:12]}",
        adapter_version=definition.adapter_version,
        retry_of_run_id=retry_of_run_id,
        notes=reason or f"{trigger_type.value} operator run.",
    )
    if state is not None:
        state.last_attempt_at_utc = now
        state.updated_at_utc = now
    session.add(run)
    session.flush()
    return run


def finalize_run(
    session: Session,
    run: IngestionRunRecord,
    definition: SourceDefinition,
    *,
    classification: FailureClassification | None = None,
    quality_result: QualityResult = QualityResult.PASSED,
    quality_warning_count: int = 0,
    quality_error_count: int = 0,
    rows_received: int = 0,
    rows_accepted: int = 0,
    rows_rejected: int = 0,
    rows_inserted: int = 0,
    rows_updated: int = 0,
    duplicate_count: int = 0,
    fallback_used: bool = False,
    lineage_refs: list[str] | None = None,
    now_utc: datetime | None = None,
    succeeded: bool | None = None,
) -> IngestionRunRecord:
    """Persist one run outcome and update per-source circuit/freshness state."""

    now = _now(now_utc)
    success = succeeded if succeeded is not None else classification is None
    run.completed_at_utc = now
    run.finished_at_utc = now
    run.rows_received = max(0, int(rows_received))
    run.rows_accepted = max(0, int(rows_accepted))
    run.rows_rejected = max(0, int(rows_rejected))
    run.rows_inserted = max(0, int(rows_inserted))
    run.rows_updated = max(0, int(rows_updated))
    run.duplicate_count = max(0, int(duplicate_count))
    run.quality_warning_count = max(0, int(quality_warning_count))
    run.quality_error_count = max(0, int(quality_error_count))
    run.fallback_used = bool(fallback_used)
    if lineage_refs is not None:
        run.lineage_refs = list(lineage_refs)
    if success and (quality_error_count or quality_warning_count):
        run.status = IngestionRunStatus.SUCCEEDED_WITH_WARNINGS.value
    elif success:
        run.status = IngestionRunStatus.SUCCEEDED.value
    else:
        run.status = IngestionRunStatus.FAILED.value
        if classification is not None:
            run.error_category = classification.category.value
            run.error_code = classification.code or "ingestion_failed"
        else:
            run.error_category = "INTERNAL"
            run.error_code = "ingestion_failed"

    state = session.get(SourceRuntimeStateRecord, definition.source_id)
    if state is None:
        session.flush()
        return run
    state.last_attempt_at_utc = now
    state.adapter_version = definition.adapter_version
    state.pipeline_lag_seconds = (
        (as_utc(run.completed_at_utc) - as_utc(run.started_at_utc)).total_seconds()
        if run.started_at_utc and run.completed_at_utc
        else None
    )
    state.last_quality_result = quality_result.value
    state.quality_warning_count = max(0, int(quality_warning_count))
    state.quality_error_count = max(0, int(quality_error_count))
    if success:
        state.last_success_at_utc = now
        state.last_error_category = None
        state.last_error_code = None
        state.last_error_message = None
        next_circuit, failures = circuit_after_success(
            CircuitState(state.circuit_state)
        )
        state.circuit_state = next_circuit.value
        state.consecutive_failures = failures
        state.consecutive_successes += 1
        state.recovery_probe_at_utc = None
        evidence = FreshnessEvidence(
            observed_at_utc=state.last_success_at_utc,
            last_success_at_utc=state.last_success_at_utc,
            last_attempt_at_utc=now,
            access_granted=True,
        )
        evaluation = evaluate_source_freshness(definition, evidence, now_utc=now)
    else:
        state.last_failure_at_utc = now
        state.last_error_category = (
            classification.category.value if classification else "INTERNAL"
        )
        state.last_error_code = (
            classification.code if classification else "ingestion_failed"
        )
        state.last_error_message = (
            classification.message if classification else "Ingestion failed."
        )
        next_circuit, failures = circuit_after_failure(
            CircuitState(state.circuit_state),
            state.consecutive_failures,
            policy=definition.circuit_policy,
        )
        state.circuit_state = next_circuit.value
        state.consecutive_failures = failures
        state.consecutive_successes = 0
        if next_circuit == CircuitState.OPEN_CIRCUIT:
            state.recovery_probe_at_utc = now + timedelta(
                seconds=max(1, int(definition.circuit_policy.recovery_probe_after_seconds))
            )
        evaluation = evaluate_source_freshness(
            definition,
            FreshnessEvidence(
                observed_at_utc=state.last_success_at_utc,
                last_success_at_utc=state.last_success_at_utc,
                last_attempt_at_utc=now,
                access_granted=state.enabled,
            ),
            now_utc=now,
        )
    state.freshness_state = evaluation.state.value
    state.source_age_seconds = evaluation.source_age_seconds
    state.updated_at_utc = now
    session.flush()
    return run


def record_quality_issues(
    session: Session,
    run_id: str,
    issues: tuple[QualityIssue, ...] | list[QualityIssue],
    *,
    now_utc: datetime | None = None,
) -> int:
    """Persist structured quality issues for one run."""

    now = _now(now_utc)
    for issue in issues:
        session.add(
            IngestionRunIssueRecord(
                issue_id=f"issue-{uuid4().hex[:20]}",
                run_id=run_id,
                quality_code=issue.quality_code,
                severity=issue.severity.value,
                field=issue.field,
                observation_reference=issue.observation_reference,
                message=issue.message,
                rule_version=issue.rule_version,
                created_at_utc=now,
            )
        )
    session.flush()
    return len(issues)


def list_source_runs(
    session: Session,
    source_id: str,
    *,
    limit: int = 100,
) -> list[dict]:
    """List persisted runs for one source, newest first."""

    rows = (
        session.query(IngestionRunRecord)
        .filter(IngestionRunRecord.source_id == source_id)
        .order_by(IngestionRunRecord.started_at_utc.desc())
        .limit(max(1, min(int(limit), 500)))
        .all()
    )
    return [ingestion_run_payload(row) for row in rows]


def get_source_run(session: Session, run_id: str) -> IngestionRunRecord | None:
    return session.get(IngestionRunRecord, run_id)


def ingestion_run_payload(run: IngestionRunRecord) -> dict:
    """Serialize one ingestion run (datetime -> UTC ISO)."""

    return {
        "run_id": run.run_id,
        "source_name": run.source_name,
        "source_id": run.source_id,
        "dataset": run.dataset,
        "trigger_type": run.trigger_type,
        "requested_at_utc": _iso(run.requested_at_utc),
        "scheduled_for_utc": _iso(run.scheduled_for_utc),
        "status": run.status,
        "started_at_utc": _iso(run.started_at_utc),
        "finished_at_utc": _iso(run.finished_at_utc),
        "completed_at_utc": _iso(run.completed_at_utc),
        "window_start_utc": _iso(run.window_start_utc),
        "window_end_utc": _iso(run.window_end_utc),
        "attempt_number": run.attempt_number,
        "rows_received": run.rows_received,
        "rows_accepted": run.rows_accepted,
        "rows_rejected": run.rows_rejected,
        "rows_inserted": run.rows_inserted,
        "rows_updated": run.rows_updated,
        "duplicate_count": run.duplicate_count,
        "quality_warning_count": run.quality_warning_count,
        "quality_error_count": run.quality_error_count,
        "error_category": run.error_category,
        "error_code": run.error_code,
        "correlation_id": run.correlation_id,
        "adapter_version": run.adapter_version,
        "retry_of_run_id": run.retry_of_run_id,
        "fallback_used": run.fallback_used,
        "lineage_refs": run.lineage_refs or [],
        "notes": run.notes,
    }


def list_run_issues(session: Session, run_id: str) -> list[dict]:
    rows = (
        session.query(IngestionRunIssueRecord)
        .filter(IngestionRunIssueRecord.run_id == run_id)
        .order_by(IngestionRunIssueRecord.created_at_utc, IngestionRunIssueRecord.issue_id)
        .all()
    )
    return [
        {
            "issue_id": row.issue_id,
            "run_id": row.run_id,
            "quality_code": row.quality_code,
            "severity": row.severity,
            "field": row.field,
            "observation_reference": row.observation_reference,
            "message": row.message,
            "rule_version": row.rule_version,
            "created_at_utc": _iso(row.created_at_utc),
        }
        for row in rows
    ]


def source_runtime_payload(state: SourceRuntimeStateRecord) -> dict:
    """Serialize one source runtime state row."""

    return {
        "source_id": state.source_id,
        "provider": state.provider,
        "dataset": state.dataset,
        "source_class": state.source_class,
        "enabled": state.enabled,
        "circuit_state": state.circuit_state,
        "consecutive_failures": state.consecutive_failures,
        "consecutive_successes": state.consecutive_successes,
        "last_attempt_at_utc": _iso(state.last_attempt_at_utc),
        "last_success_at_utc": _iso(state.last_success_at_utc),
        "last_failure_at_utc": _iso(state.last_failure_at_utc),
        "last_error_category": state.last_error_category,
        "last_error_code": state.last_error_code,
        "activated_at_utc": _iso(state.activated_at_utc),
        "next_run_at_utc": _iso(state.next_run_at_utc),
        "recovery_probe_at_utc": _iso(state.recovery_probe_at_utc),
        "freshness_state": state.freshness_state,
        "source_age_seconds": state.source_age_seconds,
        "ingestion_lag_seconds": state.ingestion_lag_seconds,
        "pipeline_lag_seconds": state.pipeline_lag_seconds,
        "last_quality_result": state.last_quality_result,
        "quality_warning_count": state.quality_warning_count,
        "quality_error_count": state.quality_error_count,
        "entitlement_state": state.entitlement_state,
        "certification_state": state.certification_state,
        "adapter_version": state.adapter_version,
        "schedule": state.schedule_json,
        "freshness_policy": state.freshness_policy_json,
        "calendar": state.calendar,
        "updated_at_utc": _iso(state.updated_at_utc),
    }


def record_heartbeat(
    session: Session,
    *,
    now_utc: datetime | None = None,
    sources_scheduled: int = 0,
    sources_healthy: int = 0,
    sources_late: int = 0,
    sources_stale: int = 0,
    sources_failed: int = 0,
    certification_gaps: int = 0,
    entitlement_failures: int = 0,
    backlog_depth: int = 0,
    oldest_overdue_seconds: float | None = None,
    due_count: int = 0,
    claimed_count: int = 0,
    run_count: int = 0,
) -> DataOperationsHeartbeatRecord:
    now = _now(now_utc)
    row = session.get(DataOperationsHeartbeatRecord, "primary")
    if row is None:
        row = DataOperationsHeartbeatRecord(heartbeat_id="primary")
        session.add(row)
    row.last_heartbeat_at_utc = now
    row.last_scan_at_utc = now
    row.sources_scheduled = max(0, int(sources_scheduled))
    row.sources_healthy = max(0, int(sources_healthy))
    row.sources_late = max(0, int(sources_late))
    row.sources_stale = max(0, int(sources_stale))
    row.sources_failed = max(0, int(sources_failed))
    row.certification_gaps = max(0, int(certification_gaps))
    row.entitlement_failures = max(0, int(entitlement_failures))
    row.backlog_depth = max(0, int(backlog_depth))
    row.oldest_overdue_seconds = oldest_overdue_seconds
    row.due_count = max(0, int(due_count))
    row.claimed_count = max(0, int(claimed_count))
    row.run_count = max(0, int(run_count))
    session.flush()
    return row


def heartbeat_payload(row: DataOperationsHeartbeatRecord | None) -> dict:
    if row is None:
        return {
            "last_heartbeat_at_utc": None,
            "sources_scheduled": 0,
            "sources_healthy": 0,
            "sources_late": 0,
            "sources_stale": 0,
            "sources_failed": 0,
            "certification_gaps": 0,
            "entitlement_failures": 0,
            "backlog_depth": 0,
            "oldest_overdue_seconds": None,
        }
    return {
        "last_heartbeat_at_utc": _iso(row.last_heartbeat_at_utc),
        "last_scan_at_utc": _iso(row.last_scan_at_utc),
        "sources_scheduled": row.sources_scheduled,
        "sources_healthy": row.sources_healthy,
        "sources_late": row.sources_late,
        "sources_stale": row.sources_stale,
        "sources_failed": row.sources_failed,
        "certification_gaps": row.certification_gaps,
        "entitlement_failures": row.entitlement_failures,
        "backlog_depth": row.backlog_depth,
        "oldest_overdue_seconds": row.oldest_overdue_seconds,
        "due_count": row.due_count,
        "claimed_count": row.claimed_count,
        "run_count": row.run_count,
    }


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return as_utc(value).isoformat()
