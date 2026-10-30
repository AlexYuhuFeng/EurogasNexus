"""Ingest overnight benchmark fixings (SONIA, €STR, SOFR) from their administrators.

Public, free sources (commercial use permitted with attribution, see
``docs/operations/INTEREST_RATES.md``):

- SONIA: Bank of England Interactive Database, series ``IUDSOIA`` (CSV);
- €STR: ECB Data Portal, series ``EST/B.EU000A2X2A25.WT`` (CSV);
- SOFR: Federal Reserve Bank of New York Markets API (JSON).

Fixings are upserted by (benchmark, value date). A published correction replaces the
stored value and is reported. The script is operator-invoked or scheduled once a
business day after 09:00 London.

    python scripts/ops/ingest_interest_rates.py --days 30
    python scripts/ops/ingest_interest_rates.py --benchmark SONIA --file sonia.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx

from eurogas_nexus.db.session import (
    get_session_factory,
    redact_database_url,
    resolve_database_url,
)
from eurogas_nexus.domain.market.interest_rates import (
    BENCHMARKS,
    InterestRateError,
    RateFixing,
    parse_boe_sonia_csv,
    parse_ecb_estr_csv,
    parse_nyfed_sofr_json,
)

MAX_PAYLOAD_BYTES = 4 * 1024 * 1024
PARSERS = {"SONIA": parse_boe_sonia_csv, "ESTR": parse_ecb_estr_csv, "SOFR": parse_nyfed_sofr_json}


def source_url(benchmark_id: str, start: date, end: date) -> str:
    """Official public endpoint for one benchmark and date range."""

    if benchmark_id == "SONIA":
        return (
            "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"
            f"?csv.x=yes&Datefrom={start.strftime('%d/%b/%Y')}&Dateto={end.strftime('%d/%b/%Y')}"
            "&SeriesCodes=IUDSOIA&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N"
        )
    if benchmark_id == "ESTR":
        return (
            "https://data-api.ecb.europa.eu/service/data/EST/B.EU000A2X2A25.WT"
            f"?format=csvdata&startPeriod={start.isoformat()}&endPeriod={end.isoformat()}"
        )
    return (
        "https://markets.newyorkfed.org/api/rates/secured/sofr/search.json"
        f"?startDate={start.isoformat()}&endDate={end.isoformat()}"
    )


def fetch(client: httpx.Client, benchmark_id: str, start: date, end: date) -> list[RateFixing]:
    """Fetch and parse one benchmark's fixings."""

    response = client.get(source_url(benchmark_id, start, end))
    response.raise_for_status()
    if len(response.content) > MAX_PAYLOAD_BYTES:
        raise InterestRateError(f"{benchmark_id} payload exceeds {MAX_PAYLOAD_BYTES} bytes")
    return PARSERS[benchmark_id](response.text)


def upsert(session, fixings: list[RateFixing], *, now: datetime) -> tuple[int, int]:
    """Insert new fixings and apply published corrections; returns (inserted, corrected)."""

    from eurogas_nexus.db.models import InterestRateObservationRecord

    inserted = corrected = 0
    for fixing in fixings:
        record = fixing.as_record()
        existing = session.get(InterestRateObservationRecord, record["observation_id"])
        if existing is None:
            session.add(InterestRateObservationRecord(**record, ingested_at_utc=now))
            inserted += 1
        elif abs(existing.rate_pct - fixing.rate_pct) > 1e-9:
            existing.rate_pct = fixing.rate_pct
            existing.ingested_at_utc = now
            corrected += 1
    return inserted, corrected


def main(argv: list[str] | None = None) -> int:
    """Run the ingest; returns a process exit code."""

    args = _parse_args(argv)
    # With --json, progress goes to stderr and stdout carries only the scheduler's report.
    say = (lambda text: print(text, file=sys.stderr)) if args.json else print
    database_url = resolve_database_url()
    if not database_url:
        say("Runtime DB URL missing. Set RUNTIME_STORE_DATABASE_URL or DATABASE_URL.")
        return 2
    say(f"Runtime DB: {redact_database_url(database_url)}")
    end = date.today()
    start = end - timedelta(days=args.days)
    selected = [args.benchmark] if args.benchmark else list(BENCHMARKS)
    now = datetime.now(UTC)
    failures = 0
    report: dict[str, dict[str, int]] = {}
    with get_session_factory(database_url=database_url)() as session:
        with httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "EurogasNexus interest-rate-ingest"},
        ) as client:
            for benchmark_id in selected:
                try:
                    if args.file:
                        fixings = PARSERS[benchmark_id](Path(args.file).read_text("utf-8"))
                    else:
                        fixings = fetch(client, benchmark_id, start, end)
                except (httpx.HTTPError, InterestRateError, OSError) as exc:
                    failures += 1
                    say(f"{benchmark_id}: failed ({exc.__class__.__name__}: {exc})")
                    continue
                inserted, corrected = upsert(session, fixings, now=now)
                report[benchmark_id] = {
                    "records": len(fixings),
                    "inserted": inserted,
                    "corrected": corrected,
                    "unchanged": len(fixings) - inserted - corrected,
                }
                say(
                    f"{benchmark_id}: {len(fixings)} fixings "
                    f"{fixings[0].value_date}..{fixings[-1].value_date}, "
                    f"{inserted} new, {corrected} corrected"
                )
        session.commit()
    if args.json:
        print(json.dumps({"ok": not failures and bool(report), "sources": report}, sort_keys=True))
    return 1 if failures else 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--benchmark", choices=sorted(BENCHMARKS), default=None)
    parser.add_argument("--days", type=int, default=30, help="look-back window in days")
    parser.add_argument("--file", default=None, help="parse a saved payload instead of fetching")
    parser.add_argument("--json", action="store_true", help="print a JSON report (scheduler)")
    args = parser.parse_args(argv)
    if args.file and not args.benchmark:
        parser.error("--file requires --benchmark")
    if not 1 <= args.days <= 3660:
        parser.error("--days must be 1..3660")
    return args


if __name__ == "__main__":
    raise SystemExit(main())
