"""OPERATOR route principal enforcement tests (Gate 1).

Two callers reach an OPERATOR route and they are held to different things since owner decision D1
installed this gate in every profile:

* the **compatibility** caller (the deployment token) identifies the deployment, not a person, so it
  must name the acting operator with ``X-Eurogas-Principal``;
* an **authenticated** caller (a session, an identity key, a validated OIDC token) *is* the acting
  operator, so demanding a spoofable header from it would add nothing - and would break the browser,
  which cannot send one and reads the ADMIN surface from a session.
"""

from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.security.identity import AuthenticatedPrincipal
from eurogas_nexus.security.permissions import Permission, permission_for_path

TOKEN_HEADERS = {"X-Eurogas-Api-Key": "test-public-api-token"}


def test_an_authenticated_caller_is_the_acting_operator() -> None:
    """A session or key caller needs no principal header, and its own name is the actor."""

    app = create_app(Settings(api_profile="development"))
    session_principal = AuthenticatedPrincipal(
        principal_id="principal-1",
        name="ops-admin",
        principal_type="USER",
        role="ADMIN",
        status="ACTIVE",
        data_scopes=("*",),
        roles=("ADMIN",),
        auth_method="session",
    )
    seen: dict[str, object] = {}

    @app.middleware("http")
    async def _inject_session_identity(request, call_next):  # type: ignore[no-untyped-def]
        request.state.identity = session_principal
        request.state.identity_authenticated = True
        response = await call_next(request)
        seen["actor"] = getattr(request.state, "actor", None)
        return response

    response = TestClient(app).get("/api/access/users")

    assert response.status_code != 401
    assert response.status_code != 403
    assert seen["actor"] == "ops-admin"


def test_operator_routes_require_principal_in_release() -> None:
    assert permission_for_path("/api/credentials/DEEPSEEK") is Permission.OPERATOR
    client = TestClient(create_app(Settings(api_profile="release")))
    body = {"api_key": "test-key", "label": "test"}

    # Token alone is not enough for OPERATOR routes.
    response = client.put("/api/credentials/DEEPSEEK", headers=TOKEN_HEADERS, json=body)
    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "operator_principal_missing"

    # An invalid principal is rejected.
    response = client.put(
        "/api/credentials/DEEPSEEK",
        headers={**TOKEN_HEADERS, "X-Eurogas-Principal": "bad principal!"},
        json=body,
    )
    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "operator_principal_invalid"

    # A valid principal passes the permission gate (route then runs).
    response = client.put(
        "/api/credentials/DEEPSEEK",
        headers={**TOKEN_HEADERS, "X-Eurogas-Principal": "operator-alice"},
        json=body,
    )
    assert response.status_code != 401
    assert response.status_code != 403


def test_read_routes_do_not_require_principal_in_release() -> None:
    client = TestClient(create_app(Settings(api_profile="release")))

    response = client.get(
        "/api/route-cost/tso-tariffs",
        headers=TOKEN_HEADERS,
    )

    assert response.status_code != 401
    assert response.status_code != 403


def test_operator_routes_are_enforced_in_development_too() -> None:
    """D1: the operator-principal gate is no longer a release-only behaviour.

    This test used to pin the opposite - that the development profile installed no route-permission
    dependency, so an OPERATOR route was reachable without a principal. Every profile identifies its
    callers now, so the same request is refused for the same reason it is refused in release, and
    the same request with a valid principal passes.
    """

    client = TestClient(create_app(Settings(api_profile="development")))

    without_principal = client.put(
        "/api/credentials/DEEPSEEK",
        json={"api_key": "test-key", "label": "test"},
    )
    assert without_principal.status_code == 401
    assert without_principal.json()["detail"]["error"] == "operator_principal_missing"

    with_principal = client.put(
        "/api/credentials/DEEPSEEK",
        headers={"X-Eurogas-Principal": "operator-alice"},
        json={"api_key": "test-key", "label": "test"},
    )
    assert with_principal.status_code != 401
    assert with_principal.status_code != 403


def test_write_operator_routes_require_principal_too() -> None:
    client = TestClient(create_app(Settings(api_profile="release")))

    response = client.post(
        "/api/credentials/DEEPSEEK/rotate",
        headers=TOKEN_HEADERS,
        json={},
    )
    assert response.status_code == 401
