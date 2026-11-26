"""A disrupted LNG cargo or pipeline supply, re-optimised across the whole portfolio (LNG-3).

When a cargo is late, the desk has several ways to land it, each with its own cost, value,
flexibility, risk and knock-on effect on the rest of the portfolio:

* **wait** at its own slot and absorb what the delay costs: the send-out rights of the days
  before it berths are lost (use it or lose it), the tank holds more than the slot's declining
  storage right, and what does not fit in the slot's send-out runs on interruptible capacity
  (where the terminal offers it) after the slot;
* **borrow** LNG in the tank from another terminal user for the days before it berths, send it
  out on those days with the slot's own rights, and return it from the cargo after it berths
  (an in-tank title transfer): the planned send-out is kept;
* **buy** extra firm send-out (and the storage the catch-up needs) for the days after berthing;
* **divert** to another terminal where the book holds a spare slot that matches;
* **swap** terminals with another cargo of the book;
* and in every case **re-align the hedges** (buy back or sell per hub and month, at short
  notice where the month has stopped trading) and pay **demurrage** where a ship waits past its
  laytime.

A pipeline supply that is curtailed gets the same treatment: absorb (re-hedge the gas that is
not delivered) or cover it from an LNG cargo at the same hub by sending that cargo's gas out
earlier on bought send-out (which changes that cargo's schedule).

Every option is valued against the plan before the disruption, across the whole portfolio
(every supply, every firm delivery obligation), under a few scenarios (the ETA earlier and
later by the spread its confidence allows, prices up and down), and placed on a Pareto
frontier over six objectives:

========================  ==========================================================  =====
objective                 meaning                                                     sense
========================  ==========================================================  =====
``pnl_expected``          P&L change in the base scenario (EUR)                       max
``pnl_worst``             worst P&L change across the scenarios (EUR): the downside   max
``cost``                  cash paid for the option less what the plan already paid    min
``flexibility_mwh``       firm send-out still held spare, less interruptible relied   max
``disrupted_mwh``         energy of supplies operating normally that the option moves min
``contract_breaches``     contracts the option breaks (LNG-4)                         min
========================  ==========================================================  =====

There is no single answer (LNG-4, the owner's 2026-11-25 instruction): every option is a
complete course of action, and the consequences that matter to a trader are explicit flags.

* **Physically impossible** (``feasible`` false, ``reasons``): the tank does not fit the
  storage right and no storage can be bought or used there, energy has no send-out right
  before the tail ends, a target slot is not the book's own. Listed as not possible, never
  chosen.
* **Contract breach** (``breaches``): the option short-delivers a firm obligation (valued at
  the obligation's liquidated damages where the contract data holds them; otherwise the
  shortfall is stated and the penalty is said not to be held), or diverts a cargo whose
  contract gives no diversion right. Such an option stays listed and can be chosen.
* **Disrupts a normal cargo** (``disrupts``): it moves supplies that were running to plan,
  each named with the MWh moved.

Every option is valued at its full cost (LNG-4, the owner's second instruction of
2026-11-25): its **direct** P&L (the cargoes it places, the capacity it buys, the substitute
gas it brings in) and its **opportunity cost**, which the P&L includes and the reader sees
apart, line by line:

* **knock-on** on the book's other cargoes: a cargo the option moves takes the berth on the day
  it can, so a cargo of the book due there waits (its demurrage, boil-off and what its later
  send-out does to hedges and deliveries); and it draws the terminals' shared per-day limits
  (interruptible or bought send-out, storage, in-tank lending) first, so a later cargo finds
  less left. Such a cargo is also flagged under ``disrupts``;
* **displaced calls**: another user's ship due at a berth the option takes, where the line-up
  is held (its demurrage past the laytime it has left, and its boil-off);
* **capacity forgone**: a spare slot of the book the option uses could have been released or
  used elsewhere (the slot's indicative release value, else the desk's value of a spare slot;
  where neither is held the line says so and adds nothing);
* **storage gas** drawn to cover a delivery is not there in the month it was to be used.

So a long-term contracted terminal is not assumed to beat a spot slot (a ``slot`` offer) at
another: both come out of the same valuation. Substitute supply (``SubstituteSource``: gas the
book holds upstream, hub gas moved on transport capacity, storage) covers what an option leaves
short of a delivery obligation, alone or cheapest first, as further options with the same
fields. Every arithmetic line names the price, rate and tariff sources it applied.

The engine then names a recommended set, each with a one-line reason: the best ranked option
that breaks no contract and moves nothing running to plan, the highest expected P&L that
breaks no contract, and the best ranked overall, where these differ. "Best" orders by a score
whose weights are named, editable assumptions used for ordering only::

    score = pnl_expected - risk_weight x (pnl_expected - pnl_worst)
            - disruption_eur_per_mwh x disrupted_mwh - disruption_eur_per_supply x supplies
            + flexibility_eur_per_mwh x flexibility_mwh - breach_eur_per_contract x breaches

with the weights from the firm's approved assumptions (desk standards otherwise, named as
such). Ties go to fewer disrupted supplies, then to the option key, so the result is
deterministic. A trader decides; choosing records the choice and books nothing.

Conventions (docs/engineering/Commercial-Intelligence-V3/
17_LNG_PORTFOLIO_DISRUPTION_OPTIMISATION.md):

* Time is the gas day; energy MWh; money EUR. A slot is ``days`` gas days from ``start`` with a
  send-out right of ``send_out_mwh_per_day`` each day and a storage right that, for a
  ``linear_decline`` slot (the standard slot of Zeebrugge and others), falls linearly to zero
  over the slot: at the end of slot day ``k`` (0-based) it is ``storage x (days - 1 - k) / days``.
* Storage is checked at the end of each gas day; the send-out of a day is sent before the
  check. Boil-off while a ship waits at anchor is costed at the hub price (it is not taken out
  of the send-out schedule: at most a few tenths of a percent of a cargo, and the schedule
  stays in whole slot days).
* Physical value moved is valued at the hub's month price. Re-hedging aligns the hedges so the
  book's net per hub and month stays what it was: a month that still trades costs the futures
  trade cost per MWh; a month that has stopped trading costs the short-notice premium (BOM or
  day-ahead); a gas day already nominated costs the cash-out premium on the day's price.
  In a scenario, the hedges are re-aligned once for that scenario's physical.
* Energy that cannot be landed (no storage right, no interruptible capacity) is stranded: it
  is infeasible in the base scenario and, in a scenario, valued at the slot's last month price
  less the stranded discount.

Pure: no I/O, no clock (``now`` is in the market). Advice only: nothing is booked, borrowed,
bought, traded or nominated; a person chooses. Money is EUR: a demurrage rate held in another
currency is converted before it reaches the engine (``application/lng_disruption.py``), and
``Supply.demurrage_note`` carries the conversion into the arithmetic.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from itertools import product
from typing import Any

from eurogas_nexus.domain.lng.in_transit import last_trading_day
from eurogas_nexus.domain.tariffs.precedence import offer_rank

#: Below this an energy figure is rounding, not a position (MWh).
EPS_MWH = 1.0
#: Below this a money figure is rounding (EUR).
EPS_EUR = 1.0
#: How many gas days after a slot ends the engine follows a tail on interruptible or bought
#: send-out before it calls the rest stranded.
TAIL_DAYS = 14
#: A bound on the options built per disrupted supply and on combinations across supplies.
MAX_OPTIONS_PER_SUPPLY = 24
MAX_COMBINATIONS = 256

LNG = "lng"
PIPELINE = "pipeline"

OBJECTIVES: tuple[tuple[str, str], ...] = (
    ("pnl_expected", "max"),
    ("pnl_worst", "max"),
    ("cost", "min"),
    ("flexibility_mwh", "max"),
    ("disrupted_mwh", "min"),
    ("contract_breaches", "min"),
)
#: The bases of a recommendation, in the order they are named (LNG-4).
CLEAN = "clean"
BEST_EXPECTED = "best_expected"
OVERALL = "overall"
RECOMMENDATION_BASES = (CLEAN, BEST_EXPECTED, OVERALL)


#: A spot slot bought from a ``slot`` offer is placed as ``spot:<offer_id>``.
SPOT_PREFIX = "spot:"
#: Substitute gas delivered for an option lands as ``cover:<source_id>``.
COVER_PREFIX = "cover:"
#: Gas days a call holds a berth where the terminal terms do not say (desk standard).
DEFAULT_BERTH_DAYS = 1


class DisruptionError(ValueError):
    """An input the optimiser cannot work from."""


def _month(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def _days(first: date, last: date) -> Iterable[date]:
    day = first
    while day <= last:
        yield day
        day += timedelta(days=1)


def _fmt(value: float) -> str:
    return f"{value:,.0f}"


def _signed(value: float) -> str:
    return f"{value:+,.0f}"


# ------------------------------------------------------------------------------- inputs


@dataclass(frozen=True)
class SlotTerms:
    """A slot the book holds at a terminal and its day-by-day entitlement."""

    slot_id: str
    terminal: str
    hub: str
    start: date
    days: int
    send_out_mwh_per_day: float
    storage_mwh: float
    #: ``linear_decline`` (storage falls to zero over the slot) or ``flat``.
    profile: str = "linear_decline"
    #: What the secondary market would pay per MWh of send-out right if the slot is released
    #: unused (indicative); ``None``: not known, the slot is kept.
    release_value_eur_mwh: float | None = None
    #: The supply the slot is booked for; ``None``: a spare slot of the book.
    holder: str | None = None
    source: str = ""

    def __post_init__(self) -> None:
        if self.days <= 0:
            raise DisruptionError(f"slot {self.slot_id}: days must be positive")
        if self.send_out_mwh_per_day <= 0 or self.storage_mwh < 0:
            raise DisruptionError(f"slot {self.slot_id}: send-out must be positive")
        if self.profile not in ("linear_decline", "flat"):
            raise DisruptionError(f"slot {self.slot_id}: profile {self.profile!r} is unknown")

    @property
    def last_day(self) -> date:
        return self.start + timedelta(days=self.days - 1)

    def right(self, k: int) -> float:
        """The send-out right on slot day ``k`` (0-based)."""

        return self.send_out_mwh_per_day if 0 <= k < self.days else 0.0

    def storage_cap_end(self, k: int) -> float:
        """The storage right at the end of slot day ``k``."""

        if k < 0:
            return self.storage_mwh
        if k >= self.days - 1:
            return 0.0
        if self.profile == "flat":
            return self.storage_mwh
        return self.storage_mwh * (self.days - 1 - k) / self.days

    def entitlement(self) -> list[dict[str, Any]]:
        """The slot's rights day by day, for a reader."""

        return [
            {
                "gas_day": (self.start + timedelta(days=k)).isoformat(),
                "send_out_mwh": round(self.right(k), 1),
                "storage_end_mwh": round(self.storage_cap_end(k), 1),
            }
            for k in range(self.days)
        ]


@dataclass(frozen=True)
class Supply:
    """A cargo or pipeline supply of the portfolio."""

    supply_id: str
    label: str
    kind: str = LNG
    #: LNG: energy delivered at berth (after boil-off to the ETA and gas in kind).
    energy_mwh: float = 0.0
    #: LNG: the gas day the ship arrives at ``terminal`` (its ETA).
    arrival: date | None = None
    slot_id: str | None = None
    terminal: str | None = None
    eta_confidence: str | None = None
    laytime_hours: float = 36.0
    demurrage_eur_per_day: float = 0.0
    #: Energy that boils off per day of waiting at anchor.
    boil_off_mwh_per_day: float = 0.0
    #: Whether the cargo's contract lets the desk send it to another terminal.
    can_divert: bool = True
    diversion_note: str = ""
    #: The cargo's contract (Confirmation Notice) or pipeline supply contract, when held.
    contract_id: str | None = None
    #: How the demurrage rate was read and converted to EUR, for the arithmetic line.
    demurrage_note: str = ""
    #: Where the laytime and demurrage terms came from (Confirmation Notice, voyage terms...).
    demurrage_source: str = ""
    #: Pipeline: the hub, the delivery point and the daily quantity in ``[start, end]``.
    hub: str | None = None
    point: str | None = None
    daily_mwh: float = 0.0
    start: date | None = None
    end: date | None = None
    #: Pipeline: gas days with the energy not delivered on each.
    curtailed: tuple[tuple[date, float], ...] = ()
    #: Pipeline: what the contract charges per MWh delivered (not paid on gas not delivered).
    cost_eur_mwh: float = 0.0

    def __post_init__(self) -> None:
        if self.kind not in (LNG, PIPELINE):
            raise DisruptionError(f"supply {self.supply_id}: kind {self.kind!r} is unknown")
        if self.kind == LNG and (self.arrival is None or self.energy_mwh <= 0):
            raise DisruptionError(f"cargo {self.supply_id} needs an arrival and its energy")
        if self.kind == PIPELINE and (
            self.hub is None or self.start is None or self.end is None or self.daily_mwh <= 0
        ):
            raise DisruptionError(f"pipeline supply {self.supply_id} needs hub, period, MWh/d")


@dataclass(frozen=True)
class Obligation:
    """Gas the book must deliver at a terminal or point each day of a window."""

    obligation_id: str
    counterparty: str
    #: A terminal name (LNG send-out there counts) or a hub code (any supply at it counts).
    point: str
    hub: str
    start: date
    end: date
    mwh_per_day: float
    firm: bool = True
    #: A non-firm obligation: what each MWh short costs (``None`` counts as 0). A firm one:
    #: the contract's liquidated damages per MWh short, when the contract data holds them;
    #: ``None`` means the penalty is not held, so a breach is stated but not valued.
    penalty_eur_mwh: float | None = None
    contract_id: str | None = None
    tolerance_mwh: float = EPS_MWH
    #: The breach terms as the contract states them (a cap, a cure period), for the reader.
    penalty_terms: str = ""


