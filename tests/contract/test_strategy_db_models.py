"""Strategy-lab DB schema contract tests."""

from eurogas_nexus.db.registry import get_metadata, list_required_tables


def test_strategy_tables_are_in_metadata_and_required_registry() -> None:
    metadata = get_metadata()
    expected = {
        "strategies",
        "strategy_versions",
        "strategy_data_snapshots",
        "backtest_experiments",
        "backtest_decision_events",
        "backtest_series",
        "backtest_attribution",
        "strategy_shadow_monitors",
        "strategy_shadow_evaluations",
        "strategy_shadow_candidates",
        "strategy_shadow_risk_checks",
        "strategy_shadow_outcomes",
        "strategy_shadow_alerts",
        "strategy_shadow_drift_snapshots",
        "strategy_shadow_scheduler_heartbeat",
        "strategy_definitions",
        "strategy_runs",
        "strategy_allocation_targets",
        "strategy_alerts",
    }

    assert expected.issubset(metadata.tables)
    assert expected.issubset(set(list_required_tables()))
