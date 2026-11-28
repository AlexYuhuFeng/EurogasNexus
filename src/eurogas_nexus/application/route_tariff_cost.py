"""The transport cost of moving gas from one hub to another, from the tariffs the store holds.

The route is the proven one (``MarketAreaGraph``: exit from the first market area, any
pipeline charge, entry to the second; TTF → NBP runs through BBL: GTS exit at Julianadorp, the
BBL charge at Bacton, National Gas entry at Bacton). Each leg is priced from the tariff
register (``tso_tariffs``) by point, direction, operator and capacity product, the row in force
on the first gas day of the delivery period. The register holds what the operator published
(a price per unit of capacity per period, ``ingestion/entsog_tariffs.py``); the per-MWh cost is
worked out here, for the stated product (yearly firm by default) and load factor (100 % by
default), by ``domain/route_cost/tariff_units.per_mwh``, and each leg says how. A leg the
register does not hold, or whose unit is not understood, is **missing**, named, and the total
is not given: never zero.

Each leg carries its tariff's gas year, status and data class: a ``FINAL`` publication is
``sourced``; ``INDICATIVE``, ``PROVISIONAL`` and ``DRAFT`` are ``indicative``; the demo's
``SIMULATOR_ONLY`` rows are ``simulated``. The route's class is its weakest leg's.

**The cheapest route** (:func:`cheapest_route`, the one implementation Spreads, Today and the
opportunity evaluators call): every simple sequence of market areas up to ``max_hops`` crossings
is priced, each crossing at its cheapest complete way across (exit, pipeline charges, entry, for
the delivery period, firm annual capacity per MWh at 100 % load factor unless the caller
states another product or load factor), legs in another
currency brought to one at the stated FX. The cheapest complete route is chosen; the next-best
is returned with its extra cost; a route with a leg the register does not hold is unavailable
and names the leg; with no complete route the result says exactly which legs are missing.

**Contracted before public (TAR-2).** Where the firm holds capacity on a leg
(``capacity_bookings``, passed as ``bookings``), :func:`price_leg` splits the requirement:
the booked capacity at its contracted cost, the rest at the register's public tariff for the
product the caller states (the day-ahead reserve price for a day-ahead requirement), else not
held (``domain/tariffs/precedence.split``). The leg's value is then the blended cost per MWh
and ``layers`` shows each part (MWh, cost, source, status, tariff year).

**Point in time (TAR-2).** :func:`load_tariff_rows` with ``as_of`` reads the tariff book's
versions held at that instant instead of the register, so a valuation re-run as of an earlier
instant never uses a tariff published later; every leg names the version, its tariff year, its
status (with NC TAR's rule evaluated at that instant for a row that carries no marker) and its
publication date where the publisher states one.

本模块按已证实的路径（出口、管道、入口）从费率登记表计算枢纽间运输成本；缺失的费率明确
标为缺失，绝不按零计算；每段都带气体年、状态与数据类别。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from eurogas_nexus.domain.market.fx_forward import Delivery
from eurogas_nexus.domain.route_cost.tariff_units import per_mwh
from eurogas_nexus.domain.tariffs import precedence

#: Data classes from weakest to strongest (design basis 2, B.2).
CLASS_ORDER: tuple[str, ...] = (
    "missing",
    "simulated",
    "assumption",
    "indicative",
    "derived",
    "converted",
    "reference",
    "sourced",
)
_STATUS_CLASS = {
    "FINAL": "sourced",
    "INDICATIVE": "indicative",
    "PROVISIONAL": "indicative",
    "DRAFT": "indicative",
    "SIMULATOR_ONLY": "simulated",
    # TAR-2: a leg wholly covered by the firm's own booking is priced from its own records.
    "CONTRACTED": "sourced",
}
#: Which of two rows covering the same day a leg takes: the firmer publication first.
_STATUS_RANK = {"FINAL": 0, "INDICATIVE": 1, "PROVISIONAL": 2, "DRAFT": 3, "SIMULATOR_ONLY": 4}


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
    #: The figure the operator published, as stored ("7.06 EUR/(kWh/h)/y").
    published: str | None = None
    #: How the per-MWh value was read from it (period days, capacity unit, load factor).
    basis: str | None = None
    #: Why a leg the register names is still missing (a unit not understood).
    note: str | None = None
    #: TAR-2: the tariff-book version the public figure is (id, number), its tariff year, the
    #: basis of its status, when the publisher published it (``None``: not stated) and when
    #: this platform first held it.
    version_id: str | None = None
    version: int | None = None
    tariff_year: str | None = None
    status_basis: str | None = None
    published_at: str | None = None
    recorded_at: str | None = None
    #: ``public`` (the register only), ``contracted`` (the firm's bookings cover it all) or
    #: ``contracted+public`` (a booking covers part); the parts are in ``layers``.
    cost_basis: str = "public"
    layers: tuple[dict[str, Any], ...] = ()
    breakdown: dict[str, Any] | None = None

    @property
    def input_class(self) -> str:
        if self.value is None:
            return "missing"
        if self.cost_basis == "contracted":
            return "sourced"
        return _STATUS_CLASS.get((self.status or "").upper(), "indicative")

    @property
    def indicative(self) -> bool:
        """Whether the public figure the leg uses is not FINAL."""

        if self.value is None or self.cost_basis == "contracted":
            return False
        return (self.status or "").upper() != "FINAL"

    @property
    def source_kind(self) -> str | None:
        """Where the leg's tariff comes from, in desk words (None when missing)."""

        if self.value is None:
            return None
        tariff_id = self.tariff_id or ""
        if self.cost_basis == "contracted":
            return "contracted (the firm's booking)"
        if (self.status or "").upper() == "SIMULATOR_ONLY":
            return "simulated"
        if tariff_id.startswith("entsog-"):
            return "published (ENTSOG TP)"
        if tariff_id.startswith("entry-"):
            if "awaiting review" in (self.source or ""):
                return "public tariff, awaiting review"
            return "reviewed public tariff"
        return "tariff register"

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
            "published": self.published,
            "basis": self.basis,
            "note": self.note,
            "source_kind": self.source_kind,
            "input_class": self.input_class,
            "indicative": self.indicative,
            "version_id": self.version_id,
            "version": self.version,
            "tariff_year": self.tariff_year,
            "status_basis": self.status_basis,
            "published_at": self.published_at,
            "recorded_at": self.recorded_at,
            "cost_basis": self.cost_basis,
            "layers": [dict(item) for item in self.layers],
            "breakdown": self.breakdown,
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
    #: Market-area codes in flow order (NBP, ZTP, PEG).
    hubs: tuple[str, ...] = ()
    #: The currency the total is stated in when legs are in several, and the factor taking one
    #: unit of each leg currency into it (the stated FX).
    reporting_currency: str | None = None
    fx_factors: tuple[tuple[str, float], ...] = ()
    product: str = "ANNUAL"
    load_factor: float = 1.0

    @property
    def currency(self) -> str | None:
        currencies = {leg.currency for leg in self.legs if leg.currency}
        if len(currencies) == 1:
            return next(iter(currencies))
        if self.reporting_currency and currencies <= {self.reporting_currency} | {
            code for code, _ in self.fx_factors
        }:
            return self.reporting_currency
        return None

    @property
    def complete(self) -> bool:
        return self.proven and bool(self.legs) and all(leg.value is not None for leg in self.legs)

    @property
    def total(self) -> float | None:
        """Sum of the legs per MWh in their one currency, or None when anything is missing."""

        if not self.complete or self.currency is None:
            return None
        factors = dict(self.fx_factors)
        return sum(
            leg.value * (1.0 if leg.currency == self.currency else factors[leg.currency])
            for leg in self.legs
            if leg.value is not None and leg.currency is not None
        )

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
            "hubs": list(self.hubs),
            "through": list(self.hubs[1:-1]),
            "fx": [{"currency": code, "factor": factor} for code, factor in self.fx_factors],
            "legs": [leg.as_dict() for leg in self.legs],
            "total": self.total,
            "currency": self.currency,
            "unit": f"{self.currency}/MWh" if self.currency else None,
            "complete": self.complete,
            "gas_years": self.gas_years,
            "input_class": self.input_class,
            "missing": self.missing_legs(),
            "product": self.product,
            "load_factor": f"{self.load_factor:.0%} (capacity tariff per MWh at this load)",
            "load_factor_value": self.load_factor,
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


