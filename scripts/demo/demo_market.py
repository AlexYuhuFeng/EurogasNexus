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
  stored day); WD sits on DA with a small gap, WE below DA (weekend demand), BOM between.
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
#: EUR per GBP-equivalent for converting NBP into EUR for cross-hub cases (the demo FX fixing,
#: EUR base: 1 EUR = 0.853 GBP).
DEMO_EURGBP = 0.853
#: The simulated BBL crossing cost TTF -> NBP in EUR/MWh: GTS exit 0.56 + BBL 1.20 + National Gas
#: entry 0.12 (``seed_demo_desk.SIMULATED_TARIFFS``).
BBL_ROUTE_COST_EUR_MWH = 0.56 + 1.20 + 0.12
#: The storage cost the time-spread case is measured against (EUR/MWh, injection, withdrawal
#: and capacity together; invented).
STORAGE_COST_EUR_MWH = 3.8
#: Tick per hub, in the hub's native quotation.
TICKS = {"NBP": 0.01}  # pence per therm
DEFAULT_TICK = 0.005  # EUR/MWh
#: Half the bid/offer width at DA, in EUR/MWh (NBP: GBP/MWh), by hub liquidity.
HALF_WIDTH = {
    "TTF": 0.025, "NBP": 0.03, "THE": 0.04, "PEG": 0.06, "ZTP": 0.06, "PSV": 0.05,
    "CEGH": 0.075, "PVB": 0.10, "ETF": 0.10, "GTF": 0.125,
}
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
        "L1-nbp-over-ttf-da", "L (locational) / A (arbitrage)", ("TTF", "NBP"), ("DA",),
        "NBP day-ahead (in EUR at the demo fixing) over TTF day-ahead exceeds the simulated "
        f"BBL route cost ({BBL_ROUTE_COST_EUR_MWH:.2f} EUR/MWh) by 1.20 on planted days "
        "(ordinal % 23 in {0, 1}); on every other day it is 0.65-1.15 below the cost (0.05-0.55 "
        "while O1 is active), so the "
        "net spread flips sign on exactly those days.",
    ),
    PlantedCase(
        "W1-ttf-wd-over-da", "A (prompt arbitrage)", ("TTF",), ("WD", "DA"),
        "TTF within-day trades 1.50 EUR/MWh over day-ahead on planted days (ordinal % 17 == 5); "
        "on every other day, and at every other hub, |WD - DA| <= 0.25.",
    ),
    PlantedCase(
        "T1-cegh-winter-over-summer", "T (storage time spread)", ("CEGH",), ("Sum", "Win"),
        "CEGH carries a far-winter scarcity premium of "
        f"{CEGH_FAR_WINTER_PREMIUM:.2f} EUR/MWh on winter months {CEGH_FAR_WINTER_FROM_MONTHS}+ "
        "months ahead, so its next full winter over the summer before it exceeds the storage "
        f"cost ({STORAGE_COST_EUR_MWH:.2f} EUR/MWh); every other hub stays below it.",
    ),
    PlantedCase(
        "O1-nbp-outage-basis", "event exposure", ("NBP",), ("DA",),
        "While the demo's unplanned Norwegian-shelf outage (balancing zone NBP) is active, NBP "
        "day-ahead carries +0.60 EUR/MWh; it does not lift the L1 net spread above zero.",
    ),
)


def l1_planted(day: date) -> bool:
    return day.toordinal() % 23 in (0, 1)


def w1_planted(day: date) -> bool:
    return day.toordinal() % 17 == 5


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


def prompt_basis(hub: str, day: date) -> float:
    """A mean-reverting prompt basis (AR(1), phi 0.8) built from per-day noise only."""

    return round(sum(0.8**k * _noise(hub, "prompt", day - timedelta(days=k), 0.18)
                     for k in range(25)), 6)


def tick_of(hub: str) -> float:
    return TICKS.get(hub, DEFAULT_TICK)


class DemoMarket:
    """Prices of every product of the demo hubs on a day, from the stored month-ahead."""

    def __init__(self, curve_price, *, eur_per_mwh_to_native=None):
        #: ``curve_price(hub, first_of_month)`` -> the hub's seasonal curve (per MWh, hub currency).
        self.curve_price = curve_price
        #: ``(hub, price per MWh) -> native price`` (NBP p/th), identity elsewhere.
        self.to_native = eur_per_mwh_to_native or (lambda hub, price: price)

    # ------------------------------------------------------------------ curve
    def drift(self, hub: str, day: date, month_ahead: float) -> float:
        return month_ahead - self.curve_price(hub, month_start(day, 1))

    def month_price(self, hub: str, day: date, month_ahead: float, first: date) -> float:
        """A delivery month on ``day`` (unrounded): the seasonal curve plus the day's drift."""

        price = self.curve_price(hub, first) + self.drift(hub, day, month_ahead)
        ahead = (first.year - day.year) * 12 + first.month - day.month
        if hub == "CEGH" and ahead >= CEGH_FAR_WINTER_FROM_MONTHS and first.month in (
            10, 11, 12, 1, 2, 3
        ):
            price += CEGH_FAR_WINTER_PREMIUM
        return price

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
    def prompt(self, hub: str, day: date, month_ahead: float, *,
               ttf_day_ahead: float | None = None, outage: bool = False) -> dict[str, float]:
        """WD, DA, WE and BOM (unrounded) for ``hub`` on ``day``.

        NBP's day-ahead is set against TTF's (``ttf_day_ahead``) so the L1 case is exact:
        it holds wherever TTF's day-ahead is known, which the generator ensures by pricing TTF
        first.
        """

        front = self.month_price(hub, day, month_ahead, month_start(day))
        basis = prompt_basis(hub, day)
        day_ahead = front + basis
        if hub == "NBP" and ttf_day_ahead is not None:
            gap = 1.20 if l1_planted(day) else -0.90 + max(-0.25, min(0.25, _noise(
                hub, "l1", day, 0.12)))
            net_eur = BBL_ROUTE_COST_EUR_MWH + gap + (0.60 if outage else 0.0)
            day_ahead = (ttf_day_ahead + net_eur) * DEMO_EURGBP
        wd_gap = max(-0.25, min(0.25, _noise(hub, "wd", day, 0.08)))
        if hub == "TTF" and w1_planted(day):
            wd_gap = 1.50
        return {
            "within-day": day_ahead + wd_gap,
            "day-ahead": day_ahead,
            "weekend": day_ahead - WEEKEND_DISCOUNT,
            "bom": front + 0.5 * basis,
        }

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
