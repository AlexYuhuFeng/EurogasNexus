"""SDK client for strategy-lab decision-support APIs."""

from __future__ import annotations

import httpx
from pydantic import BaseModel, Field


class StrategyAllocationTarget(BaseModel):
    market_bucket: str
    target_allocation_pct: float
    target_quantity_mwh_per_day: float
    reference_price_gbp_mwh: float | None = None
    expected_margin_gbp_mwh: float | None = None
    rationale: list[str] = Field(default_factory=list)


class StrategyLabResult(BaseModel):
    run_id: str
    strategy_id: str
    strategy_name: str
    run_mode: str
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
    response = httpx.post(
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
    params = {"limit": str(limit)}
    if strategy_id:
        params["strategy_id"] = strategy_id
    if run_mode:
        params["run_mode"] = run_mode
    response = httpx.get(f"{base_url}/api/strategy-lab/runs", params=params, timeout=15)
    response.raise_for_status()
    return [StrategyRunDTO(**row) for row in response.json()["data"]]


def get_strategy_run(base_url: str, run_id: str) -> StrategyRunDTO:
    response = httpx.get(f"{base_url}/api/strategy-lab/runs/{run_id}", timeout=15)
    response.raise_for_status()
    return StrategyRunDTO(**response.json()["data"])


def strategy_summary(
    base_url: str,
    *,
    strategy_id: str | None = None,
    run_mode: str | None = None,
) -> StrategySummaryDTO:
    params = {}
    if strategy_id:
        params["strategy_id"] = strategy_id
    if run_mode:
        params["run_mode"] = run_mode
    response = httpx.get(f"{base_url}/api/strategy-lab/summary", params=params, timeout=15)
    response.raise_for_status()
    return StrategySummaryDTO(**response.json()["data"])