@dataclass(frozen=True)
class LegBooking:
    """Capacity the firm holds at one point and direction (TAR-2), its cost per MWh at the
    route's load factor (``application/capacity_costs.leg_bookings``)."""

    point_key: str
    direction: str
    operator: str | None
    held: precedence.Held

    def applies_to(self, spec: Any) -> bool:
        if self.point_key != spec.point_key or self.direction.upper() != spec.direction.upper():
            return False
        return not self.operator or _tso_matches(self.operator, spec.tso)


def _iso(value: Any) -> str | None:
    moment = _aware(value)
    return moment.isoformat() if moment is not None else (str(value) if value else None)


def price_leg(
    spec: Any,
    rows: Iterable[Mapping[str, Any]],
    on: date,
    *,
    product: str = "ANNUAL",
    firmness: str = "FIRM",
    load_factor: float = 1.0,
    bookings: Sequence[LegBooking] = (),
    orders: Mapping[str, Any] | None = None,
    last: date | None = None,
    mwh_per_day: float | None = None,
) -> RouteLeg:
    """The leg priced from the tariff row in force on ``on``, or missing.

    Only rows of the stated capacity ``product`` and ``firmness`` count (a row that names
    neither, as an older register row may not, counts for any). Of the rows in force, the
    firmest publication wins (FINAL before INDICATIVE before simulated), then the latest:
    the best version held, final where a final is held for that period.

    With ``bookings`` that hold capacity on this leg (TAR-2), the requirement of
    ``mwh_per_day`` (default: the capacity the bookings hold on ``on``) from ``on`` to
    ``last`` is split: the booked part at its contracted cost, the rest at the public rate of
    each gas day (a period across two tariff years takes each year's tariff), else not held.
    The leg's value is the blended cost per MWh, and ``layers`` holds the parts.
    """

    rows = rows if isinstance(rows, list) else list(rows)
    mine = [item for item in bookings if item.applies_to(spec)]
    public = _price_public_leg(spec, rows, on, product=product, firmness=firmness,
                               load_factor=load_factor)
    if not mine:
        return public
    end = last or on
    quantity = mwh_per_day
    if quantity is None:
        quantity = sum(item.held.quantity for item in mine if item.held.covers(on)) or sum(
            item.held.quantity for item in mine
        )
    # The split prices capacity (MWh/d a gas day, load factor 1) so its costs are money; the
    # leg's value per MWh flowed then divides by the load factor, as the public read does.
    cache: dict[date, RouteLeg] = {}

    def rate(day: date) -> precedence.PublicRate | None:
        leg = cache.get(day)
        if leg is None:
            leg = cache[day] = _price_public_leg(
                spec, rows, day, product=product, firmness=firmness, load_factor=1.0
            )
        if leg.value is None or leg.currency is None:
            return None
        return precedence.PublicRate(
            unit_cost=leg.value,
            currency=leg.currency,
            status=leg.status or "INDICATIVE",
            tariff_year=leg.tariff_year or leg.gas_year,
            version_id=leg.version_id,
            published_at=leg.published_at,
            recorded_at=leg.recorded_at,
            status_basis=leg.status_basis,
            how_bought=precedence.HOW_BOUGHT.get(product.upper(), product),
            price_text=leg.published or "",
            source=leg.source_kind or "",
            reference=leg.tariff_id or "",
        )

    breakdown = precedence.split(
        precedence.Requirement(on, end, float(quantity)),
        [item.held for item in mine],
        rate,
        not_held_reason=f"no booking covers it and no {product.lower()} tariff is held",
        configured=orders,
        context="route_cost",
    )
    view = breakdown.as_dict()
    covered = view["covered"]
    basis = (
        "contracted"
        if covered[precedence.PUBLIC] <= precedence.EPS
        and covered[precedence.NOT_HELD] <= precedence.EPS
        else "contracted+public"
    )
    unit_cost = None if breakdown.unit_cost is None else breakdown.unit_cost / load_factor
    return RouteLeg(
        **{
            **{name: getattr(public, name) for name in public.__dataclass_fields__},
            "value": None if unit_cost is None else unit_cost,
            "currency": breakdown.currency if unit_cost is not None else public.currency,
            "unit": (f"{breakdown.currency}/MWh" if unit_cost is not None else public.unit),
            "status": public.status if basis != "contracted" else (public.status or "CONTRACTED"),
            "cost_basis": basis,
            "layers": tuple(view["layers"]),
            "breakdown": view,
            "note": "; ".join(view["issues"]) or public.note,
        }
    )


