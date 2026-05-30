"""Route-registration profile contract tests."""

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings


def test_release_profile_excludes_dev_and_internal_paths() -> None:
    app = create_app(Settings(api_profile="release"))
    paths = {route.path for route in app.routes}

    assert "/v1/health" in paths
    assert "/api/v1/health" in paths
    assert not any(path.startswith("/api/dev") for path in paths)
    assert not any(path.startswith("/api/internal") for path in paths)


def test_development_profile_includes_api_prefixed_dev_endpoint_only() -> None:
    app = create_app(Settings(api_profile="development"))
    paths = {route.path for route in app.routes}

    assert "/v1/health" in paths
    assert "/api/v1/health" in paths
    assert "/api/dev/health" in paths
    assert not any(path.startswith("/api/internal") for path in paths)


def test_internal_profile_includes_api_prefixed_internal_endpoint_only() -> None:
    app = create_app(Settings(api_profile="internal"))
    paths = {route.path for route in app.routes}

    assert "/api/internal/health" in paths
    assert not any(path.startswith("/api/dev") for path in paths)
