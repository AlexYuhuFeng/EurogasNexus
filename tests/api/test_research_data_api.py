"""API tests for the CR-14 research data foundation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import MarketObservationRecord
from eurogas_nexus.db.repositories import research as repo
from eurogas_nexus.domain.research.features import FeatureDefinition
from eurogas_nexus.domain.research.resampling import ResamplingPolicy
from eurogas_nexus.domain.research.targets import TargetDefinition, TargetKind
from eurogas_nexus.domain.research.temporal import DatasetMode, TemporalIntegrityState
from eurogas_nexus.security.permissions import Permission, permission_for_path


def _dt(hour: int) -> datetime:
    return datetime(2026, 1, 1, hour, tzinfo=UTC)


def _feature() -> FeatureDefinition:
    return FeatureDefinition(
        feature_id="NBP_TTF_DA_SPREAD",
        name="NBP-TTF day-ahead spread",
        description="API test feature.",
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


def _target() -> TargetDefinition:
    return TargetDefinition(
        target_id="NBP_DA_PRICE_D1",
        name="NBP day-ahead price",
        description="API test target.",
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


def _spec_payload() -> dict:
    return {
        "dataset_spec_id": "spec-api",
        "name": "API dataset",
        "description": "API point-in-time dataset.",
        "target_ids": ["NBP_DA_PRICE_D1"],
        "feature_ids": ["NBP_TTF_DA_SPREAD"],
        "entity_ids": ["ent:market_hub:NBP", "ent:market_hub:TTF"],
        "start": _dt(0).isoformat(),
        "end": _dt(3).isoformat(),
        "forecast_origin_frequency": "1h",
        "point_in_time_policy": {
            "policy_id": "pit-policy/v1",
            "cutoff_semantics": "available_at_lt_or_eq_cutoff",
            "allow_forecast_vintages": True,
            "allow_simulated": False,
            "mode": DatasetMode.STRICT.value,
        },
        "resampling_policy_id": "resampling/v1",
        "missing_data_policy": "mask",
        "minimum_coverage": 0.0,
        "ontology_version": "energy-ontology/v1",
        "entitlement_envelope": {"export_policy": "EXPORT_ALLOWED"},
    }


@pytest.fixture()
def client(tmp_path, monkeypatch: pytest.MonkeyPatch):
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'research-api.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    with Session(engine) as session:
        feature = _feature()
        target = _target()
        repo.upsert_feature_definition(
            session,
            feature_id=feature.feature_id,
            definition_json=feature.model_dump(mode="json"),
            content_hash=feature.content_hash(),
        )
        repo.upsert_target_definition(
            session,
            target_id=target.target_id,
            definition_json=target.model_dump(mode="json"),
            content_hash=target.content_hash(),
        )
        repo.upsert_resampling_policy(
            session,
            policy_id="resampling/v1",
            definition_json=ResamplingPolicy(semantic_type="market_price").model_dump(
                mode="json"
            ),
            content_hash="0" * 64,
        )
        for hour in range(4):
            for hub, value, currency in (("NBP", 20.0 + hour, "GBP"), ("TTF", 18.0 + hour, "EUR")):
                observation_id = f"obs-{hub}-{hour}"
                observed_at = _dt(hour)
                session.add(
                    MarketObservationRecord(
                        observation_id=observation_id,
                        market_venue=hub,
                        product="DAY_AHEAD",
                        price=value,
                        unit="GBP/MWh",
                        currency=currency,
                        period_start_utc=observed_at,
                        period_end_utc=observed_at + timedelta(hours=1),
                        observed_at_utc=observed_at,
                        source_system="ICE_OCM_Research",
                        source_reference=f"test:{observation_id}",
                        source_record_id=observation_id,
                        freshness="OBSERVED",
                        quality_score=1.0,
                        research_only=True,
                        metadata_json={"hub": hub, "tenor": "DAY_AHEAD"},
                    )
                )
                session.add(
                    repo.upsert_observation_temporal_metadata(
                        session,
                        observation_id=observation_id,
                        observation_table="market_observations",
                        observed_at_utc=observed_at,
                        available_at_utc=observed_at,
                        ingested_at_utc=observed_at,
                        temporal_integrity=TemporalIntegrityState.TEMPORAL_VERIFIED.value,
                    )
                )
        session.commit()
    test_client = TestClient(create_app())
    test_client.engine = engine
    return test_client


def test_research_paths_have_declared_permissions() -> None:
    assert permission_for_path("/api/research/features") == Permission.READ
    assert permission_for_path("/api/research/datasets/validate") == Permission.GOVERNED
    assert permission_for_path("/api/research/datasets/snap-1/export") == Permission.GOVERNED


def test_research_catalog_endpoints_are_read_only_metadata(client) -> None:
    features = client.get("/api/research/features")
    assert features.status_code == 200
    assert features.json()["meta"]["research_only"] is True
    assert [row["feature_id"] for row in features.json()["data"]] == ["NBP_TTF_DA_SPREAD"]

    feature = client.get("/api/research/features/NBP_TTF_DA_SPREAD")
    assert feature.status_code == 200
    assert feature.json()["data"]["definition"]["feature_id"] == "NBP_TTF_DA_SPREAD"

    targets = client.get("/api/research/targets")
    assert targets.status_code == 200
    assert [row["target_id"] for row in targets.json()["data"]] == ["NBP_DA_PRICE_D1"]

    capabilities = client.get("/api/research/capabilities")
    assert capabilities.status_code == 200
    assert {
        row["name"] for row in capabilities.json()["data"]
    } >= {"dataset.build", "dataset.export", "ontology.resolve_entity"}

    assert client.get("/api/research/features/missing").status_code == 404



def test_dataset_validate_reports_semantic_issues_without_persisting(client) -> None:
    response = client.post(
        "/api/research/datasets/validate",
        json={"dataset_spec": {**_spec_payload(), "target_ids": []}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"]["ok"] is False
    assert "at least one target_id is required" in body["data"]["issues"]

    valid = client.post(
        "/api/research/datasets/validate",
        json={"dataset_spec": _spec_payload()},
    )
    assert valid.status_code == 200
    assert valid.json()["data"]["ok"] is True
    assert len(valid.json()["data"]["spec_hash"]) == 64


def test_dataset_build_persists_point_in_time_snapshot_and_supports_export_gate(
    client,
) -> None:
    build = client.post(
        "/api/research/datasets",
        json={"dataset_spec": _spec_payload(), "materialize": True},
    )
    assert build.status_code == 200
    body = build.json()["data"]
    assert body["row_count"] == 6
    assert body["temporal_integrity"] == "TEMPORAL_VERIFIED"
    assert body["quality_report"]["coverage"] == 0.8333
    snapshot_id = body["dataset_snapshot_id"]

    datasets = client.get("/api/research/datasets")
    assert datasets.status_code == 200
    assert [row["dataset_snapshot_id"] for row in datasets.json()["data"]] == [snapshot_id]

    detail = client.get(f"/api/research/datasets/{snapshot_id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["entitlement_envelope"] == {
        "export_policy": "EXPORT_ALLOWED"
    }
    assert detail.json()["data"]["spec_hash"] == body["dataset_spec_version"].split("@")[-1]

    quality = client.get(f"/api/research/datasets/{snapshot_id}/quality")
    assert quality.status_code == 200
    assert quality.json()["data"]["leakage_issues"] == []

    export = client.post(
        f"/api/research/datasets/{snapshot_id}/export",
        json={"format": "parquet"},
    )
    assert export.status_code == 200
    assert export.json()["data"]["entitlement_policy"] == "EXPORT_ALLOWED"
