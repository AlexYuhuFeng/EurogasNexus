"""Workflow API contract tests (DB-free)."""

import pytest
from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app


@pytest.fixture(name="client")
def _client() -> TestClient:
    return TestClient(create_app())


WORKFLOW_PATHS = [
    "/api/v1/workflows/route-cost",
    "/api/v1/workflows/netback",
    "/api/v1/workflows/feasibility",
    "/api/v1/workflows/allocation",
    "/api/v1/workflows/monitoring",
    "/api/v1/workflows/nowcast",
    "/api/v1/workflows/backtest",
    "/api/v1/workflows/shadow-run",
    "/api/v1/workflows/llm-analysis",
    "/api/v1/workflows/brief",
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


def test_glossary_list_en(client: TestClient) -> None:
    r = client.get("/api/v1/glossary?lang=en")
    assert r.status_code == 200
    terms = r.json()["data"]
    assert any(t["term"] == "TTF" for t in terms)


def test_glossary_list_zh(client: TestClient) -> None:
    r = client.get("/api/v1/glossary?lang=zh")
    assert r.status_code == 200
    terms = r.json()["data"]
    ttf = next(t for t in terms if t["term"] == "TTF")
    assert "荷兰" in ttf["definition"]


def test_glossary_single_term(client: TestClient) -> None:
    r = client.get("/api/v1/glossary/TTF")
    assert r.status_code == 200
    assert r.json()["data"]["term"] == "TTF"


def test_glossary_term_not_found(client: TestClient) -> None:
    r = client.get("/api/v1/glossary/NONEXISTENT")
    assert r.status_code == 404
