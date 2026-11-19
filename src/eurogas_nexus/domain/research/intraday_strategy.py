"""Intraday strategy evaluation on arriving quotes, and the paper book a shadow run keeps.

A tracked strategy names its legs (hub and product, a weight each: ``TTF WD +1, TTF DA −1``)
and an intraday rule. Each time one of its instruments ticks, the application calls
:func:`evaluate` with the latest top of book of every leg; this module is pure and returns the
new state, what happened (events) and the advice line. Nothing here can place an order: a fill
is a paper fill against the quote that was on the screen, recorded for review.

Rules (``IntradayRule.kind``):

- ``zscore_window``: mean reversion of the spread mid on a rolling ``window_minutes`` window.
  The mean and deviation come from the samples *before* the current one (causal), so a tick
  never scores against itself. Short the spread at ``z >= entry_z``, long at ``z <= -entry_z``,
  flat at ``|z| <= exit_z``.
- ``vwap_reversion``: the same, measured from the session VWAP of the legs (``Σ w × VWAP``):
  where business was done, not where it was offered. Needs a VWAP on every leg.
- ``breakout``: long when the mid clears the window's high by ``breakout_buffer``, short below
  its low; flat when it comes back to the window mean.

Liquidity gates (a gated tick changes no signal; an open position is still marked): both sides
quoted on every leg, the quoted size at least ``min_top_size_mwh``, the quote no older than
``max_quote_age_seconds``, and, when set, a screen trade on every leg within
``max_no_trade_minutes``.

Fill model (stated on every result): a paper order fills at once against the quote available
when the signal is computed: to buy the spread, legs with a positive weight are bought at the
offer and the others sold at the bid (selling: the reverse). The fill is limited by the quoted
size on that side, top of book only (no depth is walked: what does not fill is not filled), plus
``slippage_per_mwh`` against the trader on every leg. A signal whose edge, net of the spread
crossed on the way in and the half-spread to get out, is not positive is reported as
"no edge" and not filled.

P&L: per MWh of the spread and in the legs' currency for the filled size (MWh per gas day ×
``delivery_days`` of the product). An open position is marked at the price it could be closed
at (a long at the bid side of the spread, a short at the offer side), so the unrealised P&L
already pays the exit spread. A contract change on any leg (the DA rolls to the next gas day)
closes the position at the last price of the old contract.

日内策略：行情到达时评估、纸面账簿（模拟成交，不下单）。成交模型：按当时屏幕报价成交
（买价/卖价，受报价量限制，仅一档），持仓按可平仓价格盯市。
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from typing import Any

KINDS = ("zscore_window", "vwap_reversion", "breakout")
#: Gas days a position in one product delivers (size × days = energy).
DELIVERY_DAYS = {"within-day": 1, "day-ahead": 1, "weekend": 2}
MAX_SAMPLES = 4000
#: Equity marks kept in the state for the curve (the application stores more, throttled).
MAX_STATE_MARKS = 0


class IntradayRuleError(ValueError):
    """A rule that cannot run."""


@dataclass(frozen=True)
class IntradayRule:
    kind: str = "zscore_window"
    window_minutes: float = 30.0
    min_points: int = 20
    entry_z: float = 2.0
    exit_z: float = 0.5
    breakout_buffer: float = 0.0
    #: Paper size, MW (continental) — stored per gas day as ``size_mw × 24`` MWh.
    size_mw: float = 10.0
    min_top_size_mwh: float = 1.0
    max_quote_age_seconds: float = 120.0
    max_no_trade_minutes: float | None = None
    slippage_per_mwh: float = 0.0
    require_positive_edge: bool = True
    max_hold_minutes: float | None = None
    advice_ttl_seconds: float = 300.0
    debounce_seconds: float = 2.0

    def validate(self) -> None:
        if self.kind not in KINDS:
            raise IntradayRuleError(f"rule kind must be one of {KINDS}")
        if not 1 <= self.window_minutes <= 24 * 60:
            raise IntradayRuleError("window must be 1 minute to 24 hours")
        if not 5 <= self.min_points <= MAX_SAMPLES:
            raise IntradayRuleError(f"min_points must be 5..{MAX_SAMPLES}")
        if self.kind != "breakout" and not 0 <= self.exit_z < self.entry_z <= 10:
            raise IntradayRuleError("need 0 <= exit_z < entry_z <= 10")
        if not 0 < self.size_mw <= 5000:
            raise IntradayRuleError("size must be 0..5000 MW")
        for name in ("min_top_size_mwh", "max_quote_age_seconds", "slippage_per_mwh",
                     "advice_ttl_seconds", "debounce_seconds", "breakout_buffer"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise IntradayRuleError(f"{name} must be zero or positive")
        if self.debounce_seconds > 300:
            raise IntradayRuleError("debounce at most 300 seconds")

    @property
    def size_mwh_per_day(self) -> float:
        return self.size_mw * 24.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def rule_from_dict(data: dict[str, Any] | None) -> IntradayRule:
    data = dict(data or {})
    allowed = set(IntradayRule.__dataclass_fields__)
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise IntradayRuleError(f"unknown rule fields: {', '.join(unknown)}")
    try:
        rule = IntradayRule(**data)
    except TypeError as exc:  # pragma: no cover - guarded above
        raise IntradayRuleError(str(exc)) from exc
    rule.validate()
    return rule


@dataclass(frozen=True)
class Leg:
    hub: str
    product: str
    weight: float

    @property
    def key(self) -> str:
        return f"{self.hub}|{self.product}"


@dataclass(frozen=True)
class LegQuote:
    """The latest top of book of one leg, per MWh in the leg's currency."""

    bid: float | None
    ask: float | None
    bid_size_mwh: float | None
    ask_size_mwh: float | None
    observed_at: datetime
    delivery_start: str
    currency: str
    source_system: str = ""
    simulated: bool = False
    vwap: float | None = None
    volume_mwh: float | None = None
    last_trade_at: datetime | None = None

    @property
    def mid(self) -> float | None:
        if self.bid is None or self.ask is None:
            return None
        return (self.bid + self.ask) / 2


