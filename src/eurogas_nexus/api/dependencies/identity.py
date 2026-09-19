"""FastAPI dependency that resolves the authenticated R32 identity.

Installed in every route profile (finding C5 / owner decision D1): a profile no longer decides
whether callers are identified. ``X-Eurogas-Identity`` carries a DB-backed bearer key, and a
presented OIDC access token or backend session cookie is validated the same way.

What a caller that presents *nothing* gets is the one thing that changed, and it is a deployment
statement rather than a code default:

* a **verified deployment token** (``require_public_api_auth``) still resolves to the legacy
  single-trust-domain service principal, because that is the documented SDK/CLI caller, and the
  request is marked ``request.state.identity_authenticated = False`` - attaching a compatibility
  principal is not the same thing as authenticating a caller;
* a deployment that has explicitly said it trusts its network
  (``EUROGAS_NEXUS_ALLOW_ANONYMOUS_CALLERS``) gets the same compatibility principal, so the old
  posture remains available and is now opt-in;
* otherwise the request is **refused** with 401 ``authentication_required``. The authentication
  routes and the health probes are exempt, because the login that would supply a credential cannot
  itself require one.

An identity already resolved by an outer layer is never replaced: overwriting it would silently
re-authorise a decision another layer already made, which is exactly the entitlement widening the
first attempt at this change produced.

The resolved principal is attached to ``request.state.identity`` for route-permission and
row-entitlement enforcement.
"""

from __future__ import annotations

from fastapi import HTTPException, Request

from eurogas_nexus.api.dependencies.exempt_paths import (
    CREDENTIAL_EXEMPT_PREFIXES,
    is_credential_exempt,
)
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

#: Paths that must answer without a credential. Declared once, in ``exempt_paths``, because the
#: public-token gate needs the same list; re-exported here for the readers of this dependency.
IDENTITY_EXEMPT_PREFIXES = CREDENTIAL_EXEMPT_PREFIXES


def _allow_anonymous(request: Request) -> bool:
    """Whether this deployment explicitly permits callers that present no credential."""

    settings = getattr(request.app.state, "settings", None)
    if settings is None:
        from eurogas_nexus.core.config import get_settings

        settings = get_settings()
    return bool(getattr(settings, "allow_anonymous_callers", False))


async def require_identity(request: Request) -> None:
    """Resolve and attach the authenticated principal for this request.

    ``request.state.identity_authenticated`` records whether a *real* credential (DB identity key,
    OIDC access token, or backend session cookie) was presented and validated. It stays ``False``
    for the two compatibility callers above, whose principal is attached but not authenticated.

    Args:
        request: The incoming request.

    Returns:
        None. The principal is attached to ``request.state``.

    Raises:
        HTTPException: 401 ``authentication_required`` when the caller presented no credential and
            the deployment has not opted into trusting its network.
    """

    if getattr(request.state, "identity", None) is not None:
        # Resolved earlier in the chain, and that decision is authoritative.
        return

    bearer = request.headers.get(IDENTITY_HEADER)
    oidc_token = request.headers.get(OIDC_ACCESS_TOKEN_HEADER)
    session_cookie = request.cookies.get(SESSION_COOKIE, "")

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

    verified_token = bool(getattr(request.state, PUBLIC_TOKEN_VERIFIED_FLAG, False))
    if verified_token or _allow_anonymous(request):
        request.state.identity = legacy_public_token_principal()
        request.state.identity_authenticated = False
        return

    if is_credential_exempt(request.url.path):
        # No principal is attached: an exempt route is reachable without one, and inventing a
        # compatibility caller here would report an identity the request never presented.
        return

    raise HTTPException(
        status_code=401,
        detail={
            "error": "authentication_required",
            "message": (
                "This deployment identifies its callers: present a session, an identity key, an "
                "OIDC access token, or the deployment API token."
            ),
        },
    )


async def require_identity_for_route(request: Request) -> None:
    """Resolve a presented credential for one route that needs the distinction.

    Kept for routes that must tell "authenticated" from "not" independently of the app-wide
    dependency (``GET /api/me``): it is a no-op once an identity is attached, and otherwise runs
    the same resolution - including the refusal of a caller that presented nothing.
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