def _price_public_leg(
    spec: Any,
    rows: Iterable[Mapping[str, Any]],
    on: date,
    *,
    product: str = "ANNUAL",
    firmness: str = "FIRM",
    load_factor: float = 1.0,
) -> RouteLeg:
    """The leg at the public tariff in force on ``on`` (no bookings), or missing."""

    moment = datetime(on.year, on.month, on.day, tzinfo=UTC)
    best: Mapping[str, Any] | None = None
    best_key: tuple[int, datetime] | None = None
    for row in rows:
        if row.get("point_id") != spec.point_key:
            continue
        if str(row.get("direction") or "").upper() != spec.direction.upper():
            continue
        if not _tso_matches(str(row.get("tso") or ""), spec.tso):
            continue
        row_product = str(row.get("capacity_product") or "").upper()
        if row_product and row_product != product.upper():
            continue
        row_firmness = str(row.get("firmness") or "").upper()
        if row_firmness and row_firmness != firmness.upper():
            continue
        start, end = _aware(row.get("effective_from")), _aware(row.get("effective_to"))
        if start is not None and start > moment:
            continue
        if end is not None and end < moment:  # effective_to is the last day in force
            continue
        key = (
            -_STATUS_RANK.get(str(row.get("tariff_status") or "").upper(), 9),
            start or moment,
        )
        if best_key is None or key > best_key:
            best, best_key = row, key
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
    raw = float(best["tariff_value"])
    anniversary = _aware(best.get("effective_from"))
    read = per_mwh(
        raw,
        unit,
        on=on,
        load_factor=load_factor,
        anniversary=anniversary.date() if anniversary else None,
        currency=currency or None,
    )
    published = f"{raw:g} {unit}".strip()
    if read is None:
        # Not a unit this reading understands: not summable, stated missing with the reason.
        return RouteLeg(**base, published=published, note=f"unit not understood: {unit}")
    return RouteLeg(
        **base,
        value=read.value,
        currency=read.currency,
        unit=read.unit,
        gas_year=str(best.get("gas_year") or "") or None,
        status=str(best.get("tariff_status") or "") or None,
        tariff_id=str(best.get("tariff_id") or "") or None,
        source=str(best.get("source_table") or "") or None,
        published=published,
        basis=read.basis,
        version_id=best.get("version_id"),
        version=best.get("version"),
        tariff_year=best.get("tariff_year") or (str(best.get("gas_year") or "") or None),
        status_basis=best.get("status_basis"),
        published_at=_iso(best.get("published_at_utc")),
        recorded_at=_iso(best.get("recorded_at_utc")),
    )


