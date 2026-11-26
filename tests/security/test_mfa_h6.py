"""Local accounts: TOTP second factor, session lifetimes, and no silent fallback (H6)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.security import totp

KEY = "a" * 43 + "="


def test_rfc6238_reference_vector():
    # RFC 6238 appendix B, SHA-1, T = 59 s: 94287082 (8 digits) -> last 6 digits.
    secret = __import__("base64").b32encode(b"12345678901234567890").decode()
    assert totp.hotp(secret, 59 // 30) == "287082"
    assert totp.verify(secret, "287082", now=59) == 1
    assert totp.verify(secret, "287082", last_step=1, now=59) is None  # used once


@pytest.fixture
def app_with_account(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'mfa.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_SECRET_KEY", KEY)
    monkeypatch.setenv("EUROGAS_NEXUS_LOCAL_ACCOUNTS", "on")
    monkeypatch.setenv("EUROGAS_NEXUS_TEST_ANONYMOUS", "1")
    from eurogas_nexus.application import local_accounts

    with Session(engine) as session:
        row, secret = local_accounts.create_local_account(
            session, username="risk.anna", display_name="Anna", email=None,
            grants=local_accounts.AccountGrants(roles=("REVIEWER",)), actor="setup",
        )
        session.commit()
    client = TestClient(create_app())
    first = client.post("/api/auth/login", json={"username": "risk.anna", "password": secret})
    change = first.json()["data"]["change_token"]
    signed = client.post(
        "/api/auth/password-change",
        json={"change_token": change, "new_password": "correct horse battery staple 9"},
    )
    assert signed.status_code == 200, signed.text
    return client, engine


def _guard(client) -> None:
    """Send what a browser sends with a cookie session: its origin and CSRF token."""

    from eurogas_nexus.api.middleware.origin_csrf import csrf_for_session

    token = client.cookies.get("eurogas_session")
    client.headers.update(
        {"Origin": "http://testserver", "X-Eurogas-CSRF": csrf_for_session(token)}
    )


def _code(secret: str) -> str:
    return totp.hotp(secret, totp.current_step())


def test_enrol_then_sign_in_needs_the_code(app_with_account):
    client, _engine = app_with_account
    _guard(client)
    response = client.post("/api/me/mfa/enrol")
    assert response.status_code == 200, response.text
    enrol = response.json()["data"]
    assert enrol["otpauth_uri"].startswith("otpauth://totp/")
    assert client.post("/api/me/mfa/confirm", json={"code": "000000"}).status_code == 401
    confirmed = client.post("/api/me/mfa/confirm", json={"code": _code(enrol["secret"])})
    codes = confirmed.json()["data"]["recovery_codes"]
    assert len(codes) == 10
    client.post("/api/auth/logout")
    client.cookies.clear()
    client.headers.pop("X-Eurogas-CSRF", None)

    step = client.post(
        "/api/auth/login",
        json={"username": "risk.anna", "password": "correct horse battery staple 9"},
    ).json()["data"]
    assert step["mfa_required"] is True and step["authenticated"] is False
    assert "eurogas_session" not in client.cookies
    wrong = client.post("/api/auth/mfa/verify", json={"mfa_token": step["mfa_token"],
                                                      "code": "123456"})
    assert wrong.status_code == 401
    ok = client.post("/api/auth/mfa/verify",
                     json={"mfa_token": step["mfa_token"], "recovery_code": codes[0]})
    assert ok.status_code == 200 and ok.json()["data"]["authenticated"] is True
    # A recovery code works once; the token too.
    again = client.post("/api/auth/mfa/verify",
                        json={"mfa_token": step["mfa_token"], "recovery_code": codes[0]})
    assert again.status_code == 401


def test_policy_forces_enrolment_before_anything_else(tmp_path, monkeypatch):
    monkeypatch.setenv("EUROGAS_NEXUS_MFA_REQUIRED", "privileged")
    url = f"sqlite+pysqlite:///{(tmp_path / 'p.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_SECRET_KEY", KEY)
    monkeypatch.setenv("EUROGAS_NEXUS_LOCAL_ACCOUNTS", "on")
    monkeypatch.setenv("EUROGAS_NEXUS_TEST_ANONYMOUS", "1")
    from eurogas_nexus.application import local_accounts

    with Session(engine) as session:
        _row, secret = local_accounts.create_local_account(
            session, username="admin.bo", display_name="Bo", email=None,
            grants=local_accounts.AccountGrants(roles=("ADMIN",)), actor="setup",
        )
        session.commit()
    client = TestClient(create_app())
    change = client.post(
        "/api/auth/login", json={"username": "admin.bo", "password": secret}
    ).json()["data"]["change_token"]
    signed = client.post(
        "/api/auth/password-change",
        json={"change_token": change, "new_password": "correct horse battery staple 9"},
    ).json()["data"]
    assert signed["mfa_enrolment_required"] is True
    _guard(client)
    assert client.get("/api/access/users").status_code == 403
    enrol = client.post("/api/me/mfa/enrol").json()["data"]
    client.post("/api/me/mfa/confirm", json={"code": _code(enrol["secret"])})
    assert client.get("/api/access/users").status_code == 200


def test_production_does_not_fall_back_to_local_accounts(monkeypatch):
    from eurogas_nexus.security.local_accounts_policy import (
        assert_sign_in_configured,
        local_accounts_enabled,
    )

    env = {"EUROGAS_NEXUS_ENV": "release"}
    assert local_accounts_enabled(env) is False
    with pytest.raises(RuntimeError, match="No sign-in is configured"):
        assert_sign_in_configured("release", env)
    assert_sign_in_configured("release", {**env, "EUROGAS_NEXUS_LOCAL_ACCOUNTS": "on"})
    assert local_accounts_enabled({"EUROGAS_NEXUS_ENV": "development"}) is True


def test_release_profile_never_defaults_to_development(monkeypatch):
    from eurogas_nexus.core.config import runtime_environment

    assert runtime_environment({"EUROGAS_NEXUS_API_PROFILE": "release"}) == "release"
    assert runtime_environment({}) == "development"


def test_session_lifetimes_are_settings_with_safer_production_defaults(monkeypatch):
    from eurogas_nexus.db.repositories import security

    monkeypatch.setenv("EUROGAS_NEXUS_ENV", "release")
    assert security.session_idle_ttl() == timedelta(minutes=30)
    assert security.session_absolute_ttl() == timedelta(hours=10)
    monkeypatch.setenv("EUROGAS_NEXUS_SESSION_IDLE_MINUTES", "15")
    assert security.session_idle_ttl() == timedelta(minutes=15)
