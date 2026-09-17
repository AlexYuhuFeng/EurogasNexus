"""Job-record retention controls (Architecture V2 Wave 8).

The unified job model writes a row per tracked run, so the table grows with use and an operator
needs a supported way to bound it. Pruning follows the audit-retention pattern
(:mod:`eurogas_nexus.application.audit_retention`): operator-controlled, dry-run by default, and
never scheduled - nothing deletes job records on its own.

Two rules this module enforces rather than documents:

- **A job that has not reached a terminal state is never pruned, whatever its age.** Deleting a
  ``QUEUED``, ``RUNNING`` or ``WAITING_FOR_INPUT`` row would erase work that is still happening,
  and that row is what ``POST /api/jobs/{job_id}/cancel`` acts on. Stale active rows are counted
  and reported instead, because they are a signal to run ``scripts/ops/recover_stale_jobs.py``,
  not something a retention pass should silently remove.
- **Pruning removes the record and nothing else.** A job's ``output_refs``, and the reports,
  runs, dataset snapshots and agent runs they name, are separate records: a job row is
  bookkeeping *about* work, so deleting it must never delete the work.

Unlike the audit window - which came from a stated policy (R32, 365 days) - there is no agreed
retention window for job records, so this module has **no default**: the caller states one, and
the bounds below only reject nonsense.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

MIN_JOB_RETENTION_DAYS = 1
MAX_JOB_RETENTION_DAYS = 3650


def prune_expired_job_records(
    session: Session,
    *,
    retention_days: int,
    now_utc: datetime | None = None,
    dry_run: bool = True,
) -> dict:
    """Delete (or count, when dry-run) terminal job rows older than the retention window.

    Args:
        session: Open session; the caller decides whether to commit.
        retention_days: The operator's window. Required, because no retention policy for job
            records has been agreed; the bounds below only reject values that cannot be meant.
        now_utc: Reference instant, defaulting to now.
        dry_run: When true (the default) nothing is deleted and the counts are what *would* be.

    Returns:
        A summary with the counts an operator needs to decide: how many rows are eligible, how
        many were deleted, how many active rows are older than the window and were kept, and
        the oldest instant still represented in the table.

    Raises:
        ValueError: ``retention_days`` is outside the supported bounds.
    """

    from eurogas_nexus.db.models import JobRecord
    from eurogas_nexus.domain.operations.jobs import TERMINAL_JOB_STATES

    if not MIN_JOB_RETENTION_DAYS <= retention_days <= MAX_JOB_RETENTION_DAYS:
        raise ValueError(
            f"retention_days must be between {MIN_JOB_RETENTION_DAYS} "
            f"and {MAX_JOB_RETENTION_DAYS}"
        )

    now = _as_utc(now_utc or datetime.now(UTC))
    cutoff = now - timedelta(days=retention_days)
    terminal_states = sorted(state.value for state in TERMINAL_JOB_STATES)

    eligible = session.query(JobRecord).filter(
        JobRecord.created_at_utc < cutoff,
        JobRecord.status.in_(terminal_states),
    )
    eligible_count = eligible.count()
    deleted = 0 if dry_run else eligible.delete(synchronize_session=False)
    if not dry_run:
        session.flush()

    # Active rows past the window are reported, never removed: they are work that has not
    # finished, and the honest answer is to surface them rather than to prune them.
    retained_active = (
        session.query(JobRecord)
        .filter(
            JobRecord.created_at_utc < cutoff,
            JobRecord.status.notin_(terminal_states),
        )
        .count()
    )
    oldest = session.query(JobRecord).order_by(JobRecord.created_at_utc.asc()).first()

    return {
        "dry_run": dry_run,
        "retention_days": retention_days,
        "cutoff_utc": cutoff.isoformat(),
        "jobs_eligible": eligible_count,
        "jobs_deleted": deleted,
        "active_jobs_retained": retained_active,
        "oldest_job_created_at_utc": (
            _as_utc(oldest.created_at_utc).isoformat() if oldest is not None else None
        ),
    }


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
