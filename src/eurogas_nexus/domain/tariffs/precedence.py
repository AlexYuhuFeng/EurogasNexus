"""Which cost applies to a capacity requirement: contracted before public, never a silent zero.

Every capacity cost (pipeline entry and exit capacity, LNG slots, regasification, send-out,
storage) is split across three layers, in this order (TAR-2, ADR Decision 38):

(a) **contracted**: capacity the firm holds (booked at auction, a long-term contract, slots
    bought in an allocation, a secondary purchase), at the firm's own contracted cost, for
    the quantities and gas days the booking covers;
(b) **public**: for any quantity or gas day no booking covers, the public tariff for how it
    would be bought (the day-ahead, within-day or other auction's reserve price plus any
    premium stated; a terminal's first-come-first-served rate), as of the valuation instant,
    FINAL where a final is held for that tariff year, otherwise INDICATIVE and flagged;
(c) **not held**: where neither is held, the quantity is stated as not priced and the total
    is not given.

:func:`split` works gas day by gas day, so a booking that covers part of the period or part
of the quantity leaves the rest to the next layer, and a period that spans two tariff years
takes each day's public rate from its own year. A booking either holds a quantity **per gas
day** (capacity, send-out, storage space) or a **pool** over its period (a number of slots),
which requirements draw down in date order.

The layer order is the source-precedence resolver's ``capacity_cost`` order
(``domain/pricing/source_precedence.py``: ``contracted``, ``public_final``,
``public_indicative`` by default, reorderable per firm and per calculation through the governed
``source_precedence`` setting), so capacity costs, FX and interest rates share one mechanism;
each day's public part is resolved by :func:`source_precedence.resolve` and the breakdown lists
every tier in order with the one used marked (``sources``).

Pure and deterministic. The application layer (``application/capacity_costs.py``) loads the
bookings and the public tariff versions; the caller converts every price into the
requirement's unit first (``domain/route_cost/tariff_units.per_mwh``).

TAR-2：容量成本先按企业已签约（已订）容量计价，未覆盖的数量或日期按相应购买方式的公开费率
（最终优先，否则指示性并标注），两者皆无则明确为未持有，不按零计。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from eurogas_nexus.domain.pricing import source_precedence as sp

CONTRACTED = "contracted"
PUBLIC = "public"
NOT_HELD = "not_held"
LAYERS = (CONTRACTED, PUBLIC, NOT_HELD)

PER_DAY = "per_day"
POOL = "pool"

#: How a requirement's uncovered part would be bought, and the public rate that prices it.
HOW_BOUGHT = {
    "YEARLY": "yearly auction reserve price",
    "ANNUAL": "yearly auction reserve price",
    "QUARTERLY": "quarterly auction reserve price",
    "MONTHLY": "monthly auction reserve price",
    "DAILY": "day-ahead auction reserve price",
    "WITHIN_DAY": "within-day auction reserve price",
    "spot": "first-come-first-served public rate",
    "fcfs": "first-come-first-served public rate",
}

PRECEDENCE_TEXT = (
    "contracted cost for what the firm's bookings cover, then the public tariff for how the "
    "rest would be bought (final where held, else indicative), else not held"
)

#: Rank of an LNG-3 capacity offer's basis: what the firm holds first, then what it can buy.
_OFFER_RANK = {"contracted": 0, "tariff": 1, "quoted": 1, "indicative": 2}
EPS = 1e-9


def offer_rank(basis: str) -> int:
    """Precedence of a terminal capacity offer by its basis (``contracted`` first)."""

    return _OFFER_RANK.get(str(basis or "").lower(), 3)


@dataclass(frozen=True)
class Held:
    """One booking the firm holds, its cost already in the requirement's unit."""

    booking_id: str
    first: date
    last: date
    quantity: float
    unit_cost: float | None
    currency: str | None
    basis: str = PER_DAY
    acquired_via: str = ""
    price_text: str = ""
    source: str = ""

    def covers(self, day: date) -> bool:
        return self.first <= day <= self.last


@dataclass(frozen=True)
class PublicRate:
    """The public tariff for a gas day, in the requirement's unit."""

    unit_cost: float
    currency: str
    status: str
    tariff_year: str | None = None
    version_id: str | None = None
    published_at: str | None = None
    recorded_at: str | None = None
    status_basis: str | None = None
    how_bought: str = ""
    premium: float = 0.0
    price_text: str = ""
    source: str = ""
    reference: str = ""

    @property
    def indicative(self) -> bool:
        return self.status.upper() != "FINAL"


