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
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
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


@dataclass
class PipelineSupply:
    #: Energy landed per gas day (GWh), for days with at least one row.
    by_day: dict[date, float]
    #: The same, split by scope, for the reader who wants Norway apart from UK terminals.
    by_scope: dict[str, dict[date, float]]
    #: ``registry`` (ENTSOG point keys), ``legacy_names`` (pre-native rows) or ``none``.
    basis: str
    legacy_rows: int = 0


def row_energy_gwh(record: Any) -> tuple[float | None, bool]:
    """A flow row's energy for its gas day in GWh, and whether it came from legacy volume."""

    unit = str(getattr(record, "original_unit", "") or "").strip().lower()
    value = getattr(record, "original_value", None)
    if value is not None and unit.startswith("kwh"):
        return float(value) / 1_000_000.0, False
    if value is not None and unit.startswith("mwh"):
        return float(value) / 1_000.0, False
    if value is not None and unit.startswith("gwh"):
        return float(value), False
    volume = getattr(record, "flow_mcm_d", None)
    if volume is not None:
        return float(volume) * LEGACY_GCV_KWH_M3, True
    return None, False


def landed_supply(session, first: date, *, as_of: datetime | None = None) -> PipelineSupply:
    """Sum closed gas days of entry flow at the registry's points since ``first``."""

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
    registry_rows = legacy_rows = 0
    for record in query.all():
        operator = str((record.metadata_json or {}).get("operatorKey") or "")
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
        day = record.period_start_utc.date()
        totals[day] += energy
        scopes[scope][day] += energy
    basis = "registry" if registry_rows else "legacy_names" if legacy_rows else "none"
    return PipelineSupply(
        by_day=dict(totals),
        by_scope={scope: dict(days) for scope, days in scopes.items()},
        basis=basis,
        legacy_rows=legacy_rows,
    )
