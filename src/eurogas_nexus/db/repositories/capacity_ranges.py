"""Keep the receipt order of ENTSOG capacity ranges right when the provider re-splits them.

Readers take, for each instant, the covering capacity range received last
(``application/capacity_resolution``). A range that is re-published unchanged keeps its
first receipt (append-or-verify), which is right until the provider goes back to a range it
had re-split: the 12 Nov read holds 13 Nov - 1 Dec, the 13 Nov read 13-14 Nov and
14 Nov - 1 Dec, and a later read 13 Nov - 1 Dec again. Without a new receipt the stale
13-14 Nov range would keep winning 13 Nov.

So when an incoming capacity row is already stored, and a stored range of the same series
that overlaps it was received later and is not in this read, the stored version is
appended to ``observation_revisions`` with reason ``range_resplit`` (no field changed) and
the row takes this receipt (``revised_at_utc``) and lineage. An as-of read before this
receipt still sees the version and the receipt it had then.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from eurogas_nexus.db.repositories.public_ingestion_upsert import (
    _append_revision,
    _replace_current,
    _utc_instant,
    received_at,
)

_CHUNK = 500


def _series(row: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
    metadata = row.get("metadata_json") or {}
    operator = metadata.get("operatorKey") if isinstance(metadata, Mapping) else None
    return (
        str(row.get("source_system") or "").strip().upper(),
        str(row.get("point_id") or ""),
        str(row.get("direction") or "").strip().casefold(),
        str(row.get("capacity_type") or ""),
        str(operator or ""),
    )


def _select(session: Session, statement: Any) -> list[dict[str, Any]]:
    return [dict(row) for row in session.execute(statement).mappings()]


def reconfirm_resplit_ranges(session: Session, rows: Sequence[Mapping[str, Any]]) -> int:
    """Move the receipt of re-published, re-split capacity ranges forward; returns the count.

    Call after the batch has been upserted, in the same transaction. Rows inserted or revised
    by the batch already carry its receipt and are left alone.
    """

    from eurogas_nexus.db.models import CapacityObservationRecord

    table = CapacityObservationRecord.__table__
    incoming = {str(row["observation_id"]): row for row in rows}
    ids = sorted(incoming)
    stored: dict[str, dict[str, Any]] = {}
    for start in range(0, len(ids), _CHUNK):
        for row in _select(
            session, select(table).where(table.c.observation_id.in_(ids[start : start + _CHUNK]))
        ):
            stored[str(row["observation_id"])] = row

    candidates: list[tuple[dict[str, Any], Mapping[str, Any], datetime, datetime]] = []
    for key, row in stored.items():
        prior = received_at(row)
        now = _utc_instant(incoming[key].get("observed_at_utc"))
        if prior is not None and now is not None and prior < now:
            candidates.append((row, incoming[key], prior, now))
    if not candidates:
        return 0

    points = sorted({str(row["point_id"]) for row, *_ in candidates})
    low = min(_utc_instant(row["period_start_utc"]) for row, *_ in candidates)
    high = max(_utc_instant(row["period_end_utc"]) for row, *_ in candidates)
    since = min(prior for _, _, prior, _ in candidates)
    naive = session.get_bind().dialect.name == "sqlite"

    def bound(moment: datetime) -> datetime:
        return moment.replace(tzinfo=None) if naive else moment

    later: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for start in range(0, len(points), _CHUNK):
        statement = (
            select(table)
            .where(table.c.point_id.in_(points[start : start + _CHUNK]))
            .where(table.c.period_end_utc > bound(low))
            .where(table.c.period_start_utc < bound(high))
            .where(func.coalesce(table.c.revised_at_utc, table.c.observed_at_utc) > bound(since))
        )
        for row in _select(session, statement):
            if str(row["observation_id"]) not in incoming:
                later[_series(row)].append(row)

    moved = 0
    for row, new, prior, now in candidates:
        start, end = _utc_instant(row["period_start_utc"]), _utc_instant(row["period_end_utc"])
        superseded = any(
            _utc_instant(other["period_start_utc"]) < end
            and _utc_instant(other["period_end_utc"]) > start
            and (received_at(other) or prior) > prior
            for other in later.get(_series(row), ())
        )
        if not superseded:
            continue
        _append_revision(
            session,
            table,
            row,
            new,
            reason="range_resplit",
            changed_fields=[],
            prior_received=prior,
            superseded_at=now,
        )
        _replace_current(session, table, ["observation_id"], (row["observation_id"],), new, now)
        moved += 1
    return moved