@dataclass(frozen=True)
class CapacityOffer:
    """Terminal capacity the desk could borrow or buy (quoted, indicative or a tariff).

    ``borrow``: LNG lent in the tank by another user for gas days in the window, up to
    ``max_mwh_per_day``, returned from the cargo after it berths; ``price_eur_mwh`` per MWh
    borrowed. ``send_out``: extra firm send-out up to ``max_mwh_per_day``, per MWh sent.
    ``storage``: extra firm storage up to ``max_mwh``, per MWh and day. ``interruptible``:
    unused rights of other users, send-out per MWh (``price_eur_mwh``, up to
    ``max_mwh_per_day``) and storage per MWh and day (``storage_price_eur_mwh_day``, up to
    ``max_mwh``), granted only when others do not use them. ``slot`` (LNG-4): a spot slot at a
    terminal the book holds no slot at, from ``start`` to ``end`` with ``max_mwh_per_day``
    send-out and ``max_mwh`` storage (declining linearly), at ``price_eur_mwh`` per MWh of
    send-out right bought; ``hub`` names the hub its gas reaches.

    A per-day limit is shared by every cargo of the book at the terminal (LNG-4): what one
    cargo takes on a gas day is not there for the next.
    """

    offer_id: str
    terminal: str
    kind: str
    start: date
    end: date
    price_eur_mwh: float
    max_mwh_per_day: float = 0.0
    max_mwh: float = 0.0
    storage_price_eur_mwh_day: float = 0.0
    basis: str = "indicative"
    source: str = ""
    hub: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in ("borrow", "send_out", "storage", "interruptible", "slot"):
            raise DisruptionError(f"offer {self.offer_id}: kind {self.kind!r} is unknown")

    def covers(self, day: date) -> bool:
        return self.start <= day <= self.end

    @property
    def where(self) -> str:
        """The offer as a source for the arithmetic: its reference and basis."""

        return f"{self.source or self.offer_id} ({self.basis})"


@dataclass(frozen=True)
class BerthCall:
    """A ship due at a terminal's berth that the book does not place (LNG-4): another user's
    cargo in the terminal's line-up, where the data holds it. When an option puts a cargo on
    the berth while this call is due, the call waits and the option carries its cost: the
    demurrage past the laytime it has left and the boil-off of the wait."""

    call_id: str
    terminal: str
    label: str
    #: The gas day it is due to berth.
    berth: date
    hub: str = ""
    berth_days: int = 1
    #: Laytime the call has left when it is due to berth (hours).
    laytime_hours: float = 0.0
    demurrage_eur_per_day: float = 0.0
    boil_off_mwh_per_day: float = 0.0
    source: str = ""
    demurrage_note: str = ""


#: The kinds of substitute supply (LNG-4): gas the book holds upstream (an equity field or a
#: supply contract's swing), gas bought at a hub and moved on transport capacity, gas
#: withdrawn from the firm's storage.
SUBSTITUTE_KINDS = ("upstream", "hub", "storage")


@dataclass(frozen=True)
class SubstituteSource:
    """Gas from elsewhere in the portfolio that can reach a delivery point (LNG-4).

    It delivers at ``point`` (a delivery point or hub code an obligation names) up to
    ``max_mwh_per_day`` each gas day in ``[start, end]`` and ``max_mwh`` in all (0: no total).
    What it costs per MWh delivered:

    * ``upstream``: ``price_eur_mwh`` (the contract's price, in EUR) plus ``transport_eur_mwh``;
    * ``hub``: the month price at ``price_hub`` plus ``premium_eur_mwh`` (short notice) plus
      ``transport_eur_mwh`` (capacity to the point, contracted first, else the public tariff);
    * ``storage``: ``fee_eur_mwh`` (withdrawal) plus ``transport_eur_mwh`` paid now, and, as an
      opportunity cost, the value of the gas at ``price_hub`` in ``value_month``, the month it
      would otherwise have been withdrawn and sold.

    ``sources`` names where each figure came from (``gas``, ``transport``, ``fee``, ``value``,
    ``fx``), in the order they were applied.
    """

    source_id: str
    kind: str
    label: str
    point: str
    start: date
    end: date
    max_mwh_per_day: float
    max_mwh: float = 0.0
    price_eur_mwh: float | None = None
    price_hub: str | None = None
    premium_eur_mwh: float = 0.0
    transport_eur_mwh: float = 0.0
    fee_eur_mwh: float = 0.0
    value_month: str | None = None
    sources: Mapping[str, str] = field(default_factory=dict)
    note: str = ""

    def __post_init__(self) -> None:
        if self.kind not in SUBSTITUTE_KINDS:
            raise DisruptionError(f"substitute {self.source_id}: kind {self.kind!r} is unknown")
        if self.max_mwh_per_day <= 0:
            raise DisruptionError(f"substitute {self.source_id}: a daily quantity is needed")
        if self.kind == "upstream" and self.price_eur_mwh is None:
            raise DisruptionError(f"substitute {self.source_id}: an upstream price is needed")
        if self.kind in ("hub", "storage") and not self.price_hub:
            raise DisruptionError(f"substitute {self.source_id}: a price hub is needed")
        if self.kind == "storage" and not self.value_month:
            raise DisruptionError(f"substitute {self.source_id}: the month it would be used")

    def covers(self, day: date) -> bool:
        return self.start <= day <= self.end

    def direct_unit(self, market: Market, day: date, factor: float = 1.0) -> float | None:
        """EUR per MWh paid to deliver on ``day``."""

        if self.kind == "upstream":
            gas = self.price_eur_mwh or 0.0
        elif self.kind == "hub":
            price = market.price(self.price_hub or "", _month(day))
            if price is None:
                return None
            gas = price * factor + self.premium_eur_mwh
        else:
            gas = self.fee_eur_mwh
        return gas + self.transport_eur_mwh

    def forgone_unit(self, market: Market, factor: float = 1.0) -> float | None:
        """EUR per MWh of value given up elsewhere (storage gas not there when planned)."""

        if self.kind != "storage":
            return 0.0
        price = market.price(self.price_hub or "", self.value_month or "")
        return None if price is None else price * factor


@dataclass(frozen=True)
class Market:
    """Month prices per hub (EUR/MWh) and the instant the plan is judged at."""

    prices: Mapping[tuple[str, str], float]
    now: datetime
    holidays: tuple[date, ...] = ()
    #: Where each price came from, for the arithmetic.
    sources: Mapping[tuple[str, str], str] = field(default_factory=dict)

    def price(self, hub: str, month: str) -> float | None:
        return self.prices.get((hub.upper(), month))

    def trading(self, month: str) -> bool:
        return self.now.date() <= last_trading_day(month, self.holidays)

    @property
    def nominated_through(self) -> date:
        """The last gas day already nominated (and sold or bought) day-ahead."""

        return self.now.date() + timedelta(days=1)


@dataclass(frozen=True)
class DeskTerms:
    """Execution costs, scenario widths and the preference weights, with their sources."""

    trade_cost_eur_mwh: float = 0.01
    short_notice_premium_eur_mwh: float = 0.25
    cash_out_pct: float = 3.0
    stranded_discount_eur_mwh: float = 3.0
    price_shock_pct: float = 10.0
    eta_spread_days: Mapping[str, int] = field(
        default_factory=lambda: {"high": 0, "medium": 1, "low": 2, "": 2}
    )
    swap_cost_eur: float = 0.0
    risk_weight: float = 0.5
    disruption_eur_per_mwh: float = 0.5
    disruption_eur_per_supply: float = 0.0
    flexibility_eur_per_mwh: float = 0.0
    #: Ordering only: EUR taken off the score per contract an option breaks (LNG-4).
    breach_eur_per_contract: float = 0.0
    #: The value forgone per MWh of send-out right when a spare slot of the book is used and
    #: the slot holds no indicative release value: its best other use (LNG-4). ``None``: not
    #: held, so the forgone value is stated as not known and left out.
    spare_slot_value_eur_mwh: float | None = None
    #: Material change of the recommended option's expected P&L (EUR) for a new notice.
    material_change_eur: float = 50_000.0
    sources: Mapping[str, str] = field(default_factory=dict)

    def spread(self, confidence: str | None) -> int:
        return int(self.eta_spread_days.get(confidence or "", self.eta_spread_days.get("", 2)))


@dataclass(frozen=True)
class Portfolio:
    supplies: tuple[Supply, ...]
    slots: tuple[SlotTerms, ...]
    obligations: tuple[Obligation, ...] = ()
    offers: tuple[CapacityOffer, ...] = ()
    #: Extra sailing days to each terminal versus the reference terminal (lng_terminal_terms).
    sailing_days: Mapping[str, float] = field(default_factory=dict)
    #: Other users' ships due at the terminals' berths (LNG-4), where the data holds them.
    berth_calls: tuple[BerthCall, ...] = ()
    #: Gas days a cargo of the book holds a terminal's berth (berthing, unloading, sailing).
    berth_days: Mapping[str, int] = field(default_factory=dict)
    #: Gas from elsewhere in the portfolio that can cover a short delivery (LNG-4).
    substitutes: tuple[SubstituteSource, ...] = ()

    def slot(self, slot_id: str | None) -> SlotTerms | None:
        for slot in self.slots:
            if slot.slot_id == slot_id:
                return slot
        if slot_id and slot_id.startswith(SPOT_PREFIX):
            offer = next(
                (
                    o
                    for o in self.offers
                    if o.kind == "slot" and SPOT_PREFIX + o.offer_id == slot_id
                ),
                None,
            )
            if offer is not None:
                return spot_slot(offer)
        return None

    def berth_hold(self, terminal: str) -> int:
        return int(self.berth_days.get(terminal, DEFAULT_BERTH_DAYS))

    def spot_offers(self) -> list[CapacityOffer]:
        return sorted(
            (o for o in self.offers if o.kind == "slot"), key=lambda o: (o.terminal, o.offer_id)
        )

    def supply(self, supply_id: str) -> Supply:
        for supply in self.supplies:
            if supply.supply_id == supply_id:
                return supply
        raise DisruptionError(f"no supply {supply_id}")

    def offers_at(self, terminal: str, kind: str) -> list[CapacityOffer]:
        # TAR-2: capacity the firm holds (basis "contracted") before any public or quoted
        # offer, then the cheapest (domain/tariffs/precedence.offer_rank).
        return sorted(
            (o for o in self.offers if o.terminal == terminal and o.kind == kind),
            key=lambda o: (offer_rank(o.basis), o.price_eur_mwh, o.offer_id),
        )


def spot_slot(offer: CapacityOffer) -> SlotTerms:
    """The slot a ``slot`` offer would give the book."""

    return SlotTerms(
        slot_id=SPOT_PREFIX + offer.offer_id,
        terminal=offer.terminal,
        hub=(offer.hub or "").upper(),
        start=offer.start,
        days=(offer.end - offer.start).days + 1,
        send_out_mwh_per_day=offer.max_mwh_per_day,
        storage_mwh=offer.max_mwh,
        source=offer.where,
    )


# ------------------------------------------------------------------------- placements


@dataclass(frozen=True)
class Placement:
    """Where and how one supply lands in an option."""

    supply_id: str
    slot_id: str | None = None
    #: The arrival in the base scenario at that slot's terminal (LNG).
    arrival: date | None = None
    #: In-tank borrowing fixed in advance: (gas day, MWh).
    borrow: tuple[tuple[date, float], ...] = ()
    borrow_offer: str | None = None
    #: Extra firm send-out and storage booked at the terminal (daily products, up to limits).
    buy_offer: str | None = None
    storage_offer: str | None = None
    #: Pipeline cover: extra send-out from this cargo on fixed days, (gas day, MWh).
    cover: tuple[tuple[date, float], ...] = ()
    cover_offer: str | None = None


@dataclass(frozen=True)
class Landing:
    """One supply's day-by-day result in one scenario."""

    supply_id: str
    terminal: str
    hub: str
    flows: dict[date, float]
    stranded_mwh: float = 0.0
    stranded_month: str | None = None
    unhoused_mwh: float = 0.0
    unhoused_day: date | None = None
    wait_days: int = 0
    demurrage_eur: float = 0.0
    boil_off_mwh: float = 0.0
    boil_off_eur: float = 0.0
    fees: dict[str, float] = field(default_factory=dict)
    usage: dict[str, float] = field(default_factory=dict)
    berth: date | None = None
    returned: tuple[date, float] | None = None
    #: Gas days the berth was held for another call the option placed there (LNG-4).
    hold_days: int = 0
    held_by: str | None = None
    #: Where each fee's price came from (the offer's reference and basis).
    fee_sources: dict[str, str] = field(default_factory=dict)
    #: The hub the ship's own gas is priced at (boil-off).
    price_source: str = ""


@dataclass(frozen=True)
class Cover:
    """Substitute gas delivered at an obligation's point on fixed gas days (LNG-4)."""

    source_id: str
    obligation_id: str
    days: tuple[tuple[date, float], ...]

    @property
    def mwh(self) -> float:
        return sum(mwh for _, mwh in self.days)


class Pool:
    """What is left of each shared per-day limit of the terminals' offers (LNG-4)."""

    def __init__(self) -> None:
        self.used: dict[tuple[str, str, date], float] = {}

    def left(self, offer: CapacityOffer, what: str, day: date, limit: float) -> float:
        return max(0.0, limit - self.used.get((offer.offer_id, what, day), 0.0))

    def take(self, offer: CapacityOffer, what: str, day: date, mwh: float) -> None:
        key = (offer.offer_id, what, day)
        self.used[key] = self.used.get(key, 0.0) + mwh


def _arrival_at(supply: Supply, terminal: str, sailing: Mapping[str, float]) -> date:
    """The gas day the cargo can reach ``terminal``: its ETA plus the sailing difference."""

    assert supply.arrival is not None
    if supply.terminal is None or terminal == supply.terminal:
        return supply.arrival
    diff = sailing.get(terminal, 0.0) - sailing.get(supply.terminal, 0.0)
    return supply.arrival + timedelta(days=round(diff))


