"""Enterprise interactive authentication endpoints (OIDC + sessions).

The browser flow uses Authorization Code + PKCE and a backend HttpOnly session
cookie. The desktop flow exchanges its system-browser authorization code for a
short-lived opaque session token held in desktop memory. No OIDC token is
returned to the browser.

``GET /api/me`` fails closed with 401 for a caller that presented no
credential at all; the legacy service principal is only returned when a
credential was actually validated, or when the release profile verified the
static deployment API token (SDK/CLI compatibility).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from eurogas_nexus.api.dependencies.identity import (
    IDENTITY_AUTHENTICATED_FLAG,
    PUBLIC_TOKEN_VERIFIED_FLAG,
    require_identity_for_route,
)
from eurogas_nexus.api.route_profiles import get_route_profile
from eurogas_nexus.core.config import resolve_dev_login_credentials_from_env
from eurogas_nexus.security.cookie_policy import (
    deployment_cookie_context,
    request_cookie_secure,
)
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


def _cookie_secure(request: Request) -> bool:
    """Whether cookies for this request must be HTTPS-only.

    Delegates to the explicit policy in ``eurogas_nexus.security.cookie_policy``:
    a production deployment is always ``Secure`` even when the request scheme
    looks like ``http`` because a reverse proxy in front of the API is not in
    uvicorn's trusted-proxy list.
    """

    api_profile, environment = deployment_cookie_context(request)
    return request_cookie_secure(request, api_profile=api_profile, environment=environment)


def _secure_attribute(request: Request) -> str:
    return "Secure; " if _cookie_secure(request) else ""


def _session_cookie(token: str, *, request: Request, max_age_seconds: int) -> str:
    return (
        f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax; "
        f"{_secure_attribute(request)}Max-Age={max_age_seconds}"
    )


def _verifier_cookie(verifier: str, *, request: Request) -> str:
    return (
        f"{OIDC_VERIFIER_COOKIE}={verifier}; Path=/api/auth; HttpOnly; "
        f"SameSite=Lax; {_secure_attribute(request)}Max-Age=300"
    )


@router.get("/api/auth/status")
def auth_status(request: Request) -> dict:
    """Return safe SSO configuration state for the login screen."""

    return {
        "data": {
            "oidc_configured": oidc_configured(),
            "session_cookie": bool(request.cookies.get(SESSION_COOKIE)),
            "profile": configured_oidc_profile() if oidc_configured() else None,
            "dev_login": _dev_login_available(request),
            # Local accounts (user name and password) for firms without SSO.
            "local_login": _local_login_available(),
        },
        "meta": {"research_only": False, "human_review_required": False},
    }


def _dev_login_available(request: Request) -> bool:
    """True only when the dev routes are mounted and their credentials exist.

    The development credential login is never registered by the internal or
    release route profiles, so this flag cannot be true outside the
    development profile even when the environment variables are set.
    """

    profile = getattr(request.app.state, "route_profile", None)
    if profile is None:
        settings = getattr(request.app.state, "settings", None)
        if settings is None:
            return False
        profile = get_route_profile(settings.api_profile)
    if not bool(getattr(profile, "include_dev", False)):
        return False
    return resolve_dev_login_credentials_from_env() is not None


def _local_login_available() -> bool:
    from eurogas_nexus.security.local_accounts_policy import local_accounts_enabled

    try:
        return local_accounts_enabled()
    except Exception:  # noqa: BLE001 - the sign-in screen must render whatever happens
        return False


class LocalLoginRequest(BaseModel):
    """User name (or e-mail) and password of a local account."""

    username: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=256)
    #: "desktop" returns the session token in the body (held in memory); see dev login.
    client: Literal["browser", "desktop"] = "browser"


class PasswordChangeRequest(BaseModel):
    """The forced password change after a temporary-password sign-in."""

    change_token: str = Field(min_length=16, max_length=128)
    new_password: str = Field(min_length=1, max_length=256)
    client: Literal["browser", "desktop"] = "browser"


class OwnPasswordChangeRequest(BaseModel):
    """A signed-in person changes their own password."""

    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


def _local_session_max_age() -> int:
    from eurogas_nexus.db.repositories.security import session_absolute_ttl

    return int(session_absolute_ttl().total_seconds())


LOCAL_SESSION_MAX_AGE_SECONDS = 12 * 3600  # kept for importers; the cookie uses the setting


def _client_address(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _refuse_foreign_origin(request: Request) -> None:
    """Login CSRF: a sign-in posted from another site's page is refused.

    The login entry points are exempt from the session CSRF header (there is no session
    yet), so they check the Origin a browser always sends with a cross-site POST.
    """

    from eurogas_nexus.api.middleware.origin_csrf import _origin_allowed

    origin = request.headers.get("origin")
    if not origin:
        return
    headers = {
        key.encode("latin-1"): value.encode("latin-1") for key, value in request.headers.items()
    }
    if not _origin_allowed(origin, headers):
        raise HTTPException(
            status_code=403,
            detail={"error": "origin_not_allowed", "message": "Sign-in from another site refused."},
        )


def _account_error(exc) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"error": exc.code, "code": exc.code, "message": exc.message},
    )


@router.post("/api/auth/login")
def local_login(
    body: LocalLoginRequest,
    request: Request,
    _rate: None = Depends(require_auth_rate_limit),
) -> JSONResponse:
    """Sign in to a local account (user name or e-mail, and password).

    Every refusal answers 401 ``invalid_credentials`` with one message, whatever the
    reason (unknown name, wrong password, locked, disabled); the audit trail records the
    reason. A temporary password answers 200 with ``password_change_required`` and a
    single-use ``change_token`` instead of a session: the person chooses a password at
    ``POST /api/auth/password-change`` first. 429 after repeated failures from one address.
    """

    from eurogas_nexus.application import local_accounts

    _refuse_foreign_origin(request)
    _require_db()
    sqlalchemy_error = _sqlalchemy_error_type()
    client_type = "local_password_desktop" if body.client == "desktop" else "local_password"
    try:
        with _session() as session:
            try:
                outcome = local_accounts.sign_in(
                    session,
                    username=body.username,
                    password=body.password,
                    source_address=_client_address(request),
                    client_type=client_type,
                )
            except local_accounts.LocalAccountError as exc:
                session.commit()  # keep the failure count and the audit of the refusal
                raise _account_error(exc) from exc
            payload = _principal_permissions(session, outcome.principal)
            session.commit()
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc
    if outcome.mfa_token:
        return _second_factor_step(outcome, payload)
    if outcome.change_token:
        return JSONResponse(
            {
                "data": {
                    "authenticated": False,
                    "password_change_required": True,
                    "change_token": outcome.change_token,
                    "display_name": payload["display_name"],
                    "expires_in_seconds": int(
                        local_accounts.CHANGE_TOKEN_TTL.total_seconds()
                    ),
                },
                "meta": {"research_only": False, "human_review_required": False},
            },
            headers={"Cache-Control": "no-store"},
        )
    return _signed_in(request, outcome, payload, client=body.client)


@router.post("/api/auth/password-change")
def local_password_change(
    body: PasswordChangeRequest,
    request: Request,
    _rate: None = Depends(require_auth_rate_limit),
) -> JSONResponse:
    """Choose a password after a temporary-password sign-in; opens the session.

    The single-use ``change_token`` from ``POST /api/auth/login`` is the authority (it
    expires in 10 minutes). Policy: 12-128 characters, not the user name, not a common
    password. Every earlier session of the person ends.
    """

    from eurogas_nexus.application import local_accounts

    _refuse_foreign_origin(request)
    _require_db()
    sqlalchemy_error = _sqlalchemy_error_type()
    client_type = "local_password_desktop" if body.client == "desktop" else "local_password"
    try:
        with _session() as session:
            try:
                outcome = local_accounts.complete_password_change(
                    session,
                    change_token=body.change_token,
                    new_password=body.new_password,
                    client_type=client_type,
                )
            except local_accounts.LocalAccountError as exc:
                session.rollback()
                raise _account_error(exc) from exc
            payload = _principal_permissions(session, outcome.principal)
            session.commit()
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc
    if outcome.mfa_token:
        return _second_factor_step(outcome, payload)
    return _signed_in(request, outcome, payload, client=body.client)


def _second_factor_step(outcome, payload: dict) -> JSONResponse:
    """The password was right; the session opens after the second factor (H6)."""

    from eurogas_nexus.application.mfa import CHALLENGE_TTL

    return JSONResponse(
        {
            "data": {
                "authenticated": False,
                "password_change_required": False,
                "mfa_required": True,
                "mfa_token": outcome.mfa_token,
                "display_name": payload["display_name"],
                "expires_in_seconds": int(CHALLENGE_TTL.total_seconds()),
            },
            "meta": {"research_only": False, "human_review_required": False},
        },
        headers={"Cache-Control": "no-store"},
    )


class MfaVerifyRequest(BaseModel):
    """The code step of a sign-in with a second factor."""

    mfa_token: str = Field(min_length=16, max_length=128)
    code: str | None = Field(default=None, max_length=12)
    recovery_code: str | None = Field(default=None, max_length=24)
    client: Literal["browser", "desktop"] = "browser"


@router.post("/api/auth/mfa/verify")
def local_mfa_verify(
    body: MfaVerifyRequest,
    request: Request,
    _rate: None = Depends(require_auth_rate_limit),
) -> JSONResponse:
    """Send the authenticator code (or a recovery code) after the password; opens the session.

    401 ``mfa_code_invalid`` for a wrong code (five end the step), 401 ``mfa_challenge_invalid``
    when the step expired (five minutes): sign in again.
    """

    from eurogas_nexus.application import local_accounts

    _refuse_foreign_origin(request)
    _require_db()
    if not (body.code or body.recovery_code):
        raise HTTPException(status_code=422, detail={"code": "mfa_code_required"})
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        with _session() as session:
            try:
                outcome = local_accounts.complete_mfa_sign_in(
                    session,
                    mfa_token=body.mfa_token,
                    code=body.code,
                    recovery_code=body.recovery_code,
                )
            except local_accounts.LocalAccountError as exc:
                session.commit()  # keep the attempt count and the audit of the refusal
                raise _account_error(exc) from exc
            payload = _principal_permissions(session, outcome.principal)
            session.commit()
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc
    return _signed_in(request, outcome, payload, client=body.client)


class MfaCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=12)


def _me_row(session, request: Request):
    from eurogas_nexus.db.models import IdentityPrincipalRecord

    identity = getattr(request.state, "identity", None)
    row = session.get(IdentityPrincipalRecord, getattr(identity, "principal_id", "") or "")
    if row is None or getattr(identity, "auth_method", "") != "session":
        raise HTTPException(
            status_code=403,
            detail={"code": "mfa_session_required",
                    "message": "Set up a second factor from a signed-in session."},
        )
    return row


def _mfa_error(exc) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}
    )


@router.get("/api/me/mfa")
def own_mfa_status(request: Request) -> dict:
    """Whether the caller has a second factor, and whether the policy requires one."""

    from eurogas_nexus.application import mfa

    _require_db()
    with _session() as session:
        row = _me_row(session, request)
        return {"data": mfa.status(session, row), "meta": {"research_only": False}}


@router.post("/api/me/mfa/enrol")
def own_mfa_enrol(request: Request) -> JSONResponse:
    """A new authenticator secret for the caller, shown once (not active until confirmed)."""

    from eurogas_nexus.application import mfa

    _require_db()
    with _session() as session:
        row = _me_row(session, request)
        try:
            data = mfa.begin_enrolment(session, row)
        except mfa.MfaError as exc:
            raise _mfa_error(exc) from exc
        session.commit()
    return JSONResponse({"data": data, "meta": {"research_only": False}},
                        headers={"Cache-Control": "no-store"})


@router.post("/api/me/mfa/confirm")
def own_mfa_confirm(body: MfaCodeRequest, request: Request) -> JSONResponse:
    """Confirm the secret with a code; answers ten single-use recovery codes, once."""

    from eurogas_nexus.application import mfa

    _require_db()
    with _session() as session:
        row = _me_row(session, request)
        try:
            data = mfa.confirm_enrolment(session, row, body.code)
        except mfa.MfaError as exc:
            session.rollback()
            raise _mfa_error(exc) from exc
        session.commit()
    return JSONResponse({"data": data, "meta": {"research_only": False}},
                        headers={"Cache-Control": "no-store"})


@router.post("/api/me/password")
def own_password_change(
    body: OwnPasswordChangeRequest,
    request: Request,
    _identity: None = Depends(require_identity_for_route),
) -> JSONResponse:
    """A signed-in local-account user changes their own password.

    Requires the current password. Every other session of the person ends; this browser
    gets a fresh session. SSO users change their password at the company provider.
    """

    from eurogas_nexus.application import local_accounts

    if not _credential_authenticated(request):
        raise HTTPException(status_code=401, detail={"error": "unauthenticated"})
    principal = getattr(request.state, "identity", None)
    principal_id = getattr(principal, "principal_id", None)
    if not principal_id:
        raise HTTPException(status_code=401, detail={"error": "unauthenticated"})
    _require_db()
    desktop = bool((request.headers.get("X-Eurogas-Session") or "").strip()) and not (
        request.cookies.get(SESSION_COOKIE)
    )
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        with _session() as session:
            try:
                outcome = local_accounts.change_own_password(
                    session,
                    principal_id=principal_id,
                    current_password=body.current_password,
                    new_password=body.new_password,
                    source_address=_client_address(request),
                    client_type="local_password_desktop" if desktop else "local_password",
                )
            except local_accounts.LocalAccountError as exc:
                if exc.code == "current_password_incorrect":
                    session.commit()  # the failed attempt counts towards the back-off
                else:
                    session.rollback()
                raise _account_error(exc) from exc
            payload = _principal_permissions(session, outcome.principal)
            session.commit()
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc
    return _signed_in(request, outcome, payload, client="desktop" if desktop else "browser")


def _principal_permissions(session, principal) -> dict:
    from eurogas_nexus.application.enterprise_auth import principal_payload

    return principal_payload(session, principal)


def _signed_in(request: Request, outcome, payload: dict, *, client: str) -> JSONResponse:
    data = {
        "authenticated": True,
        "password_change_required": False,
        "principal_id": payload["principal_id"],
        "display_name": payload["display_name"],
        "role": payload["role"],
        "permissions": payload["permissions"],
        # The policy requires a second factor this person has not set up: the session opens
        # the enrolment only (security review H6).
        "mfa_enrolment_required": bool(getattr(outcome, "mfa_enrolment_required", False)),
    }
    meta: dict = {"research_only": False, "human_review_required": False}
    if client == "desktop":
        data["session_token"] = outcome.session_token
        data["token_type"] = "session"
        data["expires_in_seconds"] = _local_session_max_age()
        meta["warnings"] = ["Keep this token in memory only; never store it on disk."]
        return JSONResponse({"data": data, "meta": meta}, headers={"Cache-Control": "no-store"})
    response = JSONResponse({"data": data, "meta": meta}, headers={"Cache-Control": "no-store"})
    response.headers["Set-Cookie"] = _session_cookie(
        outcome.session_token, request=request, max_age_seconds=_local_session_max_age()
    )
    return response


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
            try:
                result = complete_browser_login(
                    session,
                    code=code or "",
                    state=state or "",
                    verifier=verifier,
                    redirect_uri=redirect_uri,
                )
            except OidcValidationError as exc:
                _keep_pending_registration(session, exc)
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
            try:
                result = complete_desktop_login(
                    session,
                    code=body.code,
                    state=body.state,
                    verifier=body.code_verifier,
                    redirect_uri=body.redirect_uri,
                )
            except OidcValidationError as exc:
                _keep_pending_registration(session, exc)
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


def _ai_state(principal) -> dict:
    from eurogas_nexus.api.dependencies.ai_authority import ai_authority_denial
    from eurogas_nexus.application.ai_controls import ai_state

    state = ai_state(role_denied=bool(ai_authority_denial(principal)))
    # The provider and the sharing choices are administration facts: a person sees whether
    # AI is on and why not, an administrator sees the rest on the settings page.
    return {"available": state["available"], "reason": state["reason"]}


@router.get("/api/me")
def get_me(
    request: Request,
    _identity: None = Depends(require_identity_for_route),
) -> dict:
    """Return safe current-user capability information.

    Anonymous callers get 401 ``unauthenticated``: attaching the legacy
    service principal for SDK/CLI compatibility is not an authentication. The
    legacy principal is still returned when the release profile verified the
    static deployment API token, when a DB identity key or OIDC access token
    validated, or when a backend session cookie resolved.
    """

    if not _credential_authenticated(request):
        raise HTTPException(
            status_code=401,
            detail={
                "error": "unauthenticated",
                "message": "No authenticated identity was presented.",
            },
        )
    principal = getattr(request.state, "identity", legacy_public_token_principal())
    session_token = request.cookies.get(SESSION_COOKIE, "")
    from eurogas_nexus.api.middleware.origin_csrf import csrf_for_session

    csrf_token = csrf_for_session(session_token) if session_token else None
    from eurogas_nexus.security.authorization import permissions_for_principal
    from eurogas_nexus.security.capabilities import build_experience_profile

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
            # Architecture V2 composition contract: capability names, functional
            # assignments and work modes. Composition only - it grants nothing,
            # and every route re-authorises the caller server-side.
            "experience": build_experience_profile(principal).to_payload(),
            # Whether AI can be used for this person now and why not (small-desk plan 3.6):
            # the client hides or labels every AI control from this; it grants nothing.
            "ai": _ai_state(principal),
        },
        "meta": {
            "research_only": False,
            "human_review_required": False,
            "source_references": ["identity"],
            "warnings": [],
        },
    }


def _credential_authenticated(request: Request) -> bool:
    """Whether this request presented a credential the backend validated."""

    if getattr(request.state, IDENTITY_AUTHENTICATED_FLAG, False):
        return True
    # Release profile: ``require_public_api_auth`` verified the static
    # deployment token before this route ran (the legacy compatibility case).
    return bool(getattr(request.state, PUBLIC_TOKEN_VERIFIED_FLAG, False))


@router.post("/api/auth/logout")
def logout(request: Request) -> dict:
    """Revoke the current backend session and clear its cookie."""

    # A browser session arrives as the cookie, a desktop session as the header.
    token = request.cookies.get(SESSION_COOKIE, "") or (
        request.headers.get("X-Eurogas-Session") or ""
    ).strip()
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
    response = JSONResponse({"data": {"logged_out": True}, "meta": {"research_only": False}})
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


PENDING_APPROVAL_CODE = "identity_pending_approval"


def _keep_pending_registration(session, exc: OidcValidationError) -> None:
    """Persist a just-in-time registration that was rejected for approval.

    Registration is not approval: the ``PENDING`` principal and its
    issuer+subject link are committed so an administrator can see and activate
    the identity, while this login attempt still fails closed. Any other
    validation error is re-raised untouched, so its transaction rolls back.
    """

    if exc.code != PENDING_APPROVAL_CODE:
        raise exc
    session.commit()
    raise _oidc_error(exc) from exc


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
