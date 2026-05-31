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
    research_only: bool
    human_review_required: bool


def evaluate_strategy_lab(base_url: str, **kwargs) -> StrategyLabResult:
    response = httpx.post(
        f"{base_url}/api/v1/strategy-lab/evaluate",
        json=kwargs,
        timeout=15,
    )
    response.raise_for_status()
    return StrategyLabResult(**response.json()["data"])
