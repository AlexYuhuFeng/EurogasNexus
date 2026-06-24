"""API import contract tests."""

from fastapi.testclient import TestClient


def test_app_import_exposes_fastapi_app() -> None:
    from apps.api.main import app

    client = TestClient(app)

    assert app.title == "Eurogas Nexus"
    assert client.get("/v1/health").status_code == 200
    assert client.get("/api/v1/health").status_code == 200

