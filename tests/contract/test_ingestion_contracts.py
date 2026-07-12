"""Ingestion and source registry contract tests (DB-free)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_source_registry_entry_has_required_fields() -> None:
    from eurogas_nexus.ingestion.contracts import SourceRegistryEntry, SourceStatus

    entry = SourceRegistryEntry(
        source_id="src-001",
        source_system="ENTSOG",
        datasets=("flows", "capacity"),
    )
    assert entry.source_id == "src-001"
    assert entry.source_system == "ENTSOG"
    assert entry.status == SourceStatus.UNKNOWN
    assert entry.entitlement_scope == "internal-research"


def test_source_status_values() -> None:
    from eurogas_nexus.ingestion.contracts import SourceStatus

    assert SourceStatus.REGISTERED.value == "registered"
    assert SourceStatus.ACTIVE.value == "active"
    assert SourceStatus.DEGRADED.value == "degraded"
    assert SourceStatus.UNAVAILABLE.value == "unavailable"


def test_ingestion_run_has_required_fields() -> None:
    from eurogas_nexus.ingestion.contracts import IngestionRun, IngestionRunStatus

    run = IngestionRun(source_id="src-001")
    assert run.run_id
    assert run.status == IngestionRunStatus.QUEUED


def test_ingestion_run_status_values() -> None:
    from eurogas_nexus.ingestion.contracts import IngestionRunStatus

    assert IngestionRunStatus.QUEUED.value == "queued"
    assert IngestionRunStatus.RUNNING.value == "running"
    assert IngestionRunStatus.SUCCEEDED.value == "succeeded"
    assert IngestionRunStatus.FAILED.value == "failed"


def test_normalization_status_values() -> None:
    from eurogas_nexus.ingestion.contracts import NormalizationStatus

    assert NormalizationStatus.RAW.value == "raw"
    assert NormalizationStatus.NORMALIZED.value == "normalized"
    assert NormalizationStatus.FAILED.value == "failed"


def test_normalized_record_preserves_source_traceability() -> None:
    from eurogas_nexus.ingestion.contracts import NormalizedRecord

    rec = NormalizedRecord(
        source_system="ENTSOG",
        dataset="flows",
        normalized_data={"value": 100},
        source_reference_id="ref-001",
    )
    assert rec.source_system == "ENTSOG"
    assert rec.source_reference_id == "ref-001"


def test_ingestion_payload_has_source_fields() -> None:
    from eurogas_nexus.ingestion.contracts import IngestionPayload

    payload = IngestionPayload(
        source_name="entsog-test",
        source_system="ENTSOG",
        dataset="flows",
    )
    assert payload.source_name == "entsog-test"
    assert payload.source_system == "ENTSOG"


def test_entsog_flow_ingestion_requests_and_replaces_only_physical_flow() -> None:
    script = (ROOT / "scripts" / "ops" / "ingest_public_sources.py").read_text(
        encoding="utf-8"
    )

    assert '"indicator": "Physical Flow"' in script
    assert "delete(FlowObservationRecord)" in script
    assert "ENTSOG returned no physical-flow observations" in script
