"""Research budget and overfitting controls (CR-15)."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, Field

DEFAULT_RESEARCH_BUDGET = {
    "max_hypotheses": 3,
    "max_parameter_variants": 8,
    "max_backtest_runs": 5,
    "max_llm_calls": 12,
    "time_budget_seconds": 900,
    "token_budget": 100_000,
}


class ResearchBudget(BaseModel):
    """Bounded search budget; prevents automated data mining."""

    budget_id: str
    agent_run_id: str | None = None
    max_hypotheses: int = Field(default=3, ge=1, le=50)
    max_parameter_variants: int = Field(default=8, ge=1, le=200)
    max_backtest_runs: int = Field(default=5, ge=1, le=50)
    max_llm_calls: int = Field(default=12, ge=0, le=100)
    time_budget_seconds: int = Field(default=900, ge=10, le=86_400)
    token_budget: int = Field(default=100_000, ge=0, le=10_000_000)
    hypotheses_used: int = 0
    parameter_variants_used: int = 0
    backtest_runs_used: int = 0
    llm_calls_used: int = 0
    tokens_used: int = 0
    selection_criterion: str = "highest_validated_risk_adjusted_result"
    final_holdout_period: dict = Field(default_factory=dict)
    final_holdout_inspections: int = 0
    max_final_holdout_inspections: int = Field(default=1, ge=1, le=5)
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BudgetDecision(BaseModel):
    allowed: bool
    reason: str = ""
    remaining: dict = Field(default_factory=dict)


class BudgetExceededError(ValueError):
    """A bounded research budget was exhausted."""


def enforce_research_budget(
    budget: ResearchBudget,
    *,
    hypotheses_delta: int = 0,
    parameter_variants_delta: int = 0,
    backtest_runs_delta: int = 0,
    llm_calls_delta: int = 0,
    tokens_delta: int = 0,
    final_holdout_inspection: bool = False,
) -> BudgetDecision:
    """Return an explicit decision and mutate the budget when allowed."""

    if final_holdout_inspection and (
        budget.final_holdout_inspections >= budget.max_final_holdout_inspections
    ):
        return BudgetDecision(
            allowed=False,
            reason="final_holdout_inspection_budget_exhausted",
            remaining=_remaining(budget),
        )
    checks = [
        (budget.hypotheses_used + hypotheses_delta, budget.max_hypotheses, "hypotheses"),
        (
            budget.parameter_variants_used + parameter_variants_delta,
            budget.max_parameter_variants,
            "parameter_variants",
        ),
        (
            budget.backtest_runs_used + backtest_runs_delta,
            budget.max_backtest_runs,
            "backtest_runs",
        ),
        (budget.llm_calls_used + llm_calls_delta, budget.max_llm_calls, "llm_calls"),
        (budget.tokens_used + tokens_delta, budget.token_budget, "tokens"),
    ]
    for proposed, maximum, name in checks:
        if proposed > maximum:
            return BudgetDecision(
                allowed=False,
                reason=f"{name}_budget_exhausted",
                remaining=_remaining(budget),
            )
    budget.hypotheses_used += hypotheses_delta
    budget.parameter_variants_used += parameter_variants_delta
    budget.backtest_runs_used += backtest_runs_delta
    budget.llm_calls_used += llm_calls_delta
    budget.tokens_used += tokens_delta
    if final_holdout_inspection:
        budget.final_holdout_inspections += 1
    return BudgetDecision(allowed=True, reason="budget_allowed", remaining=_remaining(budget))


def _remaining(budget: ResearchBudget) -> dict:
    return {
        "hypotheses": budget.max_hypotheses - budget.hypotheses_used,
        "parameter_variants": budget.max_parameter_variants - budget.parameter_variants_used,
        "backtest_runs": budget.max_backtest_runs - budget.backtest_runs_used,
        "llm_calls": budget.max_llm_calls - budget.llm_calls_used,
        "tokens": budget.token_budget - budget.tokens_used,
        "final_holdout_inspections": (
            budget.max_final_holdout_inspections - budget.final_holdout_inspections
        ),
    }