@dataclass(frozen=True)
class _LegSpec:
    point_key: str
    point_name: str
    tso: str
    direction: str
    role: str


def public_tariff_for_leg(
    point_key: str,
    direction: str,
    tso: str,
    on: date,
    *,
    rows: Iterable[Mapping[str, Any]] | None = None,
    product: str = "ANNUAL",
    firmness: str = "FIRM",
    load_factor: float = 1.0,
    point_name: str | None = None,
    role: str = "leg",
    bookings: Sequence[LegBooking] = (),
    orders: Mapping[str, Any] | None = None,
    last: date | None = None,
    mwh_per_day: float | None = None,
) -> RouteLeg:
    """The public tariff for one transmission leg on gas day ``on``, per MWh, or missing.

    The single per-leg read of the public tariff register for callers that price a leg the
    firm has no contract for (``application/contract_costs`` reads the firm's own transport
    contracts first, then this). Rows default to the register (:func:`load_tariff_rows` for
    the product and firmness); the leg names its source (``source_kind``: published, reviewed
    public tariff, awaiting review, simulated) and is missing, never zero, when none is held.
    """

    if rows is None:
        rows = load_tariff_rows(product=product, firmness=firmness)
    spec = _LegSpec(point_key, point_name or point_key, tso, direction.upper(), role)
    return price_leg(spec, rows, on, product=product, firmness=firmness, load_factor=load_factor,
                     bookings=bookings, last=last, mwh_per_day=mwh_per_day, orders=orders)


@dataclass(frozen=True)
class RouteChoice:
    """The cheapest complete route, the next-best ones and the routes that cannot be priced."""

    from_hub: str
    to_hub: str
    chosen: RouteCost
    alternatives: tuple[RouteCost, ...] = ()
    unavailable: tuple[RouteCost, ...] = ()
    issues: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        best = self.chosen.total
        return {
            "chosen": self.chosen.as_dict(),
            "alternatives": [
                {
                    **route.as_dict(),
                    "extra_cost": None
                    if best is None or route.total is None
                    else round(route.total - best, 6),
                }
                for route in self.alternatives
            ],
            "unavailable": [
                {"hubs": list(route.hubs), "via": list(route.via), "missing": route.missing_legs()}
                for route in self.unavailable
            ],
            "missing": [] if self.chosen.complete else self.chosen.missing_legs(),
            "issues": list(self.issues),
        }


#: Crossings a route may chain (NBP -> ZTP -> PEG is two; four reaches across the continent).
MAX_ROUTE_HOPS = 4


