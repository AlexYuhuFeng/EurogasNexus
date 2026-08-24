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
def test_legacy_workflow_shell_was_physically_removed(client: TestClient, path: str) -> None:
    """S4.3 post-migration contract: no /api/workflows/* path remains."""

    r = client.get(path)
    assert r.status_code == 404, f"{path} should be removed, got {r.status_code}"


def test_legacy_workflow_paths_are_absent_from_openapi() -> None:
    from apps.api.main import app

    paths = app.openapi()["paths"]
    assert not any(path.startswith("/api/workflows/") for path in paths)


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
