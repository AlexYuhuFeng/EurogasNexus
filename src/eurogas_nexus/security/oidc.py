"""Import-safe OIDC access-token verification (R32A).

Supported flow is machine-to-machine / bearer access-token validation against
a company OIDC issuer. No login redirect, PKCE, refresh token, or session is
implemented. Discovery and JWKS retrieval are lazy, cached, and bounded; this
module performs no network I/O at import time.
"""

from __future__ import annotations

import base64
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

OIDC_ISSUER_ENV = "EUROGAS_NEXUS_OIDC_ISSUER"
OIDC_CLIENT_ID_ENV = "EUROGAS_NEXUS_OIDC_CLIENT_ID"
OIDC_AUDIENCE_ENV = "EUROGAS_NEXUS_OIDC_AUDIENCE"
OIDC_ROLE_CLAIM_ENV = "EUROGAS_NEXUS_OIDC_ROLE_CLAIM"
OIDC_SCOPE_CLAIM_ENV = "EUROGAS_NEXUS_OIDC_SCOPE_CLAIM"
OIDC_ALLOW_HTTP_ENV = "EUROGAS_NEXUS_OIDC_ALLOW_HTTP"

DISCOVERY_CACHE_TTL_SECONDS = 300.0
DEFAULT_LEEWAY_SECONDS = 60.0
SUPPORTED_ALGORITHM = "RS256"

_ROLE_ALIASES = {
    "admin": "ADMIN",
    "administrator": "ADMIN",
    "operator": "OPERATOR",
    "ops": "OPERATOR",
    "operations": "OPERATOR",
    "analyst": "ANALYST",
    "trader": "ANALYST",
    "research": "ANALYST",
    "viewer": "VIEWER",
    "read": "VIEWER",
}

_cache: dict[str, tuple[float, Any]] = {}


@dataclass(frozen=True)
class OidcValidationError(Exception):
    """Safe OIDC validation failure; never carries token material."""

    code: str
    status_code: int
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


@dataclass(frozen=True, slots=True)
class OidcIdentity:
    """Claims extracted from a verified OIDC access token."""

    subject: str
    name: str
    role: str
    data_scopes: tuple[str, ...]
    issuer: str


def oidc_configured() -> bool:
    """Return whether an OIDC issuer and client id are configured."""

    return bool(_issuer()) and bool(_client_id())


def validate_oidc_access_token(
    token: str | None,
    *,
    http_get: Callable[..., Any] | None = None,
    now_utc: datetime | None = None,
    leeway_seconds: float = DEFAULT_LEEWAY_SECONDS,
) -> OidcIdentity:
    """Validate one OIDC access token and return its mapped identity.

    Args:
        token: Compact JWT access token.
        http_get: Injectable HTTP GET function for discovery/JWKS (tests use
            a fake; production uses the bounded httpx default).
        now_utc: Evaluation clock; defaults to now.
        leeway_seconds: Clock-skew tolerance.

    Returns:
        OidcIdentity with subject, display name, mapped role, and scopes.

    Raises:
        OidcValidationError: When configuration, discovery, signature, or
            claims validation fails. No exception message carries the token.
    """

    issuer = _issuer()
    client_id = _client_id()
    audience = _audience() or client_id
    if not issuer or not client_id:
        raise OidcValidationError(
            code="oidc_not_configured",
            status_code=503,
            message="OIDC issuer/client id are not configured.",
        )
    if not token or not token.strip():
        raise OidcValidationError(
            code="oidc_token_missing",
            status_code=401,
            message="OIDC access token is required.",
        )

    now = _as_utc(now_utc or datetime.now(UTC))
    header, payload, signing_input, signature = _decode_jwt(token)
    _validate_header(header)
    _validate_payload_claims(
        payload,
        issuer=issuer,
        client_id=client_id,
        audience=audience,
        now_utc=now,
        leeway_seconds=leeway_seconds,
    )

    jwks = _cached_json(
        "jwks",
        lambda: _fetch_jwks(
            issuer,
            http_get=http_get or _default_http_get,
            allow_insecure=_allow_insecure(),
        ),
        ttl_seconds=DISCOVERY_CACHE_TTL_SECONDS,
    )
    key = _select_signing_key(jwks, header.get("kid"))
    _verify_rs256_signature(key, signing_input, signature)

    return OidcIdentity(
        subject=str(payload["sub"]),
        name=_display_name(payload),
        role=_mapped_role(payload),
        data_scopes=tuple(_claim_list(payload, _scope_claim())),
        issuer=issuer,
    )


