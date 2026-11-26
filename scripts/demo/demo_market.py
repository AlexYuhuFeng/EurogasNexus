"""The demo market: every product of every demo hub, coherent by construction (demo only).

The demo desk used to simulate one month-ahead series and a monthly curve per hub, so the
board's WD, DA and WE columns were empty and cross-tenor or cross-hub questions had nothing to
answer. This module derives the whole product set from the month-ahead history the demo seed
already stores (``demo:history``), without drawing from the seed's shared random sequence:

* **Anchor.** The stored month-ahead close ``M1(hub, day)``. Its drift over the hub's seasonal
  curve (``drift = M1 - curve(hub, next month)``) is the fundamental move of that day; TTF's
  path is the anchor the other hubs' month-ahead already follow with a basis of their own.
* **Curve.** Every delivery month ``k >= 1`` months ahead is ``curve(hub, month) + drift``
  (a parallel move, so calendar spreads stay seasonal); the front month (k = 0) the same.
* **Strips.** A quarter, season or calendar year is the day-weighted average of its months
  (flat daily volume), rounded to the hub's tick: no arbitrage within a hub, to the tick.
* **Prompt.** DA is the front month plus a prompt basis that mean-reverts (an AR(1) built from
  per-day noise, so any day is reproducible on its own and a roll-forward never re-draws a
  stored day): TTF and NBP have their own, a continental hub TTF's plus a small one of its own;
  WD sits on DA with a small gap; WE and BOM each have a small process of their own around DA,
  bounded so a prompt spread at one hub stays the prompt's normal shape.
* **Arbitrage band.** The hubs of the market-area graph (TTF, THE, PEG, ZTP, NBP) are held,
  day by day and month by month, inside the band no route can arbitrage at the simulated route
  costs (``seed_demo_desk.demo_route_costs``: the cheapest route over ``SIMULATED_TARIFFS``),
  TTF being the reference. So a locational spread nets below its transport cost unless
  planted. The board's months are held in the band; the stored month-ahead history is not.
* **Today's board.** On gas day D the board quotes D's prompt (WD = gas day D, DA the next
  quoted day: Monday's on a Friday), from each hub's newest stored month-ahead carried
  forward; WD and DA are written at every roll-forward with a small intraday move and a
  running "last" from their own stream (``demo-market-live-v1``), except TTF and NBP while
  the demo exchange feed writes them (on unless ``EUROGAS_NEXUS_DEMO_EXCHANGE_FEED=off``,
  in its trading hours).
* **Quotes.** Two-sided, around the mid, with a hub- and tenor-dependent width, on the hub's
  tick in its native quotation (NBP in pence per therm, the others in EUR/MWh).
* **Noise.** Each draw comes from ``random.Random`` seeded by a name, hub and day
  (``demo-market-v1:...``): a separate stream, so the seed's shared sequence (reports, storage
  tests) is unchanged.

Planted dislocations (:data:`PLANTED_CASES`) are deliberate, documented and the only ones: the
evaluators should find exactly them. Every price here is invented and is written with the
simulated source class; it is never a market price.
"""

from __future__ import annotations

import calendar
import math
import random
from dataclasses import dataclass
from datetime import date, timedelta

