"""Pipeline gas landed in north-west Europe from the Norwegian and UK shelves.

The balance needs this as energy per gas day. Two things went wrong when it met live ENTSOG
data (2026-11-12), and this module is the repair:

- **Identity by name.** Points were matched on name fragments ("DUNKERQUE", "DORNUM"...).
  That also took the Dunkerque LNG terminal, and it counted one flow two or three times:
  ``ITP-00126`` and ``ITP-00525`` publish the same Dornum flow to the decimal, every day;
  ``ITP-00081`` and ``ITP-00105`` are the two sides' meters on one Emden flow (within
  0.03 %). Points are now named by ENTSOG point key and reporting operator, one row per
  physical landing, in :data:`LANDING_POINTS`.
- **Unit.** The native ENTSOG adapter stores energy (``kWh/d``) and leaves the legacy
  volume column empty, so a sum of volumes read 0.0, a wrong number rather than a missing
  one. Energy is now read as published; only rows from before the native adapter (a volume
  and no native unit) are converted at the declared calorific value.

The UK terminals (Easington, St Fergus) land Norwegian gas together with UK shelf gas and
ENTSOG does not split them, so they are in the registry with that scope stated. A day with
no row for any point is absent from the result, never zero.

Every other reader of ENTSOG flows uses the same two helpers: :func:`row_energy_gwh` for the
energy of one row and :func:`select_operator_rows` for choosing one operator's report per
point and gas day (:data:`OPERATOR_SELECTION_RULE`), which also drops a second key's copy of
one physical point (:data:`SAME_PHYSICAL_POINT`). :func:`published_after_close`
(:data:`CLOSED_DAY_RULE`) tells a closed day's figure from a snapshot taken while the day
was still open; every flow reader applies it through this module.

The alias table lives here, beside the operator rule, rather than in
``domain/ontology/identity.py``: that module names hubs from text and reads no data, while an
alias is a fact about how ENTSOG publishes point keys, proved from flow rows and needed by
the one helper every flow reader already calls.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from statistics import median
from typing import Any

#: Gross calorific value for legacy volume rows only (kWh per m3).
LEGACY_GCV_KWH_M3 = 11.0
#: Name fragments used only for legacy rows that carry no ENTSOG point key.
LEGACY_NAME_FRAGMENTS = (
    "EMDEN", "DORNUM", "ZEEBRUGGE ZPT", "DUNKERQUE", "ST. FERGUS", "ST FERGUS", "EASINGTON",
)


@dataclass(frozen=True)
class LandingPoint:
    point_id: str
    operator: str
    label: str
    #: ``norway`` (a Norwegian export pipeline's landing) or ``uk_terminal`` (Norwegian and
    #: UK shelf gas together).
    scope: str

    def as_dict(self) -> dict[str, str]:
        return dict(self.__dict__)


LANDING_POINTS: tuple[LandingPoint, ...] = (
    LandingPoint("ITP-00188", "DE-TSO-0005", "Dornum / NETRA (Gasunie Deutschland)", "norway"),
    LandingPoint("ITP-00126", "DE-TSO-0009", "Dornum / NETRA (OGE)", "norway"),
    LandingPoint("ITP-00160", "NL-TSO-0001", "Emden EPT1 (GTS)", "norway"),
    LandingPoint("ITP-00081", "DE-TSO-0005", "Emden EPT1 (Gasunie Deutschland)", "norway"),
    LandingPoint("ITP-00080", "DE-TSO-0009", "Emden EPT1 (OGE)", "norway"),
    LandingPoint("ITP-00106", "BE-TSO-0001", "Zeebrugge ZPT (Zeepipe)", "norway"),
    LandingPoint("ITP-00045", "FR-TSO-0003", "Dunkerque (Franpipe)", "norway"),
    LandingPoint("ITP-00097", "DK-TSO-0001", "Nybro", "norway"),
    LandingPoint("ITP-00091", "UK-TSO-0001", "Easington (Langeled and UK shelf)", "uk_terminal"),
    LandingPoint("ITP-00022", "UK-TSO-0001", "St Fergus (Vesterled, FLAGS and UK shelf)",
                 "uk_terminal"),
)
_REGISTRY = {(point.point_id, point.operator): point for point in LANDING_POINTS}
#: The operator whose side the registry reads at each registry point.
_REGISTRY_OPERATOR = {point.point_id: point.operator for point in LANDING_POINTS}

#: How every flow reader picks one report when several operators publish a point.
#:
#: Each operator at an interconnection reports the point from its own side: its ``entry``
#: is flow into its system, its ``exit`` flow out of it. So one physical flow appears as
#: one operator's exit and the other's entry, and adding the operators' rows for a point
#: counts it twice. Choosing per point *and direction* would be wrong too: it can take the
#: flow once as entry (operator B) and again as exit (operator A). The choice is therefore
#: per point and gas day, and both directions are read from the chosen operator's side.
OPERATOR_SELECTION_RULE = (
    "One operator per ENTSOG point and gas day: the operator the landing registry names "
    "for that point; else the operator chosen for that point on the previous gas day read, "
    "if it reports a value that day; else the operator key that sorts first among those "
    "reporting a value at that point that day. Entry and exit are both that operator's "
    "report, so direction is relative to its system; other operators' copies are not added."
)

@dataclass(frozen=True)
class PointAlias:
    """A second ENTSOG point key that publishes the flow of another key's physical point."""

    alias: str
    canonical: str
    evidence: str


