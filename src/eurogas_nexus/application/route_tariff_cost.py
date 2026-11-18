"""The transport cost of moving gas from one hub to another, from the tariffs the store holds.

The route is the proven one (``MarketAreaGraph``: exit from the first market area, any
pipeline charge, entry to the second; TTF → NBP runs through BBL: GTS exit at Julianadorp, the
BBL charge at Bacton, National Gas entry at Bacton). Each leg is priced from the tariff
register (``tso_tariffs``) by point, direction and operator, the row in force on the first gas
day of the delivery period; the per-MWh figure is the register's (ENTSOG capacity tariffs are
stored per MWh at 100 % load factor, ``ingestion/entsog_tariffs.per_mwh_at_full_load``). A leg
the register does not hold is **missing**, named, and the total is not given: never zero.

Each leg carries its tariff's gas year, status and data class: a ``FINAL`` publication is
``sourced``; ``INDICATIVE``, ``PROVISIONAL`` and ``DRAFT`` are ``indicative``; the demo's
``SIMULATOR_ONLY`` rows are ``simulated``. The route's class is its weakest leg's.

本模块按已证实的路径（出口、管道、入口）从费率登记表计算枢纽间运输成本；缺失的费率明确
标为缺失，绝不按零计算；每段都带气体年、状态与数据类别。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from eurogas_nexus.domain.market.fx_forward import Delivery

#: Data classes from weakest to strongest (design basis 2, B.2).
CLASS_ORDER: tuple[str, ...] = (
    "missing", "simulated", "assumption", "indicative", "derived", "converted", "reference",
    "sourced",
)
_STATUS_CLASS = {
    "FINAL": "sourced",
    "INDICATIVE": "indicative",
    "PROVISIONAL": "indicative",
    "DRAFT": "indicative",
    "SIMULATOR_ONLY": "simulated",
}


def weakest(classes: Iterable[str]) -> str:
    """The weakest data class among ``classes`` (``sourced`` when there are none)."""

    found = [item for item in classes if item]
    if not found:
        return "sourced"
    return min(found, key=lambda item: CLASS_ORDER.index(item) if item in CLASS_ORDER else 0)


@dataclass(frozen=True)
class RouteLeg:
    """One exit, pipeline or entry charge of the route, priced or missing."""

    point_key: str
    point_name: str
    tso: str
    direction: str
    role: str
    value: float | None = None
    currency: str | None = None
    unit: str | None = None
    gas_year: str | None = None
    status: str | None = None
    tariff_id: str | None = None
    source: str | None = None

    @property
    def input_class(self) -> str:
        if self.value is None:
            return "missing"
        return _STATUS_CLASS.get((self.status or "").upper(), "indicative")

    def as_dict(self) -> dict[str, Any]:
        return {
            "point_key": self.point_key,
            "point_name": self.point_name,
            "tso": self.tso,
            "direction": self.direction,
            "role": self.role,
            "value": self.value,
            "currency": self.currency,
            "unit": self.unit,
            "gas_year": self.gas_year,
            "status": self.status,
            "tariff_id": self.tariff_id,
            "source": self.source,
            "input_class": self.input_class,
        }


@dataclass(frozen=True)
class RouteCost:
    """The route from ``from_hub`` to ``to_hub`` for a delivery period and its priced legs."""

    from_hub: str
    to_hub: str
    proven: bool
    via: tuple[str, ...] = ()
    legs: tuple[RouteLeg, ...] = ()
    delivery: Delivery | None = None
    issues: tuple[str, ...] = field(default_factory=tuple)

    @property
    def currency(self) -> str | None:
        currencies = {leg.currency for leg in self.legs if leg.currency}
        return next(iter(currencies)) if len(currencies) == 1 else None

    @property
    def complete(self) -> bool:
        return self.proven and bool(self.legs) and all(leg.value is not None for leg in self.legs)

    @property
    def total(self) -> float | None:
        """Sum of the legs per MWh in their one currency, or None when anything is missing."""

        if not self.complete or self.currency is None:
            return None
        return sum(leg.value for leg in self.legs if leg.value is not None)

    @property
    def input_class(self) -> str:
        if not self.proven:
            return "missing"
        return weakest(leg.input_class for leg in self.legs)

    @property
    def gas_years(self) -> list[str]:
        return sorted({leg.gas_year for leg in self.legs if leg.gas_year})

    def missing_legs(self) -> list[str]:
        return [
            f"{leg.point_name} {leg.direction.lower()} ({leg.tso})"
            for leg in self.legs
            if leg.value is None
        ]

    def as_dict(self) -> dict[str, Any]:
        return {
            "from_hub": self.from_hub,
            "to_hub": self.to_hub,
            "direction": f"{self.from_hub} → {self.to_hub}",
            "proven": self.proven,
            "via": list(self.via),
            "legs": [leg.as_dict() for leg in self.legs],
            "total": self.total,
            "currency": self.currency,
            "unit": f"{self.currency}/MWh" if self.currency else None,
            "complete": self.complete,
            "gas_years": self.gas_years,
            "input_class": self.input_class,
            "missing": self.missing_legs(),
            "load_factor": "100 % (capacity tariff per MWh at full load)",
            "delivery": self.delivery.as_dict() if self.delivery else None,
            "issues": list(self.issues),
        }


def _aware(moment: Any) -> datetime | None:
    if moment is None:
        return None
    if isinstance(moment, datetime):
        return moment if moment.tzinfo else moment.replace(tzinfo=UTC)
    if isinstance(moment, date):
        return datetime(moment.year, moment.month, moment.day, tzinfo=UTC)
    return None


def _tso_matches(row_tso: str, leg_tso: str) -> bool:
    row = row_tso.strip().lower()
    return any(row == part.strip().lower() for part in leg_tso.split("/")) or (
        row and row in leg_tso.lower()
    )


def price_leg(spec: Any, rows: Iterable[Mapping[str, Any]], on: date) -> RouteLeg:
    """The leg priced from the tariff row in force on ``on``, or missing."""

    moment = datetime(on.year, on.month, on.day, tzinfo=UTC)
    best: Mapping[str, Any] | None = None
    for row in rows:
        if row.get("point_id") != spec.point_key:
            continue
        if str(row.get("direction") or "").upper() != spec.direction.upper():
            continue
        if not _tso_matches(str(row.get("tso") or ""), spec.tso):
            continue
        start, end = _aware(row.get("effective_from")), _aware(row.get("effective_to"))
        if start is not None and start > moment:
            continue
        if end is not None and end < moment:  # effective_to is the last day in force
            continue
        if best is None or (_aware(row.get("effective_from")) or moment) > (
            _aware(best.get("effective_from")) or moment
        ):
            best = row
    base = {
        "point_key": spec.point_key,
        "point_name": spec.point_name,
        "tso": spec.tso,
        "direction": spec.direction,
        "role": spec.role,
    }
    if best is None:
        return RouteLeg(**base)
    unit = str(best.get("unit") or "")
    currency = str(best.get("currency") or "")
    if unit and "MWH" not in unit.upper():
        return RouteLeg(**base)  # not a per-MWh figure: not summable here, stated missing
    return RouteLeg(
        **base,
        value=float(best["tariff_value"]),
        currency=currency or unit.split("/")[0],
        unit=f"{currency}/MWh" if currency else unit,
        gas_year=str(best.get("gas_year") or "") or None,
        status=str(best.get("tariff_status") or "") or None,
        tariff_id=str(best.get("tariff_id") or "") or None,
        source=str(best.get("source_table") or "") or None,
    )


def route_cost(
    from_hub: str,
    to_hub: str,
    delivery: Delivery,
    tariff_rows: Iterable[Mapping[str, Any]],
    *,
    graph: Any = None,
) -> RouteCost:
    """The priced route from ``from_hub`` to ``to_hub`` for ``delivery``."""

    if graph is None:
        from eurogas_nexus.reference_data.network_adjacency import shipped_market_area_graph

        graph = shipped_market_area_graph()
    start, target = graph.hub_for(from_hub), graph.hub_for(to_hub)
    if not start or not target:
        return RouteCost(from_hub, to_hub, False, delivery=delivery,
                         issues=(f"no market area held for {from_hub if not start else to_hub}",))
    crossings = graph.route(start, target)
    if not crossings:
        return RouteCost(from_hub, to_hub, False, delivery=delivery,
                         issues=(f"no proven route from {from_hub} to {to_hub}",))
    rows = list(tariff_rows)
    legs = tuple(
        price_leg(spec, rows, delivery.first)
        for crossing in crossings
        for spec in graph.legs(crossing)
    )
    via = tuple(
        " / ".join(str(graph.points.get(point, {}).get("name") or point) for point in c.points)
        for c in crossings
    )
    return RouteCost(from_hub, to_hub, True, via=via, legs=legs, delivery=delivery)


def load_tariff_rows() -> list[dict[str, Any]]:
    """Every tariff register row, as mappings (tariffs are public reference data)."""

    from eurogas_nexus.db.models import TsoTariffRecord
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None:
        return []
    with get_session_factory()() as session:
        return [
            {
                "tariff_id": row.tariff_id,
                "tso": row.tso,
                "point_id": row.point_id,
                "direction": row.direction,
                "gas_year": row.gas_year,
                "tariff_value": row.tariff_value,
                "currency": row.currency,
                "unit": row.unit,
                "effective_from": row.effective_from,
                "effective_to": row.effective_to,
                "tariff_status": row.tariff_status,
                "source_table": row.source_table,
                "capacity_product": row.capacity_product,
            }
            for row in session.query(TsoTariffRecord).all()
            # Firm annual capacity: the product a route cost is quoted on.
            if str(row.capacity_product or "").upper() == "ANNUAL"
            and str(row.firmness or "").upper() == "FIRM"
        ]
