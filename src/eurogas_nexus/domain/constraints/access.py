"""TSO access constraint with explicit three-state semantics.

Access is evaluated as CONFIRMED, DENIED or UNKNOWN. UNKNOWN (no company
access list supplied) must never be interpreted as granted: it fails closed
for any route that actually requires TSO access.

三态语义是本模块的契约核心：任何调用方都不得把 UNKNOWN 当作放行，
路由优化与报告链路统一在此处裁决，避免各端自行猜测。
"""

from __future__ import annotations

from collections.abc import Sequence

from eurogas_nexus.domain.ontology.vocabulary import AccessStatus


def tso_access_status(
    required_tso_access: Sequence[str],
    company_accessible_tsos: Sequence[str] | None,
) -> AccessStatus:
    """Evaluate TSO access for a route requiring ``required_tso_access``.

    评估一条需要 TSO 访问权的路由的访问状态（三态，fail-closed）。

    Args:
        required_tso_access: TSO codes the route must be able to reach;
            empty means no access is required.
        company_accessible_tsos: Company access list, or None when no list
            was supplied (access state unknown).

    Returns:
        ``CONFIRMED`` when nothing is required or every required TSO is
        present in the supplied access list; ``DENIED`` when a list was
        supplied and at least one required TSO is missing from it;
        ``UNKNOWN`` when no list was supplied while access is required.
        Callers must treat UNKNOWN as a blocker, never as unrestricted.
    """

    required = [item.strip() for item in required_tso_access if item.strip()]
    if not required:
        # 无访问要求：无条件放行，不涉及任何裁决。
        return AccessStatus.CONFIRMED
    if company_accessible_tsos is None:
        # 需要访问权但未提供清单：状态未知，禁止当作已授权。
        return AccessStatus.UNKNOWN
    # 比对时统一小写并去除首尾空白，容忍各来源的大小写差异。
    allowed = {item.strip().lower() for item in company_accessible_tsos if item.strip()}
    if all(item.lower() in allowed for item in required):
        return AccessStatus.CONFIRMED
    return AccessStatus.DENIED


def inaccessible_tsos(
    required_tso_access: Sequence[str],
    company_accessible_tsos: Sequence[str] | None,
) -> list[str]:
    """Return required TSOs that are NOT confirmed accessible (fail-closed).

    返回未获确认可访问的必需 TSO 清单（fail-closed 语义）。

    Args:
        required_tso_access: TSO codes the route must be able to reach.
        company_accessible_tsos: Company access list, or None when the
            access state is unknown.

    Returns:
        ``company_accessible_tsos=None`` means the access state is unknown,
        so every required TSO is reported as inaccessible: unknown access
        must not be interpreted as granted. A supplied list (even empty)
        fails closed for any required TSO not present in it.
    """

    if company_accessible_tsos is None:
        # 无清单 = 全部视为不可达（未知即拒绝）。
        return [item.strip() for item in required_tso_access if item.strip()]
    allowed = {item.strip().lower() for item in company_accessible_tsos if item.strip()}
    return [
        item.strip()
        for item in required_tso_access
        if item.strip() and item.strip().lower() not in allowed
    ]
