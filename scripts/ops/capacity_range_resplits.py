"""Count ENTSOG capacity ranges that overlap, and replay the re-split rule over stored reads.

ENTSOG re-splits capacity validity ranges between reads, and the record id holds the period
end, so overlapping ranges of one series are all stored (live, 14 Nov 2026: 539 point/
direction/type/operator/start keys held two or three times). Nothing needs deleting: each
row is what the provider stated when it was received, an as-of read needs it, and every
reader resolves a day to the latest-received covering range
(``application/capacity_resolution``).

What the stored rows lack is the receipt of a range the provider re-published unchanged
after a later read had re-split it: before 2026-11-14 ingestion recorded nothing for an
unchanged row, so such a range keeps its first receipt and loses to the stale split. This
script replays the archived ENTSOG pages (``raw_payload_archives``) in receipt order with
the ingestion rule (``db/repositories/capacity_ranges``) and lists the receipts that rule
would have moved. Dry run by default (counts only, nothing written); ``--commit`` records
each move as ingestion would have: a ``range_resplit`` history record and the row's
``revised_at_utc``. Only moves later than the row's current receipt are applied; a row whose
value was revised after the move is left as it is (counted as ``skipped_revised_later``).

    python scripts/ops/capacity_range_resplits.py            # counts, nothing written
    python scripts/ops/capacity_range_resplits.py --json
    python scripts/ops/capacity_range_resplits.py --commit   # record the moves
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

#: Pages received within this gap of each other belong to one read (one ingestion run).
READ_GAP = timedelta(minutes=10)
#: Gas days compared before and after the moves: around the stored reads.
COMPARE_DAYS = 60


def _utc(value: Any) -> datetime:
    if isinstance(value, str):  # a timestamp read through plain SQL on SQLite
        value = datetime.fromisoformat(value)
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _series(row: dict[str, Any]) -> tuple[str, str, str, str, str]:
    metadata = row.get("metadata_json") or {}
    return (
        str(row.get("source_system") or "").strip().upper(),
        str(row.get("point_id") or ""),
        str(row.get("direction") or "").strip().casefold(),
        str(row.get("capacity_type") or ""),
        str(metadata.get("operatorKey") or ""),
    )


def _stored(session) -> dict[str, dict[str, Any]]:
    from sqlalchemy import select

    from eurogas_nexus.db.models import CapacityObservationRecord

    table = CapacityObservationRecord.__table__
    return {
        str(row["observation_id"]): dict(row)
        for row in session.execute(
            select(table).where(table.c.source_system == "ENTSOG")
        ).mappings()
    }


def overlap_counts(stored: dict[str, dict[str, Any]]) -> dict[str, int]:
    """Same-start keys held more than once, overlapping rows, and rows read nowhere."""

    from eurogas_nexus.application.capacity_resolution import resolve_capacity

    by_key: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    by_series: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for row in stored.values():
        by_key[(*_series(row), _utc(row["period_start_utc"]))].append(row)
        by_series[_series(row)].append(row)
    repeated = [rows for rows in by_key.values() if len(rows) > 1]
    overlapping: set[str] = set()
    for rows in by_series.values():
        for i, a in enumerate(rows):
            for b in rows[i + 1 :]:
                if _utc(a["period_start_utc"]) < _utc(b["period_end_utc"]) and _utc(
                    b["period_start_utc"]
                ) < _utc(a["period_end_utc"]):
                    overlapping.update((a["observation_id"], b["observation_id"]))
    records = [_record(row) for row in stored.values()]
    winners = {item.observation_id for item in resolve_capacity(records)}
    return {
        "rows": len(stored),
        "series": len(by_series),
        "start_keys_held_more_than_once": len(repeated),
        "of_which_values_differ": sum(
            1 for rows in repeated if len({row["original_value"] for row in rows}) > 1
        ),
        "rows_overlapping_another_range": len(overlapping),
        # Rows no instant is read from: superseded by later ranges, or the other operator's
        # copy at a point both operators publish. Kept as history, never deleted.
        "rows_read_nowhere": len(stored) - len(winners & set(stored)),
    }


def _record(row: dict[str, Any], received: datetime | None = None) -> SimpleNamespace:
    from eurogas_nexus.db.models import CapacityObservationRecord

    values = dict(row)
    if received is not None:
        values["revised_at_utc"] = received
    values["__table__"] = CapacityObservationRecord.__table__
    return SimpleNamespace(**values)


def _reads(session) -> list[list[tuple[str, str, datetime, list[dict[str, Any]]]]]:
    """Archived capacity pages, normalised, grouped into reads in receipt order."""

    from sqlalchemy import text

    from eurogas_nexus.ingestion.public_sources import entsog_capacity_observations_from_json

    pages = session.execute(
        text(
            "SELECT archive_id, source_reference, received_at_utc FROM raw_payload_archives "
            "WHERE source_system = 'ENTSOG' AND dataset = 'operationaldatas' "
            "ORDER BY received_at_utc"
        )
    ).all()
    reads: list[list[tuple[str, str, datetime, list[dict[str, Any]]]]] = []
    last: datetime | None = None
    for archive_id, reference, received in pages:
        payload_text = session.execute(
            text("SELECT payload_text FROM raw_payload_archives WHERE archive_id = :a"),
            {"a": archive_id},
        ).scalar()
        if not payload_text:
            continue
        payload = json.loads(payload_text, parse_float=str, parse_int=str)
        received = _utc(received)
        rows = entsog_capacity_observations_from_json(payload, observed_at_utc=received)
        if not rows:
            continue
        if last is None or received - last > READ_GAP:
            reads.append([])
        reads[-1].append((archive_id, str(reference), received, rows))
        last = received
    return reads


def replay(stored: dict[str, dict[str, Any]], reads) -> list[dict[str, Any]]:
    """The receipt moves the ingestion rule makes over the archived reads, in order."""

    receipt: dict[str, datetime] = {}
    value: dict[str, Any] = {}
    series: dict[tuple, set[str]] = defaultdict(set)
    span: dict[str, tuple[datetime, datetime]] = {}
    moves: list[dict[str, Any]] = []
    for read in reads:
        ids_in_read = {row["observation_id"] for *_, rows in read for row in rows}
        for archive_id, reference, received, rows in read:
            for row in rows:
                key = row["observation_id"]
                if key not in receipt:
                    receipt[key], value[key] = received, row["original_value"]
                    series[_series(row)].add(key)
                    span[key] = (_utc(row["period_start_utc"]), _utc(row["period_end_utc"]))
                    continue
                if row["original_value"] != value[key]:
                    receipt[key], value[key] = received, row["original_value"]  # revised
                    continue
                start, end = span[key]
                later = any(
                    other != key
                    and other not in ids_in_read
                    and span[other][0] < end
                    and span[other][1] > start
                    and receipt[other] > receipt[key]
                    for other in series[_series(row)]
                )
                if later:
                    moves.append(
                        {
                            "observation_id": key,
                            "prior_received_at_utc": receipt[key],
                            "superseded_at_utc": received,
                            "archive_id": archive_id,
                            "source_reference": reference,
                        }
                    )
                    receipt[key] = received
    return [move for move in moves if move["observation_id"] in stored]


def changed_days(stored: dict[str, dict[str, Any]], moves: list[dict[str, Any]]) -> int:
    """Series-gas-days whose resolved value the moves change (around the stored reads)."""

    from eurogas_nexus.application.capacity_resolution import resolve_capacity

    latest = {}
    for move in moves:
        latest[move["observation_id"]] = move["superseded_at_utc"]
    if not latest:
        return 0
    before = resolve_capacity([_record(row) for row in stored.values()])
    after = resolve_capacity(
        [_record(row, latest.get(key)) for key, row in stored.items()]
    )
    anchor = max(_utc(row["observed_at_utc"]) for row in stored.values()).replace(
        hour=5, minute=0, second=0, microsecond=0
    )
    days = [anchor + timedelta(days=offset) for offset in range(-COMPARE_DAYS, COMPARE_DAYS)]

    def values(resolved):
        found = {}
        for item in resolved:
            for day in days:
                if item.start <= day < item.end:
                    found[(*_series(vars(item.record)), day)] = item.original_value
        return found

    first, second = values(before), values(after)
    return sum(1 for key in first.keys() | second.keys() if first.get(key) != second.get(key))


def apply(session, stored: dict[str, dict[str, Any]], moves: list[dict[str, Any]]) -> dict:
    """Record each move as ingestion would have (history record, then the new receipt)."""

    from sqlalchemy import update

    from eurogas_nexus.db.models import CapacityObservationRecord
    from eurogas_nexus.db.repositories.public_ingestion_upsert import (
        _append_revision,
        received_at,
    )

    table = CapacityObservationRecord.__table__
    applied = skipped = 0
    for move in sorted(moves, key=lambda item: item["superseded_at_utc"]):
        row = stored[move["observation_id"]]
        current = received_at(row)
        if current is not None and move["superseded_at_utc"] <= current:
            skipped += 1
            continue
        _append_revision(
            session,
            table,
            row,
            {"source_reference": move["source_reference"]},
            reason="range_resplit",
            changed_fields=[],
            prior_received=current,
            superseded_at=move["superseded_at_utc"],
        )
        session.execute(
            update(table)
            .where(table.c.observation_id == move["observation_id"])
            .values(
                revised_at_utc=move["superseded_at_utc"],
                source_reference=move["source_reference"][:128],
            )
        )
        row["revised_at_utc"] = move["superseded_at_utc"]
        row["source_reference"] = move["source_reference"][:128]
        applied += 1
    return {"applied": applied, "skipped_revised_later": skipped}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--commit", action="store_true", help="Record the moves (default: count)")
    parser.add_argument("--json", action="store_true", help="Print the report as JSON")
    args = parser.parse_args(argv)

    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None:
        print(json.dumps({"ok": False, "error": "database_url_missing"}))
        return 2
    with get_session_factory()() as session:
        stored = _stored(session)
        report: dict[str, Any] = {"ok": True, "dry_run": not args.commit}
        report["overlaps"] = overlap_counts(stored)
        reads = _reads(session)
        moves = replay(stored, reads)
        report["replay"] = {
            "archived_reads": len(reads),
            "archived_pages": sum(len(read) for read in reads),
            "receipt_moves": len(moves),
            "rows_moved": len({move["observation_id"] for move in moves}),
            "series_gas_days_changed": changed_days(stored, moves),
        }
        if args.commit:
            report["commit"] = apply(session, stored, moves)
            session.commit()
        else:
            session.rollback()
    if args.json:
        print(json.dumps(report, sort_keys=True, default=str))
    else:
        for section in ("overlaps", "replay", "commit"):
            if section in report:
                print(f"{section}:")
                for name, count in report[section].items():
                    print(f"  {name:34} {count}")
        if not args.commit:
            print("dry run: nothing written (add --commit to record the moves)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