def _land(
    portfolio: Portfolio,
    supply: Supply,
    placement: Placement,
    arrival: date,
    market: Market,
    *,
    strand_unhoused: bool,
    hold_days: int = 0,
    held_by: str | None = None,
    pool: Pool | None = None,
) -> Landing:
    """Simulate a cargo landing at its placed slot, gas day by gas day.

    ``hold_days``: the berth is taken by another call for that many gas days after the ship
    could berth, so it waits at anchor longer. ``pool``: the shared per-day limits of the
    terminal's offers, drawn down by the cargoes landed before this one.
    """

    slot = portfolio.slot(placement.slot_id)
    if slot is None:
        return Landing(supply.supply_id, supply.terminal or "", "", {}, supply.energy_mwh, None)
    offers = {o.offer_id: o for o in portfolio.offers}
    buy = offers.get(placement.buy_offer or "")
    storage = offers.get(placement.storage_offer or "")
    cover = offers.get(placement.cover_offer or "")
    interruptible = next(iter(portfolio.offers_at(slot.terminal, "interruptible")), None)
    borrowed = {day: mwh for day, mwh in placement.borrow}
    covered = {day: mwh for day, mwh in placement.cover}
    borrow_offer = offers.get(placement.borrow_offer or "")
    borrow_fee = borrow_offer.price_eur_mwh if borrow_offer is not None else 0.0
    shared = pool if pool is not None else Pool()
    trial = Pool()

    k_arrival = (arrival - slot.start).days
    wait_days = max(0, -k_arrival) + hold_days
    berth_k = max(0, k_arrival) + hold_days
    berth = slot.start + timedelta(days=berth_k)
    energy = supply.energy_mwh
    stranded = 0.0
    for _attempt in range(2):
        trial = Pool()
        trial.used = dict(shared.used)
        flows: dict[date, float] = {}
        fees: dict[str, float] = {}
        usage: dict[str, float] = {}
        inventory = 0.0
        liability = 0.0
        unhoused = 0.0
        unhoused_day = None
        returned = None
        last_k = slot.days + TAIL_DAYS
        for k in range(0, last_k):
            day = slot.start + timedelta(days=k)
            right = slot.right(k)
            sent = 0.0
            lend = borrowed.get(day, 0.0)
            if lend > 0 and borrow_offer is not None:
                lend = min(
                    lend, right, trial.left(borrow_offer, "lend", day, borrow_offer.max_mwh_per_day)
                )
                trial.take(borrow_offer, "lend", day, lend)
                sent += lend
                liability += lend
                right -= lend
                usage["borrowed_mwh"] = usage.get("borrowed_mwh", 0.0) + lend
                fees["borrow"] = fees.get("borrow", 0.0) + lend * borrow_fee
            if k == berth_k:
                inventory += energy
                if liability > 0:
                    pay = min(liability, inventory)
                    inventory -= pay
                    liability -= pay
                    returned = (day, pay)
            if k >= berth_k:
                own = min(inventory, right)
                inventory -= own
                sent += own
                fixed = min(covered.get(day, 0.0), inventory)
                if fixed > 0 and cover is not None:
                    inventory -= fixed
                    sent += fixed
                    usage["cover_mwh"] = usage.get("cover_mwh", 0.0) + fixed
                    fees["cover_send_out"] = fees.get("cover_send_out", 0.0) + (
                        fixed * cover.price_eur_mwh
                    )
                ahead = slot.send_out_mwh_per_day * max(0, slot.days - k - 1)
                if buy is not None and buy.covers(day) and inventory > ahead + EPS_MWH:
                    extra = min(
                        inventory - ahead, trial.left(buy, "send", day, buy.max_mwh_per_day)
                    )
                    trial.take(buy, "send", day, extra)
                    inventory -= extra
                    sent += extra
                    usage["extra_send_out_mwh"] = usage.get("extra_send_out_mwh", 0.0) + extra
                    fees["extra_send_out"] = fees.get("extra_send_out", 0.0) + (
                        extra * buy.price_eur_mwh
                    )
                if (
                    k >= slot.days
                    and inventory > EPS_MWH
                    and interruptible is not None
                    and interruptible.covers(day)
                ):
                    extra = min(
                        inventory,
                        trial.left(interruptible, "send", day, interruptible.max_mwh_per_day),
                    )
                    trial.take(interruptible, "send", day, extra)
                    inventory -= extra
                    sent += extra
                    usage["interruptible_send_out_mwh"] = (
                        usage.get("interruptible_send_out_mwh", 0.0) + extra
                    )
                    fees["interruptible_send_out"] = fees.get("interruptible_send_out", 0.0) + (
                        extra * interruptible.price_eur_mwh
                    )
                over = inventory - slot.storage_cap_end(k)
                if over > EPS_MWH:
                    if storage is not None and storage.covers(day):
                        held = min(over, trial.left(storage, "store", day, storage.max_mwh))
                        trial.take(storage, "store", day, held)
                        over -= held
                        usage["extra_storage_mwh_days"] = (
                            usage.get("extra_storage_mwh_days", 0.0) + held
                        )
                        fees["extra_storage"] = fees.get("extra_storage", 0.0) + (
                            held * storage.price_eur_mwh
                        )
                    if over > EPS_MWH and interruptible is not None and interruptible.covers(day):
                        held = (
                            min(
                                over, trial.left(interruptible, "store", day, interruptible.max_mwh)
                            )
                            if interruptible.max_mwh
                            else over
                        )
                        trial.take(interruptible, "store", day, held)
                        over -= held
                        usage["interruptible_storage_mwh_days"] = (
                            usage.get("interruptible_storage_mwh_days", 0.0) + held
                        )
                        fees["interruptible_storage"] = (
                            fees.get("interruptible_storage", 0.0)
                            + held * interruptible.storage_price_eur_mwh_day
                        )
                    if over > unhoused + EPS_MWH:
                        unhoused = over
                        unhoused_day = unhoused_day or day
            if sent > 0:
                flows[day] = flows.get(day, 0.0) + sent
            if k >= berth_k and inventory <= EPS_MWH and liability <= EPS_MWH:
                break
        leftover = inventory if inventory > EPS_MWH else 0.0
        if strand_unhoused and unhoused > EPS_MWH and _attempt == 0:
            # In a scenario the part that has no storage right cannot be unloaded: it is
            # stranded aboard and sold where it lies; land the rest.
            stranded = unhoused
            energy = max(supply.energy_mwh - unhoused, 0.0)
            continue
        stranded += leftover
        break
    shared.used = trial.used

    fee_sources = {}
    for name, offer in (
        ("borrow", borrow_offer),
        ("extra_send_out", buy),
        ("extra_storage", storage),
        ("interruptible_send_out", interruptible),
        ("interruptible_storage", interruptible),
        ("cover_send_out", cover),
    ):
        if offer is not None and name in fees:
            fee_sources[name] = offer.where
    wait_hours = wait_days * 24.0
    demurrage = max(0.0, wait_hours - supply.laytime_hours) / 24.0 * supply.demurrage_eur_per_day
    boil = wait_days * supply.boil_off_mwh_per_day
    price = market.price(slot.hub, _month(berth)) or 0.0
    return Landing(
        supply_id=supply.supply_id,
        terminal=slot.terminal,
        hub=slot.hub,
        flows=flows,
        stranded_mwh=stranded,
        stranded_month=_month(slot.last_day) if stranded > EPS_MWH else None,
        unhoused_mwh=0.0 if strand_unhoused else unhoused,
        unhoused_day=None if strand_unhoused else unhoused_day,
        wait_days=wait_days,
        demurrage_eur=demurrage,
        boil_off_mwh=boil,
        boil_off_eur=boil * price,
        fees=fees,
        usage=usage,
        berth=berth,
        returned=returned,
        hold_days=hold_days,
        held_by=held_by,
        fee_sources=fee_sources,
        price_source=market.sources.get((slot.hub.upper(), _month(berth)), ""),
    )


def _pipeline_flows(supply: Supply, *, curtailed: bool) -> Landing:
    assert supply.start is not None and supply.end is not None and supply.hub is not None
    lost = {day: mwh for day, mwh in supply.curtailed} if curtailed else {}
    flows = {
        day: max(supply.daily_mwh - lost.get(day, 0.0), 0.0)
        for day in _days(supply.start, supply.end)
    }
    return Landing(supply.supply_id, supply.point or supply.hub, supply.hub, flows)


# ------------------------------------------------------------------------------ options


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    label: str
    #: Days added to each disrupted cargo's arrival.
    eta_shift_days: int = 0
    price_factor: float = 1.0


@dataclass
class Valuation:
    """The P&L change of one option in one scenario, by component (EUR)."""

    scenario: Scenario
    physical_moved: float = 0.0
    hedge_cost: float = 0.0
    cash_out: float = 0.0
    capacity_fees: float = 0.0
    demurrage: float = 0.0
    boil_off: float = 0.0
    stranded: float = 0.0
    release: float = 0.0
    swap_cost: float = 0.0
    obligation_penalty: float = 0.0
    #: Liquidated damages for a firm obligation the option breaks, where the contract holds
    #: them (LNG-4); a breach whose penalty is not held adds nothing here and says so.
    contract_exposure: float = 0.0
    #: Substitute gas bought or drawn to cover a short delivery: gas, fees, transport (LNG-4).
    substitute_cost: float = 0.0
    #: Opportunity cost (LNG-4): what the option does to the rest of the book's cargoes (a
    #: berth taken, shared send-out or storage left short) ...
    knock_on: float = 0.0
    #: ... to other users' ships due at a berth it takes (demurrage past laytime, boil-off) ...
    displaced_calls: float = 0.0
    #: ... the value forgone of a spare slot it uses (release value or best other use) ...
    capacity_forgone: float = 0.0
    #: ... and the value of storage gas at the time it would otherwise have been used.
    storage_forgone: float = 0.0
    lines: list[dict[str, Any]] = field(default_factory=list)
    hedge_legs: list[dict[str, Any]] = field(default_factory=list)
    landings: dict[str, Landing] = field(default_factory=dict)
    #: The consequences behind the opportunity cost, each naming the cargo it hits.
    opportunity: list[dict[str, Any]] = field(default_factory=list)

    @property
    def opportunity_cost(self) -> float:
        return self.knock_on + self.displaced_calls + self.capacity_forgone + self.storage_forgone

    @property
    def direct_pnl(self) -> float:
        """The P&L change before the opportunity cost."""

        return self.pnl + self.opportunity_cost

    @property
    def pnl(self) -> float:
        return (
            self.physical_moved
            - self.hedge_cost
            - self.cash_out
            - self.capacity_fees
            - self.demurrage
            - self.boil_off
            - self.stranded
            + self.release
            - self.swap_cost
            - self.obligation_penalty
            - self.contract_exposure
            - self.substitute_cost
            - self.knock_on
            - self.displaced_calls
            - self.capacity_forgone
            - self.storage_forgone
        )

    @property
    def cash_cost(self) -> float:
        return (
            self.hedge_cost
            + self.cash_out
            + self.capacity_fees
            + self.demurrage
            + self.swap_cost
            + self.obligation_penalty
            + self.contract_exposure
            + self.substitute_cost
        )

    def components(self) -> dict[str, float]:
        return {
            "physical_moved": round(self.physical_moved, 2),
            "hedge_cost": round(-self.hedge_cost, 2),
            "cash_out": round(-self.cash_out, 2),
            "capacity_fees": round(-self.capacity_fees, 2),
            "demurrage": round(-self.demurrage, 2),
            "boil_off": round(-self.boil_off, 2),
            "stranded": round(-self.stranded, 2),
            "release": round(self.release, 2),
            "swap_cost": round(-self.swap_cost, 2),
            "obligation_penalty": round(-self.obligation_penalty, 2),
            "contract_exposure": round(-self.contract_exposure, 2),
            "substitute_cost": round(-self.substitute_cost, 2),
            "knock_on": round(-self.knock_on, 2),
            "displaced_calls": round(-self.displaced_calls, 2),
            "capacity_forgone": round(-self.capacity_forgone, 2),
            "storage_forgone": round(-self.storage_forgone, 2),
        }

    def split(self) -> dict[str, float]:
        """Direct P&L, opportunity cost and the P&L that includes both (EUR)."""

        return {
            "direct_pnl": round(self.direct_pnl, 2),
            "opportunity_cost": round(self.opportunity_cost, 2),
            "pnl": round(self.pnl, 2),
        }


@dataclass
class Option:
    option_id: str
    key: str
    kind: str
    title: str
    placements: dict[str, Placement]
    releases: tuple[str, ...] = ()
    swaps: tuple[tuple[str, str], ...] = ()
    #: Substitute gas delivered to cover a short obligation (LNG-4).
    covers: tuple[Cover, ...] = ()
    feasible: bool = True
    reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    base: Valuation | None = None
    scenarios: list[Valuation] = field(default_factory=list)
    objectives: dict[str, float] = field(default_factory=dict)
    disrupted_supplies: list[str] = field(default_factory=list)
    interruptible_mwh: float = 0.0
    obligations: list[dict[str, Any]] = field(default_factory=list)
    #: Contracts the option breaks (LNG-4): what, how and the exposure where it is held.
    breaches: list[dict[str, Any]] = field(default_factory=list)
    #: Supplies running to plan that the option moves, with the MWh moved.
    disrupts: list[dict[str, Any]] = field(default_factory=list)
    score: float = 0.0
    on_frontier: bool = False
    dominated_by: str | None = None
    dominated_why: list[str] = field(default_factory=list)
    #: Place in the ranked list of possible options (1 is first); ``None``: not possible.
    rank: int | None = None
    #: The bases it is recommended on (``clean``, ``best_expected``, ``overall``) and why.
    recommended_as: list[str] = field(default_factory=list)
    recommended_why: list[str] = field(default_factory=list)

    @property
    def flags(self) -> dict[str, bool]:
        """The consequences a trader weighs, as labelled flags."""

        return {
            "physically_possible": self.feasible,
            "contract_breach": bool(self.breaches),
            "disrupts_normal_cargo": bool(self.disrupts),
        }


def _option_id(key: str) -> str:
    return "opt-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def disrupted(portfolio: Portfolio) -> list[Supply]:
    """The supplies that cannot run as planned: a cargo that berths after its slot starts
    (it loses slot days) and a pipeline supply with curtailed days."""

    out = []
    for supply in portfolio.supplies:
        if supply.kind == PIPELINE:
            if any(mwh > EPS_MWH for _, mwh in supply.curtailed):
                out.append(supply)
            continue
        slot = portfolio.slot(supply.slot_id)
        if slot is not None and supply.arrival is not None and supply.arrival > slot.start:
            out.append(supply)
    return out


