"""Prune expired runtime rows per the retention policy.

Defaults (D6): market quotes 30 days, market observations 90 days, intraday
opportunities 7 days. Run with --dry-run to report counts without deleting.
"""

from __future__ import annotations

import argparse
import json

from eurogas_nexus.db.session import get_session_factory, resolve_database_url


def main() -> int:
    """    Prune stale runtime records per the retention policy."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Report counts without deleting.")
    args = parser.parse_args()

    if resolve_database_url() is None:
        print(json.dumps({"status": "blocked", "reason": "database_url_missing"}))
        return 2

    from eurogas_nexus.application.retention import prune_expired_rows

    try:
        with get_session_factory()() as session:
            summary = prune_expired_rows(session, dry_run=args.dry_run)
            session.commit()
        print(json.dumps({"status": "ok", **summary}, sort_keys=True), flush=True)
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": exc.__class__.__name__,
                }
            ),
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
