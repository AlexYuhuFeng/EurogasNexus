"""CR-09 data-operations API tests (SQLite-backed, development profile)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import IngestionRunRecord
from eurogas_nexus.db.repositories import dataops as dataops_repository
from eurogas_nexus.domain.dataops.registry import definition_for_source
from eurogas_nexus.security.permissions import permission_for_path


@pytest.fixture()
def client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'dataops-api.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    client = TestClient(create_app())
    client.engine = engine
    return client


def test_operator_actions_have_declared_permissions() -> None:
    assert permission_for_path("/api/sources/src-entsog/run").value == "operator"
    assert permission_for_path("/api/sources/src-entsog/runs").value == "read"
    assert permission_for_path("/api/runtime/metrics").value == "read"


def test_source_health_and_runs_are_persisted(client: TestClient) -> None:
    health = client.get("/api/sources/src-entsog/health")
    assert health.status_code == 200
    body = health.json()["data"]
    assert body["source_id"] == "src-entsog"
    assert body["freshness_state"] in {"UNKNOWN", "MISSING", "NOT_EXPECTED"}

    runs = client.get("/api/sources/src-entsog/runs")
    assert runs.status_code == 200
    assert runs.json()["data"] == []


def test_manual_run_is_queued_and_visible(client: TestClient) -> None:
    response = client.post(
        "/api/sources/src-entsog/run",
        json={"reason": "operator smoke"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["trigger_type"] == "MANUAL"
    assert response.json()["data"]["status"] == "QUEUED"

    runs = client.get("/api/sources/src-entsog/runs")
    assert len(runs.json()["data"]) == 1
    assert runs.json()["data"][0]["issues"] == []


def test_backfill_is_bounded_and_does_not_look_live(client: TestClient) -> None:
    now = datetime.now(UTC)
    rejected = client.post(
        "/api/sources/src-ecb/backfill",
        json={
            "start_utc": (now - timedelta(days=40)).isoformat(),
            "end_utc": now.isoformat(),
            "reason": "too wide",
        },
    )
    assert rejected.status_code == 422

    accepted = client.post(
        "/api/sources/src-ecb/backfill",
        json={
            "start_utc": (now - timedelta(days=1)).isoformat(),
            "end_utc": now.isoformat(),
            "reason": "explicit operator backfill",
        },
    )
    assert accepted.status_code == 200
    data = accepted.json()["data"]
    assert data["trigger_type"] == "BACKFILL"
    assert data["window_start_utc"] is not None
    assert data["window_end_utc"] is not None


def test_retry_failed_run_creates_recovery_run(client: TestClient) -> None:
    definition = definition_for_source("src-entsog")
    with Session(client.engine) as session:
        state = dataops_repository.ensure_source_runtime_state(
            session, definition, now_utc=datetime.now(UTC)
        )
        state.enabled = True
        run = IngestionRunRecord(
            run_id="ingest-failed-test",
            source_name="ENTSOG",
            source_id="src-entsog",
            dataset="flows",
            trigger_type="MANUAL",
            status="FAILED",
            started_at_utc=datetime.now(UTC) - timedelta(minutes=5),
        )
        session.add(run)
        session.commit()
        run_id = run.run_id

    response = client.post(
        "/api/sources/src-entsog/retry",
        json={"run_id": run_id, "reason": "operator retry"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["trigger_type"] == "RECOVERY"
    assert data["retry_of_run_id"] == run_id


def test_enable_disable_is_backend_owned(client: TestClient) -> None:
    disabled = client.patch(
        "/api/sources/src-entsog/enabled",
        json={"enabled": False, "reason": "maintenance"},
    )
    assert disabled.status_code == 200
    assert disabled.json()["data"]["enabled"] is False
    assert disabled.json()["data"]["circuit_state"] == "DISABLED"

    enabled = client.patch(
        "/api/sources/src-entsog/enabled",
        json={"enabled": True, "reason": "resume"},
    )
    assert enabled.status_code == 200
    assert enabled.json()["data"]["enabled"] is True


def test_certification_records_and_mocked_certified_is_rejected(
    client: TestClient,
) -> None:
    configured = client.post(
        "/api/source-certifications/src-eex/certify",
        json={
            "dataset": "gas-spot",
            "environment": "test",
            "stage": "configured",
            "checks": ["credential_verified"],
            "evidence": {"source": "operator fixture"},
        },
    )
    assert configured.status_code == 200
    assert configured.json()["data"]["stage"] == "configured"
    assert configured.json()["data"]["dataset"] == "gas-spot"

    certifications = client.get("/api/source-certifications")
    assert certifications.status_code == 200
    assert any(row["dataset"] == "gas-spot" for row in certifications.json()["data"])

    fake_certified = client.post(
        "/api/source-certifications/src-eex/certify",
        json={
            "dataset": "gas-spot",
            "environment": "test",
            "stage": "certified",
            "checks": ["simulated_shape_match", "live_sample_validation"],
            "evidence": {"mocked": True},
        },
    )
    assert fake_certified.status_code == 422
    assert "live_test" in fake_certified.json()["detail"]["message"]


def test_runtime_source_operations_and_metrics(client: TestClient) -> None:
    operations = client.get("/api/runtime/source-operations")
    assert operations.status_code == 200
    data = operations.json()["data"]
    assert data["totals"]["registered_sources"] == 24
    assert "heartbeat" in data

    metrics = client.get("/api/runtime/metrics")
    assert metrics.status_code == 200
    text = metrics.json()["data"]
    assert "eurogas_ingestion_runs_total" in text
    assert "eurogas_source_scheduler_overdue" in text
    assert "eurogas_source_certification_state" in text
