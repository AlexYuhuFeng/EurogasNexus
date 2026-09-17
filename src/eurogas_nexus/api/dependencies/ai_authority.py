"""Per-call AI authority dependency (Architecture V2, finding C8).

``02_ARCHITECTURE_CONSTITUTION.md`` rule 22 and
``08_DECISION_APPLICATION_AI.md`` section 4 make AI authority explicit:

    AI inherits the invoking user's authority, is re-authorised on every call,
    may not bypass entitlement, and its runs are recorded as observable actions
    rather than hidden reasoning.

``application/agents/runtime.py`` already re-authorises registry capability
invocations against a rebuilt principal. The *direct* provider routes did not: a route
permission from the read family was enough to spend a provider credential and return
model output composed from commercial evidence, with no principal, scope or
entitlement decision anywhere in the call. That is finding C8 in
``W0-03_ARCHITECTURE_RECONCILIATION.md``, and this dependency is the shared check the
direct routes now run.

What it decides:

- a **user** identity must hold ``analysis.query``. AI work over commercial evidence is
  commercial work, so a platform-administration identity does not hold it
  (``06_IDENTITY_ACCESS_CONTROL_PLANE.md`` section 7: administration is not a
  commercial super-user), and a viewer may read market data without spending analysis
  capability on it;
- the documented single-trust-domain **compatibility principal** (static deployment API
  token, ``legacy_public_token``) is accepted as before. Bounding that posture is
  finding C5; this dependency neither widens nor narrows it, and the carve-out is
  written down here rather than left implicit;
- the decision is **explicit and reported**: a refusal is ``403
  ai_authority_not_granted`` naming the permission that was missing, so a caller learns
  why the answer was withheld instead of receiving an unauthorised one.

Composition note: this only ever refuses. It grants nothing and adds no capability -
the model call still happens under the same entitlement the payload was composed with.
"""

from __future__ import annotations

from fastapi import HTTPException, Request

from eurogas_nexus.security.authorization import Permission, authorize
from eurogas_nexus.security.identity import (
    LEGACY_PUBLIC_TOKEN_PRINCIPAL_ID,
    AuthenticatedPrincipal,
    legacy_public_token_principal,
)

AI_AUTHORITY_DENIED = "ai_authority_not_granted"

#: The commercial capability a user identity needs before a provider may be invoked.
AI_AUTHORITY_PERMISSION = Permission.ANALYSIS_QUERY


def ai_caller(request: Request) -> AuthenticatedPrincipal:
    """Resolve the principal an AI invocation runs as.

    The authenticated identity when the deployment resolved one; otherwise the
    documented compatibility principal for the static deployment token, which is the
    same fallback every other governed read uses.
    """

    identity = getattr(request.state, "identity", None)
    if identity is not None:
        return identity
    return legacy_public_token_principal()


def ai_authority_denial(principal: AuthenticatedPrincipal) -> str:
    """Return why this principal may not invoke AI, or ``""`` when it may.

    The compatibility service principal is the deployment's own token: its authority is
    the deployment configuration, not a role assignment, so it keeps the posture it had
    before this check existed (finding C5 tracks that posture separately).
    """

    if principal.principal_id == LEGACY_PUBLIC_TOKEN_PRINCIPAL_ID:
        return ""
    if principal.principal_type != "USER":
        return (
            f"principal type {principal.principal_type!r} is not a user identity, so it "
            "holds no analysis capability of its own"
        )
    decision = authorize(principal, AI_AUTHORITY_PERMISSION)
    if decision.allowed:
        return ""
    return decision.reason or f"permission {AI_AUTHORITY_PERMISSION.value!r} is not granted"


def require_ai_authority(request: Request) -> AuthenticatedPrincipal:
    """Re-authorise one AI call against the calling identity's authority.

    Returns:
        The principal the invocation runs as, so the caller can attribute the run.

    Raises:
        HTTPException: 403 ``ai_authority_not_granted`` when the calling identity holds
            no analysis capability, with the permission that was missing.
    """

    principal = ai_caller(request)
    denial = ai_authority_denial(principal)
    if not denial:
        return principal

    raise HTTPException(
        status_code=403,
        detail={
            "error": AI_AUTHORITY_DENIED,
            "message": (
                "AI analysis runs under your own authority, and this identity does not "
                "hold the analysis capability it needs. Ask for the analysis.query "
                "permission (an ANALYST role grants it) instead of invoking a provider "
                "through a read-only route."
            ),
            "principal_id": principal.principal_id,
            "permission_required": AI_AUTHORITY_PERMISSION.value,
            "reason": denial,
        },
    )
