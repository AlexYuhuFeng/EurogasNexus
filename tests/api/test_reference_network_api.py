"""Reference network API contract tests using explicit source-shaped DB rows."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models.reference_network import (
    ReferenceEdge,
    ReferenceFacility,
    ReferenceMarketHub,
    ReferenceNode,
    ReferenceTsoAccessPoint,
)
from tests.fixtures.reference_network import (
    reference_edges,
    reference_facilities,
    reference_market_hubs,
    reference_nodes,
    reference_tso_access_points,
)


@pytest.fixture(name="client")
def _client(tmp_path, monkeypatch) -> TestClient:
    db_path = tmp_path / "reference-network-api.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        for payload in reference_nodes():
            session.merge(ReferenceNode(**payload))
        for payload in reference_facilities():
            session.merge(ReferenceFacility(**payload))
        for payload in reference_market_hubs():
            session.merge(ReferenceMarketHub(**payload))
        for payload in reference_edges():
            session.merge(ReferenceEdge(**payload))
        for payload in reference_tso_access_points():
            session.merge(ReferenceTsoAccessPoint(**payload))
        session.commit()

    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    return TestClient(create_app())


# --- Node routes -------------------------------------------------------------


def test_list_nodes_returns_200(client: TestClient) -> None:
    response = client.get("/api/reference-network/nodes")
    assert response.status_code == 200

    body = response.json()
    assert "data" in body
    assert isinstance(body["data"], list)
    assert len(body["data"]) > 0


def test_list_nodes_filter_by_country(client: TestClient) -> None:
    response = client.get("/api/reference-network/nodes?country=NL")
    assert response.status_code == 200

    body = response.json()
    nodes = body["data"]
    assert all(n["country"] == "NL" for n in nodes)
    assert len(nodes) > 0


def test_list_nodes_filter_by_type(client: TestClient) -> None:
    response = client.get("/api/reference-network/nodes?node_type=hub")
    assert response.status_code == 200

    body = response.json()
    nodes = body["data"]
    assert all(n["node_type"] == "hub" for n in nodes)
    assert len(nodes) > 0


def test_get_node_by_id_returns_200(client: TestClient) -> None:
    response = client.get("/api/reference-network/nodes/entsog-vtp-nl-ttf")
    assert response.status_code == 200

    body = response.json()
    assert body["data"]["id"] == "entsog-vtp-nl-ttf"
    assert body["data"]["name"] == "TTF"
    assert body["data"]["source_system"] == "ENTSOG"
    assert body["data"]["source_record_id"] == "VTP-NL-TTF"
    assert body["data"]["metadata_json"]["source_system"] == "ENTSOG"
    assert body["data"]["metadata_json"]["data_status"] == "live_source_metadata"


def test_get_node_unknown_returns_404(client: TestClient) -> None:
    response = client.get("/api/reference-network/nodes/nonexistent")
    assert response.status_code == 404


# --- Edge routes -------------------------------------------------------------


def test_list_edges_returns_200_even_when_no_verified_geometry(client: TestClient) -> None:
    response = client.get("/api/reference-network/edges")
    assert response.status_code == 200

    body = response.json()
    assert isinstance(body["data"], list)
    assert body["data"] == []
    assert body["meta"]["warnings"]


def test_list_edges_filter_by_from_node(client: TestClient) -> None:
    response = client.get("/api/reference-network/edges?from_node_id=entsog-vtp-nl-ttf")
    assert response.status_code == 200

    body = response.json()
    assert body["data"] == []


def test_get_edge_by_id_returns_404_when_not_verified_geometry(client: TestClient) -> None:
    response = client.get("/api/reference-network/edges/entsog-opd-bbl-ttf-entry")
    assert response.status_code == 404


def test_list_tso_access_returns_operator_direction_metadata(client: TestClient) -> None:
    response = client.get("/api/reference-network/tso-access?point_id=entsog-vtp-nl-ttf")
    assert response.status_code == 200

    body = response.json()
    assert body["data"][0]["access_id"] == "entsog-opd-bbl-ttf-entry"
    assert body["data"][0]["operator_name"] == "BBL Company"
    assert body["data"][0]["booking_platform"] == "PRISMA"
    assert body["data"][0]["source_dataset"] == "operatorpointdirections"


def test_get_edge_unknown_returns_404(client: TestClient) -> None:
    response = client.get("/api/reference-network/edges/nonexistent")
    assert response.status_code == 404


# --- Facility routes ---------------------------------------------------------


def test_list_facilities_returns_200(client: TestClient) -> None:
    response = client.get("/api/reference-network/facilities")
    assert response.status_code == 200

    body = response.json()
    assert isinstance(body["data"], list)
    assert len(body["data"]) > 0


def test_list_facilities_filter_by_type(client: TestClient) -> None:
    response = client.get("/api/reference-network/facilities?facility_type=lng_terminal")
    assert response.status_code == 200

    body = response.json()
    facilities = body["data"]
    assert all(f["facility_type"] == "lng_terminal" for f in facilities)
    assert len(facilities) > 0


def test_get_facility_by_id_returns_200(client: TestClient) -> None:
    response = client.get("/api/reference-network/facilities/fac-entsog-lng-nl-gate")
    assert response.status_code == 200

    body = response.json()
    assert body["data"]["id"] == "fac-entsog-lng-nl-gate"


def test_get_facility_unknown_returns_404(client: TestClient) -> None:
    response = client.get("/api/reference-network/facilities/nonexistent")
    assert response.status_code == 404


# --- Market hub routes -------------------------------------------------------


def test_list_market_hubs_returns_200(client: TestClient) -> None:
    response = client.get("/api/reference-network/market-hubs")
    assert response.status_code == 200

    body = response.json()
    assert isinstance(body["data"], list)
    assert len(body["data"]) > 0
    assert any(h["hub_code"] == "TTF" for h in body["data"])


# --- Response envelope -------------------------------------------------------


def test_responses_include_runtime_db_metadata(client: TestClient) -> None:
    response = client.get("/api/reference-network/nodes")
    assert response.status_code == 200

    body = response.json()
    meta = body.get("meta", {})
    assert meta.get("research_only") is True
    assert meta.get("human_review_required") is True
    assert meta.get("source_references") == ["runtime-postgresql"]
    assert isinstance(meta.get("warnings", []), list)


def test_list_nodes_without_runtime_db_returns_empty_status(monkeypatch) -> None:
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    response = TestClient(create_app()).get("/api/reference-network/nodes")

    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert body["meta"]["source_references"] == ["runtime-db-not-configured"]
    assert "reference_nodes" in body["meta"]["missing_inputs"]


# --- App import safety -------------------------------------------------------


def test_app_import_does_not_require_db(monkeypatch) -> None:
    """Verifying app import is DB-free."""
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    from apps.api.main import app

    assert app is not None
