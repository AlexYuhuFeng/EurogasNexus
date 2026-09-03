"""Import-safe R32 identity and authorization primitives.

The supported production identity model is a local PostgreSQL principal
(``USER`` or ``SERVICE``) authenticated by a hashed bearer API key. Company
SSO/OIDC remains deferred to a separately reviewed R32A; no identity-provider
call or OIDC dependency is introduced here.

Roles and data scopes are the authorization inputs consumed by the FastAPI
permission dependency.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

PUBLIC_BASELINE_SOURCE_FAMILIES = frozenset(
    {
        "operator-input",
        "ENTSOG",
        "GIE",
        "ECB",
        "Weather",
    }
)

LEGACY_PUBLIC_TOKEN_PRINCIPAL_ID = "service:public-api"
IDENTITY_HEADER = "X-Eurogas-Identity"
IDENTITY_BEARER_PREFIX = "nexus_"


class Role(StrEnum):
    """Local identity roles, least-privilege ordered."""

    VIEWER = "VIEWER"
    ANALYST = "ANALYST"
    OPERATOR = "OPERATOR"
    ADMIN = "ADMIN"


ROLE_RANK: dict[Role, int] = {
    Role.VIEWER: 0,
    Role.ANALYST: 1,
    Role.OPERATOR: 2,
    Role.ADMIN: 3,
}


@dataclass(frozen=True)
class IdentityAuthError(Exception):
    """Safe identity authentication error; never carries key material."""

    code: str
    status_code: int
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    """Typed authenticated identity attached to ``request.state.identity``."""

    principal_id: str
    name: str
    principal_type: str
    role: str
    status: str
    data_scopes: tuple[str, ...] = ()
    auth_method: str = "identity_key"


@dataclass(frozen=True, slots=True)
class NewApiKey:
    """A newly generated API key returned exactly once."""

    key_id: str
    bearer: str
    key_prefix: str
    key_hash: str
    display_name: str
    created_at_utc: datetime = field(default_factory=lambda: datetime.now(UTC))


def role_value(value: str | None) -> Role:
    """Normalize a role string to the Role enum or fail closed."""

    normalized = (value or "").strip().upper()
    try:
        return Role(normalized)
    except ValueError as exc:
        raise IdentityAuthError(
            code="identity_role_invalid",
            status_code=422,
            message=(
                f"Unsupported role {value!r}; expected one of "
                f"{[item.value for item in Role]}."
            ),
        ) from exc


def role_allows(actual: str | Role, required: str | Role) -> bool:
    """Return whether ``actual`` satisfies ``required`` (ADMIN is superuser)."""

    try:
        actual_role = actual if isinstance(actual, Role) else Role(str(actual).upper())
        required_role = required if isinstance(required, Role) else Role(str(required).upper())
    except ValueError:
        return False
    return ROLE_RANK[actual_role] >= ROLE_RANK[required_role]


def legacy_public_token_principal() -> AuthenticatedPrincipal:
    """Compatibility principal for the static deployment API token.

    Deployments that send only ``X-Eurogas-Api-Key`` keep working as the
    single-trust-domain operator service. New multi-user clients should send
    ``X-Eurogas-Identity`` to obtain role/scope-limited authorization.
    """

    return AuthenticatedPrincipal(
        principal_id=LEGACY_PUBLIC_TOKEN_PRINCIPAL_ID,
        name="public-api",
        principal_type="SERVICE",
        role=Role.OPERATOR.value,
        status="ACTIVE",
        data_scopes=("*",),
        auth_method="legacy_public_token",
    )


def generate_api_key(*, key_id: str, display_name: str) -> NewApiKey:
    """Generate a bearer key and return its hash plus one-time plaintext."""

    secret = secrets.token_urlsafe(32)
    bearer = f"{IDENTITY_BEARER_PREFIX}{key_id}_{secret}"
    return NewApiKey(
        key_id=key_id,
        bearer=bearer,
        key_prefix=bearer[:24],
        key_hash=hash_key_secret(secret),
        display_name=display_name,
    )


def hash_key_secret(secret: str) -> str:
    """Return the non-reversible SHA-256 hex digest for a key secret."""

    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def verify_key_hash(secret: str, expected_hash: str) -> bool:
    """Constant-time compare a provided key secret against its stored hash."""

    return hmac.compare_digest(hash_key_secret(secret), expected_hash or "")


def parse_identity_bearer(value: str | None) -> tuple[str, str] | None:
    """Parse ``nexus_<key_id>_<secret>`` without exposing secrets in errors."""

    token = (value or "").strip()
    if not token.startswith(IDENTITY_BEARER_PREFIX):
        return None
    parts = token.split("_", 2)
    if len(parts) != 3 or not parts[1] or not parts[2]:
        return None
    return parts[1], parts[2]


def normalize_data_scope(value: str) -> str:
    """Normalize one data-scope family for storage/compare."""

    return (value or "").strip()


def source_family_for_entitlement(source_system: str) -> str:
    """Map a source system to its commercial entitlement family."""

    value = (source_system or "").strip()
    return value.removesuffix("_Sim") if value.endswith("_Sim") else value


def principal_allows_source_family(
    principal: AuthenticatedPrincipal,
    source_system: str,
) -> bool:
    """Fail-closed row-level commercial-data entitlement check.

    Public baseline families are available to every active authenticated
    principal. Commercial families (EEX, Trayport, ICE_OCM, etc.) require an
    explicit ``*`` or family grant in ``data_scopes``; unknown families always
    return False.
    """

    family = source_family_for_entitlement(source_system)
    if not family:
        return False
    if family in PUBLIC_BASELINE_SOURCE_FAMILIES:
        return True
    scopes = {normalize_data_scope(scope).casefold() for scope in principal.data_scopes}
    return "*" in scopes or family.casefold() in scopes