@dataclass
class Evaluation:
    state: dict[str, Any]
    events: list[dict[str, Any]] = field(default_factory=list)
    snapshot: dict[str, Any] = field(default_factory=dict)
    signal_changed: bool = False


def assumptions(rule: IntradayRule) -> str:
    """The one line every result carries."""

    depth = "top of book only"
    return (
        f"Paper only, nothing is sent. Fills at the quote on the screen when the signal is "
        f"computed (buy at the offer, sell at the bid), limited to the quoted size, {depth}; "
        f"slippage {rule.slippage_per_mwh:g}/MWh per leg; marked at the price it could be "
        f"closed at; size {rule.size_mw:g} MW = {rule.size_mwh_per_day:g} MWh per gas day "
        f"(a within-day position counted as a full gas day); a contract change closes the "
        f"position at the old contract's last price; signal window {rule.window_minutes:g} min, "
        f"mean and deviation from earlier ticks only."
    )


def _executable(legs: list[Leg], book: dict[str, LegQuote], side: int,
                slippage: float) -> tuple[float | None, float | None]:
    """(price per MWh, fillable MWh/d) to buy (side +1) or sell (side −1) one spread unit."""

    price = 0.0
    fillable = math.inf
    for leg in legs:
        quote = book[leg.key]
        buying = (leg.weight > 0) == (side > 0)
        level = quote.ask if buying else quote.bid
        size = quote.ask_size_mwh if buying else quote.bid_size_mwh
        if level is None:
            return None, None
        adverse = slippage if buying else -slippage
        price += leg.weight * (level + adverse)
        fillable = min(fillable, (size or 0.0) / abs(leg.weight))
    return price, (0.0 if fillable is math.inf else fillable)