def cheapest_route(
    from_hub: str,
    to_hub: str,
    delivery: Delivery,
    tariff_rows: Iterable[Mapping[str, Any]],
    *,
    graph: Any = None,
    through: Iterable[str] | None = None,
    fx: Mapping[str, float] | None = None,
    reporting_currency: str = "EUR",
    max_hops: int = MAX_ROUTE_HOPS,
    alternatives: int = 3,
    product: str = "ANNUAL",
    firmness: str = "FIRM",
    load_factor: float = 1.0,
    bookings: Sequence[LegBooking] = (),
    orders: Mapping[str, Any] | None = None,
    mwh_per_day: float | None = None,
) -> RouteChoice:
    """Price every proven route from ``from_hub`` to ``to_hub`` and choose the cheapest.

    Args:
        from_hub, to_hub: Market codes (TTF, NBP) or VTP point keys; gas moves from -> to.
        delivery: The delivery period; each leg is the tariff in force on its first gas day.
        tariff_rows: The register's rows (:func:`load_tariff_rows`).
        graph: The market-area graph (default the shipped one).
        through: Market codes the route must pass through, in order (a route the desk picked,
            e.g. ``("ZTP",)``); default any.
        fx: Units of ``reporting_currency`` per one unit of each other leg currency, for
            routes whose legs are in several currencies (the stated FX). A currency without a
            factor leaves such a route without a total (named in ``issues``).
        reporting_currency: The currency a mixed-currency route is totalled in.
        max_hops: The most crossings a route may chain.
        alternatives: How many next-best complete routes to return.
        product, firmness: The capacity booked on every leg (firm yearly by default); only
            register rows of that product count, never another product's price.
        load_factor: The share of the booked capacity used (100 % by default).
        bookings: Capacity the firm holds (TAR-2, ``capacity_costs.leg_bookings``): a leg it
            covers is priced at the contracted cost first, the rest at ``product``'s public
            tariff over the delivery period.
        mwh_per_day: The quantity moved per gas day, for splitting a leg a booking covers
            only in part (default: what the bookings hold).

    Returns:
        A :class:`RouteChoice`. ``chosen`` is the cheapest complete route; when none is
        complete it is the shortest route with the fewest missing legs (``complete`` false,
        its missing legs named, never priced at zero).
    """

    if graph is None:
        from eurogas_nexus.reference_data.network_adjacency import shipped_market_area_graph

        graph = shipped_market_area_graph()
    start, target = graph.hub_for(from_hub), graph.hub_for(to_hub)
    if not start or not target:
        issue = f"no market area held for {from_hub if not start else to_hub}"
        empty = RouteCost(
            from_hub,
            to_hub,
            False,
            delivery=delivery,
            issues=(issue,),
            product=product,
            load_factor=load_factor,
        )
        return RouteChoice(from_hub, to_hub, empty, issues=(issue,))
    rows = list(tariff_rows)
    factors = {code.upper(): float(value) for code, value in (fx or {}).items()}
    wanted = [graph.hub_for(code) for code in (through or ()) if code]
    code_of = getattr(graph, "hub_names", {})
    priced_pairs: dict[tuple[str, str], list[tuple[Any, tuple[RouteLeg, ...]]]] = {}

    def crossing_options(a: str, b: str):
        if (a, b) not in priced_pairs:
            options = []
            for crossing in graph.crossings(a, b):
                legs = tuple(
                    price_leg(
                        spec,
                        rows,
                        delivery.first,
                        product=product,
                        firmness=firmness,
                        load_factor=load_factor,
                        bookings=bookings,
                        orders=orders,
                        last=delivery.last,
                        mwh_per_day=mwh_per_day,
                    )
                    for spec in graph.legs(crossing)
                )
                options.append((crossing, legs))
            priced_pairs[(a, b)] = options
        return priced_pairs[(a, b)]

    def leg_cost(legs: tuple[RouteLeg, ...]) -> float | None:
        total = 0.0
        for leg in legs:
            if leg.value is None or leg.currency is None:
                return None
            if leg.currency == reporting_currency:
                total += leg.value
            elif leg.currency in factors:
                total += leg.value * factors[leg.currency]
            else:
                return None
        return total

    complete: list[RouteCost] = []
    partial: list[tuple[int, int, RouteCost]] = []
    missing_fx: set[str] = set()
    for hubs in graph.all_hub_paths(start, target, max_hops=max_hops):
        if wanted and hubs[1:-1] != wanted:
            continue
        chosen: list[tuple[Any, tuple[RouteLeg, ...]]] = []
        ok = True
        for a, b in zip(hubs, hubs[1:], strict=False):
            options = crossing_options(a, b)
            if not options:
                ok = False
                break
            costed = [(leg_cost(legs), crossing, legs) for crossing, legs in options]
            usable = [item for item in costed if item[0] is not None]
            if usable:
                _cost, crossing, legs = min(usable, key=lambda item: item[0])
            else:
                # Not priceable this way: keep the representative crossing, its gaps named.
                crossing, legs = options[0]
                ok = False
                missing_fx |= {
                    leg.currency
                    for leg in legs
                    if leg.value is not None
                    and leg.currency
                    and leg.currency != reporting_currency
                    and leg.currency not in factors
                }
            chosen.append((crossing, legs))
        if not chosen or len(chosen) != len(hubs) - 1:
            continue
        currencies = {leg.currency for _c, legs in chosen for leg in legs if leg.currency}
        route = RouteCost(
            from_hub,
            to_hub,
            True,
            via=tuple(
                " / ".join(
                    str(graph.points.get(point, {}).get("name") or point) for point in c.points
                )
                for c, _legs in chosen
            ),
            legs=tuple(leg for _c, legs in chosen for leg in legs),
            delivery=delivery,
            hubs=tuple(code_of.get(hub, hub) for hub in hubs),
            reporting_currency=reporting_currency if len(currencies) > 1 else None,
            fx_factors=tuple(sorted((c, factors[c]) for c in currencies if c in factors)),
            product=product,
            load_factor=load_factor,
        )
        if ok and route.total is not None:
            complete.append(route)
        else:
            partial.append((len(route.missing_legs()), len(hubs), route))
    issues = tuple(
        f"no FX held for {code} legs" for code in sorted(missing_fx if missing_fx else ())
    )
    if complete:
        ordered = sorted(complete, key=lambda route: (route.total, len(route.hubs)))
        unavailable = tuple(route for *_rank, route in sorted(partial, key=lambda x: (x[1], x[0])))[
            :3
        ]
        return RouteChoice(
            from_hub,
            to_hub,
            ordered[0],
            tuple(ordered[1 : 1 + alternatives]),
            unavailable,
            issues,
        )
    if partial:
        best = min(partial, key=lambda item: (item[1], item[0]))[2]
        others = tuple(
            route
            for *_rank, route in sorted(partial, key=lambda x: (x[1], x[0]))
            if route is not best
        )[:3]
        return RouteChoice(from_hub, to_hub, best, (), others, issues)
    issue = f"no proven route from {from_hub} to {to_hub}" + (
        f" through {', '.join(through or ())}" if through else ""
    )
    return RouteChoice(
        from_hub,
        to_hub,
        RouteCost(
            from_hub,
            to_hub,
            False,
            delivery=delivery,
            issues=(issue,),
            product=product,
            load_factor=load_factor,
        ),
        issues=(issue,),
    )


