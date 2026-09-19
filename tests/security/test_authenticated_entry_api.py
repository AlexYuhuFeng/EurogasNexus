"""Authentication-first entry: /api/me 401 + development credential login.

The development credential value is generated per test and injected through the
environment; no credential is hardcoded in source or tests.
"""

from __future__ import annotations

import hashlib
import secrets

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import (
    DEV_LOGIN_PASSWORD_ENV,
    DEV_LOGIN_USERNAME_ENV,
    Settings,
)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import IdentityPrincipalRecord
from eurogas_nexus.db.repositories import identity as identity_repository
from eurogas_nexus.security import rate_limit as rate_limit_module

DEV_LOGIN_PATH = "/api/dev/auth/login"


@pytest.fixture(autouse=True)
def _reset_auth_rate_limit():
    """Keep auth-throttle windows from leaking between tests."""

    rate_limit_module._WINDOWS.clear()
    yield
    rate_limit_module._WINDOWS.clear()


@pytest.fixture()
def env_db(tmp_path, monkeypatch):
    db_path = tmp_path / "entry.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    monkeypatch.delenv(DEV_LOGIN_USERNAME_ENV, raising=False)
    monkeypatch.delenv(DEV_LOGIN_PASSWORD_ENV, raising=False)
    return engine


def _configure_dev_credentials(monkeypatch) -> tuple[str, str]:
    """Set per-test development credentials from the environment."""

    username = f"dev-{secrets.token_hex(6)}"
    password = secrets.token_urlsafe(24)
    monkeypatch.setenv(DEV_LOGIN_USERNAME_ENV, username)
    monkeypatch.setenv(DEV_LOGIN_PASSWORD_ENV, password)
    return username, password


def _seed_principal(engine, *, name: str, status: str = "ACTIVE") -> str:
    with Session(engine) as session:
        principal = identity_repository.create_identity_principal(
            session,
            name=name,
            display_name="Development Operator",
            role="OPERATOR",
            data_scopes=["EEX"],
        )
        principal.status = status
        session.commit()
        return principal.principal_id


def _dev_client() -> TestClient:
    return TestClient(create_app(Settings(api_profile="development")))


def test_me_returns_401_without_any_presented_credential(env_db, monkeypatch) -> None:
    """D1: a caller that presents nothing is refused before ``/api/me`` can describe them.

    This test used to rely on the development profile installing no authentication, so the
    compatibility principal answered and ``/api/me`` reported it as unauthenticated. The profile
    now identifies its callers, so the same request is refused at the gate with the stable
    ``authentication_required`` code - which is the stronger statement of the same fact.
    """

    _configure_dev_credentials(monkeypatch)
    monkeypatch.setenv("EUROGAS_NEXUS_TEST_ANONYMOUS", "1")
    try:
        client = _dev_client()

        response = client.get("/api/me")

        # A caller that presents nothing is refused, and the gate that answers first is the
        # deployment-token gate: this deployment has one configured, so its refusal is the one the
        # caller meets (owner decision D1 installed that gate in every profile). The identity
        # dependency keeps its own refusal as a second lock, exercised in
        # ``tests/security/test_public_api_auth.py``.
        assert response.status_code == 401
        assert response.json()["detail"]["error"] == "public_api_token_missing"
    finally:
        monkeypatch.delenv("EUROGAS_NEXUS_TEST_ANONYMOUS", raising=False)


def test_me_returns_principal_for_a_dev_login_session(env_db, monkeypatch) -> None:
    engine = env_db
    username, password = _configure_dev_credentials(monkeypatch)
    principal_id = _seed_principal(engine, name=username)
    client = _dev_client()

    login = client.post(DEV_LOGIN_PATH, json={"username": username, "password": password})

    assert login.status_code == 200
    cookie_header = login.headers["set-cookie"]
    assert "eurogas_session=" in cookie_header
    assert "HttpOnly" in cookie_header
    assert "SameSite=Lax" in cookie_header
    assert "Max-Age=43200" in cookie_header
    payload = login.json()
    assert payload["meta"] == {"research_only": False, "human_review_required": False}
    assert set(payload["data"]) == {
        "authenticated",
        "principal_id",
        "display_name",
        "role",
        "permissions",
    }
    assert payload["data"]["authenticated"] is True
    assert payload["data"]["principal_id"] == principal_id
    assert payload["data"]["display_name"] == "Development Operator"
    assert payload["data"]["role"] == "OPERATOR"
    assert "me.read" in payload["data"]["permissions"]

    session_token = client.cookies.get("eurogas_session")
    assert session_token
    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["data"]["principal_id"] == principal_id
    assert me.json()["data"]["auth_method"] == "session"
    assert me.json()["data"]["csrf_token"]


