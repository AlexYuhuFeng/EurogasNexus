"""Review DB schema contract tests."""

from eurogas_nexus.db.registry import get_metadata, list_required_tables


def test_review_decisions_table_in_metadata_and_registry() -> None:
    metadata = get_metadata()
    assert "review_decisions" in metadata.tables
    assert "review_decisions" in set(list_required_tables())
