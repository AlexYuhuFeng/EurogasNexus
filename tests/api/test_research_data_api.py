"""API tests for the CR-14 research data foundation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import DatasetSnapshotRecord, MarketObservationRecord
from eurogas_nexus.db.repositories import research as repo
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.domain.research.features import FeatureDefinition
from eurogas_nexus.domain.research.resampling import ResamplingPolicy
from eurogas_nexus.domain.research.targets import TargetDefinition, TargetKind
from eurogas_nexus.domain.research.temporal import DatasetMode, TemporalIntegrityState
from eurogas_nexus.security.permissions import Permission, permission_for_path
from eurogas_nexus.security.public_api import PUBLIC_API_TOKEN_ENV


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
    # CR14-ARTIFACT-001: artifacts go to the configurable research artifact root;
    # tests redirect it so nothing is written into the checkout.
    monkeypatch.setenv(
        "EUROGAS_NEXUS_RESEARCH_ARTIFACT_ROOT", str(tmp_path / "research-artifacts")
    )
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
        for entity_type, code, display_name in (
            ("market_hub", "NBP", "NBP Virtual Trading Point"),
            ("market_hub", "TTF", "TTF Virtual Trading Point"),
        ):
            repo.upsert_canonical_entity(
                session,
                canonical_entity_id=f"ent:{entity_type}:{code}",
                entity_type=entity_type,
                canonical_code=code,
                display_name=display_name,
            )
        # Row 0 stays the permissive default policy; the bounded and unsupported
        # rows exist to prove the requested resampling_policy_id is resolved
        # instead of the first registry row.
        repo.upsert_resampling_policy(
            session,
            policy_id="resampling/v1",
            definition_json=ResamplingPolicy(semantic_type="market_price").model_dump(
                mode="json"
            ),
            content_hash="0" * 64,
        )
        repo.upsert_resampling_policy(
            session,
            policy_id="resampling/bounded",
            definition_json=ResamplingPolicy(
                policy_id="resampling/bounded",
                semantic_type="market_price",
                maximum_carry_seconds=1800,
            ).model_dump(mode="json"),
            content_hash="1" * 64,
        )
        repo.upsert_resampling_policy(
            session,
            policy_id="resampling/unsupported",
            definition_json=ResamplingPolicy(
                policy_id="resampling/unsupported",
                semantic_type="market_price",
                aggregation="mean",
                maximum_carry_seconds=3600,
            ).model_dump(mode="json"),
            content_hash="2" * 64,
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
                        source_system="ENTSOG",
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
    # Issues are structured field-level objects (field/code/message), matching the
    # 422 envelope used by the build route.
    assert body["data"]["issues"] == [
        {
            "field": "target_ids",
            "code": "target_required",
            "message": "at least one target_id is required",
        }
    ]

    valid = client.post(
        "/api/research/datasets/validate",
        json={"dataset_spec": _spec_payload()},
    )
    assert valid.status_code == 200
    assert valid.json()["data"]["ok"] is True
    assert valid.json()["data"]["issues"] == []
    assert valid.json()["data"]["registry_resolution"] == "RESOLVED"
    assert len(valid.json()["data"]["spec_hash"]) == 64


@pytest.mark.parametrize(
    ("override", "field", "code"),
    [
        ({"feature_ids": ["MISSING_FEATURE"]}, "feature_ids", "unknown_feature_id"),
        ({"target_ids": ["MISSING_TARGET"]}, "target_ids", "unknown_target_id"),
        ({"entity_ids": ["ent:market_hub:THE"]}, "entity_ids", "unknown_entity_id"),
        (
            {"source_restrictions": ["NOT_A_SOURCE"]},
            "source_restrictions",
            "unknown_source_id",
        ),
        (
            {"resampling_policy_id": "resampling/missing"},
            "resampling_policy_id",
            "unknown_resampling_policy_id",
        ),
        (
            {"resampling_policy_id": "resampling/unsupported"},
            "resampling_policy_id",
            "resampling_policy_unsupported",
        ),
    ],
)
def test_dataset_validate_resolves_registry_ids(client, override, field, code) -> None:
    """CR14-SEMANTICS-001: unknown ids fail at VALIDATE time, not silently."""

    response = client.post(
        "/api/research/datasets/validate",
        json={"dataset_spec": {**_spec_payload(), **override}},
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["ok"] is False
    issue = body["issues"][0]
    assert issue["field"] == field
    assert issue["code"] == code
    assert issue["message"]


def test_dataset_build_rejects_unresolvable_registry_ids_with_structured_422(
    client,
) -> None:
    response = client.post(
        "/api/research/datasets",
        json={
            "dataset_spec": {
                **_spec_payload(),
                "resampling_policy_id": "resampling/unsupported",
            },
            "materialize": False,
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error"] == "dataset_registry_invalid"
    assert detail["issues"][0]["field"] == "resampling_policy_id"
    assert detail["issues"][0]["code"] == "resampling_policy_unsupported"


@pytest.mark.parametrize(
    ("field", "value", "error_code"),
    [
        ("forecast_origin_frequency", "0h", "frequency_invalid"),
        ("forecast_origin_frequency", "-1h", "frequency_invalid"),
        ("forecast_origin_frequency", "15m", "frequency_invalid"),
        ("forecast_origin_frequency", "9" * 12 + "h", "frequency_invalid"),
        ("forecast_origin_frequency", "١h", "frequency_invalid"),
        ("start", _dt(3).isoformat(), "date_bounds_invalid"),
        (
            "end",
            (_dt(0) + timedelta(hours=250_001)).isoformat(),
            "origin_count_limit",
        ),
        ("history_lookback", -86400, "history_lookback_invalid"),
        ("history_lookback", (3650 + 1) * 86400, "history_lookback_invalid"),
    ],
)
def test_dataset_build_rejects_invalid_bounds_with_safe_structured_422(
    client, field: str, value, error_code: str
) -> None:
    payload = _spec_payload()
    payload[field] = value
    response = client.post(
        "/api/research/datasets",
        json={"dataset_spec": payload, "materialize": False},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["error"] == "dataset_spec_invalid"
    assert detail["issues"][0]["code"] == error_code
    assert "Value error" not in response.text


def test_release_dataset_build_requires_analyst_role(client, monkeypatch) -> None:
    monkeypatch.setenv(PUBLIC_API_TOKEN_ENV, "test-public-api-token")
    with Session(client.engine) as session:
        viewer = create_identity_principal(
            session,
            name="research-viewer",
            display_name="Research Viewer",
            role="VIEWER",
        )
        _, viewer_bearer = create_identity_api_key(session, viewer.principal_id)
        analyst = create_identity_principal(
            session,
            name="research-analyst",
            display_name="Research Analyst",
            role="ANALYST",
        )
        _, analyst_bearer = create_identity_api_key(session, analyst.principal_id)
        session.commit()

    release_client = TestClient(create_app(Settings(api_profile="release")))
    base_headers = {"X-Eurogas-Api-Key": "test-public-api-token"}
    viewer_response = release_client.post(
        "/api/research/datasets",
        headers={**base_headers, "X-Eurogas-Identity": viewer_bearer},
        json={"dataset_spec": _spec_payload(), "materialize": False},
    )
    assert viewer_response.status_code == 403

    analyst_response = release_client.post(
        "/api/research/datasets",
        headers={**base_headers, "X-Eurogas-Identity": analyst_bearer},
        json={"dataset_spec": _spec_payload(), "materialize": True},
    )
    assert analyst_response.status_code == 200
    authorized_snapshot_id = analyst_response.json()["data"]["dataset_snapshot_id"]
    authorized_headers = {
        **base_headers,
        "X-Eurogas-Identity": analyst_bearer,
    }
    assert (
        release_client.get(
            f"/api/research/datasets/{authorized_snapshot_id}",
            headers=authorized_headers,
        ).status_code
        == 200
    )
    assert (
        release_client.get(
            f"/api/research/datasets/{authorized_snapshot_id}/quality",
            headers=authorized_headers,
        ).status_code
        == 200
    )

    denied_by_client_restriction = release_client.post(
        "/api/research/datasets",
        headers={**base_headers, "X-Eurogas-Identity": analyst_bearer},
        json={
            "dataset_spec": {**_spec_payload(), "source_restrictions": ["EEX"]},
            "materialize": False,
        },
    )
    assert denied_by_client_restriction.status_code == 403


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
        "export_policy": "EXPORT_RESTRICTED",
        "policy_source": "dataops",
    }
    assert detail.json()["data"]["metadata"]["trusted_source_ids"] == ["src-entsog"]
    assert detail.json()["data"]["spec_hash"] == body["dataset_spec_version"].split("@")[-1]

    quality = client.get(f"/api/research/datasets/{snapshot_id}/quality")
    assert quality.status_code == 200
    assert quality.json()["data"]["leakage_issues"] == []

    export = client.post(
        f"/api/research/datasets/{snapshot_id}/export",
        json={"format": "parquet"},
    )
    assert export.status_code == 403
    assert export.json()["detail"]["code"] == "export_denied_entitlement"


def test_snapshot_reads_fail_closed_for_unknown_mixed_and_legacy_provenance(
    client, monkeypatch
) -> None:
    monkeypatch.setenv(PUBLIC_API_TOKEN_ENV, "test-public-api-token")
    now = _dt(0)
    with Session(client.engine) as session:
        for snapshot_id, source_ids in (
            ("snapshot-unknown-source", ["src-not-registered"]),
            ("snapshot-mixed-source", ["src-entsog", "src-eex"]),
            ("snapshot-legacy", None),
        ):
            metadata = {
                "quality_report": {"coverage": 1.0, "temporal_integrity": "TEMPORAL_VERIFIED"},
            }
            if source_ids is not None:
                metadata["trusted_source_ids"] = source_ids
            session.add(
                DatasetSnapshotRecord(
                    dataset_snapshot_id=snapshot_id,
                    dataset_spec_id="spec-fixture",
                    spec_hash="a" * 64,
                    ontology_version="energy-ontology/v1",
                    source_cutoff_utc=now,
                    row_count=1,
                    column_count=1,
                    coverage=1.0,
                    temporal_integrity="TEMPORAL_VERIFIED",
                    content_hash="b" * 64,
                    entitlement_envelope={"export_policy": "EXPORT_ALLOWED"},
                    metadata_json=metadata,
                    artifact_ref="artifacts/fixture.parquet",
                    created_at_utc=now,
                    created_by="test",
                    status="COMPLETE",
                )
            )
        principal = create_identity_principal(
            session,
            name="entsog-snapshot-reader",
            display_name="ENTSOG Snapshot Reader",
            role="ANALYST",
            data_scopes=["ENTSOG"],
        )
        _, bearer = create_identity_api_key(session, principal.principal_id)
        session.commit()

    release_client = TestClient(create_app(Settings(api_profile="release")))
    headers = {
        "X-Eurogas-Api-Key": "test-public-api-token",
        "X-Eurogas-Identity": bearer,
    }
    listed = release_client.get("/api/research/datasets", headers=headers)
    assert listed.status_code == 200
    assert "snapshot-legacy" not in {row["dataset_snapshot_id"] for row in listed.json()["data"]}
    for snapshot_id in (
        "snapshot-unknown-source",
        "snapshot-mixed-source",
        "snapshot-legacy",
    ):
        response = release_client.get(
            f"/api/research/datasets/{snapshot_id}", headers=headers
        )
        assert response.status_code == 403
        quality = release_client.get(
            f"/api/research/datasets/{snapshot_id}/quality", headers=headers
        )
        assert quality.status_code == 403
        export = release_client.post(
            f"/api/research/datasets/{snapshot_id}/export",
            headers=headers,
            json={"format": "parquet"},
        )
        assert export.status_code == 403


def test_concrete_simulation_source_is_filtered_and_authorized_by_family(
    client, monkeypatch
) -> None:
    monkeypatch.setenv(PUBLIC_API_TOKEN_ENV, "test-public-api-token")
    with Session(client.engine) as session:
        session.query(MarketObservationRecord).update(
            {MarketObservationRecord.source_system: "EEX_Sim"},
            synchronize_session=False,
        )
        principal = create_identity_principal(
            session,
            name="eex-simulation-reader",
            display_name="EEX Simulation Reader",
            role="ANALYST",
            data_scopes=["EEX"],
        )
        _, bearer = create_identity_api_key(session, principal.principal_id)
        session.commit()

    release_client = TestClient(create_app(Settings(api_profile="release")))
    response = release_client.post(
        "/api/research/datasets",
        headers={
            "X-Eurogas-Api-Key": "test-public-api-token",
            "X-Eurogas-Identity": bearer,
        },
        json={
            "dataset_spec": {**_spec_payload(), "source_restrictions": ["EEX_Sim"]},
            "materialize": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["row_count"] == 6
    assert payload["trusted_source_ids"] == ["src-eex-sim"]
    assert payload["entitlement_envelope"]["export_policy"] == "EXPORT_RESTRICTED"


def _build_materialized(client, spec: dict | None = None) -> dict:
    response = client.post(
        "/api/research/datasets",
        json={"dataset_spec": spec or _spec_payload(), "materialize": True},
    )
    assert response.status_code == 200
    return response.json()["data"]


def test_dataset_build_registers_format_specific_artifact(client, tmp_path) -> None:
    """CR14-ARTIFACT-001: a materialized build persists a real artifact."""

    body = _build_materialized(client)
    snapshot_id = body["dataset_snapshot_id"]

    with Session(client.engine) as session:
        artifacts = repo.list_dataset_artifacts(session, snapshot_id)
        stored = repo.get_dataset_snapshot(session, snapshot_id)
        parquet = repo.get_dataset_artifact(session, snapshot_id, "parquet")
        assert stored is not None
        # pyarrow is an optional extra; CSV is always available in this environment.
        assert [artifact.format for artifact in artifacts] == ["csv"]
        artifact = artifacts[0]
        assert artifact.sha256 and len(artifact.sha256) == 64
        assert stored.artifact_ref == artifact.artifact_path
        assert parquet is None
        artifact_path = artifact.artifact_path
        artifact_sha256 = artifact.sha256

    written = tmp_path / "research-artifacts" / artifact_path
    assert written.is_file()
    import hashlib

    assert hashlib.sha256(written.read_bytes()).hexdigest() == artifact_sha256

    detail = client.get(f"/api/research/datasets/{snapshot_id}")
    assert detail.status_code == 200
    assert detail.json()["data"]["artifact_ref"] == artifact_path
    assert str(tmp_path) not in artifact_path


def test_dataset_export_matches_requested_format_or_fails_closed(
    client, monkeypatch
) -> None:
    """Export resolves a STORED artifact; an unregistered format never returns 200.

    ``effective_entitlement_envelope`` is overridden to EXPORT_ALLOWED because the
    canonical registry policy is fail-closed by construction (no registered source
    family maps to the PUBLIC scope), so the success path is otherwise unreachable;
    the entitlement gate itself is covered by the 403 tests above.
    """

    from eurogas_nexus.api.routes.public import research_data

    body = _build_materialized(client)
    snapshot_id = body["dataset_snapshot_id"]

    denied = client.post(
        f"/api/research/datasets/{snapshot_id}/export", json={"format": "csv"}
    )
    assert denied.status_code == 403
    assert denied.json()["detail"]["code"] == "export_denied_entitlement"

    monkeypatch.setattr(
        research_data,
        "effective_entitlement_envelope",
        lambda _definitions: {"export_policy": "EXPORT_ALLOWED", "policy_source": "test"},
    )

    # parquet was never registered for this snapshot: fail closed, no null ref.
    unavailable = client.post(
        f"/api/research/datasets/{snapshot_id}/export", json={"format": "parquet"}
    )
    assert unavailable.status_code == 409
    detail = unavailable.json()["detail"]
    assert detail["code"] == "artifact_not_available"
    assert detail["reason"] == "FORMAT_NOT_REGISTERED"
    assert detail["format"] == "parquet"
    assert detail["available_formats"] == ["csv"]
    assert "artifact_ref" not in detail

    with Session(client.engine) as session:
        stored = repo.get_dataset_artifact(session, snapshot_id, "csv")
    assert stored is not None

    allowed = client.post(
        f"/api/research/datasets/{snapshot_id}/export", json={"format": "csv"}
    )
    assert allowed.status_code == 200
    payload = allowed.json()["data"]
    assert payload["format"] == "csv"
    assert payload["artifact_ref"] == stored.artifact_path
    assert payload["artifact_ref"] is not None
    assert payload["artifact_id"] == stored.artifact_id
    assert payload["available_formats"] == ["csv"]
    assert payload["entitlement_policy"] == "EXPORT_ALLOWED"
    assert allowed.json()["meta"]["research_only"] is True
    assert any("EXPORT_REFERENCE_ONLY" in item for item in allowed.json()["meta"]["warnings"])


def test_dataset_export_fails_closed_when_registered_file_is_gone(
    client, monkeypatch, tmp_path
) -> None:
    from eurogas_nexus.api.routes.public import research_data

    body = _build_materialized(client)
    snapshot_id = body["dataset_snapshot_id"]
    with Session(client.engine) as session:
        artifact = repo.get_dataset_artifact(session, snapshot_id, "csv")
    assert artifact is not None
    (tmp_path / "research-artifacts" / artifact.artifact_path).unlink()
    monkeypatch.setattr(
        research_data,
        "effective_entitlement_envelope",
        lambda _definitions: {"export_policy": "EXPORT_ALLOWED", "policy_source": "test"},
    )

    response = client.post(
        f"/api/research/datasets/{snapshot_id}/export", json={"format": "csv"}
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "artifact_not_available"
    assert response.json()["detail"]["reason"] == "FILE_MISSING"


def test_dataset_build_entity_ids_filter_the_built_rows(client) -> None:
    """CR14-SEMANTICS-001: spec.entity_ids actually filters the built dataset."""

    both = _build_materialized(client)
    assert both["row_count"] == 6
    assert both["quality_report"]["coverage"] == 0.8333

    nbp_only = _build_materialized(
        client,
        {
            **_spec_payload(),
            "dataset_spec_id": "spec-api-nbp-only",
            "entity_ids": ["ent:market_hub:NBP"],
        },
    )

    assert nbp_only["row_count"] == 6  # rows are per origin/feature/target
    # Only the NBP observations may enter the build: the NBP/TTF spread feature
    # can no longer resolve, and the TTF source references disappear from lineage.
    assert nbp_only["quality_report"]["coverage"] == 0.3333
    assert all(row["value"] is None for row in nbp_only["rows"] if row.get("feature_id"))
    assert not any("TTF" in ref for ref in nbp_only["lineage"])
    assert any("NBP" in ref for ref in nbp_only["lineage"])


def test_dataset_build_uses_requested_resampling_policy(client) -> None:
    """CR14-SEMANTICS-001: the requested registry row, not row 0, drives the build."""

    with Session(client.engine) as session:
        session.query(MarketObservationRecord).filter(
            MarketObservationRecord.observation_id.in_(["obs-NBP-1", "obs-TTF-1"])
        ).delete(synchronize_session=False)
        session.commit()

    permissive = _build_materialized(client)
    assert permissive["resampling_policy"]["policy_id"] == "resampling/v1"
    # Unbounded carry-forward: the hour-0 value still resolves the hour-1 origin.
    assert permissive["quality_report"]["coverage"] == 0.8333

    bounded = _build_materialized(
        client,
        {
            **_spec_payload(),
            "dataset_spec_id": "spec-api-bounded",
            "resampling_policy_id": "resampling/bounded",
        },
    )
    assert bounded["resampling_policy"]["policy_id"] == "resampling/bounded"
    assert bounded["resampling_policy"]["supported"] is True
    # The requested bounded policy drops the stale hour-0 value at the hour-1
    # origin, which the permissive default policy silently carried forward.
    assert bounded["quality_report"]["coverage"] == 0.6667
    assert bounded["quality_report"]["observed_values"] == (
        permissive["quality_report"]["observed_values"] - 1
    )
    hour_one = [
        row
        for row in bounded["rows"]
        if row.get("feature_id") and row["forecast_origin"].startswith("2026-01-01T01:00")
    ]
    assert hour_one and hour_one[0]["value"] is None

    detail = client.get(f"/api/research/datasets/{bounded['dataset_snapshot_id']}")
    assert detail.status_code == 200
    assert (
        detail.json()["data"]["metadata"]["resampling_policy"]["policy_id"]
        == "resampling/bounded"
    )
