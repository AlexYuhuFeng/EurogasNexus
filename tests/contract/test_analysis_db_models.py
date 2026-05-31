"""Analysis and report DB schema contract tests."""

from eurogas_nexus.db.registry import get_metadata, list_required_tables


def test_analysis_report_tables_are_in_metadata_and_registry() -> None:
    metadata = get_metadata()
    expected = {
        "analysis_runs",
        "generated_reports",
        "business_ontology_terms",
    }

    assert expected.issubset(metadata.tables)
    assert expected.issubset(set(list_required_tables()))
