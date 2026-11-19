"""Intraday strategy evaluation and the paper book (fill model, gates, marks, contract change)."""

from datetime import UTC, datetime, timedelta

import pytest

from eurogas_nexus.domain.research.intraday_strategy import (
    IntradayRule,
    IntradayRuleError,
    Leg,
    LegQuote,
    assumptions,
    evaluate,
    rule_from_dict,
)

T0 = datetime(2026, 11, 19, 9, 0, tzinfo=UTC)
LEGS = [Leg("TTF", "within-day", 1.0), Leg("TTF", "day-ahead", -1.0)]
RULE = IntradayRule(window_minutes=30, min_points=20, entry_z=2.0, exit_z=0.5, size_mw=10,
                    min_top_size_mwh=24, max_quote_age_seconds=60, debounce_seconds=0)


def _book(at, wd_mid, da_mid=41.0, *, half=0.01, wd_size=480.0, da_size=480.0,
          delivery="2026-11-20T05:00:00+00:00", vwap=None, last_trade=None):
    def quote(mid, size):
        return LegQuote(round(mid - half, 6), round(mid + half, 6), size, size, at, delivery,
                        "EUR", "EEX", False, vwap, None, last_trade)

    return {"TTF|within-day": quote(wd_mid, wd_size), "TTF|day-ahead": quote(da_mid, da_size)}


def _warm(rule=RULE, n=30):
    state = None
    for i in range(n):
        at = T0 + timedelta(seconds=30 * i)
        result = evaluate(LEGS, rule, _book(at, 41.10 + (0.01 if i % 2 else -0.01)), state, at)
        state = result.state
    return state, T0 + timedelta(seconds=30 * n)


def test_signal_fill_at_the_quote_mark_and_close():
    state, at = _warm()
    # The WD premium jumps from 0.10 to 0.30: z far above 2 -> short the spread.
    spike = evaluate(LEGS, RULE, _book(at, 41.30), state, at)
    assert spike.signal_changed and spike.state["signal"] == "short"
    fill = next(e for e in spike.events if e["kind"] == "fill")
    # Selling the spread: sell WD at its bid (41.29), buy DA at its offer (41.01).
    assert fill["price"] == pytest.approx(41.29 - 41.01)
    assert fill["qty_mwh_per_day"] == pytest.approx(240.0)  # 10 MW × 24 h, inside 480 quoted
    assert fill["legs"][0] == {"leg": "TTF within-day", "side": "sell", "price": 41.29,
                               "quoted_size_mwh_per_day": 480.0, "source_system": "EEX"}
    # Marked at the price it could be bought back at (WD offer − DA bid = 0.31 − (−0.01)).
    assert spike.snapshot["unrealised"] == pytest.approx((0.28 - 0.32) * 240, abs=1e-6)
    # Back to the mean: |z| <= 0.5 -> buy back at the offer side of the spread.
    at2 = at + timedelta(seconds=30)
    back = evaluate(LEGS, RULE, _book(at2, 41.10), spike.state, at2)
    close = next(e for e in back.events if e["kind"] == "fill")
    assert close["action"] == "close"
    assert close["price"] == pytest.approx(41.11 - 40.99)
    assert close["pnl_per_mwh"] == pytest.approx(0.28 - 0.12)
    assert close["pnl"] == pytest.approx(0.16 * 240)
    assert back.snapshot["realised"] == pytest.approx(38.4)
    assert back.snapshot["closed_trades"] == 1 and back.snapshot["winning_trades"] == 1


def test_size_beyond_the_screen_is_not_filled():
    state, at = _warm()
    thin = evaluate(LEGS, RULE, _book(at, 41.30, wd_size=100.0, da_size=480.0), state, at)
    # 100 MWh/d on the WD bid is below the 24 MWh gate? no: gate passes; fill is partial.
    fill = next(e for e in thin.events if e["kind"] == "fill")
    assert fill["qty_mwh_per_day"] == pytest.approx(100.0) and fill["partial"] is True


def test_gates_stop_a_signal_on_a_quote_with_no_size_or_an_old_quote():
    state, at = _warm()
    empty = evaluate(LEGS, RULE, _book(at, 41.30, wd_size=0.0), state, at)
    assert not empty.signal_changed and empty.state["signal"] == "flat"
    assert any("no size" in reason for reason in empty.state["gated"])
    old = evaluate(LEGS, RULE, _book(at - timedelta(seconds=90), 41.30), state, at)
    assert any("90s old" in reason for reason in old.state["gated"])
    quiet = IntradayRule(**{**RULE.as_dict(), "max_no_trade_minutes": 5})
    no_trades = evaluate(LEGS, quiet, _book(at, 41.30, last_trade=at - timedelta(minutes=9)),
                         state, at)
    assert any("no trade in 5 min" in reason for reason in no_trades.state["gated"])


def test_no_edge_after_crossing_a_wide_market():
    state, at = _warm()
    wide = evaluate(LEGS, RULE, _book(at, 41.30, half=0.15), state, at)
    assert wide.state["signal"] == "no_edge"
    assert not any(e["kind"] == "fill" for e in wide.events)


def test_a_contract_change_closes_at_the_old_contracts_last_price():
    state, at = _warm()
    spike = evaluate(LEGS, RULE, _book(at, 41.30), state, at)
    at2 = at + timedelta(seconds=30)
    rolled = evaluate(LEGS, RULE, _book(at2, 41.32, delivery="2026-11-21T05:00:00+00:00"),
                      spike.state, at2)
    close = next(e for e in rolled.events if e["kind"] == "fill")
    assert close["reason"] == "contract change"
    assert close["price"] == pytest.approx(0.32)  # the last buy-back price before the roll


def test_vwap_reversion_needs_vwap_on_every_leg():
    rule = IntradayRule(**{**RULE.as_dict(), "kind": "vwap_reversion"})
    state, at = _warm(rule)
    result = evaluate(LEGS, rule, _book(at, 41.30), state, at)
    assert "no session VWAP on every leg" in result.state["gated"]
    with_vwap = evaluate(LEGS, rule, _book(at, 41.30, vwap=41.05), state, at)
    # Anchor = VWAP(WD) − VWAP(DA) = 0: the spread at 0.30 is far above it.
    assert with_vwap.snapshot["vwap_anchor"] == pytest.approx(0.0)
    assert with_vwap.state["signal"] == "short"


def test_rule_validation_and_assumptions():
    with pytest.raises(IntradayRuleError):
        rule_from_dict({"kind": "martingale"})
    with pytest.raises(IntradayRuleError):
        rule_from_dict({"order_type": "market"})
    line = assumptions(RULE)
    assert "Paper only" in line and "buy at the offer, sell at the bid" in line
