"""Source registry and ingestion API contract tests (DB-free)."""

import pytest
from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app


@pytest.fixture(name="client")
def _client() -> TestClient:
    return TestClient(create_app())


def test_list_sources_returns_200(client: TestClient) -> None:
    response = client.get("/api/sources")
    assert response.status_code == 200

    body = response.json()
    assert isinstance(body["data"], list)
    assert len(body["data"]) >= 13


def test_list_sources_includes_all_families(client: TestClient) -> None:
    response = client.get("/api/sources")
    systems = {s["source_system"] for s in response.json()["data"]}
    assert {
        "Argus",
        "DEEPSEEK",
        "ECB",
        "EEX",
        "ENTSOG",
        "GIE",
        "ICE_OCM",
        "ICIS",
        "Kpler",
        "NationalGasNTS",
        "Platts",
        "Trayport",
        "Weather",
    }.issubset(systems)


def test_sources_are_grouped_for_source_center(client: TestClient) -> None:
    response = client.get("/api/sources")
    data = response.json()["data"]
    by_category = {}
    for source in data:
        by_category.setdefault(source["category"], set()).add(source["source_system"])

    assert {"Platts", "ICIS", "EEX", "ICE_OCM", "Trayport", "Kpler", "Argus"}.issubset(
        by_category["price"]
    )
    assert by_category["fx"] == {"ECB"}
    assert {"ENTSOG", "GIE"}.issubset(by_category["infrastructure"])
    assert by_category["tariff"] == {"NationalGasNTS"}
    assert "Weather" in by_category["weather"]
    assert "DEEPSEEK" in by_category["ai"]


def test_source_records_include_diagnostics_and_credential_state(client: TestClient) -> None:
    response = client.get("/api/sources")
    source = next(item for item in response.json()["data"] if item["source_system"] == "ICIS")

    assert source["category"] == "price"
    assert source["category_label"] == "Prices"
    assert source["credential_state"] == "missing"
    assert source["connectivity_status"] == "needs_credential"
    assert source["status"] == source["connectivity_status"]
    assert source["last_success_at_utc"] is None
    assert source["last_failure_at_utc"] is None
    assert source["diagnostics"] == ["credential_missing"]


def test_get_source_by_id_returns_200(client: TestClient) -> None:
    response = client.get("/api/sources/src-entsog")
    assert response.status_code == 200
    assert response.json()["data"]["source_system"] == "ENTSOG"
    assert response.json()["data"]["credential_requirements"] == []


def test_gie_source_declares_operator_key_requirement(client: TestClient) -> None:
    response = client.get("/api/sources/src-gie")
    assert response.status_code == 200
    assert response.json()["data"]["source_system"] == "GIE"
    assert response.json()["data"]["credential_requirements"] == ["api_key"]
    assert response.json()["data"]["category"] == "infrastructure"


def test_get_source_unknown_returns_404(client: TestClient) -> None:
    response = client.get("/api/sources/nonexistent")
    assert response.status_code == 404


def test_list_ingestion_runs_returns_200(client: TestClient) -> None:
    response = client.get("/api/ingestion-runs")
    assert response.status_code == 200

    body = response.json()
    assert isinstance(body["data"], list)
    assert body["data"] == []
    assert body["meta"]["source_references"] == ["source-registry"]


def test_list_ingestion_runs_filter_by_source(client: TestClient) -> None:
    response = client.get("/api/ingestion-runs?source_id=src-ecb")
    assert response.status_code == 200

    runs = response.json()["data"]
    assert all(r["source_id"] == "src-ecb" for r in runs)


def test_response_metadata(client: TestClient) -> None:
    response = client.get("/api/sources")
    meta = response.json()["meta"]
    assert meta["research_only"] is True
    assert meta["human_review_required"] is True
