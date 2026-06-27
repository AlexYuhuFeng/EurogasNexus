"""Runtime store contract tests (DB-free)."""

import pytest

# --- ResultEnvelope ----------------------------------------------------------

def test_result_envelope_defaults() -> None:
    from eurogas_nexus.runtime_store.contracts import ResultEnvelope

    envelope = ResultEnvelope(payload={"key": "val"})
    assert envelope.research_only is True
    assert envelope.human_review_required is True


def test_result_envelope_metadata_fields_are_lists() -> None:
    from eurogas_nexus.runtime_store.contracts import ResultEnvelope

    envelope = ResultEnvelope(payload=42)
    assert isinstance(envelope.assumptions, list)
    assert isinstance(envelope.missing_inputs, list)
    assert isinstance(envelope.warnings, list)
    assert isinstance(envelope.source_references, list)
    assert isinstance(envelope.lineage, list)


def test_result_envelope_payload_is_preserved() -> None:
    from eurogas_nexus.runtime_store.contracts import ResultEnvelope

    payload = {"route": "TTF-NBP", "cost": 1.5}
    envelope = ResultEnvelope(payload=payload)
    assert envelope.payload == payload


# --- SourceReference ---------------------------------------------------------

def test_source_reference_has_required_fields() -> None:
    from eurogas_nexus.runtime_store.contracts import SourceReference

    ref = SourceReference(
        reference_id="ref-001",
        source_system="ENTSOG",
        source_dataset="tp-2026-05",
    )
    assert ref.reference_id == "ref-001"
    assert ref.source_system == "ENTSOG"
    assert ref.entitlement_scope == "internal-research"
    assert ref.freshness is not None


def test_source_reference_freshness_defaults_to_unknown() -> None:
    from eurogas_nexus.runtime_store.contracts import FreshnessState, SourceReference

    ref = SourceReference(reference_id="r1", source_system="test")
    assert ref.freshness == FreshnessState.UNKNOWN


def test_source_reference_marks_test_fixture_lineage() -> None:
    from eurogas_nexus.runtime_store.contracts import SourceReference

    ref = SourceReference(reference_id="r1", source_system="test", is_test_fixture=True)
    assert ref.is_test_fixture is True


# --- LineageRecord -----------------------------------------------------------

def test_lineage_record_has_required_fields() -> None:
    from eurogas_nexus.runtime_store.contracts import LineageRecord

    rec = LineageRecord(
        event_type="transform",
        source_reference_id="src-1",
        target_reference_id="tgt-1",
        detail="normalized flow units",
    )
    assert rec.event_type == "transform"
    assert rec.source_reference_id == "src-1"
    assert rec.target_reference_id == "tgt-1"
    assert rec.event_id  # auto-generated


def test_lineage_record_defaults_event_type_to_load() -> None:
    from eurogas_nexus.runtime_store.contracts import LineageRecord

    rec = LineageRecord()
    assert rec.event_type == "load"


# --- DataQualityRecord -------------------------------------------------------

def test_data_quality_record_has_required_fields() -> None:
    from eurogas_nexus.runtime_store.contracts import DataQualityRecord

    rec = DataQualityRecord(
        check_name="non-null-price",
        severity="error",
        passed=True,
        detail="all prices present",
    )
    assert rec.check_name == "non-null-price"
    assert rec.severity == "error"
    assert rec.passed is True


def test_data_quality_record_failed_check() -> None:
    from eurogas_nexus.runtime_store.contracts import DataQualityRecord

    rec = DataQualityRecord(check_name="freshness-check", severity="warning", passed=False)
    assert rec.passed is False


# --- FreshnessState ----------------------------------------------------------

def test_freshness_state_values() -> None:
    from eurogas_nexus.runtime_store.contracts import FreshnessState

    assert FreshnessState.FRESH.value == "fresh"
    assert FreshnessState.STALE.value == "stale"
    assert FreshnessState.UNKNOWN.value == "unknown"
    assert FreshnessState.UNAVAILABLE.value == "unavailable"


# --- RuntimeStoreRepository --------------------------------------------------

def test_runtime_store_repository_is_abstract() -> None:
    from eurogas_nexus.runtime_store.contracts import RuntimeStoreRepository

    with pytest.raises(TypeError):
        RuntimeStoreRepository()  # type: ignore[abstract]


# --- HeartbeatRecord ---------------------------------------------------------

def test_heartbeat_record_fields() -> None:
    from eurogas_nexus.runtime_store.contracts import HeartbeatRecord

    rec = HeartbeatRecord(
        service_name="ingestion-worker",
        instance_id="i-abc123",
        observed_at_utc="2026-05-29T12:00:00Z",
    )
    assert rec.service_name == "ingestion-worker"
    assert rec.instance_id == "i-abc123"


# --- No file fallback --------------------------------------------------------

def test_no_file_fallback_raises_in_trial_and_release() -> None:
    from eurogas_nexus.runtime_store.contracts import (
        _no_file_fallback_in_trial_or_release,
    )

    for env in ("trial", "release"):
        with pytest.raises(RuntimeError, match="forbidden"):
            _no_file_fallback_in_trial_or_release(env)


def test_no_file_fallback_allows_development_and_test() -> None:
    from eurogas_nexus.runtime_store.contracts import (
        _no_file_fallback_in_trial_or_release,
    )

    # Must not raise.
    _no_file_fallback_in_trial_or_release("development")
    _no_file_fallback_in_trial_or_release("test")