def route_cost(
    from_hub: str,
    to_hub: str,
    delivery: Delivery,
    tariff_rows: Iterable[Mapping[str, Any]],
    *,
    graph: Any = None,
    through: Iterable[str] | None = None,
    fx: Mapping[str, float] | None = None,
    reporting_currency: str = "EUR",
    product: str = "ANNUAL",
    firmness: str = "FIRM",
    load_factor: float = 1.0,
    bookings: Sequence[LegBooking] = (),
    orders: Mapping[str, Any] | None = None,
    mwh_per_day: float | None = None,
) -> RouteCost:
    """The chosen route of :func:`cheapest_route` (the cheapest complete one, else the
    shortest with its missing legs named)."""

    return cheapest_route(
        from_hub,
        to_hub,
        delivery,
        tariff_rows,
        graph=graph,
        through=through,
        fx=fx,
        reporting_currency=reporting_currency,
        product=product,
        firmness=firmness,
        load_factor=load_factor,
        bookings=bookings,
        mwh_per_day=mwh_per_day,
        orders=orders,
    ).chosen


def load_tariff_rows(
    *, product: str = "ANNUAL", firmness: str = "FIRM", as_of: datetime | None = None
) -> list[dict[str, Any]]:
    """Tariff rows of one capacity product and firmness, as mappings.

    Tariffs are public reference data. The default, firm yearly capacity, is the product a
    route cost is quoted on unless the reader names another.

    Without ``as_of``: the register (``tso_tariffs``), each row annotated with its current
    tariff-book version (id, number, tariff year, status basis, publication and record
    times), and a status that NC TAR's rule decides re-evaluated as of now. With ``as_of``
    (TAR-2): the versions the tariff book held at that instant, so nothing published later is
    used (``tariff_versions_as_rows``); the demo's simulated rows are not versioned and are
    left out.
    """

    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None:
        return []
    with get_session_factory()() as session:
        return tariff_rows(session, product=product, firmness=firmness, as_of=as_of)


def load_route_capacity(
    *, as_of: datetime | None = None, book_ids: Iterable[str] | None = None
) -> tuple[list[LegBooking], dict[str, Any]]:
    """The firm's pipeline bookings held at ``as_of`` and its configured source order, for
    route pricing (TAR-2); none and the default order without a store."""

    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None:
        return [], {}
    from eurogas_nexus.application.capacity_costs import load_leg_bookings
    from eurogas_nexus.application.source_precedence import configured_orders

    try:
        with get_session_factory()() as session:
            return (
                load_leg_bookings(session, as_of=as_of, book_ids=book_ids),
                dict(configured_orders(session)),
            )
    except Exception:  # noqa: BLE001 - a store without the bookings table: public tariffs only
        return [], {}


