"""Strategy risk constraints (stop-loss and allocation limits).

风险约束的单一实现：止损判定与 OCM/日前分配比例推导，任何策略评估
路径都必须复用本模块，避免各端自行实现不一致的风险规则。
"""

from __future__ import annotations


def stop_loss_triggered(
    cumulative_pnl_gbp: float,
    stop_shadow_run_loss_gbp: float | None,
) -> bool:
    """Return True when cumulative paper PnL breaches the shadow-run stop-loss.

    判定影子运行是否触发止损。

    The threshold is a positive loss amount; it triggers when the cumulative PnL
    is at or below the negative of that amount.

    Args:
        cumulative_pnl_gbp: Cumulative paper PnL of the shadow run.
        stop_shadow_run_loss_gbp: Stop-loss threshold as a positive amount,
            or None when no stop-loss is configured.

    Returns:
        True when the PnL breaches the threshold; False when no threshold
        is configured (no stop-loss policy).
    """

    if stop_shadow_run_loss_gbp is None:
        return False
    # 阈值取绝对值：防止调用方误传负数导致比较方向反转。
    return cumulative_pnl_gbp <= -abs(stop_shadow_run_loss_gbp)


def ocm_day_split(
    weighted_score: float,
    max_ocm_allocation_pct: float,
    min_day_ahead_allocation_pct: float,
) -> tuple[float, float]:
    """Derive OCM versus day-ahead allocation percentages from a weighted score.

    由加权评分推导 OCM 与日前分配的百分比组合。

    OCM starts at 50% and moves by up to 30% with the score, then is clamped to
    the configured maximum OCM and minimum day-ahead floors.

    Args:
        weighted_score: Weighted signal score in ``[-1, 1]`` (positive
            favours OCM).
        max_ocm_allocation_pct: Upper clamp for the OCM share (percent).
        min_day_ahead_allocation_pct: Lower floor for the day-ahead share
            (percent).

    Returns:
        Tuple ``(ocm_pct, day_pct)`` summing to at most 100; the day-ahead
        floor wins when both constraints cannot be satisfied.
    """

    # 基准 50%，评分每 +1 至多上浮 30%；随后双向钳制。
    ocm_pct = 50.0 + weighted_score * 30.0
    ocm_pct = min(max(ocm_pct, 0.0), max_ocm_allocation_pct)
    day_pct = max(100.0 - ocm_pct, min_day_ahead_allocation_pct)
    if day_pct + ocm_pct > 100:
        # 日前下限优先：必要时回退 OCM 份额，保证日前敞口不被压缩。
        ocm_pct = 100.0 - day_pct
    return ocm_pct, day_pct