def _gates(legs: list[Leg], book: dict[str, LegQuote], rule: IntradayRule,
           now: datetime) -> list[str]:
    reasons: list[str] = []
    for leg in legs:
        quote = book.get(leg.key)
        if quote is None:
            reasons.append(f"{leg.hub} {leg.product}: no quote")
            continue
        if quote.bid is None or quote.ask is None:
            reasons.append(f"{leg.hub} {leg.product}: one-sided")
            continue
        if quote.bid >= quote.ask:
            reasons.append(f"{leg.hub} {leg.product}: crossed or locked")
        if min(quote.bid_size_mwh or 0.0, quote.ask_size_mwh or 0.0) < rule.min_top_size_mwh:
            reasons.append(f"{leg.hub} {leg.product}: no size on the screen")
        age = (now - quote.observed_at).total_seconds()
        if age > rule.max_quote_age_seconds:
            reasons.append(f"{leg.hub} {leg.product}: quote {age:.0f}s old")
        if rule.max_no_trade_minutes is not None:
            last = quote.last_trade_at
            if last is None or (now - last).total_seconds() > rule.max_no_trade_minutes * 60:
                reasons.append(
                    f"{leg.hub} {leg.product}: no trade in {rule.max_no_trade_minutes:g} min"
                )
    return reasons


def _stats(values: list[float]) -> tuple[float, float]:
    mean = sum(values) / len(values)
    var = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return mean, math.sqrt(var)


def new_state() -> dict[str, Any]:
    return {
        "samples": [],
        "signal": "flat",
        "signal_at": None,
        "position": 0,
        "qty_mwh_per_day": 0.0,
        "entry_price": None,
        "entry_at": None,
        "entry_deliveries": {},
        "realised": 0.0,
        "realised_per_mwh": 0.0,
        "closed_trades": 0,
        "winning_trades": 0,
        "worst_trade": None,
        "peak_equity": 0.0,
        "max_drawdown": 0.0,
        "last_liquidation": None,
        "evaluations": 0,
        "gated": [],
    }


def _energy(legs: list[Leg], qty: float) -> float:
    days = max(DELIVERY_DAYS.get(leg.product, 1) for leg in legs)
    return qty * days


