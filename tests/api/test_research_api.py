"""Research API endpoint tests (DB-free)."""

import pytest
from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app


@pytest.fixture(name="client")
def _client() -> TestClient:
    return TestClient(create_app())


def test_post_route_cost_200(client: TestClient) -> None:
    r = client.post("/api/v1/research/route-cost", json={
        "route_name": "TTF-NCG", "from_node_id": "node-ttf", "to_node_id": "node-ncg",
        "components": [
            {"component_type": "tariff", "amount": 1.50},
            {"component_type": "fuel", "amount": 0.85},
        ],
        "route_km": 200.0,
    })
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["total_cost_eur_mwh"] == 2.35
    assert d["research_only"] is True


def test_post_route_cost_empty_components_warns(client: TestClient) -> None:
    r = client.post("/api/v1/research/route-cost", json={
        "route_name": "Test", "from_node_id": "n1", "to_node_id": "n2",
    })
    assert r.status_code == 200
    assert len(r.json()["data"]["warnings"]) >= 1


def test_post_netback_200(client: TestClient) -> None:
    r = client.post("/api/v1/research/netback", json={
        "route_name": "TTF-NBP", "from_market": "TTF", "to_market": "NBP",
        "market_price_eur_mwh": 42.50, "route_cost_eur_mwh": 1.80,
    })
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["netback_eur_mwh"] == 40.70


def test_post_netback_with_fx(client: TestClient) -> None:
    r = client.post("/api/v1/research/netback", json={
        "route_name": "TTF-NBP", "from_market": "TTF", "to_market": "NBP",
        "market_price_eur_mwh": 42.50, "route_cost_eur_mwh": 1.80,
        "fx_rate": 0.851, "fx_pair": "EURGBP",
    })
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["netback_local_mwh"] == round(40.70 * 0.851, 4)


def test_research_metadata(client: TestClient) -> None:
    r = client.post("/api/v1/research/route-cost", json={
        "route_name": "T", "from_node_id": "a", "to_node_id": "b",
    })
    meta = r.json()["meta"]
    assert meta["research_only"] is True
    data = r.json()["data"]
    assert data["research_only"] is True
    assert "assumptions" in data
    assert "source_references" in data
