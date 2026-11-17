"""Local accounts and SSO pre-provisioning (Admin -> Users), end to end on SQLite.

Covers: an administrator creates a local account and receives a one-time password once; the
person signs in with it, must choose a password (policy enforced), and gets a session; a
uniform refusal for every failed sign-in; per-account back-off and per-address throttle;
disable ends every session; reset issues a new one-time password; delete only without
history; the last active administrator cannot be disabled, demoted or deleted; only ADMIN may
do any of it (a job function never grants it); the audit trail names who, whom and what and
never a password or token; demo test accounts never sign in outside the demo profile.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.application import local_accounts
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    AuditEventRecord,
    IdentityLocalCredentialRecord,
    IdentityPrincipalRecord,
)
from eurogas_nexus.db.repositories import identity as identity_repository
from eurogas_nexus.security import passwords
from eurogas_nexus.security import rate_limit as rate_limit_module

PUBLIC_TOKEN = "test-public-api-token"
NEW_PASSWORD = "a calm and long pass phrase"


@pytest.fixture(autouse=True)
def _fast_kdf_and_clean_throttles(monkeypatch):
    # The production parameters cost 32 MiB and ~0.1 s per derivation; tests use small ones.
    monkeypatch.setattr(passwords, "DEFAULT_KDF_PARAMS", {"n": 2**10, "r": 8, "p": 1, "dklen": 32})
    monkeypatch.setattr(passwords, "_DUMMY", None)
    monkeypatch.delenv("EUROGAS_NEXUS_OIDC_ISSUER", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_OIDC_CLIENT_ID", raising=False)
    monkeypatch.delenv(local_accounts.LOCAL_ACCOUNTS_ENV, raising=False)
    monkeypatch.delenv(local_accounts.DEMO_TEST_ACCOUNTS_ENV, raising=False)
    rate_limit_module._WINDOWS.clear()
    local_accounts.reset_address_throttle()
    yield
    rate_limit_module._WINDOWS.clear()
    local_accounts.reset_address_throttle()


@pytest.fixture
def store(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'accounts.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", PUBLIC_TOKEN)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with Session(engine) as session:
        admin = identity_repository.create_identity_principal(
            session, name="first-admin", display_name="First Admin", role="ADMIN"
        )
        admin.roles = ["ADMIN"]
        _key, admin_bearer = identity_repository.create_identity_api_key(
            session, admin.principal_id
        )
        analyst = identity_repository.create_identity_principal(
            session, name="an-analyst", display_name="Analyst", role="ANALYST"
        )
        # A declared job function is composition only: it must never grant administration.
        analyst.job_functions = ["PLATFORM_ADMINISTRATOR"]
        _key, analyst_bearer = identity_repository.create_identity_api_key(
            session, analyst.principal_id
        )
        session.commit()
        ids = {"admin": admin.principal_id, "analyst": analyst.principal_id}
    return engine, ids, {"admin": admin_bearer, "analyst": analyst_bearer}


def _admin(bearer: str) -> dict[str, str]:
    return {"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer}


def _client() -> TestClient:
    # Release session cookies are Secure, so the test browser speaks https.
    return TestClient(create_app(Settings(api_profile="release")), base_url="https://testserver")


def _create_local(client, bearer, username="jane.trader", roles=("ANALYST",)) -> tuple[str, str]:
    response = client.post(
        "/api/access/users",
        headers=_admin(bearer),
        json={
            "kind": "local",
            "username": username,
            "display_name": "Jane Trader",
            "roles": list(roles),
            "job_functions": ["TRADER"],
            "office": "UK",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["user"]["account_kind"] == "local"
    assert data["user"]["account_state"] == "INVITED"
    return data["user"]["principal_id"], data["one_time_password"]


def _first_sign_in(client, username, secret) -> str:
    step = client.post("/api/auth/login", json={"username": username, "password": secret})
    assert step.status_code == 200, step.text
    data = step.json()["data"]
    assert data["password_change_required"] is True and "set-cookie" not in step.headers
    done = client.post(
        "/api/auth/password-change",
        json={"change_token": data["change_token"], "new_password": NEW_PASSWORD},
    )
    assert done.status_code == 200, done.text
    return done.cookies.get("eurogas_session") or done.headers["set-cookie"].split(";")[0].split(
        "="
    )[1]


def _audit(engine) -> list[AuditEventRecord]:
    with Session(engine) as session:
        return session.query(AuditEventRecord).all()


def test_status_advertises_local_sign_in_only_without_sso(store, monkeypatch):
    client = _client()
    assert client.get("/api/auth/status").json()["data"]["local_login"] is True
    monkeypatch.setenv("EUROGAS_NEXUS_OIDC_ISSUER", "https://idp.example.test")
    monkeypatch.setenv("EUROGAS_NEXUS_OIDC_CLIENT_ID", "nexus")
    assert client.get("/api/auth/status").json()["data"]["local_login"] is False
    monkeypatch.setenv(local_accounts.LOCAL_ACCOUNTS_ENV, "on")
    assert client.get("/api/auth/status").json()["data"]["local_login"] is True
    monkeypatch.delenv("EUROGAS_NEXUS_OIDC_ISSUER")
    monkeypatch.setenv(local_accounts.LOCAL_ACCOUNTS_ENV, "off")
    assert client.get("/api/auth/status").json()["data"]["local_login"] is False


def test_local_account_lifecycle_first_sign_in_and_forced_change(store):
    engine, ids, bearers = store
    client = _client()
    principal_id, secret = _create_local(client, bearers["admin"])

    listed = client.get("/api/access/users", headers=_admin(bearers["admin"])).json()
    assert listed["meta"]["account_options"]["local_accounts"] is True
    row = next(item for item in listed["data"] if item["principal_id"] == principal_id)
    assert row["local_password"]["must_change_password"] is True
    assert "salt" not in str(row) and secret not in str(listed)

    # The temporary password opens no session and cannot be kept as the new password.
    step = client.post("/api/auth/login", json={"username": "jane.trader", "password": secret})
    token = step.json()["data"]["change_token"]
    weak = client.post(
        "/api/auth/password-change", json={"change_token": token, "new_password": "short"}
    )
    assert weak.status_code == 422 and weak.json()["detail"]["code"] == "password_too_short"
    reused = client.post(
        "/api/auth/password-change", json={"change_token": token, "new_password": secret}
    )
    assert reused.json()["detail"]["code"] == "password_reused"
    named = client.post(
        "/api/auth/password-change",
        json={"change_token": token, "new_password": "jane.trader-forever"},
    )
    assert named.json()["detail"]["code"] == "password_contains_username"
    done = client.post(
        "/api/auth/password-change", json={"change_token": token, "new_password": NEW_PASSWORD}
    )
    assert done.status_code == 200
    assert "HttpOnly" in done.headers["set-cookie"]
    # The change token was single-use.
    again = client.post(
        "/api/auth/password-change", json={"change_token": token, "new_password": NEW_PASSWORD}
    )
    assert again.status_code == 401

    me = client.get("/api/me")
    assert me.status_code == 200 and me.json()["data"]["principal_id"] == principal_id
    # The temporary password no longer works; the chosen one does, by name or case-folded.
    fresh = _client()
    old = fresh.post("/api/auth/login", json={"username": "jane.trader", "password": secret})
    assert old.status_code == 401
    ok = fresh.post("/api/auth/login", json={"username": "Jane.Trader", "password": NEW_PASSWORD})
    assert ok.status_code == 200 and ok.json()["data"]["password_change_required"] is False
    with Session(engine) as session:
        credential = session.get(IdentityLocalCredentialRecord, principal_id)
        assert credential.must_change_password is False and credential.change_token_hash is None
        principal = session.get(IdentityPrincipalRecord, principal_id)
        assert principal.last_login_at_utc is not None
        assert principal.job_functions == ["TRADER"] and principal.roles == ["ANALYST"]


def test_uniform_refusal_back_off_and_unlock(store):
    engine, ids, bearers = store
    client = _client()
    principal_id, secret = _create_local(client, bearers["admin"])
    _first_sign_in(client, "jane.trader", secret)

    unknown = client.post("/api/auth/login", json={"username": "nobody", "password": "x" * 12})
    wrong = client.post("/api/auth/login", json={"username": "jane.trader", "password": "x" * 12})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["detail"] == wrong.json()["detail"]
    for _ in range(local_accounts.MAX_FAILED_ATTEMPTS - 1):
        client.post("/api/auth/login", json={"username": "jane.trader", "password": "y" * 12})
    # Locked: even the right password is refused, with the same answer.
    locked = client.post(
        "/api/auth/login", json={"username": "jane.trader", "password": NEW_PASSWORD}
    )
    assert locked.status_code == 401 and locked.json()["detail"] == wrong.json()["detail"]
    users = _client().get("/api/access/users", headers=_admin(bearers["admin"])).json()["data"]
    row = next(item for item in users if item["principal_id"] == principal_id)
    assert row["account_state"] == "LOCKED" and row["local_password"]["locked_until_utc"]
    actions = [event.action for event in _audit(engine)]
    assert "auth.local.locked" in actions

    # Enabling the account lifts the back-off (an administrator's own client).
    enabled = _client().patch(
        f"/api/access/users/{principal_id}",
        headers=_admin(bearers["admin"]),
        json={"status": "ACTIVE"},
    )
    assert enabled.status_code == 200 and enabled.json()["data"]["account_state"] == "ACTIVE"
    local_accounts.reset_address_throttle()
    assert (
        client.post(
            "/api/auth/login", json={"username": "jane.trader", "password": NEW_PASSWORD}
        ).status_code
        == 200
    )


def test_back_off_doubles_and_is_capped():
    assert local_accounts.lockout_duration(4) is None
    assert local_accounts.lockout_duration(5) == timedelta(minutes=15)
    assert local_accounts.lockout_duration(7) is None
    assert local_accounts.lockout_duration(10) == timedelta(minutes=30)
    assert local_accounts.lockout_duration(500) == timedelta(hours=24)


def test_per_address_throttle(store):
    _engine, _ids, _bearers = store
    client = _client()
    codes = []
    for attempt in range(local_accounts.MAX_ADDRESS_FAILURES + 1):
        rate_limit_module._WINDOWS.clear()  # isolate this throttle from the generic one
        codes.append(
            client.post(
                "/api/auth/login", json={"username": f"user{attempt}", "password": "z" * 12}
            ).status_code
        )
    assert codes[:-1] == [401] * local_accounts.MAX_ADDRESS_FAILURES
    assert codes[-1] == 429


def test_disable_ends_sessions_and_reset_issues_a_new_one_time_password(store):
    engine, ids, bearers = store
    client = _client()
    principal_id, secret = _create_local(client, bearers["admin"])
    _first_sign_in(client, "jane.trader", secret)
    assert client.get("/api/me").status_code == 200

    admin = _client()
    disabled = admin.patch(
        f"/api/access/users/{principal_id}",
        headers=_admin(bearers["admin"]),
        json={"status": "DISABLED"},
    )
    assert disabled.status_code == 200 and disabled.json()["data"]["account_state"] == "DISABLED"
    assert client.get("/api/me").status_code == 401  # the session ended
    refused = _client().post(
        "/api/auth/login", json={"username": "jane.trader", "password": NEW_PASSWORD}
    )
    assert refused.status_code == 401

    admin.patch(
        f"/api/access/users/{principal_id}",
        headers=_admin(bearers["admin"]),
        json={"status": "ACTIVE"},
    )
    reset = admin.post(
        f"/api/access/users/{principal_id}/reset-password", headers=_admin(bearers["admin"])
    )
    assert reset.status_code == 200
    new_secret = reset.json()["data"]["one_time_password"]
    assert new_secret != secret
    old = _client().post(
        "/api/auth/login", json={"username": "jane.trader", "password": NEW_PASSWORD}
    )
    assert old.status_code == 401
    step = _client().post(
        "/api/auth/login", json={"username": "jane.trader", "password": new_secret}
    )
    assert step.json()["data"]["password_change_required"] is True

    # Audit: who, whom, what - never a password, a temporary password or a token.
    events = _audit(engine)
    text = " ".join(f"{e.action} {e.resource} {e.detail} {e.principal}" for e in events)
    for value in (secret, new_secret, NEW_PASSWORD):
        assert value not in text
    reset_event = next(e for e in events if e.action == "access.user.password_reset")
    assert reset_event.principal == ids["admin"]
    assert reset_event.resource == f"identity_principal:{principal_id}"
    created = next(e for e in events if e.action == "access.user.create")
    assert "roles=['ANALYST']" in created.detail


def test_own_password_change_requires_the_current_one_and_ends_other_sessions(store):
    _engine, _ids, bearers = store
    client = _client()
    _principal_id, secret = _create_local(client, bearers["admin"])
    _first_sign_in(client, "jane.trader", secret)
    other = _client()
    other.post("/api/auth/login", json={"username": "jane.trader", "password": NEW_PASSWORD})
    assert other.get("/api/me").status_code == 200

    session_token = client.cookies.get("eurogas_session")
    csrf = hashlib.sha256(session_token.encode()).hexdigest()[:32]
    guarded = {
        "Origin": "https://testserver",
        "X-Forwarded-Proto": "https",
        "X-Eurogas-CSRF": csrf,
    }
    wrong = client.post(
        "/api/me/password",
        headers=guarded,
        json={"current_password": "not the password", "new_password": "another long phrase"},
    )
    assert wrong.status_code == 403
    changed = client.post(
        "/api/me/password",
        headers=guarded,
        json={"current_password": NEW_PASSWORD, "new_password": "another long phrase"},
    )
    assert changed.status_code == 200, changed.text
    assert other.get("/api/me").status_code == 401
    assert client.get("/api/me").status_code == 200  # this browser got a fresh session


def test_only_admin_manages_users_and_a_job_function_grants_nothing(store):
    _engine, ids, bearers = store
    client = _client()
    body = {"kind": "local", "username": "someone", "roles": ["ADMIN"]}
    denied = client.post("/api/access/users", headers=_admin(bearers["analyst"]), json=body)
    assert denied.status_code == 403
    for method, path in (
        ("post", f"/api/access/users/{ids['admin']}/reset-password"),
        ("delete", f"/api/access/users/{ids['admin']}"),
    ):
        response = getattr(client, method)(path, headers=_admin(bearers["analyst"]))
        assert response.status_code == 403, path
    # Anonymous callers are refused as well.
    assert client.post("/api/access/users", json=body).status_code in {401, 403}


def test_last_active_administrator_cannot_be_disabled_demoted_or_deleted(store):
    engine, ids, bearers = store
    client = _client()
    headers = _admin(bearers["admin"])
    path = f"/api/access/users/{ids['admin']}"
    second_id, _secret = _create_local(client, bearers["admin"], "second.admin", roles=("ADMIN",))
    # Two active administrators: the second may be disabled, enabled and demoted.
    second = f"/api/access/users/{second_id}"
    assert client.patch(second, headers=headers, json={"status": "DISABLED"}).status_code == 200
    assert client.patch(second, headers=headers, json={"status": "ACTIVE"}).status_code == 200
    # A disabled administrator does not count: the first one is now the last.
    assert client.patch(second, headers=headers, json={"status": "DISABLED"}).status_code == 200
    for body in ({"status": "DISABLED"}, {"status": "LOCKED"}):
        refused = client.patch(path, headers=headers, json=body)
        assert refused.status_code == 409, body
        assert refused.json()["detail"]["code"] == "last_administrator"
    assert client.delete(path, headers=headers).status_code == 409
    assert client.get("/api/access/users", headers=headers).status_code == 200  # still in
    with Session(engine) as session:
        row = session.get(IdentityPrincipalRecord, ids["admin"])
        assert row.status == "ACTIVE"
        # The same guard serves demotion (a second administrator demoting the last one).
        with pytest.raises(local_accounts.LocalAccountError) as raised:
            local_accounts.ensure_not_last_administrator(session, row)
        assert raised.value.code == "last_administrator"
        session.get(IdentityPrincipalRecord, second_id).status = "ACTIVE"
        session.commit()
    # With the second active again, the first may be demoted by the second.
    with Session(engine) as session:
        _key, second_bearer = identity_repository.create_identity_api_key(session, second_id)
        session.commit()
    demoted = client.patch(path, headers=_admin(second_bearer), json={"roles": ["VIEWER"]})
    assert demoted.status_code == 200, demoted.text
    # ... and now the second is the last one: the first (no longer an admin) cannot act,
    # and a demotion of the second through the guard is refused.
    with Session(engine) as session:
        last = session.get(IdentityPrincipalRecord, second_id)
        assert local_accounts.active_administrator_ids(session) == {second_id}
        with pytest.raises(local_accounts.LocalAccountError):
            local_accounts.ensure_not_last_administrator(session, last)
    events = [e for e in _audit(engine) if e.action == "access.user.update"]
    assert any(e.outcome == "denied" and "last active administrator" in e.detail for e in events)


def test_delete_only_without_history(store):
    engine, ids, bearers = store
    client = _client()
    headers = _admin(bearers["admin"])
    never_id, _secret = _create_local(client, bearers["admin"], "never.signed")
    used_id, used_secret = _create_local(client, bearers["admin"], "has.history")
    _first_sign_in(_client(), "has.history", used_secret)
    # The list says in advance which delete the server would accept.
    listed = {
        row["principal_id"]: row["deletable"]
        for row in client.get("/api/access/users", headers=headers).json()["data"]
    }
    assert listed[never_id] is True and listed[used_id] is False and listed[ids["admin"]] is False
    kept = client.delete(f"/api/access/users/{used_id}", headers=headers)
    assert kept.status_code == 409 and kept.json()["detail"]["code"] == "user_has_history"
    gone = client.delete(f"/api/access/users/{never_id}", headers=headers)
    assert gone.status_code == 200
    with Session(engine) as session:
        assert session.get(IdentityPrincipalRecord, never_id) is None
        assert session.get(IdentityLocalCredentialRecord, never_id) is None
    assert any(e.action == "access.user.delete" for e in _audit(engine))


def test_local_creation_refused_when_turned_off(store, monkeypatch):
    _engine, _ids, bearers = store
    monkeypatch.setenv(local_accounts.LOCAL_ACCOUNTS_ENV, "off")
    client = _client()
    refused = client.post(
        "/api/access/users",
        headers=_admin(bearers["admin"]),
        json={"kind": "local", "username": "x.y"},
    )
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "local_accounts_disabled"
    login = client.post("/api/auth/login", json={"username": "a", "password": "b"})
    assert login.status_code == 404


def test_sign_in_from_a_foreign_origin_is_refused(store):
    client = _client()
    refused = client.post(
        "/api/auth/login",
        headers={"Origin": "https://attacker.example"},
        json={"username": "a", "password": "b"},
    )
    assert refused.status_code == 403


def test_expired_temporary_password_says_so_only_to_its_holder(store):
    engine, _ids, bearers = store
    client = _client()
    principal_id, secret = _create_local(client, bearers["admin"])
    with Session(engine) as session:
        credential = session.get(IdentityLocalCredentialRecord, principal_id)
        credential.temporary_expires_at_utc = datetime.now(UTC) - timedelta(minutes=1)
        session.commit()
    expired = client.post("/api/auth/login", json={"username": "jane.trader", "password": secret})
    assert expired.status_code == 401
    assert expired.json()["detail"]["code"] == "temporary_password_expired"
    wrong = client.post("/api/auth/login", json={"username": "jane.trader", "password": "q" * 12})
    assert wrong.json()["detail"]["code"] == "invalid_credentials"


def test_demo_account_never_signs_in_outside_the_demo_profile(store, monkeypatch):
    engine, _ids, _bearers = store
    monkeypatch.setenv("EUROGAS_NEXUS_API_PROFILE", "demo")
    monkeypatch.setenv("EUROGAS_NEXUS_ENV", "development")
    (spec,) = local_accounts.parse_demo_accounts("test_trader:12345678")
    with Session(engine) as session:
        outcome = local_accounts.ensure_demo_account(
            session,
            spec,
            display_name="Test trader",
            grants=local_accounts.AccountGrants(roles=("ANALYST",), job_functions=("TRADER",)),
            reapply=False,
        )
        session.commit()
    assert outcome == "created"
    # On the demo server the weak password works and no change is required.
    demo = TestClient(
        create_app(Settings(api_profile="demo", environment="development")),
        base_url="https://testserver",
    )
    signed = demo.post("/api/auth/login", json={"username": "test_trader", "password": "12345678"})
    assert signed.status_code == 200
    assert signed.json()["data"]["password_change_required"] is False
    # The same database behind a customer runtime: refused like any wrong password.
    monkeypatch.setenv("EUROGAS_NEXUS_API_PROFILE", "release")
    refused = _client().post(
        "/api/auth/login", json={"username": "test_trader", "password": "12345678"}
    )
    assert refused.status_code == 401
    assert refused.json()["detail"]["code"] == "invalid_credentials"