def evaluate(
    legs: list[Leg],
    rule: IntradayRule,
    book: dict[str, LegQuote],
    state: dict[str, Any] | None,
    now: datetime,
) -> Evaluation:
    """One evaluation on the latest quotes: signal, paper fills, marks. Pure."""

    state = dict(state or new_state())
    state["evaluations"] = int(state.get("evaluations", 0)) + 1
    events: list[dict[str, Any]] = []
    stamp = now.isoformat()
    window_start = now - timedelta(minutes=rule.window_minutes)
    samples = [
        sample for sample in state.get("samples", [])
        if datetime.fromisoformat(sample[0]) >= window_start
    ][-MAX_SAMPLES:]

    gates = _gates(legs, book, rule, now)
    complete = all(leg.key in book and book[leg.key].mid is not None for leg in legs)
    mid = (
        sum(leg.weight * float(book[leg.key].mid) for leg in legs)  # type: ignore[arg-type]
        if complete else None
    )
    buy_px, buy_qty = (
        _executable(legs, book, +1, rule.slippage_per_mwh) if complete else (None, None)
    )
    sell_px, sell_qty = (
        _executable(legs, book, -1, rule.slippage_per_mwh) if complete else (None, None)
    )
    simulated = any(book[leg.key].simulated for leg in legs if leg.key in book)
    deliveries = {leg.key: book[leg.key].delivery_start for leg in legs if leg.key in book}

    # A contract change on any leg closes the position at the old contract's last price.
    position = int(state.get("position", 0))
    if position and state.get("entry_deliveries") and any(
        state["entry_deliveries"].get(key) != value for key, value in deliveries.items()
    ):
        last = state.get("last_liquidation")
        if last is not None:
            events.append(_close(state, legs, float(last), stamp, "contract change"))
        position = 0

    z = mean = sd = anchor = None
    desired = state.get("signal", "flat")
    reason = ""
    if mid is not None and not gates:
        history = [float(sample[1]) for sample in samples]
        if len(history) >= rule.min_points:
            mean, sd = _stats(history)
            if rule.kind == "vwap_reversion":
                vwaps = [book[leg.key].vwap for leg in legs]
                if all(value is not None for value in vwaps):
                    anchor = sum(leg.weight * float(v) for leg, v in zip(legs, vwaps, strict=True))
                else:
                    gates.append("no session VWAP on every leg")
            if not gates:
                centre = anchor if anchor is not None else mean
                if rule.kind in ("zscore_window", "vwap_reversion"):
                    z = None if sd == 0 else (mid - centre) / sd
                    if z is not None:
                        if position == 0 and z >= rule.entry_z:
                            desired, reason = "short", f"z {z:+.2f} ≥ {rule.entry_z:g}"
                        elif position == 0 and z <= -rule.entry_z:
                            desired, reason = "long", f"z {z:+.2f} ≤ −{rule.entry_z:g}"
                        elif position != 0 and abs(z) <= rule.exit_z:
                            desired, reason = "flat", f"|z| {abs(z):.2f} ≤ {rule.exit_z:g}"
                        elif position == 0:
                            desired = "flat"
                else:
                    high, low = max(history), min(history)
                    if position == 0 and mid > high + rule.breakout_buffer:
                        desired, reason = "long", f"above the {rule.window_minutes:g}-min high"
                    elif position == 0 and mid < low - rule.breakout_buffer:
                        desired, reason = "short", f"below the {rule.window_minutes:g}-min low"
                    elif position > 0 and mid <= mean or position < 0 and mid >= mean:
                        desired, reason = "flat", "back to the window mean"
                    elif position == 0:
                        desired = "flat"
        else:
            reason = f"warming up: {len(history)}/{rule.min_points} ticks in the window"
    if position and rule.max_hold_minutes and state.get("entry_at"):
        held = (now - datetime.fromisoformat(state["entry_at"])).total_seconds() / 60
        if held >= rule.max_hold_minutes and not gates:
            desired, reason = "flat", f"held {held:.0f} min (time stop)"

    # Edge net of the spread crossed: distance to the mean, less the entry crossing and the
    # half-spread to get out again (per MWh of the spread).
    edge = None
    if mid is not None and buy_px is not None and sell_px is not None and mean is not None:
        half_out = (buy_px - sell_px) / 2
        centre = anchor if anchor is not None else mean
        if desired == "long":
            edge = (centre - mid) - (buy_px - mid) - half_out
        elif desired == "short":
            edge = (mid - centre) - (mid - sell_px) - half_out
    if desired in ("long", "short") and position == 0 and rule.require_positive_edge and (
        edge is None or edge <= 0
    ) and rule.kind != "breakout":
        reason = f"{reason}; no edge after crossing the spread ({edge:+.3f}/MWh)" if edge \
            is not None else reason
        desired = "no_edge"

    previous = state.get("signal", "flat")
    changed = desired != previous and not gates
    if gates:
        if gates != state.get("gated"):
            events.append({"kind": "gated", "at": stamp, "reasons": gates})
        state["gated"] = gates
    else:
        state["gated"] = []

    if changed:
        state["signal"] = desired
        state["signal_at"] = stamp
        events.append({
            "kind": "signal", "at": stamp, "signal": desired, "reason": reason,
            "mid": _r(mid), "mean": _r(mean), "sd": _r(sd), "z": _r(z, 4),
            "vwap_anchor": _r(anchor), "spread_bid": _r(sell_px), "spread_offer": _r(buy_px),
            "edge_net_per_mwh": _r(edge),
            "quote_age_seconds": _ages(legs, book, now),
            "expires_at": (now + timedelta(seconds=rule.advice_ttl_seconds)).isoformat(),
            "simulated": simulated,
        })
        # Paper order intent, then its paper fill (or the reason it did not fill).
        if desired == "flat" and position != 0:
            side = -position
            price = sell_px if position > 0 else buy_px
            qty = sell_qty if position > 0 else buy_qty
            wanted = float(state["qty_mwh_per_day"])
            intent = _intent(legs, book, rule, stamp, "close", side, wanted, price, qty, reason,
                             edge, deliveries)
            events.append(intent)
            if price is None or not qty or qty < wanted:
                events.append({"kind": "no_fill", "at": stamp, "side": "close",
                               "intent_id": intent["intent_id"],
                               "reason": "not enough size on the screen to close"})
            else:
                closed = _close(state, legs, price, stamp, reason)
                closed["intent_id"] = intent["intent_id"]
                events.append(closed)
                position = 0
        elif desired in ("long", "short") and position == 0:
            side = 1 if desired == "long" else -1
            price = buy_px if side > 0 else sell_px
            on_screen = (buy_qty if side > 0 else sell_qty) or 0.0
            qty = min(rule.size_mwh_per_day, on_screen)
            intent = _intent(legs, book, rule, stamp, "open", side, rule.size_mwh_per_day, price,
                             on_screen, reason, edge, deliveries)
            events.append(intent)
            if price is None or qty <= 0:
                events.append({"kind": "no_fill", "at": stamp, "side": desired,
                               "intent_id": intent["intent_id"],
                               "reason": "no size on the screen"})
            else:
                state.update(position=side, qty_mwh_per_day=round(qty, 6), entry_price=price,
                             entry_at=stamp, entry_deliveries=deliveries)
                position = side
                events.append({
                    "kind": "fill", "at": stamp, "side": "buy" if side > 0 else "sell",
                    "action": "open", "price": _r(price), "mid": _r(mid),
                    "intent_id": intent["intent_id"],
                    "crossed_per_mwh": _r(abs(price - mid)) if mid is not None else None,
                    "qty_mwh_per_day": round(qty, 6),
                    "partial": qty < rule.size_mwh_per_day,
                    "legs": _leg_prices(legs, book, side, rule.slippage_per_mwh),
                })

    # Mark the open position at the price it could be closed at.
    unrealised = 0.0
    unrealised_per_mwh = 0.0
    if position:
        liquidation = sell_px if position > 0 else buy_px
        if liquidation is not None:
            state["last_liquidation"] = liquidation
        liquidation = state.get("last_liquidation")
        if liquidation is not None and state.get("entry_price") is not None:
            unrealised_per_mwh = position * (float(liquidation) - float(state["entry_price"]))
            unrealised = unrealised_per_mwh * _energy(legs, float(state["qty_mwh_per_day"]))
    equity = float(state.get("realised", 0.0)) + unrealised
    state["peak_equity"] = max(float(state.get("peak_equity", 0.0)), equity)
    state["max_drawdown"] = min(float(state.get("max_drawdown", 0.0)),
                                equity - state["peak_equity"])
    if mid is not None and not gates:
        samples.append([stamp, round(mid, 6)])
    state["samples"] = samples[-MAX_SAMPLES:]
    snapshot = {
        "at": stamp,
        "signal": state.get("signal"),
        "signal_at": state.get("signal_at"),
        "reason": reason,
        "gated": state.get("gated"),
        "mid": _r(mid), "mean": _r(mean), "sd": _r(sd), "z": _r(z, 4),
        "vwap_anchor": _r(anchor), "spread_bid": _r(sell_px), "spread_offer": _r(buy_px),
            "edge_net_per_mwh": _r(edge),
        "position": state.get("position", 0),
        "qty_mwh_per_day": state.get("qty_mwh_per_day", 0.0),
        "entry_price": _r(state.get("entry_price")),
        "unrealised": round(unrealised, 2),
        "unrealised_per_mwh": _r(unrealised_per_mwh),
        "realised": round(float(state.get("realised", 0.0)), 2),
        "realised_per_mwh": _r(float(state.get("realised_per_mwh", 0.0))),
        "equity": round(equity, 2),
        "max_drawdown": round(float(state["max_drawdown"]), 2),
        "closed_trades": state.get("closed_trades", 0),
        "winning_trades": state.get("winning_trades", 0),
        "worst_trade": state.get("worst_trade"),
        "samples_in_window": len(samples),
        "quote_age_seconds": _ages(legs, book, now),
        "simulated": simulated,
        "currency": next(iter({book[leg.key].currency for leg in legs if leg.key in book}), None),
    }
    return Evaluation(state=state, events=events, snapshot=snapshot, signal_changed=changed)


