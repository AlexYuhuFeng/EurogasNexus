"""Backtest computation tests."""

from eurogas_nexus.domain.research.backtest import BacktestInput, compute_backtest


def _run(trades: list[dict], **kwargs):
    return compute_backtest(BacktestInput(
        strategy_name=kwargs.pop("strategy_name", "Test"),
        trades=trades,
        **kwargs,
    ))


def test_backtest_computes_metrics() -> None:
    result = compute_backtest(BacktestInput(
        strategy_name="Winter spread", start_utc="2025-10-01", end_utc="2026-03-31",
        trades=[
            {"pnl_eur": 5000.0, "date": "2025-10-15"},
            {"pnl_eur": -2000.0, "date": "2025-11-01"},
            {"pnl_eur": 8000.0, "date": "2025-12-10"},
            {"pnl_eur": 3000.0, "date": "2026-01-20"},
        ],
    ))
    assert result.total_return_eur == 14000.0
    assert result.trade_count == 4
    assert result.win_count == 3
    assert result.loss_count == 1
    assert result.win_rate_pct == 75.0


def test_backtest_empty_trades_warns() -> None:
    result = compute_backtest(BacktestInput(strategy_name="Test"))
    assert result.trade_count == 0
    assert len(result.warnings) >= 1
    assert result.max_drawdown_eur is None
    assert result.max_drawdown_pct is None


def test_backtest_research_metadata() -> None:
    result = compute_backtest(BacktestInput(strategy_name="Test"))
    assert result.research_only is True
    assert "backtest-computation" in result.lineage


# --- Drawdown regression coverage -------------------------------------------
#
# Golden values for the defect this suite previously missed: the old code only
# accumulated ``decline`` while ``peak > 0``, so a curve that fell from a peak at
# or below zero contributed nothing and reported a drawdown of exactly 0.0. A
# strategy that lost money on every trade therefore looked identical to one that
# never drew down, and ``tests/domain/research/test_backtest.py`` asserted
# neither drawdown field.


def test_drawdown_reports_amount_for_all_losing_curve() -> None:
    """A curve that only ever falls must report its real decline, not 0.0."""

    result = _run([{"pnl_eur": -100.0}, {"pnl_eur": -50.0}, {"pnl_eur": -80.0}])
    # Curve: 0 -> -100 -> -150 -> -230. Falls 230 from the zero starting peak.
    assert result.max_drawdown_eur == 230.0
    # No capital base and no positive peak -> no denominator for a percentage.
    assert result.max_drawdown_pct is None
    assert any("capital_base_eur" in w for w in result.warnings)


def test_drawdown_reports_amount_for_single_losing_trade() -> None:
    result = _run([{"pnl_eur": -100.0}])
    assert result.max_drawdown_eur == 100.0
    assert result.max_drawdown_pct is None


def test_drawdown_reports_percent_when_capital_base_is_declared() -> None:
    """A declared capital base makes the percentage available on any curve."""

    result = _run(
        [{"pnl_eur": -100.0}, {"pnl_eur": -50.0}, {"pnl_eur": -80.0}],
        capital_base_eur=1000.0,
    )
    assert result.max_drawdown_eur == 230.0
    assert result.max_drawdown_pct == 23.0
    assert not any("capital_base_eur" in w for w in result.warnings)


def test_drawdown_amount_and_percent_on_classic_peak_then_trough() -> None:
    """Curve: 0 -> +100 -> +40 -> +60: peak 100, trough 40, decline 60, 60%."""

    result = _run([{"pnl_eur": 100.0}, {"pnl_eur": -60.0}, {"pnl_eur": 20.0}])
    assert result.max_drawdown_eur == 60.0
    assert result.max_drawdown_pct == 60.0


def test_drawdown_percent_uses_the_deepest_decline_not_the_last() -> None:
    """Curve: 0 -> -50 -> +100 -> +20: peak 100, deepest decline 80, 80%."""

    result = _run([{"pnl_eur": -50.0}, {"pnl_eur": 150.0}, {"pnl_eur": -80.0}])
    assert result.max_drawdown_eur == 80.0
    assert result.max_drawdown_pct == 80.0


def test_drawdown_is_zero_for_monotonically_rising_curve() -> None:
    result = _run([{"pnl_eur": 100.0}, {"pnl_eur": 50.0}, {"pnl_eur": 80.0}])
    assert result.max_drawdown_eur == 0.0
    assert result.max_drawdown_pct == 0.0
    # Nothing fell, so no percentage warning is warranted.
    assert not any("capital_base_eur" in w for w in result.warnings)


def test_drawdown_measures_the_deepest_point_below_the_starting_equity() -> None:
    """The running peak is seeded at zero, so a curve that sinks reports that fall.

    Curve: 0 -> -100 -> -150 -> -120. The deepest point is 150 below the starting
    equity, so the drawdown is 150 -- not the 50 fall from the -100 mark and not
    the 120 the run ends down. The peak is a running maximum, so a later, lower
    mark never replaces the zero start.
    """

    result = _run([
        {"pnl_eur": -100.0},
        {"pnl_eur": -50.0},
        {"pnl_eur": 30.0},
    ])
    assert result.max_drawdown_eur == 150.0
    assert result.max_drawdown_pct is None  # no capital base, no positive peak
    assert result.total_return_eur == -120.0


def test_drawdown_follows_dates_not_submission_order() -> None:
    """Out-of-order submissions are replayed in chronological order."""

    chronological = _run([
        {"pnl_eur": 100.0, "date": "2026-01-01"},
        {"pnl_eur": -50.0, "date": "2026-02-01"},
    ])
    # Curve: 0 -> +100 -> +50. Falls 50 from a 100 peak.
    assert chronological.max_drawdown_eur == 50.0
    assert chronological.max_drawdown_pct == 50.0

    reversed_dates = _run([
        {"pnl_eur": 100.0, "date": "2026-02-01"},
        {"pnl_eur": -50.0, "date": "2026-01-01"},
    ])
    # Curve: 0 -> -50 -> +50, and the first trade falls 50 from the zero peak;
    # a positive peak is reached later, so the percent is available.
    assert reversed_dates.max_drawdown_eur == 50.0


def test_drawdown_keeps_submission_order_without_dates() -> None:
    result = _run([{"pnl_eur": 100.0}, {"pnl_eur": -50.0}])
    # Curve: 0 -> +100 -> +50. Falls 50 from a 100 peak.
    assert result.max_drawdown_eur == 50.0
    assert result.max_drawdown_pct == 50.0
