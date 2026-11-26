"""The prompt market read: within-day and day-ahead for one hub, and today's performance.

For the trader who balances and optimises on WD/DA in seconds to minutes (the execution
screen, Trayport or the exchange, is where orders go; nothing here sends one, AGENTS.md
rule 8). One read, also called in-process by Today (``prompt_market``):

- **Market**: the live WD and DA bid/offer with size, last trade, session VWAP, volume and
  number of trades, prior settlement where the feed carries it, each quote's age, and the
  WD − DA spread (mid and what crossing it costs).
- **Performance**, post-trade only: for trades booked today on these two gas days, the
  achieved price against the session VWAP, the day-ahead settlement (index) and the mid at
  decision (trade) time, the slippage against the touch at that moment, the running day P&L
  marked at the current mid, and the caller's tracked-strategy signals that expired unused
  ("missed").

The position to balance, nomination deadlines and imbalance exposure belong to Today's gas-day
view, not to this read. Every read runs under the caller (book scope and source entitlement);
simulated inputs keep the result simulated.

即日/日前行情读取与当日成交后绩效（相对 VWAP、结算价、决策时中间价）；不下单。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func

from eurogas_nexus.domain.market.gas_day import gas_day_label, gas_day_start_for_date
from eurogas_nexus.domain.market.products import resolve_product

PRODUCTS = (("within_day", "within-day"), ("day_ahead", "day-ahead"))
QUOTE_MAX_AGE = timedelta(hours=6)


def _aware(moment):
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _round(value, places=4):
    return None if value is None else round(float(value), places)


def _quote_dict(row) -> dict[str, Any]:
    mid = None if row.bid_price is None or row.ask_price is None else (
        row.bid_price + row.ask_price) / 2
    return {
        "bid": row.bid_price, "ask": row.ask_price, "mid": _round(mid, 5),
        "bid_mwh_per_day": row.bid_quantity_mwh, "ask_mwh_per_day": row.ask_quantity_mwh,
        "last": row.last_price, "last_mwh_per_day": row.last_quantity_mwh,
        "vwap": row.vwap, "volume_mwh": row.volume_mwh, "trade_count": row.trade_count,
        "session_high": row.session_high, "session_low": row.session_low,
        "settlement": row.settlement_price, "prior_settlement": row.prior_settlement_price,
        "observed_at_utc": _aware(row.observed_at_utc).isoformat(),
        "source_system": row.source_system, "simulated": bool(row.simulated),
        "currency": row.currency, "delivery_start_utc": _aware(row.delivery_start_utc).isoformat(),
    }


def _quotes(session, principal, hub: str, product: str, delivery_start: datetime, now: datetime):
    """Entitled quotes for one delivery, newest first (a sized screen quote first)."""

    from eurogas_nexus.application.projections.market_reads import row_allowed
    from eurogas_nexus.db.models import MarketQuoteRecord

    rows = (
        session.query(MarketQuoteRecord)
        .filter(MarketQuoteRecord.hub == hub, MarketQuoteRecord.product == product,
                MarketQuoteRecord.delivery_start_utc == delivery_start,
                MarketQuoteRecord.observed_at_utc >= now - QUOTE_MAX_AGE,
                MarketQuoteRecord.observed_at_utc <= now + timedelta(seconds=5))
        .order_by(MarketQuoteRecord.observed_at_utc.desc())
        .limit(400)
        .all()
    )
    allowed = [row for row in rows if row_allowed(principal, row.source_system)]
    real = [row for row in allowed if not row.simulated]
    return real or allowed


def prompt_days(today: date) -> dict[str, date]:
    """The gas days the within-day and day-ahead products deliver on ``today``.

    Day-ahead is the next working day (Friday's DA delivers Monday), resolved exactly as the
    tick intake resolves it, so a Friday read finds the DA quote the intake stored.
    """

    return {"within_day": today, "day_ahead": resolve_product("DA", today).first_gas_day}


def _at(rows, moment: datetime):
    """The newest quote at or before ``moment`` (rows newest first)."""

    return next((row for row in rows if _aware(row.observed_at_utc) <= moment), None)


def prompt_market(session, who: Any, hub: str, *, now: datetime | None = None,
                  ) -> dict[str, Any]:
    from eurogas_nexus.application.caller import caller_of
    from eurogas_nexus.application.projections.market_reads import row_allowed
    from eurogas_nexus.application.projections.portfolio_reads import screen_orders
    from eurogas_nexus.db.models import MarketTradeRecord

    caller = caller_of(who)
    principal = caller.principal
    now = now or datetime.now(UTC)
    hub = hub.upper()
    today = date.fromisoformat(gas_day_label(now))
    days = prompt_days(today)
    starts = {key: gas_day_start_for_date(day) for key, day in days.items()}
    warnings: list[str] = []

    # Market, per product.
    market: dict[str, Any] = {}
    quote_rows: dict[str, list] = {}
    for key, product in PRODUCTS:
        rows = _quotes(session, principal, hub, product, starts[key], now)
        quote_rows[key] = rows
        sized = [row for row in rows if row.bid_quantity_mwh is not None] or rows
        latest = sized[0] if sized else None
        entry = _quote_dict(latest) if latest else None
        if entry:
            entry["age_seconds"] = round((now - _aware(latest.observed_at_utc)).total_seconds(), 1)
            last_trade = (
                session.query(MarketTradeRecord)
                .filter(MarketTradeRecord.hub == hub, MarketTradeRecord.product == product,
                        MarketTradeRecord.delivery_start_utc == starts[key],
                        MarketTradeRecord.source_system == latest.source_system,
                        MarketTradeRecord.trade_type == "screen")
                .order_by(MarketTradeRecord.traded_at_utc.desc())
                .first()
            )
            if last_trade is not None and row_allowed(principal, last_trade.source_system):
                entry["last_trade"] = {
                    "price": last_trade.price, "mwh_per_day": last_trade.quantity_mwh,
                    "aggressor": last_trade.aggressor,
                    "at_utc": _aware(last_trade.traded_at_utc).isoformat(),
                }
        market[key] = {"gas_day": days[key].isoformat(), "quote": entry}
    wd, da = (market[key]["quote"] for key, _ in PRODUCTS)
    spread = None
    if wd and da and None not in (wd["bid"], wd["ask"], da["bid"], da["ask"]):
        spread = {"mid": _round(wd["mid"] - da["mid"], 5),
                  "buy": _round(wd["ask"] - da["bid"], 5),
                  "sell": _round(wd["bid"] - da["ask"], 5),
                  "unit": f"{wd['currency']}/MWh"}

    # Performance of today's booked prompt trades.
    trades = []
    pnl = 0.0
    pnl_simulated = False
    try:
        orders = screen_orders(session, principal_id=principal.principal_id)
    except Exception as exc:  # noqa: BLE001
        orders = []
        warnings.append(f"booked trades not available ({type(exc).__name__})")
    for order in orders:
        if (order.hub or "").upper() != hub or str(order.status).upper() != "FILLED":
            continue
        traded_at = _aware(order.observed_at_utc if isinstance(order.observed_at_utc, datetime)
                           else datetime.fromisoformat(str(order.observed_at_utc)))
        if gas_day_label(traded_at) != today.isoformat():
            continue
        start = _aware(order.delivery_start_utc if isinstance(order.delivery_start_utc, datetime)
                       else datetime.fromisoformat(str(order.delivery_start_utc)))
        key = next((k for k, s in starts.items() if s == start), None)
        if key is None:
            continue
        sign = 1 if str(order.side).lower() in {"buy", "b"} else -1
        qty = float(order.filled_quantity_mwh or 0.0)
        price = float(order.price)
        rows = quote_rows[key]
        at = _at(rows, traded_at)
        current = market[key]["quote"]
        decision_mid = None if at is None or at.bid_price is None or at.ask_price is None else (
            (at.bid_price + at.ask_price) / 2)
        touch = None if at is None else (at.ask_price if sign > 0 else at.bid_price)
        vwap = current.get("vwap") if current else None
        settlement = current.get("prior_settlement") if current else None
        mark = current.get("mid") if current else None
        trade_pnl = None if mark is None else sign * (mark - price) * qty
        if trade_pnl is not None:
            pnl += trade_pnl
            pnl_simulated = pnl_simulated or bool(current.get("simulated"))

        def better(reference, sign=sign, price=price):
            # Positive is better for the desk: bought below, or sold above, the reference.
            return None if reference is None else _round(sign * (reference - price), 4)

        trades.append({
            "id": order.external_order_id, "product": key, "side": "buy" if sign > 0 else "sell",
            "price": price, "mwh": qty, "traded_at_utc": traded_at.isoformat(),
            "vs_vwap": better(vwap), "vs_settlement": better(settlement),
            "vs_decision_mid": better(decision_mid),
            "slippage_vs_touch": None if touch is None else _round(sign * (touch - price), 4),
            "pnl": None if trade_pnl is None else round(trade_pnl, 2),
            "simulated": str(order.source_system).endswith("_Sim"),
        })
    performance = {
        "trades": trades,
        "day_pnl": round(pnl, 2),
        "currency": (wd or da or {}).get("currency"),
        "marked_at": "current mid",
        "simulated": pnl_simulated or any(item["simulated"] for item in trades),
        "basis": "Post-trade: positive is better for the desk (bought below / sold above the "
                 "reference). Decision mid and touch are the quote on the screen at the "
                 "booked trade time; settlement is the venue's prior settlement where the "
                 "feed carries it.",
    }
    try:
        from eurogas_nexus.application.strategy_tracking import missed_signals

        performance["missed_signals"] = missed_signals(
            session, principal, hub, starts["within_day"])
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"tracked signals not available ({type(exc).__name__})")
    simulated = any((q or {}).get("simulated") for q in (wd, da)) or performance["simulated"]
    return {
        "hub": hub, "as_of_utc": now.isoformat(), "market": market,
        "spread_wd_da": spread, "performance": performance, "simulated": simulated,
        "warnings": warnings,
        "execution": "none: decision support only; orders go on the execution screen",
    }


def latest_tick_receipt(session) -> datetime | None:
    from eurogas_nexus.db.models import MarketQuoteRecord

    return _aware(session.query(func.max(MarketQuoteRecord.received_at_utc)).scalar())