@dataclass(frozen=True)
class Requirement:
    """What is needed: ``quantity`` per gas day in ``unit`` from ``first`` to ``last``.

    For a pool (slots), ``quantity`` is what each gas day in the period draws (a cargo's one
    slot on its arrival day: ``first == last``, ``quantity`` 1).
    """

    first: date
    last: date
    quantity: float
    unit: str = "MWh/d"

    def __post_init__(self) -> None:
        if self.last < self.first:
            raise ValueError("the requirement's last gas day is before its first")
        if not self.quantity >= 0:
            raise ValueError("the requirement's quantity must be zero or more")

    def days(self) -> Iterable[date]:
        day = self.first
        while day <= self.last:
            yield day
            day += timedelta(days=1)


@dataclass
class Layer:
    """One part of the requirement and what prices it."""

    layer: str
    reference: str
    quantity: float = 0.0
    cost: float | None = 0.0
    currency: str | None = None
    unit_cost: float | None = None
    first: date | None = None
    last: date | None = None
    detail: dict[str, Any] = field(default_factory=dict)

    def add(self, day: date, quantity: float, unit_cost: float | None) -> None:
        self.quantity += quantity
        if unit_cost is None or self.cost is None:
            self.cost = None
        else:
            self.cost += quantity * unit_cost
        self.first = day if self.first is None else min(self.first, day)
        self.last = day if self.last is None else max(self.last, day)

    def as_dict(self, energy_unit: str) -> dict[str, Any]:
        average = None
        if self.cost is not None and self.quantity > EPS:
            average = self.cost / self.quantity
        return {
            "layer": self.layer,
            "reference": self.reference,
            "quantity": round(self.quantity, 6),
            "unit": energy_unit,
            "unit_cost": None if average is None else round(average, 6),
            "cost": None if self.cost is None else round(self.cost, 2),
            "currency": self.currency,
            "first_gas_day": self.first.isoformat() if self.first else None,
            "last_gas_day": self.last.isoformat() if self.last else None,
            **self.detail,
        }


@dataclass
class Breakdown:
    """A requirement split across contracted, public and not-held layers."""

    requirement: Requirement
    layers: list[Layer]
    issues: list[str] = field(default_factory=list)
    order: tuple[str, ...] = sp.DEFAULT_ORDERS[sp.CAPACITY_COST]
    order_source: str = "default"
    tiers: dict[str, dict[str, Any]] = field(default_factory=dict)

    def sources(self) -> list[dict[str, Any]]:
        """Every tier of the order, in order: used (with the quantity it priced) or skipped and
        why, as the source-precedence resolver reports it."""

        out = []
        # The order in force, then any tier it leaves out (listed as not configured).
        for tier in (*self.order, *(t for t in self.tiers if t not in self.order)):
            seen = self.tiers.get(tier, {})
            used = seen.get("quantity", 0.0) > EPS
            out.append(
                {
                    "tier": tier,
                    "label": sp.TIER_TEXT.get(tier, tier),
                    "used": used,
                    "quantity": round(seen.get("quantity", 0.0), 6),
                    "reason": "used" if used else seen.get("reason", "not_tried"),
                    "note": seen.get("note") or None,
                }
            )
        return out

    @property
    def energy_unit(self) -> str:
        unit = self.requirement.unit
        return unit[:-2] if unit.endswith("/d") else unit

    def quantity(self, layer: str) -> float:
        return sum(item.quantity for item in self.layers if item.layer == layer)

    @property
    def currency(self) -> str | None:
        found = {item.currency for item in self.layers if item.currency and item.quantity > EPS}
        return next(iter(found)) if len(found) == 1 else None

    @property
    def complete(self) -> bool:
        return (
            self.quantity(NOT_HELD) <= EPS
            and all(item.cost is not None for item in self.layers if item.quantity > EPS)
            and (self.currency is not None or self.total_quantity <= EPS)
        )

    @property
    def total_quantity(self) -> float:
        return sum(item.quantity for item in self.layers)

    @property
    def total_cost(self) -> float | None:
        if not self.complete:
            return None
        return sum(item.cost or 0.0 for item in self.layers)

    @property
    def unit_cost(self) -> float | None:
        total = self.total_cost
        if total is None or self.total_quantity <= EPS:
            return None
        return total / self.total_quantity

    @property
    def indicative(self) -> bool:
        return any(
            item.layer == PUBLIC and item.detail.get("status") != "FINAL" and item.quantity > EPS
            for item in self.layers
        )

    def as_dict(self) -> dict[str, Any]:
        unit = self.energy_unit
        return {
            "precedence": PRECEDENCE_TEXT,
            "order": list(self.order),
            "order_source": self.order_source,
            "sources": self.sources(),
            "requirement": {
                "first_gas_day": self.requirement.first.isoformat(),
                "last_gas_day": self.requirement.last.isoformat(),
                "quantity": self.requirement.quantity,
                "unit": self.requirement.unit,
            },
            "layers": [item.as_dict(unit) for item in self.layers if item.quantity > EPS],
            "covered": {layer: round(self.quantity(layer), 6) for layer in LAYERS},
            "unit": unit,
            "total_quantity": round(self.total_quantity, 6),
            "total_cost": None if self.total_cost is None else round(self.total_cost, 2),
            "unit_cost": None if self.unit_cost is None else round(self.unit_cost, 6),
            "currency": self.currency,
            "complete": self.complete,
            "indicative": self.indicative,
            "issues": list(dict.fromkeys(self.issues)),
        }


