"""The most a desk can bid for a regas slot, and what drives it (the regas auction desk).

The desk acts as a regasification agent: a terminal auctions a slot, a cargo owner offers a
cargo for it (fixed price or a formula on a hub index, valid for the auction window), and the
desk nets back. Energy and money are carried as exact totals and divided at the end::

    E_unl     slot energy unloaded from the ship (MWh) = slot quantity x stated factor
    E_out     = E_unl x (1 - losses %)                          sent out to the grid
    q_d       = E_out x w_d / sum(w)                             send-out profile, gas day d
    gross     = sum_d E_unl x w_d / sum(w) x P_d                 the energy at the hub
    revenue   = sum_d q_d x P_d                                  P_d: the price for that day
    cargo     = E_unl x cargo price per MWh (hub currency)       fixed, or slope x index + const
    costs     = sum of the cost lines                            regas fee, berthing, entry ...
    max bid   = revenue - costs - cargo                          a total for the slot
    quoted    = max bid / E_unl (per MWh) or max bid (per slot), as the auction quotes
    headroom  = quoted - current auction level

Cost lines by basis: ``per_slot`` (a total), ``per_mwh_unloaded`` (x E_unl), ``per_mwh_sent_out``
(x E_out), ``percent_of_energy`` (reduces E_out; its money effect is ``gross - revenue``),
``hedge_spread`` (half the bid/offer of each hedge leg times its volume) and ``financing``
(the cargo payment x rate x days tied / day count).

**Residual exposure and hedges.** Revenue is long the slot's hub on the send-out days. A cargo
priced on a formula is short its index hub over the pricing period (``slope x E_unl`` MWh,
spread evenly over the send-out days, or all in the named month). Per hub and month the formula
covers ``min(long, short)`` where both are the same hub; the rest is the residual, and the
hedge that locks the margin sells (or buys) exactly that, by hub and delivery month.

**Missing is never zero.** An input that is not held leaves the answer uncomputed and named in
``missing``; a simulated input makes the answer an illustration, never a bid level.

Pure, Decimal, deterministic: no I/O and no clock.

LNG 再气化档期竞拍：按枢纽远期价格的送出收入减去全部成本与船货价格，得出档期最高出价。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from eurogas_nexus.domain.lng.cargo_economics import MMBTU_PER_MWH, Valued, missing
from eurogas_nexus.domain.ontology.quantity import convert as _convert_units
from eurogas_nexus.domain.valuation.quality import InputClass, weakest

#: Therms in one MWh, from the ontology's unit table.
THERM_PER_MWH = Decimal(str(_convert_units(1.0, "MWh", "th")))
_HUNDRED = Decimal(100)
_CENT = Decimal("0.01")
_UNIT = Decimal("0.0001")
_ENERGY = Decimal("0.001")

BASES = (
    "per_slot",
    "per_mwh_unloaded",
    "per_mwh_sent_out",
    "percent_of_energy",
    "hedge_spread",
    "financing",
)
QUOTATIONS = ("per_mwh", "per_slot")
OFFER_KINDS = ("fixed", "formula")
PRICING = ("send_out_days", "month")
PRICE_UNITS = ("EUR/MWh", "GBP/MWh", "USD/MWh", "USD/MMBtu", "GBp/th")
#: A hub price whose move changes the max bid by less than this share of the energy sent out
#: does not decide the bid (a formula cargo on the same hub): no break-even price is given.
BREAK_EVEN_MIN_SHARE = Decimal("0.05")
STATES = ("missing_inputs", "illustration", "no_level", "room", "at_limit", "stop")


class RegasAuctionError(ValueError):
    """An input the calculation cannot take (not a missing value: a wrong one)."""


@dataclass(frozen=True)
class CostLine:
    """One cost of getting the gas to the hub, with where its value came from."""

    key: str
    label: str
    basis: str
    #: In the unit of its basis (hub currency, per MWh, or percent); missing when not held.
    value: Valued
    #: register | publication | computed | hand | default
    origin: str = "hand"
    entered_by: str = ""
    entered_at: str = ""
    link: str = ""

    def __post_init__(self) -> None:
        if self.basis not in BASES:
            raise RegasAuctionError(f"cost line {self.key}: basis {self.basis!r} is not known")


@dataclass(frozen=True)
class CargoTerms:
    """The cargo owner's offer: a fixed price, or ``slope x index + constant``.

    A fixed price is in ``price_unit`` (its currency per MWh, MMBtu or therm). A formula is in
    the index hub's currency per MWh: the index is that hub's price for the pricing period
    (the send-out days, each day weighted the same, or one delivery month).
    """

    kind: str
    fixed_price: Valued = field(default_factory=missing)
    price_unit: str = "EUR/MWh"
    index_hub: str = ""
    pricing: str = "send_out_days"
    pricing_month: str = ""
    slope: Valued = field(default_factory=missing)
    constant: Valued = field(default_factory=missing)
    tolerance_pct: Decimal = Decimal(0)

    def __post_init__(self) -> None:
        if self.kind not in OFFER_KINDS:
            raise RegasAuctionError("the offer is fixed or formula")
        if self.kind == "fixed" and self.price_unit not in PRICE_UNITS:
            raise RegasAuctionError(f"price unit {self.price_unit!r} is not known")
        if self.kind == "formula":
            if not self.index_hub:
                raise RegasAuctionError("a formula names its index hub")
            if self.pricing not in PRICING:
                raise RegasAuctionError("a formula prices on the send-out days or a month")
            if self.pricing == "month" and len(self.pricing_month) != 7:
                raise RegasAuctionError("a month pricing period names its month (YYYY-MM)")

    @property
    def price_currency(self) -> str:
        """The currency of a fixed price (``GBp`` counts as GBP)."""

        code = self.price_unit.split("/")[0]
        return "GBP" if code == "GBp" else code


@dataclass(frozen=True)
class SlotCase:
    """Everything the answer needs except the market (``Market``)."""

    hub: str
    currency: str
    energy_mwh: Valued
    days: tuple[date, ...]
    weights: tuple[Decimal, ...]
    cargo: CargoTerms
    cost_lines: tuple[CostLine, ...]
    quotation: str = "per_mwh"
    level: Valued | None = None
    at_limit_within_pct: Decimal = Decimal(2)
    delay_days: int = 0
    financing_days: Decimal = Decimal(30)
    day_count: Decimal = Decimal(365)
    #: Annual percent, benchmark plus the desk's spread.
    rate_pct: Valued = field(default_factory=missing)
    #: Hub currency per one unit of the fixed price's currency (1 when the same).
    cargo_fx: Valued = field(default_factory=lambda: Valued(Decimal(1), InputClass.SOURCED, "same"))
    #: Hub currency per one unit of the index hub's currency (1 when the same).
    index_fx: Valued = field(default_factory=lambda: Valued(Decimal(1), InputClass.SOURCED, "same"))
    index_currency: str = ""
    #: Half the bid/offer per MWh for a hedge leg with no quotes held (desk default).
    hedge_default_half_spread: Decimal = Decimal("0.05")

    def __post_init__(self) -> None:
        if self.quotation not in QUOTATIONS:
            raise RegasAuctionError("the auction quotes per MWh or per slot")
        if not self.days:
            raise RegasAuctionError("the slot has at least one send-out day")
        if len(self.weights) != len(self.days):
            raise RegasAuctionError("one send-out weight per day")
        if any(w < 0 for w in self.weights) or sum(self.weights) <= 0:
            raise RegasAuctionError("send-out weights are positive")
        if self.delay_days < 0:
            raise RegasAuctionError("a delay is zero or more days")


@dataclass(frozen=True)
class Market:
    """Prices per MWh in each hub's own currency, keyed ``(hub, "YYYY-MM-DD" | "YYYY-MM")``,
    and half the bid/offer per ``(hub, "YYYY-MM")``."""

    prices: Mapping[tuple[str, str], Valued]
    half_spreads: Mapping[tuple[str, str], Valued] = field(default_factory=dict)

    def bumped(self, hub: str, step: Decimal) -> Market:
        return Market(
            {
                key: replace(value, value=value.value + step)
                if key[0] == hub and value.value is not None
                else value
                for key, value in self.prices.items()
            },
            self.half_spreads,
        )


@dataclass(frozen=True)
class HedgeLeg:
    hub: str
    month: str
    side: str  # sell | buy
    mwh: Decimal
    half_spread: Valued
    cost: Decimal  # slot hub currency
    long_mwh: Decimal
    formula_mwh: Decimal
    covered_mwh: Decimal


@dataclass(frozen=True)
class _Core:
    days: tuple[date, ...]
    e_unl: Decimal
    e_out: Decimal
    gross: Decimal
    revenue: Decimal
    cargo_price: Decimal  # hub currency per MWh unloaded
    cargo_cost: Decimal
    index_value: Decimal | None
    lines: tuple[tuple[str, Decimal], ...]
    hedges: tuple[HedgeLeg, ...]
    #: Every hub and month the case is exposed in, including those the formula balances.
    exposures: tuple[HedgeLeg, ...]
    max_bid: Decimal
    day_rows: tuple[tuple[date, Decimal, Decimal], ...]  # day, MWh sent out, price


@dataclass(frozen=True)
class Answer:
    computed: bool
    state: str
    missing: tuple[str, ...] = ()
    simulated: bool = False
    hand_entered: tuple[str, ...] = ()
    defaults: tuple[str, ...] = ()
    grade: InputClass = InputClass.MISSING
    core: _Core | None = None
    quoted: Decimal | None = None
    quoted_low: Decimal | None = None
    quoted_high: Decimal | None = None
    level: Decimal | None = None
    headroom: Decimal | None = None
    waterfall: tuple[tuple[str, str, Decimal], ...] = ()
    sensitivities: tuple[tuple[str, str, Decimal | None, str], ...] = ()
    break_even: Decimal | None = None
    break_even_note: str = ""
    inputs: tuple[tuple[str, Valued], ...] = ()


def shifted(days: tuple[date, ...], delay: int) -> tuple[date, ...]:
    return tuple(day + timedelta(days=delay) for day in days)


def _month(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def fixed_price_per_mwh(price: Decimal, unit: str) -> Decimal:
    """A fixed price in its currency per MWh (``GBp/th`` to GBP/MWh)."""

    if unit.endswith("/MMBtu"):
        return price * MMBTU_PER_MWH
    if unit == "GBp/th":
        return price / _HUNDRED * THERM_PER_MWH
    return price


def even_weights(days: int) -> tuple[Decimal, ...]:
    return tuple(Decimal(1) for _ in range(days))


def _needed(case: SlotCase, market: Market) -> list[tuple[str, Valued]]:
    """Every input the answer rests on, by name, as held (missing ones included)."""

    days = shifted(case.days, case.delay_days)
    out: list[tuple[str, Valued]] = [("slot_energy", case.energy_mwh)]
    for day in days:
        key = (case.hub, day.isoformat())
        out.append((f"price:{case.hub}:{day.isoformat()}", market.prices.get(key, missing())))
    cargo = case.cargo
    if cargo.kind == "fixed":
        out.append(("cargo_price", cargo.fixed_price))
        if cargo.price_currency != case.currency:
            out.append(("cargo_fx", case.cargo_fx))
    else:
        out += [("formula_slope", cargo.slope), ("formula_constant", cargo.constant)]
        if cargo.pricing == "month":
            key = (cargo.index_hub, cargo.pricing_month)
            out.append((f"price:{cargo.index_hub}:{cargo.pricing_month}",
                        market.prices.get(key, missing())))
        elif cargo.index_hub != case.hub:
            for day in days:
                key = (cargo.index_hub, day.isoformat())
                out.append((f"price:{cargo.index_hub}:{day.isoformat()}",
                            market.prices.get(key, missing())))
        if cargo.index_hub != case.hub and case.index_currency != case.currency:
            out.append(("index_fx", case.index_fx))
    for line in case.cost_lines:
        if line.basis == "financing":
            out.append(("financing_rate", case.rate_pct))
        elif line.basis == "hedge_spread":
            if line.origin == "hand":
                out.append(("cost:hedging", line.value))
        else:
            out.append((f"cost:{line.key}", line.value))
    if case.level is not None:
        out.append(("auction_level", case.level))
    return out


def _core(case: SlotCase, market: Market) -> _Core:
    """The arithmetic, every input held (the caller checked)."""

    days = shifted(case.days, case.delay_days)
    e_unl = case.energy_mwh.value
    loss_pct = sum(
        (line.value.value for line in case.cost_lines if line.basis == "percent_of_energy"),
        Decimal(0),
    )
    keep = 1 - loss_pct / _HUNDRED
    e_out = e_unl * keep
    total_w = sum(case.weights)
    gross = revenue = Decimal(0)
    rows = []
    long_by: dict[tuple[str, str], Decimal] = {}
    for day, weight in zip(days, case.weights, strict=True):
        share = weight / total_w
        price = market.prices[(case.hub, day.isoformat())].value
        sent = e_out * share
        gross += e_unl * share * price
        revenue += sent * price
        rows.append((day, sent, price))
        bucket = (case.hub, _month(day))
        long_by[bucket] = long_by.get(bucket, Decimal(0)) + sent

    cargo = case.cargo
    short_by: dict[tuple[str, str], Decimal] = {}
    index_value: Decimal | None = None
    if cargo.kind == "fixed":
        per_mwh = fixed_price_per_mwh(cargo.fixed_price.value, cargo.price_unit)
        fx = Decimal(1) if cargo.price_currency == case.currency else case.cargo_fx.value
        cargo_price = per_mwh * fx
    else:
        if cargo.pricing == "month":
            index_value = market.prices[(cargo.index_hub, cargo.pricing_month)].value
            short_by[(cargo.index_hub, cargo.pricing_month)] = cargo.slope.value * e_unl
        else:
            prices = [market.prices[(cargo.index_hub, day.isoformat())].value for day in days]
            index_value = sum(prices, Decimal(0)) / len(prices)
            per_day = cargo.slope.value * e_unl / len(days)
            for day in days:
                bucket = (cargo.index_hub, _month(day))
                short_by[bucket] = short_by.get(bucket, Decimal(0)) + per_day
        fx = case.index_fx.value if cargo.index_hub != case.hub else Decimal(1)
        cargo_price = (cargo.slope.value * index_value + cargo.constant.value) * fx
    cargo_cost = e_unl * cargo_price

    hedging_line = next((line for line in case.cost_lines if line.basis == "hedge_spread"), None)
    hand_spread = (
        hedging_line.value
        if hedging_line is not None and hedging_line.origin == "hand" and hedging_line.value.held
        else None
    )
    default_spread = Valued(
        case.hedge_default_half_spread
        if hedging_line is None or not hedging_line.value.held
        else hedging_line.value.value,
        InputClass.ASSUMPTION,
        "desk default: no bid/offer held for this contract",
    )
    hedges = []
    for bucket in sorted(set(long_by) | set(short_by)):
        hub, month = bucket
        long = long_by.get(bucket, Decimal(0))
        short = short_by.get(bucket, Decimal(0))
        net = long - short
        spread = hand_spread or market.half_spreads.get(bucket)
        if spread is None or not spread.held:
            spread = default_spread
        to_slot = Decimal(1) if hub == case.hub else case.index_fx.value
        hedges.append(
            HedgeLeg(
                hub=hub,
                month=month,
                side="sell" if net > 0 else "buy",
                mwh=abs(net),
                half_spread=spread,
                cost=abs(net) * spread.value * to_slot,
                long_mwh=long,
                formula_mwh=short,
                covered_mwh=min(long, short),
            )
        )

    exposures = tuple(hedges)
    hedges = [leg for leg in hedges if leg.mwh != 0]
    lines: list[tuple[str, Decimal]] = []
    for line in case.cost_lines:
        if line.basis == "percent_of_energy":
            continue
        if line.basis == "per_slot":
            amount = line.value.value
        elif line.basis == "per_mwh_unloaded":
            amount = line.value.value * e_unl
        elif line.basis == "per_mwh_sent_out":
            amount = line.value.value * e_out
        elif line.basis == "hedge_spread":
            amount = sum((leg.cost for leg in hedges), Decimal(0))
        else:  # financing
            days_tied = case.financing_days + case.delay_days
            amount = max(cargo_cost, Decimal(0)) * case.rate_pct.value / _HUNDRED * (
                days_tied / case.day_count
            )
        lines.append((line.key, amount))
    max_bid = revenue - sum((amount for _, amount in lines), Decimal(0)) - cargo_cost
    return _Core(
        days=days,
        e_unl=e_unl,
        e_out=e_out,
        gross=gross,
        revenue=revenue,
        cargo_price=cargo_price,
        cargo_cost=cargo_cost,
        index_value=index_value,
        lines=tuple(lines),
        hedges=tuple(hedges),
        exposures=exposures,
        max_bid=max_bid,
        day_rows=tuple(rows),
    )


def _quoted(case: SlotCase, core: _Core) -> Decimal:
    return core.max_bid / core.e_unl if case.quotation == "per_mwh" else core.max_bid


def _holds(case: SlotCase, market: Market) -> bool:
    return all(value.held for _, value in _needed(case, market))


def _delta(case: SlotCase, market: Market, base: Decimal) -> Decimal | None:
    if not _holds(case, market):
        return None
    return _core(case, market).max_bid - base


def evaluate(
    case: SlotCase,
    market: Market,
    *,
    price_steps: Mapping[str, tuple[Decimal, str]] | None = None,
) -> Answer:
    """The answer for one case on one market.

    ``price_steps`` is the move each hub's sensitivity is stated for, in that hub's currency
    per MWh, with its label in the hub's own quotation (NBP: ``0.01 x therms per MWh`` labelled
    ``1 p/th``); default 1 per MWh.
    """

    needed = _needed(case, market)
    gaps = tuple(name for name, value in needed if not value.held)
    classes = [value.input_class for _, value in needed if value.held]
    simulated = any(value.input_class == InputClass.SIMULATED for _, value in needed)
    hand: list[str] = [
        name for name, value in needed
        if value.held and value.source.startswith(("entered", "hand"))
    ]
    defaults: list[str] = []
    for line in case.cost_lines:
        name = f"cost:{line.key}"
        if line.basis == "financing" or not line.value.held:
            continue
        if line.origin == "hand" and name not in hand:
            hand.append(name)
        elif line.origin == "default":
            defaults.append(name)
    if gaps:
        return Answer(computed=False, state="missing_inputs", missing=gaps, simulated=simulated,
                      hand_entered=tuple(hand), defaults=tuple(defaults),
                      grade=InputClass.MISSING, inputs=tuple(needed))
    core = _core(case, market)
    quoted = _quoted(case, core)
    tolerance = case.cargo.tolerance_pct / _HUNDRED
    low = high = None
    if tolerance > 0:
        bounds = []
        for factor in (1 - tolerance, 1 + tolerance):
            scaled = replace(case, energy_mwh=replace(case.energy_mwh,
                                                      value=case.energy_mwh.value * factor))
            other = _core(scaled, market)
            # Quoted per MWh of the slot's stated energy: the slot is what is auctioned.
            bounds.append(other.max_bid / core.e_unl if case.quotation == "per_mwh"
                          else other.max_bid)
        low, high = min(bounds), max(bounds)

    level = case.level.value if case.level is not None and case.level.held else None
    headroom = None if level is None else quoted - level
    if simulated:
        state = "illustration"
    elif core.max_bid <= 0:
        state = "stop"
    elif headroom is None:
        state = "no_level"
    elif headroom < 0:
        state = "stop"
    elif headroom <= abs(quoted) * case.at_limit_within_pct / _HUNDRED:
        state = "at_limit"
    else:
        state = "room"

    lost = core.gross - core.revenue
    labels = {line.key: line.label for line in case.cost_lines}
    waterfall: list[tuple[str, str, Decimal]] = [
        ("gross", "Hub value of the slot's energy", core.gross),
    ]
    if lost:
        waterfall.append(("losses", labels.get("losses", "Losses"), -lost))
    waterfall += [(key, labels[key], -amount) for key, amount in core.lines]
    waterfall += [("cargo", "Cargo under the offer", -core.cargo_cost),
                  ("max_bid", "Maximum bid for the slot", core.max_bid)]

    steps = dict(price_steps or {})
    sens: list[tuple[str, str, Decimal | None, str]] = []
    hubs = [case.hub]
    if case.cargo.kind == "formula" and case.cargo.index_hub not in hubs:
        hubs.append(case.cargo.index_hub)
    for hub in hubs:
        step, label = steps.get(hub, (Decimal(1), "1 per MWh"))
        sens.append((f"price:{hub}", hub, _delta(case, market.bumped(hub, step), core.max_bid),
                     label))
    sens.append(("delay", "one day late",
                 _delta(replace(case, delay_days=case.delay_days + 1), market, core.max_bid),
                 "1 day"))
    loss_lines = [line for line in case.cost_lines if line.basis == "percent_of_energy"]
    if loss_lines:
        first = loss_lines[0]
        bumped_lines = tuple(
            replace(line, value=replace(line.value, value=line.value.value + 1))
            if line is first else line
            for line in case.cost_lines
        )
        sens.append(("losses", "losses", _delta(replace(case, cost_lines=bumped_lines), market,
                                                core.max_bid), "1 percentage point"))
    if case.cargo.kind == "fixed" and case.cargo.price_currency != case.currency:
        moved = replace(case, cargo_fx=replace(case.cargo_fx,
                                               value=case.cargo_fx.value * Decimal("1.01")))
        sens.append(("fx", f"{case.cargo.price_currency}/{case.currency}",
                     _delta(moved, market, core.max_bid), "+1 %"))
    if (case.cargo.kind == "formula" and case.cargo.index_hub != case.hub
            and case.index_currency and case.index_currency != case.currency):
        moved = replace(case, index_fx=replace(case.index_fx,
                                               value=case.index_fx.value * Decimal("1.01")))
        sens.append(("fx", f"{case.index_currency}/{case.currency}",
                     _delta(moved, market, core.max_bid), "+1 %"))

    break_even = None
    note = ""
    if level is not None:
        per_unit = _delta(case, market.bumped(case.hub, Decimal(1)), core.max_bid)
        target = level * core.e_unl if case.quotation == "per_mwh" else level
        # Under 5 % of the energy sent out, the formula carries the hub price: a break-even
        # would be a price far from any market and decide nothing.
        if per_unit is None or abs(per_unit) < core.e_out * BREAK_EVEN_MIN_SHARE:
            note = "price_does_not_decide"
        else:
            shift = (target - core.max_bid) / per_unit
            break_even = core.revenue / core.e_out + shift
    return Answer(
        computed=True,
        state=state,
        simulated=simulated,
        hand_entered=tuple(hand),
        defaults=tuple(defaults),
        grade=weakest(classes),
        core=core,
        quoted=quoted,
        quoted_low=low,
        quoted_high=high,
        level=level,
        headroom=headroom,
        waterfall=tuple(waterfall),
        sensitivities=tuple(sens),
        break_even=break_even,
        break_even_note=note,
        inputs=tuple(needed),
    )


# ----------------------------------------------------------------------------- payload


def money(value: Decimal | None) -> str | None:
    return None if value is None else str(value.quantize(_CENT, rounding=ROUND_HALF_UP))


def unit(value: Decimal | None) -> str | None:
    return None if value is None else str(value.quantize(_UNIT, rounding=ROUND_HALF_UP))


def energy(value: Decimal | None) -> str | None:
    return None if value is None else str(value.quantize(_ENERGY, rounding=ROUND_HALF_UP))


def serialise(case: SlotCase, answer: Answer) -> dict[str, object]:
    """The answer as exact decimal text: money to the cent, per-unit figures to four places."""

    core = answer.core
    out: dict[str, object] = {
        "computed": answer.computed,
        "state": answer.state,
        "missing": list(answer.missing),
        "simulated": answer.simulated,
        "hand_entered": list(answer.hand_entered),
        "defaults": list(answer.defaults),
        "grade": str(answer.grade),
        "currency": case.currency,
        "quotation": case.quotation,
    }
    if core is None:
        return out
    per = core.e_unl
    out.update(
        {
            "max_bid_total": money(core.max_bid),
            "max_bid_quoted": unit(answer.quoted) if case.quotation == "per_mwh"
            else money(answer.quoted),
            "max_bid_per_mwh": unit(core.max_bid / per),
            "quoted_low": None if answer.quoted_low is None else unit(answer.quoted_low),
            "quoted_high": None if answer.quoted_high is None else unit(answer.quoted_high),
            "level": None if answer.level is None else unit(answer.level),
            "headroom": None if answer.headroom is None else unit(answer.headroom),
            "energy_unloaded_mwh": energy(core.e_unl),
            "energy_sent_out_mwh": energy(core.e_out),
            "revenue": money(core.revenue),
            "gross": money(core.gross),
            "average_hub_price": unit(core.revenue / core.e_out),
            "cargo_price_per_mwh": unit(core.cargo_price),
            "cargo_cost": money(core.cargo_cost),
            "index_value": unit(core.index_value),
            "lines": [{"key": key, "total": money(amount), "per_mwh": unit(amount / per)}
                      for key, amount in core.lines],
            "days": [{"day": day.isoformat(), "sent_out_mwh": energy(sent), "price": unit(price),
                      "revenue": money(sent * price)} for day, sent, price in core.day_rows],
            "waterfall": [{"key": key, "label": label, "total": money(amount),
                           "per_mwh": unit(amount / per)} for key, label, amount in
                          answer.waterfall],
            "sensitivities": [
                {"key": key, "label": label, "per": step,
                 "max_bid_total": money(delta),
                 "max_bid_quoted": None if delta is None else
                 (unit(delta / per) if case.quotation == "per_mwh" else money(delta))}
                for key, label, delta, step in answer.sensitivities
            ],
            "break_even_hub_price": unit(answer.break_even),
            "break_even_note": answer.break_even_note,
            "hedges": [
                {"hub": leg.hub, "month": leg.month, "side": leg.side, "mwh": energy(leg.mwh),
                 "half_spread": unit(leg.half_spread.value),
                 "half_spread_source": leg.half_spread.source,
                 "half_spread_class": str(leg.half_spread.input_class),
                 "cost": money(leg.cost),
                 "long_mwh": energy(leg.long_mwh), "formula_mwh": energy(leg.formula_mwh),
                 "covered_mwh": energy(leg.covered_mwh)}
                for leg in core.hedges
            ],
            "exposure": [
                {"hub": leg.hub, "month": leg.month, "long_mwh": energy(leg.long_mwh),
                 "formula_mwh": energy(leg.formula_mwh), "covered_mwh": energy(leg.covered_mwh),
                 "residual_mwh": energy(leg.long_mwh - leg.formula_mwh),
                 # Money per one unit move of that hub's price, in that hub's currency.
                 "per_unit_move": money(leg.long_mwh - leg.formula_mwh)}
                for leg in core.exposures
            ],
        }
    )
    return out
