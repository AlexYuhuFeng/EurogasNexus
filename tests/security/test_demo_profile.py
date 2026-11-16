"""The demo route profile: a hosted test/demo server's surface and its tester sign-in.

It is the release surface (no /docs, no /openapi.json, every caller identified) plus the
credential sign-in for the provisioned tester identities, with Secure session cookies. It is
refused in trial and release environments. Credentials are generated per test.
"""

from __future__ import annotations

import secrets

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.api.route_profiles import API_ROUTE_PROFILES, ApiProfileName
from eurogas_nexus.core.config import DEV_LOGIN_PASSWORD_ENV, DEV_LOGIN_USERNAME_ENV, Settings
from eurogas_nexus.core.preflight import check_environment
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.repositories import identity as identity_repository
from eurogas_nexus.security import rate_limit as rate_limit_module
from eurogas_nexus.security.cookie_policy import session_cookie_secure

LOGIN = "/api/dev/auth/login"


@pytest.fixture(autouse=True)
def _reset_rate_limit():
    rate_limit_module._WINDOWS.clear()
    yield
    rate_limit_module._WINDOWS.clear()


@pytest.fixture
def testers(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'demo.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", secrets.token_urlsafe(24))
    names = ["tester", "demo.trader", "demo.risk"]
    with Session(engine) as session:
        for name in [*names, "not.listed"]:
            identity_repository.create_identity_principal(
                session, name=name, display_name=name, role="ANALYST", data_scopes=["*"]
            )
        session.commit()
    password = secrets.token_urlsafe(18)
    monkeypatch.setenv(DEV_LOGIN_USERNAME_ENV, ",".join(names))
    monkeypatch.setenv(DEV_LOGIN_PASSWORD_ENV, password)
    return names, password


def _demo_client() -> TestClient:
    return TestClient(create_app(Settings(api_profile="demo", environment="development")))


def test_demo_profile_is_the_release_surface_plus_the_tester_sign_in():
    profile = API_ROUTE_PROFILES[ApiProfileName.DEMO]
    assert profile.expose_docs is False and profile.expose_openapi is False
    assert profile.require_auth is True and profile.include_internal is False


def test_every_listed_tester_signs_in_with_the_one_password_and_others_cannot(testers):
    names, password = testers
    client = _demo_client()
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
    assert client.get("/api/auth/status").json()["data"]["dev_login"] is True
    for name in names:
        response = _demo_client().post(LOGIN, json={"username": name, "password": password})
        assert response.status_code == 200, name
        cookie = response.headers["set-cookie"]
        assert "Secure" in cookie and "HttpOnly" in cookie  # even over plain http
    wrong = client.post(LOGIN, json={"username": names[0], "password": password + "x"})
    assert wrong.status_code == 401
    unlisted = client.post(LOGIN, json={"username": "not.listed", "password": password})
    assert unlisted.status_code == 401
    assert client.get("/api/me").status_code == 401  # nothing without signing in


def test_sign_in_is_throttled(testers):
    names, _password = testers
    client = _demo_client()
    codes = [
        client.post(LOGIN, json={"username": names[0], "password": "wrong-password"}).status_code
        for _ in range(35)
    ]
    assert codes[-1] == 429


@pytest.mark.parametrize("environment", ["trial", "release"])
def test_the_demo_profile_is_refused_in_trial_and_release(environment):
    with pytest.raises(RuntimeError, match="demo"):
        create_app(Settings(api_profile="demo", environment=environment))


def test_demo_sessions_are_always_secure():
    assert session_cookie_secure(scheme="http", api_profile="demo") is True


def test_preflight_requires_a_strong_tester_password_and_refuses_release():
    base = {
        "EUROGAS_NEXUS_ENV": "development",
        "EUROGAS_NEXUS_API_PROFILE": "demo",
        "EUROGAS_NEXUS_PUBLIC_API_TOKEN": "a-generated-token-for-this-test",
        "EUROGAS_NEXUS_SECRET_KEY": "1mDk0Q0m9K4pXc2rWb7tLzYvHsAeNfRgUjOiPlMnQ4E=",
        "RUNTIME_STORE_DATABASE_URL": "postgresql+pg8000://nexus:pw@db:5432/nexus",
        DEV_LOGIN_USERNAME_ENV: "tester",
    }
    codes = [item.code for item in check_environment(base).findings]
    assert "demo_password_weak" in codes
    strong = {**base, DEV_LOGIN_PASSWORD_ENV: secrets.token_urlsafe(18)}
    errors = [item.code for item in check_environment(strong).findings if item.severity == "error"]
    assert errors == []
    release = {**strong, "EUROGAS_NEXUS_ENV": "release"}
    release_codes = [item.code for item in check_environment(release).findings]
    assert "demo_profile_in_production" in release_codes
