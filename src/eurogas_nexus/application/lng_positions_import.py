"""Store a vessel-feed or ETRM export of LNG cargoes or regas slots (QA-L-04).

An export says what its source knows. A vessel feed (Kpler, Spire, MarineTraffic) knows the
ship: position, track, ETA, destination. The ETRM knows the firm's side: the book, the
energy, the terminal. So an import updates a stored cargo or slot only in the fields its
file supplies, and a column the file leaves out, or a cell it leaves blank, keeps the stored
value: a Kpler update without ``book_id`` must not take the firm's cargo out of its book
(that left 1.13 TWh of hedges without a cargo). A cargo moves to another book only when a
file names the other book.

Every change to a firm cargo's plan inputs is a ``cargo.changed`` market event through the
outbox (``market_event_capture.capture_desk``), in the import's transaction: a new ETA, a
new book, or a slot that now holds the cargo. An ETA that changes a value another source
set is listed, so the desk sees the feed and the ETRM disagree.

Commit is the caller's.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

#: Identity, not data: never changed by an update.
_KEYS = {"cargo": "cargo_id", "slot": "slot_id"}


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def store_lng_rows(
    session, kind: str, rows: list[dict[str, Any]], *, now_utc: datetime | None = None
) -> dict[str, Any]:
    """Insert new cargoes or slots and update stored ones field by field.

    ``kind`` is ``cargo`` or ``slot``; ``rows`` are what ``ingestion.lng_positions`` parsed,
    where ``None`` means the file did not supply the value. Returns the counts, the ETA
    changes that overwrite another source's ETA, and the cargo events published.
    """

    from eurogas_nexus.application.market_event_capture import capture_desk
    from eurogas_nexus.db.models import LngCargoRecord, RegasSlotRecord

    if kind not in _KEYS:
        raise ValueError(f"kind must be one of {sorted(_KEYS)}")
    model = LngCargoRecord if kind == "cargo" else RegasSlotRecord
    key = _KEYS[kind]
    moment = _aware(now_utc) or datetime.now(UTC)
    created = updated = 0
    eta_disagreements: list[dict[str, Any]] = []
    touched: set[str] = set()  # firm cargoes whose plan inputs this file may change
    for row in rows:
        held = session.get(model, row[key])
        if held is None:
            session.add(model(**row))
            created += 1
            continue
        if kind == "slot" and held.cargo_id:
            touched.add(held.cargo_id)  # a slot given to another cargo changes both plans
        if kind == "cargo":
            before, after = _aware(held.eta_utc), _aware(row.get("eta_utc"))
            if (
                before is not None
                and after is not None
                and before != after
                and held.source_system != row.get("source_system")
            ):
                eta_disagreements.append(
                    {
                        "cargo_id": held.cargo_id,
                        "eta_before_utc": before.isoformat(),
                        "eta_before_source": held.source_system,
                        "eta_utc": after.isoformat(),
                        "source": row.get("source_system"),
                        "hours": round((after - before).total_seconds() / 3600, 1),
                    }
                )
        for name, value in row.items():
            if name == key or value is None:
                continue  # not supplied: the stored value stands
            setattr(held, name, value)
        updated += 1
    cargo_ids = sorted(touched | {row["cargo_id"] for row in rows if row.get("cargo_id")})
    events = capture_desk(session, cargo_ids=cargo_ids, now_utc=moment)
    return {
        "kind": kind,
        "created": created,
        "updated": updated,
        "eta_disagreements": eta_disagreements,
        "events": events,
    }
