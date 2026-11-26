"""Audit-event retention controls (R32).

Audit rows are kept at least seven years (retention schedule, data class
``audit_and_decisions``: REMIT, MiFID II and EMIR record keeping). Pruning older rows is always
operator-controlled and audited by the internal administration endpoint; the dry-run default
prevents accidental deletion, and the scheduled retention job never touches the audit trail.
Export the range first (``docs/compliance/RETENTION_SCHEDULE.md``).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

#: Seven years: the longest record-keeping horizon among MiFID II Art. 16(6)-(7) (5, up to 7
#: on a regulator's request), MAR, REMIT and EMIR. It is also the floor: a shorter window is
#: refused, because nothing a regulation requires may be deleted by a setting (decision record
#: 2026-11-26). It was five years by default with a 30-day floor.
DEFAULT_AUDIT_RETENTION_DAYS = 2557
MIN_AUDIT_RETENTION_DAYS = 2557
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
