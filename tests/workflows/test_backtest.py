"""Backtest computation tests."""

from eurogas_nexus.workflows.backtest import BacktestInput, compute_backtest


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


def test_backtest_research_metadata() -> None:
    result = compute_backtest(BacktestInput(strategy_name="Test"))
    assert result.research_only is True
    assert "backtest-computation" in result.lineage
