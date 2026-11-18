"""``GET /api/discoveries``: what needs the caller, ranked for one of their job functions.

Today ("What needs you") and the situational strip read it. The function is one the caller
holds (a persona never grants a read: every finding is built from reads that run under the
caller). An empty list means nothing needs them, not an error.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from eurogas_nexus.security.authorization import Permission, authorize
from eurogas_nexus.security.identity import AuthenticatedPrincipal, legacy_public_token_principal

router = APIRouter(tags=["discoveries"])


@router.get("/api/discoveries")
def get_discoveries(
    request: Request,
    function: str | None = Query(default=None, max_length=32),
    lang: str = Query(default="en", pattern="^(en|zh|zh-CN)$"),
    limit: int = Query(default=10, ge=1, le=25),
) -> dict:
    """Findings the caller may read, ranked and phrased for ``function``.

    Raises:
        HTTPException: 403 when ``function`` is not one of the caller's job functions.
    """

    identity = getattr(request.state, "identity", None)
    principal = (
        identity
        if isinstance(identity, AuthenticatedPrincipal)
        else legacy_public_token_principal()
    )
    if not authorize(principal, Permission.MARKET_READ).allowed:
        raise HTTPException(status_code=403, detail={"code": "permission_denied"})
    held = [str(item).upper() for item in getattr(principal, "job_functions", ()) or ()]
    chosen = (function or (held[0] if held else "")).upper() or None
    if function and chosen not in held:
        raise HTTPException(
            status_code=403,
            detail={"code": "function_not_held", "message": "Choose one of your job functions."},
        )
    from eurogas_nexus.application.discovery import discoveries
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None:
        raise HTTPException(status_code=503, detail={"code": "runtime_db_required"})
    with get_session_factory()() as session:
        data = discoveries(session, request, function=chosen, language=lang, limit=limit)
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["runtime-postgresql"],
            "warnings": data["warnings"],
        },
    }
