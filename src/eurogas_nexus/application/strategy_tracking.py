"""Track a Spreads strategy: a shadow run on the same StrategySpec, with a paper book only.

Two modes, one store (``strategy_tracks``/``strategy_track_events``), no second engine:

- **daily**: a history spec with a rule (z-score or threshold) is re-run on the daily closes
  by the spread lab's engine (``domain/research/spread_analysis``) when a new close arrives;
  the track keeps the signal of the latest close and the paper P&L since the track started.
- **intraday**: legs on prompt products (WD, DA, WE, BOM, M+1) and an intraday rule
  (``domain/research/intraday_strategy``) evaluated when one of its instruments ticks
  (:func:`on_market_update`, called by the tick ingestion in the same process and
  transaction), at most once per ``debounce_seconds``; :func:`run_due` catches the trailing
  tick from the monitoring worker's loop.

Every read and evaluation runs under the owner: prices from source families the owner is
entitled to (re-read from the identity store, so a withdrawn scope stops the track's inputs),
and only the owner sees the track. A stopped owner identity pauses its tracks. Nothing here
creates an order, a nomination or an instruction: fills are paper fills against the quote that
was on the screen, labelled paper.

跟踪策略（影子运行）：与价差工作台同一 StrategySpec；日度按收盘、日内按行情到达评估；
仅纸面账簿，不下单；按所有者授权读取价格，只有所有者可见。
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from eurogas_nexus.db.models import (
    MarketQuoteRecord,
    MarketTradeRecord,
    StrategyTrackEventRecord,
    StrategyTrackRecord,
)
from eurogas_nexus.domain.research import intraday_strategy as engine
from eurogas_nexus.domain.research.strategy_spec import spec_from_dict

MODES = ("daily", "intraday")
MAX_TRACKS_PER_OWNER = 20
EQUITY_MARK_SECONDS = 15.0
#: Desk product code → the stored quote product key.
QUOTE_PRODUCTS = {
    "WD": "within-day", "DA": "day-ahead", "WE": "weekend", "BOM": "bom", "M+1": "month-ahead",
    "MA": "month-ahead",
}
#: Quotes older than this are not looked at for a leg (the rule's own age gate is tighter).
QUOTE_LOOKBACK = timedelta(hours=36)


class TrackError(ValueError):
    """A track that cannot be saved as asked; ``code`` names the field."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _aware(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _currency(hub: str) -> str:
    from eurogas_nexus.domain.market.units import HUB_NATIVE_PRICE_UNIT

    native = HUB_NATIVE_PRICE_UNIT.get(hub, "EUR/MWh")
    return "GBP" if native.startswith("GBp") or native.startswith("GBP") else native.split("/")[0]


def intraday_legs(spec_data: dict[str, Any]) -> list[engine.Leg]:
    spec = spec_from_dict(spec_data)
    if spec.issues:
        raise TrackError("spec", spec.issues[0].message)
    legs = []
    for leg in spec.legs:
        product = QUOTE_PRODUCTS.get((leg.tenor or "").strip().upper())
        if product is None:
            raise TrackError(
                "spec.legs",
                f"{leg.hub} {leg.tenor or ''}: intraday tracking reads WD, DA, WE, BOM or M+1",
            )
        legs.append(engine.Leg(leg.hub, product, leg.weight))
    if len({_currency(leg.hub) for leg in legs}) > 1:
        raise TrackError("spec.legs", "intraday tracking needs legs quoted in one currency")
    return legs


