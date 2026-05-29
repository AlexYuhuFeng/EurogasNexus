"""Reference network API contract tests (DB-free, uses fixture data via FastAPI TestClient)."""

import pytest
from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app


@pytest.fixture(name="client")
def _client() -> TestClient:
    app = create_app()
    return TestClient(app)


# --- Node routes -------------------------------------------------------------


def test_list_nodes_returns_200(client: TestClient) -> None:
    response = client.get("/api/v1/reference-network/nodes")
    assert response.status_code == 200

    body = response.json()
    assert "data" in body
    assert isinstance(body["data"], list)
    assert len(body["data"]) > 0


def test_list_nodes_filter_by_country(client: TestClient) -> None:
    response = client.get("/api/v1/reference-network/nodes?country=NL")
    assert response.status_code == 200

    body = response.json()
    nodes = body["data"]
    assert all(n["country"] == "NL" for n in nodes)
    assert len(nodes) > 0


def test_list_nodes_filter_by_type(client: TestClient) -> None:
    response = client.get("/api/v1/reference-network/nodes?node_type=hub")
    assert response.status_code == 200

    body = response.json()
    nodes = body["data"]
    assert all(n["node_type"] == "hub" for n in nodes)


def test_get_node_by_id_returns_200(client: TestClient) -> None:
    response = client.get("/api/v1/reference-network/nodes/node-ttf")
    assert response.status_code == 200

    body = response.json()
    assert body["data"]["id"] == "node-ttf"
    assert body["data"]["name"] == "TTF Hub"


def test_get_node_unknown_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/reference-network/nodes/nonexistent")
    assert response.status_code == 404


# --- Edge routes -------------------------------------------------------------


def test_list_edges_returns_200(client: TestClient) -> None:
    response = client.get("/api/v1/reference-network/edges")
    assert response.status_code == 200

    body = response.json()
    assert isinstance(body["data"], list)
    assert len(body["data"]) > 0


def test_list_edges_filter_by_from_node(client: TestClient) -> None:
    response = client.get("/api/v1/reference-network/edges?from_node_id=node-ttf")
    assert response.status_code == 200

    body = response.json()
    edges = body["data"]
    assert all(e["from_node_id"] == "node-ttf" for e in edges)


def test_get_edge_by_id_returns_200(client: TestClient) -> None:
    response = client.get("/api/v1/reference-network/edges/edge-1")
    assert response.status_code == 200

    body = response.json()
    assert body["data"]["id"] == "edge-1"


def test_get_edge_unknown_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/reference-network/edges/nonexistent")
    assert response.status_code == 404


# --- Facility routes ---------------------------------------------------------


def test_list_facilities_returns_200(client: TestClient) -> None:
    response = client.get("/api/v1/reference-network/facilities")
    assert response.status_code == 200

    body = response.json()
    assert isinstance(body["data"], list)
    assert len(body["data"]) > 0


def test_list_facilities_filter_by_type(client: TestClient) -> None:
    response = client.get("/api/v1/reference-network/facilities?facility_type=lng_terminal")
    assert response.status_code == 200

    body = response.json()
    facilities = body["data"]
    assert all(f["facility_type"] == "lng_terminal" for f in facilities)


def test_get_facility_by_id_returns_200(client: TestClient) -> None:
    response = client.get("/api/v1/reference-network/facilities/fac-zee-lng")
    assert response.status_code == 200

    body = response.json()
    assert body["data"]["id"] == "fac-zee-lng"


def test_get_facility_unknown_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/reference-network/facilities/nonexistent")
    assert response.status_code == 404


# --- Market hub routes -------------------------------------------------------


def test_list_market_hubs_returns_200(client: TestClient) -> None:
    response = client.get("/api/v1/reference-network/market-hubs")
    assert response.status_code == 200

    body = response.json()
    assert isinstance(body["data"], list)
    assert len(body["data"]) > 0
    assert any(h["hub_code"] == "TTF" for h in body["data"])


# --- Response envelope -------------------------------------------------------


def test_responses_include_research_metadata(client: TestClient) -> None:
    response = client.get("/api/v1/reference-network/nodes")
    assert response.status_code == 200

    body = response.json()
    meta = body.get("meta", {})
    assert meta.get("research_only") is True
    assert meta.get("human_review_required") is True
    assert "synthetic-fixture" in meta.get("source_references", [])
    assert isinstance(meta.get("warnings", []), list)


# --- App import safety -------------------------------------------------------


def test_app_import_does_not_require_db() -> None:
    """Verifying app import is DB-free (this test always runs without DB)."""
    from apps.api.main import app

    assert app is not None
