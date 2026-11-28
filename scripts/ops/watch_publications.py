"""Check the watched public publications now, and show their state (Package G).

The scheduler already runs this every 15 minutes (each publication on its own interval); use
it by hand to see the state, or to read one publication again at once. Without ``--commit``
nothing is stored: the run reports what it would do and rolls back. The registry and each
publication's terms: ``domain/publications/registry.py`` and ``docs/legal/DATA_SOURCE_TERMS.md``
("Watched publications, checked 2026-11-28"). Publications whose terms do not allow storing
them are never fetched; they are listed with their state.

    python scripts/ops/watch_publications.py                     # dry run, every publication
    python scripts/ops/watch_publications.py --commit
    python scripts/ops/watch_publications.py --publication entsog-cam-auction-calendar \\
        --force --commit
    python scripts/ops/watch_publications.py --status            # the state only, no fetch
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

from eurogas_nexus.application.news_ingest import Fetcher, http_fetch
from eurogas_nexus.application.publication_watch import (
    check_publication,
    queue_deadline_notifications,
    source_status,
    watch_all,
)
from eurogas_nexus.db.session import get_session_factory, redact_database_url, resolve_database_url
from eurogas_nexus.domain.publications.registry import WATCHED_PUBLICATIONS, watched_publication


def main(argv: list[str] | None = None, *, fetch: Fetcher = http_fetch) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--publication", choices=sorted(i.publication_id
                                                        for i in WATCHED_PUBLICATIONS))
    parser.add_argument("--force", action="store_true", help="Ignore the interval")
    parser.add_argument("--commit", action="store_true", help="Store what was read")
    parser.add_argument("--status", action="store_true", help="Show the state; fetch nothing")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    database_url = resolve_database_url()
    if not database_url:
        print("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2
    now = datetime.now(UTC)
    with get_session_factory(database_url=database_url)() as session:
        if args.status:
            rows = source_status(session, now=now)
            if args.json:
                print(json.dumps(rows, indent=2, default=str))
            else:
                for row in rows:
                    print(f"{row['publication_id']:38s} {row['state']:20s} "
                          f"fetched={row['last_fetched_at_utc'] or '-'}  {row['detail'][:70]}")
            return 0
        print(f"Runtime DB: {redact_database_url(database_url)}")
        if args.publication:
            outcomes = [check_publication(session, watched_publication(args.publication),
                                          fetch=fetch, now=now, force=args.force)]
            queue_deadline_notifications(session, now=now)
        else:
            outcomes = watch_all(session, fetch=fetch, now=now, force=args.force)
        for outcome in outcomes:
            print(f"{outcome.publication_id:38s} {outcome.status:20s} {outcome.detail[:80]}"
                  + (f"  {outcome.applied}" if outcome.applied else ""))
        if args.commit:
            session.commit()
            print("Stored.")
        else:
            session.rollback()
            print("Dry run: nothing stored (use --commit).")
    return 1 if any(o.status == "unreachable" for o in outcomes) else 0


if __name__ == "__main__":
    raise SystemExit(main())
