"""One capacity value per ENTSOG point, direction, capacity type and gas day.

ENTSOG publishes capacity over validity ranges and re-splits them between reads: a value
valid 13 Nov - 1 Dec in the 12 Nov read is 13-14 Nov and 14 Nov - 1 Dec in the 13 Nov read
(live, UGS-00397 firm technical entry: 64.4 GWh/d for the whole range, then 28.1 GWh/d for
13 Nov alone). The provider's record id contains the period end, so each range is its own
row, and on 14 Nov 2026 539 (point, direction, type, operator, start) keys were held two or
three times, 168 of them with different values. A reader that adds capacity per day would
count those days twice.

The rows are all kept (each was the provider's statement when received, and an as-of read
needs them); every reader resolves them here (:data:`CAPACITY_RESOLUTION_RULE`), next to
the flow rules in :mod:`pipeline_supply`. Ingestion keeps the receipt order right when the
provider goes back to a range it had re-split: the re-published range's receipt moves
forward with a ``range_resplit`` history record
(``db/repositories/capacity_ranges.reconfirm_resplit_ranges``).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Any

from eurogas_nexus.application.pipeline_supply import _REGISTRY_OPERATOR, row_operator
from eurogas_nexus.db.repositories.observation_revisions import (
    value_received_at,
    versions_as_of,
)

CAPACITY_RESOLUTION_RULE = (
    "One capacity value per ENTSOG point, direction, capacity type and instant: of the "
    "stored validity ranges covering it, the one whose value was received last (ties: the "
    "later-starting, then the shorter range). A later read that re-splits a range "
    "supersedes the earlier range on the days they share and leaves its other days as they "
    "were. Read as of an earlier time, only versions received by then compete. Where more "
    "than one operator publishes capacity at a point, one operator is read per point, as "
    "for flows: the operator the landing registry names, else the operator chosen for the "
    "preceding period while it still publishes, else the operator key that sorts first; "
    "other operators' figures are not added."
)


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def capacity_series(record: Any) -> tuple[str, str, str, str, str]:
    """Source, point, direction, capacity type and operator: one published capacity series."""

    return (
        str(getattr(record, "source_system", "") or "").strip().upper(),
        str(getattr(record, "point_id", "") or ""),
        str(getattr(record, "direction", "") or "").strip().casefold(),
        str(getattr(record, "capacity_type", "") or ""),
        row_operator(record),
    )


def _has_value(record: Any) -> bool:
    if getattr(record, "original_value", None) is not None:
        return True
    if getattr(record, "capacity_mcm_d", None) is not None:
        return True
    native = getattr(record, "native_rate_json", None)
    return isinstance(native, dict) and any(
        native.get(name) is not None for name in ("energy_kwh_per_day", "volume_mcm_per_day")
    )


def _rank(record: Any) -> tuple:
    start, end = _utc(record.period_start_utc), _utc(record.period_end_utc)
    received = value_received_at(record) or datetime.min.replace(tzinfo=UTC)
    return (received, start, -(end - start).total_seconds(), str(record.observation_id))


class ResolvedCapacity:
    """A stored capacity row (or as-of version) read over the period where it holds.

    Every attribute is the row's, except ``period_start_utc``/``period_end_utc``, which are
    the part of the published range this value covers after resolution;
    ``published_period_start_utc``/``published_period_end_utc`` keep the provider's range.
    """

    __slots__ = ("_record", "start", "end", "period_start_utc", "period_end_utc")

    def __init__(self, record: Any, start: datetime, end: datetime) -> None:
        self._record = record
        #: The resolved period as aware UTC instants.
        self.start, self.end = start, end
        # An unchanged bound is the row's own value, exactly as stored.
        own_start, own_end = record.period_start_utc, record.period_end_utc
        self.period_start_utc = own_start if _utc(own_start) == start else start
        self.period_end_utc = own_end if _utc(own_end) == end else end

    @property
    def record(self) -> Any:
        return self._record

    @property
    def published_period_start_utc(self) -> datetime:
        return _utc(self._record.period_start_utc)

    @property
    def published_period_end_utc(self) -> datetime:
        return _utc(self._record.period_end_utc)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._record, name)

    def __repr__(self) -> str:
        return (
            f"ResolvedCapacity({self._record.observation_id!r}, "
            f"{self.start.isoformat()}, {self.end.isoformat()})"
        )


def _merge(pieces: list[tuple[Any, datetime, datetime]]) -> list[tuple[Any, datetime, datetime]]:
    merged: list[tuple[Any, datetime, datetime]] = []
    for record, start, end in sorted(pieces, key=lambda item: item[1]):
        if merged and merged[-1][0] is record and merged[-1][2] == start:
            merged[-1] = (record, merged[-1][1], end)
        else:
            merged.append((record, start, end))
    return merged


def _series_pieces(rows: Sequence[Any]) -> list[tuple[Any, datetime, datetime]]:
    """The latest-received covering range for each elementary interval of one series."""

    bounds = sorted(
        {_utc(row.period_start_utc) for row in rows} | {_utc(row.period_end_utc) for row in rows}
    )
    pieces = []
    for start, end in zip(bounds, bounds[1:], strict=False):
        covering = [
            row
            for row in rows
            if _utc(row.period_start_utc) <= start and _utc(row.period_end_utc) >= end
        ]
        if covering:
            pieces.append((max(covering, key=_rank), start, end))
    return _merge(pieces)


def _choose_operators(
    pieces: list[tuple[Any, datetime, datetime]],
) -> list[tuple[Any, datetime, datetime]]:
    """Keep one operator's pieces per point and instant (the flow rule, over periods)."""

    by_point: dict[tuple[str, str], list[tuple[Any, datetime, datetime]]] = defaultdict(list)
    for piece in pieces:
        series = capacity_series(piece[0])
        by_point[(series[0], series[1])].append(piece)
    kept: list[tuple[Any, datetime, datetime]] = []
    for (_source, point), items in by_point.items():
        operators = {row_operator(record) for record, _, _ in items}
        if len(operators) == 1:
            kept.extend(items)
            continue
        bounds = sorted({start for _, start, _ in items} | {end for _, _, end in items})
        named = _REGISTRY_OPERATOR.get(point)
        previous: str | None = None
        for start, end in zip(bounds, bounds[1:], strict=False):
            here = [item for item in items if item[1] <= start and item[2] >= end]
            reporting = {row_operator(record) for record, _, _ in here if _has_value(record)}
            if not reporting:
                continue
            if named in reporting:
                chosen = named
            elif previous in reporting:
                chosen = previous
            else:
                chosen = min(reporting, key=lambda op: (op == "", op))
            previous = chosen
            kept.extend(
                (record, start, end) for record, _, _ in here if row_operator(record) == chosen
            )
    by_record: dict[int, list[tuple[Any, datetime, datetime]]] = defaultdict(list)
    for piece in kept:
        by_record[id(piece[0])].append(piece)
    return [merged for group in by_record.values() for merged in _merge(group)]


