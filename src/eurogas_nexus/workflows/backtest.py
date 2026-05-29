"""Strategy backtest computation — research-only."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class BacktestResultStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    ERROR = "error"


@dataclass(frozen=True)
class BacktestInput:
    strategy_name: str
    start_utc: str = ""
    end_utc: str = ""
    trades: list[dict] = field(default_factory=list)  # [{"pnl_eur": ..., "date": ...}, ...]


@dataclass(frozen=True)
class BacktestOutput:
    strategy_name: str
    start_utc: str
    end_utc: str
    total_return_eur: float = 0.0
    trade_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    win_rate_pct: float = 0.0
    sharpe_ratio: float | None = None
    max_drawdown_pct: float | None = None
    status: BacktestResultStatus = BacktestResultStatus.COMPLETE
    assumptions: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    source_references: list[str] = field(default_factory=list)
    lineage: list[str] = field(default_factory=list)
    research_only: bool = True
    human_review_required: bool = True
    generated_at_utc: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )


def compute_backtest(input_: BacktestInput) -> BacktestOutput:
    """Compute backtest metrics from a list of trade PnL records."""

    missing: list[str] = []
    warnings: list[str] = []

    if not input_.strategy_name:
        missing.append("strategy_name is required.")
    if not input_.trades:
        warnings.append("No trades provided; all metrics are zero.")

    pnls = [t.get("pnl_eur", 0.0) for t in input_.trades]
    total_return = sum(pnls)
    trade_count = len(pnls)
    win_count = sum(1 for p in pnls if p > 0)
    loss_count = sum(1 for p in pnls if p < 0)
    win_rate = (win_count / trade_count * 100) if trade_count > 0 else 0.0

    # Simple Sharpe approximation
    sharpe = None
    if trade_count > 1 and total_return != 0:
        mean = total_return / trade_count
        import math
        sq_diffs = sum((p - mean) ** 2 for p in pnls)
        variance = sq_diffs / (trade_count - 1) if trade_count > 1 else 0.0
        sharpe = mean / math.sqrt(variance) if variance > 0 else None

    # Simple max drawdown approximation
    max_dd = None
    if pnls:
        cumulative = 0.0
        peak = 0.0
        max_dd_pct = 0.0
        for p in pnls:
            cumulative += p
            if cumulative > peak:
                peak = cumulative
            dd = (peak - cumulative) / peak if peak > 0 else 0.0
            max_dd_pct = max(max_dd_pct, dd)
        max_dd = round(max_dd_pct * 100, 2)

    return BacktestOutput(
        strategy_name=input_.strategy_name,
        start_utc=input_.start_utc,
        end_utc=input_.end_utc,
        total_return_eur=round(total_return, 2),
        trade_count=trade_count,
        win_count=win_count,
        loss_count=loss_count,
        win_rate_pct=round(win_rate, 2),
        sharpe_ratio=round(sharpe, 4) if sharpe is not None else None,
        max_drawdown_pct=max_dd,
        assumptions=[
            "Backtest uses historical synthetic data only.",
            "Sharpe ratio is a simple approximation (no risk-free rate).",
            "Max drawdown is computed from cumulative PnL.",
        ],
        missing_inputs=missing,
        warnings=warnings,
        source_references=["synthetic-input"],
        lineage=["backtest-computation"],
        human_review_required=bool(missing),
    )
