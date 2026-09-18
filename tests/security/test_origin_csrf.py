"""CR-10 origin/CSRF guard tests."""

from __future__ import annotations

import hashlib
import secrets

import pytest
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
from eurogas_nexus.db.repositories import identity as identity_repository
from eurogas_nexus.db.repositories.security import create_session
from eurogas_nexus.security import rate_limit as rate_limit_module


def _setup(tmp_path, monkeypatch):
    db_path = tmp_path / "csrf.sqlite"
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    token = "csrf-session-token"
    with Session(engine) as session:
        principal = identity_repository.create_identity_principal(
            session,
            name="csrf-user",
            display_name="CSRF User",
            role="VIEWER",
            data_scopes=[],
        )
        create_session(session, principal_id=principal.principal_id, token=token)
        session.commit()
    return token


def test_cookie_mutation_requires_origin_and_csrf(tmp_path, monkeypatch) -> None:
    token = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app(Settings(api_profile="release")))
    cookie = f"eurogas_session={token}"

    missing = client.post("/api/auth/logout", headers={"Cookie": cookie})
    assert missing.status_code == 403
    assert missing.json()["error"] == "origin_not_allowed"
    # This middleware sits outside the one that stamps a request id, so a rejection here used
    # to answer with a bare error code: a user had nothing to quote and a client could not
    # classify the refusal. It now answers in the product's error shape, id included.
    assert missing.json()["family"] == "AUTH"
    assert missing.json()["recoverability"] == "after_user_action"
    assert missing.json()["correlation_id"]
    assert missing.headers["x-request-id"] == missing.json()["correlation_id"]

    wrong_csrf = client.post(
        "/api/auth/logout",
        headers={"Cookie": cookie, "Origin": "http://testserver", "X-Eurogas-CSRF": "bad"},
    )
    assert wrong_csrf.status_code == 403
    assert wrong_csrf.json()["error"] == "csrf_invalid"
    assert wrong_csrf.json()["family"] == "AUTH"
    # The endpoint's own `detail` shape is kept, so a client reading it is unaffected.
    assert wrong_csrf.json()["detail"]["error"] == "csrf_invalid"

    csrf = hashlib.sha256(token.encode("utf-8")).hexdigest()[:32]
    ok = client.post(
        "/api/auth/logout",
        headers={
            "Cookie": cookie,
            "Origin": "http://testserver",
            "X-Eurogas-CSRF": csrf,
        },
    )
    assert ok.status_code == 200


def test_api_key_mutations_are_not_cookie_guarded(tmp_path, monkeypatch) -> None:
    _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", "public-token")
    client = TestClient(create_app(Settings(api_profile="release")))
    response = client.post(
        "/api/auth/logout",
        headers={"X-Eurogas-Api-Key": "public-token"},
    )
    # No cookie -> no origin guard; the route itself is permitted.
    assert response.status_code == 200


@pytest.fixture(autouse=True)
def _reset_auth_rate_limit():
    """Keep auth-throttle windows from leaking between tests."""

    rate_limit_module._WINDOWS.clear()
    yield
    rate_limit_module._WINDOWS.clear()


def test_login_paths_are_csrf_exempt_even_with_a_stale_session_cookie(
    tmp_path, monkeypatch,
) -> None:
    """A stale cookie must not block the login POST; other writes stay guarded."""

    token = _setup(tmp_path, monkeypatch)
    username = f"dev-{secrets.token_hex(6)}"
    password = secrets.token_urlsafe(24)
    monkeypatch.setenv(DEV_LOGIN_USERNAME_ENV, username)
    monkeypatch.setenv(DEV_LOGIN_PASSWORD_ENV, password)
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'csrf.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    with Session(engine) as session:
        identity_repository.create_identity_principal(
            session,
            name=username,
            display_name="CSRF Dev Operator",
            role="OPERATOR",
            data_scopes=[],
        )
        session.commit()
    client = TestClient(create_app(Settings(api_profile="development")))
    stale = {"Cookie": f"eurogas_session={token}"}

    login = client.post(
        "/api/dev/auth/login",
        headers=stale,
        json={"username": username, "password": password},
    )

    assert login.status_code == 200, login.text
    assert "eurogas_session=" in login.headers["set-cookie"]

    # An unrelated mutating route is still origin+CSRF guarded.
    blocked = client.post("/api/route-cost/recommend", headers=stale, json={})
    assert blocked.status_code == 403
    assert blocked.json()["error"] == "origin_not_allowed"

    # Logout (same cookie, same profile) stays guarded as well.
    logout = client.post("/api/auth/logout", headers=stale)
    assert logout.status_code == 403
    assert logout.json()["error"] == "origin_not_allowed"
