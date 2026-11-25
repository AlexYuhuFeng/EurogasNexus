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
frontier over five objectives:

========================  ==========================================================  =====
objective                 meaning                                                     sense
========================  ==========================================================  =====
``pnl_expected``          P&L change in the base scenario (EUR)                       max
``pnl_worst``             worst P&L change across the scenarios (EUR): the downside   max
``cost``                  cash paid for the option less what the plan already paid    min
``flexibility_mwh``       firm send-out still held spare, less interruptible relied   max
``disrupted_mwh``         energy of supplies operating normally that the option moves min
========================  ==========================================================  =====

Hard constraints are never traded off: a firm delivery obligation (a contract to deliver gas
at a terminal or point, per day, in a window) must be met in the base scenario, the tank must
fit in firm or interruptible storage, a diversion must be allowed by the cargo's contract, and
a target slot must be the book's own and free. An option that breaks one is listed as
infeasible with the reason and is never recommended.

The recommended default is the feasible frontier option with the highest score::

    score = pnl_expected - risk_weight x (pnl_expected - pnl_worst)
            - disruption_eur_per_mwh x disrupted_mwh - disruption_eur_per_supply x supplies
            + flexibility_eur_per_mwh x flexibility_mwh

with the weights from the firm's approved assumptions (desk standards otherwise, named as
such). Ties go to fewer disrupted supplies, then to the option key, so the result is
deterministic.

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
bought, traded or nominated; a person chooses.
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
)


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
    penalty_eur_mwh: float = 0.0
    contract_id: str | None = None
    tolerance_mwh: float = EPS_MWH