def test_me_accepts_a_validated_identity_key_in_development(env_db) -> None:
    engine = env_db
    principal_id = _seed_principal(engine, name="dev-key-user")
    with Session(engine) as session:
        _key, bearer = identity_repository.create_identity_api_key(session, principal_id)
        session.commit()
    client = _dev_client()

    response = client.get("/api/me", headers={"X-Eurogas-Identity": bearer})

    assert response.status_code == 200
    assert response.json()["data"]["principal_id"] == principal_id
    assert response.json()["data"]["auth_method"] == "identity_key"


def test_me_rejects_a_stale_session_cookie(env_db) -> None:
    client = _dev_client()

    response = client.get("/api/me", headers={"Cookie": "eurogas_session=stale-token"})

    assert response.status_code == 401
    assert response.json()["detail"]["error"] == "session_invalid"


@pytest.mark.parametrize("profile", ["internal", "release"])
def test_dev_login_is_absent_from_non_development_profiles(
    env_db, monkeypatch, profile,
) -> None:
    _configure_dev_credentials(monkeypatch)
    app = create_app(Settings(api_profile=profile))
    client = TestClient(app)

    response = client.post(
        DEV_LOGIN_PATH,
        json={"username": "whoever", "password": "whatever"},
    )

    assert response.status_code == 404
    assert DEV_LOGIN_PATH not in set(app.openapi()["paths"])
    status = client.get("/api/auth/status").json()["data"]
    assert status["dev_login"] is False


def test_me_keeps_the_legacy_principal_for_a_verified_public_token(
    env_db, monkeypatch,
) -> None:
    """Release-profile SDK/CLI compatibility: verified token, legacy principal."""

    token = secrets.token_urlsafe(24)
    _seed_principal(env_db, name="unrelated-principal")
    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", token)
    client = TestClient(create_app(Settings(api_profile="release")))

    response = client.get("/api/me", headers={"X-Eurogas-Api-Key": token})
    invalid = client.get("/api/me", headers={"X-Eurogas-Api-Key": "not-the-token"})

    assert response.status_code == 200
    assert response.json()["data"]["principal_id"] == "service:public-api"
    assert response.json()["data"]["auth_method"] == "legacy_public_token"
    assert invalid.status_code == 403
    assert invalid.json()["detail"]["error"] == "public_api_token_invalid"


def test_dev_login_is_disabled_when_credentials_are_unconfigured(env_db) -> None:
    client = _dev_client()

    response = client.post(
        DEV_LOGIN_PATH,
        json={"username": "whoever", "password": "whatever"},
    )

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "dev_login_disabled"
    assert client.get("/api/auth/status").json()["data"]["dev_login"] is False


def test_dev_login_rejects_wrong_credentials(env_db, monkeypatch) -> None:
    engine = env_db
    username, password = _configure_dev_credentials(monkeypatch)
    _seed_principal(engine, name=username)
    client = _dev_client()

    wrong_password = client.post(
        DEV_LOGIN_PATH,
        json={"username": username, "password": secrets.token_urlsafe(24)},
    )
    wrong_username = client.post(
        DEV_LOGIN_PATH,
        json={"username": f"other-{secrets.token_hex(4)}", "password": password},
    )

    for response in (wrong_password, wrong_username):
        assert response.status_code == 401
        assert response.json()["detail"]["error"] == "invalid_credentials"
        assert "eurogas_session" not in response.headers.get("set-cookie", "")


def test_dev_login_requires_an_existing_active_identity(env_db, monkeypatch) -> None:
    engine = env_db
    username, password = _configure_dev_credentials(monkeypatch)
    client = _dev_client()

    unprovisioned = client.post(
        DEV_LOGIN_PATH,
        json={"username": username, "password": password},
    )
    assert unprovisioned.status_code == 403
    assert unprovisioned.json()["detail"]["error"] == "identity_not_provisioned"

    _seed_principal(engine, name=username, status="PENDING")
    pending = client.post(
        DEV_LOGIN_PATH,
        json={"username": username, "password": password},
    )
    assert pending.status_code == 403
    assert pending.json()["detail"]["error"] == "identity_not_provisioned"

    # No principal was invented by the failed attempts.
    with Session(engine) as session:
        assert session.query(IdentityPrincipalRecord).count() == 1


