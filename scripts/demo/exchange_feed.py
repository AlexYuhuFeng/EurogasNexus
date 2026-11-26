#!/usr/bin/env python
"""Demo exchange feed: a simulated live exchange screen for every demo hub, and a TTF/NBP replay.

Demo profile only. Every tick is invented, stored as simulated (``DEMO_Sim`` by the continuous
feed, ``EEX_Sim`` by the API replay) and labelled simulated wherever it travels; it is never a
market price (AGENTS.md rule 17). It exists so the screens that read prices (the Prices board,
Today, marks and P&L, spreads, the prompt desk, strategy evaluation on arrival) move as they
would on a licensed feed, and can be seen and measured without one.

**Continuous (``--continuous``, the demo server's feed, :class:`LiveScreen`).** Every demo hub
(TTF, NBP, THE, PEG, ZTP, PSV, CEGH, PVB and the Danish ETF, which OTC calls GTF) is quoted on
WD, DA, WE and the front month, quarter and season, each instrument on its own clock (a fresh
draw of 1-5 seconds after each quote), small moves on the hub's tick, the odd print, with
session statistics (open/high/low, VWAP, volume, count, prior settlement). The rest of each
hub's curve (months to M+12, quarters, the next winter, two calendar years) requotes with the
front in whole curve moves, so a strip stays its months' average: no arbitrage within a hub. The
prices start on the demo board of the gas day (``seed_demo_desk.demo_board_now``, priced by
``demo_market.py``) and revert to it, a common factor moves the hubs together and each hub's own
part is bounded so a locational spread stays inside the demo market's arbitrage band; the
planted P1/P2 prompt cases are laid on the path on their schedule. It writes straight through
``application.market_ticks.ingest_ticks`` (the path a licensed connector's batches take), so the
live stream's ``prices`` notices fire as for a real feed.

Session (``--session`` or ``EUROGAS_NEXUS_DEMO_FEED_SESSION``): ``exchange`` (default),
simulated trading hours 07:00-19:00 CET/CEST every day; ``24h``, a demo-only session that never
closes so a demo opened at 03:00 still moves (the hosted demo sets it). Neither is a real
venue's timetable: ICE Endex and EEX gas sessions differ, and the feed's status line says so.

**Replay (default, ``/api/market/ticks``).** Bursty two-sided quotes and prints for TTF and NBP
WD/DA (:func:`session_events`, one ``random.Random`` stream of its own,
``demo-exchange-feed-v1``):

* **Anchor.** Each instrument starts at the demo market's own mid for the day (the stored
  ``DEMO_Sim`` board quote), so the session sits on the demo market's daily path.
* **Path.** The mid moves on a tick grid as an Ornstein-Uhlenbeck walk around the anchor; each WD
  carries its own mean-reverting premium over its DA (the spread a WD–DA rule trades), with rare
  planted dislocations (``--dislocations`` per hour) that revert over a few minutes.
* **Cadence.** Arrivals are exponential with a two-state regime (calm: about one event every
  four seconds per instrument; burst: several per second), switching at random, as screens do
  around news and the close.
* **Book and prints.** Top of book on the hub's tick with a width by hub and product; sizes in
  MW (NBP therms/day) per side. About one event in four is a trade: an aggressor lifts the offer
  or hits the bid for part of the quoted size (screen), or, rarely, a larger block at the mid.
  Session open/high/low, VWAP, volume and count (screen prints only) travel with every quote,
  with yesterday's demo close as the prior settlement. No open interest (spot products).

Delivery: batches POSTed to ``/api/market/ticks`` as a data-operations identity (``--user``),
the way a feed adapter delivers, either in real time or as a compressed ``--replay`` of
``--minutes`` of session time.

    python scripts/demo/exchange_feed.py --minutes 10                 # real time
    python scripts/demo/exchange_feed.py --minutes 120 --replay       # compressed session
    python scripts/demo/exchange_feed.py --continuous --session 24h   # the demo server's feed
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

STREAM = "demo-exchange-feed-v1"
SOURCE = "EEX_Sim"
#: (hub, product): native tick and half-width at the touch, in the native unit.
INSTRUMENTS = {
    ("TTF", "WD"): (0.005, 0.035),
    ("TTF", "DA"): (0.005, 0.025),
    ("NBP", "WD"): (0.01, 0.10),
    ("NBP", "DA"): (0.01, 0.08),
}
#: Fallback anchors when the store holds no demo board quote (native units).
FALLBACK = {("TTF", "WD"): 41.30, ("TTF", "DA"): 41.17, ("NBP", "WD"): 98.1, ("NBP", "DA"): 97.7}
#: Mean-reversion speed per second and volatility per sqrt(second), native units.
KAPPA = 1 / 600
SIGMA = {"TTF": 0.0025, "NBP": 0.007}
WD_PREMIUM_SIGMA = 0.0035
WD_PREMIUM_KAPPA = 1 / 240


@dataclass
class Book:
    hub: str
    product: str
    anchor: float
    mid: float
    tick: float
    half: float
    prior_settlement: float
    stats: dict = field(default_factory=lambda: {"open": None, "high": None, "low": None,
                                                 "pv": 0.0, "volume": 0.0, "count": 0,
                                                 "last": None, "last_qty": None})

    def quote(self, rng: random.Random, at: datetime, sequence: int,
              jitter: float = 0.6) -> dict:
        half = self.half * (1.0 + jitter * rng.random())
        bid = math.floor((self.mid - half) / self.tick) * self.tick
        ask = math.ceil((self.mid + half) / self.tick) * self.tick
        if ask - bid < self.tick:
            ask = bid + self.tick
        digits = 3 if self.tick < 0.01 else 2
        sizes = (5, 10, 15, 20, 25, 30, 50) if self.hub != "NBP" else (
            25000, 50000, 75000, 100000, 150000)
        s = self.stats
        vwap = round(s["pv"] / s["volume"], 4) if s["volume"] else None
        self.bid, self.ask = round(bid, digits), round(ask, digits)
        self.bid_qty, self.ask_qty = rng.choice(sizes), rng.choice(sizes)
        return {
            "hub": self.hub, "product": self.product, "exchange_time": at.isoformat(),
            "sequence": sequence, "bid": self.bid, "ask": self.ask,
            "bid_qty": self.bid_qty, "ask_qty": self.ask_qty,
            "last": s["last"], "last_qty": s["last_qty"], "open": s["open"], "high": s["high"],
            "low": s["low"], "vwap": vwap, "volume": s["volume"] or None,
            "trade_count": s["count"], "prior_settlement": self.prior_settlement,
        }

    def trade(self, rng: random.Random, at: datetime, sequence: int) -> dict | None:
        if not hasattr(self, "bid"):
            return None
        block = rng.random() < 0.08
        if block:
            price = round(round(self.mid / self.tick) * self.tick, 3 if self.tick < 0.01 else 2)
            qty = (100 if self.hub != "NBP" else 500000) * rng.choice((1, 2, 3))
            side = None
        else:
            buy = rng.random() < 0.5
            price = self.ask if buy else self.bid
            quoted = self.ask_qty if buy else self.bid_qty
            step = 5 if self.hub != "NBP" else 25000
            qty = max(step, round(quoted * rng.uniform(0.2, 1.0) / step) * step)
            side = "buy" if buy else "sell"
            s = self.stats
            s["open"] = price if s["open"] is None else s["open"]
            s["high"] = price if s["high"] is None else max(s["high"], price)
            s["low"] = price if s["low"] is None else min(s["low"], price)
            s["pv"] += price * qty
            s["volume"] += qty
            s["count"] += 1
            s["last"], s["last_qty"] = price, qty
        return {"trade_id": f"{at:%Y%m%d%H%M%S%f}-{self.hub}-{self.product}-{sequence}",
                "hub": self.hub, "product": self.product, "exchange_time": at.isoformat(),
                "price": price, "qty": qty, "trade_type": "block" if block else "screen",
                "aggressor": side}


def anchors(api: str, token: str) -> dict:
    """Today's demo board mids (native units) from the market quote read."""

    out = {}
    for hub in ("TTF", "NBP"):
        rows = call(api, token, "GET", f"/api/market/quotes?hub={hub}&limit=200").get("data") or []
        for row in rows:
            if row.get("source_system") != "DEMO_Sim":
                continue
            product = (row.get("metadata_json") or {}).get("product_label")
            native = (row.get("metadata_json") or {}).get("native_mid")
            if (hub, product) in INSTRUMENTS and native and (hub, product) not in out:
                out[(hub, product)] = float(native)
    return out


