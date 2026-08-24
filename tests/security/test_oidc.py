"""R32A OIDC access-token verification tests (offline RSA fixtures)."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from eurogas_nexus.security.oidc import (
    OidcValidationError,
    clear_oidc_cache,
    oidc_configured,
    validate_oidc_access_token,
)

ISSUER = "https://idp.example.test"
CLIENT_ID = "eurogas-nexus"
AUDIENCE = "eurogas-api"


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
        "jwks_uri": f"{ISSUER}/keys",
    }
    jwks = {"keys": [jwk]}
    return private_key, jwk, discovery, jwks


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


def _base_claims() -> dict:
    now = datetime.now(UTC)
    return {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "user-123",
        "preferred_username": "trader.alice",
        "exp": int((now + timedelta(minutes=5)).timestamp()),
        "iat": int(now.timestamp()),
    }


def _fake_get(discovery: dict, jwks: dict):
    def fake(url: str, *, timeout: float):
        class Response:
            status_code = 200

            def json(self):
                return discovery if url.endswith("openid-configuration") else jwks

        return Response()

    return fake


def _configure_env(monkeypatch):
    monkeypatch.setenv("EUROGAS_NEXUS_OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("EUROGAS_NEXUS_OIDC_CLIENT_ID", CLIENT_ID)
    monkeypatch.setenv("EUROGAS_NEXUS_OIDC_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("EUROGAS_NEXUS_OIDC_ALLOW_HTTP", "false")


def test_oidc_configured_flag(monkeypatch) -> None:
    monkeypatch.delenv("EUROGAS_NEXUS_OIDC_ISSUER", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_OIDC_CLIENT_ID", raising=False)
    assert oidc_configured() is False
    _configure_env(monkeypatch)
    assert oidc_configured() is True


def test_valid_rs256_token_maps_subject_role_and_scopes(monkeypatch, signing_key) -> None:
    _configure_env(monkeypatch)
    private_key, jwk, discovery, jwks = signing_key
    claims = {
        **_base_claims(),
        "roles": ["analyst"],
        "entitlements": ["EEX", "ICE_OCM"],
    }
    token = _sign(private_key, {"alg": "RS256", "typ": "at+jwt", "kid": "test-key-1"}, claims)

    identity = validate_oidc_access_token(
        token,
        http_get=_fake_get(discovery, jwks),
        now_utc=datetime.now(UTC),
    )

    assert identity.subject == "user-123"
    assert identity.name == "trader.alice"
    assert identity.role == "ANALYST"
    assert identity.data_scopes == ("EEX", "ICE_OCM")


def test_operator_role_from_realm_access_claim(monkeypatch, signing_key) -> None:
    _configure_env(monkeypatch)
    private_key, jwk, discovery, jwks = signing_key
    claims = {
        **_base_claims(),
        "realm_access": {"roles": ["ops"]},
        "entitlements": ["*"],
    }
    token = _sign(private_key, {"alg": "RS256", "kid": "test-key-1"}, claims)

    identity = validate_oidc_access_token(token, http_get=_fake_get(discovery, jwks))

    assert identity.role == "OPERATOR"
    assert identity.data_scopes == ("*",)


def test_wrong_signature_is_rejected(monkeypatch, signing_key) -> None:
    _configure_env(monkeypatch)
    _, jwk, discovery, jwks = signing_key
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = _sign(other_key, {"alg": "RS256", "kid": "test-key-1"}, _base_claims())

    with pytest.raises(OidcValidationError) as exc_info:
        validate_oidc_access_token(token, http_get=_fake_get(discovery, jwks))
    assert exc_info.value.code == "oidc_signature_invalid"


def test_expired_token_is_rejected(monkeypatch, signing_key) -> None:
    _configure_env(monkeypatch)
    private_key, jwk, discovery, jwks = signing_key
    claims = _base_claims()
    claims["exp"] = int((datetime.now(UTC) - timedelta(minutes=5)).timestamp())
    token = _sign(private_key, {"alg": "RS256", "kid": "test-key-1"}, claims)

    with pytest.raises(OidcValidationError) as exc_info:
        validate_oidc_access_token(token, http_get=_fake_get(discovery, jwks))
    assert exc_info.value.code == "oidc_token_expired"


def test_issuer_and_audience_must_match_configuration(monkeypatch, signing_key) -> None:
    _configure_env(monkeypatch)
    private_key, jwk, discovery, jwks = signing_key

    wrong_issuer = {**_base_claims(), "iss": "https://other-idp.test"}
    token = _sign(private_key, {"alg": "RS256", "kid": "test-key-1"}, wrong_issuer)
    with pytest.raises(OidcValidationError) as exc_info:
        validate_oidc_access_token(token, http_get=_fake_get(discovery, jwks))
    assert exc_info.value.code == "oidc_issuer_invalid"

    wrong_audience = {**_base_claims(), "aud": "other-api"}
    token = _sign(private_key, {"alg": "RS256", "kid": "test-key-1"}, wrong_audience)
    with pytest.raises(OidcValidationError) as exc_info:
        validate_oidc_access_token(token, http_get=_fake_get(discovery, jwks))
    assert exc_info.value.code == "oidc_audience_invalid"


def test_non_rs256_token_is_rejected(monkeypatch, signing_key) -> None:
    _configure_env(monkeypatch)
    private_key, jwk, discovery, jwks = signing_key
    token = _sign(private_key, {"alg": "HS256", "kid": "test-key-1"}, _base_claims())

    with pytest.raises(OidcValidationError) as exc_info:
        validate_oidc_access_token(token, http_get=_fake_get(discovery, jwks))
    assert exc_info.value.code == "oidc_algorithm_unsupported"


def test_missing_subject_or_kid_is_rejected(monkeypatch, signing_key) -> None:
    _configure_env(monkeypatch)
    private_key, jwk, discovery, jwks = signing_key

    claims = _base_claims()
    claims.pop("sub")
    token = _sign(private_key, {"alg": "RS256", "kid": "test-key-1"}, claims)
    with pytest.raises(OidcValidationError) as exc_info:
        validate_oidc_access_token(token, http_get=_fake_get(discovery, jwks))
    assert exc_info.value.code == "oidc_subject_missing"

    token = _sign(private_key, {"alg": "RS256"}, _base_claims())
    with pytest.raises(OidcValidationError) as exc_info:
        validate_oidc_access_token(token, http_get=_fake_get(discovery, jwks))
    assert exc_info.value.code == "oidc_token_kid_missing"


def test_discovery_issuer_mismatch_is_rejected(monkeypatch, signing_key) -> None:
    _configure_env(monkeypatch)
    private_key, jwk, discovery, jwks = signing_key
    bad_discovery = {**discovery, "issuer": "https://wrong.test"}

    token = _sign(private_key, {"alg": "RS256", "kid": "test-key-1"}, _base_claims())
    with pytest.raises(OidcValidationError) as exc_info:
        validate_oidc_access_token(token, http_get=_fake_get(bad_discovery, jwks))
    assert exc_info.value.code == "oidc_discovery_invalid"


def test_unconfigured_oidc_fails_closed(monkeypatch) -> None:
    monkeypatch.delenv("EUROGAS_NEXUS_OIDC_ISSUER", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_OIDC_CLIENT_ID", raising=False)

    with pytest.raises(OidcValidationError) as exc_info:
        validate_oidc_access_token("jwt")
    assert exc_info.value.code == "oidc_not_configured"