def tariff_rows(
    session, *, product: str = "ANNUAL", firmness: str = "FIRM", as_of: datetime | None = None
) -> list[dict[str, Any]]:
    """:func:`load_tariff_rows` in an open session."""

    from eurogas_nexus.db.models import TsoTariffRecord

    if as_of is not None:
        from eurogas_nexus.application.tariff_book import tariff_versions_as_rows

        return tariff_versions_as_rows(session, product=product, firmness=firmness, as_of=as_of)
    query = session.query(TsoTariffRecord).filter(
        TsoTariffRecord.capacity_product == product.upper(),
        TsoTariffRecord.firmness == firmness.upper(),
    )
    rows = [
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
            "firmness": row.firmness,
        }
        for row in query.all()
    ]
    from eurogas_nexus.application.tariff_book import annotate_register_rows

    return annotate_register_rows(session, rows)


# ----------------------------------------------------------------- marginal cost of a spread

#: The capacity product a trade over a delivery buys at the margin (CAM standard products,
#: their NC TAR multiplier and any seasonal factor already in the published price): a
#: day-ahead spread the daily product, a month spread the monthly product. Yearly firm capacity
#: at 100 % load factor is what a holder has already paid for: sunk, not marginal.
MARGINAL_PRODUCT = {"day_ahead": "DAILY", "month": "MONTHLY"}
#: Register rows for flow-based charges: a commodity charge per MWh flowed, and fuel gas (gas
#: in kind) as a share of the gas flowed. Entered as ``capacity_product`` COMMODITY or FUEL.
COMMODITY_PRODUCT, FUEL_PRODUCT = "COMMODITY", "FUEL"


def marginal_product(delivery: Delivery) -> str:
    """The capacity product a spread over ``delivery`` is priced on at the margin."""

    return MARGINAL_PRODUCT.get(delivery.kind, "ANNUAL")


@dataclass(frozen=True)
class MarginalRouteCost:
    """What moving one more MWh over the route costs for a prompt spread, and what is sunk.

    ``capacity`` is the route at the marginal capacity product (``product``); ``commodity``
    and ``fuel_cost`` are the flow-based charges the register holds for the route's points
    (``None`` when none is held, which ``flow_not_held`` says); ``total`` is their sum, what a
    desk without capacity pays. ``holder`` is what a desk that already holds the capacity pays
    (the flow charges only), and ``sunk`` the yearly firm route at 100 % load factor (the
    firm's bookings first), for context: capacity already paid for.
    """

    product: str
    choice: RouteChoice
    commodity: float | None = None
    fuel_pct: float | None = None
    fuel_cost: float | None = None
    flow_not_held: tuple[str, ...] = ()
    sunk: RouteCost | None = None

    @property
    def capacity(self) -> float | None:
        return self.choice.chosen.total

    @property
    def total(self) -> float | None:
        if self.capacity is None:
            return None
        return self.capacity + (self.commodity or 0.0) + (self.fuel_cost or 0.0)

    @property
    def holder(self) -> float:
        return (self.commodity or 0.0) + (self.fuel_cost or 0.0)

    @property
    def capacity_held(self) -> str:
        """Whether the firm's own bookings (TAR-2) cover the route: ``all`` when every leg of
        the yearly route is contracted, ``part`` when a booking covers some of it, ``none``
        otherwise. Read from the bookings the sunk route was priced with; nothing new."""

        legs = self.sunk.legs if self.sunk is not None else ()
        if legs and all(leg.cost_basis == "contracted" for leg in legs):
            return "all"
        if any(leg.cost_basis != "public" for leg in legs):
            return "part"
        return "none"

    def as_dict(self) -> dict[str, Any]:
        def rounded(value: float | None) -> float | None:
            return None if value is None else round(value, 6)

        return {
            "product": self.product,
            "capacity": rounded(self.capacity),
            "commodity": rounded(self.commodity),
            "fuel_pct": rounded(self.fuel_pct),
            "fuel": rounded(self.fuel_cost),
            "flow_not_held": list(self.flow_not_held),
            "total": rounded(self.total),
            "holder": rounded(self.holder),
            "capacity_held": self.capacity_held,
            "sunk_capacity": None
            if self.sunk is None
            else {"product": "ANNUAL", "load_factor": 1.0, "value": rounded(self.sunk.total),
                  "complete": self.sunk.complete},
        }


