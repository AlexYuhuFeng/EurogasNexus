"""Workflow model contract tests (DB-free)."""


def test_route_cost_result() -> None:
    from eurogas_nexus.workflows.models import RouteCostResult

    r = RouteCostResult(result_id="rc-001", route_name="TTF-NCG",
                        from_node_id="n1", to_node_id="n2", total_cost_eur_mwh=2.35)
    assert r.research_only is True
    assert r.human_review_required is True


def test_indicative_netback() -> None:
    from eurogas_nexus.workflows.models import IndicativeNetbackResult

    r = IndicativeNetbackResult(result_id="nb-001", route_name="TTF-NBP",
                                from_market="TTF", to_market="NBP")
    assert r.research_only is True


def test_feasibility_result() -> None:
    from eurogas_nexus.workflows.models import FeasibilityResult, FeasibilityStatus

    r = FeasibilityResult(
        result_id="f-001", route_name="TTF-NCG", status=FeasibilityStatus.FEASIBLE
    )
    assert r.status == FeasibilityStatus.FEASIBLE


def test_allocation_scenario() -> None:
    from eurogas_nexus.workflows.models import AllocationScenarioResult

    r = AllocationScenarioResult(result_id="a-001", scenario_name="Winter",
                                 total_demand_boe_d=5000000.0)
    assert r.total_demand_boe_d == 5000000.0


def test_monitoring_alert() -> None:
    from eurogas_nexus.workflows.models import AlertSeverity, MonitoringAlert

    a = MonitoringAlert(alert_id="alt-001", alert_type="price_spike",
                        severity=AlertSeverity.WARNING, message="Price above threshold")
    assert a.severity == AlertSeverity.WARNING


def test_nowcast_result() -> None:
    from eurogas_nexus.workflows.models import NowcastResult

    r = NowcastResult(result_id="nc-001", market="TTF", adjusted_demand_boe_d=4350000.0)
    assert r.adjusted_demand_boe_d == 4350000.0


def test_backtest_result() -> None:
    from eurogas_nexus.workflows.models import BacktestResult

    r = BacktestResult(result_id="bt-001", strategy_name="Test",
                       total_return_eur=125000.0, sharpe_ratio=1.45)
    assert r.sharpe_ratio == 1.45


def test_shadow_run_result() -> None:
    from eurogas_nexus.workflows.models import ShadowRunResult, ShadowRunStatus

    r = ShadowRunResult(result_id="sr-001", strategy_name="Test", status=ShadowRunStatus.ACTIVE)
    assert r.status == ShadowRunStatus.ACTIVE


def test_candidate_actions_are_research_only() -> None:
    from eurogas_nexus.workflows.models import CandidateAction

    allowed = {
        "research_candidate", "candidate_ranking", "research_signal",
        "candidate_action_for_review",
    }
    forbidden = {"execute", "place_order", "submit_nomination", "approve_trade"}
    values = {a.value for a in CandidateAction}
    assert values <= allowed
    assert not (values & forbidden)


def test_llm_market_analysis() -> None:
    from eurogas_nexus.workflows.models import LlmMarketAnalysis

    a = LlmMarketAnalysis(analysis_id="llm-001", topic="TTF outlook",
                          analysis_text="Analysis...", citations=["Source A"])
    assert a.citations == ["Source A"]


def test_research_brief() -> None:
    from eurogas_nexus.workflows.models import ResearchBrief

    b = ResearchBrief(brief_id="brief-001", title="Weekly Report", summary="Summary...")
    assert b.research_only is True
