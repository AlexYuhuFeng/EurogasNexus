"""Route-registration profile contract tests."""

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings


def test_release_profile_excludes_dev_and_internal_paths() -> None:
    client = TestClient(create_app(Settings(api_profile="release")))

    assert client.get("/api/health").status_code == 200
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/dev/health").status_code == 404
    assert client.get("/api/internal/health").status_code == 404


def test_development_profile_includes_api_prefixed_dev_endpoint_only() -> None:
    client = TestClient(create_app(Settings(api_profile="development")))

    assert client.get("/api/health").status_code == 200
    assert client.get("/api/health").status_code == 200
    assert client.get("/api/dev/health").status_code == 200
    assert client.get("/api/internal/health").status_code == 404


def test_internal_profile_includes_api_prefixed_internal_endpoint_only() -> None:
    client = TestClient(create_app(Settings(api_profile="internal")))

    assert client.get("/api/internal/health").status_code == 200
    assert client.get("/api/dev/health").status_code == 404