def _decode_jwt(token: str) -> tuple[dict, dict, bytes, bytes]:
    parts = token.strip().split(".")
    if len(parts) != 3:
        raise OidcValidationError(
            code="oidc_token_malformed",
            status_code=401,
            message="OIDC access token must be a compact three-part JWT.",
        )
    try:
        header = json.loads(_b64url_decode(parts[0]))
        payload = json.loads(_b64url_decode(parts[1]))
    except (ValueError, TypeError) as exc:
        raise OidcValidationError(
            code="oidc_token_malformed",
            status_code=401,
            message="OIDC access token header/payload are not valid JSON.",
        ) from exc
    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise OidcValidationError(
            code="oidc_token_malformed",
            status_code=401,
            message="OIDC access token header/payload must be JSON objects.",
        )
    signing_input = f"{parts[0]}.{parts[1]}".encode("ascii")
    signature = _b64url_decode_raw(parts[2])
    return header, payload, signing_input, signature


def _validate_header(header: dict) -> None:
    if header.get("alg") != SUPPORTED_ALGORITHM:
        raise OidcValidationError(
            code="oidc_algorithm_unsupported",
            status_code=403,
            message="Only RS256 OIDC access tokens are accepted.",
        )
    if not header.get("kid"):
        raise OidcValidationError(
            code="oidc_token_kid_missing",
            status_code=403,
            message="OIDC access token is missing a key id (kid).",
        )


def _validate_payload_claims(
    payload: dict,
    *,
    issuer: str,
    client_id: str,
    audience: str,
    now_utc: datetime,
    leeway_seconds: float,
) -> None:
    if payload.get("iss") != issuer:
        raise OidcValidationError(
            code="oidc_issuer_invalid",
            status_code=403,
            message="OIDC access token issuer does not match configuration.",
        )
    audiences = payload.get("aud")
    if isinstance(audiences, list):
        valid_audiences = {client_id, audience}
        if not any(value in valid_audiences for value in audiences):
            raise OidcValidationError(
                code="oidc_audience_invalid",
                status_code=403,
                message="OIDC access token audience does not match configuration.",
            )
    elif audiences not in {client_id, audience}:
        raise OidcValidationError(
            code="oidc_audience_invalid",
            status_code=403,
            message="OIDC access token audience does not match configuration.",
        )
    if not isinstance(payload.get("sub"), str) or not payload["sub"].strip():
        raise OidcValidationError(
            code="oidc_subject_missing",
            status_code=403,
            message="OIDC access token is missing a subject claim.",
        )
    exp = payload.get("exp")
    if not isinstance(exp, int | float) or _epoch_seconds(exp) <= (
        now_utc.timestamp() - leeway_seconds
    ):
        raise OidcValidationError(
            code="oidc_token_expired",
            status_code=401,
            message="OIDC access token has expired.",
        )
    nbf = payload.get("nbf")
    if nbf is not None and (
        not isinstance(nbf, int | float)
        or _epoch_seconds(nbf) > now_utc.timestamp() + leeway_seconds
    ):
        raise OidcValidationError(
            code="oidc_token_not_yet_valid",
            status_code=403,
            message="OIDC access token is not valid yet.",
        )


def _mapped_role(payload: dict) -> str:
    role_claim = _role_claim()
    claims = _claim_list(payload, role_claim)
    if role_claim != "roles":
        claims.extend(_claim_list(payload, "roles"))
    if role_claim != "realm_access.roles":
        claims.extend(_claim_list(payload, "realm_access.roles"))
    claims.extend(_scope_roles(payload.get("scope")))
    normalized = {str(value).strip().lower() for value in claims if isinstance(value, str)}
    matched = [_ROLE_ALIASES[value] for value in normalized if value in _ROLE_ALIASES]
    if not matched:
        # No recognized role claim: least privilege rather than fail-open.
        return "VIEWER"
    return max(matched, key=lambda role: ["VIEWER", "ANALYST", "OPERATOR", "ADMIN"].index(role))


def _display_name(payload: dict) -> str:
    for key in ("preferred_username", "email", "name"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return str(payload["sub"])


def _claim_list(payload: dict, claim: str) -> list[str]:
    value: Any = payload
    for part in claim.split("."):
        if not isinstance(value, dict):
            return []
        value = value.get(part)
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if isinstance(item, str)]
    return []


def _scope_roles(value: Any) -> list[str]:
    if not isinstance(value, str):
        return []
    return [token for token in value.split() if token.strip().lower() in _ROLE_ALIASES]


def _select_signing_key(jwks: dict, kid: str | None) -> dict:
    keys = jwks.get("keys")
    if not isinstance(keys, list):
        raise OidcValidationError(
            code="oidc_jwks_invalid",
            status_code=503,
            message="OIDC JWKS response is missing keys.",
        )
    for key in keys:
        if isinstance(key, dict) and key.get("kid") == kid and key.get("kty") == "RSA":
            return key
    raise OidcValidationError(
        code="oidc_jwks_key_missing",
        status_code=403,
        message="OIDC JWKS has no matching RSA signing key.",
    )