RateFor = Callable[[date], "PublicRate | Sequence[PublicRate] | None"]


def _candidates(found: PublicRate | Sequence[PublicRate] | None) -> list[PublicRate]:
    if found is None:
        return []
    if isinstance(found, PublicRate):
        return [found]
    return [item for item in found if item is not None]


def _public_lookups(candidates: list[PublicRate], *, why: str):
    """The resolver's public tiers for one gas day: the final version, the indicative one."""

    def pick(final: bool):
        def lookup():
            for rate in candidates:
                if rate.indicative != final:
                    return sp.Found(rate.unit_cost + rate.premium, rate.source,
                                    rate.version_id or rate.reference, detail={"rate": rate})
            if candidates:
                year = candidates[0].tariff_year or "this tariff year"
                kind = "final" if final else "indicative"
                return sp.Skipped(sp.NOT_HELD, f"no {kind} version held for {year}")
            return sp.Skipped(sp.NOT_HELD, why)

        return lookup

    return {"public_final": pick(True), "public_indicative": pick(False)}


def split(
    requirement: Requirement,
    held: Sequence[Held] = (),
    public: RateFor | PublicRate | None = None,
    *,
    not_held_reason: str = "no booking covers it and no public tariff is held",
    order: Sequence[str] | None = None,
    configured: Mapping[str, Any] | None = None,
    context: str = "",
) -> Breakdown:
    """Split ``requirement`` across the firm's bookings, the public rate and not held.

    Bookings are drawn in a fixed order: per-day bookings before pools, then by first gas
    day and id, so the same inputs always give the same layers. A booking without a
    contracted price still covers its quantity (the firm holds it); its layer has no cost and
    the total is not given, with the booking named.

    The layer order is the resolver's ``capacity_cost`` order: ``order`` (the calculation's
    own), else the firm's configured ``source_precedence`` for ``context``, else the default.
    A tier the order leaves out is not used (``contracted`` left out ignores the bookings).
    ``public`` gives each gas day's best public version, or every version held for it.
    """

    if order is not None:
        chosen = tuple(sp.validate_orders({sp.CAPACITY_COST: list(order)})[sp.CAPACITY_COST])
        origin = "calculation"
    else:
        chosen, origin = sp.order_for(sp.CAPACITY_COST, context, configured)
    # The order in runs: "contracted" draws bookings for part of a day; a run of public tiers
    # is resolved by the resolver and prices all that is left of the day.
    runs: list[tuple[str, ...]] = []
    for tier in chosen:
        if tier == "contracted" or not runs or runs[-1] == ("contracted",):
            runs.append((tier,))
        else:
            runs[-1] = runs[-1] + (tier,)
    tiers: dict[str, dict[str, Any]] = {}

    def note(tier: str, *, quantity: float = 0.0, reason: str = "", text: str = "") -> None:
        seen = tiers.setdefault(tier, {"quantity": 0.0})
        seen["quantity"] += quantity
        if reason and seen["quantity"] <= EPS:
            seen["reason"], seen["note"] = reason, text

    rate_for: RateFor
    if public is None or isinstance(public, (PublicRate, list, tuple)):
        fixed = public

        def rate_for(_day: date, _fixed=fixed):
            return _fixed
    else:
        rate_for = public
    bookings = sorted(held, key=lambda h: (h.basis != PER_DAY, h.first, h.booking_id))
    pools: dict[str, float] = {h.booking_id: h.quantity for h in bookings if h.basis == POOL}
    layers: dict[tuple[str, str], Layer] = {}
    issues: list[str] = []

    def layer(kind: str, reference: str, currency: str | None, detail: Mapping[str, Any]):
        key = (kind, reference)
        if key not in layers:
            layers[key] = Layer(kind, reference, currency=currency, detail=dict(detail))
        return layers[key]

    def draw(day: date, left: float) -> float:
        if not bookings:
            note("contracted", reason=sp.NOT_HELD, text="the firm holds no booking for this")
            return left
        for item in bookings:
            if left <= EPS:
                break
            if not item.covers(day):
                continue
            room = item.quantity if item.basis == PER_DAY else pools[item.booking_id]
            take = min(left, max(room, 0.0))
            if take <= EPS:
                continue
            if item.basis == POOL:
                pools[item.booking_id] -= take
            if item.unit_cost is None:
                issues.append(f"booking {item.booking_id}: the contracted cost is not recorded")
            layer(
                CONTRACTED,
                item.booking_id,
                item.currency,
                {
                    "booking_id": item.booking_id,
                    "acquired_via": item.acquired_via,
                    "contracted_price": item.price_text,
                    "source": item.source,
                    "status": "CONTRACTED",
                },
            ).add(day, take, item.unit_cost)
            note("contracted", quantity=take)
            left -= take
        if left > EPS:
            note("contracted", reason=sp.NOT_COVERING,
                 text="no booking covers these gas days or quantities")
        return left

    def price_public(day: date, left: float, run: tuple[str, ...]) -> float:
        resolution = sp.resolve(
            sp.CAPACITY_COST,
            _public_lookups(_candidates(rate_for(day)), why=not_held_reason),
            order=run,
        )
        for outcome in resolution.tiers:
            if outcome.used:
                note(outcome.tier, quantity=left)
            elif outcome.reason != "not_tried":
                note(outcome.tier, reason=outcome.reason, text=outcome.note)
        used = resolution.used
        if used is None or used.found is None:
            return left
        rate = used.found.detail["rate"]
        layer(
            PUBLIC,
            rate.version_id or rate.reference or rate.source,
            rate.currency,
            {
                "status": rate.status.upper(),
                "indicative": rate.indicative,
                "status_basis": rate.status_basis,
                "tariff_year": rate.tariff_year,
                "version_id": rate.version_id,
                "published_at": rate.published_at,
                "recorded_at": rate.recorded_at,
                "how_bought": rate.how_bought,
                "premium": rate.premium,
                "public_price": rate.price_text,
                "source": rate.source,
            },
        ).add(day, left, rate.unit_cost + rate.premium)
        return 0.0

    if "contracted" not in chosen:
        note("contracted", reason=sp.NOT_CONFIGURED, text="left out of the order in force")
    for day in requirement.days():
        left = requirement.quantity
        for run in runs:
            if left <= EPS:
                break
            left = draw(day, left) if run == ("contracted",) else price_public(day, left, run)
        if left > EPS:
            layer(NOT_HELD, "not_held", None, {"reason": not_held_reason}).add(day, left, None)
    out = Breakdown(requirement, list(layers.values()), issues, chosen, origin, tiers)
    if out.quantity(NOT_HELD) > EPS:
        out.issues.append(
            f"{out.quantity(NOT_HELD):,.1f} {out.energy_unit} not priced: {not_held_reason}"
        )
    currencies = {i.currency for i in out.layers if i.currency and i.quantity > EPS}
    if len(currencies) > 1:
        out.issues.append(f"layers in more than one currency: {', '.join(sorted(currencies))}")
    if out.indicative:
        out.issues.append("part of the cost is priced at an INDICATIVE public tariff")
    return out


__all__ = [
    "CONTRACTED",
    "HOW_BOUGHT",
    "LAYERS",
    "NOT_HELD",
    "PER_DAY",
    "POOL",
    "PRECEDENCE_TEXT",
    "PUBLIC",
    "Breakdown",
    "Held",
    "Layer",
    "PublicRate",
    "Requirement",
    "offer_rank",
    "split",
]