STREAM = "demo-market-v1"
#: The intraday snapshots' own stream (one per roll-forward), never the daily one.
LIVE_STREAM = "demo-market-live-v1"
#: EUR per GBP-equivalent for converting NBP into EUR for cross-hub cases (the demo FX fixing,
#: EUR base: 1 EUR = 0.853 GBP).
DEMO_EURGBP = 0.853
#: The simulated BBL crossing cost TTF -> NBP in EUR/MWh: GTS exit 0.56 + BBL 1.20 + National Gas
#: entry 0.12 (``seed_demo_desk.SIMULATED_TARIFFS``).
BBL_ROUTE_COST_EUR_MWH = 0.56 + 1.20 + 0.12
#: The storage cost the time-spread case is measured against (EUR/MWh, injection, withdrawal
#: and capacity together; invented).
STORAGE_COST_EUR_MWH = 3.8
#: L1: NBP DA net of the BBL route over TTF DA on planted days, and the arbitrage margin
#: below which it stays on every other day (EUR/MWh). O1: NBP DA premium during the outage.
L1_PLANTED_EXCESS = 1.20
L1_NO_ARB_MARGIN = 0.65
O1_OUTAGE_PREMIUM_EUR = 0.60
W1_PLANTED_GAP = 1.50
#: S1: the gas days of each month on which the demo schedule leaves the book open, and the
#: schedule lines' volumes then (MWh; every other gas day the seed's balanced volumes apply).
S1_DAYS_OF_MONTH = frozenset({18, 19, 20})
#: LNG-3: the day of each month on which the demo LNG book holds a late cargo (D1).
D1_DAY_OF_MONTH = 24
S1_OPEN_MWH = {"uk-offtake": 9_000.0, "nl-storage": 7_000.0}
#: R1 (SCHED-1): on these gas days of each month the demo TSO confirms only part of the UK
#: book's bilateral sale to Aldermoor: Aldermoor nominated less, and the lesser rule applies.
R1_DAYS_OF_MONTH = frozenset({11, 12})
R1_ALDERMOOR_MWH = 6_000.0
R1_COUNTERPARTY_MWH = 4_800.0
#: The arbitrage band (``DemoMarket.arbitrage_free``): TTF is the reference; the graph hubs are
#: held in this order; every route nets at least ARBITRAGE_MARGIN below its cost, and a hub's
#: price below TTF at least REFERENCE_MARGIN below the cost of reaching TTF (so L1's 1.20 at
#: NBP is reachable only from TTF).
REFERENCE_HUB = "TTF"
ARBITRAGE_ORDER = ("THE", "PEG", "ZTP", "NBP")
ARBITRAGE_MARGIN = 0.25
REFERENCE_MARGIN = L1_PLANTED_EXCESS + 0.15
#: Hubs whose prompt basis is their own (the others share TTF's plus a small own part).
OWN_PROMPT_BASIS = frozenset({"TTF", "NBP"})
#: BOM's distance from DA is at most this (plus its own small draw): a prompt spread at one
#: hub stays under the scan's minimum edge unless planted.
BOM_MAX_GAP = 0.30
#: Tick per hub, in the hub's native quotation.
TICKS = {"NBP": 0.01}  # pence per therm
DEFAULT_TICK = 0.005  # EUR/MWh
#: Half the bid/offer width at DA, in EUR/MWh (NBP: GBP/MWh), by hub liquidity.
HALF_WIDTH = {
    "TTF": 0.025, "NBP": 0.03, "THE": 0.04, "PEG": 0.06, "ZTP": 0.06, "PSV": 0.05,
    "CEGH": 0.075, "PVB": 0.10, "ETF": 0.10, "GTF": 0.125,
}
#: Size shown at the best bid and offer, MWh per gas day of delivery (invented, by liquidity).
QUOTE_DEPTH_MWH = {"TTF": 24000, "NBP": 14400, "THE": 14400, "PEG": 12000, "ZTP": 12000,
                   "PSV": 12000}
DEFAULT_DEPTH_MWH = 7200
#: Width multiplier by product kind.
WIDTH_FACTOR = {
    "within_day": 1.5, "day_ahead": 1.0, "weekend": 1.3, "balance_of_month": 1.4,
    "month": 1.0, "quarter": 1.4, "season": 1.8, "calendar_year": 2.2,
}
#: The rolling series kept as daily closes (history), by stored tenor key.
HISTORY_TENORS = ("within-day", "day-ahead", "weekend", "bom", "q+1", "s+1", "cal+1")
#: Weekend discount to DA and the BOM blend of the prompt basis.
WEEKEND_DISCOUNT = 0.35
#: Far-winter premium planted at CEGH (months at least this many months ahead).
CEGH_FAR_WINTER_PREMIUM = 1.0
CEGH_FAR_WINTER_FROM_MONTHS = 6


@dataclass(frozen=True)
class PlantedCase:
    case_id: str
    evaluator: str
    hubs: tuple[str, ...]
    products: tuple[str, ...]
    description: str