def test_dev_login_resolves_an_existing_principal_by_email(env_db, monkeypatch) -> None:
    engine = env_db
    username, password = _configure_dev_credentials(monkeypatch)
    email = f"{username}@example.test"
    with Session(engine) as session:
        principal = identity_repository.create_identity_principal(
            session,
            name=f"principal-{username}",
            display_name="Email Operator",
            role="ANALYST",
            data_scopes=[],
        )
        principal.email = email
        session.commit()
        principal_id = principal.principal_id
    monkeypatch.setenv(DEV_LOGIN_USERNAME_ENV, email)
    client = _dev_client()

    login = client.post(DEV_LOGIN_PATH, json={"username": email, "password": password})

    assert login.status_code == 200
    assert login.json()["data"]["principal_id"] == principal_id
    assert login.json()["data"]["role"] == "ANALYST"


def test_auth_status_reports_dev_login_only_when_mounted_and_configured(
    env_db, monkeypatch,
) -> None:
    client = _dev_client()
    baseline = client.get("/api/auth/status")
    assert baseline.status_code == 200
    assert baseline.json()["data"]["dev_login"] is False
    # Existing keys are unchanged.
    assert set(baseline.json()["data"]) == {
        "oidc_configured",
        "session_cookie",
        "profile",
        "dev_login",
    }
    _configure_dev_credentials(monkeypatch)

    configured = client.get("/api/auth/status")

    assert configured.json()["data"]["dev_login"] is True


def test_dev_login_issues_a_revocable_backend_session(env_db, monkeypatch) -> None:
    """The revoked session is not a credential any more.

    The client is built without the suite's deployment token (``EUROGAS_NEXUS_TEST_ANONYMOUS``), so
    the session cookie is the *only* credential this request could carry: after logout there is
    nothing left to authenticate with, and the answer is the gate's refusal rather than a fresh
    compatibility principal.
    """

    engine = env_db
    username, password = _configure_dev_credentials(monkeypatch)
    _seed_principal(engine, name=username)
    monkeypatch.setenv("EUROGAS_NEXUS_TEST_ANONYMOUS", "1")
    try:
        client = _dev_client()

        login = client.post(
            DEV_LOGIN_PATH, json={"username": username, "password": password}
        )
        assert login.status_code == 200
        session_token = client.cookies.get("eurogas_session")
        assert session_token

        logout = client.post(
            "/api/auth/logout",
            headers={
                "Origin": "http://testserver",
                "X-Eurogas-CSRF": hashlib.sha256(
                    session_token.encode("utf-8")
                ).hexdigest()[:32],
            },
        )

        assert logout.status_code == 200
        assert client.get("/api/me").status_code == 401
    finally:
        monkeypatch.delenv("EUROGAS_NEXUS_TEST_ANONYMOUS", raising=False)


def test_rejected_jit_registration_is_committed_before_the_login_fails(monkeypatch) -> None:
    """Registration is not approval, but it must survive the rejected login.

    A just-in-time identity that is not approved yet fails closed; committing
    the pending principal and its issuer+subject link is what lets an
    administrator see and activate the identity afterwards. Any other OIDC
    validation failure must keep rolling back.
    """

    from eurogas_nexus.api.routes.public import auth as auth_routes
    from eurogas_nexus.application import enterprise_auth
    from eurogas_nexus.security.oidc import OidcValidationError

    class _RecordingSession:
        def __init__(self) -> None:
            self.commits = 0

        def __enter__(self) -> _RecordingSession:
            return self

        def __exit__(self, *_exc: object) -> bool:
            return False

        def commit(self) -> None:
            self.commits += 1

    def _callback_with_failure(code: str):
        session = _RecordingSession()
        monkeypatch.setattr(auth_routes, "_require_db", lambda: None)
        monkeypatch.setattr(auth_routes, "_session", lambda: session)

        def _fail(*_args: object, **_kwargs: object) -> None:
            raise OidcValidationError(
                code=code,
                status_code=403 if code == "identity_pending_approval" else 400,
                message="Identity cannot complete sign-in.",
            )

        monkeypatch.setattr(enterprise_auth, "complete_browser_login", _fail)
        monkeypatch.setattr(auth_routes, "_oidc_error", lambda exc: HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ))
        client = TestClient(create_app(Settings(api_profile="development")))
        response = client.get("/api/auth/oidc/callback?code=code-1&state=state-1")
        return response, session

    pending, pending_session = _callback_with_failure("identity_pending_approval")
    assert pending.status_code == 403
    assert pending_session.commits == 1

    rejected, rejected_session = _callback_with_failure("oidc_token_invalid")
    assert rejected.status_code == 400
    assert rejected_session.commits == 0
