"""Unified Job repository (Architecture V2 Wave 8).

Storage for the shared lifecycle in ``eurogas_nexus.domain.operations.jobs``. The
domain module owns the transition rules; this module owns persistence, ordering and
the audit trail, so a job list and an audit export cannot disagree.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from eurogas_nexus.db.models.jobs import JobRecord
from eurogas_nexus.db.repositories.audit import record_audit_event
from eurogas_nexus.domain.identity.principal import normalize_principal
from eurogas_nexus.domain.operations.jobs import (
    Job,
    JobKind,
    JobState,
    job_cancelled,
    job_failed,
    job_payload,
    job_progress,
    job_started,
    job_succeeded,
)


def create_job(
    session: Session,
    *,
    kind: str,
    principal: str,
    scope_refs: tuple[str, ...] = (),
    snapshot_id: str = "",
    input_hash: str = "",
    correlation_id: str | None = None,
    provenance: tuple[str, ...] = (),
    cancellable: bool = True,
    now_utc: datetime | None = None,
) -> dict:
    """Create a job in QUEUED state.

    Raises:
        ValueError: unknown job kind.
    """

    try:
        resolved_kind = JobKind(kind)
    except ValueError as exc:
        raise ValueError("unknown_job_kind") from exc

    now = _as_utc(now_utc or datetime.now(UTC))
    row = JobRecord(
        job_id=f"job-{uuid4().hex[:24]}",
        kind=resolved_kind.value,
        job_version="job/v1",
        status=JobState.QUEUED.value,
        principal=normalize_principal(principal),
        scope_refs_json=list(scope_refs),
        snapshot_id=snapshot_id,
        input_hash=input_hash,
        progress=0.0,
        created_at_utc=now,
        started_at_utc=None,
        finished_at_utc=None,
        output_refs_json=[],
        error_code="",
        error_message=None,
        retryable=False,
        cancellable=cancellable,
        correlation_id=correlation_id,
        provenance_json=list(provenance),
    )
    session.add(row)
    session.flush()
    return job_payload(_to_domain(row))


def start_job(session: Session, job_id: str, *, now_utc: datetime | None = None) -> dict:
    """Move a job into RUNNING."""

    row = _require_job(session, job_id)
    return _apply(session, row, job_started(_to_domain(row), now_utc=now_utc))


def update_progress(
    session: Session, job_id: str, progress: float, *, now_utc: datetime | None = None
) -> dict:
    """Advance progress monotonically."""

    row = _require_job(session, job_id)
    return _apply(session, row, job_progress(_to_domain(row), progress))


def finish_job(
    session: Session,
    job_id: str,
    *,
    output_refs: tuple[str, ...] = (),
    now_utc: datetime | None = None,
) -> dict:
    """Finish a job successfully and record the audit event."""

    row = _require_job(session, job_id)
    domain = job_succeeded(_to_domain(row), output_refs=output_refs, now_utc=now_utc)
    payload = _apply(session, row, domain)
    record_audit_event(
        session,
        event_type="operations.job",
        principal=domain.principal,
        action="job_succeeded",
        resource=f"job:{job_id}",
        outcome="succeeded",
        severity="info",
        detail=f"kind={domain.kind.value}; outputs={len(domain.output_refs)}",
        source_system="operations",
        now_utc=_as_utc(now_utc or datetime.now(UTC)),
    )
    return payload


def fail_job(
    session: Session,
    job_id: str,
    *,
    error_code: str,
    error_message: str = "",
    retryable: bool = False,
    now_utc: datetime | None = None,
) -> dict:
    """Fail a job with a stable taxonomy code and record the audit event."""

    row = _require_job(session, job_id)
    domain = job_failed(
        _to_domain(row),
        error_code=error_code,
        error_message=error_message,
        retryable=retryable,
        now_utc=now_utc,
    )
    payload = _apply(session, row, domain)
    record_audit_event(
        session,
        event_type="operations.job",
        principal=domain.principal,
        action="job_failed",
        resource=f"job:{job_id}",
        outcome="failed",
        severity="warning",
        detail=f"kind={domain.kind.value}; code={domain.error_code}",
        source_system="operations",
        now_utc=_as_utc(now_utc or datetime.now(UTC)),
    )
    return payload


def cancel_job(session: Session, job_id: str, *, now_utc: datetime | None = None) -> dict:
    """Cancel a cancellable, non-terminal job.

    Raises:
        ValueError: ``job_already_finished`` or ``job_not_cancellable``.
    """

    row = _require_job(session, job_id)
    domain = job_cancelled(_to_domain(row), now_utc=now_utc)
    payload = _apply(session, row, domain)
    record_audit_event(
        session,
        event_type="operations.job",
        principal=domain.principal,
        action="job_cancelled",
        resource=f"job:{job_id}",
        outcome="cancelled",
        severity="info",
        detail=f"kind={domain.kind.value}",
        source_system="operations",
        now_utc=_as_utc(now_utc or datetime.now(UTC)),
    )
    return payload


def get_job(session: Session, job_id: str) -> dict | None:
    """Return one job payload, or ``None`` when it does not exist."""

    row = session.get(JobRecord, job_id)
    return None if row is None else job_payload(_to_domain(row))


def list_jobs(
    session: Session,
    *,
    status: str | None = None,
    kind: str | None = None,
    principal: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """List jobs newest first."""

    query = session.query(JobRecord)
    if status:
        query = query.filter(JobRecord.status == status)
    if kind:
        query = query.filter(JobRecord.kind == kind)
    if principal:
        query = query.filter(JobRecord.principal == principal)
    rows = (
        query.order_by(JobRecord.created_at_utc.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return [job_payload(_to_domain(row)) for row in rows]


def _apply(session: Session, row: JobRecord, domain: Job) -> dict:
    row.status = domain.status.value
    row.progress = domain.progress
    row.started_at_utc = _parse(domain.started_at_utc)
    row.finished_at_utc = _parse(domain.finished_at_utc)
    row.output_refs_json = list(domain.output_refs)
    row.error_code = domain.error_code
    row.error_message = domain.error_message or None
    row.retryable = domain.retryable
    row.cancellable = domain.cancellable
    session.flush()
    return job_payload(domain)


def _to_domain(row: JobRecord) -> Job:
    return Job(
        job_id=row.job_id,
        kind=JobKind(row.kind),
        status=JobState(row.status),
        principal=row.principal,
        job_version=row.job_version,
        scope_refs=tuple(str(value) for value in row.scope_refs_json or []),
        snapshot_id=row.snapshot_id or "",
        input_hash=row.input_hash or "",
        progress=float(row.progress or 0.0),
        created_at_utc=_as_utc(row.created_at_utc).isoformat(),
        started_at_utc=_as_utc(row.started_at_utc).isoformat() if row.started_at_utc else None,
        finished_at_utc=(
            _as_utc(row.finished_at_utc).isoformat() if row.finished_at_utc else None
        ),
        output_refs=tuple(str(value) for value in row.output_refs_json or []),
        error_code=row.error_code or "",
        error_message=row.error_message or "",
        retryable=bool(row.retryable),
        cancellable=bool(row.cancellable),
        correlation_id=row.correlation_id,
        provenance=tuple(str(value) for value in row.provenance_json or []),
    )


def _require_job(session: Session, job_id: str) -> JobRecord:
    row = session.get(JobRecord, job_id)
    if row is None:
        raise ValueError("unknown_job")
    return row


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return _as_utc(datetime.fromisoformat(value))
    except ValueError:
        return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