#: ENTSOG point keys that publish another key's physical flow, with the evidence. Only
#: pairs the data proves belong here; :func:`identical_series_candidates` lists candidates
#: for a person to check, and nothing is added from it automatically.
SAME_PHYSICAL_POINT: dict[str, PointAlias] = {
    alias.alias: alias
    for alias in (
        PointAlias(
            "ITP-00525",
            "ITP-00126",
            "Dornum GASPOOL (OGE, no adjacent operator) publishes the same entry and exit "
            "as Dornum / NETRA (OGE) to the kWh on every gas day from 27 Sep to 12 Nov 2026 "
            "(47 days), while its bookings and nominations differ: one meter, two keys.",
        ),
    )
}

#: How an alias key's rows are treated by :func:`select_operator_rows`.
SAME_PHYSICAL_POINT_RULE = (
    "A point key listed as another key's alias (same physical point) is dropped for a gas "
    "day on which the canonical key reported a value; it is kept only when the canonical "
    "key has not reported, so the flow is never counted under both keys."
)

#: Days of history a gas day's landing coverage is compared with.
COVERAGE_REFERENCE_DAYS = 28


def row_operator(record: Any) -> str:
    """The ENTSOG operator key that published a row (empty for rows without one)."""

    return str((getattr(record, "metadata_json", None) or {}).get("operatorKey") or "")


def gas_day(record: Any) -> date:
    """The gas day a daily flow row belongs to (the UTC date its period starts)."""

    return record.period_start_utc.date()


def select_operator_rows(records: Iterable[Any]) -> list[Any]:
    """Keep only the chosen operator's rows per point and gas day (:data:`OPERATOR_SELECTION_RULE`).

    A row "reports a value" when :func:`row_energy_gwh` finds energy or a legacy volume in
    it. Rows of the chosen operator are kept even when one of its directions carries no
    value, so a reader sees a missing figure as missing, never as zero. The input order is
    preserved.

    **Stable side.** When the first-sorting operator misses a day (live: at Bacton IUK,
    ITP-00005, National Gas had not yet reported 11 November and IUK had), the choice falls
    to the other side and stays there while that side keeps reporting, instead of flipping
    back and forth and with it the meaning of ``entry``/``exit``. The chain starts at the
    first gas day in ``records``.

    **Same physical point.** Rows of a key in :data:`SAME_PHYSICAL_POINT` are dropped for a
    gas day on which its canonical key reported a value (:data:`SAME_PHYSICAL_POINT_RULE`).
    """

    def point_day(record: Any) -> tuple[str, Any, date]:
        source = str(getattr(record, "source_system", "") or "").strip().upper()
        return source, record.point_id, gas_day(record)

    rows = list(records)
    reporting: dict[tuple[str, Any, date], set[str]] = defaultdict(set)
    for record in rows:
        if row_energy_gwh(record)[0] is not None:
            reporting[point_day(record)].add(row_operator(record))
    chosen: dict[tuple[str, Any, date], str] = {}
    previous: dict[tuple[str, Any], str] = {}
    for key in sorted(reporting, key=lambda item: (item[0], str(item[1]), item[2])):
        alias = SAME_PHYSICAL_POINT.get(str(key[1]))
        if alias is not None and (key[0], alias.canonical, key[2]) in reporting:
            continue  # the canonical key carries this physical flow today
        operators = reporting[key]
        named = _REGISTRY_OPERATOR.get(key[1])
        prior = previous.get(key[:2])
        if named in operators:
            operator = named
        elif prior in operators:
            operator = prior
        else:
            # Rows without an operator key sort after every named operator.
            operator = min(operators, key=lambda op: (op == "", op))
        chosen[key] = previous[key[:2]] = operator
    return [record for record in rows if chosen.get(point_day(record)) == row_operator(record)]


