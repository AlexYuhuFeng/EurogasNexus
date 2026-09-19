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

    # The probe path is a *business* read, not a health probe: owner decision D1 exempts the health
    # probes and the authentication routes from the credential requirement, so they are the wrong
    # subject for a test about the gate (the exemption has its own test below).
    path = "/api/market/observations"

    # No token -> 401.
    response = client.get(path)
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "public_api_token_missing"

    # Invalid token -> 403.
    response = client.get(path, headers={"X-Eurogas-Api-Key": "nope"})
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "public_api_token_invalid"

    # Valid token via header -> 200.
    response = client.get(path, headers=AUTH_HEADERS)
    assert response.status_code == 200

    # Valid token via Authorization bearer -> 200.
    response = client.get(
        path,
        headers={"Authorization": "Bearer test-public-api-token"},
    )
    assert response.status_code == 200


def test_release_profile_accepts_token_via_query_param_for_sse(monkeypatch) -> None:
    """EventSource cannot set headers; the api_key query channel is the SSE path."""

    monkeypatch.setenv(PUBLIC_API_TOKEN_ENV, "test-public-api-token")
    client = TestClient(create_app(Settings(api_profile="release")))

    path = "/api/market/observations"
    response = client.get(path, params={"api_key": "test-public-api-token"})
    assert response.status_code == 200

    wrong = client.get(path, params={"api_key": "nope"})
    assert wrong.status_code == 403


def test_the_health_probes_and_login_are_reachable_without_a_credential(monkeypatch) -> None:
    """D1's exemption, pinned where the gate lives.

    A login that required a credential could never be used, and the probes are read by tooling
    (orchestrators, load balancers, CI readiness loops) that has no principal to present. Both
    gates - the deployment token and the identity dependency - honour the one list.
    """

    monkeypatch.setenv(PUBLIC_API_TOKEN_ENV, "test-public-api-token")
    client = TestClient(create_app(Settings(api_profile="release")))

    assert client.get("/api/health").status_code == 200
    assert client.get("/api/health/live").status_code == 200
    # The business surface behind them is *not* exempt, so the probes are not a loophole.
    assert client.get("/api/market/observations").status_code == 401


def test_release_profile_fails_closed_without_configured_token(
    monkeypatch,
) -> None:
    monkeypatch.delenv(PUBLIC_API_TOKEN_ENV, raising=False)
    client = TestClient(create_app(Settings(api_profile="release")))

    response = client.get("/api/market/observations", headers=AUTH_HEADERS)

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "public_api_token_not_configured"


def test_development_profile_identifies_its_callers_without_a_token(monkeypatch) -> None:
    """D1 changed this test's premise, and this is the change.

    The development profile used to install no authentication at all, so a request with no
    credential was served as the compatibility principal. It now identifies its callers like every
    other profile, and which gate refuses an anonymous caller depends on the deployment:

    * a deployment token is configured (the ordinary case) -> the token gate answers 401
      ``public_api_token_missing``;
    * no deployment token is configured -> it fails closed with 503, exactly as release does;
    * the deployment has said it trusts its network -> both gates honour that and the documented
      compatibility caller is back, which is what this profile used to do unconditionally.
    """

    monkeypatch.setenv(PUBLIC_API_TOKEN_ENV, "test-public-api-token")
    monkeypatch.setenv("EUROGAS_NEXUS_TEST_ANONYMOUS", "1")
    try:
        client = TestClient(create_app(Settings(api_profile="development")))
        assert client.get("/api/market/observations").status_code == 401

        # The deployment's own statement is the only way back to the pre-D1 posture, and both
        # gates have to honour it: the token gate would otherwise still refuse a caller that
        # presented nothing, and the statement would never take effect.
        opting_in = TestClient(
            create_app(
                Settings(api_profile="development", allow_anonymous_callers=True)
            )
        )
        assert opting_in.get("/api/market/observations").status_code == 200
        # A *presented* credential is still verified: the opt-in is about anonymity, not about
        # skipping verification of a token somebody sent.
        assert (
            opting_in.get(
                "/api/market/observations", headers={"X-Eurogas-Api-Key": "nope"}
            ).status_code
            == 403
        )

        monkeypatch.delenv(PUBLIC_API_TOKEN_ENV, raising=False)
        fails_closed = TestClient(create_app(Settings(api_profile="development")))
        assert fails_closed.get("/api/market/observations").status_code == 503
    finally:
        monkeypatch.delenv("EUROGAS_NEXUS_TEST_ANONYMOUS", raising=False)


def test_the_identity_gate_refuses_an_anonymous_caller() -> None:
    """The backstop, exercised directly.

    In the shipped profiles the deployment-token gate is the gate that refuses an anonymous caller
    first, so this branch is a second lock on the same door rather than the one a caller meets - and
    it is kept precisely because the requirement is "this deployment identifies its callers", which
    should not depend on a *different* dependency staying installed. The test drives
    ``require_identity`` itself: a non-exempt path, no credential, no verified token, no opt-in.
    """

    import asyncio
    from types import SimpleNamespace

    from fastapi import HTTPException

    from eurogas_nexus.api.dependencies.identity import require_identity

    request = SimpleNamespace(
        headers={},
        cookies={},
        url=SimpleNamespace(path="/api/market/observations"),
        state=SimpleNamespace(),
        app=SimpleNamespace(
            state=SimpleNamespace(settings=Settings(api_profile="release"))
        ),
    )

    try:
        asyncio.run(require_identity(request))
    except HTTPException as exc:
        assert exc.status_code == 401
        assert exc.detail["error"] == "authentication_required"
    else:  # pragma: no cover - the assertion is the point
        raise AssertionError("an anonymous caller was not refused")


def test_openapi_declares_security_scheme_in_development() -> None:
    client = TestClient(create_app(Settings(api_profile="development")))

    schema = client.get("/openapi.json").json()

    assert "ApiKeyAuth" in schema["components"]["securitySchemes"]
    assert schema["security"] == [{"ApiKeyAuth": []}]
