"""Import quotes exported from your own licensed trading screen (Trayport, ICE, EEX).

Live hub prices are licensed per subscriber; this bridges the entitlement a desk
already holds. Export the screen (or save an Excel/RTD sheet as CSV on a timer) and
import it once, or let ``--watch`` re-import whenever the file changes:

    python scripts/ops/import_market_quotes.py --source Trayport --file trayport.csv
    python scripts/ops/import_market_quotes.py --source Trayport --file trayport.csv --watch 5
    python scripts/ops/import_market_quotes.py --source ICE_OCM --file ice.csv --nbp-unit GBP/MWh

Rows land in ``market_quotes`` under the licensed source family (entitlement applies),
not marked simulated, and the intraday spread scan runs on them.
"""

from __future__ import annotations

import argparse
import time
from datetime import UTC, datetime
from pathlib import Path

from eurogas_nexus.db.session import (
    get_session_factory,
    redact_database_url,
    resolve_database_url,
)
from eurogas_nexus.ingestion.licensed_quote_import import (
    LICENSED_QUOTE_SOURCES,
    QuoteImportError,
    parse_quote_export,
)

MAX_EXPORT_BYTES = 16 * 1024 * 1024


def import_once(session_factory, path: Path, args: argparse.Namespace) -> int:
    """Parse and persist one export; returns rows imported (0 on refusal)."""

    from eurogas_nexus.db.repositories.market_intelligence import (
        scan_and_persist_intraday_opportunities,
        upsert_market_quotes,
    )

    if not path.is_file() or path.stat().st_size > MAX_EXPORT_BYTES:
        print(f"Refused: export missing or larger than {MAX_EXPORT_BYTES} bytes: {path}")
        return 0
    now = datetime.now(UTC)
    try:
        result = parse_quote_export(
            path.read_text(encoding="utf-8"),
            source_system=args.source,
            source_reference=f"operator-export:{path.name}",
            received_at_utc=now,
            default_units={"NBP": args.nbp_unit} if args.nbp_unit else None,
            quantity_unit_override=args.quantity_unit,
        )
    except QuoteImportError as exc:
        print(f"Refused: {exc}")
        return 0
    if args.dry_run:
        print(f"{len(result.rows)} quotes ok: hubs={result.hubs} products={result.products}")
        return len(result.rows)
    with session_factory() as session:
        upsert_market_quotes(session, result.rows)
        scan = scan_and_persist_intraday_opportunities(session, detected_at_utc=now)
        session.commit()
    print(
        f"{now.isoformat()} imported {len(result.rows)} {args.source} quotes "
        f"({', '.join(result.hubs)}); spread scan: {scan}"
    )
    return len(result.rows)


def main(argv: list[str] | None = None) -> int:
    """Run once or watch the export file; returns a process exit code."""

    args = _parse_args(argv)
    path = Path(args.file)
    session_factory = None
    if not args.dry_run:
        database_url = resolve_database_url()
        if not database_url:
            print("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
            return 2
        print(f"Runtime DB: {redact_database_url(database_url)}")
        session_factory = get_session_factory(database_url=database_url)
    if not args.watch:
        return 0 if import_once(session_factory, path, args) else 2
    last_mtime = None
    print(f"Watching {path} every {args.watch}s (Ctrl+C to stop)")
    try:
        while True:
            mtime = path.stat().st_mtime if path.exists() else None
            if mtime is not None and mtime != last_mtime:
                last_mtime = mtime
                import_once(session_factory, path, args)
            time.sleep(args.watch)
    except KeyboardInterrupt:
        return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", required=True, choices=sorted(LICENSED_QUOTE_SOURCES))
    parser.add_argument("--file", required=True)
    parser.add_argument("--nbp-unit", choices=("GBp/th", "GBP/MWh"), default=None)
    parser.add_argument(
        "--quantity-unit", choices=("MW", "MWh/d", "th/d"), default=None,
        help="screen volume unit; default MW for MWh-priced rows, th/d for p/th rows",
    )
    parser.add_argument("--watch", type=float, default=0, help="poll seconds; 0 imports once")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.watch and not 1 <= args.watch <= 3600:
        parser.error("--watch must be 1..3600 seconds")
    return args


if __name__ == "__main__":
    raise SystemExit(main())
