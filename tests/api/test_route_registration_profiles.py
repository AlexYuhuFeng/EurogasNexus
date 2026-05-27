"""Route-registration profile contract tests."""

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings


def test_release_profile_excludes_dev_and_internal_paths() -> None:
    app = create_app(Settings(api_profile="release"))
    paths = {route.path for route in app.routes}

    assert "/v1/health" in paths
    assert not any(path.startswith("/dev") for path in paths)
    assert not any(path.startswith("/internal") for path in paths)


def test_development_profile_currently_has_no_dev_or_internal_endpoints() -> None:
    app = create_app(Settings(api_profile="development"))
    paths = {route.path for route in app.routes}

    assert "/v1/health" in paths
    assert not any(path.startswith("/dev") for path in paths)
    assert not any(path.startswith("/internal") for path in paths)
