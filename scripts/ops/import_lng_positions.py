"""Load LNG cargoes or regas slots (idempotent: rows are keyed by cargo or slot id).

    python scripts/ops/import_lng_positions.py --kind cargoes --source KPLER --file cargoes.csv
    python scripts/ops/import_lng_positions.py --kind slots --source ETRM --file slots.csv

Cargo exports come from the firm's own vessel-tracking subscription (for example Kpler)
or from the ETRM; slots from the ETRM or the terminal's capacity confirmation. See
``eurogas_nexus.ingestion.lng_positions`` for the columns. Books named in the file must
exist.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from eurogas_nexus.db.session import get_session_factory, redact_database_url, resolve_database_url
from eurogas_nexus.ingestion.lng_positions import (
    LngImportError,
    parse_lng_cargoes,
    parse_regas_slots,
)

MAX_BYTES = 64 * 1024 * 1024


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--kind", required=True, choices=("cargoes", "slots"))
    parser.add_argument("--source", required=True, help="KPLER, ETRM, MANUAL, ...")
    parser.add_argument("--file", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    path = Path(args.file)
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        print(f"File missing or larger than {MAX_BYTES} bytes: {path}")
        return 2
    parse = parse_lng_cargoes if args.kind == "cargoes" else parse_regas_slots
    source = args.source.strip().upper()
    try:
        rows = parse(
            path.read_text(encoding="utf-8"),
            source_system=source,
            source_reference=f"{source.lower()}:{path.name}",
            now_utc=datetime.now(UTC),
        )
    except LngImportError as exc:
        print(f"Refused: {exc}")
        return 2
    books = sorted({row["book_id"] for row in rows if row["book_id"]})
    print(f"{len(rows)} {args.kind}, books={books}")
    if args.dry_run:
        return 0
    database_url = resolve_database_url()
    if not database_url:
        print("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2
    print(f"Runtime DB: {redact_database_url(database_url)}")
    from eurogas_nexus.db.models import LngCargoRecord, RegasSlotRecord, TradingBookRecord

    model = LngCargoRecord if args.kind == "cargoes" else RegasSlotRecord
    with get_session_factory(database_url=database_url)() as session:
        known = {row.book_id for row in session.query(TradingBookRecord.book_id).all()}
        unknown = [book for book in books if book not in known]
        if unknown:
            print(f"Refused: books not defined: {unknown}")
            return 2
        for row in rows:
            session.merge(model(**row))
        session.commit()
    print(f"Loaded {len(rows)} {args.kind}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
