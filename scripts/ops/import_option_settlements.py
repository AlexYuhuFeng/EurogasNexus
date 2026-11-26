"""Import end-of-day gas option settlements from a licensed exchange or vendor export.

    python scripts/ops/import_option_settlements.py --source ICE_ENDEX --file ttf.csv --dry-run
    python scripts/ops/import_option_settlements.py --source EEX --file eex_options.csv

Option settlements are licensed market data (ICE Report Center, EEX Group DataSource, CME
DataMine); export the file your firm is entitled to and import it here. See
``eurogas_nexus.ingestion.option_settlements`` for the columns and
``docs/data/GAS_OPTION_SETTLEMENTS.md`` for the licence situation, precedence and how the
implied volatility is solved. Rows are upserted by (source, hub, contract, trade date,
strike, call/put) and served only to users whose data scopes include the source family.

Without an ``underlying`` column the futures settlement already stored for the same source,
hub, contract and day is used (``scripts/ops/import_settlements.py``), else put-call parity.
Premium-paid options are discounted with the stored €STR / SONIA / SOFR fixing.
"""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime
from pathlib import Path

from eurogas_nexus.db.session import get_session_factory, redact_database_url, resolve_database_url
from eurogas_nexus.ingestion.option_settlements import (
    OPTION_SETTLEMENT_SOURCES,
    OptionSettlementImportError,
    parse_option_settlements,
)

MAX_EXPORT_BYTES = 64 * 1024 * 1024


def stored_underlyings(session, source_system: str) -> dict[tuple[str, str, date], float]:
    """Futures settlements this source already imported, in each hub's native unit."""

    from eurogas_nexus.db.models import MarketObservationRecord
    from eurogas_nexus.domain.market.units import (
        HUB_NATIVE_PRICE_UNIT,
        UnitConversionError,
        convert_price,
    )

    out: dict[tuple[str, str, date], float] = {}
    rows = (
        session.query(MarketObservationRecord)
        .filter(MarketObservationRecord.source_system == source_system)
        .filter(MarketObservationRecord.freshness == "end_of_day")
        .limit(500_000)
        .all()
    )
    for row in rows:
        metadata = row.metadata_json or {}
        hub = str(metadata.get("hub") or "")
        if not metadata.get("settlement") or hub not in HUB_NATIVE_PRICE_UNIT:
            continue
        label = row.product.split(" ", 1)[1] if " " in row.product else ""
        try:
            price = convert_price(float(row.price), row.unit, HUB_NATIVE_PRICE_UNIT[hub])
        except UnitConversionError:
            continue
        out[(hub, label, row.observed_at_utc.date())] = price
    return out


def rate_lookup(session):
    """``(currency, day) -> (ACT/365F %, reference)`` from stored overnight fixings."""

    from eurogas_nexus.db.models import InterestRateObservationRecord
    from eurogas_nexus.domain.market.interest_rates import (
        DEFAULT_BENCHMARK_FOR_CURRENCY,
        InterestRateError,
        resolve_financing_rate,
    )

    fixings = [
        {
            "benchmark_id": row.benchmark_id,
            "value_date": row.value_date,
            "rate_pct": row.rate_pct,
            "source_system": row.source_system,
            "source_reference": row.source_reference,
        }
        for row in session.query(InterestRateObservationRecord).all()
    ]

    def lookup(currency: str, day: date):
        benchmark = DEFAULT_BENCHMARK_FOR_CURRENCY.get(currency.upper())
        if benchmark is None:
            return None
        try:
            rate = resolve_financing_rate(fixings, benchmark, as_of=day)
        except InterestRateError:
            return None
        return rate.all_in_act365_pct, f"{benchmark} {rate.fixing_date.isoformat()}"

    return lookup


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--source", required=True, choices=sorted(OPTION_SETTLEMENT_SOURCES))
    parser.add_argument("--file", required=True)
    parser.add_argument("--source-reference", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    path = Path(args.file)
    if not path.is_file() or path.stat().st_size > MAX_EXPORT_BYTES:
        print(f"Export file missing or larger than {MAX_EXPORT_BYTES} bytes: {path}")
        return 2
    text = path.read_text(encoding="utf-8")
    reference = args.source_reference or f"operator-export:{path.name}"
    database_url = resolve_database_url()
    session_factory = get_session_factory(database_url=database_url) if database_url else None
    if session_factory is None and not args.dry_run:
        print("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2
    try:
        if session_factory is None:
            result = parse_option_settlements(
                text, source_system=args.source, source_reference=reference
            )
        else:
            print(f"Runtime DB: {redact_database_url(database_url)}")
            with session_factory() as session:
                result = parse_option_settlements(
                    text,
                    source_system=args.source,
                    source_reference=reference,
                    underlying_prices=stored_underlyings(session, args.source),
                    discount_rate=rate_lookup(session),
                )
    except OptionSettlementImportError as exc:
        print(f"Refused: {exc}")
        return 2
    print(
        f"{len(result.rows)} option settlements, hubs={result.hubs}, contracts={result.contracts}, "
        f"{result.first_day}..{result.last_day}; implied vol for {result.solved}, none for "
        f"{sum(result.unsolved.values())} {result.unsolved or ''}".rstrip()
    )
    for warning in result.warnings:
        print(f"Warning: {warning}")
    if args.dry_run:
        return 0
    from eurogas_nexus.db.models import IngestionRunRecord, OptionSettlementRecord

    now = datetime.now(UTC)
    with session_factory() as session:
        for row in result.rows:
            session.merge(OptionSettlementRecord(**row))
        session.merge(
            IngestionRunRecord(
                run_id=f"options-{args.source.lower()}-{now:%Y%m%dT%H%M%S}",
                source_name=args.source,
                status="succeeded",
                started_at_utc=now,
                finished_at_utc=now,
                notes=(
                    f"records={len(result.rows)}; source={args.source}; option_settlements; "
                    f"file={path.name}"
                ),
            )
        )
        session.commit()
    print(f"Stored {len(result.rows)} {args.source} option settlements.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
