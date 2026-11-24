"""Prices, FX and observations as known at an earlier instant (DATA-1, lesson P1).

A read "as of T" answers with what this installation knew at ``T``: the value that was
current then, the revision it was, when the source published it and when this store first
held that revision. Without ``as_of`` every read is unchanged.

Where the earlier values live
-----------------------------
Settlements, daily closes and FX fixings are stored in place (``market_observations``,
``fx_observations``): an importer that receives a corrected figure overwrites the row. The
outbox already keeps every figure it was told about, though: change capture (M5) publishes
one ``price.updated`` or ``fx.updated`` event per figure with the value in its payload, and a
changed figure is revision ``n + 1`` of the same event, never an overwrite
(``market_events`` is append-only). So the revision history of a settlement *is* its event
chain, and no new table is needed:

- a figure is **known from** the ingestion time of its first revision;
- **as of T** it reads the payload of the newest revision ingested at or before ``T``
  (its ``revision``, ``published_at_utc`` and ``ingested_at_utc`` as ``known_from_utc``);
- a figure whose first revision was ingested after ``T`` was not known at ``T`` and is left
  out, even when its trade day is earlier;
- a row with no event chain (stored before M5, or never captured: no hub or no canonical
  period) falls back to the stored row, known from its observation instant, with
  ``revision`` ``None`` and ``revision_basis`` ``stored_row``; an overwrite of such a row
  before M5 left no trace, and the answer says so rather than inventing a revision.

Live ticks (``market_quotes``) are never revised: each tick is its own row, known from its
receipt (``received_at_utc``), revision 1. Firm marks are versioned by supersession
(``firm_marks``): the mark in force at ``T`` and its position among the marks entered for its
hub and period. Physical observations keep their own history (``observation_revisions``,
``docs/operations/DATA_REVISIONS.md``) and are read as of through that, unchanged here.

DATA-1：按“某一时刻已知”读取价格、汇率与观测（修订号、发布时间、首次入库时间）。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

#: Basis of a version: the outbox event chain, the stored row (no chain), a tick, a mark.
BASIS_EVENT = "market_event"
BASIS_ROW = "stored_row"
BASIS_TICK = "tick"
BASIS_MARK = "firm_mark_entry"
#: The current row differs from the newest event (a correction stored, capture not yet run).
BASIS_PENDING = "capture_pending"

#: How far an ``as_of`` may run ahead of the server clock (client clocks are not ours).
AS_OF_SKEW = timedelta(minutes=5)

_CHUNK = 500


class AsOfError(ValueError):
    """An ``as_of`` that cannot be read; ``code`` is the API error code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _iso(value: datetime | None) -> str | None:
    value = _aware(value)
    return None if value is None else value.isoformat()


def parse_as_of(text: str | None, *, now: datetime | None = None) -> datetime | None:
    """``as_of`` as an aware UTC instant, or ``None`` when not given.

    ISO 8601 with ``Z`` or an offset; a time without one is read as UTC, a bare date as its
    00:00 UTC. Refused (:class:`AsOfError`): text that is not a time (``as_of_invalid``) and
    an instant later than the server clock plus five minutes (``as_of_in_future``): nobody
    knew anything then yet.
    """

    if text is None or not str(text).strip():
        return None
    raw = str(text).strip()
    try:
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        raise AsOfError(
            "as_of_invalid", "as_of must be an ISO 8601 instant, e.g. 2026-11-20T17:30:00Z"
        ) from None
    moment = _aware(moment)
    clock = _aware(now) or datetime.now(UTC)
    if moment > clock + AS_OF_SKEW:
        raise AsOfError("as_of_in_future", "as_of is later than the server clock")
    return moment


@dataclass(frozen=True)
class KnownVersion:
    """One figure as known at an instant.

    ``values`` are the figure's fields as that revision stated them (``price``, ``unit``,
    ``currency`` for a settlement; ``rate`` for a fixing); empty for the stored-row basis,
    whose values are the row's.
    """

    revision: int | None
    published_at_utc: datetime | None
    known_from_utc: datetime | None
    basis: str
    event_id: str | None = None
    values: dict[str, Any] = field(default_factory=dict)

    def as_fields(self) -> dict[str, Any]:
        """The version as additive row fields."""

        return {
            "revision": self.revision,
            "revision_basis": self.basis,
            "published_at_utc": _iso(self.published_at_utc),
            "known_from_utc": _iso(self.known_from_utc),
            "revision_event_id": self.event_id,
        }


