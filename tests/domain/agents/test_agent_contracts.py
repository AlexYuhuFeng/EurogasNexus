"""CR-15 domain contract tests: plans, budgets, challenger."""

from __future__ import annotations

from eurogas_nexus.domain.agents.budget import (
    ResearchBudget,
    enforce_research_budget,
)
from eurogas_nexus.domain.agents.challenge import (
    ChallengeResult,
    challenge_backtest_result,
)
from eurogas_nexus.domain.agents.research_plan import (
    AnalysisRequirement,
    ResearchPlan,
    deterministic_plan,
    validate_research_plan,
)


def _plan(**updates) -> ResearchPlan:
    payload = deterministic_plan(
        "Does NBP trade at a premium to TTF?", agent_run_id="agent-run-test"
    )
    return payload.model_copy(update=updates)


def _catalog() -> dict:
    return {
        "NBP_TTF_DA_SPREAD": {
            "output_unit": "EUR/MWh",
            "feature_version": "v1",
        }
    }


def test_research_plan_validation_happy_path() -> None:
    plan = _plan()
    result = validate_research_plan(
        plan,
        known_entities=set(plan.entities),
        available_series={item.series_id: {"history_days": 60} for item in plan.required_evidence},
    )
    assert result.ok is True
    assert result.supported_analyses == ["spread-distribution", "rolling-volatility"]


def test_research_plan_validation_rejects_unknown_entity() -> None:
    plan = _plan(entities=["ent:market_hub:ATLANTIS"])
    result = validate_research_plan(plan, known_entities=set())
    assert not result.ok
    assert "ENTITY_NOT_FOUND" in result.blockers


def test_research_plan_validation_rejects_unavailable_data() -> None:
    plan = _plan()
    result = validate_research_plan(plan, known_entities=set(plan.entities), available_series={})
    assert not result.ok
    assert "SERIES_UNAVAILABLE" in result.blockers


def test_research_plan_validation_rejects_insufficient_history() -> None:
    plan = _plan()
    result = validate_research_plan(
        plan,
        known_entities=set(plan.entities),
        available_series={item.series_id: {"history_days": 3} for item in plan.required_evidence},
        min_history_days=14,
    )
    assert not result.ok
    assert "INSUFFICIENT_HISTORY" in result.blockers


def test_research_plan_validation_rejects_temporal_insufficient() -> None:
    plan = _plan()
    series = {
        item.series_id: {"history_days": 60, "temporal_integrity": "TEMPORAL_INSUFFICIENT"}
        for item in plan.required_evidence
    }
    result = validate_research_plan(
        plan, known_entities=set(plan.entities), available_series=series
    )
    assert "TEMPORAL_PROVENANCE_INSUFFICIENT" in result.blockers


def test_research_plan_validation_rejects_missing_entitlement() -> None:
    plan = _plan()
    series = {
        item.series_id: {"history_days": 60, "source_family": "ICIS"}
        for item in plan.required_evidence
    }
    result = validate_research_plan(
        plan,
        known_entities=set(plan.entities),
        available_series=series,
        entitled_source_families={"EEX"},
    )
    assert "ENTITLEMENT_MISSING" in result.blockers


def test_research_plan_validation_rejects_invalid_analysis() -> None:
    plan = _plan(analyses=[AnalysisRequirement(analysis_id="bad", analysis_type="unsupported")])
    result = validate_research_plan(
        plan,
        known_entities=set(plan.entities),
        available_series={},
    )
    assert "INVALID_ANALYSIS" in result.blockers


def test_budget_tracks_hypotheses_variants_and_backtests() -> None:
    budget = ResearchBudget(budget_id="budget-1")
    decision = enforce_research_budget(
        budget,
        hypotheses_delta=1,
        parameter_variants_delta=8,
        backtest_runs_delta=5,
        llm_calls_delta=2,
    )
    assert decision.allowed is True
    assert budget.hypotheses_used == 1
    assert budget.backtest_runs_used == 5
    blocked = enforce_research_budget(budget, backtest_runs_delta=1)
    assert blocked.allowed is False
    assert blocked.reason == "backtest_runs_budget_exhausted"


def test_budget_limits_final_holdout_inspections() -> None:
    budget = ResearchBudget(budget_id="budget-2", max_final_holdout_inspections=1)
    assert enforce_research_budget(budget, final_holdout_inspection=True).allowed
    assert not enforce_research_budget(budget, final_holdout_inspection=True).allowed


def test_challenger_reports_insufficient_sample_and_unmodeled_costs() -> None:
    report = challenge_backtest_result(
        challenge_report_id="challenge-1",
        strategy_version_id="sv-1",
        backtest_run_id="run-1",
        metrics={"net_indicative_pnl_gbp": 2.0},
        sample_size=12,
        cost_policy="EXPLICIT_ZERO_UNMODELED",
    )
    assert report.overall_result in {
        ChallengeResult.FAIL,
        ChallengeResult.INSUFFICIENT_EVIDENCE,
        ChallengeResult.CONCERN,
    }
    assert report.items
    assert report.recommended_follow_up


def test_challenger_is_structured_and_evidence_based() -> None:
    report = challenge_backtest_result(
        challenge_report_id="challenge-2",
        strategy_version_id=None,
        backtest_run_id=None,
        metrics={"net_indicative_pnl_gbp": 100.0, "max_drawdown_gbp": -10.0},
        sample_size=200,
        warnings=[],
        missing_inputs=[],
    )
    assert report.overall_result == ChallengeResult.PASS
    assert report.items[0].evidence


def test_challenger_fails_on_missing_inputs() -> None:
    report = challenge_backtest_result(
        challenge_report_id="challenge-3",
        strategy_version_id=None,
        backtest_run_id=None,
        metrics={},
        missing_inputs=["market.price.NBP.DAY_AHEAD"],
    )
    assert report.overall_result == ChallengeResult.FAIL
