"""Shadow run evaluation tests."""

from eurogas_nexus.workflows.shadow_run import (
    ShadowRunInput,
    ShadowSignal,
    evaluate_shadow_run,
)


def test_shadow_run_evaluates_signals() -> None:
    result = evaluate_shadow_run(ShadowRunInput(
        strategy_name="NBP-PEG spread",
        started_at_utc="2026-05-01",
        signals=[
            ShadowSignal("s1", "NBP-Zeebrugge", score=0.85),
            ShadowSignal("s2", "PEG-NCG", score=0.70),
        ],
        paper_pnl_eur=8500.0,
    ))
    assert result.signal_count == 2
    assert result.paper_pnl_eur == 8500.0
    assert result.status == "active"
    assert result.research_only is True


def test_shadow_run_no_signals() -> None:
    result = evaluate_shadow_run(ShadowRunInput(strategy_name="Test"))
    assert result.signal_count == 0


def test_shadow_run_lineage() -> None:
    result = evaluate_shadow_run(ShadowRunInput(strategy_name="T1"))
    assert "shadow-run-evaluation" in result.lineage
