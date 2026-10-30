"""Import daily settlement prices (carbon, coal, power, gas, Henry Hub) from a licensed export.

    python scripts/ops/import_settlements.py --source ICE_ENDEX --file eua_api2.csv --dry-run
    python scripts/ops/import_settlements.py --source EEX --file eex_settlements.csv

See ``eurogas_nexus.ingestion.commodity_settlements`` for the columns. Rows are upserted by
(source, market, product, date) and served only to users whose data scopes include the
source family, which an administrator grants against the organisation's licence.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from eurogas_nexus.db.session import get_session_factory, redact_database_url, resolve_database_url
from eurogas_nexus.ingestion.commodity_settlements import (
    SETTLEMENT_SOURCES,
    SettlementImportError,
    parse_settlements,
)

MAX_EXPORT_BYTES = 16 * 1024 * 1024


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", required=True, choices=sorted(SETTLEMENT_SOURCES))
    parser.add_argument("--file", required=True)
    parser.add_argument("--source-reference", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    path = Path(args.file)
    if not path.is_file() or path.stat().st_size > MAX_EXPORT_BYTES:
        print(f"Export file missing or larger than {MAX_EXPORT_BYTES} bytes: {path}")
        return 2
    try:
        result = parse_settlements(
            path.read_text(encoding="utf-8"),
            source_system=args.source,
            source_reference=args.source_reference or f"operator-export:{path.name}",
        )
    except SettlementImportError as exc:
        print(f"Refused: {exc}")
        return 2
    print(
        f"{len(result.rows)} settlements, markets={result.markets}, "
        f"{result.first_day}..{result.last_day}"
    )
    if args.dry_run:
        return 0
    database_url = resolve_database_url()
    if not database_url:
        print("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2
    print(f"Runtime DB: {redact_database_url(database_url)}")
    from eurogas_nexus.db.models import MarketObservationRecord

    with get_session_factory(database_url=database_url)() as session:
        for row in result.rows:
            session.merge(MarketObservationRecord(**row))
        session.commit()
    print(f"Stored {len(result.rows)} {args.source} settlements.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
