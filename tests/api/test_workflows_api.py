"""Workflow API contract tests (DB-free)."""

import pytest
from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app


@pytest.fixture(name="client")
def _client() -> TestClient:
    return TestClient(create_app())


WORKFLOW_PATHS = [
    "/api/workflows/route-cost",
    "/api/workflows/netback",
    "/api/workflows/feasibility",
    "/api/workflows/allocation",
    "/api/workflows/monitoring",
    "/api/workflows/nowcast",
    "/api/workflows/backtest",
    "/api/workflows/shadow-run",
    "/api/workflows/llm-analysis",
    "/api/workflows/brief",
]


@pytest.mark.parametrize("path", WORKFLOW_PATHS)
def test_workflow_route_returns_200(client: TestClient, path: str) -> None:
    r = client.get(path)
    assert r.status_code == 200, f"{path} returned {r.status_code}"


@pytest.mark.parametrize("path", WORKFLOW_PATHS)
def test_workflow_route_research_metadata(client: TestClient, path: str) -> None:
    r = client.get(path)
    meta = r.json()["meta"]
    assert meta["research_only"] is True, f"{path} missing research_only"
    assert meta["human_review_required"] is True, f"{path} missing human_review_required"
    assert meta["source_references"] == ["runtime-db-not-configured"]
    assert "RUNTIME_DB_NOT_CONFIGURED" in meta["warnings"]


@pytest.mark.parametrize("path", WORKFLOW_PATHS)
def test_workflow_route_has_no_static_fixture_payload(client: TestClient, path: str) -> None:
    r = client.get(path)
    data = r.json()["data"]
    assert data["status"] == "BLOCKED"
    assert data["code"] == "RUNTIME_DATA_REQUIRED"


def test_glossary_list_en(client: TestClient) -> None:
    r = client.get("/api/glossary?lang=en")
    assert r.status_code == 200
    terms = r.json()["data"]
    assert any(t["term"] == "TTF" for t in terms)


def test_glossary_list_zh(client: TestClient) -> None:
    r = client.get("/api/glossary?lang=zh")
    assert r.status_code == 200
    terms = r.json()["data"]
    ttf = next(t for t in terms if t["term"] == "TTF")
    assert "荷兰" in ttf["definition"]
    assert ttf["definition_zh_cn"]
    assert ttf["category"] == "hub"


def test_glossary_filter_and_search(client: TestClient) -> None:
    r = client.get("/api/glossary?lang=zh-CN&category=venue&q=ICE")
    assert r.status_code == 200
    terms = r.json()["data"]
    assert any(term["term"] == "ICE OCM" for term in terms)


def test_glossary_single_term(client: TestClient) -> None:
    r = client.get("/api/glossary/TTF")
    assert r.status_code == 200
    assert r.json()["data"]["term"] == "TTF"


def test_glossary_term_not_found(client: TestClient) -> None:
    r = client.get("/api/glossary/NONEXISTENT")
    assert r.status_code == 404
