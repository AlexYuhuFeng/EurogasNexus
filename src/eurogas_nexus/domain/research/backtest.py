"""Strategy backtest computation — research-only."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class BacktestResultStatus(StrEnum):
    """Backtest outcome status."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    ERROR = "error"


@dataclass(frozen=True)
class BacktestInput:
    """Backtest input (strategy identity + trade PnL records).

    Attributes:
        strategy_name: Strategy display name.
        start_utc / end_utc: Backtest window (ISO).
        trades: List of ``{"pnl_eur": ..., "date": ...}`` records.
        capital_base_eur: Capital the strategy risked, used only as the
            denominator of ``max_drawdown_pct``. ``0.0`` (the default) means no
            capital base is declared; the percent is then reported only once the
            curve has been positive, where the running peak can serve as the
            base, and is ``None`` otherwise. The EUR amount is unaffected.
    """

    strategy_name: str
    start_utc: str = ""
    end_utc: str = ""
    trades: list[dict] = field(default_factory=list)  # [{"pnl_eur": ..., "date": ...}, ...]
    capital_base_eur: float = 0.0


@dataclass(frozen=True)
class BacktestOutput:
    """Backtest metrics output (research-only envelope).

    Attributes:
        strategy_name: Strategy display name.
        start_utc / end_utc: Backtest window.
        total_return_eur: Total PnL.
        trade_count / win_count / loss_count: Trade statistics.
        win_rate_pct: Win rate percent.
        sharpe_ratio: Simple Sharpe approximation, or None.
        max_drawdown_eur: Deepest peak-to-trough decline of the cumulative PnL
            curve, in EUR. Always available when trades were supplied.
        max_drawdown_pct: Deepest decline as a percent of the running peak, or
            None when no positive running peak was ever reached. See
            :func:`_drawdown_metrics`.
        status: COMPLETE / PARTIAL / ERROR.
        assumptions / missing_inputs / warnings: Transparency fields.
        source_references / lineage: Provenance.
        research_only / human_review_required: Always True.
        generated_at_utc: Generation time (ISO).
    """

    strategy_name: str
    start_utc: str
    end_utc: str
    total_return_eur: float = 0.0
    trade_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    win_rate_pct: float = 0.0
    sharpe_ratio: float | None = None
    max_drawdown_eur: float | None = None
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

    pnls = _chronological_pnls(input_.trades)
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

    # Drawdown of the cumulative PnL curve.
    max_dd_eur: float | None = None
    max_dd_pct: float | None = None
    if pnls:
        max_dd_eur, max_dd_pct, dd_note = _drawdown_metrics(
            pnls, input_.capital_base_eur
        )
        if dd_note is not None:
            warnings.append(dd_note)

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
        max_drawdown_eur=max_dd_eur,
        max_drawdown_pct=max_dd_pct,
        assumptions=[
            "Backtest uses the supplied historical operator/runtime input.",
            "Sharpe ratio is a simple approximation (no risk-free rate).",
            "Trades are ordered by their ISO date when one is supplied, otherwise by "
            "the order given; drawdown follows that cumulative PnL order.",
            "Max drawdown is measured from a zero starting equity, because no "
            "capital base is supplied with the trade list.",
            "Max drawdown percent divides by the running peak, so it is reported "
            "only once the cumulative PnL has been positive.",
        ],
        missing_inputs=missing,
        warnings=warnings,
        source_references=["operator-input"],
        lineage=["backtest-computation"],
        human_review_required=bool(missing),
    )


def _chronological_pnls(trades: list[dict]) -> list[float]:
    """Return trade PnLs ordered by their ISO date, keeping the given order otherwise.

    A drawdown is only meaningful along the curve's actual time order. Trades
    that carry no usable ``date`` keep their submitted position, so a caller that
    supplies no dates gets exactly the order it sent.
    """

    if not any(str(t.get("date") or "").strip() for t in trades):
        return [t.get("pnl_eur", 0.0) for t in trades]

    indexed = list(enumerate(trades))
    # Undated trades keep their submitted position by sorting on the original
    # index as the tie-breaker.
    indexed.sort(key=lambda pair: (str(pair[1].get("date") or "").strip(), pair[0]))
    return [trade.get("pnl_eur", 0.0) for _, trade in indexed]


def _drawdown_metrics(
    pnls: list[float], capital_base_eur: float = 0.0
) -> tuple[float, float | None, str | None]:
    """Return ``(max_drawdown_eur, max_drawdown_pct, note)`` for a cumulative PnL curve.

    The amount is the largest fall from a peak of the cumulative PnL curve,
    matching the strategy engine's definition (``domain/backtest._drawdown``,
    which likewise seeds its running peak at zero because the simulated state has
    no injected capital). The curve therefore starts flat at zero: a curve that
    only rises has no drawdown, while a curve that falls from a peak at or below
    zero still reports that fall -- the case the previous implementation
    suppressed, making a strategy that lost money on every trade report exactly
    ``0.0``.

    The percent needs a denominator that the trade list does not itself carry:

    * ``capital_base_eur > 0`` -- the caller declared the capital at risk, so the
      percent is ``decline / capital_base_eur`` and is available for any curve;
    * otherwise the running peak is used, which is only defined once that peak is
      positive. Before then the percent is ``None`` and ``note`` says why, rather
      than a fabricated ``0.0`` that reads as "never drew down".
    """

    peak = 0.0
    cumulative = 0.0
    max_dd_eur = 0.0
    max_dd_pct = 0.0
    seen_positive_peak = False
    has_capital_base = capital_base_eur > 0

    for pnl in pnls:
        cumulative += pnl
        if cumulative > peak:
            peak = cumulative
            seen_positive_peak = True
            continue
        decline = peak - cumulative
        if decline > max_dd_eur:
            max_dd_eur = decline
            if has_capital_base:
                max_dd_pct = decline / capital_base_eur
            elif peak > 0:
                max_dd_pct = decline / peak

    if has_capital_base or seen_positive_peak:
        return round(max_dd_eur, 2), round(max_dd_pct * 100, 2), None

    if max_dd_eur == 0.0:
        # Nothing fell, so an absent percentage claims nothing misleading.
        return 0.0, None, None
    return (
        round(max_dd_eur, 2),
        None,
        "Max drawdown percent is unavailable: no capital base was supplied and "
        "the cumulative PnL never reached a positive peak, so there is no "
        "denominator. Supply capital_base_eur, or read max_drawdown_eur.",
    )
