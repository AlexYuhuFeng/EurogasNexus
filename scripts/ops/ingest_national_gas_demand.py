"""Bounded operator CLI for National Gas NTS actual-demand ingestion.

The CLI performs actual network and database work only when an operator invokes
it explicitly.  It obtains the database URL from ``--database-url`` or the
existing ``resolve_database_url`` precedence and never creates schema, grants
access, activates a source, or prints provider response bodies.

Two ways to name the window:

- strict: ``--date-from``/``--date-to`` and ``--ids`` (an explicit operator capture);
- rolling: ``--days N`` reads the N gas days ending yesterday for both approved ids
  (``--ids`` may narrow them). The data-ops scheduler runs
  ``--json --days 8`` (``src-national-gas-demand``): with ``--json`` stdout carries only
  the scheduler's report.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime, timedelta

import httpx

from eurogas_nexus.core.outbound_http import client_options
from eurogas_nexus.db.repositories.demand import (
    DemandPersistenceError,
    insert_demand_rows,
)
from eurogas_nexus.db.session import get_session_factory, resolve_database_url
from eurogas_nexus.ingestion.national_gas_demand import (
    ALLOWED_PROVIDER_ITEM_IDS,
    DOWNLOAD_URL,
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
    parser.add_argument("--date-from", default=None, type=date.fromisoformat)
    parser.add_argument("--date-to", default=None, type=date.fromisoformat)
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        help="Rolling window: the N gas days ending yesterday (instead of explicit dates).",
    )
    parser.add_argument(
        "--ids",
        default=None,
        nargs="+",
        choices=sorted(ALLOWED_PROVIDER_ITEM_IDS),
        help="One or both approved public item ids (required with explicit dates).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the data-ops scheduler's JSON report (ok, sources) on stdout.",
    )
    return parser


def _window(args, parser: argparse.ArgumentParser) -> tuple[date, date, list[str]]:
    """The gas days and ids to read: explicit (strict) or a rolling ``--days`` window."""

    explicit = args.date_from is not None or args.date_to is not None
    if args.days is not None:
        if explicit:
            parser.error("use --days or --date-from/--date-to, not both")
        if args.days < 1:
            parser.error("--days must be at least 1")
        last = datetime.now(UTC).date() - timedelta(days=1)
        ids = list(args.ids or sorted(ALLOWED_PROVIDER_ITEM_IDS))
        return last - timedelta(days=args.days - 1), last, ids
    if args.date_from is None or args.date_to is None or not args.ids:
        parser.error("--date-from, --date-to and --ids are required without --days")
    return args.date_from, args.date_to, list(args.ids)


def main(argv: list[str] | None = None) -> int:
    """Run one bounded ingestion attempt and print a safe summary."""

    parser = build_parser()
    args = parser.parse_args(argv)
    date_from, date_to, ids = _window(args, parser)
    publication_ids = list(dict.fromkeys(ids))
    if len(publication_ids) > 2:
        parser.error("at most two approved publication ids are allowed")

    try:
        validate_query_window(date_from, date_to)
    except NationalGasDemandError as exc:
        parser.error(exc.code)

    def fail(code: str) -> int:
        print(json.dumps({"status": "error", "code": code}), file=sys.stderr)
        if args.json:
            print(json.dumps({"ok": False, "failures": [{"code": code}], "sources": {}}))
        return 2

    database_url = args.database_url or resolve_database_url()
    if not database_url:
        return fail("DATABASE_URL_REQUIRED")

    try:
        with httpx.Client(
            timeout=10.0,
            follow_redirects=False,
            trust_env=False,
            **client_options(DOWNLOAD_URL),
        ) as client:
            downloads = [
                download_national_gas_csv(
                    publication_id,
                    date_from=date_from,
                    date_to=date_to,
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
        return fail(exc.code)
    except Exception:
        # Do not expose credentials, URLs, SQL, or provider payloads.
        return fail("INGESTION_FAILED")

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
    if not args.json:
        print(json.dumps(payload, sort_keys=True))
        return 0
    # The scheduler's report: an append-only log, so a publication seen before is
    # "unchanged" and nothing is ever updated or revised in place.
    print(f"window {date_from} to {date_to}: {json.dumps(payload, sort_keys=True)}",
          file=sys.stderr)
    seen = sum(summary.rows_seen for summary in summaries)
    report = {
        "ok": seen > 0,
        "failures": [] if seen else [{"code": "NO_ROWS_PUBLISHED"}],
        "sources": {
            "national_gas_demand": {
                "records": seen,
                "inserted": payload["inserted"],
                "updated": 0,
                "unchanged": payload["duplicates"],
                "revised": 0,
            }
        },
    }
    print(json.dumps(report, sort_keys=True))
    return 0 if seen else 1


if __name__ == "__main__":
    raise SystemExit(main())