def _intent(legs: list[Leg], book: dict[str, LegQuote], rule: IntradayRule, stamp: str,
            action: str, side: int, size: float, limit: float | None, on_screen: float | None,
            reason: str, edge: float | None, deliveries: dict[str, str]) -> dict[str, Any]:
    """The order intent a signal makes: what a desk would put on the screen, recorded only.

    The same record a later order-ticket hand-off would carry (instrument per leg, side, size,
    limit, reason and the checks it passed); it is never sent anywhere (``sent: False``).
    """

    return {
        "kind": "intent",
        "intent_id": f"int-{stamp}-{action}",
        "at": stamp,
        "action": action,
        "side": "buy_spread" if side > 0 else "sell_spread",
        "legs": [
            {"instrument": f"{leg.hub} {leg.product}", "delivery_start": deliveries.get(leg.key),
             "side": "buy" if (leg.weight > 0) == (side > 0) else "sell",
             "weight": leg.weight}
            for leg in legs
        ],
        "size_mwh_per_day": round(size, 6),
        "limit": _r(limit),
        "reason": reason,
        "checks": {
            "liquidity_gates": "passed",
            "size_on_screen_mwh_per_day": _r(on_screen),
            "edge_net_per_mwh": _r(edge),
            "positive_edge": None if edge is None else edge > 0,
            "quote_age_seconds": {f"{leg.hub} {leg.product}": None for leg in legs}
            if not book else _ages(legs, book, datetime.fromisoformat(stamp)),
        },
        "paper": True,
        "sent": False,
    }


