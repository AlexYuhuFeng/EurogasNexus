"""Prune expired audit events under the R32 retention policy.

Dry-run by default. Never prints event details or database secrets. A deletion needs a
privileged change of kind ``audit_prune`` that a second administrator approved (security review
H5/H7); with the database roles split it runs with the schema owner's URL, because the
application role may not delete audit rows (docs/security/DATABASE_ROLES.md).

Usage:
    python scripts/ops/prune_audit_events.py --retention-days 1827
    python scripts/ops/prune_audit_events.py --retention-days 1827 --commit --approved-change pc-...
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SRC_PATH = Path(__file__).resolve().parents[2] / "src"
if str(_SRC_PATH) not in sys.path:
    sys.path.insert(0, str(_SRC_PATH))


def main(argv: list[str] | None = None) -> int:
    """Prune audit events according to the operator-supplied retention window."""

    from eurogas_nexus.application.audit_retention import (
        DEFAULT_AUDIT_RETENTION_DAYS,
        prune_expired_audit_events,
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
        default=DEFAULT_AUDIT_RETENTION_DAYS,
        help="Audit rows older than this many days are eligible for pruning.",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Actually delete rows; the default is a dry-run.",
    )
    parser.add_argument(
        "--approved-change",
        default=None,
        help="The approved audit_prune privileged change that authorises a deletion.",
    )
    args = parser.parse_args(argv)

    database_url = resolve_database_url()
    if not database_url:
        print("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2

    print(f"Runtime DB: {redact_database_url(database_url)}")
    with get_session_factory()() as session:
        try:
            change_id = None
            if args.commit:
                change_id = _approved_change(session, args.approved_change, args.retention_days)
            summary = prune_expired_audit_events(
                session,
                retention_days=args.retention_days,
                dry_run=not args.commit,
                approved_change_id=change_id,
                by="prune-cli",
            )
            session.commit()
        except ValueError as exc:
            print(f"Refused: {exc}")
            return 2

    mode = "committed" if args.commit else "dry-run"
    print(
        f"Audit prune {mode}: {summary['audit_events_deleted']} rows eligible "
        f"(retention_days={summary['retention_days']}, "
        f"cutoff={summary['cutoff_utc']})."
    )
    return 0


def _approved_change(session, change_id: str | None, retention_days: int) -> str:
    """The approved audit_prune change for this window, marked applied; ValueError otherwise."""

    from datetime import UTC, datetime

    from eurogas_nexus.db.models import PrivilegedChangeRecord

    change = session.get(PrivilegedChangeRecord, change_id or "")
    if (
        change is None
        or change.kind != "audit_prune"
        or change.state != "approved"
        or (change.body_json or {}).get("retention_days") != retention_days
    ):
        raise ValueError(
            "a deletion needs --approved-change naming an approved audit_prune change for "
            "this retention window (request it under Admin, Audit)"
        )
    change.state = "applied"
    change.applied_at_utc = datetime.now(UTC)
    return change.change_id


if __name__ == "__main__":
    raise SystemExit(main())
