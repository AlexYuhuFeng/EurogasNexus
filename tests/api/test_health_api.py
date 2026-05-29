"""Health route tests."""

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings


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


def test_release_profile_hides_dev_and_internal_routes_and_openapi() -> None:
    release_settings = Settings(api_profile="release")
    release_client = TestClient(create_app(settings=release_settings))

    assert release_client.get("/v1/health").status_code == 200
    assert release_client.get("/api/v1/health").status_code == 200
    assert release_client.get("/dev/health").status_code == 404
    assert release_client.get("/internal/health").status_code == 404
    assert release_client.get("/api/dev/health").status_code == 404
    assert release_client.get("/api/internal/health").status_code == 404
    assert release_client.get("/openapi.json").status_code == 404


def test_development_profile_includes_dev_route_only() -> None:
    dev_client = TestClient(create_app(settings=Settings(api_profile="development")))

    dev_response = dev_client.get("/api/dev/health")

    assert dev_response.status_code == 200
    assert dev_response.json() == {"status": "ok", "scope": "development"}
    assert dev_client.get("/dev/health").status_code == 404
    assert dev_client.get("/api/internal/health").status_code == 404


def test_internal_profile_includes_internal_routes_only() -> None:
    internal_client = TestClient(create_app(settings=Settings(api_profile="internal")))

    assert internal_client.get("/v1/health").status_code == 200
    assert internal_client.get("/api/v1/health").status_code == 200
    assert internal_client.get("/api/internal/health").status_code == 200
    assert internal_client.get("/internal/health").status_code == 404
    assert internal_client.get("/api/dev/health").status_code == 404
    assert internal_client.get("/openapi.json").status_code == 404
