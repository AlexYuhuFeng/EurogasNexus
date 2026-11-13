"""Reading flow, capacity, storage and LNG observations as they were known at a time.

The observation tables hold each provider value's latest version; every version it replaced
is in ``observation_revisions`` (written by ``public_ingestion_upsert`` under a
``RevisionPolicy``). A version was the known value from its receipt until the receipt of
the next one:

- the current row: from ``revised_at_utc`` (or ``observed_at_utc`` if never revised);
- a revision record: from ``prior_received_at_utc`` until ``superseded_at_utc``.

An as-of read at ``T`` therefore takes rows first received at or before ``T`` and, for a
row revised after ``T``, the revision record whose interval contains ``T``. Nothing here
writes.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from sqlalchemy import DateTime, select

_CHUNK = 500


def _utc(value: Any) -> datetime | None:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def value_received_at(record: Any) -> datetime | None:
    """When the value a row (or a historical version) carries was received."""

    return _utc(getattr(record, "revised_at_utc", None)) or _utc(
        getattr(record, "observed_at_utc", None)
    )


def revisions_by_observation(
    session: Any, table_name: str, observation_ids: Iterable[str]
) -> dict[str, list[Any]]:
    """Revision records per observation id, oldest first."""

    from eurogas_nexus.db.models.observation import ObservationRevisionRecord as Revision

    ids = sorted({str(item) for item in observation_ids})
    found: dict[str, list[Any]] = defaultdict(list)
    for start in range(0, len(ids), _CHUNK):
        rows = session.execute(
            select(Revision)
            .where(Revision.observation_table == table_name)
            .where(Revision.observation_id.in_(ids[start : start + _CHUNK]))
            .order_by(Revision.observation_id, Revision.superseded_at_utc)
        ).scalars()
        for row in rows:
            found[row.observation_id].append(row)
    return dict(found)


def historical_version(record: Any, revision: Any) -> SimpleNamespace:
    """The version a revision record superseded, shaped like the observation row.

    Timestamps come back as aware datetimes. ``observed_at_utc`` stays the row's first
    receipt and ``revised_at_utc`` is this version's own receipt when it was itself a
    revision, so :func:`value_received_at` works on it as on a row.
    """

    table = record.__table__
    values: dict[str, Any] = {}
    prior = revision.prior_row_json or {}
    for column in table.columns:
        value = prior.get(column.name)
        if isinstance(column.type, DateTime):
            value = _utc(value)
        values[column.name] = value
    first = _utc(getattr(record, "observed_at_utc", None))
    received = _utc(revision.prior_received_at_utc)
    values["observed_at_utc"] = first
    values["revised_at_utc"] = received if received and first and received > first else None
    values["__table__"] = table
    values["superseded_at_utc"] = _utc(revision.superseded_at_utc)
    return SimpleNamespace(**values)


def versions_as_of(session: Any, records: Sequence[Any], as_of: datetime) -> list[Any]:
    """Each row as it was known at ``as_of``, in input order.

    Rows first received after ``as_of`` are dropped. A row whose current value arrived
    after ``as_of`` is replaced by the historical version known then; the current ORM
    object is returned unchanged otherwise.
    """

    cutoff = _utc(as_of)
    if cutoff is None:
        raise ValueError("as_of must be a datetime")
    known = [row for row in records if (_utc(row.observed_at_utc) or cutoff) <= cutoff]
    late = [row for row in known if (value_received_at(row) or cutoff) > cutoff]
    if not late:
        return known
    history: dict[str, list[Any]] = {}
    by_table: dict[str, list[Any]] = defaultdict(list)
    for row in late:
        by_table[row.__table__.name].append(row)
    for table_name, rows in by_table.items():
        for key, items in revisions_by_observation(
            session, table_name, (row.observation_id for row in rows)
        ).items():
            history[f"{table_name}|{key}"] = items
    late_ids = {id(row) for row in late}
    result = []
    for row in known:
        if id(row) not in late_ids:
            result.append(row)
            continue
        for revision in history.get(f"{row.__table__.name}|{row.observation_id}", []):
            start = _utc(revision.prior_received_at_utc)
            end = _utc(revision.superseded_at_utc)
            if start is not None and end is not None and start <= cutoff < end:
                result.append(historical_version(row, revision))
                break
    return result


def all_versions(session: Any, records: Sequence[Any]) -> list[Any]:
    """Every version of each row, oldest first, the current row last.

    For point-in-time research: each version carries its own receipt
    (:func:`value_received_at`), so a builder can take the one known at each origin.
    """

    by_table: dict[str, list[Any]] = defaultdict(list)
    for row in records:
        if getattr(row, "revised_at_utc", None) is not None:
            by_table[row.__table__.name].append(row)
    if not by_table:
        return list(records)
    history: dict[str, list[Any]] = {}
    for table_name, rows in by_table.items():
        for key, items in revisions_by_observation(
            session, table_name, (row.observation_id for row in rows)
        ).items():
            history[f"{table_name}|{key}"] = items
    result: list[Any] = []
    for row in records:
        if getattr(row, "revised_at_utc", None) is not None:
            for revision in history.get(f"{row.__table__.name}|{row.observation_id}", []):
                result.append(historical_version(row, revision))
        result.append(row)
    return result