def create_track(
    session: Session,
    principal: Any,
    *,
    name: str,
    spec: dict[str, Any],
    mode: str,
    rule: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Save a track for ``principal``; raises :class:`TrackError` with the field at fault."""

    now = now or datetime.now(UTC)
    if mode not in MODES:
        raise TrackError("mode", f"mode must be one of {MODES}")
    owner = principal.principal_id
    count = session.query(func.count(StrategyTrackRecord.track_id)).filter(
        StrategyTrackRecord.owner_principal_id == owner,
        StrategyTrackRecord.state == "active",
    ).scalar()
    if int(count or 0) >= MAX_TRACKS_PER_OWNER:
        raise TrackError("tracks", f"at most {MAX_TRACKS_PER_OWNER} active tracks each")
    parsed = spec_from_dict(spec)
    if parsed.issues:
        raise TrackError("spec", parsed.issues[0].message)
    if mode == "intraday":
        legs = intraday_legs(spec)
        try:
            checked = engine.rule_from_dict(rule)
        except engine.IntradayRuleError as exc:
            raise TrackError("rule", str(exc)) from exc
        rule_json = checked.as_dict()
        instruments = [leg.key for leg in legs]
    else:
        if parsed.kind != "history" or parsed.rule is None:
            raise TrackError("spec.rule", "a daily track needs a history with a rule")
        _check_daily_rule(parsed)
        rule_json = parsed.rule.as_dict()
        instruments = [f"{leg.hub}|{leg.tenor}" for leg in parsed.legs]
    record = StrategyTrackRecord(
        track_id=f"trk-{uuid.uuid4().hex[:20]}",
        owner_principal_id=owner,
        name=(name or "").strip()[:160] or "Tracked strategy",
        mode=mode,
        state="active",
        spec_json=parsed.as_dict(),
        rule_json=rule_json,
        instruments=instruments,
        book_state=engine.new_state(),
        snapshot=None,
        created_at_utc=now,
        evaluations=0,
    )
    session.add(record)
    session.flush()
    return summary(record)


def _check_daily_rule(parsed) -> None:
    """Refuse a daily rule the spread engine would refuse on every evaluation.

    Without this a rule such as ``exit_z >= entry_z`` was saved as an active track whose every
    evaluation failed, so the panel showed "no signal" for a strategy that could never run.
    """

    from eurogas_nexus.domain.research.spread_analysis import SpreadAnalysisError, SpreadRule

    rule = {k: v for k, v in parsed.rule.as_dict().items() if v is not None}
    if parsed.volume_mwh_per_day:
        rule["volume_mwh_per_day"] = parsed.volume_mwh_per_day
    try:
        SpreadRule(**rule).validate()
    except (SpreadAnalysisError, TypeError) as exc:
        raise TrackError("spec.rule", str(exc)) from exc


def summary(record: StrategyTrackRecord) -> dict[str, Any]:
    snapshot = record.snapshot or {}
    return {
        "track_id": record.track_id,
        "name": record.name,
        "mode": record.mode,
        "state": record.state,
        "paper": True,
        "spec": record.spec_json,
        "rule": record.rule_json,
        "created_at_utc": _aware(record.created_at_utc).isoformat(),
        "last_evaluated_at_utc": _iso(record.last_evaluated_at_utc),
        "signal_changed_at_utc": _iso(record.signal_changed_at_utc),
        "evaluations": record.evaluations,
        "snapshot": snapshot,
        "assumptions": _assumptions(record),
    }


def _iso(moment: datetime | None) -> str | None:
    aware = _aware(moment)
    return aware.isoformat() if aware else None


def _assumptions(record: StrategyTrackRecord) -> str:
    if record.mode == "intraday":
        return engine.assumptions(engine.rule_from_dict(record.rule_json))
    from eurogas_nexus.domain.research.spread_analysis import assumptions_line

    return "Paper only, nothing is sent. " + assumptions_line(record.rule_json)


def list_tracks(session: Session, principal: Any) -> list[dict[str, Any]]:
    rows = (
        session.query(StrategyTrackRecord)
        .filter(StrategyTrackRecord.owner_principal_id == principal.principal_id)
        .order_by(StrategyTrackRecord.created_at_utc.desc())
        .limit(100)
        .all()
    )
    return [summary(row) for row in rows]


def _owned(session: Session, principal: Any, track_id: str) -> StrategyTrackRecord | None:
    record = session.get(StrategyTrackRecord, track_id)
    if record is None or record.owner_principal_id != principal.principal_id:
        return None  # another user's track reads as absent
    return record


def get_track(session: Session, principal: Any, track_id: str,
              *, limit: int = 500) -> dict[str, Any] | None:
    record = _owned(session, principal, track_id)
    if record is None:
        return None
    events = (
        session.query(StrategyTrackEventRecord)
        .filter(StrategyTrackEventRecord.track_id == track_id)
        .order_by(StrategyTrackEventRecord.at_utc.desc())
        .limit(max(1, min(limit, 5000)))
        .all()
    )
    events = list(reversed(events))
    blotter = [dict(e.payload, kind=e.kind) for e in events if e.kind in ("fill", "no_fill")]
    intents = [dict(e.payload, kind=e.kind) for e in events if e.kind == "intent"]
    signals = [dict(e.payload, kind=e.kind) for e in events
               if e.kind in ("signal", "gated", "missed", "superseded")]
    equity = [
        {"at": e.payload.get("at"), "equity": e.payload.get("equity"),
         "realised": e.payload.get("realised"), "unrealised": e.payload.get("unrealised")}
        for e in events if e.kind == "mark"
    ]
    return {**summary(record), "intents": intents, "blotter": blotter, "signals": signals,
            "equity": equity}


def stop_track(session: Session, principal: Any, track_id: str,
               now: datetime | None = None) -> dict[str, Any] | None:
    record = _owned(session, principal, track_id)
    if record is None:
        return None
    record.state = "stopped"
    record.stopped_at_utc = now or datetime.now(UTC)
    session.flush()
    return summary(record)


# ---------------------------------------------------------------------------- evaluation


def _owner_caller(session: Session, principal_id: str):
    """The owner as stored now (status and data scopes), or None when no longer active."""

    from eurogas_nexus.application.caller import Caller
    from eurogas_nexus.db.models import IdentityPrincipalRecord
    from eurogas_nexus.security.identity import AuthenticatedPrincipal

    record = session.get(IdentityPrincipalRecord, principal_id)
    if record is None or str(record.status).upper() != "ACTIVE":
        return None
    return Caller(AuthenticatedPrincipal(
        principal_id=record.principal_id,
        name=record.name,
        principal_type=record.principal_type,
        role=record.role,
        status=record.status,
        data_scopes=tuple(record.data_scopes or ()),
        roles=tuple(record.roles or ()),
    ))


def _book(session: Session, caller, legs: list[engine.Leg], now: datetime,
          sticky: dict[str, str] | None = None, max_age: float = 120.0,
          ) -> tuple[dict[str, engine.LegQuote], datetime | None]:
    """The quote per leg the track reads: one source per leg, kept between evaluations.

    A licensed source beats a simulated one; a quote that carries a size (a two-sided screen
    quote) beats one that does not (an end-of-day board snapshot); among those, the source the
    leg was read from last time (``sticky``) while it is fresh, else the newest. Sources are
    not mixed tick by tick.
    """

    from eurogas_nexus.application.projections.market_reads import row_allowed

    principal = caller.principal
    book: dict[str, engine.LegQuote] = {}
    newest_receipt: datetime | None = None
    since = now - QUOTE_LOOKBACK
    for leg in legs:
        rows = (
            session.query(MarketQuoteRecord)
            .filter(MarketQuoteRecord.hub == leg.hub,
                    MarketQuoteRecord.product == leg.product,
                    MarketQuoteRecord.observed_at_utc >= since,
                    MarketQuoteRecord.observed_at_utc <= now + timedelta(seconds=5))
            .order_by(MarketQuoteRecord.observed_at_utc.desc())
            .limit(40)
            .all()
        )
        allowed = [row for row in rows if row_allowed(principal, row.source_system)]
        pool = [row for row in allowed if not row.simulated] or allowed
        if not pool:
            continue
        previous = (sticky or {}).get(leg.key)
        sized = [row for row in pool
                 if row.bid_quantity_mwh is not None and row.ask_quantity_mwh is not None]
        candidates = sized or pool
        fresh = now - timedelta(seconds=max_age)
        same = [row for row in candidates if row.source_system == previous
                and _aware(row.observed_at_utc) >= fresh]
        chosen = (same or candidates)[0]
        last_trade = (
            session.query(func.max(MarketTradeRecord.traded_at_utc))
            .filter(and_(MarketTradeRecord.hub == leg.hub,
                         MarketTradeRecord.product == leg.product,
                         MarketTradeRecord.source_system == chosen.source_system,
                         MarketTradeRecord.delivery_start_utc == chosen.delivery_start_utc,
                         MarketTradeRecord.trade_type == "screen"))
            .scalar()
        )
        received = _aware(chosen.received_at_utc)
        newest_receipt = max(filter(None, [newest_receipt, received]), default=None)
        book[leg.key] = engine.LegQuote(
            bid=chosen.bid_price,
            ask=chosen.ask_price,
            bid_size_mwh=chosen.bid_quantity_mwh,
            ask_size_mwh=chosen.ask_quantity_mwh,
            observed_at=_aware(chosen.observed_at_utc),
            delivery_start=_aware(chosen.delivery_start_utc).isoformat(),
            currency=chosen.currency,
            source_system=chosen.source_system,
            simulated=bool(chosen.simulated),
            vwap=chosen.vwap,
            volume_mwh=chosen.volume_mwh,
            last_trade_at=_aware(last_trade),
        )
    return book, newest_receipt


def _event(session: Session, track_id: str, kind: str, at: datetime,
           payload: dict[str, Any]) -> None:
    session.add(StrategyTrackEventRecord(
        event_id=f"tev-{uuid.uuid4().hex[:24]}", track_id=track_id, kind=kind, at_utc=at,
        payload={**payload, "paper": True},
    ))


def evaluate_intraday(session: Session, record: StrategyTrackRecord,
                      now: datetime) -> dict[str, Any]:
    """Evaluate one intraday track on the latest quotes; persist state, events and a mark."""

    started = time.perf_counter()
    caller = _owner_caller(session, record.owner_principal_id)
    if caller is None:
        record.state = "paused"
        return {"track_id": record.track_id, "status": "owner_inactive"}
    legs = intraday_legs(record.spec_json)
    rule = engine.rule_from_dict(record.rule_json)
    sticky = dict((record.book_state or {}).get("sources") or {})
    book, receipt = _book(session, caller, legs, now, sticky, rule.max_quote_age_seconds)
    result = engine.evaluate(legs, rule, book, record.book_state, now)
    result.state["sources"] = {key: quote.source_system for key, quote in book.items()}
    for item in result.events:
        _event(session, record.track_id, item["kind"], now, item)
    record.book_state = result.state
    last_mark = (record.snapshot or {}).get("last_mark_at")
    snapshot = dict(result.snapshot)
    fills = any(item["kind"] == "fill" for item in result.events)
    if fills or last_mark is None or (
        now - datetime.fromisoformat(last_mark)
    ).total_seconds() >= EQUITY_MARK_SECONDS:
        _event(session, record.track_id, "mark", now, {
            "at": now.isoformat(), "equity": snapshot["equity"],
            "realised": snapshot["realised"], "unrealised": snapshot["unrealised"],
            "mid": snapshot["mid"], "position": snapshot["position"],
        })
        last_mark = now.isoformat()
    elapsed_ms = (time.perf_counter() - started) * 1000
    # From the newest leg quote's receipt to this evaluation's end, on the wall clock.
    latency_ms = None if receipt is None else (
        (datetime.now(UTC) - receipt).total_seconds() * 1000
    )
    snapshot.update(last_mark_at=last_mark, evaluation_ms=round(elapsed_ms, 2),
                    latency_ms=None if latency_ms is None else round(latency_ms, 1))
    cutoff = cutoff_for(legs, result.state, now)
    previous = (record.snapshot or {}).get("advice")
    if result.signal_changed:
        if previous and previous.get("signal") in ("long", "short", "flat"):
            _event(session, record.track_id, "superseded", now,
                   {"at": now.isoformat(), "advice": previous})
        record.signal_changed_at_utc = now
        advice = _advice(result.events, snapshot, cutoff)
        closed = any(item["kind"] == "fill" and item.get("action") == "close"
                     for item in result.events)
        keep = advice is not None and (advice["signal"] in ("long", "short")
                                       or (advice["signal"] == "flat" and closed))
        snapshot["advice"] = advice if keep else None
    elif previous:
        stale = max((snapshot.get("quote_age_seconds") or {"": 0}).values() or [0]) > float(
            rule.max_quote_age_seconds)
        expired = previous.get("expires_at") and datetime.fromisoformat(
            previous["expires_at"]) <= now
        if expired or stale or result.state.get("gated"):
            # Withdrawn, never left on screen as overdue: logged as missed for review.
            reason = "expired" if expired else ("quote stale" if stale else "market gated")
            _event(session, record.track_id, "missed", now,
                   {"at": now.isoformat(), "reason": reason, "advice": previous})
            snapshot["advice"] = None
            snapshot["withdrawn"] = {"at": now.isoformat(), "reason": reason}
        else:
            snapshot["advice"] = previous
    record.snapshot = snapshot
    record.last_evaluated_at_utc = now
    record.evaluations = int(record.evaluations or 0) + 1
    return {"track_id": record.track_id, "status": "evaluated",
            "signal_changed": result.signal_changed, "evaluation_ms": round(elapsed_ms, 2),
            "latency_ms": snapshot["latency_ms"]}


def cutoff_for(legs: list[engine.Leg], book_state: dict[str, Any], now: datetime) -> datetime:
    """The latest instant the signal can still be acted on, by the legs' products.

    Within-day: the last renomination of the gas day (three hours before its end); day-ahead:
    the nomination deadline for that gas day (13:00 UTC the day before in winter); others: the
    end of the current gas day. Network-code defaults, stated with the signal; one calendar
    with Today's gas day (``domain/market/hub_cutoffs``).
    """

    from eurogas_nexus.domain.market.gas_day import gas_day_label
    from eurogas_nexus.domain.market.hub_cutoffs import gas_day_end, product_cutoff

    end_of_today = gas_day_end(date.fromisoformat(gas_day_label(now)))
    cutoffs = [product_cutoff(leg.product, now) for leg in legs]
    return min(cutoffs) if cutoffs else end_of_today


def _advice(events: list[dict[str, Any]], snapshot: dict[str, Any],
            cutoff: datetime | None = None) -> dict[str, Any] | None:
    signal = next((item for item in events if item["kind"] == "signal"), None)
    if signal is None:
        return None
    return {
        "signal": signal["signal"],
        "reason": signal.get("reason"),
        "entry_level": signal["spread_offer"] if signal["signal"] == "long"
        else signal["spread_bid"] if signal["signal"] == "short" else None,
        "spread_bid": signal.get("spread_bid"),
        "spread_offer": signal.get("spread_offer"),
        "edge_net_per_mwh": signal.get("edge_net_per_mwh"),
        "at": signal["at"],
        "computed_at": signal["at"],
        "quote_age_seconds": signal.get("quote_age_seconds"),
        "expires_at": min(
            filter(None, [signal.get("expires_at"), cutoff.isoformat() if cutoff else None])
        ) if signal.get("expires_at") or cutoff else None,
        "cutoff_at": cutoff.isoformat() if cutoff else None,
        "currency": snapshot.get("currency"),
        "simulated": signal.get("simulated"),
    }


def on_market_update(session: Session, instruments: set[str],
                     now: datetime | None = None, *, replay: bool = False) -> dict[str, Any]:
    """Evaluate the active intraday tracks listening to any of ``instruments`` (debounced).

    ``replay`` (a compressed simulated session, its clock behind the last evaluation) debounces
    on the session clock only.
    """

    now = now or datetime.now(UTC)
    if not instruments:
        return {"evaluated": 0, "debounced": 0, "results": []}
    tracks = (
        session.query(StrategyTrackRecord)
        .filter(StrategyTrackRecord.mode == "intraday", StrategyTrackRecord.state == "active")
        .all()
    )
    results, debounced = [], 0
    for record in tracks:
        if not set(record.instruments or ()) & instruments:
            continue
        debounce = float((record.rule_json or {}).get("debounce_seconds") or 0)
        last = _aware(record.last_evaluated_at_utc)
        gap = None if last is None else (now - last).total_seconds()
        if gap is not None and gap < debounce and not (replay and gap < 0):
            debounced += 1
            continue
        results.append(evaluate_intraday(session, record, now))
    session.flush()
    return {"evaluated": len(results), "debounced": debounced, "results": results}


def run_due(session: Session, now: datetime | None = None) -> dict[str, Any]:
    """The trailing tick of each intraday track (a quote newer than its last evaluation),
    and the daily tracks whose newest close is newer than their last evaluation."""

    now = now or datetime.now(UTC)
    evaluated = 0
    for record in session.query(StrategyTrackRecord).filter(
        StrategyTrackRecord.state == "active"
    ).all():
        last = _aware(record.last_evaluated_at_utc)
        if record.mode == "intraday":
            hubs_products = [key.split("|", 1) for key in record.instruments or ()]
            newest = max(
                (_aware(session.query(func.max(MarketQuoteRecord.received_at_utc)).filter(
                    MarketQuoteRecord.hub == hub, MarketQuoteRecord.product == product
                ).scalar()) for hub, product in hubs_products),
                default=None, key=lambda value: value or datetime.min.replace(tzinfo=UTC),
            )
            if newest is not None and (last is None or newest > last):
                evaluate_intraday(session, record, now)
                evaluated += 1
        elif last is None or last.date() < now.date():
            evaluate_daily(session, record, now)
            evaluated += 1
    session.flush()
    return {"evaluated": evaluated}


def evaluate_daily(session: Session, record: StrategyTrackRecord,
                   now: datetime) -> dict[str, Any]:
    """Re-run the spread lab on the closes; keep the latest signal and P&L since the start."""

    from eurogas_nexus.application.spread_history import (
        SpreadAnalysisInput,
        SpreadHistoryError,
        spread_history,
    )
    from eurogas_nexus.application.spreads_workbench import load_holdings, stored_tenor

    caller = _owner_caller(session, record.owner_principal_id)
    if caller is None:
        record.state = "paused"
        return {"track_id": record.track_id, "status": "owner_inactive"}
    spec = spec_from_dict(record.spec_json)
    holdings = load_holdings(caller, today=now.date())
    legs = [{"hub": leg.hub,
             "tenor": stored_tenor(holdings, leg.hub, leg.tenor or "") or leg.tenor,
             "weight": leg.weight} for leg in spec.legs]
    rule = {k: v for k, v in (record.rule_json or {}).items() if v is not None}
    if spec.volume_mwh_per_day:
        rule["volume_mwh_per_day"] = spec.volume_mwh_per_day
    try:
        analysis = spread_history(
            SpreadAnalysisInput(
                legs=legs, rule=rule, unit=spec.unit, fx=spec.fx,
                route_cost={"from_hub": spec.cost.from_hub, "to_hub": spec.cost.to_hub}
                if spec.cost else None,
            ),
            caller,
        )["data"]
    except SpreadHistoryError as exc:
        record.snapshot = {**(record.snapshot or {}), "error": dict(exc.detail)}
        record.last_evaluated_at_utc = now
        return {"track_id": record.track_id, "status": "refused"}
    points = analysis["points"]
    start: date = _aware(record.created_at_utc).date()
    since = [p for p in points if date.fromisoformat(p["date"]) > start]
    last = points[-1] if points else None
    # ``position`` is what the rule holds from the latest close (decided at the close before,
    # under next-close execution); ``signal`` is what the latest close decided, to be traded at
    # the next close. The advice must be the signal: showing the held position announced every
    # entry and exit one close after the backtest (and the paper P&L) had already traded it.
    position = last["position"] if last else 0
    decided = int(last.get("signal", position)) if last else 0
    signal = {1: "long", -1: "short", 0: "flat"}[decided]
    previous = (record.snapshot or {}).get("signal")
    pnl = round(sum(p["pnl"] for p in since), 2)
    snapshot = {
        "at": now.isoformat(), "signal": signal, "position": position,
        "trade_at": "next close" if (record.rule_json or {}).get("execution", "next_close")
        == "next_close" else "this close",
        "close_date": last["date"] if last else None, "spread": last["spread"] if last else None,
        "z": last["zscore"] if last else None, "unit": analysis.get("unit"),
        "paper_pnl_since_start": pnl, "days_since_start": len(since),
        "simulated": any("simulated" in str(item).lower()
                         for item in analysis.get("limitations", [])),
    }
    changed = previous is not None and previous != signal
    if previous is None or changed:
        _event(session, record.track_id, "signal", now, {
            "at": now.isoformat(), "signal": signal, "close_date": snapshot["close_date"],
            "spread": snapshot["spread"], "z": snapshot["z"], "unit": snapshot["unit"],
            "simulated": snapshot["simulated"],
        })
    if changed:
        record.signal_changed_at_utc = now
        snapshot["advice"] = {"signal": signal, "at": now.isoformat(),
                              "entry_level": snapshot["spread"], "unit": snapshot["unit"],
                              "simulated": snapshot["simulated"]}
    _event(session, record.track_id, "mark", now, {"at": now.isoformat(), "equity": pnl,
                                                    "realised": None, "unrealised": None})
    record.snapshot = snapshot
    record.book_state = {**(record.book_state or {}), "position": position}
    record.last_evaluated_at_utc = now
    record.evaluations = int(record.evaluations or 0) + 1
    return {"track_id": record.track_id, "status": "evaluated", "signal_changed": changed}


def signal_findings(session: Session, principal: Any, now: datetime,
                    hours: float = 6.0) -> list[dict[str, Any]]:
    """The owner's tracks whose signal changed in the last ``hours`` (for "What needs me")."""

    since = now - timedelta(hours=hours)
    rows = (
        session.query(StrategyTrackRecord)
        .filter(StrategyTrackRecord.owner_principal_id == principal.principal_id,
                StrategyTrackRecord.state == "active",
                StrategyTrackRecord.signal_changed_at_utc >= since)
        .all()
    )
    out = []
    for row in rows:
        advice = (row.snapshot or {}).get("advice")
        if not advice:
            continue
        expires = advice.get("expires_at")
        if expires and datetime.fromisoformat(expires) <= now:
            continue  # withdrawn at its cut-off, never shown as overdue
        out.append({"track_id": row.track_id, "name": row.name, "mode": row.mode,
                    "advice": advice, "changed_at": _iso(row.signal_changed_at_utc)})
    return out


def _on_inputs_changed(session: Session, instruments: frozenset[str], at: datetime,
                       replay: bool) -> dict[str, Any]:
    return on_market_update(session, set(instruments), now=at, replay=replay)


def _subscribe() -> None:
    from eurogas_nexus.application.market_inputs import subscribe_inputs_changed

    subscribe_inputs_changed("strategy_tracks", _on_inputs_changed)


_subscribe()


def missed_signals(session: Session, principal: Any, hub: str, since: datetime,
                   ) -> list[dict[str, Any]]:
    """The caller's withdrawn (expired or stale) signals on ``hub`` since ``since``."""

    rows = (
        session.query(StrategyTrackEventRecord, StrategyTrackRecord.name,
                      StrategyTrackRecord.instruments)
        .join(StrategyTrackRecord,
              StrategyTrackRecord.track_id == StrategyTrackEventRecord.track_id)
        .filter(StrategyTrackRecord.owner_principal_id == principal.principal_id,
                StrategyTrackEventRecord.kind == "missed",
                StrategyTrackEventRecord.at_utc >= since)
        .order_by(StrategyTrackEventRecord.at_utc.desc())
        .limit(50)
        .all()
    )
    return [
        {"track": name, "at": event.payload.get("at"), "reason": event.payload.get("reason"),
         "advice": event.payload.get("advice")}
        for event, name, instruments in rows
        if any(str(key).split("|")[0] == hub for key in instruments or ())
    ]
