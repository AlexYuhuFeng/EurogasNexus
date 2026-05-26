"""Health route tests."""

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app


def test_health_route_returns_shell_status() -> None:
    client = TestClient(create_app())

    response = client.get("/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "eurogas-nexus",
        "version": "0.1.0",
        "profile": "development",
    }

