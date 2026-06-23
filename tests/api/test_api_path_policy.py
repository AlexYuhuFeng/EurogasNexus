"""API path normalization policy tests."""

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings


def test_v1_health_bootstrap_path_still_works() -> None:
    client = TestClient(create_app(Settings(api_profile="release")))

    assert client.get("/v1/health").status_code == 200


def test_api_v1_health_alias_works() -> None:
    client = TestClient(create_app(Settings(api_profile="release")))

    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_internal_and_dev_paths_use_api_prefixes() -> None:
    internal_client = TestClient(create_app(Settings(api_profile="internal")))
    dev_client = TestClient(create_app(Settings(api_profile="development")))

    assert internal_client.get("/api/internal/health").status_code == 200
    assert internal_client.get("/internal/health").status_code == 404
    assert dev_client.get("/api/dev/health").status_code == 200
    assert dev_client.get("/dev/health").status_code == 404


def test_local_desktop_cors_preflight_for_api_v1_post() -> None:
    client = TestClient(create_app(Settings(api_profile="release")))

    response = client.options(
        "/api/v1/route-cost/uk/easington/live-pnl",
        headers={
            "Origin": "http://tauri.localhost",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://tauri.localhost"
    assert "POST" in response.headers["access-control-allow-methods"]