def _planned_arrival(portfolio: Portfolio, supply: Supply, hit: set[str]) -> date | None:
    """The arrival the plan before the disruption assumed: the slot's first day for a
    disrupted cargo (the slot was booked for it), else its ETA."""

    if supply.supply_id in hit:
        slot = portfolio.slot(supply.slot_id)
        if slot is not None:
            return slot.start
    return supply.arrival


def _borrow_days(
    portfolio: Portfolio, supply: Supply, slot: SlotTerms, arrival: date
) -> tuple[tuple[tuple[date, float], ...], str | None]:
    """Borrow for each slot day before the berth, up to the energy the late berth leaves
    without a send-out right, from the cheapest in-tank offer at the terminal."""

    berth_k = max(0, (arrival - slot.start).days)
    if berth_k <= 0:
        return (), None
    gap = supply.energy_mwh - slot.send_out_mwh_per_day * max(0, slot.days - berth_k)
    for offer in portfolio.offers_at(slot.terminal, "borrow"):
        days = []
        left = gap
        for k in range(berth_k):
            day = slot.start + timedelta(days=k)
            if left <= EPS_MWH or not offer.covers(day):
                continue
            amount = min(slot.send_out_mwh_per_day, offer.max_mwh_per_day, left)
            if amount > EPS_MWH:
                days.append((day, amount))
                left -= amount
        if days:
            return tuple(days), offer.offer_id
    return (), None


def _capacity_variants(
    portfolio: Portfolio, supply: Supply, slot: SlotTerms, arrival: date
) -> list[tuple[str, Placement]]:
    """How a cargo can land at ``slot``: absorb, borrow, buy, borrow and buy."""

    base = Placement(supply.supply_id, slot.slot_id, arrival)
    variants = [("absorb", base)]
    late = arrival > slot.start
    borrow, offer = _borrow_days(portfolio, supply, slot, arrival) if late else ((), None)
    buy = next(iter(portfolio.offers_at(slot.terminal, "send_out")), None)
    storage = next(iter(portfolio.offers_at(slot.terminal, "storage")), None)
    if borrow:
        variants.append(("borrow", replace(base, borrow=borrow, borrow_offer=offer)))
    gap = supply.energy_mwh - slot.send_out_mwh_per_day * max(
        0, slot.days - max(0, (arrival - slot.start).days)
    )
    if late and buy is not None:
        bought = replace(
            base,
            buy_offer=buy.offer_id,
            storage_offer=None if storage is None else storage.offer_id,
        )
        variants.append(("buy", bought))
        borrowed = sum(mwh for _, mwh in borrow)
        if borrow and borrowed < gap - EPS_MWH:
            variants.append(("borrow_buy", replace(bought, borrow=borrow, borrow_offer=offer)))
    return variants


_CAPACITY_WORDS = {
    "absorb": "absorb the delay",
    "borrow": "borrow in tank before berthing, return after",
    "buy": "buy extra send-out and storage",
    "borrow_buy": "borrow in tank and buy extra send-out",
}


def generate(portfolio: Portfolio, market: Market, terms: DeskTerms) -> list[Option]:
    """The option set for every disrupted supply, combined across supplies (bounded)."""

    hit = disrupted(portfolio)
    per_supply: list[list[tuple[str, str, str, dict[str, Placement], tuple, tuple, list[str]]]] = []
    for supply in hit:
        per_supply.append(_supply_options(portfolio, supply, market)[:MAX_OPTIONS_PER_SUPPLY])
    options: list[Option] = []
    if not per_supply:
        return options
    combos = list(product(*per_supply))[:MAX_COMBINATIONS]
    for combo in combos:
        placements: dict[str, Placement] = {}
        releases: list[str] = []
        swaps: list[tuple[str, str]] = []
        notes: list[str] = []
        keys, titles, kinds = [], [], []
        clash = False
        for key, kind, title, placed, released, swapped, note in combo:
            for supply_id, placement in placed.items():
                if supply_id in placements and placements[supply_id] != placement:
                    clash = True
                placements[supply_id] = placement
            releases.extend(released)
            swaps.extend(swapped)
            notes.extend(note)
            keys.append(key)
            titles.append(title)
            kinds.append(kind)
        used = [p.slot_id for p in placements.values() if p.slot_id is not None]
        if clash or len(used) != len(set(used)) or set(used) & set(releases):
            continue
        key = " | ".join(keys)
        options.append(
            Option(
                option_id=_option_id(key),
                key=key,
                kind=kinds[0] if len(kinds) == 1 else "combined",
                title="; ".join(titles),
                placements=placements,
                releases=tuple(sorted(set(releases))),
                swaps=tuple(swaps),
                notes=notes,
            )
        )
    return options


def _supply_options(portfolio: Portfolio, supply: Supply, market: Market):
    """``(key, kind, title, placements, releases, swaps, notes)`` for one disrupted supply."""

    out = []
    hit = disrupted(portfolio)
    if supply.kind == PIPELINE:
        out.append(
            (
                f"{supply.supply_id}:absorb",
                "absorb",
                f"{supply.label}: absorb the curtailment and re-hedge",
                {},
                (),
                (),
                [],
            )
        )
        for cargo in portfolio.supplies:
            if cargo.kind != LNG or cargo in hit:
                continue
            slot = portfolio.slot(cargo.slot_id)
            if slot is None or slot.hub != supply.hub:
                continue
            offer = next(iter(portfolio.offers_at(slot.terminal, "send_out")), None)
            if offer is None:
                continue
            days = tuple(
                (day, min(mwh, offer.max_mwh_per_day))
                for day, mwh in supply.curtailed
                if offer.covers(day) and slot.start <= day and mwh > EPS_MWH
            )
            if not days:
                continue
            placement = Placement(
                cargo.supply_id,
                cargo.slot_id,
                cargo.arrival,
                cover=days,
                cover_offer=offer.offer_id,
            )
            out.append(
                (
                    f"{supply.supply_id}:cover:{cargo.supply_id}",
                    "cover",
                    f"{supply.label}: cover from {cargo.label}'s send-out at {slot.terminal}",
                    {cargo.supply_id: placement},
                    (),
                    (),
                    [],
                )
            )
        return out

    own = portfolio.slot(supply.slot_id)
    positions: list[tuple[str, str, SlotTerms, tuple, tuple, list[str]]] = []
    if own is not None:
        positions.append(("stay", f"stay at {own.terminal}", own, (), (), []))
    for slot in portfolio.slots:
        if slot.holder is not None or own is None or slot.slot_id == own.slot_id:
            continue
        reach = _arrival_at(supply, slot.terminal, portfolio.sailing_days)
        if (reach - slot.start).days >= slot.days:
            continue
        released = (own.slot_id,) if own.release_value_eur_mwh is not None else ()
        note = (
            []
            if supply.can_divert
            else [supply.diversion_note or "the cargo's contract does not allow a diversion"]
        )
        positions.append(
            (f"divert:{slot.slot_id}", f"divert to {slot.terminal}", slot, released, (), note)
        )
    for offer in portfolio.spot_offers():
        if own is None or offer.terminal == own.terminal:
            continue
        slot = spot_slot(offer)
        reach = _arrival_at(supply, slot.terminal, portfolio.sailing_days)
        if (reach - slot.start).days >= slot.days:
            continue
        released = (own.slot_id,) if own.release_value_eur_mwh is not None else ()
        note = (
            []
            if supply.can_divert
            else [supply.diversion_note or "the cargo's contract does not allow a diversion"]
        )
        positions.append(
            (
                f"spot:{offer.offer_id}",
                f"buy a spot slot at {offer.terminal}",
                slot,
                released,
                (),
                note,
            )
        )
    for other in portfolio.supplies:
        if other.kind != LNG or other.supply_id == supply.supply_id or own is None:
            continue
        theirs = portfolio.slot(other.slot_id)
        if theirs is None or theirs.terminal == own.terminal:
            continue
        mine_there = _arrival_at(supply, theirs.terminal, portfolio.sailing_days)
        theirs_here = _arrival_at(other, own.terminal, portfolio.sailing_days)
        if (mine_there - theirs.start).days >= theirs.days:
            continue
        if (theirs_here - own.start).days >= own.days:
            continue
        positions.append(
            (
                f"swap:{other.supply_id}",
                f"swap terminals with {other.label}",
                theirs,
                (),
                ((supply.supply_id, other.supply_id),),
                [],
            )
        )

    for position, words, slot, released, swaps, note in positions:
        arrival = _arrival_at(supply, slot.terminal, portfolio.sailing_days)
        for capacity, placement in _capacity_variants(portfolio, supply, slot, arrival):
            placed = {supply.supply_id: placement}
            if swaps:
                other = portfolio.supply(swaps[0][1])
                placed[other.supply_id] = Placement(
                    other.supply_id,
                    own.slot_id if own else None,
                    _arrival_at(other, own.terminal, portfolio.sailing_days) if own else None,
                )
            kind = "wait" if position == "stay" else position.split(":", 1)[0]
            if kind == "wait" and capacity != "absorb":
                kind = capacity
            out.append(
                (
                    f"{supply.supply_id}:{position}+{capacity}",
                    kind,
                    f"{supply.label}: {words}, {_CAPACITY_WORDS[capacity]}",
                    placed,
                    released,
                    swaps,
                    list(note),
                )
            )
    return out


# ---------------------------------------------------------------------------- valuation


def _scenarios(portfolio: Portfolio, terms: DeskTerms) -> list[Scenario]:
    hit = disrupted(portfolio)
    spread = max((terms.spread(s.eta_confidence) for s in hit if s.kind == LNG), default=0)
    out = [Scenario("base", "ETA as reported, prices as marked")]
    if spread:
        out.append(Scenario("early", f"ETA {spread} day(s) earlier", eta_shift_days=-spread))
        out.append(Scenario("late", f"ETA {spread} day(s) later", eta_shift_days=spread))
    if terms.price_shock_pct:
        shock = terms.price_shock_pct / 100
        out.append(
            Scenario("prices_up", f"prices +{terms.price_shock_pct:g} %", price_factor=1 + shock)
        )
        out.append(
            Scenario("prices_down", f"prices -{terms.price_shock_pct:g} %", price_factor=1 - shock)
        )
    return out


def _landings(
    portfolio: Portfolio,
    market: Market,
    placements: Mapping[str, Placement],
    *,
    planned: bool,
    shift: int,
    strand: bool,
    plan: Mapping[str, Landing] | None = None,
    knock_on: bool = True,
    covers: tuple[Cover, ...] = (),
) -> dict[str, Landing]:
    """Every supply landed for an option (or the plan, ``planned``).

    For an option (LNG-4), the cargoes it places somewhere or on a day other than the plan's
    (``plan``) are "moved": they land first, take the berth on the day they can, and draw the
    terminals' shared per-day limits first. Every other cargo then lands in berth order: one
    whose berth a moved cargo holds waits until it is free, and each finds only what the moved
    cargoes left of a shared limit. With ``knock_on`` false the other cargoes land as if the
    moved ones took nothing from them: the difference is the option's knock-on on the rest of
    the portfolio. ``covers`` add the substitute gas the option delivers.
    """

    hit = {s.supply_id for s in disrupted(portfolio)}
    out: dict[str, Landing] = {}
    wanted: dict[str, tuple[Placement, date | None]] = {}
    for supply in portfolio.supplies:
        if supply.kind == PIPELINE:
            out[supply.supply_id] = _pipeline_flows(supply, curtailed=not planned)
            continue
        placement = placements.get(supply.supply_id) if not planned else None
        if placement is None:
            placement = Placement(supply.supply_id, supply.slot_id, supply.arrival)
        slot = portfolio.slot(placement.slot_id)
        if planned:
            arrival = _planned_arrival(portfolio, supply, hit)
        else:
            arrival = (
                _arrival_at(supply, slot.terminal, portfolio.sailing_days)
                if slot is not None
                else supply.arrival
            )
            if supply.supply_id in hit:
                arrival = arrival + timedelta(days=shift)
        wanted[supply.supply_id] = (placement, arrival)

    def berth_of(supply_id: str) -> tuple[str, date | None]:
        placement, arrival = wanted[supply_id]
        slot = portfolio.slot(placement.slot_id)
        if slot is None or arrival is None:
            return "", arrival
        return slot.terminal, slot.start + timedelta(days=max(0, (arrival - slot.start).days))

    moved = set()
    if plan is not None:
        for supply_id in wanted:
            was = plan.get(supply_id)
            terminal, day = berth_of(supply_id)
            if was is None or was.terminal != terminal or was.berth != day:
                moved.add(supply_id)
    order = sorted(
        wanted,
        key=lambda sid: (sid not in moved, berth_of(sid)[1] or date.max, sid),
    )
    pool, free_pool = Pool(), Pool()
    busy: dict[str, list[tuple[date, date, str]]] = {}
    for supply_id in order:
        supply = portfolio.supply(supply_id)
        placement, arrival = wanted[supply_id]
        terminal, day = berth_of(supply_id)
        hold, held_by = 0, None
        use = pool
        if supply_id not in moved and moved and not knock_on:
            use = free_pool
        elif supply_id not in moved and day is not None:
            for first, last, who in sorted(busy.get(terminal, [])):
                start = day + timedelta(days=hold)
                if first <= start <= last:
                    hold = (last - day).days + 1
                    held_by = who
        landing = _land(
            portfolio,
            supply,
            placement,
            arrival or supply.arrival,
            market,
            strand_unhoused=strand,
            hold_days=hold,
            held_by=held_by,
            pool=use,
        )
        out[supply_id] = landing
        if supply_id in moved and landing.berth is not None:
            stay = portfolio.berth_hold(landing.terminal)
            busy.setdefault(landing.terminal, []).append(
                (landing.berth, landing.berth + timedelta(days=stay - 1), supply.label)
            )
    by_id = {item.obligation_id: item for item in portfolio.obligations}
    sources = {item.source_id: item for item in portfolio.substitutes}
    for cover in covers:
        item, source = by_id.get(cover.obligation_id), sources.get(cover.source_id)
        if item is None or source is None:
            continue
        out[COVER_PREFIX + cover.source_id] = Landing(
            supply_id=COVER_PREFIX + cover.source_id,
            terminal=item.point,
            hub=item.hub,
            flows={d: m for d, m in cover.days},
        )
    return out


