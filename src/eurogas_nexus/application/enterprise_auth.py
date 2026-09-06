"""Enterprise authentication application service (OIDC + sessions).

Authorization-code + PKCE login resolves issuer+subject to a local principal,
creates a backend session, and never returns OIDC tokens to the browser. The
desktop flow returns one short-lived opaque session token for in-memory use.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from eurogas_nexus.db.models import IdentityPrincipalRecord
from eurogas_nexus.db.repositories import identity as identity_repository
from eurogas_nexus.db.repositories.security import (
    consume_oidc_authorization_state,
    create_external_identity,
    create_oidc_authorization_state,
    create_session,
    find_external_identity,
    hash_code_verifier,
)
from eurogas_nexus.domain.dataops.contracts import as_utc
from eurogas_nexus.security.authorization import (
    permissions_for_principal,
)
from eurogas_nexus.security.identity import (
    AuthenticatedPrincipal,
    Role,
    role_value,
)
from eurogas_nexus.security.oidc import (
    OidcValidationError,
    approved_domains,
    exchange_authorization_code,
    groups_role_map,
    groups_scope_map,
    oidc_authorization_url,
    provisioning_mode,
    validate_oidc_access_token,
)

SESSION_COOKIE = "eurogas_session"
OIDC_VERIFIER_COOKIE = "eurogas_oidc_verifier"


class LoginStart:
    """Login-start result: state, verifier and provider URL."""

    def __init__(self, state: str, verifier: str, url: str) -> None:
        self.state = state
        self.verifier = verifier
        self.url = url


class LoginResult:
    """Completed login: principal id and one-time session token."""

    def __init__(self, principal_id: str, session_token: str, principal_name: str) -> None:
        self.principal_id = principal_id
        self.session_token = session_token
        self.principal_name = principal_name


def pkce_pair() -> tuple[str, str]:
    """Return (verifier, S256 challenge) for one login."""

    verifier = secrets.token_urlsafe(48)
    challenge = (
        hashlib.sha256(verifier.encode("ascii"))
        .digest()
        .hex()
    )
    return verifier, challenge


def start_browser_login(
    session: Session,
    *,
    redirect_uri: str,
    http_get: Callable[..., Any] | None = None,
    now_utc: datetime | None = None,
) -> LoginStart:
    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    verifier, challenge = pkce_pair()
    now = as_utc(now_utc or datetime.now(UTC))
    create_oidc_authorization_state(
        session,
        state=state,
        code_challenge=challenge,
        code_challenge_method="S256",
        code_verifier=verifier,
        nonce=nonce,
        redirect_uri=redirect_uri,
        flow_type="browser",
        client_type="browser",
        now_utc=now,
    )
    url = oidc_authorization_url(
        state=state,
        code_challenge=challenge,
        redirect_uri=redirect_uri,
        nonce=nonce,
        http_get=http_get,
    )
    return LoginStart(state=state, verifier=verifier, url=url)


def start_desktop_login(
    session: Session,
    *,
    code_challenge: str,
    code_verifier: str,
    redirect_uri: str,
    http_get: Callable[..., Any] | None = None,
    now_utc: datetime | None = None,
) -> LoginStart:
    """Register a desktop PKCE authorization request and return provider URL."""

    state = secrets.token_urlsafe(24)
    nonce = secrets.token_urlsafe(24)
    now = as_utc(now_utc or datetime.now(UTC))
    create_oidc_authorization_state(
        session,
        state=state,
        code_challenge=code_challenge,
        code_challenge_method="S256",
        code_verifier=code_verifier,
        nonce=nonce,
        redirect_uri=redirect_uri,
        flow_type="desktop",
        client_type="desktop",
        now_utc=now,
    )
    url = oidc_authorization_url(
        state=state,
        code_challenge=code_challenge,
        redirect_uri=redirect_uri,
        nonce=nonce,
        http_get=http_get,
    )
    return LoginStart(state=state, verifier=code_verifier, url=url)


def complete_browser_login(
    session: Session,
    *,
    code: str,
    state: str,
    verifier: str,
    redirect_uri: str,
    http_get: Callable[..., Any] | None = None,
    http_post: Callable[..., Any] | None = None,
    now_utc: datetime | None = None,
) -> LoginResult:
    identity = _exchange_and_validate(
        session,
        code=code,
        state=state,
        verifier=verifier,
        redirect_uri=redirect_uri,
        http_get=http_get,
        http_post=http_post,
        now_utc=now_utc,
    )
    token = secrets.token_urlsafe(32)
    principal = _principal_for_identity(session, identity, now_utc=now_utc)
    create_session(
        session,
        principal_id=principal.principal_id,
        token=token,
        client_type="browser",
        now_utc=now_utc,
    )
    return LoginResult(
        principal_id=principal.principal_id,
        session_token=token,
        principal_name=principal.name,
    )


def complete_desktop_login(
    session: Session,
    *,
    code: str,
    state: str,
    verifier: str,
    redirect_uri: str,
    http_get: Callable[..., Any] | None = None,
    http_post: Callable[..., Any] | None = None,
    now_utc: datetime | None = None,
) -> LoginResult:
    identity = _exchange_and_validate(
        session,
        code=code,
        state=state,
        verifier=verifier,
        redirect_uri=redirect_uri,
        http_get=http_get,
        http_post=http_post,
        now_utc=now_utc,
    )
    token = secrets.token_urlsafe(32)
    principal = _principal_for_identity(session, identity, now_utc=now_utc)
    create_session(
        session,
        principal_id=principal.principal_id,
        token=token,
        client_type="desktop",
        now_utc=now_utc,
    )
    return LoginResult(
        principal_id=principal.principal_id,
        session_token=token,
        principal_name=principal.name,
    )


def _exchange_and_validate(
    session: Session,
    *,
    code: str,
    state: str,
    verifier: str,
    redirect_uri: str,
    http_get: Callable[..., Any] | None,
    http_post: Callable[..., Any] | None,
    now_utc: datetime | None,
) -> Any:
    now = as_utc(now_utc or datetime.now(UTC))
    auth_state = consume_oidc_authorization_state(session, state, now_utc=now)
    if auth_state is None:
        raise OidcValidationError(
            code="oidc_state_invalid",
            status_code=403,
            message="OIDC authorization state is invalid or expired.",
        )
    if auth_state.redirect_uri != redirect_uri:
        raise OidcValidationError(
            code="oidc_redirect_invalid",
            status_code=403,
            message="OIDC redirect URI does not match the authorization request.",
        )
    if auth_state.code_verifier_hash != hash_code_verifier(verifier):
        raise OidcValidationError(
            code="oidc_pkce_invalid",
            status_code=403,
            message="PKCE verifier does not match the authorization request.",
        )
    token_response = exchange_authorization_code(
        code=code,
        code_verifier=verifier,
        redirect_uri=redirect_uri,
        http_get=http_get,
        http_post=http_post,
    )
    id_token = token_response.get("id_token")
    if not isinstance(id_token, str) or not id_token:
        raise OidcValidationError(
            code="oidc_id_token_missing",
            status_code=503,
            message="OIDC token response did not include an id_token.",
        )
    return validate_oidc_access_token(
        id_token,
        http_get=http_get,
        now_utc=now,
        expected_nonce=auth_state.nonce,
    )


def _principal_for_identity(
    session: Session,
    identity,
    *,
    now_utc: datetime | None,
) -> IdentityPrincipalRecord:
    now = as_utc(now_utc or datetime.now(UTC))
    external = find_external_identity(session, identity.issuer, identity.subject)
    if external is None:
        principal = _provision_identity(session, identity, now_utc=now)
    else:
        principal = session.get(IdentityPrincipalRecord, external.principal_id)
    if principal is None or principal.status != "ACTIVE":
        raise OidcValidationError(
            code="identity_principal_not_active",
            status_code=403,
            message="Local identity is missing or not active.",
        )
    email = _email_from(identity)
    if external is None:
        create_external_identity(
            session,
            principal_id=principal.principal_id,
            issuer=identity.issuer,
            subject=identity.subject,
            provider_id="oidc",
            email=email,
            display_name=identity.name,
            now_utc=now,
        )
    principal.last_login_at_utc = now
    principal.updated_at_utc = now
    from eurogas_nexus.db.repositories.audit import record_audit_event

    record_audit_event(
        session,
        event_type="governance.auth",
        principal=principal.principal_id,
        action="auth.oidc.login",
        resource=f"identity_principal:{principal.principal_id}",
        outcome="success",
        severity="info",
        detail=f"issuer={identity.issuer}; subject={identity.subject[:32]}",
        source_system="oidc-auth",
        now_utc=now,
        client_type="oidc",
        correlation_id=None,
    )
    session.flush()
    return principal


def _provision_identity(
    session: Session,
    identity,
    *,
    now_utc: datetime,
) -> IdentityPrincipalRecord:
    now = as_utc(now_utc or datetime.now(UTC))
    mode = provisioning_mode()
    if mode != "approved_domain":
        raise OidcValidationError(
            code="external_identity_not_provisioned",
            status_code=403,
            message=(
                "External identity is not pre-provisioned. An administrator "
                "must link issuer+subject to a local principal."
            ),
        )
    email = _email_from(identity) or ""
    domain = email.partition("@")[2].lower()
    if domain not in approved_domains():
        raise OidcValidationError(
            code="external_identity_domain_not_approved",
            status_code=403,
            message="External identity email domain is not approved for JIT provisioning.",
        )
    role_by_group = groups_role_map()
    scope_by_group = groups_scope_map()
    roles = [role_by_group.get(group, "VIEWER") for group in identity.groups] or ["VIEWER"]
    scopes = sorted(
        {
            str(scope).upper()
            for group in identity.groups
            for scope in scope_by_group.get(group, [])
            if str(scope).strip()
        }
    )
    principal = identity_repository.create_identity_principal(
        session,
        name=f"oidc-{_safe_name(identity.subject)}",
        display_name=identity.name,
        role="VIEWER",
        principal_type="USER",
        data_scopes=scopes,
        now_utc=now,
    )
    principal.roles = sorted(set(roles)) or ["VIEWER"]
    rank = ["VIEWER", "REVIEWER", "ANALYST", "OPERATOR", "ADMIN"]
    principal.role = max(principal.roles, key=rank.index)
    principal.email = email or None
    principal.identity_source = "OIDC"
    session.flush()
    return principal


def _email_from(identity) -> str | None:
    return getattr(identity, "email", None) or None


def _safe_name(subject: str) -> str:
    cleaned = "".join(ch for ch in subject if ch.isalnum() or ch in "._@-")[:40]
    return cleaned or "oidc-user"


def principal_payload(session: Session, principal: IdentityPrincipalRecord) -> dict:
    permissions = sorted(
        permission.value
        for permission in permissions_for_principal(
            AuthenticatedPrincipal(
                principal_id=principal.principal_id,
                name=principal.name,
                principal_type=principal.principal_type,
                role=principal.role,
                status=principal.status,
                data_scopes=tuple(principal.data_scopes or []),
                roles=tuple(principal.roles or [principal.role]),
                email=principal.email,
                identity_source=principal.identity_source or "LOCAL",
                auth_method="session",
            )
        )
    )
    return {
        "principal_id": principal.principal_id,
        "principal_type": principal.principal_type,
        "name": principal.name,
        "display_name": principal.display_name,
        "email": principal.email,
        "identity_source": principal.identity_source or "LOCAL",
        "status": principal.status,
        "role": principal.role,
        "roles": list(principal.roles or [principal.role]),
        "data_scopes": list(principal.data_scopes or []),
        "permissions": permissions,
        "last_login_at_utc": (
            principal.last_login_at_utc.isoformat() if principal.last_login_at_utc else None
        ),
    }


def assign_access(
    session: Session,
    *,
    principal: IdentityPrincipalRecord,
    roles: list[str],
    data_scopes: list[str],
    actor: str,
    now_utc: datetime | None = None,
) -> IdentityPrincipalRecord:
    normalized_roles = [role_value(value).value for value in roles]
    if not normalized_roles:
        normalized_roles = [Role.VIEWER.value]
    principal.roles = normalized_roles
    principal.role = max(
        normalized_roles,
        key=lambda value: ["VIEWER", "REVIEWER", "ANALYST", "OPERATOR", "ADMIN"].index(value),
    )
    principal.data_scopes = [
        str(scope).strip().upper() for scope in data_scopes if str(scope).strip()
    ]
    principal.updated_at_utc = as_utc(now_utc or datetime.now(UTC))
    session.flush()
    return principal
