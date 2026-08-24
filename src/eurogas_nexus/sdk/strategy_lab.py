"""SDK client for strategy-lab decision-support APIs."""

from __future__ import annotations

from pydantic import BaseModel, Field

from eurogas_nexus.sdk import _http


class StrategyAllocationTarget(BaseModel):
    """Target allocation for one market bucket within a strategy run.

    Attributes:
        market_bucket: Market segment the target applies to.
        target_allocation_pct: Target share of the portfolio in percent.
        target_quantity_mwh_per_day: Target volume in MWh per day.
        reference_price_gbp_mwh: Reference price in GBP/MWh, when available.
        expected_margin_gbp_mwh: Expected margin in GBP/MWh, when available.
        rationale: Reasons for this allocation target.
    """

    market_bucket: str
    target_allocation_pct: float
    target_quantity_mwh_per_day: float
    reference_price_gbp_mwh: float | None = None
    expected_margin_gbp_mwh: float | None = None
    rationale: list[str] = Field(default_factory=list)


class StrategyLabResult(BaseModel):
    """Evaluation result of one strategy-lab run.

    Attributes:
        run_id: Identifier of the strategy run.
        strategy_id: Identifier of the evaluated strategy.
        strategy_name: Display name of the evaluated strategy.
        run_mode: Run mode (e.g. ``BACKTEST``/``PAPER``).
        status: Run status (e.g. ``COMPLETED``/``PENDING``).
        weighted_score: Weighted score of the run.
        day_ahead_average_gbp_mwh: Average day-ahead price in GBP/MWh.
        intraday_average_gbp_mwh: Average intraday price in GBP/MWh.
        intraday_vs_day_ahead_spread_gbp_mwh: Average intraday-vs-day-ahead
            spread in GBP/MWh.
        allocation_targets: Target allocations per market bucket.
        missing_inputs: Inputs that were absent during the evaluation.
        warnings: Human-readable evaluation warnings.
        source_refs: References to the source data used.
        candidate_action_for_review: Candidate action proposed for review.
        paper_pnl_gbp: Paper PnL of the run in GBP.
        cumulative_pnl_gbp: Cumulative paper PnL in GBP.
        hit: True when the run hit its target outcome.
        research_only: True when the payload is a research-only envelope.
        human_review_required: True when output needs human review before use.
    """

    run_id: str
    strategy_id: str
    strategy_name: str
    run_mode: str
    # 状态为字符串而非枚举：运行状态由后端定义并会扩展（如新增 PENDING），
    # 枚举会让旧 SDK 解析新状态失败，字符串保持向前兼容。
    status: str
    weighted_score: float
    day_ahead_average_gbp_mwh: float | None = None
    intraday_average_gbp_mwh: float | None = None
    intraday_vs_day_ahead_spread_gbp_mwh: float | None = None
    allocation_targets: list[StrategyAllocationTarget] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    candidate_action_for_review: str
    paper_pnl_gbp: float = 0.0
    cumulative_pnl_gbp: float = 0.0
    hit: bool = False
    research_only: bool
    human_review_required: bool


class StrategyRunDTO(BaseModel):
    """One historical strategy run as stored by the backend.

    Attributes:
        run_id: Identifier of the strategy run.
        strategy_id: Identifier of the evaluated strategy.
        run_mode: Run mode (e.g. backtest/paper).
        status: Run status (e.g. ``COMPLETED``/``PENDING``).
        started_at_utc: UTC timestamp when the run started.
        finished_at_utc: UTC timestamp when the run finished; None while running.
        paper_pnl_gbp: Paper PnL of the run in GBP.
        cumulative_pnl_gbp: Cumulative paper PnL in GBP.
        hit: Whether the run hit its target outcome.
        weighted_score: Weighted score of the run.
        allocation_targets: Raw allocation-target records.
        missing_inputs: Inputs that were absent during the run.
        warnings: Human-readable run warnings.
        source_refs: References to the source data used.
        research_only: True when the payload is a research-only envelope.
        human_review_required: True when output needs human review before use.
    """

    run_id: str
    strategy_id: str
    run_mode: str
    status: str
    started_at_utc: str
    finished_at_utc: str | None = None
    paper_pnl_gbp: float | None = None
    cumulative_pnl_gbp: float | None = None
    hit: bool | None = None
    weighted_score: float | None = None
    allocation_targets: list[dict] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    research_only: bool
    human_review_required: bool