#: A figure that was not known at the instant asked.
NOT_KNOWN = None


def _event_chains(session, keys: Iterable[str]) -> dict[str, list[Any]]:
    """Every revision of each event key, oldest first (one query per 500 keys)."""

    from eurogas_nexus.db.models import MarketEventRecord

    e = MarketEventRecord
    wanted = sorted({key for key in keys if key})
    chains: dict[str, list[Any]] = {}
    for start in range(0, len(wanted), _CHUNK):
        rows = (
            session.query(
                e.event_key,
                e.revision,
                e.event_id,
                e.ingested_at_utc,
                e.published_at_utc,
                e.payload_json,
            )
            .filter(e.event_key.in_(wanted[start : start + _CHUNK]))
            .all()
        )
        for row in rows:
            chains.setdefault(row.event_key, []).append(row)
    for chain in chains.values():
        chain.sort(key=lambda item: item.revision)
    return chains


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(Decimal(str(value)))
    except (InvalidOperation, ValueError):
        return None


def _versions(
    session,
    keyed: dict[str, str | None],
    *,
    as_of: datetime | None,
    fallback_from: dict[str, datetime | None],
    values_of,
) -> dict[str, KnownVersion | None]:
    """Each reference's version as known at ``as_of`` (``None``: the newest known now).

    ``keyed`` maps a row reference to its event key (``None``: the row makes no event);
    ``fallback_from`` gives the row's own first-known instant for the stored-row basis.
    """

    chains = _event_chains(session, (key for key in keyed.values() if key))
    out: dict[str, KnownVersion | None] = {}
    for reference, key in keyed.items():
        chain = chains.get(key or "", [])
        if not chain:
            out[reference] = KnownVersion(
                revision=None,
                published_at_utc=None,
                known_from_utc=_aware(fallback_from.get(reference)),
                basis=BASIS_ROW,
            )
            continue
        known = (
            chain
            if as_of is None
            else [item for item in chain if _aware(item.ingested_at_utc) <= as_of]
        )
        if not known:
            out[reference] = NOT_KNOWN
            continue
        latest = known[-1]
        out[reference] = KnownVersion(
            revision=int(latest.revision),
            published_at_utc=_aware(latest.published_at_utc),
            known_from_utc=_aware(latest.ingested_at_utc),
            basis=BASIS_EVENT,
            event_id=latest.event_id,
            values=values_of(latest.payload_json or {}),
        )
    return out


def _settlement_key(row) -> str | None:
    from eurogas_nexus.application.market_event_capture import settlement_event
    from eurogas_nexus.domain.market_events import MarketEventError

    observed = _aware(row.observed_at_utc)
    try:
        event = settlement_event(row, ingested_at_utc=observed)
    except MarketEventError:
        return None
    return None if event is None else event.event_key


def _fx_key(row) -> str | None:
    from eurogas_nexus.application.market_event_capture import fx_event
    from eurogas_nexus.domain.market_events import MarketEventError

    observed = _aware(row.observed_at_utc) or datetime.now(UTC)
    try:
        event = fx_event(row, ingested_at_utc=observed)
    except MarketEventError:
        return None
    return None if event is None else event.event_key


def settlement_versions(
    session, rows: Sequence[Any], *, as_of: datetime | None
) -> dict[str, KnownVersion | None]:
    """Each settlement or close row's version as known at ``as_of`` (by observation id)."""

    keyed = {str(row.observation_id): _settlement_key(row) for row in rows}
    return _versions(
        session,
        keyed,
        as_of=as_of,
        fallback_from={str(row.observation_id): row.observed_at_utc for row in rows},
        values_of=lambda payload: {
            "price": _number(payload.get("price")),
            "unit": payload.get("unit"),
            "currency": payload.get("currency"),
        },
    )


def fx_versions(
    session, rows: Sequence[Any], *, as_of: datetime | None
) -> dict[str, KnownVersion | None]:
    """Each FX fixing row's version as known at ``as_of`` (by observation id)."""

    keyed = {str(row.observation_id): _fx_key(row) for row in rows}
    return _versions(
        session,
        keyed,
        as_of=as_of,
        fallback_from={str(row.observation_id): row.observed_at_utc for row in rows},
        values_of=lambda payload: {
            "rate": _number(payload.get("rate")),
            "rate_type": payload.get("rate_type"),
        },
    )