def call(api: str, token: str, method: str, path: str, payload: dict | None = None) -> dict:
    request = urllib.request.Request(
        api + path, None if payload is None else json.dumps(payload).encode(),
        {"Content-Type": "application/json", "X-Eurogas-Session": token}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        return {"http_error": exc.code, "body": exc.read().decode()[:500]}


def login(api: str, user: str, password: str) -> str:
    body = json.dumps({"username": user, "password": password, "client": "desktop"}).encode()
    request = urllib.request.Request(api + "/api/dev/auth/login", body,
                                     {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)["data"]["session_token"]


#: Planted prompt cases (UTC is not used: the schedule is in CET/CEST, the desk's clock).
#: P1: TTF WD over DA by P1_PREMIUM for P1_MINUTES from minute 10, 30 and 50 of each trading
#: hour (the sign alternates by hour); P2: NBP DA over TTF DA net of the simulated BBL route
#: (1.88 EUR/MWh) by P2_EXCESS for P2_MINUTES from 10:00 and 15:00.
P1_MINUTES_PAST = (10, 30, 50)
P1_MINUTES = 3
P1_PREMIUM = 0.60
P2_STARTS = ((10, 0), (15, 0))
P2_MINUTES = 10
P2_EXCESS = 0.80
P2_OUTSIDE_MARGIN = 0.30
BBL_ROUTE_COST = 1.88
DEMO_EURGBP = 0.853
THERM_MWH = 0.0293071
TRADING_HOURS = (7, 19)  # CET/CEST, every day


def _local(at: datetime) -> datetime:
    from zoneinfo import ZoneInfo

    return at.astimezone(ZoneInfo("Europe/Amsterdam"))


def planted_p1(at: datetime) -> float:
    """The planted TTF WD − DA premium at ``at`` (0 outside a P1 window)."""

    local = _local(at)
    for minute in P1_MINUTES_PAST:
        if minute <= local.minute < minute + P1_MINUTES:
            return P1_PREMIUM * (1 if local.hour % 2 == 0 else -1)
    return 0.0


def planted_p2(at: datetime) -> bool:
    local = _local(at)
    return any(
        0 <= (local.hour * 60 + local.minute) - (hour * 60 + minute) < P2_MINUTES
        for hour, minute in P2_STARTS
    )


def in_trading_hours(at: datetime) -> bool:
    return TRADING_HOURS[0] <= _local(at).hour < TRADING_HOURS[1]


def _eur_to_pth(eur_mwh: float) -> float:
    return eur_mwh * DEMO_EURGBP * 100 * THERM_MWH


def _pth_to_eur(pth: float) -> float:
    return pth / 100 / THERM_MWH / DEMO_EURGBP


def session_events(rng: random.Random, books: dict, start: datetime, minutes: float,
                   dislocations_per_hour: float, planted: bool = False):
    """Yield (time, quotes, trades) events for ``minutes`` of session time.

    With ``planted`` the P1 and P2 cases are laid on the path on their schedule.
    """

    now = start
    end = start + timedelta(minutes=minutes)
    burst = False
    premium = {hub: books[(hub, "WD")].mid - books[(hub, "DA")].mid for hub in ("TTF", "NBP")}
    premium_anchor = dict(premium)
    shock = {"TTF": 0.0, "NBP": 0.0}
    sequence = 0
    while now < end:
        rate = 4.0 if burst else 0.8  # events per second across the four instruments
        dt = rng.expovariate(rate)
        now += timedelta(seconds=dt)
        if rng.random() < (0.02 if not burst else 0.05):
            burst = not burst
        # Common factor per hub, OU around each anchor.
        for hub in ("TTF", "NBP"):
            draw = rng.gauss(0.0, SIGMA[hub] * math.sqrt(dt))
            for product in ("WD", "DA"):
                book = books[(hub, product)]
                book.mid += KAPPA * (book.anchor - book.mid) * dt + draw
        # Each hub's WD premium over DA reverts on its own; a planted dislocation lifts it
        # (NBP in pence per therm: about three times the EUR/MWh figure).
        for hub, scale in (("TTF", 1.0), ("NBP", 3.0)):
            if rng.random() < dislocations_per_hour / 3600 * dt:
                shock[hub] += rng.choice((-1, 1)) * rng.uniform(0.12, 0.2) * scale
            shock[hub] *= math.exp(-dt / 180)
            premium[hub] += WD_PREMIUM_KAPPA * (premium_anchor[hub] - premium[hub]) * dt + (
                rng.gauss(0.0, WD_PREMIUM_SIGMA * scale * math.sqrt(dt)))
            books[(hub, "WD")].mid = books[(hub, "DA")].mid + premium[hub] + shock[hub]
        if planted:
            books[("TTF", "WD")].mid += planted_p1(now)
            ttf_da = books[("TTF", "DA")].mid
            nbp_da_eur = _pth_to_eur(books[("NBP", "DA")].mid)
            if planted_p2(now):
                nbp_da_eur = ttf_da + BBL_ROUTE_COST + P2_EXCESS
            else:
                nbp_da_eur = min(nbp_da_eur, ttf_da + BBL_ROUTE_COST - P2_OUTSIDE_MARGIN)
            books[("NBP", "DA")].mid = _eur_to_pth(nbp_da_eur)
        key = rng.choice(list(books))
        sequence += 1
        quotes, trades = [], []
        if rng.random() < 0.25:
            printed = books[key].trade(rng, now, sequence)
            if printed:
                trades.append(printed)
        quotes.append(books[key].quote(rng, now, sequence))
        if rng.random() < 0.5:  # the pair often requotes together
            other = (key[0], "DA" if key[1] == "WD" else "WD")
            quotes.append(books[other].quote(rng, now, sequence))
        yield now, quotes, trades


class TradeBooker:
    """A trickle of simulated booked prompt trades into the demo books (``ETRM_Sim``).

    Demo only: written straight into the book store the ETRM import writes (the simulator
    runs beside the demo database), labelled simulated, at the touch with a small random
    improvement, so the prompt desk's performance figures have something to measure.
    """

    BOOKS = {"TTF": "demo-nl-ttf", "NBP": "demo-uk-nbp"}

    def __init__(self, every_seconds: float, rng: random.Random) -> None:
        from eurogas_nexus.db.session import get_session_factory

        self.every = every_seconds
        self.rng = rng
        self.last: datetime | None = None
        self.factory = get_session_factory()
        self.booked = 0

    def maybe_book(self, at: datetime, books: dict) -> None:
        if self.last is not None and (at - self.last).total_seconds() < self.every:
            return
        self.last = at
        from eurogas_nexus.db.models import ScreenOrderObservationRecord
        from eurogas_nexus.domain.market.gas_day import gas_day_label
        from eurogas_nexus.domain.market.products import resolve_product
        from eurogas_nexus.domain.market.units import convert_price

        hub, product = self.rng.choice([("TTF", "WD"), ("TTF", "DA"), ("NBP", "WD"),
                                        ("NBP", "DA")])
        book = books.get((hub, product))
        if book is None or not hasattr(book, "bid"):
            return
        buy = self.rng.random() < 0.5
        improve = self.rng.choice((0, 0, 1)) * book.tick
        native = (book.ask - improve) if buy else (book.bid + improve)
        period = resolve_product(product, date.fromisoformat(gas_day_label(at)))
        if hub == "NBP":
            price, unit, currency = convert_price(native, "GBp/th", "GBP/MWh"), "GBP/MWh", "GBP"
            mwh = self.rng.choice((25000, 50000)) * 0.0293071
        else:
            price, unit, currency = native, "EUR/MWh", "EUR"
            mwh = self.rng.choice((5, 10, 20)) * 24.0
        self.booked += 1
        trade_id = f"SIM-{at:%Y%m%d%H%M%S}-{self.booked}"
        with self.factory() as session:
            session.merge(ScreenOrderObservationRecord(
                order_observation_id=f"etrm-sim-{trade_id}", provider_id="ETRM",
                venue="Exchange", account_label="Prompt counterparty", external_order_id=trade_id,
                side="BUY" if buy else "SELL", order_type="TRADE", hub=hub, product="ETRM",
                contract_code=trade_id, delivery_start_utc=period.delivery_start_utc,
                delivery_end_utc=period.delivery_end_utc, price=round(price, 6),
                currency=currency, unit=unit, quantity_mwh=round(mwh, 3),
                filled_quantity_mwh=round(mwh, 3), remaining_quantity_mwh=0.0, status="FILLED",
                observed_at_utc=at, source_system="ETRM_Sim",
                source_reference="demo:prompt-trades", linked_strategy_id=None,
                linked_resource_id=None, research_only=True, human_review_required=True,
                book_id=self.BOOKS[hub]))
            # SCHED-1: the demo scheduling system nominates each booked prompt trade at once
            # and the TSO matches it, so the reconciliation shows no break for it.
            from eurogas_nexus.db.models import GasDayNominationEventRecord

            day = date.fromisoformat(gas_day_label(period.delivery_start_utc))
            for status in ("sent", "confirmed"):
                session.merge(GasDayNominationEventRecord(
                    event_id=f"sim-nom-{trade_id}-{status}"[:64], gas_day=day,
                    line_ref=f"trade:etrm-sim-{trade_id}", hub=hub, book_id=self.BOOKS[hub],
                    step="nomination", status=status, quantity_mwh=round(mwh, 3), agent=None,
                    origin="import", recorded_by="Scheduling import", recorded_at_utc=at,
                    note=None, source_system="ETRM_Sim", counterparty="Prompt counterparty",
                    direction="in" if buy else "out"))
            session.commit()


FEED_SOURCE = "DEMO_Sim"
FEED_SOURCE_ID = "src-demo-exchange-feed"
FEED_REFERENCE = "feed:simulated-exchange"
#: How long the continuous feed keeps its own rows (quotes, prints, status runs, booked
#: simulated trades): the demo's small PostgreSQL must not fill.
RETENTION = timedelta(hours=48)
#: Every quote of the last hour is kept; older quotes are thinned to the last one of each
#: instrument in each :data:`THIN_BUCKET` (the intraday chart's resolution), so 48 hours of a
#: screen that ticks every few seconds stays a few hundred thousand rows (measured in
#: ``docs/deployment/SELF_HOSTED_DEMO.md``).
RAW_KEEP = timedelta(hours=1)
THIN_BUCKET = timedelta(minutes=10)
STATUS_EVERY = timedelta(seconds=60)
PRUNE_EVERY = timedelta(minutes=10)
BOOK_EVERY_SECONDS = 900.0
#: One advisory lock: two feeds never run against one demo database.
ADVISORY_LOCK = 0x45474E46  # "EGNF"

#: The feed's session. ``exchange`` (the default anywhere but the hosted demo): simulated
#: trading hours 07:00-19:00 CET/CEST every day. ``24h``: a demo-only session that never
#: closes, so a demo opened at any hour shows a moving screen; the hosted demo start-up sets
#: it. Neither is a real venue's timetable: ICE Endex and EEX gas sessions differ.
SESSION_SETTING = "EUROGAS_NEXUS_DEMO_FEED_SESSION"
SESSION_LABELS = {
    "exchange": "simulated trading hours 07:00-19:00 CET/CEST",
    "24h": "simulated 24-hour demo session (demo only; real ICE Endex and EEX sessions differ)",
}

#: What the live screen quotes for every demo hub the tick intake accepts: the prompt and the
#: front month, quarter and season, each on its own clock (:data:`CADENCE_SECONDS`); the rest
#: of the curve moves with the front in whole-curve moves (:data:`CURVE_MOVE_SECONDS`).
PROMPT_PRODUCTS = ("WD", "DA", "WE")
FRONT_CURVE = ("M+1", "Q+1", "S+1")
BACK_CURVE = (*(f"M+{n}" for n in range(2, 13)), "Q+2", "Q+3", "Q+4", "S+2", "Cal+1", "Cal+2")
CURVE_PRODUCTS = (*FRONT_CURVE, *BACK_CURVE)
FAST_PRODUCTS = (*PROMPT_PRODUCTS, *FRONT_CURVE)
#: Seconds between two quotes of one instrument: drawn uniformly, per instrument and quote.
CADENCE_SECONDS = (1.0, 5.0)
#: Seconds between two moves of a hub's curve level (the whole curve requotes then).
CURVE_MOVE_SECONDS = (20.0, 60.0)
#: The live factors, in EUR/MWh (NBP converted at the demo fixing): a common prompt factor
#: (TTF's), a curve factor that follows it in part, and a small bounded part of each hub's own,
#: so locational spreads stay inside the demo market's arbitrage band (its margin is 0.25).
LIVE_SIGMA_EUR = 0.0025
CURVE_KAPPA = 1 / 1800
CURVE_FOLLOWS = 0.6
OWN_SIGMA_EUR = 0.0008
OWN_KAPPA = 1 / 300
OWN_BOUND_EUR = 0.08
#: Hubs whose WD carries its own mean-reverting premium over DA (and the planted cases).
PREMIUM_HUBS = ("TTF", "NBP")
#: Chance that a quote comes with a print, by where it trades most.
PRINT_CHANCE = {"core_prompt": 0.12, "prompt": 0.02, "curve": 0.01}
QUOTE_JITTER = 0.3
#: The feed writes at most this often (one tick-intake call per batch, as an adapter batches).
BATCH_SECONDS = 0.5
#: Behind by more than this (a paused machine): reschedule instead of replaying the gap.
MAX_CATCH_UP = timedelta(seconds=30)


def feed_enabled(environ=os.environ) -> bool:
    """The demo exchange feed runs unless ``EUROGAS_NEXUS_DEMO_EXCHANGE_FEED`` is off.

    The demo roll-forward writes today's prompt quotes itself only when this is false.
    """

    return (environ.get("EUROGAS_NEXUS_DEMO_EXCHANGE_FEED") or "on").strip().lower() not in {
        "off", "false", "0", "no"}


def feed_session(environ=os.environ) -> str:
    """``24h`` when ``EUROGAS_NEXUS_DEMO_FEED_SESSION`` asks for it, else ``exchange``."""

    value = (environ.get(SESSION_SETTING) or "exchange").strip().lower()
    return "24h" if value in {"24h", "24", "24-hour", "always", "continuous"} else "exchange"


def in_session(at: datetime, session: str) -> bool:
    return session == "24h" or in_trading_hours(at)


@dataclass(frozen=True)
class Anchor:
    """Where an instrument is quoted around: the demo board's mid, tick and half-width (native)."""

    mid: float
    tick: float
    half: float


def _seed_module():
    import importlib.util
    from pathlib import Path

    if "seed_demo_desk" in sys.modules:
        return sys.modules["seed_demo_desk"]
    path = Path(__file__).with_name("seed_demo_desk.py")
    spec = importlib.util.spec_from_file_location("seed_demo_desk", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["seed_demo_desk"] = module
    spec.loader.exec_module(module)
    return module


def feed_hubs() -> frozenset[str]:
    from eurogas_nexus.ingestion.licensed_quote_import import SUPPORTED_HUBS

    return frozenset(SUPPORTED_HUBS)


def anchors_from_quotes(rows) -> dict[tuple[str, str], Anchor]:
    """Anchors from demo board quotes (dicts or stored rows), newest first; first one wins."""

    hubs = feed_hubs()
    wanted = {*PROMPT_PRODUCTS, *CURVE_PRODUCTS}
    out: dict[tuple[str, str], Anchor] = {}
    for row in rows:
        get = row.get if isinstance(row, dict) else (lambda name, r=row: getattr(r, name))
        meta = get("metadata_json") or {}
        hub, code = str(get("hub") or "").upper(), meta.get("rolling_code")
        mid, tick = meta.get("native_mid"), meta.get("tick")
        if hub not in hubs or code not in wanted or (hub, code) in out or not mid or not tick:
            continue
        bid, ask = meta.get("native_bid"), meta.get("native_ask")
        half = (float(ask) - float(bid)) / 2 if bid is not None and ask is not None else 0.0
        out[(hub, code)] = Anchor(float(mid), float(tick), max(float(tick), half))
    return out


def _db_anchors(session) -> dict[tuple[str, str], Anchor]:
    """The newest stored demo board quote per hub and product (when the board cannot be priced)."""

    from eurogas_nexus.db.models import MarketQuoteRecord

    rows = (session.query(MarketQuoteRecord)
            .filter(MarketQuoteRecord.source_system == FEED_SOURCE,
                    MarketQuoteRecord.source_reference == "demo:market")
            .order_by(MarketQuoteRecord.observed_at_utc.desc()).limit(4000).all())
    return anchors_from_quotes(rows)


def load_anchors(session, now: datetime) -> dict[tuple[str, str], Anchor]:
    """The demo board of the gas day at ``now`` (``seed_demo_desk.demo_board_now``), else the
    newest stored board quotes, else the TTF and NBP prompt fallbacks."""

    try:
        anchors = anchors_from_quotes(_seed_module().demo_board_now(session, now))
    except Exception as exc:  # noqa: BLE001 - the stored board is the fallback
        session.rollback()
        print(json.dumps({"feed": "demo board not priced", "error": type(exc).__name__}),
              flush=True)
        anchors = {}
    if not anchors:
        anchors = _db_anchors(session)
    if not anchors:
        anchors = {key: Anchor(FALLBACK[key], tick, half)
                   for key, (tick, half) in INSTRUMENTS.items()}
    return anchors


def _to_native(hub: str, eur_mwh: float) -> float:
    return _eur_to_pth(eur_mwh) if hub == "NBP" else eur_mwh


class LiveScreen:
    """The demo exchange screen of one gas day: every instrument on its own clock.

    * **Cadence.** Each prompt (WD, DA, WE) and front-curve (M+1, Q+1, S+1) instrument of
      every hub requotes after a fresh uniform draw from :data:`CADENCE_SECONDS`; a quote
      sometimes comes with a print (:data:`PRINT_CHANCE`).
    * **Path.** A common prompt factor (an Ornstein-Uhlenbeck walk around zero, TTF's
      volatility) moves every hub's prompt; a curve factor follows it in part and reverts
      more slowly; each hub adds a small part of its own, bounded by :data:`OWN_BOUND_EUR`,
      so a locational spread stays inside the demo market's arbitrage band. TTF and NBP WD
      carry their own premium over DA with rare dislocations, and the planted P1/P2 cases
      are laid on the path on their schedule.
    * **Curve.** A hub's curve moves as one level, at moves drawn from
      :data:`CURVE_MOVE_SECONDS`: every curve product (months, quarters, seasons, years) is
      requoted at that level then, and the front products requote at the same level until
      the next move. A strip is therefore always its months' average plus the demo market's
      own tick rounding: no arbitrage within a hub.
    * **Anchor.** Every mid starts on the demo board (``demo_market``) and reverts to it.

    Deterministic for a given ``rng`` and sequence of :meth:`step` times.
    """

    def __init__(self, anchors: dict[tuple[str, str], Anchor], rng: random.Random,
                 start: datetime, *, dislocations_per_hour: float = 6.0,
                 planted: bool = True) -> None:
        self.rng = rng
        self.t = start
        self.planted = planted
        self.dislocations = dislocations_per_hour
        self.books: dict[tuple[str, str], Book] = {}
        for (hub, code), anchor in sorted(anchors.items()):
            digits = 3 if anchor.tick < 0.01 else 2
            self.books[(hub, code)] = Book(hub, code, anchor.mid, anchor.mid, anchor.tick,
                                           anchor.half, prior_settlement=round(anchor.mid, digits))
        self.hubs = sorted({hub for hub, _code in self.books})
        self.prompt_common = 0.0
        self.curve_common = 0.0
        self.prompt_own = dict.fromkeys(self.hubs, 0.0)
        self.curve_own = dict.fromkeys(self.hubs, 0.0)
        self.level = dict.fromkeys(self.hubs, 0.0)
        self.premium = {hub: 0.0 for hub in PREMIUM_HUBS
                        if (hub, "WD") in self.books and (hub, "DA") in self.books}
        self.shock = dict.fromkeys(self.premium, 0.0)
        self.sequence = 0
        self.due = {key: start + timedelta(seconds=rng.uniform(0.0, CADENCE_SECONDS[1]))
                    for key in self.books if key[1] in FAST_PRODUCTS}
        self.curve_due = {hub: start + timedelta(seconds=rng.uniform(*CURVE_MOVE_SECONDS))
                          for hub in self.hubs
                          if any(code in CURVE_PRODUCTS for h, code in self.books if h == hub)}

    # -------------------------------------------------------------- path
    def advance(self, to: datetime) -> None:
        dt = (to - self.t).total_seconds()
        if dt <= 0:
            return
        self.t = to
        rng, root = self.rng, math.sqrt(dt)
        draw = rng.gauss(0.0, LIVE_SIGMA_EUR * root)
        self.prompt_common = self.prompt_common * math.exp(-KAPPA * dt) + draw
        self.curve_common = (self.curve_common * math.exp(-CURVE_KAPPA * dt) + CURVE_FOLLOWS * draw
                             + rng.gauss(0.0, (1 - CURVE_FOLLOWS) * LIVE_SIGMA_EUR * root))
        for hub in self.hubs:
            if hub == "TTF":
                continue  # the common factor is TTF's own
            for own in (self.prompt_own, self.curve_own):
                value = own[hub] * math.exp(-OWN_KAPPA * dt) + rng.gauss(0.0, OWN_SIGMA_EUR * root)
                own[hub] = max(-OWN_BOUND_EUR, min(OWN_BOUND_EUR, value))
        for hub in self.premium:
            # NBP in pence per therm: about three times the EUR/MWh figure.
            scale = 3.0 if hub == "NBP" else 1.0
            if rng.random() < self.dislocations / 3600 * dt:
                self.shock[hub] += rng.choice((-1, 1)) * rng.uniform(0.12, 0.2) * scale
            self.shock[hub] *= math.exp(-dt / 180)
            self.premium[hub] = (self.premium[hub] * math.exp(-WD_PREMIUM_KAPPA * dt)
                                 + rng.gauss(0.0, WD_PREMIUM_SIGMA * scale * root))

    def mid(self, key: tuple[str, str]) -> float:
        """The instrument's mid now (native unit), before the touch is put on the tick."""

        hub, code = key
        anchor = self.books[key].anchor
        if code not in PROMPT_PRODUCTS:
            return anchor + _to_native(hub, self.level[hub])
        if code == "WD" and hub in self.premium:
            day_ahead = self.books[(hub, "DA")].anchor
            mid = self.mid((hub, "DA")) + (anchor - day_ahead) + self.premium[hub] + self.shock[hub]
            if self.planted and hub == "TTF":
                mid += planted_p1(self.t)
            return mid
        mid = anchor + _to_native(hub, self.prompt_common + self.prompt_own[hub])
        if self.planted and key == ("NBP", "DA") and ("TTF", "DA") in self.books:
            ttf = self.mid(("TTF", "DA"))
            eur = _pth_to_eur(mid)
            if planted_p2(self.t):
                eur = ttf + BBL_ROUTE_COST + P2_EXCESS
            else:
                eur = min(eur, ttf + BBL_ROUTE_COST - P2_OUTSIDE_MARGIN)
            mid = _eur_to_pth(eur)
        return mid

    # -------------------------------------------------------------- ticks
    def _print_chance(self, key: tuple[str, str]) -> float:
        hub, code = key
        if code in PROMPT_PRODUCTS:
            return PRINT_CHANCE["core_prompt" if hub in PREMIUM_HUBS and code != "WE"
                                else "prompt"]
        return PRINT_CHANCE["curve"]

    def _tick(self, key: tuple[str, str], at: datetime, quotes: list, trades: list,
              printable: bool = True) -> None:
        book = self.books[key]
        book.mid = self.mid(key)
        self.sequence += 1
        if printable and self.rng.random() < self._print_chance(key):
            printed = book.trade(self.rng, at, self.sequence)
            if printed:
                trades.append(printed)
        quotes.append(book.quote(self.rng, at, self.sequence, jitter=QUOTE_JITTER))

    def next_due(self) -> datetime:
        return min([*self.due.values(), *self.curve_due.values()])

    def step(self, now: datetime) -> tuple[list[dict], list[dict]]:
        """Every quote and print due up to ``now``, in time order, each at its own time."""

        quotes: list[dict] = []
        trades: list[dict] = []
        if now - self.t > MAX_CATCH_UP:
            # Far behind (a paused machine): start the clocks again from now.
            self.advance(now)
            for key in self.due:
                self.due[key] = now + timedelta(seconds=self.rng.uniform(0.0, CADENCE_SECONDS[1]))
            for hub in self.curve_due:
                self.curve_due[hub] = now + timedelta(seconds=self.rng.uniform(*CURVE_MOVE_SECONDS))
        while True:
            key, due = min(self.due.items(), key=lambda item: (item[1], item[0]),
                           default=(None, None))
            hub, move = min(self.curve_due.items(), key=lambda item: (item[1], item[0]),
                            default=(None, None))
            if move is not None and (due is None or move < due):
                if move > now:
                    break
                self.advance(move)
                self.level[hub] = self.curve_common + self.curve_own[hub]
                for code in CURVE_PRODUCTS:
                    if (hub, code) in self.books:
                        self._tick((hub, code), move, quotes, trades, printable=code in FRONT_CURVE)
                        if code in FRONT_CURVE:
                            self.due[(hub, code)] = move + timedelta(
                                seconds=self.rng.uniform(*CADENCE_SECONDS))
                self.curve_due[hub] = move + timedelta(
                    seconds=self.rng.uniform(*CURVE_MOVE_SECONDS))
                continue
            if due is None or due > now:
                break
            self.advance(due)
            self._tick(key, due, quotes, trades)
            self.due[key] = due + timedelta(seconds=self.rng.uniform(*CADENCE_SECONDS))
        return quotes, trades


def _status(session, at: datetime, since: datetime, counts: dict, note: str) -> None:
    from eurogas_nexus.db.models import IngestionRunRecord

    seconds = max(1.0, (at - since).total_seconds())
    rows = counts["quotes"] + counts["trades"]
    session.merge(IngestionRunRecord(
        run_id=f"demo-feed-{at:%Y%m%d%H%M}", source_name=FEED_SOURCE, source_id=FEED_SOURCE_ID,
        dataset="prompt-quotes", trigger_type="SCHEDULED", status="succeeded",
        started_at_utc=since, finished_at_utc=at, completed_at_utc=at,
        window_start_utc=since, window_end_utc=at, rows_received=rows, rows_accepted=rows,
        rows_inserted=rows,
        notes=(f"Demo exchange feed (simulated): {rows / seconds:.2f} messages/s; last message "
               f"{counts['last'] or '-'}; quotes {counts['quotes']}, trades {counts['trades']}; "
               f"{note}")[:2000],
    ))


def _prune(session, now: datetime) -> dict:
    from eurogas_nexus.db.models import (
        GasDayNominationEventRecord,
        IngestionRunRecord,
        MarketQuoteRecord,
        MarketTradeRecord,
        ScreenOrderObservationRecord,
    )

    cutoff = now - RETENTION
    return {
        "quotes": session.query(MarketQuoteRecord).filter(
            MarketQuoteRecord.source_system == FEED_SOURCE,
            MarketQuoteRecord.source_reference == FEED_REFERENCE,
            MarketQuoteRecord.observed_at_utc < cutoff).delete(synchronize_session=False),
        "trades": session.query(MarketTradeRecord).filter(
            MarketTradeRecord.source_system == FEED_SOURCE,
            MarketTradeRecord.traded_at_utc < cutoff).delete(synchronize_session=False),
        "runs": session.query(IngestionRunRecord).filter(
            IngestionRunRecord.source_id == FEED_SOURCE_ID,
            IngestionRunRecord.started_at_utc < cutoff).delete(synchronize_session=False),
        "booked": session.query(ScreenOrderObservationRecord).filter(
            ScreenOrderObservationRecord.source_system == "ETRM_Sim",
            ScreenOrderObservationRecord.observed_at_utc < cutoff,
        ).delete(synchronize_session=False),
        "nominated": session.query(GasDayNominationEventRecord).filter(
            GasDayNominationEventRecord.source_system == "ETRM_Sim",
            GasDayNominationEventRecord.recorded_at_utc < cutoff,
        ).delete(synchronize_session=False),
    }


def _bucket(at: datetime) -> datetime:
    at = at.replace(tzinfo=UTC) if at.tzinfo is None else at.astimezone(UTC)
    size = int(THIN_BUCKET.total_seconds())
    return datetime.fromtimestamp(int(at.timestamp()) // size * size, UTC)


def _thin(session, now: datetime, since: datetime | None) -> tuple[int, datetime]:
    """Thin the feed's quotes older than :data:`RAW_KEEP` to the last of each instrument and
    delivery in each :data:`THIN_BUCKET`; returns (rows removed, where the next pass starts).

    Whole buckets only, each once: ``since`` is where the previous pass stopped (``None``:
    the retention window's start).
    """

    from eurogas_nexus.db.models import MarketQuoteRecord as Q

    start = _bucket(since or now - RETENTION)
    until = _bucket(now - RAW_KEEP)
    if until <= start:
        return 0, start
    naive = session.get_bind().dialect.name == "sqlite"

    def bound(value: datetime) -> datetime:
        return value.replace(tzinfo=None) if naive else value

    rows = (session.query(Q.quote_id, Q.instrument_id, Q.delivery_start_utc, Q.observed_at_utc)
            .filter(Q.source_system == FEED_SOURCE, Q.source_reference == FEED_REFERENCE,
                    Q.observed_at_utc >= bound(start), Q.observed_at_utc < bound(until))
            .order_by(Q.observed_at_utc, Q.quote_id).all())
    last: dict[tuple, str] = {}
    for quote_id, instrument, delivery, observed in rows:
        last[(instrument, delivery, _bucket(observed))] = quote_id
    keep = set(last.values())
    drop = [quote_id for quote_id, *_rest in rows if quote_id not in keep]
    for offset in range(0, len(drop), 500):
        session.query(Q).filter(Q.quote_id.in_(drop[offset:offset + 500])).delete(
            synchronize_session=False)
    return len(drop), until


def run_continuous(dislocations: float, *, clock=lambda: datetime.now(UTC),
                   sleeper=time.sleep, stop_after: float | None = None,
                   session_mode: str | None = None) -> int:
    """The demo server's feed: a live screen through the tick ingestion, in its session.

    Writes as ``DEMO_Sim`` through ``application.market_ticks.ingest_ticks`` (the path a
    licensed connector's batches take: validation, entitlement family, the inputs-changed
    hook), one batch at most every :data:`BATCH_SECONDS`, a status run a minute for Admin →
    Data feeds; thins its quotes after :data:`RAW_KEEP` and prunes its own rows after
    :data:`RETENTION`. ``session_mode`` (``exchange`` or ``24h``; default from
    :data:`SESSION_SETTING`) decides when it quotes. One advisory lock keeps it single.
    Returns when ``stop_after`` seconds have passed (tests), else never.
    """

    from sqlalchemy import text

    from eurogas_nexus.application.market_ticks import ingest_ticks
    from eurogas_nexus.db.session import get_session_factory
    from eurogas_nexus.domain.market.feed import FeedError
    from eurogas_nexus.domain.market.gas_day import gas_day_label

    mode = session_mode or feed_session()
    label = SESSION_LABELS[mode]
    factory = get_session_factory()
    with factory() as probe:
        engine = probe.get_bind()
    lock_connection = None
    if engine.dialect.name == "postgresql":
        # A session-level lock on a connection of its own, in autocommit: no open transaction.
        lock_connection = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        held = lock_connection.execute(text("select pg_try_advisory_lock(:k)"),
                                       {"k": ADVISORY_LOCK})
        if not held.scalar():
            lock_connection.close()
            print(json.dumps({"feed": "another demo exchange feed holds the lock; exiting"}))
            return 0
    started = clock()
    print(json.dumps({"feed": "started", "session": mode, "label": label, "simulated": True}),
          flush=True)
    rng = random.Random(f"{STREAM}:live:{started:%Y%m%d%H%M%S}")
    booker = TradeBooker(BOOK_EVERY_SECONDS, random.Random(f"{STREAM}:book:live"))
    screen: LiveScreen | None = None
    gas_day = None
    counts = {"quotes": 0, "trades": 0, "last": None}
    status_since = last_prune = started
    thinned_until: datetime | None = None
    while True:
        now = clock()
        if stop_after is not None and (now - started).total_seconds() >= stop_after:
            return 0
        if now - last_prune >= PRUNE_EVERY:
            with factory() as session:
                removed = _prune(session, now)
                removed["thinned"], thinned_until = _thin(session, now, thinned_until)
                session.commit()
            print(json.dumps({"feed": "pruned", **removed}), flush=True)
            last_prune = now
        if not in_session(now, mode):
            if now - status_since >= STATUS_EVERY * 5:
                with factory() as session:
                    _status(session, now, status_since, counts, f"paused outside {label}")
                    session.commit()
                status_since, counts = now, {"quotes": 0, "trades": 0, "last": counts["last"]}
            screen = None
            sleeper(30)
            continue
        day = gas_day_label(now)
        if screen is None or day != gas_day:
            with factory() as session:
                anchors = load_anchors(session, now)
            screen = LiveScreen(anchors, rng, now, dislocations_per_hour=dislocations,
                                planted=True)
            gas_day = day
            print(json.dumps({"feed": "session", "gas_day": day, "hubs": screen.hubs,
                              "instruments": len(screen.books)}), flush=True)
        quotes, trades = screen.step(now)
        if quotes or trades:
            with factory() as session:
                try:
                    ingest_ticks(session, source_system=FEED_SOURCE, quotes=quotes,
                                 trades=trades, simulated_allowed=True)
                    session.commit()
                except FeedError as exc:  # one refused batch never stops the screen
                    session.rollback()
                    print(json.dumps({"feed": "batch refused", "error": str(exc)[:300]}),
                          flush=True)
                    quotes, trades = [], []
            counts["quotes"] += len(quotes)
            counts["trades"] += len(trades)
            if quotes:
                counts["last"] = quotes[-1]["exchange_time"][:19]
        booker.maybe_book(now, screen.books)
        if clock() - status_since >= STATUS_EVERY:
            with factory() as session:
                _status(session, clock(), status_since, counts,
                        f"running; {label}; {len(screen.books)} instruments across "
                        f"{len(screen.hubs)} hubs; planted P1/P2 on schedule")
                session.commit()
            status_since, counts = clock(), {"quotes": 0, "trades": 0, "last": counts["last"]}
        sleeper(max(BATCH_SECONDS, (screen.next_due() - clock()).total_seconds()))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", default=os.environ.get("API", "http://127.0.0.1:8080"))
    parser.add_argument("--user", default="demo.ops")
    parser.add_argument("--minutes", type=float, default=10.0)
    parser.add_argument("--replay", action="store_true",
                        help="compressed session: exchange time runs ahead of the wall clock")
    parser.add_argument("--batch-ms", type=float, default=250.0,
                        help="adapter batching window in real time")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="real-time only: session seconds per wall second")
    parser.add_argument("--seed", default="1")
    parser.add_argument("--dislocations", type=float, default=6.0)
    parser.add_argument("--start", default=None, help="replay start (ISO 8601, UTC)")
    parser.add_argument("--report", default=None, help="write the per-batch timings here")
    parser.add_argument("--book-every", type=float, default=0.0,
                        help="book a simulated prompt trade every N session seconds (demo "
                             "database access needed); 0: none")
    parser.add_argument("--continuous", action="store_true",
                        help="the demo server's feed: a live screen of every demo hub straight "
                             "through the tick ingestion into the demo database, in its "
                             "session, forever")
    parser.add_argument("--session", choices=sorted(SESSION_LABELS), default=None,
                        help="continuous only: 'exchange' (07:00-19:00 CET/CEST, the default) "
                             "or '24h' (demo only; real ICE Endex and EEX sessions differ); "
                             f"default from {SESSION_SETTING}")
    args = parser.parse_args(argv)
    if args.continuous:
        if not feed_enabled():
            print(json.dumps({"feed": "disabled by EUROGAS_NEXUS_DEMO_EXCHANGE_FEED"}))
            return 0
        return run_continuous(args.dislocations, session_mode=args.session)
    password = os.environ.get("EUROGAS_NEXUS_DEV_LOGIN_PASSWORD") or ""
    if not password:
        print("EUROGAS_NEXUS_DEV_LOGIN_PASSWORD is not set", file=sys.stderr)
        return 2
    token = login(args.api, args.user, password)
    rng = random.Random(f"{STREAM}:{args.seed}")
    held = anchors(args.api, token)
    books = {}
    for (hub, product), (tick, half) in INSTRUMENTS.items():
        anchor = held.get((hub, product), FALLBACK[(hub, product)])
        books[(hub, product)] = Book(hub, product, anchor, anchor, tick, half,
                                     prior_settlement=round(anchor, 3))
    start = (datetime.fromisoformat(args.start) if args.start
             else datetime.now(UTC) - (timedelta(minutes=args.minutes) if args.replay
                                       else timedelta(0)))
    wall0 = time.monotonic()
    pending_quotes, pending_trades = [], []
    flushed_at = time.monotonic()
    timings = []
    total_quotes = total_trades = evaluated = 0

    def flush() -> None:
        nonlocal pending_quotes, pending_trades, total_quotes, total_trades, evaluated
        if not pending_quotes and not pending_trades:
            return
        sent = time.perf_counter()
        result = call(args.api, token, "POST", "/api/market/ticks", {
            "source_system": SOURCE, "quotes": pending_quotes, "trades": pending_trades,
            "replay": args.replay})
        elapsed = time.perf_counter() - sent
        if "http_error" in result:
            print(json.dumps(result), file=sys.stderr)
        data = result.get("data") or {}
        evaluation = data.get("evaluation") or {}
        timings.append({"ticks": len(pending_quotes) + len(pending_trades),
                        "seconds": round(elapsed, 4), "evaluated": evaluation.get("evaluated"),
                        "latency_ms": [r.get("latency_ms") for r in evaluation.get("results", [])],
                        "evaluation_ms": [r.get("evaluation_ms")
                                          for r in evaluation.get("results", [])]})
        total_quotes += len(pending_quotes)
        total_trades += len(pending_trades)
        evaluated += int(evaluation.get("evaluated") or 0)
        pending_quotes, pending_trades = [], []

    booker = TradeBooker(args.book_every, random.Random(f"{STREAM}:book:{args.seed}")) \
        if args.book_every > 0 else None
    for at, quotes, trades in session_events(rng, books, start, args.minutes, args.dislocations):
        if booker is not None:
            booker.maybe_book(at, books)
        if not args.replay:
            due = (at - start).total_seconds() / max(args.speed, 1e-6)
            wait = due - (time.monotonic() - wall0)
            if wait > 0:
                time.sleep(wait)
        pending_quotes += quotes
        pending_trades += trades
        if args.replay:
            if len(pending_quotes) >= 1:
                flush()  # one exchange event per call, so each tick is evaluated at its time
        elif (time.monotonic() - flushed_at) * 1000 >= args.batch_ms:
            flush()
            flushed_at = time.monotonic()
    flush()
    wall = time.monotonic() - wall0
    summary = {"quotes": total_quotes, "trades": total_trades, "evaluations": evaluated,
               "wall_seconds": round(wall, 2), "batches": len(timings),
               "ticks_per_second": round((total_quotes + total_trades) / wall, 1) if wall else None,
               "source": SOURCE, "simulated": True,
               "booked_trades": booker.booked if booker else 0}
    print(json.dumps(summary))
    if args.report:
        with open(args.report, "w", encoding="utf-8") as handle:
            json.dump({"summary": summary, "batches": timings}, handle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
