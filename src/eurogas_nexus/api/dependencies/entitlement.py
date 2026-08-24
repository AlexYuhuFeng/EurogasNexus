"""Entitlement and export enforcement dependency for API routes.

All routes that serve governed data should depend on require_entitlement
to enforce fail-closed entitlement policy.

本模块是数据治理闸门的统一入口：凡提供受治理数据（商业数据源）的路由
必须挂载此依赖；未知来源一律 403（fail-closed），绝不允许"未评估即放行"。
"""

from fastapi import HTTPException, Request

from eurogas_nexus.security.identity import (
    legacy_public_token_principal,
    principal_allows_source_family,
)


async def require_entitlement(request: Request, source_system: str = "") -> None:
    """FastAPI dependency that fails closed for unknown commercial data sources.

    对指定数据源做 entitlement 裁决的依赖注入函数（审计项 P0-2）。

    Args:
        request: The incoming FastAPI request (unused except for dependency
            wiring; kept for FastAPI injection signature).
        source_system: Source system to evaluate, e.g. ``"GIE"``. Empty
            means the route serves no governed source and the check passes.

    Returns:
        None when access is granted (or no source is governed).

    Raises:
        HTTPException: 403 with ``entitlement_denied`` when the source is not
            in the known-entitled set, and 403 with ``entitlement_unavailable``
            when the governance module itself cannot be evaluated — an unknown
            entitlement state is never a grant (P0-2).
    """

    if not source_system:
        return

    try:
        from eurogas_nexus.governance.entitlement import entitlement_check

        # V1 决策支持场景的已知授权来源白名单：与治理登记表保持同步，
        # 新增商业来源必须先经治理评审再进白名单。
        known = frozenset({
            "operator-input", "ENTSOG", "GIE", "ECB",
            "EEX", "Trayport", "ICE_OCM", "Weather",
        })
        identity = getattr(request.state, "identity", legacy_public_token_principal())
        if not principal_allows_source_family(identity, source_system):
            _record_denial(source_system, identity.principal_id, "identity_scope_denied")
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "entitlement_denied",
                    "source_system": source_system,
                    "reason": (
                        f"Authenticated identity {identity.principal_id!r} has no "
                        "data-scope grant for this commercial source family "
                        "(fail-closed)."
                    ),
                    "research_only": True,
                    "human_review_required": True,
                },
            )
        decision = entitlement_check(source_system, known_entitled_systems=known)
        if not decision.granted:
            _record_denial(source_system, identity.principal_id, "entitlement_denied")
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
    except Exception as exc:
        # 治理模块不可用时必须 fail-closed：未知授权状态绝不等于放行。
        raise HTTPException(
            status_code=403,
            detail={
                "error": "entitlement_unavailable",
                "source_system": source_system,
                "reason": (
                    "Entitlement evaluation is unavailable; access is denied "
                    "fail-closed."
                ),
                "error_class": exc.__class__.__name__,
                "research_only": True,
                "human_review_required": True,
            },
        ) from exc


def _record_denial(source_system: str, principal: str, reason: str) -> None:
    """Best-effort audit a fail-closed entitlement denial."""

    try:
        from eurogas_nexus.application.audit_service import record_audit_event

        record_audit_event(
            event_type="governance.policy",
            action="entitlement.denied",
            resource=f"source:{source_system}",
            principal=principal,
            outcome="denied",
            severity="warning",
            detail=f"reason={reason}",
            source_system="entitlement",
        )
    except Exception:
        return