def _utc(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment.astimezone(UTC)


#: The closed-day rule every flow reader applies (one place: here).
CLOSED_DAY_RULE = (
    "A flow row is a closed gas day's figure only when its current value was received at or "
    "after the period end. A value received while the day was open is a partial-day "
    "snapshot: it is kept, offered only to a reader that asks for within-day data, and "
    "flagged as open there; ingestion replaces it by the first receipt after the period end."
)


def received_at(record: Any) -> datetime | None:
    """When the value a row carries was received (its revision, else its first receipt)."""

    return _utc(getattr(record, "revised_at_utc", None)) or _utc(
        getattr(record, "observed_at_utc", None)
    )


def published_after_close(record: Any) -> bool:
    """Whether a daily row's value was received after its gas day ended (:data:`CLOSED_DAY_RULE`).

    ENTSOG publishes the open gas day as it runs; a row stored then holds part of the day
    (live: Dornum 157.8 GWh for 12 November captured at 11:56 UTC that day, against about
    740 GWh on a full day). Once the day has closed such a row would read as the day's flow,
    so a reader that wants a closed day's figure takes only values received after the period
    end. Ingestion replaces the snapshot by the first receipt after the period end and keeps
    the snapshot in ``observation_revisions``; the replacement carries ``revised_at_utc``.
    """

    end, seen = _utc(getattr(record, "period_end_utc", None)), received_at(record)
    return end is not None and seen is not None and seen >= end


def closed_day_clause(model: Any) -> Any:
    """:func:`published_after_close` as a SQL condition, for filtering before a LIMIT."""

    from sqlalchemy import func

    return func.coalesce(model.revised_at_utc, model.observed_at_utc) >= model.period_end_utc


def closed_day_rows(records: Iterable[Any], *, include_open: bool = False) -> list[Any]:
    """Rows that are closed days' figures; with ``include_open`` every row is kept.

    The open-day rows a reader asked for are recognised with :func:`published_after_close`
    and must be shown as such (see the readers' ``open_gas_day`` flag), never as a total.
    """

    return [row for row in records if include_open or published_after_close(row)]


@dataclass(frozen=True)
class AliasCandidate:
    """Two point series that carried the same values over a window (a person decides)."""

    first: tuple[str, str, str]
    second: tuple[str, str, str]
    days: int
    max_relative_difference: float
    mean_gwh_d: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "first": {"point_id": self.first[0], "operator": self.first[1],
                      "direction": self.first[2]},
            "second": {"point_id": self.second[0], "operator": self.second[1],
                       "direction": self.second[2]},
            "days": self.days,
            "max_relative_difference": self.max_relative_difference,
            "mean_gwh_d": self.mean_gwh_d,
            "already_listed": self.first[0] in SAME_PHYSICAL_POINT
            or self.second[0] in SAME_PHYSICAL_POINT,
        }


