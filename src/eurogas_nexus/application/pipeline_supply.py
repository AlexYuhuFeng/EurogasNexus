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
point and gas day (:data:`OPERATOR_SELECTION_RULE`).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime
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
    "for that point, else the operator key that sorts first among those reporting a "
    "value at that point that day. Entry and exit are both that operator's report, so "
    "direction is relative to its system; other operators' copies are not added."
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
    for key, operators in reporting.items():
        named = _REGISTRY_OPERATOR.get(key[1])
        # Rows without an operator key sort after every named operator.
        chosen[key] = (
            named if named in operators else min(operators, key=lambda op: (op == "", op))
        )
    return [record for record in rows if chosen.get(point_day(record)) == row_operator(record)]


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

    totals: dict[date, float] = defaultdict(float)
    scopes: dict[str, dict[date, float]] = defaultdict(lambda: defaultdict(float))
    reporting: dict[date, set[tuple[str, str]]] = defaultdict(set)
    registry_rows = legacy_rows = 0
    for record in query.all():
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