def moved_berths(
    portfolio: Portfolio, landings: Mapping[str, Landing], plan: Mapping[str, Landing]
) -> dict[str, list[tuple[date, date, str]]]:
    """The berth days the cargoes an option moved hold, per terminal."""

    out: dict[str, list[tuple[date, date, str]]] = {}
    for supply_id, landing in landings.items():
        was = plan.get(supply_id)
        if supply_id.startswith(COVER_PREFIX) or landing.berth is None:
            continue
        if was is not None and was.terminal == landing.terminal and was.berth == landing.berth:
            continue
        stay = portfolio.berth_hold(landing.terminal)
        label = portfolio.supply(supply_id).label
        out.setdefault(landing.terminal, []).append(
            (landing.berth, landing.berth + timedelta(days=stay - 1), label)
        )
    return out


def _by_hub_month(
    landings: Mapping[str, Landing], skip_through: date | None = None
) -> dict[tuple[str, str], float]:
    out: dict[tuple[str, str], float] = {}
    for landing in landings.values():
        for day, mwh in landing.flows.items():
            if skip_through is not None and day <= skip_through:
                continue
            key = (landing.hub, _month(day))
            out[key] = out.get(key, 0.0) + mwh
        if landing.stranded_mwh > EPS_MWH and landing.stranded_month:
            key = (landing.hub, landing.stranded_month)
            out[key] = out.get(key, 0.0) + landing.stranded_mwh
    return out


def _by_hub_day(landings: Mapping[str, Landing]) -> dict[tuple[str, date], float]:
    out: dict[tuple[str, date], float] = {}
    for landing in landings.values():
        for day, mwh in landing.flows.items():
            out[(landing.hub, day)] = out.get((landing.hub, day), 0.0) + mwh
    return out


def _value(
    portfolio: Portfolio,
    market: Market,
    terms: DeskTerms,
    option: Option,
    scenario: Scenario,
    before: Mapping[str, Landing],
) -> Valuation:
    """The option's P&L change in one scenario: its direct effect (the cargoes it places, the
    capacity it buys, the substitute gas it brings in) and its opportunity cost (LNG-4): what
    it does to the rest of the portfolio (a cargo whose berth it takes, the shared send-out or
    storage it leaves less of), to other users' ships due at a berth it takes, and the value
    of what it uses that could have been used or released elsewhere."""

    strand = scenario.scenario_id != "base"
    common = {
        "planned": False,
        "shift": scenario.eta_shift_days,
        "strand": strand,
        "plan": before,
        "covers": option.covers,
    }
    after = _landings(portfolio, market, option.placements, knock_on=True, **common)
    free = _landings(portfolio, market, option.placements, knock_on=False, **common)
    full = _direct(portfolio, market, terms, option, scenario, before, after)
    v = _direct(portfolio, market, terms, option, scenario, before, free)
    v.landings = after
    v.hedge_legs = full.hedge_legs
    _knock_on(portfolio, market, v, full, free, after, before, scenario)
    _displaced_calls(portfolio, market, v, after, before, scenario)
    _forgone(portfolio, market, terms, option, v, scenario)
    return v


def _direct(
    portfolio: Portfolio,
    market: Market,
    terms: DeskTerms,
    option: Option,
    scenario: Scenario,
    before: Mapping[str, Landing],
    after: Mapping[str, Landing],
) -> Valuation:
    v = Valuation(scenario=scenario, landings=dict(after))
    factor = scenario.price_factor
    nominated = market.nominated_through

    # Physical moved, valued at the hub's month price.
    was = _by_hub_month(before)
    now = _by_hub_month(after)
    for key in sorted(set(was) | set(now), key=lambda k: (k[1], k[0])):
        change = now.get(key, 0.0) - was.get(key, 0.0)
        if abs(change) < EPS_MWH:
            continue
        price = market.price(*key)
        if price is None:
            v.lines.append(
                {
                    "label": f"{key[0]} {key[1]}",
                    "value": 0.0,
                    "text": f"{key[0]} {key[1]}: {_signed(change)} MWh has no price; not valued",
                    "sources": [f"no {key[0]} {key[1]} price held"],
                }
            )
            continue
        amount = change * price * factor
        v.physical_moved += amount
        v.lines.append(
            {
                "label": f"physical {key[0]} {key[1]}",
                "value": round(amount, 2),
                "text": f"{key[0]} {key[1]}: {_signed(change)} MWh x {price * factor:,.2f} "
                f"= {_signed(amount)} EUR",
                "sources": [_price_source(market, *key, factor)],
            }
        )

    # A pipeline supply's gas that is not delivered is not paid for either.
    for supply in portfolio.supplies:
        if supply.kind != PIPELINE or not supply.cost_eur_mwh:
            continue
        change = sum(after[supply.supply_id].flows.values()) - sum(
            before[supply.supply_id].flows.values()
        )
        if abs(change) < EPS_MWH:
            continue
        amount = -change * supply.cost_eur_mwh
        v.physical_moved += amount
        v.lines.append(
            {
                "label": f"contract {supply.supply_id}",
                "value": round(amount, 2),
                "text": f"{supply.label}: {_signed(change)} MWh at the contract price "
                f"{supply.cost_eur_mwh:,.2f} = {_signed(amount)} EUR",
                "sources": [f"supply contract {supply.contract_id or supply.supply_id} price"],
            }
        )

    # Re-align hedges per hub and month (gas days already nominated settle at cash-out).
    was_open = _by_hub_month(before, skip_through=nominated)
    now_open = _by_hub_month(after, skip_through=nominated)
    for key in sorted(set(was_open) | set(now_open), key=lambda k: (k[1], k[0])):
        change = now_open.get(key, 0.0) - was_open.get(key, 0.0)
        if abs(change) < EPS_MWH:
            continue
        trading = market.trading(key[1])
        unit = terms.trade_cost_eur_mwh if trading else terms.short_notice_premium_eur_mwh
        cost = abs(change) * unit
        v.hedge_cost += cost
        action = "sell" if change > 0 else "buy back"
        venue = "futures" if trading else "balance-of-month or day-ahead (month stopped trading)"
        v.hedge_legs.append(
            {
                "hub": key[0],
                "month": key[1],
                "action": action,
                "mwh": round(abs(change), 1),
                "venue": venue,
                "trading": trading,
                "unit_cost_eur_mwh": unit,
                "cost_eur": round(cost, 2),
            }
        )
        v.lines.append(
            {
                "label": f"hedge {key[0]} {key[1]}",
                "value": round(-cost, 2),
                "text": f"{action} {_fmt(abs(change))} MWh {key[0]} {key[1]} in {venue}: "
                f"{_fmt(abs(change))} x {unit:.2f} = {_fmt(cost)} EUR",
                "sources": [
                    _term_source(
                        terms, "trade_cost_eur_mwh" if trading else "short_notice_premium_eur_mwh"
                    )
                ],
            }
        )
    was_day = _by_hub_day(before)
    now_day = _by_hub_day(after)
    for key in sorted(set(was_day) | set(now_day), key=lambda k: (k[1], k[0])):
        if key[1] > nominated:
            continue
        change = now_day.get(key, 0.0) - was_day.get(key, 0.0)
        if abs(change) < EPS_MWH:
            continue
        price = (market.price(key[0], _month(key[1])) or 0.0) * factor
        cost = abs(change) * price * terms.cash_out_pct / 100
        v.cash_out += cost
        v.lines.append(
            {
                "label": f"cash-out {key[0]} {key[1].isoformat()}",
                "value": round(-cost, 2),
                "text": f"gas day {key[1]:%d %b} already nominated: {_fmt(abs(change))} MWh "
                f"settles at cash-out, {terms.cash_out_pct:g} % of {price:,.2f} "
                f"= {_fmt(cost)} EUR",
                "sources": [
                    _price_source(market, key[0], _month(key[1]), factor),
                    _term_source(terms, "cash_out_pct"),
                ],
            }
        )

    # Capacity, demurrage, boil-off and stranded energy: the option's less the plan's.
    def total(landings: Mapping[str, Landing], attr: str) -> float:
        return sum(getattr(item, attr) for item in landings.values())

    fees_after = sum(sum(item.fees.values()) for item in after.values())
    fees_before = sum(sum(item.fees.values()) for item in before.values())
    v.capacity_fees = fees_after - fees_before
    v.demurrage = total(after, "demurrage_eur") - total(before, "demurrage_eur")
    boil_after = sum(item.boil_off_eur for item in after.values())
    boil_before = sum(item.boil_off_eur for item in before.values())
    v.boil_off = (boil_after - boil_before) * factor
    for landing in after.values():
        for name, amount in sorted(landing.fees.items()):
            if amount > EPS_EUR:
                v.lines.append(
                    {
                        "label": f"{name.replace('_', ' ')} {landing.supply_id}",
                        "value": round(-amount, 2),
                        "text": _fee_text(name, landing, amount),
                        "sources": [landing.fee_sources.get(name) or "offer not named"],
                    }
                )
        if landing.stranded_mwh > EPS_MWH:
            price = (market.price(landing.hub, landing.stranded_month or "") or 0.0) * factor
            loss = landing.stranded_mwh * terms.stranded_discount_eur_mwh
            v.stranded += loss
            v.lines.append(
                {
                    "label": f"stranded {landing.supply_id}",
                    "value": round(-loss, 2),
                    "text": f"{_fmt(landing.stranded_mwh)} MWh of {landing.supply_id} cannot be "
                    f"landed: sold where it lies at {price:,.2f} less "
                    f"{terms.stranded_discount_eur_mwh:.2f} = {_fmt(loss)} EUR",
                    "sources": [
                        _price_source(market, landing.hub, landing.stranded_month or "", factor),
                        _term_source(terms, "stranded_discount_eur_mwh"),
                    ],
                }
            )
    for supply_id in sorted(set(after) | set(before)):
        a, b = after.get(supply_id), before.get(supply_id)
        dem = (a.demurrage_eur if a else 0.0) - (b.demurrage_eur if b else 0.0)
        boil = ((a.boil_off_eur if a else 0.0) - (b.boil_off_eur if b else 0.0)) * factor
        if abs(dem) > EPS_EUR:
            v.lines.append(
                {
                    "label": f"demurrage {supply_id}",
                    "value": round(-dem, 2),
                    "text": _demurrage_text(portfolio.supply(supply_id), a, b, dem),
                    "sources": [portfolio.supply(supply_id).demurrage_source or "voyage terms"],
                }
            )
        if abs(boil) > EPS_EUR:
            bmwh = (a.boil_off_mwh if a else 0.0) - (b.boil_off_mwh if b else 0.0)
            v.lines.append(
                {
                    "label": f"boil-off {supply_id}",
                    "value": round(-boil, 2),
                    "text": (
                        f"{_signed(bmwh)} MWh boils off waiting at anchor: {_signed(-boil)} EUR"
                    ),
                    "sources": [
                        "boil-off rate from the voyage terms",
                        (a or b).price_source or "hub month mark",
                    ],
                }
            )

    # A slot left unused and released to the secondary market (indicative).
    for slot_id in option.releases:
        slot = portfolio.slot(slot_id)
        if slot is None or slot.release_value_eur_mwh is None:
            continue
        days = sum(1 for k in range(slot.days) if slot.start + timedelta(days=k) > nominated)
        rights = days * slot.send_out_mwh_per_day
        value = rights * slot.release_value_eur_mwh
        v.release += value
        v.lines.append(
            {
                "label": f"release {slot_id}",
                "value": round(value, 2),
                "text": f"release {slot.terminal} slot {slot_id}: {_fmt(rights)} MWh of send-out "
                f"right x {slot.release_value_eur_mwh:.2f} (indicative) = {_fmt(value)} EUR",
                "sources": [f"slot terms {slot.source or slot_id}: indicative release value"],
            }
        )
    if option.swaps:
        v.swap_cost = terms.swap_cost_eur * len(option.swaps)
        if v.swap_cost > EPS_EUR:
            v.lines.append(
                {
                    "label": "swap",
                    "value": -v.swap_cost,
                    "text": f"terminal swap cost {_fmt(v.swap_cost)} EUR",
                    "sources": [_term_source(terms, "swap_cost_eur")],
                }
            )

    # A non-firm obligation costs its penalty. A firm one short is a contract breach (flagged
    # in the base scenario by ``_check``): valued at its liquidated damages where the contract
    # data holds them, otherwise stated and left out of the P&L.
    for item in portfolio.obligations:
        short = _obligation_short(item, after, before)
        if not short:
            continue
        missed = sum(mwh for _, mwh in short)
        if not item.firm:
            unit = item.penalty_eur_mwh or 0.0
            penalty = missed * unit
            v.obligation_penalty += penalty
            v.lines.append(
                {
                    "label": f"penalty {item.obligation_id}",
                    "value": round(-penalty, 2),
                    "text": f"{item.counterparty}: {_fmt(missed)} MWh short x "
                    f"{unit:.2f} = {_fmt(penalty)} EUR",
                    "sources": [f"obligation {item.contract_id or item.obligation_id} penalty"],
                }
            )
            continue
        if item.penalty_eur_mwh is None:
            v.lines.append(
                {
                    "label": f"breach {item.obligation_id}",
                    "value": 0.0,
                    "text": f"breaks the firm delivery to {item.counterparty}: {_fmt(missed)} MWh "
                    "short; the contract's penalty is not held, so it is not in the P&L",
                    "sources": [f"obligation {item.contract_id or item.obligation_id}: no penalty"],
                }
            )
            continue
        exposure = missed * item.penalty_eur_mwh
        v.contract_exposure += exposure
        v.lines.append(
            {
                "label": f"breach {item.obligation_id}",
                "value": round(-exposure, 2),
                "text": f"breaks the firm delivery to {item.counterparty}: {_fmt(missed)} MWh "
                f"short x {item.penalty_eur_mwh:.2f} liquidated damages = {_fmt(exposure)} EUR",
                "sources": [
                    f"obligation {item.contract_id or item.obligation_id} liquidated damages"
                ],
            }
        )
    _substitute_cost(portfolio, market, option, v, scenario)
    _spot_fees(portfolio, option, v)
    for line in v.lines:
        line.setdefault("basis", "direct")
    return v


