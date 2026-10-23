"""Synthetic issuer acceptance: real loopback discovery/JWKS, signed API tokens.

Application-level Code+PKCE exchange and subsequent API session authentication are
covered; browser redirect/callback endpoints and a customer issuer are not exercised.
No production SSO certification is implied. HTTP is explicitly enabled only inside
this isolated test fixture.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.security.oidc import clear_oidc_cache


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


@pytest.fixture()
def issuer(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = key.public_key().public_numbers()
    jwk = {"kty": "RSA", "use": "sig", "alg": "RS256", "kid": "synthetic-1"}
    for name, value in (("n", numbers.n), ("e", numbers.e)):
        jwk[name] = _encode(value.to_bytes((value.bit_length() + 7) // 8, "big"))
    state = {"requests": [], "discovery_status": 200, "jwks_status": 200}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            state["requests"].append(self.path)
            if self.path == "/.well-known/openid-configuration":
                status = state["discovery_status"]
                body = {
                    "issuer": base_url,
                    "jwks_uri": f"{base_url}/keys",
                    "authorization_endpoint": f"{base_url}/authorize",
                    "token_endpoint": f"{base_url}/token",
                }
            elif self.path == "/keys":
                status = state["jwks_status"]
                body = {"keys": [jwk]}
            else:
                status, body = 404, {}
            encoded = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def do_POST(self):
            state["requests"].append(self.path)
            form = parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
            challenge = _encode(
                hashlib.sha256(form.get("code_verifier", [""])[0].encode()).digest()
            )
            valid = (
                self.path == "/token"
                and form.get("code") == ["synthetic-code"]
                and form.get("grant_type") == ["authorization_code"]
                and form.get("client_id") == ["synthetic-client"]
                and form.get("redirect_uri") == [state.get("redirect_uri")]
                and challenge == state.get("challenge")
            )
            body = (
                {"id_token": state["id_token"], "access_token": "synthetic-access"}
                if valid
                else {"error": "invalid_grant"}
            )
            encoded = json.dumps(body).encode()
            self.send_response(200 if valid else 400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    base_url = f"http://127.0.0.1:{server.server_port}"
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("EUROGAS_NEXUS_OIDC_ISSUER", base_url)
    monkeypatch.setenv("EUROGAS_NEXUS_OIDC_CLIENT_ID", "synthetic-client")
    monkeypatch.setenv("EUROGAS_NEXUS_OIDC_AUDIENCE", "synthetic-api")
    monkeypatch.setenv("EUROGAS_NEXUS_OIDC_ALLOW_HTTP", "true")
    # Keep actual HTTP transport while isolating loopback from ambient proxies.
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    clear_oidc_cache()

    def token(role="viewer", *, signing_key=None, **changes):
        now = datetime.now(UTC)
        claims = {
            "iss": base_url,
            "aud": "synthetic-api",
            "sub": "synthetic-user",
            "preferred_username": "synthetic-user",
            "roles": [role],
            "exp": int((now + timedelta(minutes=5)).timestamp()),
            "iat": int(now.timestamp()),
        }
        claims.update(changes)
        parts = [
            _encode(json.dumps(part).encode())
            for part in (
                {"alg": "RS256", "kid": "synthetic-1"},
                claims,
            )
        ]
        signed = ".".join(parts).encode()
        signature = (signing_key or key).sign(signed, padding.PKCS1v15(), hashes.SHA256())
        return f"{signed.decode()}.{_encode(signature)}"

    try:
        with TestClient(create_app(Settings(api_profile="release"))) as client:
            yield client, token, state
    finally:
        clear_oidc_cache()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _headers(token):
    return {"X-Eurogas-Api-Key": "test-public-api-token", "X-Eurogas-Oidc-Access-Token": token}


@pytest.mark.parametrize(
    "role,status",
    [("viewer", 403), ("reviewer", 403), ("analyst", 200), ("operator", 200), ("admin", 403)],
)
def test_signed_roles_enforce_governed_route(issuer, role, status):
    client, token, state = issuer
    response = client.post(
        "/api/optimization/route",
        headers=_headers(token(role)),
        json={
            "source": "A",
            "target": "B",
            "required_capacity_mwh": 1,
            "edges": [
                {
                    "edge_id": "synthetic",
                    "source": "A",
                    "target": "B",
                    "tariff_gbp_mwh": 0,
                    "available_capacity_mwh": 1,
                }
            ],
        },
    )
    assert response.status_code == status, response.text
    if status == 403:
        assert response.json()["detail"]["error"] == (
            "commercial_access_not_granted" if role == "admin" else "identity_role_forbidden"
        )
    assert state["requests"] == ["/.well-known/openid-configuration", "/keys"]


@pytest.mark.parametrize(
    "failure,status,code",
    [
        ("expired", 401, "oidc_token_expired"),
        ("audience", 403, "oidc_audience_invalid"),
        ("signature", 403, "oidc_signature_invalid"),
        ("malformed", 401, "oidc_token_malformed"),
    ],
)
def test_invalid_tokens_fail_closed(issuer, failure, status, code):
    client, token, _state = issuer
    if failure == "expired":
        credential = token(exp=int((datetime.now(UTC) - timedelta(minutes=10)).timestamp()))
    elif failure == "audience":
        credential = token(aud="another-api")
    elif failure == "signature":
        credential = token(
            signing_key=rsa.generate_private_key(public_exponent=65537, key_size=2048)
        )
    else:
        credential = "not-a-jwt"
    response = client.get("/api/health", headers=_headers(credential))
    assert response.status_code == status, response.text
    assert response.json()["detail"]["error"] == code


@pytest.mark.parametrize(
    "endpoint,code",
    [
        ("discovery", "oidc_discovery_unavailable"),
        ("jwks", "oidc_jwks_unavailable"),
    ],
)
def test_cold_cache_issuer_outage_fails_closed(issuer, endpoint, code):
    client, token, state = issuer
    state[f"{endpoint}_status"] = 503
    response = client.get("/api/health", headers=_headers(token()))
    assert response.status_code == 503, response.text
    assert response.json()["detail"]["error"] == code
    assert "/.well-known/openid-configuration" in state["requests"]


@pytest.mark.parametrize("failure", [None, "pkce", "nonce"])
def test_http_code_pkce_exchange_issues_session_and_rejects_replay(
    issuer,
    tmp_path,
    monkeypatch,
    failure,
):
    """Exchange over actual HTTP; preprovision only identity, never a session."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from eurogas_nexus.application.enterprise_auth import (
        complete_browser_login,
        start_browser_login,
    )
    from eurogas_nexus.db.base import Base
    from eurogas_nexus.db.models import UserSessionRecord
    from eurogas_nexus.db.repositories.identity import create_identity_principal
    from eurogas_nexus.db.repositories.security import create_external_identity
    from eurogas_nexus.security.oidc import OidcValidationError

    client, token, state = issuer
    database_url = f"sqlite+pysqlite:///{tmp_path / 'synthetic-oidc.sqlite'}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.setenv("EUROGAS_NEXUS_OIDC_PROVISIONING_MODE", "preprovisioned")
    for name in ("DATABASE_URL", "EUROGAS_NEXUS_DB_DSN", "EUROGAS_NEXUS_OIDC_CLIENT_SECRET"):
        monkeypatch.delenv(name, raising=False)
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    redirect_uri = "https://synthetic-nexus.test/api/auth/oidc/callback"
    try:
        with Session(engine) as session:
            principal = create_identity_principal(
                session,
                name="synthetic-user",
                display_name="Synthetic User",
                role="ANALYST",
                data_scopes=[],
            )
            principal_id = principal.principal_id
            create_external_identity(
                session,
                principal_id=principal_id,
                issuer=os.environ["EUROGAS_NEXUS_OIDC_ISSUER"],
                subject="synthetic-user",
                provider_id="oidc",
                email="synthetic@example.test",
                display_name="Synthetic User",
            )
            start = start_browser_login(session, redirect_uri=redirect_uri)
            session.commit()
            assert session.query(UserSessionRecord).count() == 0
        query = parse_qs(urlparse(start.url).query)
        assert query["code_challenge_method"] == ["S256"]
        state["challenge"] = query["code_challenge"][0]
        state["redirect_uri"] = redirect_uri
        state["id_token"] = token(nonce=query["nonce"][0], aud="synthetic-client")
        if failure:
            if failure == "pkce":
                state["challenge"] = "different-challenge"
                expected = "oidc_token_exchange_failed"
            else:
                state["id_token"] = token(nonce="wrong-nonce", aud="synthetic-client")
                expected = "oidc_nonce_invalid"
            with Session(engine) as session:
                with pytest.raises(OidcValidationError) as error:
                    complete_browser_login(
                        session,
                        code="synthetic-code",
                        state=start.state,
                        verifier=start.verifier,
                        redirect_uri=redirect_uri,
                    )
                assert error.value.code == expected
                assert session.query(UserSessionRecord).count() == 0
            assert state["requests"].count("/token") == 1
            return
        with Session(engine) as session:
            result = complete_browser_login(
                session,
                code="synthetic-code",
                state=start.state,
                verifier=start.verifier,
                redirect_uri=redirect_uri,
            )
            session.commit()
            assert result.principal_id == principal_id
            assert session.query(UserSessionRecord).count() == 1
        authenticated = client.get(
            "/api/me",
            headers={"Cookie": f"eurogas_session={result.session_token}"},
        )
        assert authenticated.status_code == 200, authenticated.text
        assert authenticated.json()["data"]["principal_id"] == principal_id
        assert authenticated.json()["data"]["auth_method"] == "session"
        with Session(engine) as session:
            with pytest.raises(OidcValidationError) as error:
                complete_browser_login(
                    session,
                    code="synthetic-code",
                    state=start.state,
                    verifier=start.verifier,
                    redirect_uri=redirect_uri,
                )
            assert error.value.code == "oidc_state_invalid"
            assert session.query(UserSessionRecord).count() == 1
        assert state["requests"].count("/token") == 1
        assert "/keys" in state["requests"]
    finally:
        engine.dispose()
