"""Poll the registered news sources and store new or changed items (NEWS-1).

REMIT items are made from the messages the platform already holds (nothing is fetched); each
feed source is read only when its terms permit reuse, its feed address is recorded on the
publisher's own host, its poll interval has passed and the host's robots.txt allows it. No
source needs credentials or a sign-up. Without ``--commit`` nothing is stored: the run reports
what it would store and rolls back. The registry and each source's terms:
``docs/integration/NEWS_SOURCE_REGISTRY.md``.

    python scripts/ops/poll_news_sources.py                       # dry run, every source
    python scripts/ops/poll_news_sources.py --commit
    python scripts/ops/poll_news_sources.py --source govuk-desnz --force --commit
    python scripts/ops/poll_news_sources.py --source ec-energy-news \
        --feed-url https://commission.europa.eu/<feed path> --commit

The market event outbox worker then routes items that touch the book to each role
(``application/news_routing.py``) and re-evaluates opportunities on a linked outage.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from eurogas_nexus.application.news_ingest import Fetcher, http_fetch, poll_all, poll_source
from eurogas_nexus.db.session import get_session_factory, redact_database_url, resolve_database_url
from eurogas_nexus.domain.news.sources import NEWS_SOURCES_BY_ID, news_source


def main(argv: list[str] | None = None, *, fetch: Fetcher = http_fetch) -> int:
    """Poll and (with ``--commit``) store; returns a process exit code."""

    args = _parse_args(argv)
    if args.feed_url and not args.source:
        print("--feed-url needs --source: an address belongs to one publisher.")
        return 2
    database_url = resolve_database_url()
    if not database_url:
        print("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2
    print(f"Runtime DB: {redact_database_url(database_url)}")
    now = datetime.now(UTC)
    with get_session_factory(database_url=database_url)() as session:
        if args.source:
            outcomes = [poll_source(session, news_source(args.source), fetch=fetch, now=now,
                                    feed_url=args.feed_url, force=args.force)]
        else:
            outcomes = poll_all(session, fetch=fetch, now=now, force=args.force)
        for outcome in outcomes:
            print(f"{outcome.source_id:28s} {outcome.status:18s} seen={outcome.seen} "
                  f"new={outcome.new} changed={outcome.changed}"
                  + (f"  ({outcome.detail})" if outcome.detail else ""))
        if args.commit:
            session.commit()
            print("Stored.")
        else:
            session.rollback()
            print("Dry run: nothing stored (use --commit).")
    return 1 if any(o.status == "failed" for o in outcomes) else 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", choices=sorted(NEWS_SOURCES_BY_ID),
                        help="Poll one registered source only")
    parser.add_argument("--feed-url", help="The feed address on the publisher's own host")
    parser.add_argument("--force", action="store_true", help="Ignore the poll interval")
    parser.add_argument("--commit", action="store_true", help="Store the items")
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
