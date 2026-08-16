"""Review decision API tests (DB-free)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_review_post_rejects_invalid_decision_value() -> None:
    response = _client().post(
        "/api/review/decisions",
        json={
            "entity_type": "intraday_opportunity",
            "entity_id": "opp-1",
            "actor": "trader-a",
            "decision": "not-a-decision",
        },
    )
    assert response.status_code == 422


def test_review_post_rejects_invalid_entity_type() -> None:
    response = _client().post(
        "/api/review/decisions",
        json={
            "entity_type": "not-an-entity",
            "entity_id": "opp-1",
            "actor": "trader-a",
            "decision": "accepted",
        },
    )
    assert response.status_code == 422


def test_review_post_degrades_explicitly_without_db() -> None:
    response = _client().post(
        "/api/review/decisions",
        json={
            "entity_type": "intraday_opportunity",
            "entity_id": "opp-1",
            "actor": "trader-a",
            "decision": "accepted",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["data"] is None
    assert "RUNTIME_DB_NOT_CONFIGURED" in body["meta"]["warnings"]


def test_review_get_degrades_explicitly_without_db() -> None:
    response = _client().get("/api/review/decisions")
    assert response.status_code == 200
    body = response.json()
    assert body["data"] == []
    assert "RUNTIME_DB_NOT_CONFIGURED" in body["meta"]["warnings"]


def test_review_routes_are_registered() -> None:
    from apps.api.main import app

    paths = set(app.openapi()["paths"])
    assert "/api/review/decisions" in paths
