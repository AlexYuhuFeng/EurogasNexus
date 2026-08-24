"""Public API token guard tests (P0-1 release auth boundary)."""

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.security.public_api import (
    PUBLIC_API_TOKEN_ENV,
    PublicApiAuthError,
    public_api_token_configured,
    verify_public_api_token,
)

AUTH_HEADERS = {"X-Eurogas-Api-Key": "test-public-api-token"}


def test_verify_public_api_token_accepts_valid(monkeypatch) -> None:
    monkeypatch.setenv(PUBLIC_API_TOKEN_ENV, "secret-token")
    verify_public_api_token("secret-token")  # must not raise


def test_verify_public_api_token_rejects_missing_value(monkeypatch) -> None:
    monkeypatch.setenv(PUBLIC_API_TOKEN_ENV, "secret-token")
    try:
        verify_public_api_token(None)
        raise AssertionError("expected PublicApiAuthError")
    except PublicApiAuthError as exc:
        assert exc.code == "public_api_token_missing"
        assert exc.status_code == 401


def test_verify_public_api_token_rejects_invalid(monkeypatch) -> None:
    monkeypatch.setenv(PUBLIC_API_TOKEN_ENV, "secret-token")
    try:
        verify_public_api_token("wrong-token")
        raise AssertionError("expected PublicApiAuthError")
    except PublicApiAuthError as exc:
        assert exc.code == "public_api_token_invalid"
        assert exc.status_code == 403


def test_verify_public_api_token_fails_closed_when_unconfigured(
    monkeypatch,
) -> None:
    monkeypatch.delenv(PUBLIC_API_TOKEN_ENV, raising=False)
    try:
        verify_public_api_token("anything")
        raise AssertionError("expected PublicApiAuthError")
    except PublicApiAuthError as exc:
        assert exc.code == "public_api_token_not_configured"
        assert exc.status_code == 503


def test_public_api_token_configured_flag(monkeypatch) -> None:
    monkeypatch.setenv(PUBLIC_API_TOKEN_ENV, "secret-token")
    assert public_api_token_configured() is True
    monkeypatch.delenv(PUBLIC_API_TOKEN_ENV, raising=False)
    assert public_api_token_configured() is False


def test_release_profile_requires_public_api_token(monkeypatch) -> None:
    monkeypatch.setenv(PUBLIC_API_TOKEN_ENV, "test-public-api-token")
    client = TestClient(create_app(Settings(api_profile="release")))

    # No token -> 401.
    response = client.get("/api/health")
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "public_api_token_missing"

    # Invalid token -> 403.
    response = client.get("/api/health", headers={"X-Eurogas-Api-Key": "nope"})
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "public_api_token_invalid"

    # Valid token via header -> 200.
    response = client.get("/api/health", headers=AUTH_HEADERS)
    assert response.status_code == 200

    # Valid token via Authorization bearer -> 200.
    response = client.get(
        "/api/health",
        headers={"Authorization": "Bearer test-public-api-token"},
    )
    assert response.status_code == 200


def test_release_profile_accepts_token_via_query_param_for_sse(monkeypatch) -> None:
    """EventSource cannot set headers; the api_key query channel is the SSE path."""

    monkeypatch.setenv(PUBLIC_API_TOKEN_ENV, "test-public-api-token")
    client = TestClient(create_app(Settings(api_profile="release")))

    response = client.get("/api/health", params={"api_key": "test-public-api-token"})
    assert response.status_code == 200

    wrong = client.get("/api/health", params={"api_key": "nope"})
    assert wrong.status_code == 403


def test_release_profile_fails_closed_without_configured_token(
    monkeypatch,
) -> None:
    monkeypatch.delenv(PUBLIC_API_TOKEN_ENV, raising=False)
    client = TestClient(create_app(Settings(api_profile="release")))

    response = client.get("/api/health", headers=AUTH_HEADERS)

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "public_api_token_not_configured"


def test_development_profile_does_not_require_token(monkeypatch) -> None:
    monkeypatch.delenv(PUBLIC_API_TOKEN_ENV, raising=False)
    client = TestClient(create_app(Settings(api_profile="development")))

    response = client.get("/api/health")

    assert response.status_code == 200


def test_openapi_declares_security_scheme_in_development() -> None:
    client = TestClient(create_app(Settings(api_profile="development")))

    schema = client.get("/openapi.json").json()

    assert "ApiKeyAuth" in schema["components"]["securitySchemes"]
    assert schema["security"] == [{"ApiKeyAuth": []}]