def _bound(session, moment: datetime) -> datetime:
    return moment.replace(tzinfo=None) if session.get_bind().dialect.name == "sqlite" else moment


def market_observations_as_of(session, as_of: datetime) -> list[dict[str, Any]]:
    """``/api/market/observations`` as known at ``as_of``, newest first; callers filter.

    Each row is the API row with the price, unit and currency of the revision current at
    ``as_of`` and the version fields (``revision``, ``revision_basis``, ``published_at_utc``,
    ``known_from_utc``, ``revision_event_id``) plus ``as_of_utc``. Two stored rows of one
    figure (the same hub, period, venue and trade day) read as one: the newer row.
    """

    from eurogas_nexus.application.projections.market_reads import market_observation_row
    from eurogas_nexus.db.models import MarketObservationRecord

    o = MarketObservationRecord
    records = (
        session.query(o)
        .filter(o.observed_at_utc <= _bound(session, as_of))
        .order_by(o.observed_at_utc.desc(), o.market_venue, o.product)
        .all()
    )
    versions = settlement_versions(session, records, as_of=as_of)
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for record in records:
        version = versions.get(str(record.observation_id))
        if version is None:
            continue  # first known after as_of
        if version.event_id:
            chain = version.event_id.rsplit("-r", 1)[0]
            if chain in seen:
                continue
            seen.add(chain)
        row = market_observation_row(record)
        for name, value in version.values.items():
            if value is not None:
                row[name] = value
        row.update(version.as_fields())
        row["as_of_utc"] = as_of.isoformat()
        out.append(row)
    return out


def fx_observations_as_of(session, as_of: datetime) -> list[dict[str, Any]]:
    """``/api/market/fx`` (the ``fx_observations`` table) as known at ``as_of``."""

    from eurogas_nexus.application.projections.market_reads import fx_observation_row
    from eurogas_nexus.db.models import FxObservationRecord

    f = FxObservationRecord
    records = (
        session.query(f)
        .filter(f.observed_at_utc <= _bound(session, as_of))
        .order_by(f.observed_at_utc.desc(), f.pair)
        .all()
    )
    versions = fx_versions(session, records, as_of=as_of)
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for record in records:
        version = versions.get(str(record.observation_id))
        if version is None:
            continue
        if version.event_id:
            chain = version.event_id.rsplit("-r", 1)[0]
            if chain in seen:
                continue
            seen.add(chain)
        row = fx_observation_row(record)
        for name, value in version.values.items():
            if value is not None:
                row[name] = value
        row.update(version.as_fields())
        row["as_of_utc"] = as_of.isoformat()
        out.append(row)
    return out


def tick_version(record) -> KnownVersion:
    """A tick: never revised, published when observed, known from its receipt."""

    return KnownVersion(
        revision=1,
        published_at_utc=_aware(record.observed_at_utc),
        known_from_utc=_aware(getattr(record, "received_at_utc", None))
        or _aware(record.observed_at_utc),
        basis=BASIS_TICK,
    )


def firm_mark_version(session, mark_id: str) -> KnownVersion | None:
    """A firm mark: its position among the marks entered for its hub and period."""

    from eurogas_nexus.db.models import FirmMarkRecord

    mark = session.get(FirmMarkRecord, mark_id)
    if mark is None:
        return None
    position = (
        session.query(FirmMarkRecord)
        .filter(FirmMarkRecord.hub == mark.hub)
        .filter(FirmMarkRecord.period_label == mark.period_label)
        .filter(FirmMarkRecord.entered_at_utc <= mark.entered_at_utc)
        .count()
    )
    return KnownVersion(
        revision=position,
        published_at_utc=_aware(mark.entered_at_utc),
        known_from_utc=_aware(mark.entered_at_utc),
        basis=BASIS_MARK,
    )


__all__ = [
    "AS_OF_SKEW",
    "BASIS_EVENT",
    "BASIS_MARK",
    "BASIS_PENDING",
    "BASIS_ROW",
    "BASIS_TICK",
    "AsOfError",
    "KnownVersion",
    "firm_mark_version",
    "fx_observations_as_of",
    "fx_versions",
    "market_observations_as_of",
    "parse_as_of",
    "settlement_versions",
    "tick_version",
]