def _price_source(market: Market, hub: str, month: str, factor: float = 1.0) -> str:
    where = market.sources.get((hub.upper(), month)) or "month mark"
    text = f"{hub} {month} price: {where}"
    return text if factor == 1.0 else f"{text}, scenario x {factor:g}"


def _term_source(terms: DeskTerms, name: str) -> str:
    return f"{name}: {terms.sources.get(name) or 'desk standard'}"


def _spot_fees(portfolio: Portfolio, option: Option, v: Valuation) -> None:
    """A spot slot bought from a ``slot`` offer: its capacity charge (direct)."""

    for placement in option.placements.values():
        if not (placement.slot_id or "").startswith(SPOT_PREFIX):
            continue
        offer = next(
            (o for o in portfolio.spot_offers() if SPOT_PREFIX + o.offer_id == placement.slot_id),
            None,
        )
        if offer is None:
            continue
        slot = spot_slot(offer)
        rights = slot.days * slot.send_out_mwh_per_day
        fee = rights * offer.price_eur_mwh
        v.capacity_fees += fee
        v.lines.append(
            {
                "label": f"spot slot {offer.offer_id}",
                "value": round(-fee, 2),
                "text": f"spot slot at {offer.terminal} {offer.start:%d %b} to {offer.end:%d %b}: "
                f"{_fmt(rights)} MWh of send-out right x {offer.price_eur_mwh:.2f} = "
                f"{_fmt(fee)} EUR",
                "sources": [offer.where],
            }
        )


def _substitute_cost(
    portfolio: Portfolio, market: Market, option: Option, v: Valuation, scenario: Scenario
) -> None:
    """Substitute gas: what it costs to deliver (direct) and, for storage gas, the value it
    would have had in the month it was to be used (opportunity)."""

    factor = scenario.price_factor
    sources = {item.source_id: item for item in portfolio.substitutes}
    obligations = {item.obligation_id: item for item in portfolio.obligations}
    for cover in option.covers:
        source = sources.get(cover.source_id)
        item = obligations.get(cover.obligation_id)
        if source is None or item is None:
            continue
        cost = 0.0
        units = set()
        for day, mwh in cover.days:
            unit = source.direct_unit(market, day, factor) or 0.0
            units.add(round(unit, 4))
            cost += mwh * unit
        v.substitute_cost += cost
        parts = {
            "upstream": f"contract price {source.price_eur_mwh or 0:.2f}",
            "hub": f"{source.price_hub} month price"
            + (f" + {source.premium_eur_mwh:.2f} short notice" if source.premium_eur_mwh else ""),
            "storage": f"withdrawal fee {source.fee_eur_mwh:.2f}",
        }[source.kind]
        unit_text = (
            f"{next(iter(units)):.2f}" if len(units) == 1 else f"{min(units):.2f}-{max(units):.2f}"
        )
        ordered = [source.sources.get(k) for k in ("gas", "fee", "transport", "fx")]
        v.lines.append(
            {
                "label": f"substitute {source.source_id}",
                "value": round(-cost, 2),
                "text": f"cover {item.counterparty} at {item.point} with {_fmt(cover.mwh)} MWh of "
                f"{source.label}: {parts} + transport {source.transport_eur_mwh:.2f} = "
                f"{unit_text} EUR/MWh = {_fmt(cost)} EUR",
                "sources": [text for text in ordered if text] or [f"substitute {source.source_id}"],
            }
        )
        if source.kind == "storage":
            unit = source.forgone_unit(market, factor) or 0.0
            value = cover.mwh * unit
            v.storage_forgone += value
            v.lines.append(
                {
                    "label": f"storage gas {source.source_id}",
                    "value": round(-value, 2),
                    "basis": "opportunity",
                    "text": f"{_fmt(cover.mwh)} MWh drawn from {source.label} is not there to "
                    f"sell in {source.value_month}: x {unit:.2f} = {_fmt(value)} EUR",
                    "sources": [
                        source.sources.get("value")
                        or _price_source(market, source.price_hub or "", source.value_month or "")
                    ],
                }
            )
            v.opportunity.append(
                {
                    "kind": "storage_used",
                    "source_id": source.source_id,
                    "label": source.label,
                    "mwh": round(cover.mwh, 1),
                    "month": source.value_month,
                    "value_eur": round(-value, 2),
                    "text": f"uses {_fmt(cover.mwh)} MWh of {source.label} planned for "
                    f"{source.value_month}",
                }
            )


def _knock_on(
    portfolio: Portfolio,
    market: Market,
    v: Valuation,
    full: Valuation,
    free: Mapping[str, Landing],
    after: Mapping[str, Landing],
    before: Mapping[str, Landing],
    scenario: Scenario,
) -> None:
    """What the cargoes the option moves do to the book's other cargoes: the P&L of the
    portfolio as it lands, less the P&L had the others landed untouched."""

    knock = v.pnl - full.pnl
    hit = []
    dem_total = boil_total = 0.0
    for supply_id in sorted(after):
        if supply_id.startswith(COVER_PREFIX) or supply_id not in free:
            continue
        a, f = after[supply_id], free[supply_id]
        if a.flows == f.flows and a.demurrage_eur == f.demurrage_eur and not a.hold_days:
            continue
        supply = portfolio.supply(supply_id)
        dem = a.demurrage_eur - f.demurrage_eur
        boil = (a.boil_off_eur - f.boil_off_eur) * scenario.price_factor
        dem_total += dem
        boil_total += boil
        moved = (
            sum(abs(a.flows.get(d, 0.0) - f.flows.get(d, 0.0)) for d in set(a.flows) | set(f.flows))
            / 2
        )
        if a.hold_days:
            text = (
                f"{supply.label} waits {a.hold_days} more gas day(s) at {a.terminal}: "
                f"{a.held_by} holds the berth; demurrage {_fmt(dem)} EUR, boil-off "
                f"{_fmt(boil)} EUR"
            )
            kind = "berth_delay"
        else:
            text = (
                f"{supply.label} at {a.terminal} finds less shared send-out or storage left: "
                f"{_fmt(moved)} MWh sent out on other days"
            )
            kind = "capacity_squeezed"
        hit.append(
            {
                "kind": kind,
                "owner": "own",
                "supply_id": supply_id,
                "label": supply.label,
                "terminal": a.terminal,
                "delay_days": a.hold_days,
                "held_by": a.held_by,
                "demurrage_eur": round(-dem, 2),
                "boil_off_eur": round(-boil, 2),
                "mwh_moved": round(moved, 1),
                "text": text,
                "sources": [supply.demurrage_source or "voyage terms", a.price_source or "mark"],
            }
        )
    if abs(knock) <= EPS_EUR and not hit:
        return
    v.knock_on = knock
    rest = knock - dem_total - boil_total
    v.opportunity.extend(hit)
    names = ", ".join(item["label"] for item in hit) or "the book's other cargoes"
    v.lines.append(
        {
            "label": "knock-on",
            "value": round(-knock, 2),
            "basis": "opportunity",
            "text": f"knock-on on {names}: demurrage {_fmt(dem_total)} + boil-off "
            f"{_fmt(boil_total)} + hedges, send-out timing and deliveries {_fmt(rest)} "
            f"= {_fmt(knock)} EUR",
            "sources": sorted({src for item in hit for src in item["sources"]})
            or ["the portfolio as landed"],
        }
    )


def _displaced_calls(
    portfolio: Portfolio,
    market: Market,
    v: Valuation,
    after: Mapping[str, Landing],
    before: Mapping[str, Landing],
    scenario: Scenario,
) -> None:
    """Other users' ships due on a gas day a cargo the option moved holds the berth."""

    busy = moved_berths(portfolio, after, before)
    for call in sorted(portfolio.berth_calls, key=lambda c: (c.terminal, c.berth, c.call_id)):
        delay, held_by = 0, None
        for first, last, who in sorted(busy.get(call.terminal, [])):
            start = call.berth + timedelta(days=delay)
            if first <= start <= last:
                delay = (last - call.berth).days + 1
                held_by = who
        if not delay:
            continue
        dem = max(0.0, delay * 24.0 - call.laytime_hours) / 24.0 * call.demurrage_eur_per_day
        price = market.price(call.hub, _month(call.berth)) or 0.0
        boil = delay * call.boil_off_mwh_per_day * price * scenario.price_factor
        cost = dem + boil
        v.displaced_calls += cost
        rate = f"{call.demurrage_eur_per_day:,.0f} EUR/day"
        if call.demurrage_note:
            rate += f" ({call.demurrage_note})"
        text = (
            f"{call.label}, due at {call.terminal} on {call.berth:%d %b}, waits {delay} gas "
            f"day(s) while {held_by} holds the berth: {delay * 24:.0f} h against "
            f"{call.laytime_hours:.0f} h laytime left at {rate} = {_fmt(dem)} EUR, boil-off "
            f"{_fmt(call.boil_off_mwh_per_day * delay)} MWh x {price * scenario.price_factor:,.2f}"
            f" = {_fmt(boil)} EUR"
        )
        sources = [
            call.source or "terminal line-up",
            _price_source(market, call.hub, _month(call.berth)),
        ]
        v.lines.append(
            {
                "label": f"displaced {call.call_id}",
                "value": round(-cost, 2),
                "basis": "opportunity",
                "text": text,
                "sources": sources,
            }
        )
        v.opportunity.append(
            {
                "kind": "berth_delay",
                "owner": "third_party",
                "call_id": call.call_id,
                "label": call.label,
                "terminal": call.terminal,
                "delay_days": delay,
                "held_by": held_by,
                "demurrage_eur": round(-dem, 2),
                "boil_off_eur": round(-boil, 2),
                "value_eur": round(-cost, 2),
                "text": text,
                "sources": sources,
            }
        )


def _forgone(
    portfolio: Portfolio,
    market: Market,
    terms: DeskTerms,
    option: Option,
    v: Valuation,
    scenario: Scenario,
) -> None:
    """A spare slot of the book the option uses: the value it could have had released or
    used elsewhere (its indicative release value, else the desk's value of a spare slot)."""

    nominated = market.nominated_through
    swapped = {sid for pair in option.swaps for sid in pair}
    for supply_id, placement in sorted(option.placements.items()):
        supply = portfolio.supply(supply_id)
        slot = portfolio.slot(placement.slot_id)
        if (
            slot is None
            or slot.slot_id.startswith(SPOT_PREFIX)
            or slot.slot_id == supply.slot_id
            or slot.holder is not None
            or supply_id in swapped
        ):
            continue
        days = sum(1 for k in range(slot.days) if slot.start + timedelta(days=k) > nominated)
        rights = days * slot.send_out_mwh_per_day
        if slot.release_value_eur_mwh is not None:
            unit, where = slot.release_value_eur_mwh, f"slot terms {slot.source or slot.slot_id}"
        elif terms.spare_slot_value_eur_mwh is not None:
            unit, where = (
                terms.spare_slot_value_eur_mwh,
                _term_source(terms, "spare_slot_value_eur_mwh"),
            )
        else:
            unit, where = None, "no release value or other use held"
        value = rights * unit if unit is not None else 0.0
        v.capacity_forgone += value
        text = (
            f"uses the book's spare {slot.terminal} slot {slot.slot_id}: {_fmt(rights)} MWh of "
            + (
                f"send-out right x {unit:.2f} that could have been released or used "
                f"elsewhere = {_fmt(value)} EUR"
                if unit is not None
                else "send-out right; no release value or other use is held, so the value "
                "forgone is not known and is left out"
            )
        )
        v.lines.append(
            {
                "label": f"forgone {slot.slot_id}",
                "value": round(-value, 2),
                "basis": "opportunity",
                "text": text,
                "sources": [where],
            }
        )
        v.opportunity.append(
            {
                "kind": "capacity_forgone",
                "slot_id": slot.slot_id,
                "terminal": slot.terminal,
                "mwh": round(rights, 1),
                "unit_eur_mwh": unit,
                "value_eur": round(-value, 2),
                "held": unit is not None,
                "text": text,
                "sources": [where],
            }
        )


def _fee_text(name: str, landing: Landing, amount: float) -> str:
    usage = landing.usage
    words = {
        "borrow": f"borrow {_fmt(usage.get('borrowed_mwh', 0))} MWh in tank at {landing.terminal}",
        "extra_send_out": f"extra send-out {_fmt(usage.get('extra_send_out_mwh', 0))} MWh at "
        f"{landing.terminal}",
        "extra_storage": f"extra storage {_fmt(usage.get('extra_storage_mwh_days', 0))} "
        f"MWh-days at {landing.terminal}",
        "interruptible_send_out": f"interruptible send-out "
        f"{_fmt(usage.get('interruptible_send_out_mwh', 0))} MWh at "
        f"{landing.terminal}",
        "interruptible_storage": f"interruptible storage "
        f"{_fmt(usage.get('interruptible_storage_mwh_days', 0))} "
        f"MWh-days at {landing.terminal}",
        "cover_send_out": f"extra send-out {_fmt(usage.get('cover_mwh', 0))} MWh at "
        f"{landing.terminal} to cover a pipeline curtailment",
    }
    return f"{words.get(name, name)}: {_fmt(amount)} EUR"


def _demurrage_text(
    supply: Supply, after: Landing | None, before: Landing | None, amount: float
) -> str:
    wait_a = after.wait_days if after else 0
    wait_b = before.wait_days if before else 0
    rate = f"{supply.demurrage_eur_per_day:,.0f} EUR/day"
    if supply.demurrage_note:
        rate += f" ({supply.demurrage_note})"
    return (
        f"{supply.label} waits {wait_a * 24:.0f} h at anchor (plan: {wait_b * 24:.0f} h) against "
        f"{supply.laytime_hours:.0f} h laytime at {rate}: {_signed(-amount)} EUR"
    )


def _delivered_at(item: Obligation, landings: Mapping[str, Landing]) -> dict[date, float]:
    out: dict[date, float] = {}
    for landing in landings.values():
        if item.point not in (landing.terminal, landing.hub):
            continue
        for day, mwh in landing.flows.items():
            out[day] = out.get(day, 0.0) + mwh
    return out


