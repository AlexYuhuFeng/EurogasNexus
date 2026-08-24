"""Release-profile API integration tests for OIDC access tokens (R32A)."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi.testclient import TestClient

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings
from eurogas_nexus.security import oidc as oidc_module

ISSUER = "https://idp.example.test"
CLIENT_ID = "eurogas-nexus"
AUDIENCE = "eurogas-api"
PUBLIC_TOKEN = "test-public-api-token"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _token(private_key, roles: list[str]) -> str:
    now = datetime.now(UTC)
    header = {"alg": "RS256", "kid": "test-key-1"}
    payload = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "user-123",
        "preferred_username": "oidc.user",
        "roles": roles,
        "entitlements": ["EEX"],
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "iat": int(now.timestamp()),
    }
    header_part = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_part = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_part}.{payload_part}".encode("ascii")
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    return f"{header_part}.{payload_part}.{_b64url(signature)}"


def _install_fake_http(monkeypatch, private_key) -> None:
    numbers = private_key.public_key().public_numbers()
    discovery = {"issuer": ISSUER, "jwks_uri": f"{ISSUER}/keys"}
    jwks = {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "alg": "RS256",
                "kid": "test-key-1",
                "n": _b64url(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")),
                "e": _b64url(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")),
            }
        ]
    }

    def fake_get(url: str, *, timeout: float):
        class Response:
            status_code = 200

            def json(self):
                return discovery if url.endswith("openid-configuration") else jwks

        return Response()

    monkeypatch.setattr(oidc_module, "_default_http_get", fake_get)
    monkeypatch.setattr(oidc_module, "_cache", {})


def _configure_env(monkeypatch) -> None:
    monkeypatch.setenv("EUROGAS_NEXUS_OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("EUROGAS_NEXUS_OIDC_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("EUROGAS_NEXUS_OIDC_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("EUROGAS_NEXUS_OIDC_ALLOW_HTTP", "false")


@pytest.fixture(autouse=True)
def _clear_cache():
    oidc_module.clear_oidc_cache()
    yield
    oidc_module.clear_oidc_cache()


def _route_body() -> dict:
    return {
        "source": "A",
        "target": "B",
        "required_capacity_mwh": 1,
        "edges": [
            {
                "edge_id": "e",
                "source": "A",
                "target": "B",
                "tariff_gbp_mwh": 0,
                "available_capacity_mwh": 1,
            }
        ],
    }


def test_oidc_roles_are_enforced_on_release_routes(monkeypatch) -> None:
    _configure_env(monkeypatch)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _install_fake_http(monkeypatch, private_key)
    viewer = _token(private_key, ["viewer"])
    analyst = _token(private_key, ["analyst"])
    client = TestClient(create_app(Settings(api_profile="release")))

    def headers(token: str) -> dict[str, str]:
        return {
            "X-Eurogas-Api-Key": PUBLIC_TOKEN,
            "X-Eurogas-Oidc-Access-Token": token,
        }

    assert client.get("/api/health", headers=headers(viewer)).status_code == 200

    viewer_governed = client.post(
        "/api/optimization/route",
        headers=headers(viewer),
        json=_route_body(),
    )
    assert viewer_governed.status_code == 403
    assert viewer_governed.json()["detail"]["error"] == "identity_role_forbidden"

    analyst_governed = client.post(
        "/api/optimization/route",
        headers=headers(analyst),
        json=_route_body(),
    )
    assert analyst_governed.status_code == 200


def test_oidc_header_without_configuration_fails_closed(monkeypatch) -> None:
    monkeypatch.delenv("EUROGAS_NEXUS_OIDC_ISSUER", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_OIDC_CLIENT_ID", raising=False)
    client = TestClient(create_app(Settings(api_profile="release")))

    response = client.get(
        "/api/health",
        headers={
            "X-Eurogas-Api-Key": PUBLIC_TOKEN,
            "X-Eurogas-Oidc-Access-Token": "jwt",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"]["error"] == "oidc_not_configured"


def test_oidc_signature_failure_is_rejected(monkeypatch) -> None:
    _configure_env(monkeypatch)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    _install_fake_http(monkeypatch, private_key)
    bad_token = _token(other_key, ["operator"])
    client = TestClient(create_app(Settings(api_profile="release")))

    response = client.get(
        "/api/health",
        headers={
            "X-Eurogas-Api-Key": PUBLIC_TOKEN,
            "X-Eurogas-Oidc-Access-Token": bad_token,
        },
    )

    assert response.status_code == 403
    assert response.json()["detail"]["error"] == "oidc_signature_invalid"
