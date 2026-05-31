"""Strategy-lab DB schema contract tests."""

from eurogas_nexus.db.registry import get_metadata, list_required_tables


def test_strategy_tables_are_in_metadata_and_required_registry() -> None:
    metadata = get_metadata()
    expected = {
        "strategy_definitions",
        "strategy_runs",
        "strategy_allocation_targets",
        "strategy_alerts",
    }

    assert expected.issubset(metadata.tables)
    assert expected.issubset(set(list_required_tables()))
