"""Enterprise interactive authentication endpoints (OIDC + sessions).

The browser flow uses Authorization Code + PKCE and a backend HttpOnly session
cookie. The desktop flow exchanges its system-browser authorization code for a
short-lived opaque session token held in desktop memory. No OIDC token is
returned to the browser.
"""

from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from eurogas_nexus.security.identity import legacy_public_token_principal
from eurogas_nexus.security.oidc import (
    OidcValidationError,
    configured_oidc_profile,
    oidc_configured,
)
from eurogas_nexus.security.rate_limit import require_auth_rate_limit

SESSION_COOKIE = "eurogas_session"
OIDC_VERIFIER_COOKIE = "eurogas_oidc_verifier"

router = APIRouter(tags=["auth"])


class DesktopLoginRequest(BaseModel):
    code_challenge: str = Field(min_length=43, max_length=128)
    code_verifier: str = Field(min_length=43, max_length=128)
    redirect_uri: str = Field(min_length=8, max_length=512)


class DesktopTokenRequest(BaseModel):
    """Desktop system-browser callback exchange."""

    code: str = Field(min_length=1, max_length=4096)
    state: str = Field(min_length=1, max_length=128)
    code_verifier: str = Field(min_length=43, max_length=128)
    redirect_uri: str = Field(min_length=8, max_length=512)


def _session_cookie(token: str, *, request: Request, max_age_seconds: int) -> str:
    secure = request.url.scheme == "https"
    value = (
        f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; "
        f"{'Secure; ' if secure else ''}Max-Age={max_age_seconds}"
    )
    return value


def _verifier_cookie(verifier: str, *, request: Request) -> str:
    secure = request.url.scheme == "https"
    return (
        f"{OIDC_VERIFIER_COOKIE}={verifier}; Path=/api/auth; HttpOnly; "
        f"SameSite=Lax; {'Secure; ' if secure else ''}Max-Age=300"
    )


@router.get("/api/auth/status")
def auth_status(request: Request) -> dict:
    """Return safe SSO configuration state for the login screen."""

    return {
        "data": {
            "oidc_configured": oidc_configured(),
            "session_cookie": bool(request.cookies.get(SESSION_COOKIE)),
            "profile": configured_oidc_profile() if oidc_configured() else None,
        },
        "meta": {"research_only": False, "human_review_required": False},
    }


@router.get("/api/auth/oidc/login")
def oidc_login(
    request: Request,
    _rate: None = Depends(require_auth_rate_limit),
) -> RedirectResponse:
    """Begin interactive SSO login (Authorization Code + PKCE)."""

    _require_db()
    if not oidc_configured():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "oidc_not_configured",
                "message": "Enterprise SSO is not configured for this deployment.",
            },
        )

    from eurogas_nexus.application.enterprise_auth import start_browser_login

    redirect_uri = _absolute_redirect_uri(request)
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        with _session() as session:
            start = start_browser_login(session, redirect_uri=redirect_uri)
            session.commit()
    except OidcValidationError as exc:
        raise _oidc_error(exc) from exc
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc
    response = RedirectResponse(url=start.url, status_code=302)
    response.headers["Set-Cookie"] = _verifier_cookie(start.verifier, request=request)
    return response


@router.get("/api/auth/oidc/callback")
def oidc_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    _rate: None = Depends(require_auth_rate_limit),
) -> RedirectResponse:
    """Complete browser SSO login and establish a backend session cookie."""

    _require_db()
    if error:
        raise HTTPException(
            status_code=400,
            detail={"code": "oidc_login_error", "message": "Identity provider returned an error."},
        )

    from eurogas_nexus.application.enterprise_auth import complete_browser_login

    verifier = request.cookies.get(OIDC_VERIFIER_COOKIE, "")
    redirect_uri = _absolute_redirect_uri(request)
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        with _session() as session:
            result = complete_browser_login(
                session,
                code=code or "",
                state=state or "",
                verifier=verifier,
                redirect_uri=redirect_uri,
            )
            session.commit()
    except OidcValidationError as exc:
        raise _oidc_error(exc) from exc
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc

    response = RedirectResponse(url="/", status_code=302)
    response.headers["Set-Cookie"] = _session_cookie(
        result.session_token,
        request=request,
        max_age_seconds=12 * 3600,
    )
    return response


@router.post("/api/auth/oidc/desktop/login")
def oidc_desktop_login(
    body: DesktopLoginRequest,
    _rate: None = Depends(require_auth_rate_limit),
) -> dict:
    """Register a desktop PKCE request and return the provider login URL."""

    from eurogas_nexus.application.enterprise_auth import start_desktop_login

    _require_db()
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        with _session() as session:
            start = start_desktop_login(
                session,
                code_challenge=body.code_challenge,
                code_verifier=body.code_verifier,
                redirect_uri=body.redirect_uri,
            )
            session.commit()
    except OidcValidationError as exc:
        raise _oidc_error(exc) from exc
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc
    return {
        "data": {
            "state": start.state,
            "authorization_url": start.url,
        },
        "meta": {"research_only": False, "human_review_required": False},
    }


