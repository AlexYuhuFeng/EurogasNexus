"""Repository integration tests for the CR-14 research data foundation."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    DatasetSnapshotRecord,
    ForecastObservationRecord,
    ObservationTemporalMetadataRecord,
    SeriesDefinitionRecord,
)
from eurogas_nexus.db.repositories import research as repo
from eurogas_nexus.domain.research.datasets import (
    DatasetEvidenceRecord,
    DatasetPointInTimePolicy,
    DatasetSpec,
    build_dataset,
)
from eurogas_nexus.domain.research.features import FeatureDefinition
from eurogas_nexus.domain.research.resampling import ResamplingPolicy
from eurogas_nexus.domain.research.targets import TargetDefinition, TargetKind
from eurogas_nexus.domain.research.temporal import TemporalIntegrityState


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _dt(hour: int) -> datetime:
    return datetime(2026, 1, 1, hour, tzinfo=UTC)


def _build_metadata() -> tuple[dict, DatasetSpec]:
    feature = FeatureDefinition(
        feature_id="NBP_TTF_DA_SPREAD",
        name="NBP-TTF day-ahead spread",
        description="Repository test feature.",
        category="market",
        input_dependencies=[
            "market.price.NBP.DAY_AHEAD",
            "market.price.TTF.DAY_AHEAD",
        ],
        output_unit="GBP/MWh",
        frequency="1h",
        availability_class="DERIVED_AS_OF",
        transformation="builtin:NBP_TTF_DA_SPREAD",
        transformation_version="v1",
        missing_data_policy="mask",
    )
    target = TargetDefinition(
        target_id="NBP_DA_PRICE_D1",
        name="NBP day-ahead price",
        description="Repository test target.",
        target_type=TargetKind.PRICE,
        entity_type="market_hub",
        entity_id="NBP",
        metric="NBP_DA_PRICE_D1",
        horizon="H1",
        target_window="1h",
        unit="GBP/MWh",
        aggregation="first",
        label_calculation="first_observation_at_or_after_origin_plus_horizon",
    )
    spec = DatasetSpec(
        dataset_spec_id="spec-repository",
        name="Repository dataset",
        description="Repository test dataset.",
        target_ids=[target.target_id],
        feature_ids=[feature.feature_id],
        entity_ids=["ent:market_hub:NBP", "ent:market_hub:TTF"],
        start=_dt(0),
        end=_dt(2),
        forecast_origin_frequency="1h",
        point_in_time_policy=DatasetPointInTimePolicy(),
        entitlement_envelope={"export_policy": "EXPORT_ALLOWED"},
    )
    records = [
        DatasetEvidenceRecord(
            record_id=f"obs-{hour}",
            series_id="market.price.NBP.DAY_AHEAD",
            entity_id="ent:market_hub:NBP",
            observed_at=_dt(hour),
            available_at=_dt(hour),
            value=20.0 + hour,
            unit="GBP/MWh",
            currency="GBP",
            source_reference=f"test:obs-{hour}",
            temporal_integrity=TemporalIntegrityState.TEMPORAL_VERIFIED,
        )
        for hour in range(3)
    ]
    records += [
        DatasetEvidenceRecord(
            record_id=f"ttf-{hour}",
            series_id="market.price.TTF.DAY_AHEAD",
            entity_id="ent:market_hub:TTF",
            observed_at=_dt(hour),
            available_at=_dt(hour),
            value=18.0 + hour,
            unit="GBP/MWh",
            currency="EUR",
            source_reference=f"test:ttf-{hour}",
            temporal_integrity=TemporalIntegrityState.TEMPORAL_VERIFIED,
        )
        for hour in range(3)
    ]
    result = build_dataset(
        spec,
        records,
        {feature.feature_id: feature},
        {target.target_id: target},
        ResamplingPolicy(semantic_type="market_price"),
    )
    return result.as_metadata(), spec


def test_canonical_entity_and_point_in_time_mapping_resolution(session) -> None:
    repo.upsert_canonical_entity(
        session,
        canonical_entity_id="ent:market_hub:NBP",
        entity_type="market_hub",
        canonical_code="NBP",
        display_name="NBP Virtual Trading Point",
        metadata_json={"country": "GB"},
    )
    repo.upsert_source_entity_mapping(
        session,
        mapping_id="map-nbp-ice-v1",
        canonical_entity_id="ent:market_hub:NBP",
        source_id="ICE_OCM_Sim",
        source_entity_type="market_hub",
        source_identifier="NBP",
        valid_from_utc=_dt(0),
        valid_to_utc=_dt(12),
    )
    session.flush()

    resolved = repo.resolve_canonical_entity(
        session,
        source_id="ICE_OCM_Sim",
        source_entity_type="market_hub",
        source_identifier="NBP",
        at_utc=_dt(1),
    )
    assert resolved is not None
    assert resolved.canonical_entity_id == "ent:market_hub:NBP"

    # A second mapping for the same source identity at a later period is legal.
    repo.upsert_canonical_entity(
        session,
        canonical_entity_id="ent:market_hub:TTF",
        entity_type="market_hub",
        canonical_code="TTF",
        display_name="TTF Virtual Trading Point",
    )
    repo.upsert_source_entity_mapping(
        session,
        mapping_id="map-nbp-ice-v2",
        canonical_entity_id="ent:market_hub:TTF",
        source_id="ICE_OCM_Sim",
        source_entity_type="market_hub",
        source_identifier="NBP",
        valid_from_utc=_dt(13),
    )
    session.flush()
    later = repo.resolve_canonical_entity(
        session,
        source_id="ICE_OCM_Sim",
        source_entity_type="market_hub",
        source_identifier="NBP",
        at_utc=_dt(13),
    )
    assert later is not None
    assert later.canonical_entity_id == "ent:market_hub:TTF"

    # Ambiguous overlap must resolve to None, never a silent first row.
    repo.upsert_source_entity_mapping(
        session,
        mapping_id="map-ambiguous",
        canonical_entity_id="ent:market_hub:NBP",
        source_id="ICE_OCM_Sim",
        source_entity_type="market_hub",
        source_identifier="NBP",
        valid_from_utc=_dt(12),
    )
    session.flush()
    assert (
        repo.resolve_canonical_entity(
            session,
            source_id="ICE_OCM_Sim",
            source_entity_type="market_hub",
            source_identifier="NBP",
            at_utc=_dt(12),
        )
        is None
    )


def test_series_feature_target_policy_and_spec_upserts(session) -> None:
    series = SeriesDefinitionRecord(
        series_id="market.price.NBP.DAY_AHEAD",
        name="NBP day-ahead price",
        metric_type="price",
        entity_type="market_hub",
        entity_id="ent:market_hub:NBP",
        product_id="DAY_AHEAD",
        source_class="simulated_exchange",
        native_frequency="1h",
        native_unit="GBP/MWh",
        currency="GBP",
        temporal_type="OBSERVED",
        availability_semantics="available_at_required",
    )
    repo.upsert_series_definition(session, series)
    repo.upsert_feature_definition(
        session,
        feature_id="NBP_TTF_DA_SPREAD",
        definition_json={"feature_id": "NBP_TTF_DA_SPREAD"},
        content_hash="a" * 64,
    )
    repo.upsert_target_definition(
        session,
        target_id="NBP_DA_PRICE_D1",
        definition_json={"target_id": "NBP_DA_PRICE_D1"},
        content_hash="b" * 64,
    )
    repo.upsert_resampling_policy(
        session,
        policy_id="resampling/v1",
        definition_json={"semantic_type": "market_price"},
        content_hash="c" * 64,
    )
    repo.upsert_dataset_spec(
        session,
        dataset_spec_id="spec-repository",
        definition_json={"dataset_spec_id": "spec-repository"},
        content_hash="d" * 64,
    )
    session.flush()

    assert session.get(SeriesDefinitionRecord, "market.price.NBP.DAY_AHEAD")
    assert repo.list_feature_definitions(session)[0].content_hash == "a" * 64
    assert repo.list_target_definitions(session)[0].target_id == "NBP_DA_PRICE_D1"
    updated_policy = repo.upsert_resampling_policy(
        session,
        policy_id="resampling/v1",
        definition_json={"semantic_type": "market_price", "version": 2},
        content_hash="c2" * 32,
    )
    assert updated_policy.content_hash == "c2" * 32


def test_dataset_snapshot_persistence_is_immutable_and_linked(session) -> None:
    metadata, spec = _build_metadata()
    dependencies = [
        {
            "dependency_id": "dep:snapshot-1:feature",
            "dependency_type": "feature",
            "dependency_id_ref": "NBP_TTF_DA_SPREAD",
            "version_ref": "NBP_TTF_DA_SPREAD@v1@00000000",
        }
    ]
    issues = [
        {
            "issue_id": "issue:snapshot-1:0",
            "severity": "WARNING",
            "code": "TEST_WARNING",
            "detail": "test",
        }
    ]
    artifacts = [
        {
            "artifact_id": "artifact:snapshot-1:parquet",
            "format": "parquet",
            "artifact_path": "output/research/snapshot-1.parquet",
            "sha256": "e" * 64,
        }
    ]
    row = repo.persist_dataset_snapshot(
        session,
        metadata=metadata,
        dependencies=dependencies,
        issues=issues,
        artifacts=artifacts,
    )
    session.flush()

    assert row.dataset_snapshot_id == metadata["dataset_snapshot_id"]
    assert row.content_hash == metadata["content_hash"]
    assert row.coverage == 1.0
    assert row.entitlement_envelope == {"export_policy": "EXPORT_ALLOWED"}
    assert row.source_cutoff_utc.astimezone(UTC) == spec.end
    assert row.artifact_ref == "output/research/snapshot-1.parquet"

    stored = session.get(DatasetSnapshotRecord, metadata["dataset_snapshot_id"])
    assert stored is not None
    assert stored.metadata_json["lineage"]
    assert len(repo.list_dataset_snapshots(session)) == 1
    assert repo.get_dataset_snapshot(session, "missing") is None



def test_forecast_observation_and_temporal_metadata_upserts(session) -> None:
    forecast = repo.upsert_forecast_observation(
        session,
        forecast_observation_id="fc-1",
        series_id="market.price.NBP.DAY_AHEAD",
        entity_id="ent:market_hub:NBP",
        forecast_issued_at=_dt(6),
        forecast_valid_start=_dt(8),
        forecast_valid_end=_dt(9),
        horizon="D1",
        value=25.0,
        unit="GBP/MWh",
        source_system="weather_sim",
        available_at_utc=_dt(6),
        model_provider="fixture",
        provenance={"run_id": "run-1"},
    )
    session.flush()
    stored = session.get(ForecastObservationRecord, "fc-1")
    assert stored is not None
    assert stored.value == 25.0
    assert stored.provenance == {"run_id": "run-1"}

    repo.upsert_forecast_observation(
        session,
        forecast_observation_id="fc-1",
        series_id="market.price.NBP.DAY_AHEAD",
        entity_id="ent:market_hub:NBP",
        forecast_issued_at=_dt(6),
        forecast_valid_start=_dt(8),
        forecast_valid_end=_dt(9),
        horizon="D1",
        value=26.0,
        unit="GBP/MWh",
        source_system="weather_sim",
        available_at_utc=_dt(6),
    )
    session.flush()
    assert forecast.value == 26.0

    temporal = repo.upsert_observation_temporal_metadata(
        session,
        observation_id="obs-1",
        observation_table="market_observations",
        observed_at_utc=_dt(6),
        available_at_utc=_dt(7),
        ingested_at_utc=_dt(7),
        temporal_integrity="TEMPORAL_VERIFIED",
        provenance={"ingestion_run_id": "ingest-1"},
    )
    session.flush()
    stored_temporal = session.get(ObservationTemporalMetadataRecord, "obs-1")
    assert stored_temporal is not None
    assert stored_temporal.available_at_utc == _dt(7)
    assert stored_temporal.temporal_integrity == "TEMPORAL_VERIFIED"
    assert temporal.ingested_at_utc == _dt(7)
