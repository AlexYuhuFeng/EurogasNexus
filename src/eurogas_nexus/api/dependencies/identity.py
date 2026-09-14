"""FastAPI dependency that resolves the authenticated R32 identity.

Release profile only. ``X-Eurogas-Identity`` carries a DB-backed bearer key.
When no credential at all is presented (no identity header, no OIDC access
token, no session cookie), the already-verified public API token maps to the
legacy single-trust-domain service principal so existing SDK/Web deployments do
not break, but the request is explicitly marked
``request.state.identity_authenticated = False``: attaching a compatibility
principal is not the same thing as authenticating a caller. Routes that must
distinguish the two (``GET /api/me``) read that flag.

The resolved principal is attached to ``request.state.identity`` for
route-permission and row-entitlement enforcement.
"""

from __future__ import annotations

from fastapi import HTTPException, Request

from eurogas_nexus.security.identity import (
    IDENTITY_HEADER,
    AuthenticatedPrincipal,
    IdentityAuthError,
    legacy_public_token_principal,
)
from eurogas_nexus.security.oidc import (
    OidcValidationError,
    oidc_configured,
    validate_oidc_access_token,
)

OIDC_ACCESS_TOKEN_HEADER = "X-Eurogas-Oidc-Access-Token"
SESSION_COOKIE = "eurogas_session"
# Set by ``require_public_api_auth`` once the static deployment token verified.
PUBLIC_TOKEN_VERIFIED_FLAG = "public_api_token_verified"
IDENTITY_AUTHENTICATED_FLAG = "identity_authenticated"


async def require_identity(request: Request) -> None:
    """Resolve and attach the authenticated principal for this request.

    ``request.state.identity_authenticated`` records whether a *real*
    credential (DB identity key, OIDC access token, or backend session cookie)
    was presented and validated. It stays ``False`` when no credential at all
    is presented, even though the legacy service principal is still attached
    for SDK/CLI compatibility.
    """

    bearer = request.headers.get(IDENTITY_HEADER)
    oidc_token = request.headers.get(OIDC_ACCESS_TOKEN_HEADER)
    session_cookie = request.cookies.get(SESSION_COOKIE, "")
    if not (bearer or "").strip() and not (oidc_token or "").strip() and not session_cookie:
        request.state.identity = legacy_public_token_principal()
        request.state.identity_authenticated = False
        return

    if (bearer or "").strip():
        request.state.identity = _authenticate_identity_key(bearer)
        request.state.identity_authenticated = True
        return

    if (oidc_token or "").strip():
        request.state.identity = _authenticate_oidc(oidc_token)
        request.state.identity_authenticated = True
        return

    if session_cookie:
        request.state.identity = _authenticate_session_cookie(request, session_cookie)
        request.state.identity_authenticated = True
        return

    request.state.identity = _authenticate_identity_key(bearer)
    request.state.identity_authenticated = True


async def require_identity_for_route(request: Request) -> None:
    """Resolve a presented credential for one route that needs the distinction.

    The release profile installs ``require_identity`` application-wide, but the
    development and internal profiles install no auth dependency at all. A route
    that must still tell "authenticated" from "anonymous" (``GET /api/me``)
    depends on this thin wrapper, which is a no-op once an identity is already
    attached.
    """

    if getattr(request.state, "identity", None) is not None:
        return
    await require_identity(request)


def _authenticate_identity_key(bearer: str) -> AuthenticatedPrincipal:
    if not _db_is_configured():
        raise HTTPException(
            status_code=503,
            detail={
                "error": "identity_store_not_configured",
                "message": (
                    "X-Eurogas-Identity authentication requires the runtime DB."
                ),
            },
        )
    try:
        from eurogas_nexus.db.repositories.identity import authenticate_identity_bearer
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            principal = authenticate_identity_bearer(session, bearer)
            session.commit()
    except IdentityAuthError as exc:
        _audit_auth_failure(exc.code)
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": exc.code, "message": exc.message},
        ) from exc
    except _sqlalchemy_error_type() as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "identity_store_unavailable",
                "message": "Identity store is configured but unavailable.",
                "error_class": exc.__class__.__name__,
            },
        ) from exc
    return principal


def _authenticate_session_cookie(request: Request, token: str) -> AuthenticatedPrincipal:
    if not _db_is_configured():
        raise HTTPException(
            status_code=503,
            detail={"error": "identity_store_not_configured"}
        )
    try:
        from eurogas_nexus.db.models import IdentityPrincipalRecord
        from eurogas_nexus.db.repositories.security import (
            get_active_session_by_token,
            touch_session,
        )
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            session_row = get_active_session_by_token(session, token)
            if session_row is None:
                _audit_auth_failure("session_invalid")
                raise HTTPException(
                    status_code=401,
                    detail={
                        "error": "session_invalid",
                        "message": "Session is invalid or expired.",
                    },
                )
            principal = session.get(IdentityPrincipalRecord, session_row.principal_id)
            if principal is None or principal.status != "ACTIVE":
                _audit_auth_failure("session_principal_inactive")
                raise HTTPException(
                    status_code=403,
                    detail={"error": "session_principal_inactive"},
                )
            touch_session(session, session_row)
            resolved = AuthenticatedPrincipal(
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
            session.commit()
    except HTTPException:
        raise
    except _sqlalchemy_error_type() as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": "identity_store_unavailable", "error_class": exc.__class__.__name__},
        ) from exc
    return resolved


def _authenticate_oidc(token: str) -> AuthenticatedPrincipal:
    """Validate an OIDC access token and map its claims to a principal."""

    if not oidc_configured():
        _audit_auth_failure("oidc_not_configured")
        raise HTTPException(
            status_code=503,
            detail={
                "error": "oidc_not_configured",
                "message": (
                    "OIDC access-token authentication requires "
                    "EUROGAS_NEXUS_OIDC_ISSUER and EUROGAS_NEXUS_OIDC_CLIENT_ID."
                ),
            },
        )
    try:
        identity = validate_oidc_access_token(token)
    except OidcValidationError as exc:
        _audit_auth_failure(exc.code)
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": exc.code, "message": exc.message},
        ) from exc
    return AuthenticatedPrincipal(
        principal_id=f"oidc:{identity.subject}",
        name=identity.name,
        principal_type="USER",
        role=identity.role,
        status="ACTIVE",
        data_scopes=identity.data_scopes,
        roles=(identity.role,),
        email=identity.email,
        identity_source="OIDC",
        auth_method="oidc_access_token",
    )


def _audit_auth_failure(code: str) -> None:
    """Best-effort audit a failed identity-key authentication."""

    try:
        from eurogas_nexus.application.audit_service import record_audit_event

        record_audit_event(
            event_type="governance.identity",
            action="identity.authentication.denied",
            resource="identity_api_keys",
            principal="anonymous",
            outcome="denied",
            severity="warning",
            detail=f"reason={code}",
            source_system="identity",
        )
    except Exception:
        return


def _db_is_configured() -> bool:
    from eurogas_nexus.db.session import resolve_database_url

    return resolve_database_url() is not None


def _sqlalchemy_error_type():
    from sqlalchemy.exc import SQLAlchemyError

    return SQLAlchemyError
