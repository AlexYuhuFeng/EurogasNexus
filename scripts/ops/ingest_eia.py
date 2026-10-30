"""Ingest the Henry Hub daily spot price from the EIA open-data API.

    python scripts/ops/ingest_eia.py --days 30            # fetch and store
    python scripts/ops/ingest_eia.py --file eia.json      # a saved response

The key comes from EIA_API_KEY and is never printed. With --json the scheduler's report
goes to stdout and progress to stderr.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from eurogas_nexus.ingestion.eia import (
    MAX_PAYLOAD_BYTES,
    EiaParseError,
    parse_prices,
    request_url,
    resolve_eia_key,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--days", type=int, default=14, help="look-back window")
    parser.add_argument("--file", type=Path, help="parse a saved response")
    parser.add_argument("--json", action="store_true", help="print a JSON report (scheduler)")
    args = parser.parse_args(argv)
    say = (lambda text: print(text, file=sys.stderr)) if args.json else print

    if args.file:
        payload, reference = args.file.read_bytes(), f"file:{args.file.name}"
    else:
        key = resolve_eia_key()
        if not key:
            say("EIA_API_KEY is not set; register free at eia.gov/opendata")
            return 2
        start = date.today() - timedelta(days=args.days)
        reference = f"eia:RNGWHHD:{start.isoformat()}"
        try:
            with urllib.request.urlopen(request_url(key, start), timeout=30) as response:
                payload = response.read(MAX_PAYLOAD_BYTES + 1)
        except OSError as exc:
            # The URL carries the key, so only the reference is reported.
            say(f"{reference}: {type(exc).__name__}")
            return 1
    try:
        prices = parse_prices(payload)
    except EiaParseError as exc:
        say(f"Refused: {exc}")
        return 1

    from eurogas_nexus.db.models import MarketObservationRecord
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if not resolve_database_url():
        say("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2
    inserted = 0
    with get_session_factory()() as session:
        for price in prices:
            record = price.as_record(source_reference=reference)
            if session.get(MarketObservationRecord, record["observation_id"]) is None:
                inserted += 1
            session.merge(MarketObservationRecord(**record))
        session.commit()
    say(f"Henry Hub: {len(prices)} prices, {inserted} new ({datetime.now(UTC):%H:%M} UTC)")
    if args.json:
        report = {
            "ok": bool(prices),
            "sources": {
                "EIA": {
                    "records": len(prices),
                    "inserted": inserted,
                    "unchanged": len(prices) - inserted,
                }
            },
        }
        print(json.dumps(report, sort_keys=True))
    return 0 if prices else 1


if __name__ == "__main__":
    raise SystemExit(main())