class StrategySummaryDTO(BaseModel):
    """Aggregate performance summary across runs of a strategy.

    Attributes:
        strategy_id: Identifier of the summarized strategy.
        run_mode: Run mode the summary is restricted to, when filtered.
        run_count: Number of runs included in the summary.
        total_paper_pnl_gbp: Sum of paper PnL across runs in GBP.
        cumulative_pnl_gbp: Cumulative paper PnL in GBP.
        hit_rate: Share of runs that hit their target outcome.
        max_drawdown_gbp: Worst peak-to-trough paper PnL in GBP.
        first_started_at_utc: UTC timestamp of the earliest run.
        last_started_at_utc: UTC timestamp of the latest run.
        latest_status: Status of the most recent run.
    """

    strategy_id: str | None = None
    run_mode: str | None = None
    run_count: int
    total_paper_pnl_gbp: float
    cumulative_pnl_gbp: float
    hit_rate: float
    max_drawdown_gbp: float
    first_started_at_utc: str | None = None
    last_started_at_utc: str | None = None
    latest_status: str | None = None


def evaluate_strategy_lab(base_url: str, **kwargs) -> StrategyLabResult:
    """Evaluate a strategy in the strategy lab.

    Args:
        base_url: Base URL of the backend server.
        **kwargs: Strategy and market inputs forwarded to the evaluate API.

    Returns:
        Evaluation result with score, prices and allocation targets.
    """

    response = _http.post(
        f"{base_url}/api/strategy-lab/evaluate",
        json=kwargs,
        timeout=15,
    )
    response.raise_for_status()
    return StrategyLabResult(**response.json()["data"])


def list_strategy_runs(
    base_url: str,
    *,
    strategy_id: str | None = None,
    run_mode: str | None = None,
    limit: int = 100,
) -> list[StrategyRunDTO]:
    """List historical strategy runs, optionally filtered.

    Args:
        base_url: Base URL of the backend server.
        strategy_id: Only runs of this strategy.
        run_mode: Only runs in this mode.
        limit: Maximum number of runs to return.

    Returns:
        List of strategy-run records.
    """

    params = {"limit": str(limit)}
    if strategy_id:
        params["strategy_id"] = strategy_id
    if run_mode:
        params["run_mode"] = run_mode
    response = _http.get(f"{base_url}/api/strategy-lab/runs", params=params, timeout=15)
    response.raise_for_status()
    return [StrategyRunDTO(**row) for row in response.json()["data"]]


def get_strategy_run(base_url: str, run_id: str) -> StrategyRunDTO:
    """Fetch one strategy run by its identifier.

    Args:
        base_url: Base URL of the backend server.
        run_id: Identifier of the run to fetch.

    Returns:
        The requested strategy-run record.
    """

    response = _http.get(f"{base_url}/api/strategy-lab/runs/{run_id}", timeout=15)
    response.raise_for_status()
    return StrategyRunDTO(**response.json()["data"])


def strategy_summary(
    base_url: str,
    *,
    strategy_id: str | None = None,
    run_mode: str | None = None,
) -> StrategySummaryDTO:
    """Fetch an aggregated performance summary for a strategy.

    Args:
        base_url: Base URL of the backend server.
        strategy_id: Only include runs of this strategy.
        run_mode: Only include runs in this mode.

    Returns:
        Aggregated performance summary across the matching runs.
    """

    params = {}
    if strategy_id:
        params["strategy_id"] = strategy_id
    if run_mode:
        params["run_mode"] = run_mode
    response = _http.get(f"{base_url}/api/strategy-lab/summary", params=params, timeout=15)
    response.raise_for_status()
    return StrategySummaryDTO(**response.json()["data"])
