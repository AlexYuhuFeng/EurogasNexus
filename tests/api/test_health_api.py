"""Health route tests."""

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.version import APPLICATION_VERSION

AUTH_HEADERS = {"X-Eurogas-Api-Key": "test-public-api-token"}


def test_health_route_returns_shell_status() -> None:
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "eurogas-nexus",
        "version": APPLICATION_VERSION,
        "profile": "development",
        # Finding C5: the development profile installs no app-wide authentication, and the
        # shell status says so instead of leaving it to a document.
        "authentication": "not_installed",
    }
    # Liveness reports the same posture, so a probe sees it too.
    assert client.get("/api/health/live").json()["authentication"] == "not_installed"


def test_health_reports_whether_the_profile_identifies_its_callers() -> None:
    """The posture is derived from the route profile, not restated per endpoint."""

    from eurogas_nexus.api.route_profiles import API_ROUTE_PROFILES, authentication_posture

    for profile in API_ROUTE_PROFILES:
        expected = "enforced" if API_ROUTE_PROFILES[profile].require_auth else "not_installed"
        assert authentication_posture(profile) == expected, profile

    # Only the release profile installs the app-wide authentication dependencies.
    assert authentication_posture("release") == "enforced"
    assert authentication_posture("development") == "not_installed"
    assert authentication_posture("internal") == "not_installed"

    internal_client = TestClient(create_app(settings=Settings(api_profile="internal")))
    assert internal_client.get("/api/health").json()["authentication"] == "not_installed"


def test_release_profile_hides_dev_and_internal_routes_and_openapi() -> None:
    release_settings = Settings(api_profile="release")
    release_client = TestClient(create_app(settings=release_settings))

    assert release_client.get("/api/health", headers=AUTH_HEADERS).status_code == 200
    # The release profile is the one that identifies its callers.
    assert (
        release_client.get("/api/health", headers=AUTH_HEADERS).json()["authentication"]
        == "enforced"
    )
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

    assert internal_client.get("/api/health").status_code == 200
    assert internal_client.get("/api/internal/health").status_code == 200
    assert internal_client.get("/internal/health").status_code == 404
    assert internal_client.get("/api/dev/health").status_code == 404
    assert internal_client.get("/openapi.json").status_code == 404