def _obligation_short(
    item: Obligation,
    landings: Mapping[str, Landing],
    plan: Mapping[str, Landing] | None = None,
) -> list[tuple[date, float]]:
    """The days the obligation is short, and by how much. With ``plan``, only what the
    option adds to the shortfall the plan already had (an option is not blamed for a short
    day it did not cause; that one is reported as ``short_in_plan``)."""

    delivered = _delivered_at(item, landings)
    planned = _delivered_at(item, plan) if plan is not None else None
    short = []
    for day in _days(item.start, item.end):
        gap = item.mwh_per_day - delivered.get(day, 0.0)
        if planned is not None:
            gap -= max(0.0, item.mwh_per_day - planned.get(day, 0.0))
        if gap > item.tolerance_mwh:
            short.append((day, gap))
    return short


def _check(
    portfolio: Portfolio, option: Option, base: Valuation, before: Mapping[str, Landing]
) -> None:
    """Physical possibility and contract breaches, in the base scenario, against the plan
    before the disruption. What cannot physically happen goes to ``reasons`` (the option is
    not possible); what breaks a contract goes to ``breaches`` (the option stays listed)."""

    for supply_id, placement in option.placements.items():
        supply = portfolio.supply(supply_id)
        slot = portfolio.slot(placement.slot_id)
        if supply.kind != LNG or slot is None:
            continue
        if (
            slot.slot_id != supply.slot_id
            and not any(supply_id in pair for pair in option.swaps)
            and not supply.can_divert
        ):
            why = supply.diversion_note or "its contract does not allow a diversion"
            option.breaches.append(
                {
                    "kind": "no_diversion_right",
                    "supply_id": supply_id,
                    "contract_id": supply.contract_id,
                    "counterparty": None,
                    "text": f"diverts {supply.label} to {slot.terminal} although {why}; "
                    "the penalty for a diversion without the right is not held",
                    "shortfall_mwh": None,
                    "days": [],
                    "penalty_eur_mwh": None,
                    "penalty_held": False,
                    "exposure_eur": None,
                }
            )
        landing = base.landings.get(supply_id)
        if landing is not None and landing.unhoused_mwh > EPS_MWH:
            option.feasible = False
            option.reasons.append(
                f"{supply.label} at {slot.terminal}: the tank holds "
                f"{_fmt(landing.unhoused_mwh)} MWh over the storage right from "
                f"{landing.unhoused_day:%d %b} and no storage can be bought or used there"
            )
        if landing is not None and landing.stranded_mwh > EPS_MWH:
            option.feasible = False
            option.reasons.append(
                f"{supply.label} at {slot.terminal}: {_fmt(landing.stranded_mwh)} MWh has no "
                "send-out right before the tail ends"
            )
    for item in portfolio.obligations:
        short = _obligation_short(item, base.landings, before)
        in_plan = _obligation_short(item, before)
        status = {
            "obligation_id": item.obligation_id,
            "counterparty": item.counterparty,
            "point": item.point,
            "firm": item.firm,
            "met": not short,
            "short": [{"gas_day": d.isoformat(), "mwh": round(m, 1)} for d, m in short],
            "short_in_plan": [{"gas_day": d.isoformat(), "mwh": round(m, 1)} for d, m in in_plan],
        }
        option.obligations.append(status)
        if item.firm and short:
            missed = sum(m for _, m in short)
            held = item.penalty_eur_mwh is not None
            exposure = missed * item.penalty_eur_mwh if held else None
            text = (
                f"breaks the firm delivery to {item.counterparty} at {item.point}: "
                f"{_fmt(missed)} MWh short on "
                + ", ".join(f"{d:%d %b}" for d, _ in short[:5])
                + ("..." if len(short) > 5 else "")
            )
            text += (
                f"; liquidated damages {item.penalty_eur_mwh:.2f} EUR/MWh = {_fmt(exposure)} EUR"
                if held
                else "; the contract's penalty is not held, so the P&L leaves it out"
            )
            option.breaches.append(
                {
                    "kind": "short_delivery",
                    "obligation_id": item.obligation_id,
                    "contract_id": item.contract_id,
                    "counterparty": item.counterparty,
                    "point": item.point,
                    "text": text,
                    "shortfall_mwh": round(missed, 1),
                    "days": [{"gas_day": d.isoformat(), "mwh": round(m, 1)} for d, m in short],
                    "penalty_eur_mwh": item.penalty_eur_mwh,
                    "penalty_held": held,
                    "penalty_terms": item.penalty_terms or None,
                    "exposure_eur": None if exposure is None else round(exposure, 2),
                }
            )


def _disruption(
    portfolio: Portfolio,
    option: Option,
    before: Mapping[str, Landing],
    after: Mapping[str, Landing],
) -> list[dict[str, Any]]:
    """Each normally running supply that no longer leaves where and when planned, with the
    energy moved."""

    hit = {s.supply_id for s in disrupted(portfolio)}
    out = []
    for supply in portfolio.supplies:
        if supply.supply_id in hit:
            continue
        a, b = after.get(supply.supply_id), before.get(supply.supply_id)
        if a is None or b is None:
            continue
        was = {(b.terminal, day): mwh for day, mwh in b.flows.items()}
        now = {(a.terminal, day): mwh for day, mwh in a.flows.items()}
        gone = sum(max(0.0, mwh - now.get(key, 0.0)) for key, mwh in was.items())
        if gone > EPS_MWH:
            if a.hold_days:
                cause = f"waits {a.hold_days} gas day(s) for the berth {a.held_by} takes"
            elif supply.supply_id in option.placements:
                cause = "placed elsewhere by the option"
            else:
                cause = "less shared send-out or storage left at its terminal"
            out.append(
                {
                    "supply_id": supply.supply_id,
                    "label": supply.label,
                    "kind": supply.kind,
                    "mwh": round(gone, 1),
                    "from": b.terminal,
                    "to": a.terminal,
                    "cause": cause,
                }
            )
    return out


def _flexibility(
    portfolio: Portfolio, option: Option, base: Valuation, market: Market
) -> tuple[float, float]:
    """Firm send-out still held spare after the option, and interruptible relied on."""

    used = {p.slot_id for p in option.placements.values() if p.slot_id}
    held = {s.slot_id for s in portfolio.supplies if s.slot_id}
    spare = 0.0
    nominated = market.nominated_through
    for slot in portfolio.slots:
        if slot.slot_id in used or slot.slot_id in option.releases:
            continue
        if slot.slot_id in held and slot.slot_id not in {
            portfolio.supply(sid).slot_id for sid in option.placements
        }:
            continue  # still holds its own cargo
        if slot.holder is not None and slot.slot_id in held:
            continue
        days = sum(1 for k in range(slot.days) if slot.start + timedelta(days=k) > nominated)
        spare += days * slot.send_out_mwh_per_day
    interrupt = sum(
        item.usage.get("interruptible_send_out_mwh", 0.0) for item in base.landings.values()
    )
    return spare - interrupt, interrupt


def planned_landings(portfolio: Portfolio, market: Market) -> dict[str, Landing]:
    """Every supply as the plan before the disruption lands it (the baseline)."""

    return _landings(portfolio, market, {}, planned=True, shift=0, strand=False)


def evaluate(
    portfolio: Portfolio, market: Market, terms: DeskTerms, options: list[Option]
) -> list[Scenario]:
    """Value every option in every scenario, check constraints, fill the objectives."""

    scenarios = _scenarios(portfolio, terms)
    before = _landings(portfolio, market, {}, planned=True, shift=0, strand=False)
    for option in options:
        option.scenarios = [
            _value(portfolio, market, terms, option, scenario, before) for scenario in scenarios
        ]
        option.base = option.scenarios[0]
        _check(portfolio, option, option.base, before)
        option.disrupts = _disruption(portfolio, option, before, option.base.landings)
        who = [item["supply_id"] for item in option.disrupts]
        moved = sum(item["mwh"] for item in option.disrupts)
        flexibility, interrupt = _flexibility(portfolio, option, option.base, market)
        option.disrupted_supplies = who
        option.interruptible_mwh = interrupt
        if interrupt > EPS_MWH:
            option.notes.append(
                f"relies on {_fmt(interrupt)} MWh of interruptible send-out, granted only if "
                "other terminal users leave theirs unused"
            )
        option.objectives = {
            "pnl_expected": round(option.base.pnl, 2),
            "pnl_worst": round(min(v.pnl for v in option.scenarios), 2),
            "pnl_best": round(max(v.pnl for v in option.scenarios), 2),
            "cost": round(option.base.cash_cost, 2),
            "flexibility_mwh": round(flexibility, 1),
            "disrupted_mwh": round(moved, 1),
            "disrupted_supplies": len(who),
            "contract_breaches": len(option.breaches),
            "direct_pnl_expected": round(option.base.direct_pnl, 2),
            "opportunity_cost": round(option.base.opportunity_cost, 2),
        }
        o = option.objectives
        option.score = (
            o["pnl_expected"]
            - terms.risk_weight * (o["pnl_expected"] - o["pnl_worst"])
            - terms.disruption_eur_per_mwh * o["disrupted_mwh"]
            - terms.disruption_eur_per_supply * o["disrupted_supplies"]
            + terms.flexibility_eur_per_mwh * o["flexibility_mwh"]
            - terms.breach_eur_per_contract * o["contract_breaches"]
        )
    return scenarios


# ------------------------------------------------------------------------------- Pareto


def _better(a: Option, b: Option) -> tuple[bool, list[str]]:
    """Whether ``a`` dominates ``b``, and the objectives where it is strictly better."""

    strictly = []
    for name, sense in OBJECTIVES:
        x, y = a.objectives[name], b.objectives[name]
        tol = 0.5 if name == "contract_breaches" else EPS_MWH if name.endswith("_mwh") else EPS_EUR
        if sense == "max":
            if x < y - tol:
                return False, []
            if x > y + tol:
                strictly.append(name)
        else:
            if x > y + tol:
                return False, []
            if x < y - tol:
                strictly.append(name)
    return bool(strictly), strictly


_OBJECTIVE_WORDS = {
    "pnl_expected": "higher expected P&L",
    "pnl_worst": "a better worst case",
    "cost": "lower cost",
    "flexibility_mwh": "more spare capacity",
    "disrupted_mwh": "disturbs less of the portfolio",
    "contract_breaches": "breaks fewer contracts",
}


def pareto(options: list[Option]) -> list[Option]:
    """Mark the feasible options no other feasible option dominates; say why for the rest."""

    feasible = [o for o in options if o.feasible]
    frontier = []
    for option in feasible:
        dominators = []
        for other in feasible:
            if other is option:
                continue
            wins, where = _better(other, option)
            if wins:
                dominators.append((other, where))
        if not dominators:
            option.on_frontier = True
            frontier.append(option)
            continue
        best, where = max(dominators, key=lambda pair: (pair[0].score, pair[0].key))
        option.dominated_by = best.option_id
        option.dominated_why = [_OBJECTIVE_WORDS[name] for name in where]
    return frontier


def _order_key(option: Option) -> tuple:
    """Best first: score (the named ordering weights), fewer contracts broken, the frontier,
    fewer supplies moved, then the lexically first key, so the order is deterministic."""

    return (
        -round(option.score, 2),
        len(option.breaches),
        not option.on_frontier,
        option.objectives.get("disrupted_supplies", 0),
        option.key,
    )


def rank(options: list[Option]) -> list[Option]:
    """Number the possible options best first; a physically impossible option has no rank."""

    possible = sorted((o for o in options if o.feasible), key=_order_key)
    for place, option in enumerate(possible, start=1):
        option.rank = place
    for option in options:
        if not option.feasible:
            option.rank = None
    return possible


@dataclass(frozen=True)
class Recommendation:
    """One recommended option, the basis it is recommended on and the one-line reason."""

    basis: str
    option: Option
    reason: str


def _consequence_words(option: Option) -> str:
    parts = []
    for item in option.breaches:
        if item["kind"] == "short_delivery":
            exposure = (
                f"liquidated damages {_fmt(item['exposure_eur'])} EUR in the P&L"
                if item["penalty_held"]
                else "penalty not held, not in the P&L"
            )
            parts.append(
                f"breaks the firm delivery to {item['counterparty']} "
                f"({_fmt(item['shortfall_mwh'])} MWh short; {exposure})"
            )
        else:
            parts.append(item["text"].split(";")[0])
    if option.disrupts:
        moved = ", ".join(f"{d['label']} {_fmt(d['mwh'])} MWh" for d in option.disrupts)
        parts.append(f"moves supplies running to plan ({moved})")
    return "; ".join(parts)


def recommend_set(options: list[Option]) -> list[Recommendation]:
    """The recommended options, each named once on the first basis it earns:

    * ``clean``: the best ranked option that breaks no contract and moves nothing running to
      plan;
    * ``best_expected``: the highest expected P&L among options that break no contract (it
      may move other cargoes, and says which);
    * ``overall``: the best ranked of all possible options, breaches included.

    The trader decides; none is chosen for them."""

    possible = sorted((o for o in options if o.feasible), key=_order_key)
    keeps = [o for o in possible if not o.breaches]
    by_value = sorted(keeps, key=lambda o: (-o.objectives["pnl_expected"], _order_key(o)))
    picks = (
        (CLEAN, [o for o in keeps if not o.disrupts]),
        (BEST_EXPECTED, by_value),
        (OVERALL, possible),
    )
    out: list[Recommendation] = []
    seen: set[str] = set()
    for basis, pool in picks:
        if not pool or pool[0].option_id in seen:
            continue
        best = pool[0]
        seen.add(best.option_id)
        o = best.objectives
        figures = f"expected {_signed(o['pnl_expected'])} EUR, worst {_signed(o['pnl_worst'])} EUR"
        consequence = _consequence_words(best)
        tail = f"; it {consequence}." if consequence else "."
        if basis == CLEAN:
            reason = (
                "Best ranked option that breaks no contract and moves no cargo running to "
                f"plan: {figures}."
            )
        elif basis == BEST_EXPECTED:
            reason = f"Highest expected P&L that breaks no contract: {figures}{tail}"
        else:
            reason = f"Best ranked of all possible options: {figures}{tail}"
        out.append(Recommendation(basis, best, reason))
    for item in out:
        item.option.recommended_as.append(item.basis)
        item.option.recommended_why.append(item.reason)
    return out


