"""CR-10 interactive OIDC + session tests (offline RSA fixtures)."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.application.enterprise_auth import (
    complete_browser_login,
    complete_desktop_login,
    start_browser_login,
    start_desktop_login,
)
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import IdentityPrincipalRecord, UserSessionRecord
from eurogas_nexus.db.repositories import identity as identity_repository
from eurogas_nexus.db.repositories.security import create_external_identity, create_session
from eurogas_nexus.security.oidc import OidcValidationError, clear_oidc_cache

ISSUER = "https://idp.example.test"
CLIENT_ID = "eurogas-nexus"


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_oidc_cache()
    yield
    clear_oidc_cache()


@pytest.fixture()
def signing_key():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = private_key.public_key().public_numbers()
    jwk = {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": "test-key-1",
        "n": _b64url_int(numbers.n),
        "e": _b64url_int(numbers.e),
    }
    discovery = {
        "issuer": ISSUER,
        "authorization_endpoint": f"{ISSUER}/authorize",
        "token_endpoint": f"{ISSUER}/token",
        "jwks_uri": f"{ISSUER}/keys",
    }
    return private_key, jwk, discovery, {"keys": [jwk]}


def _b64url_int(value: int) -> str:
    length = (value.bit_length() + 7) // 8
    return _b64url(value.to_bytes(length, "big"))


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _sign(private_key, header: dict, payload: dict) -> str:
    header_part = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_part = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_part}.{payload_part}".encode("ascii")
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{header_part}.{payload_part}.{_b64url(signature)}"


def _token(private_key, *, nonce: str, subject: str, email: str | None = None, groups=None) -> str:
    now = datetime.now(UTC)
    claims = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "sub": subject,
        "preferred_username": "alice",
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "iat": int(now.timestamp()),
        "nonce": nonce,
    }
    if email:
        claims["email"] = email
    if groups:
        claims["groups"] = groups
    return _sign(private_key, {"alg": "RS256", "kid": "test-key-1"}, claims)


def _fake_get(discovery, jwks):
    def fake(url: str, *, timeout: float):
        class Response:
            status_code = 200

            def json(self):
                return discovery if url.endswith("openid-configuration") else jwks

        return Response()

    return fake


def _fake_post(id_token: str):
    def fake(url: str, *, data: dict, auth=None, timeout: float):
        class Response:
            status_code = 200

            def json(self):
                return {"access_token": "at", "id_token": id_token}

        return Response()

    return fake


@pytest.fixture()
def env_db(tmp_path, monkeypatch):
    db_path = tmp_path / "enterprise-auth.sqlite"
    engine = create_engine(f"sqlite+pysqlite:///{db_path.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    database_url = f"sqlite+pysqlite:///{db_path.as_posix()}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    monkeypatch.setenv("EUROGAS_NEXUS_OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("EUROGAS_NEXUS_OIDC_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("EUROGAS_NEXUS_OIDC_ALLOW_HTTP", "false")
    return engine, database_url


def _configure(monkeypatch, *, mode="preprovisioned", domains="", role_map=None, scope_map=None):
    monkeypatch.setenv("EUROGAS_NEXUS_OIDC_PROVISIONING_MODE", mode)
    if domains:
        monkeypatch.setenv("EUROGAS_NEXUS_OIDC_APPROVED_DOMAINS", domains)
    else:
        monkeypatch.delenv("EUROGAS_NEXUS_OIDC_APPROVED_DOMAINS", raising=False)
    if role_map is not None:
        monkeypatch.setenv("EUROGAS_NEXUS_OIDC_GROUPS_ROLE_MAP", json.dumps(role_map))
    else:
        monkeypatch.delenv("EUROGAS_NEXUS_OIDC_GROUPS_ROLE_MAP", raising=False)
    if scope_map is not None:
        monkeypatch.setenv("EUROGAS_NEXUS_OIDC_GROUPS_SCOPE_MAP", json.dumps(scope_map))
    else:
        monkeypatch.delenv("EUROGAS_NEXUS_OIDC_GROUPS_SCOPE_MAP", raising=False)


def test_preprovisioned_browser_login_creates_session(
    env_db, monkeypatch, signing_key,
) -> None:
    engine, _ = env_db
    _configure(monkeypatch)
    private_key, _jwk, discovery, jwks = signing_key
    now = datetime.now(UTC)
    with Session(engine) as session:
        principal = identity_repository.create_identity_principal(
            session, name="alice", display_name="Alice", role="ANALYST", data_scopes=["EEX"]
        )
        create_external_identity(
            session,
            principal_id=principal.principal_id,
            issuer=ISSUER,
            subject="user-123",
            provider_id="oidc",
            email="alice@example.test",
            display_name="Alice",
        )
        session.commit()
        principal_id = principal.principal_id

    with Session(engine) as session:
        state = start_browser_login(
            session,
            redirect_uri="https://nexus.test/api/auth/oidc/callback",
            http_get=_fake_get(discovery, jwks),
            now_utc=now,
        )
        from eurogas_nexus.db.models import OidcAuthorizationStateRecord

        row = session.get(OidcAuthorizationStateRecord, state.state)
        nonce = row.nonce
        session.commit()
        token = _token(
            private_key,
            nonce=nonce,
            subject="user-123",
            email="alice@example.test",
        )
    with Session(engine) as session:
        result = complete_browser_login(
            session,
            code="code-1",
            state=state.state,
            verifier=state.verifier,
            redirect_uri="https://nexus.test/api/auth/oidc/callback",
            http_get=_fake_get(discovery, jwks),
            http_post=_fake_post(token),
            now_utc=now,
        )
        session.commit()

    assert result.principal_id == principal_id
    with Session(engine) as session:
        principal = session.get(IdentityPrincipalRecord, principal_id)
        assert principal.last_login_at_utc is not None
        assert session.query(UserSessionRecord).count() == 1


def test_wrong_pkce_or_state_fails_closed(env_db, monkeypatch, signing_key) -> None:
    engine, _ = env_db
    _configure(monkeypatch)
    private_key, _jwk, discovery, jwks = signing_key
    with Session(engine) as session:
        start = start_browser_login(
            session,
            redirect_uri="https://nexus.test/api/auth/oidc/callback",
            http_get=_fake_get(discovery, jwks),
        )
        session.commit()
    with Session(engine) as session:
        with pytest.raises(OidcValidationError) as exc:
            complete_browser_login(
                session,
                code="code-1",
                state=start.state,
                verifier="wrong-verifier-wrong-verifier-wrong-verifier",
                redirect_uri="https://nexus.test/api/auth/oidc/callback",
                http_get=_fake_get(discovery, jwks),
                http_post=_fake_post("ignored"),
            )
        assert exc.value.code == "oidc_pkce_invalid"
    with Session(engine) as session:
        with pytest.raises(OidcValidationError) as exc:
            complete_browser_login(
                session,
                code="code-1",
                state="missing-state",
                verifier=start.verifier,
                redirect_uri="https://nexus.test/api/auth/oidc/callback",
                http_get=_fake_get(discovery, jwks),
                http_post=_fake_post("ignored"),
            )
        assert exc.value.code == "oidc_state_invalid"


def test_jit_provisioning_defaults_to_minimal_access(
    env_db, monkeypatch, signing_key,
) -> None:
    engine, _ = env_db
    _configure(
        monkeypatch,
        mode="approved_domain",
        domains="example.test",
        role_map={"nexus-analysts": "ANALYST"},
        scope_map={"nexus-analysts": ["EEX"]},
    )
    private_key, _jwk, discovery, jwks = signing_key
    with Session(engine) as session:
        start = start_browser_login(
            session,
            redirect_uri="https://nexus.test/api/auth/oidc/callback",
            http_get=_fake_get(discovery, jwks),
        )
        from eurogas_nexus.db.models import OidcAuthorizationStateRecord

        nonce = session.get(OidcAuthorizationStateRecord, start.state).nonce
        session.commit()
    token = _token(
        private_key,
        nonce=nonce,
        subject="new-user",
        email="alice@example.test",
        groups=["nexus-analysts"],
    )
    with Session(engine) as session:
        result = complete_browser_login(
            session,
            code="code-1",
            state=start.state,
            verifier=start.verifier,
            redirect_uri="https://nexus.test/api/auth/oidc/callback",
            http_get=_fake_get(discovery, jwks),
            http_post=_fake_post(token),
        )
        session.commit()
    with Session(engine) as session:
        principal = session.get(IdentityPrincipalRecord, result.principal_id)
        assert principal.role == "ANALYST"
        assert principal.data_scopes == ["EEX"]
        assert principal.identity_source == "OIDC"


def test_unknown_external_identity_is_denied_in_preprovisioned_mode(
    env_db, monkeypatch, signing_key,
) -> None:
    engine, _ = env_db
    _configure(monkeypatch)
    private_key, _jwk, discovery, jwks = signing_key
    with Session(engine) as session:
        start = start_browser_login(
            session,
            redirect_uri="https://nexus.test/api/auth/oidc/callback",
            http_get=_fake_get(discovery, jwks),
        )
        from eurogas_nexus.db.models import OidcAuthorizationStateRecord

        nonce = session.get(OidcAuthorizationStateRecord, start.state).nonce
        session.commit()
    token = _token(private_key, nonce=nonce, subject="unknown-user")
    with Session(engine) as session:
        with pytest.raises(OidcValidationError) as exc:
            complete_browser_login(
                session,
                code="code-1",
                state=start.state,
                verifier=start.verifier,
                redirect_uri="https://nexus.test/api/auth/oidc/callback",
                http_get=_fake_get(discovery, jwks),
                http_post=_fake_post(token),
            )
        assert exc.value.code == "external_identity_not_provisioned"


def test_desktop_login_exchanges_loopback_code(env_db, monkeypatch, signing_key) -> None:
    engine, _ = env_db
    _configure(monkeypatch, mode="approved_domain", domains="example.test")
    private_key, _jwk, discovery, jwks = signing_key
    verifier = "desktop-verifier-desktop-verifier-desktop-verifier-123"
    challenge = __import__("hashlib").sha256(verifier.encode()).hexdigest()
    with Session(engine) as session:
        start = start_desktop_login(
            session,
            code_challenge=challenge,
            code_verifier=verifier,
            redirect_uri="http://127.0.0.1:4242/callback",
            http_get=_fake_get(discovery, jwks),
        )
        from eurogas_nexus.db.models import OidcAuthorizationStateRecord

        nonce = session.get(OidcAuthorizationStateRecord, start.state).nonce
        session.commit()
    token = _token(private_key, nonce=nonce, subject="desk-user", email="desk@example.test")
    with Session(engine) as session:
        result = complete_desktop_login(
            session,
            code="code-1",
            state=start.state,
            verifier=verifier,
            redirect_uri="http://127.0.0.1:4242/callback",
            http_get=_fake_get(discovery, jwks),
            http_post=_fake_post(token),
        )
        session.commit()
    assert result.session_token
    with Session(engine) as session:
        assert session.query(UserSessionRecord).count() == 1


def test_session_cookie_authenticates_release_api_and_disabled_denies(
    env_db, monkeypatch,
) -> None:
    engine, _ = env_db
    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", "public-token")
    with Session(engine) as session:
        principal = identity_repository.create_identity_principal(
            session,
            name="session-user",
            display_name="Session User",
            role="ANALYST",
            data_scopes=[],
        )
        session_token = "session-token-for-test"
        create_session(
            session,
            principal_id=principal.principal_id,
            token=session_token,
            client_type="browser",
        )
        session.commit()
        principal_id = principal.principal_id

    client = TestClient(create_app(Settings(api_profile="release")))
    headers = {"Cookie": f"eurogas_session={session_token}"}
    response = client.get("/api/me", headers=headers)
    assert response.status_code == 200
    assert response.json()["data"]["principal_id"] == principal_id
    assert response.json()["data"]["auth_method"] == "session"

    with Session(engine) as session:
        principal = session.get(IdentityPrincipalRecord, principal_id)
        principal.status = "DISABLED"
        session.commit()
    denied = client.get("/api/me", headers=headers)
    assert denied.status_code in {401, 403}
    assert denied.json()["detail"]["error"] in {"session_invalid", "session_principal_inactive"}