def resolve_capacity(
    records: Iterable[Any],
    *,
    from_utc: datetime | None = None,
    to_utc: datetime | None = None,
) -> list[ResolvedCapacity]:
    """Each capacity series as one value per instant (:data:`CAPACITY_RESOLUTION_RULE`).

    ``records`` are stored rows or as-of versions; pass every row of a series that overlaps
    the period of interest (a range left out cannot supersede anything). With a window,
    only results overlapping ``[from_utc, to_utc)`` are returned; they are not cut to it.
    The result is ordered by series and period start.
    """

    groups: dict[tuple[str, str, str, str, str], list[Any]] = defaultdict(list)
    for record in records:
        groups[capacity_series(record)].append(record)
    pieces: list[tuple[Any, datetime, datetime]] = []
    for rows in groups.values():
        pieces.extend(_series_pieces(rows))
    pieces = _choose_operators(pieces)
    low = _utc(from_utc) if from_utc is not None else None
    high = _utc(to_utc) if to_utc is not None else None
    result = [
        ResolvedCapacity(record, start, end)
        for record, start, end in pieces
        if (low is None or end > low) and (high is None or start < high)
    ]
    result.sort(key=lambda item: (capacity_series(item), item.start))
    return result


def resolve_capacity_as_of(
    session: Any,
    records: Sequence[Any],
    as_of: datetime,
    *,
    from_utc: datetime | None = None,
    to_utc: datetime | None = None,
) -> list[ResolvedCapacity]:
    """:func:`resolve_capacity` over the versions known at ``as_of`` (first receipt, then
    the revision record whose interval contains ``as_of``)."""

    return resolve_capacity(
        versions_as_of(session, records, as_of), from_utc=from_utc, to_utc=to_utc
    )


def overlap_extent(records: Iterable[Any]) -> tuple[datetime, datetime] | None:
    """The span of a set of ranges: a reader that loaded rows overlapping a window loads
    the rows overlapping this span as well, so a range that supersedes part of a loaded
    row outside the window is known."""

    starts, ends = [], []
    for record in records:
        starts.append(_utc(record.period_start_utc))
        ends.append(_utc(record.period_end_utc))
    if not starts:
        return None
    return min(starts), max(ends)


__all__ = [
    "CAPACITY_RESOLUTION_RULE",
    "ResolvedCapacity",
    "capacity_series",
    "overlap_extent",
    "resolve_capacity",
    "resolve_capacity_as_of",
]
