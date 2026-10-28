"""Bounded operator CLI for National Gas NTS actual-demand ingestion.

The CLI performs actual network and database work only when an operator invokes
it explicitly.  It obtains the database URL from ``--database-url`` or the
existing ``resolve_database_url`` precedence and never creates schema, grants
access, activates a source, or prints provider response bodies.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

import httpx

from eurogas_nexus.db.repositories.demand import (
    DemandPersistenceError,
    insert_demand_rows,
)
from eurogas_nexus.db.session import get_session_factory, resolve_database_url
from eurogas_nexus.ingestion.national_gas_demand import (
    ALLOWED_PROVIDER_ITEM_IDS,
    NationalGasDemandError,
    download_national_gas_csv,
    validate_query_window,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit operator surface."""

    parser = argparse.ArgumentParser(
        description=(
            "Download and append National Gas NTS actual-demand revisions. "
            "No source is activated by this command."
        )
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Explicit SQLAlchemy URL; otherwise use the existing DB URL precedence.",
    )
    parser.add_argument("--date-from", required=True, type=date.fromisoformat)
    parser.add_argument("--date-to", required=True, type=date.fromisoformat)
    parser.add_argument(
        "--ids",
        required=True,
        nargs="+",
        choices=sorted(ALLOWED_PROVIDER_ITEM_IDS),
        help="One or both approved public item ids.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run one bounded ingestion attempt and print a safe summary."""

    parser = build_parser()
    args = parser.parse_args(argv)
    publication_ids = list(dict.fromkeys(args.ids))
    if len(publication_ids) > 2:
        parser.error("at most two approved publication ids are allowed")

    try:
        validate_query_window(args.date_from, args.date_to)
    except NationalGasDemandError as exc:
        parser.error(exc.code)

    database_url = args.database_url or resolve_database_url()
    if not database_url:
        print(
            json.dumps({"status": "error", "code": "DATABASE_URL_REQUIRED"}),
            file=sys.stderr,
        )
        return 2

    try:
        with httpx.Client(timeout=10.0, follow_redirects=False, trust_env=False) as client:
            downloads = [
                download_national_gas_csv(
                    publication_id,
                    date_from=args.date_from,
                    date_to=args.date_to,
                    client=client,
                )
                for publication_id in publication_ids
            ]

        session_factory = get_session_factory(database_url=database_url)
        with session_factory() as session, session.begin():
            summaries = [
                insert_demand_rows(session, download.rows) for download in downloads
            ]
    except (NationalGasDemandError, DemandPersistenceError) as exc:
        print(json.dumps({"status": "error", "code": exc.code}), file=sys.stderr)
        return 2
    except Exception:
        # Do not expose credentials, URLs, SQL, or provider payloads.
        print(json.dumps({"status": "error", "code": "INGESTION_FAILED"}), file=sys.stderr)
        return 2

    payload = {
        "status": "ok",
        "publications": [
            {
                "provider_item_id": publication_id,
                "rows_seen": summary.rows_seen,
                "inserted": summary.inserted,
                "duplicates": summary.duplicates,
            }
            for publication_id, summary in zip(publication_ids, summaries, strict=True)
        ],
        "inserted": sum(summary.inserted for summary in summaries),
        "duplicates": sum(summary.duplicates for summary in summaries),
    }
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