@dataclass(frozen=True)
class CapacityOffer:
    """Terminal capacity the desk could borrow or buy (quoted, indicative or a tariff).

    ``borrow``: LNG lent in the tank by another user for gas days in the window, up to
    ``max_mwh_per_day``, returned from the cargo after it berths; ``price_eur_mwh`` per MWh
    borrowed. ``send_out``: extra firm send-out up to ``max_mwh_per_day``, per MWh sent.
    ``storage``: extra firm storage up to ``max_mwh``, per MWh and day. ``interruptible``:
    unused rights of other users, send-out per MWh (``price_eur_mwh``, up to
    ``max_mwh_per_day``) and storage per MWh and day (``storage_price_eur_mwh_day``, up to
    ``max_mwh``), granted only when others do not use them.
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

    def __post_init__(self) -> None:
        if self.kind not in ("borrow", "send_out", "storage", "interruptible"):
            raise DisruptionError(f"offer {self.offer_id}: kind {self.kind!r} is unknown")

    def covers(self, day: date) -> bool:
        return self.start <= day <= self.end


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

    def slot(self, slot_id: str | None) -> SlotTerms | None:
        for slot in self.slots:
            if slot.slot_id == slot_id:
                return slot
        return None

    def supply(self, supply_id: str) -> Supply:
        for supply in self.supplies:
            if supply.supply_id == supply_id:
                return supply
        raise DisruptionError(f"no supply {supply_id}")

    def offers_at(self, terminal: str, kind: str) -> list[CapacityOffer]:
        return sorted(
            (o for o in self.offers if o.terminal == terminal and o.kind == kind),
            key=lambda o: (o.price_eur_mwh, o.offer_id),
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
) -> Landing:
    """Simulate a cargo landing at its placed slot, gas day by gas day."""

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
    borrow_fee = offers[placement.borrow_offer].price_eur_mwh if placement.borrow_offer else 0.0

    k_arrival = (arrival - slot.start).days
    wait_days = max(0, -k_arrival)
    berth_k = max(0, k_arrival)
    berth = slot.start + timedelta(days=berth_k)
    energy = supply.energy_mwh
    stranded = 0.0
    for _attempt in range(2):
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
            if lend > 0:
                lend = min(lend, right)
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
                    extra = min(inventory - ahead, buy.max_mwh_per_day)
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
                    extra = min(inventory, interruptible.max_mwh_per_day)
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
                        held = min(over, storage.max_mwh)
                        over -= held
                        usage["extra_storage_mwh_days"] = (
                            usage.get("extra_storage_mwh_days", 0.0) + held
                        )
                        fees["extra_storage"] = fees.get("extra_storage", 0.0) + (
                            held * storage.price_eur_mwh
                        )
                    if over > EPS_MWH and interruptible is not None and interruptible.covers(day):
                        held = min(over, interruptible.max_mwh) if interruptible.max_mwh else over
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
    lines: list[dict[str, Any]] = field(default_factory=list)
    hedge_legs: list[dict[str, Any]] = field(default_factory=list)
    landings: dict[str, Landing] = field(default_factory=dict)

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
    feasible: bool = True
    reasons: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    base: Valuation | None = None
    scenarios: list[Valuation] = field(default_factory=list)
    objectives: dict[str, float] = field(default_factory=dict)
    disrupted_supplies: list[str] = field(default_factory=list)
    interruptible_mwh: float = 0.0
    obligations: list[dict[str, Any]] = field(default_factory=list)
    score: float = 0.0
    on_frontier: bool = False
    dominated_by: str | None = None
    dominated_why: list[str] = field(default_factory=list)


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
) -> dict[str, Landing]:
    hit = {s.supply_id for s in disrupted(portfolio)}
    out = {}
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
        out[supply.supply_id] = _land(
            portfolio, supply, placement, arrival, market, strand_unhoused=strand
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
    strand = scenario.scenario_id != "base"
    after = _landings(
        portfolio,
        market,
        option.placements,
        planned=False,
        shift=scenario.eta_shift_days,
        strand=strand,
    )
    v = Valuation(scenario=scenario, landings=after)
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
                }
            )

    # Soft obligations cost their penalty; firm ones are checked as hard constraints.
    for item in portfolio.obligations:
        short = _obligation_short(item, after, before)
        if item.firm or not short:
            continue
        missed = sum(mwh for _, mwh in short)
        penalty = missed * item.penalty_eur_mwh
        v.obligation_penalty += penalty
        v.lines.append(
            {
                "label": f"penalty {item.obligation_id}",
                "value": round(-penalty, 2),
                "text": f"{item.counterparty}: {_fmt(missed)} MWh short x "
                f"{item.penalty_eur_mwh:.2f} = {_fmt(penalty)} EUR",
            }
        )
    return v


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
    return (
        f"{supply.label} waits {wait_a * 24:.0f} h at anchor (plan: {wait_b * 24:.0f} h) against "
        f"{supply.laytime_hours:.0f} h laytime at {supply.demurrage_eur_per_day:,.0f} EUR/day: "
        f"{_signed(-amount)} EUR"
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
    """Hard constraints, in the base scenario, against the plan before the disruption."""

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
            option.feasible = False
            option.reasons.append(
                f"{supply.label}: "
                f"{supply.diversion_note or 'its contract does not allow a diversion'}"
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
            option.feasible = False
            option.reasons.append(
                f"breaks the firm delivery to {item.counterparty} at {item.point}: "
                f"{_fmt(missed)} MWh short on "
                + ", ".join(f"{d:%d %b}" for d, _ in short[:5])
                + ("..." if len(short) > 5 else "")
            )


def _disruption(
    portfolio: Portfolio,
    option: Option,
    before: Mapping[str, Landing],
    after: Mapping[str, Landing],
) -> tuple[float, list[str]]:
    """Energy of normally running supplies that no longer leaves where and when planned."""

    hit = {s.supply_id for s in disrupted(portfolio)}
    moved = 0.0
    who = []
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
            moved += gone
            who.append(supply.supply_id)
    return moved, who


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
        moved, who = _disruption(portfolio, option, before, option.base.landings)
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
        }
        o = option.objectives
        option.score = (
            o["pnl_expected"]
            - terms.risk_weight * (o["pnl_expected"] - o["pnl_worst"])
            - terms.disruption_eur_per_mwh * o["disrupted_mwh"]
            - terms.disruption_eur_per_supply * o["disrupted_supplies"]
            + terms.flexibility_eur_per_mwh * o["flexibility_mwh"]
        )
    return scenarios


# ------------------------------------------------------------------------------- Pareto


def _better(a: Option, b: Option) -> tuple[bool, list[str]]:
    """Whether ``a`` dominates ``b``, and the objectives where it is strictly better."""

    strictly = []
    for name, sense in OBJECTIVES:
        x, y = a.objectives[name], b.objectives[name]
        tol = EPS_MWH if name.endswith("_mwh") else EPS_EUR
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


def recommend(frontier: list[Option]) -> Option | None:
    if not frontier:
        return None
    return max(
        frontier,
        key=lambda o: (
            round(o.score, 2),
            -o.objectives["disrupted_supplies"],
            # Deterministic last resort: the lexically first key wins.
            [-ord(ch) for ch in o.key],
        ),
    )


# ------------------------------------------------------------------------------ result


@dataclass
class Result:
    disrupted: list[Supply]
    options: list[Option]
    scenarios: list[Scenario]
    frontier: list[Option]
    recommended: Option | None
    terms: DeskTerms

    def digest(self) -> str:
        """What a notice is about: the recommended option and the frontier."""

        body = {
            "recommended": None if self.recommended is None else self.recommended.key,
            "frontier": sorted(o.key for o in self.frontier),
        }
        return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:20]

    def option(self, option_id: str) -> Option | None:
        for option in self.options:
            if option.option_id == option_id:
                return option
        return None


def optimise(portfolio: Portfolio, market: Market, terms: DeskTerms | None = None) -> Result:
    """Generate, value, constrain and rank the options for the portfolio's disruptions."""

    terms = terms or DeskTerms()
    options = generate(portfolio, market, terms)
    scenarios = evaluate(portfolio, market, terms, options)
    frontier = pareto(options)
    chosen = recommend(frontier)
    options.sort(key=lambda o: (not o.feasible, not o.on_frontier, -o.score, o.key))
    return Result(
        disrupted=disrupted(portfolio),
        options=options,
        scenarios=scenarios,
        frontier=sorted(frontier, key=lambda o: (-o.score, o.key)),
        recommended=chosen,
        terms=terms,
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
        "obligations": list(option.obligations),
        "scenarios": [
            {
                "scenario_id": v.scenario.scenario_id,
                "label": v.scenario.label,
                "pnl": round(v.pnl, 2),
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
        "options": [option_dict(portfolio, o) for o in result.options],
        "frontier": [o.option_id for o in result.frontier],
        "recommended": None if result.recommended is None else result.recommended.option_id,
        "digest": result.digest(),
        "preference": {
            "risk_weight": terms.risk_weight,
            "disruption_eur_per_mwh": terms.disruption_eur_per_mwh,
            "disruption_eur_per_supply": terms.disruption_eur_per_supply,
            "flexibility_eur_per_mwh": terms.flexibility_eur_per_mwh,
            "rule": "score = expected - risk_weight x (expected - worst) - "
            "disruption_eur_per_mwh x disrupted MWh - disruption_eur_per_supply x "
            "supplies disturbed + flexibility_eur_per_mwh x spare MWh",
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
    "recommend",
    "result_dict",
]