def _flow_rows(rows: Iterable[Mapping[str, Any]], leg: RouteLeg, on: date, product: str):
    moment = datetime(on.year, on.month, on.day, tzinfo=UTC)
    for row in rows:
        if str(row.get("capacity_product") or "").upper() != product:
            continue
        if row.get("point_id") != leg.point_key:
            continue
        if str(row.get("direction") or "").upper() != leg.direction.upper():
            continue
        if not _tso_matches(str(row.get("tso") or ""), leg.tso):
            continue
        start, end = _aware(row.get("effective_from")), _aware(row.get("effective_to"))
        if (start is not None and start > moment) or (end is not None and end < moment):
            continue
        yield row


def flow_charges(
    route: RouteCost,
    rows: Iterable[Mapping[str, Any]],
    on: date,
    *,
    fx: Mapping[str, float] | None = None,
    reporting_currency: str = "EUR",
    gas_price: float | None = None,
) -> tuple[float | None, float | None, float | None, tuple[str, ...]]:
    """Commodity charges and fuel gas on the route's legs, from the register.

    Returns ``(commodity per MWh, fuel %, fuel cost per MWh, what is not held)`` in
    ``reporting_currency``. Fuel gas is valued at ``gas_price`` (the gas at the route's start,
    per MWh). A charge in a currency without a factor in ``fx`` is not added and is named.
    """

    rows = rows if isinstance(rows, list) else list(rows)
    commodity: float | None = None
    fuel_pct: float | None = None
    issues: list[str] = []
    for leg in route.legs:
        for row in _flow_rows(rows, leg, on, COMMODITY_PRODUCT):
            unit = str(row.get("unit") or "").replace(" ", "")
            currency, _, per = unit.partition("/")
            scale = {"MWH": 1.0, "KWH": 1000.0}.get(per.upper())
            factor = 1.0 if currency.upper() == reporting_currency else (fx or {}).get(
                currency.upper()
            )
            if scale is None or factor is None:
                issues.append(f"commodity charge at {leg.point_name or leg.point_key} "
                              f"({row.get('tariff_value')} {unit}) not converted")
                continue
            commodity = (commodity or 0.0) + float(row["tariff_value"]) * scale * factor
        for row in _flow_rows(rows, leg, on, FUEL_PRODUCT):
            if str(row.get("unit") or "").strip() != "%":
                issues.append(f"fuel gas at {leg.point_name or leg.point_key} not in %")
                continue
            fuel_pct = (fuel_pct or 0.0) + float(row["tariff_value"])
    if commodity is None:
        issues.append("no commodity charge held for the route's points")
    if fuel_pct is None:
        issues.append("no fuel gas (gas in kind) held for the route's points")
    fuel_cost = None
    if fuel_pct is not None:
        if gas_price is None:
            issues.append("fuel gas not valued: no gas price at the route's start")
        else:
            fuel_cost = fuel_pct / 100.0 * gas_price
    return commodity, fuel_pct, fuel_cost, tuple(issues)


def marginal_route_cost(
    from_hub: str,
    to_hub: str,
    delivery: Delivery,
    rows_for: Any,
    *,
    fx: Mapping[str, float] | None = None,
    reporting_currency: str = "EUR",
    bookings: Sequence[LegBooking] = (),
    orders: Mapping[str, Any] | None = None,
    gas_price: float | None = None,
) -> MarginalRouteCost:
    """The marginal transport cost of a prompt spread (quant review 2026-11-26, 3.7).

    ``rows_for(product)`` gives the register rows of one capacity product. The route is priced
    on the marginal product (:func:`marginal_product`: daily for day-ahead, monthly for a
    month) at the public tariff, plus the commodity charges and fuel gas the register holds;
    the yearly firm route at 100 % load factor, with the firm's bookings first, is returned
    beside it as sunk capacity.
    """

    product = marginal_product(delivery)
    choice = cheapest_route(
        from_hub, to_hub, delivery, rows_for(product), fx=fx,
        reporting_currency=reporting_currency, product=product,
    )
    sunk = cheapest_route(
        from_hub, to_hub, delivery, rows_for("ANNUAL"), fx=fx,
        reporting_currency=reporting_currency, bookings=bookings, orders=orders,
    ).chosen
    flow_rows = [*rows_for(COMMODITY_PRODUCT), *rows_for(FUEL_PRODUCT)]
    commodity, fuel_pct, fuel_cost, not_held = flow_charges(
        choice.chosen, flow_rows, delivery.first, fx=fx,
        reporting_currency=reporting_currency, gas_price=gas_price,
    )
    return MarginalRouteCost(product, choice, commodity, fuel_pct, fuel_cost, not_held, sunk)
