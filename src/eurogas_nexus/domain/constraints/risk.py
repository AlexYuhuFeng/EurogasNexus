"""Strategy risk constraints (stop-loss and allocation limits)."""

from __future__ import annotations


def stop_loss_triggered(
    cumulative_pnl_gbp: float,
    stop_shadow_run_loss_gbp: float | None,
) -> bool:
    """Return True when cumulative paper PnL breaches the shadow-run stop-loss.

    The threshold is a positive loss amount; it triggers when the cumulative PnL
    is at or below the negative of that amount.
    """

    if stop_shadow_run_loss_gbp is None:
        return False
    return cumulative_pnl_gbp <= -abs(stop_shadow_run_loss_gbp)


def ocm_day_split(
    weighted_score: float,
    max_ocm_allocation_pct: float,
    min_day_ahead_allocation_pct: float,
) -> tuple[float, float]:
    """Derive OCM versus day-ahead allocation percentages from a weighted score.

    OCM starts at 50% and moves by up to 30% with the score, then is clamped to
    the configured maximum OCM and minimum day-ahead floors.
    """

    ocm_pct = 50.0 + weighted_score * 30.0
    ocm_pct = min(max(ocm_pct, 0.0), max_ocm_allocation_pct)
    day_pct = max(100.0 - ocm_pct, min_day_ahead_allocation_pct)
    if day_pct + ocm_pct > 100:
        ocm_pct = 100.0 - day_pct
    return ocm_pct, day_pct
