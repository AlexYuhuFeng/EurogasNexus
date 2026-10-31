"""Load an ETRM trade extract into books (idempotent; cancellations remove trades).

    python scripts/ops/import_etrm_trades.py --system Endur --file trades.csv --dry-run
    python scripts/ops/import_etrm_trades.py --system Endur --file trades.csv

See ``eurogas_nexus.ingestion.etrm_trades`` for the columns. Books named in the extract
must exist (Portfolio -> Exposure -> Trading books, or PUT /api/portfolio/books/{id}).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from eurogas_nexus.db.session import get_session_factory, redact_database_url, resolve_database_url
from eurogas_nexus.ingestion.etrm_trades import EtrmImportError, parse_etrm_trades

MAX_BYTES = 64 * 1024 * 1024


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--system", required=True, help="ETRM name, e.g. Endur, Allegro")
    parser.add_argument("--file", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    path = Path(args.file)
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        print(f"Extract missing or larger than {MAX_BYTES} bytes: {path}")
        return 2
    try:
        result = parse_etrm_trades(
            path.read_text(encoding="utf-8"),
            system=args.system,
            source_reference=f"etrm:{args.system}:{path.name}",
        )
    except EtrmImportError as exc:
        print(f"Refused: {exc}")
        return 2
    books = sorted({row["book_id"] for row in result.upserts if row["book_id"]})
    print(f"{len(result.upserts)} trades, {len(result.cancelled_ids)} cancellations, books={books}")
    if args.dry_run:
        return 0
    database_url = resolve_database_url()
    if not database_url:
        print("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2
    print(f"Runtime DB: {redact_database_url(database_url)}")
    from eurogas_nexus.db.models import ScreenOrderObservationRecord, TradingBookRecord

    with get_session_factory(database_url=database_url)() as session:
        known = {row.book_id for row in session.query(TradingBookRecord.book_id).all()}
        unknown = [book for book in books if book not in known]
        if unknown:
            print(f"Refused: books not defined: {unknown}")
            return 2
        for row in result.upserts:
            session.merge(ScreenOrderObservationRecord(**row))
        if result.cancelled_ids:
            session.query(ScreenOrderObservationRecord).filter(
                ScreenOrderObservationRecord.order_observation_id.in_(result.cancelled_ids)
            ).delete(synchronize_session=False)
        session.commit()
    print(f"Loaded {len(result.upserts)} trades; removed {len(result.cancelled_ids)} cancelled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