PLANTED_CASES: tuple[PlantedCase, ...] = (
    PlantedCase(
        "L1-nbp-over-ttf-da", "market L (locational, BBL route)", ("TTF", "NBP"), ("DA",),
        "NBP day-ahead (in EUR at the demo fixing) over TTF day-ahead exceeds the simulated "
        f"BBL route cost ({BBL_ROUTE_COST_EUR_MWH:.2f} EUR/MWh) by 1.20 on planted days "
        "(ordinal % 23 in {0, 1}); on every other day the arbitrage band keeps it at least "
        "0.65 below the cost, so the net spread flips sign on exactly those days. Only TTF "
        "reaches it: every other hub sits close enough to TTF that its route through TTF "
        "nets below zero.",
    ),
    PlantedCase(
        "W1-ttf-wd-over-da", "market P (prompt arbitrage)", ("TTF",), ("WD", "DA"),
        "TTF within-day trades 1.50 EUR/MWh over day-ahead on planted days (ordinal % 17 == 5); "
        "on every other day, and at every other hub, |WD - DA| <= 0.25.",
    ),
    PlantedCase(
        "T1-cegh-winter-over-summer", "market T, and book T on the demo storage at CEGH",
        ("CEGH",), ("Sum", "Win"),
        "CEGH carries a far-winter scarcity premium of "
        f"{CEGH_FAR_WINTER_PREMIUM:.2f} EUR/MWh on winter months {CEGH_FAR_WINTER_FROM_MONTHS}+ "
        "months ahead, so its next full winter over the summer before exceeds the storage "
        f"cost ({STORAGE_COST_EUR_MWH:.2f} EUR/MWh); every other hub stays below it. Standing, "
        "not dated: found every day the next winter is that far ahead.",
    ),
    PlantedCase(
        "O1-nbp-outage-basis", "E (event exposure)", ("NBP",), ("DA",),
        "While the demo's unplanned Norwegian-shelf outage (balancing zone NBP) is active, NBP "
        "day-ahead carries +0.60 EUR/MWh (inside the arbitrage band on non-planted days); the "
        "outage's exposure on the demo contracts it cuts is an E item in 'must act'.",
    ),
    PlantedCase(
        "S1-open-gas-day", "S (sell-down, must act)", ("NBP", "TTF"), ("DA",),
        "On gas days 18 to 20 of each month the demo schedule leaves the book open: the UK "
        f"book's industrial offtake falls to {S1_OPEN_MWH['uk-offtake']:,.0f} MWh (long at "
        f"NBP) and the NL book injects {S1_OPEN_MWH['nl-storage']:,.0f} MWh into storage "
        "(short at TTF), so the day before shows both as sell-down items. On every other gas "
        "day the schedule balances each book within its band, with the demo outages in force.",
    ),
    PlantedCase(
        "R1-lesser-rule-at-nbp", "gas-day reconciliation (SCHED-1), lesser rule", ("NBP",),
        ("WD",),
        "On gas days 11 and 12 of each month the UK book's bilateral sale to Aldermoor "
        f"({R1_ALDERMOOR_MWH:,.0f} MWh for the day) is nominated in full, but Aldermoor "
        f"nominated {R1_COUNTERPARTY_MWH:,.0f} MWh and the demo TSO confirmed the lesser: "
        f"{R1_ALDERMOOR_MWH - R1_COUNTERPARTY_MWH:,.0f} MWh cut, the UK book long by that at "
        "NBP. On every other gas day the trade is nominated and matched in full, and each "
        "simulated prompt trade is nominated and matched as it is booked.",
    ),
    PlantedCase(
        "D1-lng-cargo-late", "LNG-3 disruption re-optimisation (cargo options)",
        ("ZTP", "TTF", "PEG", "PVB"), ("cargo",),
        f"On day {D1_DAY_OF_MONTH} of each month the demo LNG book (demo-lng-nwe) holds Demo "
        "Meridian, due two days after its Zeebrugge slot starts, beside two cargoes running "
        "normally (Rotterdam, Huelva with a firm daily delivery), a spare Dunkerque slot, "
        "illustrative Zeebrugge borrow, send-out, storage and interruptible offers and a "
        "pipeline supply at ZTP. The re-optimisation finds Meridian disrupted, values wait, "
        "borrow, buy, divert and both swaps, and marks the Huelva swap infeasible. On every "
        "other day the book is not seeded and no supply is disrupted.",
    ),
)


def r1_planted(gas_day: date) -> bool:
    """R1 is planted on the gas day itself (the reconciliation of that day shows it)."""

    return gas_day.day in R1_DAYS_OF_MONTH


