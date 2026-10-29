"""Bounded operator CLI for National Gas REST actual-demand ingestion.

The explicit window selects provider rows by publication time (``applicableAt``),
not by gas day; the response may legitimately contain revisions for earlier gas
days.  The CLI uses only the fixed official fetch and the existing repository
transaction helpers.  It never creates schema, grants, or source activation and
never prints the resolved database URL.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from eurogas_nexus.db.repositories.demand_rest import (
    DemandRestInsertSummary,
    DemandRestPersistenceError,
    insert_demand_rest_rows,
)
from eurogas_nexus.db.session import get_session_factory, resolve_database_url
from eurogas_nexus.ingestion.national_gas_rest import (
    APPROVED_PUBLICATION_IDS,
    EVIDENCE_BASIS,
    UNIT,
    NationalGasRestDownload,
    NationalGasRestError,
    fetch_national_gas_rest,
    validate_publication_ids,
    validate_query_window,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit operator surface."""

    parser = argparse.ArgumentParser(
        description=(
            "Download and append National Gas REST actual-demand revisions. "
            "The window filters provider publication time (applicableAt), not "
            "gas day. No source is activated by this command."
        )
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Explicit SQLAlchemy URL; otherwise use the existing DB URL precedence.",
    )
    parser.add_argument(
        "--date-from",
        required=True,
        help="Inclusive publication-date start (YYYY-MM-DD); not a gas day.",
    )
    parser.add_argument(
        "--date-to",
        required=True,
        help="Inclusive publication-date end (YYYY-MM-DD); not a gas day.",
    )
    parser.add_argument(
        "--ids",
        required=True,
        nargs="+",
        help=(
            "One or both approved public item ids: "
            + ", ".join(sorted(APPROVED_PUBLICATION_IDS))
            + "."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and validate only; do not resolve or touch the database.",
    )
    return parser


def _error(code: str, error_type: str) -> int:
    """Print a stable, secret-free error and return the operator exit code."""

    print(
        json.dumps(
            {"status": "error", "code": code, "type": error_type}, sort_keys=True
        ),
        file=sys.stderr,
    )
    return 2


def _parse_date(raw: str, field: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise NationalGasRestError("INVALID_DATE", f"{field} is not YYYY-MM-DD") from exc


def _payload(
    *,
    date_from: date,
    date_to: date,
    publication_ids: tuple[str, ...],
    download: NationalGasRestDownload,
    summary: DemandRestInsertSummary | None,
) -> dict[str, object]:
    """Build the safe success document from actual fetch and persistence facts."""

    dry_run = summary is None
    if summary is None:
        rows_seen = len(download.rows)
        inserted = 0
        duplicates = 0
        publications = len({row.source_publication_id for row in download.rows})
    else:
        rows_seen = summary.rows_seen
        inserted = summary.inserted
        duplicates = summary.duplicates
        publications = summary.publications

    return {
        "status": "ok",
        "dry_run": dry_run,
        "persisted": not dry_run,
        "publication_date_from": date_from.isoformat(),
        "publication_date_to": date_to.isoformat(),
        "publication_ids": list(publication_ids),
        "rows_seen": rows_seen,
        "inserted": inserted,
        "duplicates": duplicates,
        "publications": publications,
        "unit": UNIT,
        "raw_sha256": download.raw_sha256,
        "received_at_utc": download.received_at_utc.isoformat(),
        "evidence_basis": EVIDENCE_BASIS,
    }


def main(argv: list[str] | None = None) -> int:
    """Run one bounded ingestion attempt and print a safe summary."""

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        date_from = _parse_date(args.date_from, "--date-from")
        date_to = _parse_date(args.date_to, "--date-to")
        validate_query_window(date_from, date_to)
        publication_ids = validate_publication_ids(args.ids)
    except NationalGasRestError as exc:
        return _error(exc.code, type(exc).__name__)

    try:
        download = fetch_national_gas_rest(
            date_from,
            date_to,
            publication_ids=publication_ids,
        )
    except NationalGasRestError as exc:
        return _error(exc.code, type(exc).__name__)
    except Exception as exc:
        return _error("INGESTION_FAILED", type(exc).__name__)

    if args.dry_run:
        payload = _payload(
            date_from=date_from,
            date_to=date_to,
            publication_ids=publication_ids,
            download=download,
            summary=None,
        )
        print(json.dumps(payload, sort_keys=True))
        return 0

    try:
        database_url = args.database_url or resolve_database_url()
        if not database_url:
            return _error("DATABASE_URL_REQUIRED", "ConfigurationError")

        session_factory = get_session_factory(database_url=database_url)
        with session_factory() as session, session.begin():
            summary = insert_demand_rest_rows(session, download.rows)
    except (NationalGasRestError, DemandRestPersistenceError) as exc:
        return _error(exc.code, type(exc).__name__)
    except Exception as exc:
        # Do not expose credentials, URLs, SQL, or provider payloads.
        return _error("INGESTION_FAILED", type(exc).__name__)

    payload = _payload(
        date_from=date_from,
        date_to=date_to,
        publication_ids=publication_ids,
        download=download,
        summary=summary,
    )
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