def identical_series_candidates(
    records: Iterable[Any],
    *,
    days: int = 14,
    tolerance: float = 0.0,
    min_gwh_d: float = 1.0,
) -> list[AliasCandidate]:
    """Point series (point, operator, direction) with the same daily values over ``days``.

    A diagnostic, never applied: it lists candidates for :data:`SAME_PHYSICAL_POINT`. Each
    series is read over its own newest ``days`` gas days, and only series covering the same
    days with a mean of at least ``min_gwh_d`` are compared (all-zero series match each
    other trivially). Two series
    match when every day differs by at most ``tolerance`` relative to the larger value
    (``0.0``: identical to the kWh). The same point under two operators is listed too:
    that is the two sides of an interconnection, already handled by the operator rule, or
    one meter published by two operators, which needs a person's check.
    """

    series: dict[tuple[str, str, str], dict[date, float]] = defaultdict(dict)
    for record in records:
        energy, from_volume = row_energy_gwh(record)
        if energy is None or from_volume or not record.point_id:
            continue
        key = (str(record.point_id), row_operator(record), str(record.direction or "").lower())
        series[key][gas_day(record)] = energy
    # Each series over its own newest ``days`` gas days; only series covering the same days
    # are compared (a day one of them has not reported makes the pair unproven).
    groups: dict[tuple[str, tuple[date, ...]], dict[tuple[str, str, str], tuple[float, ...]]]
    groups = defaultdict(dict)
    for key, values in series.items():
        window = tuple(sorted(values)[-days:]) if days > 0 else ()
        if len(window) < max(days, 1):
            continue
        row = tuple(values[day] for day in window)
        if sum(row) / len(row) >= min_gwh_d:
            groups[(key[2], window)][key] = row
    found = []
    for members in groups.values():
        keys = sorted(members)
        for index, first in enumerate(keys):
            a = members[first]
            for second in keys[index + 1 :]:
                b = members[second]
                worst = 0.0
                for x, y in zip(a, b, strict=True):
                    scale = max(abs(x), abs(y))
                    worst = max(worst, abs(x - y) / scale if scale else 0.0)
                    if worst > tolerance:
                        break
                if worst <= tolerance:
                    found.append(
                        AliasCandidate(first, second, len(a), worst, sum(a) / len(a))
                    )
    return sorted(found, key=lambda item: (item.first, item.second))


def load_alias_candidates(
    session, *, days: int = 14, tolerance: float = 0.0, now: datetime | None = None
) -> list[AliasCandidate]:
    """:func:`identical_series_candidates` over the stored ENTSOG flow rows of closed days."""

    from eurogas_nexus.db.models import FlowObservationRecord as Flow

    now = now or datetime.now(UTC)
    naive = session.get_bind().dialect.name == "sqlite"
    start = now - timedelta(days=days + 3)
    rows = (
        session.query(Flow)
        .filter(Flow.period_start_utc >= (start.replace(tzinfo=None) if naive else start))
        .filter(Flow.period_end_utc <= (now.replace(tzinfo=None) if naive else now))
        .all()
    )
    return identical_series_candidates(
        [row for row in rows if published_after_close(row)], days=days, tolerance=tolerance
    )


@dataclass
class PipelineSupply:
    #: Energy landed per gas day (GWh), for complete days only (see :func:`landed_supply`).
    by_day: dict[date, float]
    #: The same, split by scope, for the reader who wants Norway apart from UK terminals.
    by_scope: dict[str, dict[date, float]]
    #: ``registry`` (ENTSOG point keys), ``legacy_names`` (pre-native rows) or ``none``.
    basis: str
    legacy_rows: int = 0
    #: Registry landing points reporting a value, per gas day read (complete or not).
    points_reporting: dict[date, int] = field(default_factory=dict)
    #: Days left out of ``by_day`` because fewer landing points reported than usual.
    incomplete_days: list[date] = field(default_factory=list)

    @property
    def complete_through(self) -> date | None:
        """The newest complete gas day."""

        return max(self.by_day, default=None)


def row_energy_gwh(record: Any) -> tuple[float | None, bool]:
    """A flow row's energy for its gas day in GWh, and whether it came from legacy volume."""

    from eurogas_nexus.domain.ontology.quantity import UnitError, convert

    unit = str(getattr(record, "original_unit", "") or "").strip()
    value = getattr(record, "original_value", None)
    if value is not None and unit:
        # A daily rate ("kWh/d") over its gas day is that much energy; the ontology owns
        # the factor.
        try:
            return convert(float(value), unit.split("/")[0], "GWh"), False
        except UnitError:
            pass  # not an energy unit: fall through to the legacy volume, if any
    native = getattr(record, "native_rate_json", None)
    if isinstance(native, dict) and native.get("energy_kwh_per_day") is not None:
        # The native payload's canonical daily energy, when the row kept no original value.
        try:
            return convert(float(native["energy_kwh_per_day"]), "kWh", "GWh"), False
        except (TypeError, ValueError, UnitError):
            pass
    volume = getattr(record, "flow_mcm_d", None)
    if volume is not None:
        return float(volume) * LEGACY_GCV_KWH_M3, True
    return None, False


