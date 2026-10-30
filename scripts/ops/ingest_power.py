"""Ingest ENTSO-E power data: day-ahead prices, load and generation by fuel.

Usage:
    python scripts/ops/ingest_power.py --zone GB --zone NL --days 7
    python scripts/ops/ingest_power.py --file saved_a44.xml          # a stored document

The token comes from ENTSOE_SECURITY_TOKEN and is never printed. Without --commit the run
parses and reports what it would store.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from eurogas_nexus.ingestion.entsoe_transparency import (
    BIDDING_ZONES,
    EntsoeParseError,
    fetch_document,
    parse_document,
    request_url,
    resolve_entsoe_token,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--zone", action="append", choices=sorted(BIDDING_ZONES))
    parser.add_argument("--days", type=int, default=2, help="window ending now (default 2)")
    parser.add_argument("--documents", default="A44,A65,A75", help="ENTSO-E document types")
    parser.add_argument("--file", action="append", type=Path, help="parse a stored document")
    parser.add_argument("--commit", action="store_true", help="write to the runtime database")
    args = parser.parse_args(argv)

    observations = []
    if args.file:
        for path in args.file:
            observations += parse_document(path.read_bytes(), source_reference=f"file:{path.name}")
    else:
        token = resolve_entsoe_token()
        if not token:
            print("ENTSOE_SECURITY_TOKEN is not set; see docs/operations/POWER_DATA.md")
            return 2
        end = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        start = end - timedelta(days=args.days)
        for zone in args.zone or ["GB", "NL", "DE_LU"]:
            for document in args.documents.split(","):
                url = request_url(token, document.strip(), zone, start, end)
                reference = f"entsoe:{document.strip()}:{zone}:{start:%Y%m%d}-{end:%Y%m%d}"
                try:
                    observations += parse_document(fetch_document(url), source_reference=reference)
                except (OSError, EntsoeParseError) as exc:
                    # The URL carries the token, so only the reference is reported.
                    print(f"{reference}: {type(exc).__name__}: {str(exc)[:200]}")

    by_metric: dict[tuple[str, str], int] = {}
    for item in observations:
        by_metric[(item.zone, item.metric)] = by_metric.get((item.zone, item.metric), 0) + 1
    for (zone, metric), count in sorted(by_metric.items()):
        print(f"{zone:6} {metric:28} {count:6d}")
    if not args.commit:
        print(f"{len(observations)} observations parsed; dry run (add --commit to store)")
        return 0

    from eurogas_nexus.db.repositories.power import upsert_power_observations
    from eurogas_nexus.db.session import get_session_factory

    with get_session_factory()() as session:
        counts = upsert_power_observations(session, observations)
        session.commit()
    print(f"stored: {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