def recommend(frontier: list[Option]) -> Option | None:
    """The first recommendation among ``frontier`` (kept for callers of LNG-3)."""

    chosen = recommend_set(frontier)
    for item in frontier:
        item.recommended_as.clear()
        item.recommended_why.clear()
    return chosen[0].option if chosen else None


# ------------------------------------------------------------------------------ result


@dataclass
class Result:
    disrupted: list[Supply]
    options: list[Option]
    scenarios: list[Scenario]
    frontier: list[Option]
    #: The first of the recommended set (kept for LNG-3 readers); ``None`` when nothing is
    #: possible or nothing is disrupted.
    recommended: Option | None
    terms: DeskTerms
    recommended_set: list[Recommendation] = field(default_factory=list)

    def recommended_keys(self) -> list[list[str]]:
        """``[[basis, key], ...]``: what a notice about the recommended set is about."""

        return [[item.basis, item.option.key] for item in self.recommended_set]

    def digest(self) -> str:
        """What a notice is about: what is disrupted, the recommended set and the frontier
        (so a disruption with no workable option and its clearing are told apart)."""

        body = {
            "disrupted": sorted(s.supply_id for s in self.disrupted),
            "recommended": self.recommended_keys(),
            "frontier": sorted(o.key for o in self.frontier),
        }
        return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:20]

    def option(self, option_id: str) -> Option | None:
        for option in self.options:
            if option.option_id == option_id:
                return option
        return None


def _cover_days(
    source: SubstituteSource,
    short: list[tuple[date, float]],
    market: Market,
    taken: Mapping[date, float] | None = None,
) -> tuple[tuple[date, float], ...]:
    days = []
    total = 0.0
    for day, mwh in short:
        if not source.covers(day) or source.direct_unit(market, day) is None:
            continue
        amount = min(mwh - (taken or {}).get(day, 0.0), source.max_mwh_per_day)
        if source.max_mwh:
            amount = min(amount, source.max_mwh - total)
        if amount > EPS_MWH:
            days.append((day, amount))
            total += amount
    return tuple(days)


def _unit_cost(source: SubstituteSource, market: Market, day: date) -> float:
    return (source.direct_unit(market, day) or 0.0) + (source.forgone_unit(market) or 0.0)


def cover_options(portfolio: Portfolio, market: Market, options: list[Option]) -> list[Option]:
    """For each possible option that leaves a delivery obligation short, the same option with
    the shortfall covered from substitute gas (LNG-4): from each source that reaches the
    obligation's point alone, and, where several do, from all of them cheapest first."""

    out: list[Option] = []
    if not portfolio.substitutes:
        return out
    for option in options:
        if not option.feasible or option.base is None or option.covers:
            continue
        covers: list[tuple[str, str, tuple[Cover, ...]]] = []
        for item in portfolio.obligations:
            short = _obligation_short(
                item, option.base.landings, planned_landings(portfolio, market)
            )
            if not short:
                continue
            fits = [
                src
                for src in sorted(portfolio.substitutes, key=lambda x: x.source_id)
                if src.point.upper() in (item.point.upper(), item.hub.upper())
            ]
            for src in fits:
                days = _cover_days(src, short, market)
                if days:
                    covers.append(
                        (
                            f"cover:{src.source_id}",
                            f"cover {item.counterparty} from {src.label}",
                            (Cover(src.source_id, item.obligation_id, days),),
                        )
                    )
            if len(fits) > 1:
                merit = sorted(
                    fits, key=lambda x: (_unit_cost(x, market, short[0][0]), x.source_id)
                )
                taken: dict[date, float] = {}
                parts = []
                for src in merit:
                    days = _cover_days(src, short, market, taken)
                    if days:
                        parts.append(Cover(src.source_id, item.obligation_id, days))
                        for day, mwh in days:
                            taken[day] = taken.get(day, 0.0) + mwh
                if len(parts) > 1:
                    covers.append(
                        (
                            "cover:merit",
                            f"cover {item.counterparty} cheapest first from "
                            + " then ".join(
                                next(x.label for x in fits if x.source_id == c.source_id)
                                for c in parts
                            ),
                            tuple(parts),
                        )
                    )
        for suffix, words, chosen in covers:
            key = f"{option.key} + {suffix}"
            out.append(
                Option(
                    option_id=_option_id(key),
                    key=key,
                    kind="substitute",
                    title=f"{option.title}; {words}",
                    placements=dict(option.placements),
                    releases=option.releases,
                    swaps=option.swaps,
                    covers=chosen,
                    notes=list(option.notes),
                )
            )
    return out[:MAX_COMBINATIONS]


def optimise(portfolio: Portfolio, market: Market, terms: DeskTerms | None = None) -> Result:
    """Generate, value, constrain and rank the options for the portfolio's disruptions."""

    terms = terms or DeskTerms()
    options = generate(portfolio, market, terms)
    scenarios = evaluate(portfolio, market, terms, options)
    covered = cover_options(portfolio, market, options)
    if covered:
        evaluate(portfolio, market, terms, covered)
        options.extend(covered)
    frontier = pareto(options)
    rank(options)
    chosen = recommend_set(options)
    # The ranked possible options first, then those that cannot physically happen.
    options.sort(key=lambda o: (not o.feasible, o.rank or 0, o.key))
    return Result(
        disrupted=disrupted(portfolio),
        options=options,
        scenarios=scenarios,
        frontier=sorted(frontier, key=lambda o: (-o.score, o.key)),
        recommended=chosen[0].option if chosen else None,
        terms=terms,
        recommended_set=chosen,
    )


# ---------------------------------------------------------------------------- readers


def placement_legs(portfolio: Portfolio, option: Option) -> list[dict[str, Any]]:
    """Each supply's leg in the option: terminal, slot days, capacity borrowed, bought,
    returned, waiting and demurrage, as the base scenario lands it."""

    base = option.base
    legs = []
    for supply_id in sorted(option.placements):
        placement = option.placements[supply_id]
        supply = portfolio.supply(supply_id)
        landing = base.landings.get(supply_id) if base else None
        slot = portfolio.slot(placement.slot_id)
        flows = sorted((landing.flows if landing else {}).items())
        legs.append(
            {
                "supply_id": supply_id,
                "label": supply.label,
                "kind": supply.kind,
                "terminal": None if slot is None else slot.terminal,
                "hub": None if slot is None else slot.hub,
                "slot_id": placement.slot_id,
                "moved": slot is not None and placement.slot_id != supply.slot_id,
                "arrival": None if placement.arrival is None else placement.arrival.isoformat(),
                "berth": None
                if landing is None or landing.berth is None
                else landing.berth.isoformat(),
                "wait_hours": 0 if landing is None else landing.wait_days * 24,
                "send_out_first": flows[0][0].isoformat() if flows else None,
                "send_out_last": flows[-1][0].isoformat() if flows else None,
                "send_out_mwh": round(sum(m for _, m in flows), 1),
                "borrowed": [
                    {"gas_day": d.isoformat(), "mwh": round(m, 1)} for d, m in placement.borrow
                ],
                "returned": None
                if landing is None or landing.returned is None
                else {
                    "gas_day": landing.returned[0].isoformat(),
                    "mwh": round(landing.returned[1], 1),
                },
                "covered": [
                    {"gas_day": d.isoformat(), "mwh": round(m, 1)} for d, m in placement.cover
                ],
                "usage": {k: round(v, 1) for k, v in (landing.usage if landing else {}).items()},
                "fees_eur": {k: round(v, 2) for k, v in (landing.fees if landing else {}).items()},
                "demurrage_eur": 0.0 if landing is None else round(landing.demurrage_eur, 2),
                "boil_off_mwh": 0.0 if landing is None else round(landing.boil_off_mwh, 1),
                "send_out": [{"gas_day": d.isoformat(), "mwh": round(m, 1)} for d, m in flows],
            }
        )
    return legs


def option_dict(portfolio: Portfolio, option: Option, *, detail: bool = False) -> dict[str, Any]:
    base = option.base
    out: dict[str, Any] = {
        "option_id": option.option_id,
        "key": option.key,
        "kind": option.kind,
        "title": option.title,
        "feasible": option.feasible,
        "possible": option.feasible,
        "rank": option.rank,
        "flags": option.flags,
        "breaches": [dict(item) for item in option.breaches],
        "disrupts": [dict(item) for item in option.disrupts],
        "recommended_as": list(option.recommended_as),
        "recommended_why": list(option.recommended_why),
        "reasons": list(option.reasons),
        "notes": list(option.notes),
        "on_frontier": option.on_frontier,
        "dominated_by": option.dominated_by,
        "dominated_why": list(option.dominated_why),
        "objectives": dict(option.objectives),
        "score": round(option.score, 2),
        "affects_other_supplies": list(option.disrupted_supplies),
        "interruptible_mwh": round(option.interruptible_mwh, 1),
        "releases": list(option.releases),
        "swaps": [list(pair) for pair in option.swaps],
        "covers": [
            {
                "source_id": c.source_id,
                "obligation_id": c.obligation_id,
                "mwh": round(c.mwh, 1),
                "days": [{"gas_day": d.isoformat(), "mwh": round(m, 1)} for d, m in c.days],
            }
            for c in option.covers
        ],
        "direct_pnl_expected": None if base is None else round(base.direct_pnl, 2),
        "opportunity_cost_expected": None if base is None else round(base.opportunity_cost, 2),
        "opportunity": [] if base is None else [dict(item) for item in base.opportunity],
        "obligations": list(option.obligations),
        "scenarios": [
            {
                "scenario_id": v.scenario.scenario_id,
                "label": v.scenario.label,
                "pnl": round(v.pnl, 2),
                "direct_pnl": round(v.direct_pnl, 2),
                "opportunity_cost": round(v.opportunity_cost, 2),
            }
            for v in option.scenarios
        ],
        "hedge_legs": [] if base is None else list(base.hedge_legs),
        "legs": placement_legs(portfolio, option),
    }
    if detail and base is not None:
        out["components"] = base.components()
        out["arithmetic"] = list(base.lines)
        out["scenario_detail"] = [
            {
                "scenario_id": v.scenario.scenario_id,
                "label": v.scenario.label,
                "pnl": round(v.pnl, 2),
                "components": v.components(),
                "arithmetic": v.lines,
            }
            for v in option.scenarios[1:]
        ]
    return out


def result_dict(portfolio: Portfolio, result: Result) -> dict[str, Any]:
    terms = result.terms
    return {
        "disrupted": [
            {
                "supply_id": s.supply_id,
                "label": s.label,
                "kind": s.kind,
                "arrival": None if s.arrival is None else s.arrival.isoformat(),
                "slot_id": s.slot_id,
                "terminal": s.terminal or s.point,
                "eta_confidence": s.eta_confidence,
                "curtailed": [
                    {"gas_day": d.isoformat(), "mwh": round(m, 1)} for d, m in s.curtailed
                ],
            }
            for s in result.disrupted
        ],
        "scenarios": [
            {
                "scenario_id": s.scenario_id,
                "label": s.label,
                "eta_shift_days": s.eta_shift_days,
                "price_factor": s.price_factor,
            }
            for s in result.scenarios
        ],
        "objectives": [{"name": name, "sense": sense} for name, sense in OBJECTIVES],
        "valuation": "P&L = direct P&L - opportunity cost: the direct effect of the cargoes "
        "the option places, the capacity it buys and the gas it brings in, less what it costs "
        "the rest of the portfolio (a berth it takes from a cargo due there, own or another "
        "user's, shared send-out or storage it leaves short, a spare slot's value forgone, "
        "storage gas not there when planned)",
        "options": [option_dict(portfolio, o) for o in result.options],
        "frontier": [o.option_id for o in result.frontier],
        "recommended": None if result.recommended is None else result.recommended.option_id,
        "recommended_set": [
            {
                "option_id": item.option.option_id,
                "key": item.option.key,
                "title": item.option.title,
                "basis": item.basis,
                "reason": item.reason,
            }
            for item in result.recommended_set
        ],
        "digest": result.digest(),
        "preference": {
            "use": "ordering only: the weights rank the options and pick the recommended set; "
            "they never exclude an option, and the trader decides",
            "risk_weight": terms.risk_weight,
            "disruption_eur_per_mwh": terms.disruption_eur_per_mwh,
            "disruption_eur_per_supply": terms.disruption_eur_per_supply,
            "flexibility_eur_per_mwh": terms.flexibility_eur_per_mwh,
            "breach_eur_per_contract": terms.breach_eur_per_contract,
            "spare_slot_value_eur_mwh": terms.spare_slot_value_eur_mwh,
            "rule": "score = expected - risk_weight x (expected - worst) - "
            "disruption_eur_per_mwh x disrupted MWh - disruption_eur_per_supply x "
            "supplies disturbed + flexibility_eur_per_mwh x spare MWh - "
            "breach_eur_per_contract x contracts broken",
            "sources": dict(terms.sources),
        },
        "costs": {
            "trade_cost_eur_mwh": terms.trade_cost_eur_mwh,
            "short_notice_premium_eur_mwh": terms.short_notice_premium_eur_mwh,
            "cash_out_pct": terms.cash_out_pct,
            "stranded_discount_eur_mwh": terms.stranded_discount_eur_mwh,
            "price_shock_pct": terms.price_shock_pct,
        },
    }


__all__ = [
    "BerthCall",
    "COVER_PREFIX",
    "Cover",
    "SPOT_PREFIX",
    "SUBSTITUTE_KINDS",
    "SubstituteSource",
    "cover_options",
    "spot_slot",
    "CapacityOffer",
    "DeskTerms",
    "DisruptionError",
    "LNG",
    "Market",
    "OBJECTIVES",
    "Obligation",
    "Option",
    "PIPELINE",
    "Placement",
    "Portfolio",
    "RECOMMENDATION_BASES",
    "Recommendation",
    "Result",
    "SlotTerms",
    "Supply",
    "disrupted",
    "evaluate",
    "generate",
    "optimise",
    "option_dict",
    "planned_landings",
    "pareto",
    "rank",
    "recommend",
    "recommend_set",
    "result_dict",
]
