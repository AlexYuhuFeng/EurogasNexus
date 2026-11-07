"""Pull a feed from the firm's central data platform into the runtime store.

Trading firms run one central data platform that every application subscribes to: market
quotes, ETRM trades, nominations and fixings land there once, and each tool reads what it
needs. This script is that subscription for Eurogas Nexus. It reads one view from the
platform's database and hands the rows to the same importer a file export would use, so the
validation, book checks, cancellations, licence families and provenance are identical.

The platform side publishes a view per feed with the importer's column names (see
docs/architecture/CENTRAL_DATA_PLATFORM.md). The connection is read-only and its URL is a
secret: ``EUROGAS_NEXUS_CENTRAL_PLATFORM_URL`` (a SQLAlchemy URL). It may point at the same
PostgreSQL server as the runtime store (another schema) or a different one.

Usage:

    python scripts/ops/sync_central_platform.py --feed etrm-trades \\
        --view central.egn_etrm_trades --system Endur
    python scripts/ops/sync_central_platform.py --feed deliveries \\
        --view central.egn_contract_deliveries --source GASSCO --watch 300
    python scripts/ops/sync_central_platform.py --feed quotes \\
        --view central.egn_ice_endex_quotes --source ICE_ENDEX
    python scripts/ops/sync_central_platform.py --feed fx --view central.egn_wmr --source WMR

Licensed market data stays licensed: a quote feed keeps its source family, so only holders of
that data scope see it (AGENTS.md rule 18). Nothing here writes back to the platform.
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import re
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path

ROW_LIMIT = 200_000
_VIEW = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?$")


def _importers() -> dict[str, tuple[Callable[[list[str]], int], str]]:
    """Feed name -> (importer main, the flag carrying the source/system name)."""

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import import_contract_deliveries
    import import_etrm_trades
    import import_fx_fixings
    import import_market_quotes

    return {
        "etrm-trades": (import_etrm_trades.main, "--system"),
        "deliveries": (import_contract_deliveries.main, "--source"),
        "quotes": (import_market_quotes.main, "--source"),
        "fx": (import_fx_fixings.main, "--source"),
    }


def rows_as_csv(columns: list[str], rows: list[tuple]) -> str:
    """The view's rows in the importer's CSV form; ``None`` becomes an empty cell."""

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow(["" if value is None else value for value in row])
    return buffer.getvalue()


def read_view(url: str, view: str) -> tuple[list[str], list[tuple]]:
    """Every row of ``view`` (schema-qualified name only, never free SQL)."""

    if not _VIEW.match(view):
        raise ValueError(f"not a plain view name: {view!r}")
    from sqlalchemy import create_engine, text

    engine = create_engine(url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            result = connection.execute(text(f"SELECT * FROM {view} LIMIT {ROW_LIMIT + 1}"))
            columns = list(result.keys())
            rows = [tuple(row) for row in result]
    finally:
        engine.dispose()
    if len(rows) > ROW_LIMIT:
        raise ValueError(f"{view} returned more than {ROW_LIMIT} rows; publish a bounded view")
    return columns, rows


def sync_once(url: str, args: argparse.Namespace, importer: Callable[[list[str]], int],
              flag: str) -> int:
    columns, rows = read_view(url, args.view)
    print(f"{args.view}: {len(rows)} row(s)")
    if not rows:
        return 0
    with tempfile.TemporaryDirectory(prefix="egn-central-") as folder:
        path = Path(folder) / f"{args.feed}.csv"
        path.write_text(rows_as_csv(columns, rows), encoding="utf-8")
        argv = [flag, args.name, "--file", str(path)]
        if args.dry_run:
            argv.append("--dry-run")
        return importer(argv)


def main(argv: list[str] | None = None) -> int:
    importers = _importers()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--feed", required=True, choices=sorted(importers))
    parser.add_argument("--view", required=True, help="schema.view on the central platform")
    parser.add_argument("--source", "--system", dest="name", required=True,
                        help="source family (quotes, fx, deliveries) or ETRM name (trades)")
    parser.add_argument("--watch", type=float, default=0, help="poll seconds; 0 syncs once")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if args.watch and not 30 <= args.watch <= 86_400:
        parser.error("--watch must be 30..86400 seconds")
    url = os.getenv("EUROGAS_NEXUS_CENTRAL_PLATFORM_URL", "").strip()
    if not url:
        print("EUROGAS_NEXUS_CENTRAL_PLATFORM_URL is not set.", file=sys.stderr)
        return 2
    importer, flag = importers[args.feed]
    while True:
        try:
            status = sync_once(url, args, importer, flag)
        except ValueError as exc:
            print(f"Refused: {exc}", file=sys.stderr)
            return 2
        if not args.watch:
            return status
        time.sleep(args.watch)


if __name__ == "__main__":
    raise SystemExit(main())
