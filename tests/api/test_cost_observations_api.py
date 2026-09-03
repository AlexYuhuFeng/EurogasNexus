"""API tests for /api/cost-observations."""

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app


def _client() -> TestClient:
    return TestClient(create_app())


def test_list_values_returns_warning_when_runtime_db_not_configured() -> None:
    response = _client().get("/api/cost-observations/values")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"] == []
    assert "COST_OBSERVATIONS_NOT_CONFIGURED" in payload["meta"]["warnings"]


def test_applicable_returns_warning_when_runtime_db_not_configured() -> None:
    response = _client().get(
        "/api/cost-observations/applicable",
        params={
            "scope_type": "ROUTE",
            "scope_id": "TTF-NBP",
            "as_of": "2026-06-01T00:00:00+00:00",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"] is None
    assert "COST_OBSERVATIONS_NOT_CONFIGURED" in payload["meta"]["warnings"]
