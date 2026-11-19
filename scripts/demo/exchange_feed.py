#!/usr/bin/env python
"""Demo exchange feed: bursty two-sided quotes and trade prints for TTF and NBP WD/DA.

Demo profile only. Every tick is invented, stored under ``EEX_Sim`` (the EEX family, simulated)
and labelled simulated; it is never a market price (AGENTS.md rule 17). It exists so the
intraday path (tick ingestion, strategy evaluation on arrival, the paper book) can be seen and
measured without a licensed feed.

How the session is made (one ``random.Random`` stream of its own, ``demo-exchange-feed-v1``):

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

    def quote(self, rng: random.Random, at: datetime, sequence: int) -> dict:
        half = self.half * (1.0 + 0.6 * rng.random())
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


def session_events(rng: random.Random, books: dict, start: datetime, minutes: float,
                   dislocations_per_hour: float):
    """Yield (time, quotes, trades) events for ``minutes`` of session time."""

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
        book = books[(hub, product)]
        if not hasattr(book, "bid"):
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
                venue="Demo", account_label="Demo counterparty", external_order_id=trade_id,
                side="BUY" if buy else "SELL", order_type="TRADE", hub=hub, product="ETRM",
                contract_code=trade_id, delivery_start_utc=period.delivery_start_utc,
                delivery_end_utc=period.delivery_end_utc, price=round(price, 6),
                currency=currency, unit=unit, quantity_mwh=round(mwh, 3),
                filled_quantity_mwh=round(mwh, 3), remaining_quantity_mwh=0.0, status="FILLED",
                observed_at_utc=at, source_system="ETRM_Sim",
                source_reference="demo:prompt-trades", linked_strategy_id=None,
                linked_resource_id=None, research_only=True, human_review_required=True,
                book_id=self.BOOKS[hub]))
            session.commit()


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
    args = parser.parse_args(argv)
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
