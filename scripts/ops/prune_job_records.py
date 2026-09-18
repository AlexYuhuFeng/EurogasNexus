"""Prune terminal job records older than an operator-supplied retention window.

Architecture V2 Wave 8: the unified job model writes a row per tracked run, and this is the
supported way to bound that table. Dry-run by default, and the window is required - no default
retention policy for job records has been agreed, so the operator states one.

Nothing here deletes work: a job row is bookkeeping about a run, and the reports, runs, dataset
snapshots and agent runs it references are separate records that stay. Active rows are never
eligible, however old they are; they are reported so an operator can run
`scripts/ops/recover_stale_jobs.py` instead.

Usage:
    python scripts/ops/prune_job_records.py --retention-days 180
    python scripts/ops/prune_job_records.py --retention-days 180 --commit
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC_PATH = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))


def main(argv: list[str] | None = None) -> int:
    """Prune job records according to the operator-supplied retention window."""

    from eurogas_nexus.application.job_retention import (
        MAX_JOB_RETENTION_DAYS,
        MIN_JOB_RETENTION_DAYS,
        prune_expired_job_records,
    )
    from eurogas_nexus.db.session import (
        get_session_factory,
        redact_database_url,
        resolve_database_url,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--retention-days",
        type=int,
        required=True,
        help=(
            "Terminal job rows older than this many days are eligible for pruning. Required: "
            f"no default retention policy is agreed ({MIN_JOB_RETENTION_DAYS}-"
            f"{MAX_JOB_RETENTION_DAYS})."
        ),
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Actually delete rows; the default is a dry-run.",
    )
    args = parser.parse_args(argv)

    database_url = resolve_database_url()
    if not database_url:
        print("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2

    print(f"Runtime DB: {redact_database_url(database_url)}")
    with get_session_factory()() as session:
        try:
            summary = prune_expired_job_records(
                session,
                retention_days=args.retention_days,
                dry_run=not args.commit,
            )
            session.commit()
        except ValueError as exc:
            print(f"Invalid retention policy: {exc}")
            return 2

    mode = "committed" if args.commit else "dry-run"
    print(
        f"Job prune {mode}: {summary['jobs_deleted']} rows deleted of "
        f"{summary['jobs_eligible']} eligible "
        f"(retention_days={summary['retention_days']}, cutoff={summary['cutoff_utc']})."
    )
    # What the window still represents: the oldest record that survives it, or the fact that none
    # does. An operator reading the line above alone cannot tell whether history now starts at the
    # cutoff or the table is empty, and those are different states to be in.
    oldest = summary["oldest_job_created_at_utc"]
    print(f"Oldest job still represented: {oldest if oldest else 'none'}")
    if summary["active_jobs_retained"]:
        # Older than the window and still not terminal: that is stale work, not history, and
        # the retention pass deliberately left it alone.
        print(
            f"Retained {summary['active_jobs_retained']} active row(s) older than the window; "
            "run scripts/ops/recover_stale_jobs.py to resolve them."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