def _verify_rs256_signature(key: dict, signing_input: bytes, signature: bytes) -> None:
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding, rsa

        n = int.from_bytes(_b64url_decode_raw(key["n"]), "big")
        e = int.from_bytes(_b64url_decode_raw(key["e"]), "big")
        public_key = rsa.RSAPublicNumbers(e, n).public_key()
        # Re-serialize once to reject structurally invalid public keys early.
        public_key.public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        public_key.verify(
            signature,
            signing_input,
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
    except (KeyError, TypeError, ValueError, InvalidSignature) as exc:
        raise OidcValidationError(
            code="oidc_signature_invalid",
            status_code=403,
            message="OIDC access token signature is invalid.",
        ) from exc


def _fetch_jwks(
    issuer: str,
    *,
    http_get: Callable[..., Any],
    allow_insecure: bool,
) -> dict:
    if not issuer.startswith("https://") and not allow_insecure:
        raise OidcValidationError(
            code="oidc_issuer_insecure",
            status_code=503,
            message=(
                "OIDC issuer must use https://; set EUROGAS_NEXUS_OIDC_ALLOW_HTTP "
                "only for a reviewed development/test issuer."
            ),
        )
    discovery = _cached_json(
        "discovery",
        lambda: _fetch_discovery(issuer, http_get=http_get),
        ttl_seconds=DISCOVERY_CACHE_TTL_SECONDS,
    )
    jwks_uri = discovery.get("jwks_uri")
    if not isinstance(jwks_uri, str) or not jwks_uri:
        raise OidcValidationError(
            code="oidc_discovery_invalid",
            status_code=503,
            message="OIDC discovery response is missing jwks_uri.",
        )
    response = http_get(jwks_uri, timeout=5.0)
    try:
        status_code = int(getattr(response, "status_code", 0))
        if status_code != 200:
            raise OidcValidationError(
                code="oidc_jwks_unavailable",
                status_code=503,
                message="OIDC JWKS endpoint did not return 200.",
            )
        data = response.json()
    except OidcValidationError:
        raise
    except Exception as exc:
        raise OidcValidationError(
            code="oidc_jwks_unavailable",
            status_code=503,
            message="OIDC JWKS endpoint is unavailable or invalid.",
        ) from exc
    if not isinstance(data, dict):
        raise OidcValidationError(
            code="oidc_jwks_invalid",
            status_code=503,
            message="OIDC JWKS response is not a JSON object.",
        )
    return data


def _fetch_discovery(issuer: str, *, http_get: Callable[..., Any]) -> dict:
    url = f"{issuer.rstrip('/')}/.well-known/openid-configuration"
    try:
        response = http_get(url, timeout=5.0)
        if int(getattr(response, "status_code", 0)) != 200:
            raise OidcValidationError(
                code="oidc_discovery_unavailable",
                status_code=503,
                message="OIDC discovery endpoint did not return 200.",
            )
        data = response.json()
    except OidcValidationError:
        raise
    except Exception as exc:
        raise OidcValidationError(
            code="oidc_discovery_unavailable",
            status_code=503,
            message="OIDC discovery endpoint is unavailable or invalid.",
        ) from exc
    if not isinstance(data, dict) or data.get("issuer") != issuer:
        raise OidcValidationError(
            code="oidc_discovery_invalid",
            status_code=503,
            message="OIDC discovery issuer does not match configuration.",
        )
    return data


def clear_oidc_cache() -> None:
    """Clear cached discovery/JWKS documents (tests and forced refresh)."""

    _cache.clear()


def _cached_json(name: str, loader: Callable[[], Any], *, ttl_seconds: float) -> Any:
    now = time.monotonic()
    cached = _cache.get(name)
    if cached is not None and cached[0] > now:
        return cached[1]
    value = loader()
    _cache[name] = (now + ttl_seconds, value)
    return value


def _default_http_get(url: str, *, timeout: float):
    import httpx

    return httpx.get(url, timeout=timeout, follow_redirects=True)


def _b64url_decode(value: str) -> str:
    return _b64url_decode_raw(value).decode("utf-8")


def _b64url_decode_raw(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _epoch_seconds(value: int | float) -> float:
    return float(value)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _issuer() -> str:
    return os.environ.get(OIDC_ISSUER_ENV, "").strip()


def _client_id() -> str:
    return os.environ.get(OIDC_CLIENT_ID_ENV, "").strip()


def _audience() -> str:
    return os.environ.get(OIDC_AUDIENCE_ENV, "").strip()


def _role_claim() -> str:
    return os.environ.get(OIDC_ROLE_CLAIM_ENV, "roles").strip() or "roles"


def _scope_claim() -> str:
    return os.environ.get(OIDC_SCOPE_CLAIM_ENV, "entitlements").strip() or "entitlements"


def _allow_insecure() -> bool:
    return os.environ.get(OIDC_ALLOW_HTTP_ENV, "").strip().lower() in {"1", "true", "yes"}
