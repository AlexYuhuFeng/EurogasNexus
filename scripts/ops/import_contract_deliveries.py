"""Load daily nominations and allocations for bilateral supply contracts (idempotent).

    python scripts/ops/import_contract_deliveries.py --source GASSCO --file allocations.csv

See ``eurogas_nexus.ingestion.contract_deliveries`` for the columns. Contract ids must exist
among the stored upstream contracts; unknown ids refuse the whole file.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from eurogas_nexus.db.session import get_session_factory, redact_database_url, resolve_database_url
from eurogas_nexus.ingestion.contract_deliveries import (
    DeliveryImportError,
    parse_contract_deliveries,
)

MAX_BYTES = 64 * 1024 * 1024


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", required=True, help="GASSCO, GTS, ETRM, MANUAL, ...")
    parser.add_argument("--file", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    path = Path(args.file)
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        print(f"File missing or larger than {MAX_BYTES} bytes: {path}")
        return 2
    source = args.source.strip().upper()
    try:
        rows = parse_contract_deliveries(
            path.read_text(encoding="utf-8"),
            source_system=source,
            source_reference=f"{source.lower()}:{path.name}",
            now_utc=datetime.now(UTC),
        )
    except DeliveryImportError as exc:
        print(f"Refused: {exc}")
        return 2
    contracts = sorted({row["contract_id"] for row in rows})
    print(f"{len(rows)} gas days for {len(contracts)} contracts")
    if args.dry_run:
        return 0
    database_url = resolve_database_url()
    if not database_url:
        print("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2
    print(f"Runtime DB: {redact_database_url(database_url)}")
    from eurogas_nexus.db.models import ContractDeliveryRecord, UpstreamResourceContractRecord

    with get_session_factory()() as session:
        known = {
            contract_id
            for (contract_id,) in session.query(UpstreamResourceContractRecord.contract_id)
            .filter(UpstreamResourceContractRecord.contract_id.in_(contracts))
            .all()
        }
        unknown = [contract_id for contract_id in contracts if contract_id not in known]
        if unknown:
            print(f"Refused: unknown contracts {unknown[:10]}")
            return 2
        for row in rows:
            session.merge(ContractDeliveryRecord(**row))
        session.commit()
    print("Loaded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
