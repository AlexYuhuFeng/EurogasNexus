"""Context observation API contract tests (DB-free)."""

import pytest
from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app


@pytest.fixture(name="client")
def _client() -> TestClient:
    return TestClient(create_app())


# Market
def test_market_observations_200(client: TestClient) -> None:
    r = client.get("/api/market/observations")
    assert r.status_code == 200
    body = r.json()
    assert body["data"] == []
    assert body["meta"]["source_references"] == ["runtime-db-not-configured"]

def test_market_fx_200(client: TestClient) -> None:
    r = client.get("/api/market/fx")
    assert r.status_code == 200

def test_market_spreads_200(client: TestClient) -> None:
    r = client.get("/api/market/spreads")
    assert r.status_code == 200

# Physical
def test_physical_flows_200(client: TestClient) -> None:
    r = client.get("/api/physical/flows")
    assert r.status_code == 200

def test_physical_capacity_200(client: TestClient) -> None:
    r = client.get("/api/physical/capacity")
    assert r.status_code == 200

def test_physical_outages_200(client: TestClient) -> None:
    r = client.get("/api/physical/outages")
    assert r.status_code == 200

# LNG
def test_lng_terminals_200(client: TestClient) -> None:
    r = client.get("/api/lng/terminals")
    assert r.status_code == 200

def test_lng_observations_200(client: TestClient) -> None:
    r = client.get("/api/lng/observations")
    assert r.status_code == 200

# Storage
def test_storage_sites_200(client: TestClient) -> None:
    r = client.get("/api/storage/sites")
    assert r.status_code == 200

def test_storage_observations_200(client: TestClient) -> None:
    r = client.get("/api/storage/observations")
    assert r.status_code == 200

# Weather
def test_weather_stations_200(client: TestClient) -> None:
    r = client.get("/api/weather/stations")
    assert r.status_code == 200
    body = r.json()
    assert body["data"] == []
    assert body["meta"]["source_references"] == ["runtime-db-not-configured"]

def test_weather_observations_200(client: TestClient) -> None:
    r = client.get("/api/weather/observations")
    assert r.status_code == 200
    body = r.json()
    assert body["data"] == []
    assert body["meta"]["source_references"] == ["runtime-db-not-configured"]

def test_weather_hdd_cdd_200(client: TestClient) -> None:
    r = client.get("/api/weather/hdd-cdd")
    assert r.status_code == 200
    body = r.json()
    assert body["data"] == []
    assert body["meta"]["source_references"] == ["runtime-db-not-configured"]

# Contracts
def test_contracts_capacity_200(client: TestClient) -> None:
    r = client.get("/api/contracts/capacity")
    assert r.status_code == 200

def test_contracts_routes_200(client: TestClient) -> None:
    r = client.get("/api/contracts/routes")
    assert r.status_code == 200

# Metadata
def test_all_context_routes_have_research_metadata(client: TestClient) -> None:
    for path in [
        "/api/market/observations",
        "/api/physical/flows",
        "/api/lng/terminals",
        "/api/storage/sites",
        "/api/weather/stations",
        "/api/contracts/capacity",
    ]:
        r = client.get(path)
        meta = r.json()["meta"]
        assert meta["research_only"] is True, f"{path} missing research_only"
        assert meta["human_review_required"] is True, f"{path} missing human_review_required"