def landed_supply(session, first: date, *, as_of: datetime | None = None) -> PipelineSupply:
    """Sum closed gas days of entry flow at the registry's points since ``first``.

    **Completeness is a coverage rule, not a size rule.** ENTSOG fills a gas day in point
    by point over the following day or two, so the newest days can hold only some of the
    landings (live, 2026-11-12: seven of ten points for 11 November, three for 12
    November). A day's sum is kept only when at least as many landing points reported a
    value for it as usually do: the median count over the up to
    :data:`COVERAGE_REFERENCE_DAYS` gas days read before it (for the first day read, the
    median over every day read). A point that reports zero has reported, so a genuine
    outage still shows as low supply; a point that has not reported yet makes the day
    incomplete. Incomplete days are left out of ``by_day``/``by_scope`` and listed in
    ``incomplete_days``.
    """

    from sqlalchemy import or_

    from eurogas_nexus.db.models import FlowObservationRecord as Flow

    naive = session.get_bind().dialect.name == "sqlite"
    start = datetime.combine(first, datetime.min.time())
    query = (
        session.query(Flow)
        .filter(Flow.period_start_utc >= (start if naive else start.astimezone()))
        .filter(Flow.direction.ilike("entry"))
        .filter(
            or_(
                Flow.point_id.in_(sorted({point.point_id for point in LANDING_POINTS})),
                *(Flow.point_name.ilike(f"%{name}%") for name in LEGACY_NAME_FRAGMENTS),
            )
        )
    )
    if as_of is not None:
        cutoff = as_of.replace(tzinfo=None) if naive else as_of
        query = query.filter(Flow.observed_at_utc <= cutoff, Flow.period_end_utc <= cutoff)
    records = query.all()
    if as_of is not None:
        # A value revised after ``as_of`` is read as it was known then (its prior version).
        from eurogas_nexus.db.repositories.observation_revisions import versions_as_of

        records = versions_as_of(session, records, as_of)

    totals: dict[date, float] = defaultdict(float)
    scopes: dict[str, dict[date, float]] = defaultdict(lambda: defaultdict(float))
    reporting: dict[date, set[tuple[str, str]]] = defaultdict(set)
    registry_rows = legacy_rows = 0
    for record in records:
        if not published_after_close(record):
            # A snapshot of the day while it was open (see published_after_close): not the
            # day's landing, and not a report for the coverage count either.
            continue
        operator = row_operator(record)
        point = _REGISTRY.get((record.point_id, operator))
        energy, from_volume = row_energy_gwh(record)
        if energy is None:
            continue
        if point is None:
            # Only a pre-native row (a volume, no point key in the registry) is taken by
            # name; a native row outside the registry is another operator's copy of a flow
            # already counted, or not a landing at all.
            if not from_volume:
                continue
            scope, legacy_rows = "norway", legacy_rows + 1
        else:
            scope, registry_rows = point.scope, registry_rows + 1
        day = gas_day(record)
        totals[day] += energy
        scopes[scope][day] += energy
        reporting[day].add((str(record.point_id or record.point_name), operator))
    counts = {day: len(points) for day, points in sorted(reporting.items())}
    incomplete = _incomplete_days(counts)
    basis = "registry" if registry_rows else "legacy_names" if legacy_rows else "none"
    return PipelineSupply(
        by_day={day: value for day, value in totals.items() if day not in incomplete},
        by_scope={
            scope: {day: value for day, value in days.items() if day not in incomplete}
            for scope, days in scopes.items()
        },
        basis=basis,
        legacy_rows=legacy_rows,
        points_reporting=counts,
        incomplete_days=sorted(incomplete),
    )


def _incomplete_days(counts: dict[date, int]) -> set[date]:
    """Days on which fewer landing points reported than the usual count (see landed_supply)."""

    days = sorted(counts)
    if not days:
        return set()
    overall = median(counts.values())
    incomplete = set()
    for index, day in enumerate(days):
        earlier = [
            counts[prior]
            for prior in days[max(0, index - COVERAGE_REFERENCE_DAYS) : index]
            if (day - prior).days <= COVERAGE_REFERENCE_DAYS
        ]
        reference = median(earlier) if earlier else overall
        if counts[day] < reference:
            incomplete.add(day)
    return incomplete
