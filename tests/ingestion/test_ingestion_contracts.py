"""Ingestion boundary contract tests."""

from pathlib import Path

from eurogas_nexus.ingestion import IngestionPayload
from eurogas_nexus.ingestion.normalization import NormalizedRecord

ROOT = Path(__file__).resolve().parents[2]


def test_ingestion_payload_carries_traceability_fields() -> None:
    payload = IngestionPayload(
        source_name="fixture-source",
        source_reference="file://data/raw/sample.csv",
        collected_at_utc="2026-05-27T00:00:00Z",
        raw_blob_path="data/raw/sample.csv",
    )

    assert payload.source_name == "fixture-source"
    assert payload.source_reference.startswith("file://")


def test_normalized_record_preserves_traceability_and_research_flag() -> None:
    record = NormalizedRecord(
        dataset_id="dataset-1",
        source_name="fixture-source",
        source_reference="file://data/raw/sample.csv",
        canonical_path="data/canonical/dataset-1.parquet",
    )

    assert record.source_name == "fixture-source"
    assert record.research_only is True


def test_ingestion_contract_doc_preserves_no_live_dependency_rules() -> None:
    text = (ROOT / "docs" / "contracts" / "10_INGESTION_ETL_CONTRACT.md").read_text(
        encoding="utf-8"
    )

    assert "Ingestion jobs must be runnable without live external dependencies in tests" in text
    assert "Live connectors" in text
