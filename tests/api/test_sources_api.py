"""Source registry and ingestion API contract tests (DB-free)."""

import pytest
from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app


@pytest.fixture(name="client")
def _client() -> TestClient:
    return TestClient(create_app())


def test_list_sources_returns_200(client: TestClient) -> None:
    response = client.get("/api/v1/sources")
    assert response.status_code == 200

    body = response.json()
    assert isinstance(body["data"], list)
    assert len(body["data"]) == 7


def test_list_sources_includes_all_families(client: TestClient) -> None:
    response = client.get("/api/v1/sources")
    systems = {s["source_system"] for s in response.json()["data"]}
    assert systems == {"ECB", "ENTSOG", "GIE", "EEX", "Trayport", "ICE_OCM", "Weather"}


def test_get_source_by_id_returns_200(client: TestClient) -> None:
    response = client.get("/api/v1/sources/src-entsog")
    assert response.status_code == 200
    assert response.json()["data"]["source_system"] == "ENTSOG"
    assert response.json()["data"]["credential_requirements"] == []


def test_gie_source_declares_operator_key_requirement(client: TestClient) -> None:
    response = client.get("/api/v1/sources/src-gie")
    assert response.status_code == 200
    assert response.json()["data"]["source_system"] == "GIE"
    assert response.json()["data"]["credential_requirements"] == ["api_key"]


def test_get_source_unknown_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/sources/nonexistent")
    assert response.status_code == 404


def test_list_ingestion_runs_returns_200(client: TestClient) -> None:
    response = client.get("/api/v1/ingestion-runs")
    assert response.status_code == 200

    body = response.json()
    assert isinstance(body["data"], list)
    assert len(body["data"]) >= 1


def test_list_ingestion_runs_filter_by_source(client: TestClient) -> None:
    response = client.get("/api/v1/ingestion-runs?source_id=src-ecb")
    assert response.status_code == 200

    runs = response.json()["data"]
    assert all(r["source_id"] == "src-ecb" for r in runs)


def test_response_metadata(client: TestClient) -> None:
    response = client.get("/api/v1/sources")
    meta = response.json()["meta"]
    assert meta["research_only"] is True
    assert meta["human_review_required"] is True