def _close(state: dict[str, Any], legs: list[Leg], price: float, stamp: str,
           reason: str) -> dict[str, Any]:
    side = int(state["position"])
    entry = float(state["entry_price"])
    qty = float(state["qty_mwh_per_day"])
    per_mwh = side * (price - entry)
    pnl = per_mwh * _energy(legs, qty)
    state["realised"] = float(state.get("realised", 0.0)) + pnl
    state["realised_per_mwh"] = float(state.get("realised_per_mwh", 0.0)) + per_mwh
    state["closed_trades"] = int(state.get("closed_trades", 0)) + 1
    state["winning_trades"] = int(state.get("winning_trades", 0)) + (1 if pnl > 0 else 0)
    worst = state.get("worst_trade")
    if worst is None or pnl < float(worst):
        state["worst_trade"] = round(pnl, 2)
    event = {
        "kind": "fill", "at": stamp, "side": "sell" if side > 0 else "buy", "action": "close",
        "price": _r(price), "entry_price": _r(entry), "opened_at": state.get("entry_at"),
        "qty_mwh_per_day": qty, "pnl_per_mwh": _r(per_mwh), "pnl": round(pnl, 2),
        "reason": reason,
    }
    state.update(position=0, qty_mwh_per_day=0.0, entry_price=None, entry_at=None,
                 entry_deliveries={})
    return event


def _leg_prices(legs: list[Leg], book: dict[str, LegQuote], side: int,
                slippage: float) -> list[dict[str, Any]]:
    out = []
    for leg in legs:
        quote = book[leg.key]
        buying = (leg.weight > 0) == (side > 0)
        level = quote.ask if buying else quote.bid
        out.append({
            "leg": f"{leg.hub} {leg.product}", "side": "buy" if buying else "sell",
            "price": _r((level or 0.0) + (slippage if buying else -slippage)),
            "quoted_size_mwh_per_day": quote.ask_size_mwh if buying else quote.bid_size_mwh,
            "source_system": quote.source_system,
        })
    return out


def _ages(legs: list[Leg], book: dict[str, LegQuote], now: datetime) -> dict[str, float]:
    return {
        f"{leg.hub} {leg.product}": round((now - book[leg.key].observed_at).total_seconds(), 3)
        for leg in legs if leg.key in book
    }


def _r(value: float | None, digits: int = 6) -> float | None:
    return None if value is None else round(float(value), digits)
