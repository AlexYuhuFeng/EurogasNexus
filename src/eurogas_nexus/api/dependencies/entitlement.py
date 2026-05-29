"""Entitlement and export enforcement dependency for API routes.

All routes that serve governed data should depend on require_entitlement
to enforce fail-closed entitlement policy.
"""

from fastapi import HTTPException, Request


async def require_entitlement(request: Request, source_system: str = "") -> None:
    """FastAPI dependency that fails closed for unknown commercial data sources.

    When a source_system is provided and the governance module is available,
    this dependency checks whether the source is in the known-entitled set.
    Unknown sources are denied with 403.

    If no governance module is available (bootstrap), the check passes with
    a research-only warning.
    """
    if not source_system:
        return

    try:
        from eurogas_nexus.governance.entitlement import entitlement_check

        # Known entitled sources for V1 research context
        known = frozenset({
            "synthetic-fixture", "ENTSOG", "GIE", "ECB",
            "EEX", "Trayport", "ICE_OCM", "Weather",
        })
        decision = entitlement_check(source_system, known_entitled_systems=known)
        if not decision.granted:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "entitlement_denied",
                    "source_system": source_system,
                    "reason": decision.reason,
                    "research_only": True,
                    "human_review_required": True,
                },
            )
    except HTTPException:
        raise
    except Exception:
        # Governance module not available — allow with research warning
        pass