@router.post("/api/auth/oidc/desktop/token")
def oidc_desktop_token(
    body: DesktopTokenRequest,
    request: Request,
    _rate: None = Depends(require_auth_rate_limit),
) -> dict:
    """Exchange a desktop system-browser code for a short-lived session token."""


    from eurogas_nexus.application.enterprise_auth import complete_desktop_login

    _require_db()
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        with _session() as session:
            result = complete_desktop_login(
                session,
                code=body.code,
                state=body.state,
                verifier=body.code_verifier,
                redirect_uri=body.redirect_uri,
            )
            session.commit()
    except OidcValidationError as exc:
        raise _oidc_error(exc) from exc
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc
    return {
        "data": {
            "access_token": result.session_token,
            "token_type": "Bearer",
            "principal_id": result.principal_id,
            "principal_name": result.principal_name,
            "expires_in_seconds": 12 * 3600,
        },
        "meta": {
            "research_only": False,
            "human_review_required": False,
            "warnings": ["Keep this token in memory only; never store it on disk."],
        },
    }


@router.get("/api/me")
def get_me(request: Request) -> dict:
    """Return safe current-user capability information."""

    principal = getattr(request.state, "identity", legacy_public_token_principal())
    session_token = request.cookies.get(SESSION_COOKIE, "")
    csrf_token = (
        hashlib.sha256(session_token.encode("utf-8")).hexdigest()[:32]
        if session_token
        else None
    )
    from eurogas_nexus.security.authorization import permissions_for_principal

    permissions = sorted(permission.value for permission in permissions_for_principal(principal))
    return {
        "data": {
            "principal_id": principal.principal_id,
            "name": principal.name,
            "principal_type": principal.principal_type,
            "role": principal.role,
            "roles": list(principal.roles or [principal.role]),
            "email": principal.email,
            "identity_source": principal.identity_source,
            "status": principal.status,
            "data_scopes": list(principal.data_scopes or []),
            "permissions": permissions,
            "auth_method": principal.auth_method,
            "csrf_token": csrf_token,
        },
        "meta": {
            "research_only": False,
            "human_review_required": False,
            "source_references": ["identity"],
            "warnings": [],
        },
    }


@router.post("/api/auth/logout")
def logout(request: Request) -> dict:
    """Revoke the current backend session and clear its cookie."""

    token = request.cookies.get(SESSION_COOKIE, "")
    if token:
        try:
            from eurogas_nexus.db.session import resolve_database_url

            if resolve_database_url() is not None:
                from eurogas_nexus.db.repositories.security import revoke_session_by_token

                with _session() as session:
                    revoke_session_by_token(session, token)
                    session.commit()
        except Exception:
            pass
    response = JSONResponse(
        {"data": {"logged_out": True}, "meta": {"research_only": False}}
    )
    response.delete_cookie(SESSION_COOKIE, path="/")
    response.delete_cookie(OIDC_VERIFIER_COOKIE, path="/api/auth")
    return response


def _absolute_redirect_uri(request: Request) -> str:
    from eurogas_nexus.security.oidc import oidc_redirect_uri

    configured = oidc_redirect_uri()
    if configured.startswith("http://") or configured.startswith("https://"):
        return configured
    base = str(request.base_url).rstrip("/")
    return f"{base}{configured}"


def _require_db() -> None:
    from eurogas_nexus.db.session import resolve_database_url

    if resolve_database_url() is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "runtime_db_required",
                "message": "Enterprise auth requires the runtime DB.",
            },
        )


def _session():
    from eurogas_nexus.db.session import get_session_factory

    return get_session_factory()()


def _sqlalchemy_error_type():
    from sqlalchemy.exc import SQLAlchemyError

    return SQLAlchemyError


def _db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "runtime_db_unavailable",
            "message": "Runtime DB is unavailable for authentication.",
            "error_class": exc.__class__.__name__,
        },
    )


def _oidc_error(exc: OidcValidationError) -> HTTPException:
    try:
        from eurogas_nexus.application.audit_service import record_audit_event

        record_audit_event(
            event_type="governance.auth",
            action="auth.oidc.failure",
            resource="oidc_login",
            principal="anonymous",
            outcome="denied",
            severity="warning",
            detail=f"reason={exc.code}",
            source_system="oidc-auth",
        )
    except Exception:
        pass
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.message},
    )
