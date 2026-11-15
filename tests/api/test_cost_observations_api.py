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


def test_list_values_with_a_database_is_an_envelope_not_a_500(tmp_path, monkeypatch) -> None:
    """QA-03: the success path called the envelope without ``warnings`` and answered 500
    whenever a runtime database was configured."""

    from sqlalchemy import create_engine

    import eurogas_nexus.db.models  # noqa: F401
    from eurogas_nexus.db.base import Base

    url = f"sqlite+pysqlite:///{tmp_path / 'cost.sqlite'}"
    Base.metadata.create_all(create_engine(url))
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    response = _client().get("/api/cost-observations/values")
    assert response.status_code == 200, response.text
    assert response.json()["data"] == [] and response.json()["meta"]["warnings"] == []
