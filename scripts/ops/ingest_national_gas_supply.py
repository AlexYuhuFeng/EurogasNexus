"""Ingest Great Britain storage and LNG from the National Gas data portal.

    python scripts/ops/ingest_national_gas_supply.py --days 7 --commit
    python scripts/ops/ingest_national_gas_supply.py --days 30 --end 2026-10-13 --commit

Loads N completed gas days ending yesterday (or ending ``--end``, for a back-fill in
30-day steps): storage stock, withdrawal and injection,
LNG tank stock and send-out, in TWh. No key is needed. GIE AGSI/ALSI carry GB rows
with no values; this is the GB side of the NW Europe storage and LNG balance. A later
run replaces a provisional (nomination) value with the D+2 allocation and fills in
stock published after the first run. See docs/operations/GB_GAS_SUPPLY.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--days", type=int, default=7, help="completed gas days ending yesterday (1..30)"
    )
    parser.add_argument(
        "--end", type=_iso_day, default=None,
        help="last gas day to load, YYYY-MM-DD (default: yesterday; must be before today)",
    )
    parser.add_argument("--commit", action="store_true", help="write to the runtime database")
    parser.add_argument("--json", action="store_true", help="print a JSON report (scheduler)")
    args = parser.parse_args(argv)
    say = (lambda text: print(text, file=sys.stderr)) if args.json else print
    if not 1 <= args.days <= 30:
        parser.error("--days must be 1..30")

    from eurogas_nexus.ingestion.national_gas_supply import fetch_national_gas_supply

    today = datetime.now(UTC).date()
    last = args.end or today - timedelta(days=1)
    if last >= today:
        parser.error("--end must be a completed gas day (before today)")
    first = last - timedelta(days=args.days - 1)
    storage_rows: list[dict] = []
    lng_rows: list[dict] = []
    failures = []
    try:
        download = fetch_national_gas_supply(first, last)
        storage_rows, lng_rows = download.storage_rows, download.lng_rows
    except (OSError, ValueError) as exc:
        failures.append({"source": "national-gas:supply", "code": getattr(exc, "code", None)
                         or type(exc).__name__})
        say(f"national-gas:supply: {type(exc).__name__}: {str(exc)[:160]}")

    for row in storage_rows:
        day = row["metadata_json"]["gas_day"]
        say(f"GB storage {day}  stock {_fmt(row['inventory_twh'])} TWh  "
            f"withdrawal {_fmt(row['withdrawal_twh_d'], 1000)} GWh  "
            f"injection {_fmt(row['injection_twh_d'], 1000)} GWh  "
            f"{_basis(row)}")
    for row in lng_rows:
        day = row["metadata_json"]["gas_day"]
        say(f"GB LNG     {day}  stock {_fmt(row['inventory_twh'])} TWh  "
            f"send-out {_fmt(row['send_out_twh_d'], 1000)} GWh  {_basis(row)}")

    stored = {"storage": 0, "lng": 0}
    if args.commit and (storage_rows or lng_rows):
        from eurogas_nexus.db.models.observation import (
            LngObservationRecord,
            StorageObservationRecord,
        )
        from eurogas_nexus.db.repositories.public_ingestion_upsert import (
            upsert_observation_rows,
        )
        from eurogas_nexus.db.session import get_session_factory

        # Insert-or-update by observation_id: a provisional nomination is replaced by the
        # allocation, and a stock published later fills in. observed_at_utc keeps the
        # first-seen instant.
        with get_session_factory()() as session:
            stored["storage"] = upsert_observation_rows(
                session, StorageObservationRecord, storage_rows
            )
            stored["lng"] = upsert_observation_rows(session, LngObservationRecord, lng_rows)
            session.commit()
        say(f"stored: {stored}")
    elif not args.commit:
        say(f"{len(storage_rows) + len(lng_rows)} rows parsed; dry run (add --commit to store)")
    records = len(storage_rows) + len(lng_rows)
    provisional = sum(
        1 for row in (*storage_rows, *lng_rows) if row["metadata_json"]["provisional"]
    )
    ok = bool(records) and not failures
    if args.json:
        print(json.dumps({"ok": ok, "failures": failures, "sources": {"national-gas-supply": {
            "records": records, "provisional": provisional, **stored}}}))
    return 0 if ok else 1


def _iso_day(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError("expected YYYY-MM-DD") from None


def _fmt(value: float | None, scale: float = 1.0) -> str:
    return "     -" if value is None else f"{value * scale:8.3f}"


def _basis(row: dict) -> str:
    basis = row["metadata_json"]["basis"]
    return ", ".join(f"{name}={kind}" for name, kind in sorted(basis.items()))


if __name__ == "__main__":
    raise SystemExit(main())
