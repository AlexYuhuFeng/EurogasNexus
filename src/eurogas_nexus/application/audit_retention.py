"""Audit-event retention controls (R32).

Default retention is 365 days. Pruning is always operator-controlled and
audited by the internal administration endpoint; the dry-run default prevents
accidental deletion.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

DEFAULT_AUDIT_RETENTION_DAYS = 365
MIN_AUDIT_RETENTION_DAYS = 30
MAX_AUDIT_RETENTION_DAYS = 3650


def prune_expired_audit_events(
    session: Session,
    *,
    retention_days: int = DEFAULT_AUDIT_RETENTION_DAYS,
    now_utc: datetime | None = None,
    dry_run: bool = True,
) -> dict:
    """Delete (or count, when dry-run) audit rows older than retention."""

    from eurogas_nexus.db.models import AuditEventRecord

    if not MIN_AUDIT_RETENTION_DAYS <= retention_days <= MAX_AUDIT_RETENTION_DAYS:
        raise ValueError(
            f"retention_days must be between {MIN_AUDIT_RETENTION_DAYS} "
            f"and {MAX_AUDIT_RETENTION_DAYS}"
        )
    now = _as_utc(now_utc or datetime.now(UTC))
    cutoff = now - timedelta(days=retention_days)
    query = session.query(AuditEventRecord).filter(
        AuditEventRecord.event_ts_utc < cutoff
    )
    deleted = query.count() if dry_run else query.delete(synchronize_session=False)
    session.flush()
    return {
        "dry_run": dry_run,
        "retention_days": retention_days,
        "cutoff_utc": cutoff.isoformat(),
        "audit_events_deleted": deleted,
    }


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
