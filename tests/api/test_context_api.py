"""Context observation API contract tests (DB-free)."""

import pytest
from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app


@pytest.fixture(name="client")
def _client() -> TestClient:
    return TestClient(create_app())


# Market
def test_market_observations_200(client: TestClient) -> None:
    r = client.get("/api/v1/market/observations")
    assert r.status_code == 200
    assert len(r.json()["data"]) == 3

def test_market_fx_200(client: TestClient) -> None:
    r = client.get("/api/v1/market/fx")
    assert r.status_code == 200

def test_market_spreads_200(client: TestClient) -> None:
    r = client.get("/api/v1/market/spreads")
    assert r.status_code == 200

# Physical
def test_physical_flows_200(client: TestClient) -> None:
    r = client.get("/api/v1/physical/flows")
    assert r.status_code == 200

def test_physical_capacity_200(client: TestClient) -> None:
    r = client.get("/api/v1/physical/capacity")
    assert r.status_code == 200

def test_physical_outages_200(client: TestClient) -> None:
    r = client.get("/api/v1/physical/outages")
    assert r.status_code == 200

# LNG
def test_lng_terminals_200(client: TestClient) -> None:
    r = client.get("/api/v1/lng/terminals")
    assert r.status_code == 200

def test_lng_observations_200(client: TestClient) -> None:
    r = client.get("/api/v1/lng/observations")
    assert r.status_code == 200

# Storage
def test_storage_sites_200(client: TestClient) -> None:
    r = client.get("/api/v1/storage/sites")
    assert r.status_code == 200

def test_storage_observations_200(client: TestClient) -> None:
    r = client.get("/api/v1/storage/observations")
    assert r.status_code == 200

# Weather
def test_weather_stations_200(client: TestClient) -> None:
    r = client.get("/api/v1/weather/stations")
    assert r.status_code == 200

def test_weather_observations_200(client: TestClient) -> None:
    r = client.get("/api/v1/weather/observations")
    assert r.status_code == 200

def test_weather_hdd_cdd_200(client: TestClient) -> None:
    r = client.get("/api/v1/weather/hdd-cdd")
    assert r.status_code == 200

# Contracts
def test_contracts_capacity_200(client: TestClient) -> None:
    r = client.get("/api/v1/contracts/capacity")
    assert r.status_code == 200

def test_contracts_routes_200(client: TestClient) -> None:
    r = client.get("/api/v1/contracts/routes")
    assert r.status_code == 200

# Metadata
def test_all_context_routes_have_research_metadata(client: TestClient) -> None:
    for path in [
        "/api/v1/market/observations",
        "/api/v1/physical/flows",
        "/api/v1/lng/terminals",
        "/api/v1/storage/sites",
        "/api/v1/weather/stations",
        "/api/v1/contracts/capacity",
    ]:
        r = client.get(path)
        meta = r.json()["meta"]
        assert meta["research_only"] is True, f"{path} missing research_only"
        assert meta["human_review_required"] is True, f"{path} missing human_review_required"