def d1_planted(day: date) -> bool:
    """D1 is seeded on that calendar day only (re-seeding any other day removes it)."""

    return day.day == D1_DAY_OF_MONTH


def l1_planted(day: date) -> bool:
    return day.toordinal() % 23 in (0, 1)


def w1_planted(day: date) -> bool:
    return day.toordinal() % 17 == 5


def s1_planted(gas_day: date) -> bool:
    """S1 is planted on the gas day itself (found the day before, as tomorrow's residual)."""

    return gas_day.day in S1_DAYS_OF_MONTH


def month_start(day: date, offset: int = 0) -> date:
    index = day.year * 12 + day.month - 1 + offset
    return date(index // 12, index % 12 + 1, 1)


_NOISE_CACHE: dict[tuple[str, str, date, float], float] = {}


def _noise(hub: str, label: str, day: date, sigma: float) -> float:
    """One draw per (hub, label, day): reproducible on its own, whatever else was drawn."""

    key = (hub, label, day, sigma)
    value = _NOISE_CACHE.get(key)
    if value is None:
        if len(_NOISE_CACHE) > 200_000:
            _NOISE_CACHE.clear()
        value = random.Random(f"{STREAM}:{hub}:{label}:{day.isoformat()}").gauss(0.0, sigma)
        _NOISE_CACHE[key] = value
    return value


def _bounded(hub: str, label: str, day: date, sigma: float, bound: float) -> float:
    """One draw of a named stream, held within +/- ``bound``."""

    return max(-bound, min(bound, _noise(hub, label, day, sigma)))


def live_noise(hub: str, code: str, day: date, stamp: str, sigma: float = 0.02,
               bound: float = 0.05) -> float:
    """The intraday move of a prompt quote in one roll-forward snapshot (its own stream,
    ``demo-market-live-v1``): small, so the day's prompt shape and the planted cases hold."""

    draw = random.Random(f"{LIVE_STREAM}:{hub}:{code}:{day.isoformat()}:{stamp}").gauss(0, sigma)
    return max(-bound, min(bound, draw))


def prompt_basis(hub: str, day: date) -> float:
    """A mean-reverting prompt basis (AR(1), phi 0.8) built from per-day noise only."""

    return round(sum(0.8**k * _noise(hub, "prompt", day - timedelta(days=k), 0.18)
                     for k in range(25)), 6)


def depth_of(hub: str) -> float:
    return float(QUOTE_DEPTH_MWH.get(hub, DEFAULT_DEPTH_MWH))


def tick_of(hub: str) -> float:
    return TICKS.get(hub, DEFAULT_TICK)


class DemoMarket:
    """Prices of every product of the demo hubs on a day, from the stored month-ahead."""

    def __init__(self, curve_price, *, eur_per_mwh_to_native=None, route_costs=None):
        #: ``curve_price(hub, first_of_month)`` -> the hub's seasonal curve (per MWh, hub currency).
        self.curve_price = curve_price
        #: ``(hub, price per MWh) -> native price`` (NBP p/th), identity elsewhere.
        self.to_native = eur_per_mwh_to_native or (lambda hub, price: price)
        #: ``(buy hub, sell hub) -> EUR/MWh``: the cheapest route over the simulated tariffs
        #: (``seed_demo_desk.demo_route_costs``); empty: no arbitrage band is applied.
        self.route_costs = dict(route_costs or {})
        self.anchors: dict[date, dict[str, float]] = {}
        self._months: dict[tuple[date, date], dict[str, float]] = {}

    # ------------------------------------------------------------------ curve
    def drift(self, hub: str, day: date, month_ahead: float) -> float:
        return month_ahead - self.curve_price(hub, month_start(day, 1))

    def raw_month_price(self, hub: str, day: date, month_ahead: float, first: date) -> float:
        """A delivery month on ``day`` before the arbitrage band: curve plus the day's drift."""

        price = self.curve_price(hub, first) + self.drift(hub, day, month_ahead)
        ahead = (first.year - day.year) * 12 + first.month - day.month
        if hub == "CEGH" and ahead >= CEGH_FAR_WINTER_FROM_MONTHS and first.month in (
            10, 11, 12, 1, 2, 3
        ):
            price += CEGH_FAR_WINTER_PREMIUM
        return price

    def set_anchors(self, day: date, anchors: dict[str, float]) -> None:
        """The month-ahead of every hub on ``day``: months are then held in the arbitrage band
        across hubs (:meth:`arbitrage_free`). Without anchors a hub's months are its own."""

        self.anchors[day] = dict(anchors)
        self._months = {key: value for key, value in self._months.items() if key[0] != day}

    def month_price(self, hub: str, day: date, month_ahead: float, first: date) -> float:
        """A delivery month on ``day`` (unrounded): the seasonal curve plus the day's drift,
        held in the arbitrage band when the day's anchors are set (:meth:`set_anchors`)."""

        anchors = self.anchors.get(day)
        if not anchors or hub not in anchors or not self.route_costs:
            return self.raw_month_price(hub, day, month_ahead, first)
        key = (day, first)
        if key not in self._months:
            raw = {other: self.raw_month_price(other, day, anchor, first)
                   for other, anchor in anchors.items()}
            self._months[key] = self._from_eur(self.arbitrage_free(
                self._to_eur(raw), upper_margin={"NBP": L1_NO_ARB_MARGIN}))
        return self._months[key][hub]

    def strip(self, hub: str, day: date, month_ahead: float, first: date, last: date) -> float:
        """Day-weighted average of the months from ``first`` to ``last`` (inclusive days)."""

        total = weight = 0.0
        month = month_start(first)
        while month <= last:
            days_in = calendar.monthrange(month.year, month.month)[1]
            start = max(month, first)
            end = min(month + timedelta(days=days_in - 1), last)
            span = (end - start).days + 1
            total += self.month_price(hub, day, month_ahead, month) * span
            weight += span
            month = month_start(month, 1)
        return total / weight

    # ------------------------------------------------------------------ prompt
    def prompts(self, day: date, anchors: dict[str, float], *,
                outage: bool = False) -> dict[str, dict[str, float]]:
        """WD, DA, WE and BOM (unrounded, per MWh in the hub's currency) of every hub in
        ``anchors`` (hub -> that day's month-ahead) on ``day``.

        DA is the front month plus a prompt basis: TTF's and NBP's own, a continental hub's
        TTF's plus a small one of its own (one region, one weather). The graph hubs' DA is then
        held inside the no-arbitrage band of the simulated route costs
        (:meth:`arbitrage_free`); NBP's against TTF exactly as L1 and O1 describe. WD sits on
        DA with a small gap (W1 at TTF); WE and BOM each have a small process of their own
        around DA, bounded so that a prompt spread at one hub stays the prompt's normal shape.
        """

        fronts = {hub: self.month_price(hub, day, anchor, month_start(day))
                  for hub, anchor in anchors.items()}
        raw: dict[str, float] = {}
        for hub, front in fronts.items():
            if hub in OWN_PROMPT_BASIS:
                basis = prompt_basis(hub, day)
            else:
                basis = prompt_basis("TTF", day) + _bounded(hub, "prompt-own", day, 0.04, 0.10)
            raw[hub] = front + basis
            if hub == "NBP" and outage:
                raw[hub] += O1_OUTAGE_PREMIUM_EUR * DEMO_EURGBP
        day_ahead = self._from_eur(self.arbitrage_free(
            self._to_eur(raw), upper_margin={"NBP": L1_NO_ARB_MARGIN}))
        if "NBP" in day_ahead and "TTF" in day_ahead and l1_planted(day):
            cost = self.route_cost("TTF", "NBP")
            day_ahead["NBP"] = (day_ahead["TTF"] + cost + L1_PLANTED_EXCESS) * DEMO_EURGBP
        out: dict[str, dict[str, float]] = {}
        for hub, da in day_ahead.items():
            front = fronts[hub]
            wd_gap = max(-0.25, min(0.25, _noise(hub, "wd", day, 0.08)))
            if hub == "TTF" and w1_planted(day):
                wd_gap = W1_PLANTED_GAP
            bom_basis = max(-BOM_MAX_GAP, min(BOM_MAX_GAP, 0.5 * (da - front)))
            out[hub] = {
                "within-day": da + wd_gap,
                "day-ahead": da,
                "weekend": da - WEEKEND_DISCOUNT + _bounded(hub, "we", day, 0.06, 0.12),
                "bom": da - bom_basis + _bounded(hub, "bom", day, 0.04, 0.08),
            }
        return out

    def prompt(self, hub: str, day: date, month_ahead: float, *, outage: bool = False,
               ttf_month_ahead: float | None = None) -> dict[str, float]:
        """One hub's prompt (see :meth:`prompts`); NBP needs TTF's month-ahead for L1."""

        anchors = {hub: month_ahead}
        if ttf_month_ahead is not None:
            anchors["TTF"] = ttf_month_ahead
        return self.prompts(day, anchors, outage=outage)[hub]

    # ------------------------------------------------------------------ arbitrage
    def route_cost(self, buy: str, sell: str) -> float:
        """The simulated route cost from ``buy`` to ``sell`` (EUR/MWh); ``inf`` when none."""

        if (buy, sell) == ("TTF", "NBP"):
            return self.route_costs.get((buy, sell), BBL_ROUTE_COST_EUR_MWH)
        return self.route_costs.get((buy, sell), math.inf)

    def _to_eur(self, prices: dict[str, float]) -> dict[str, float]:
        return {hub: price / DEMO_EURGBP if hub == "NBP" else price
                for hub, price in prices.items()}

    def _from_eur(self, prices: dict[str, float]) -> dict[str, float]:
        return {hub: price * DEMO_EURGBP if hub == "NBP" else price
                for hub, price in prices.items()}

    def arbitrage_free(self, eur: dict[str, float], *,
                       upper_margin: dict[str, float] | None = None) -> dict[str, float]:
        """Hold the graph hubs' prices (EUR/MWh) inside the band no route can arbitrage.

        TTF is the reference and is never moved. Each other hub, in :data:`ARBITRAGE_ORDER`,
        is held so that buying at any hub already fixed and selling at it (or the reverse)
        nets at least :data:`ARBITRAGE_MARGIN` below the route cost; against TTF the lower
        side keeps :data:`REFERENCE_MARGIN`, so a planted dislocation at NBP (L1) is reachable
        only from TTF, not through it. ``upper_margin`` widens the upper side against TTF for a
        hub (NBP: L1's no-arbitrage margin). Hubs without route costs are left as they are.
        """

        out = dict(eur)
        if REFERENCE_HUB not in out or not self.route_costs:
            return out
        fixed = [REFERENCE_HUB]
        for hub in ARBITRAGE_ORDER:
            if hub not in out:
                continue
            low, high = -math.inf, math.inf
            for other in fixed:
                to_other = self.route_cost(hub, other)
                from_other = self.route_cost(other, hub)
                lower = REFERENCE_MARGIN if other == REFERENCE_HUB else ARBITRAGE_MARGIN
                upper = ((upper_margin or {}).get(hub, ARBITRAGE_MARGIN)
                         if other == REFERENCE_HUB else ARBITRAGE_MARGIN)
                low = max(low, out[other] - to_other + lower)
                high = min(high, out[other] + from_other - upper)
            if low <= high:
                out[hub] = min(max(out[hub], low), high)
            else:  # the band is empty by less than the margins: the middle nets <= 0 both ways
                out[hub] = (low + high) / 2
            fixed.append(hub)
        return out

    # ------------------------------------------------------------------ quotes
    def quote(self, hub: str, mid: float, kind: str) -> tuple[float, float, float]:
        """(bid, mid, ask) in the hub's native quotation, on its tick, bid < ask."""

        tick = tick_of(hub)
        native_mid = self.to_native(hub, mid)
        half = HALF_WIDTH.get(hub, 0.1) * WIDTH_FACTOR.get(kind, 1.5)
        native_half = abs(self.to_native(hub, mid + half) - native_mid)
        bid = math.floor((native_mid - native_half) / tick + 1e-9) * tick
        ask = math.ceil((native_mid + native_half) / tick - 1e-9) * tick
        if ask - bid < tick - 1e-12:
            ask = bid + tick
        digits = 3 if tick < 0.01 else 2
        mid_on_tick = round(round(native_mid / tick) * tick, digits)
        return round(bid, digits), mid_on_tick, round(ask, digits)


def round_to_tick(value: float, tick: float) -> float:
    digits = 3 if tick < 0.01 else 2
    return round(round(value / tick) * tick, digits)
