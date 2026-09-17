"""Commercial-data access dependency (Architecture V2 platform-admin boundary).

``06_IDENTITY_ACCESS_CONTROL_PLANE.md`` section 7 makes the boundary explicit:

    Platform Admin can manage SSO, users/groups, runtime, provider secret
    metadata and system settings **without automatically seeing** contract
    prices, strategy parameters, commercial PnL or restricted datasets.

The route-permission registry gates by *role rank*, and ADMIN has the highest
rank, so rank alone cannot express "administration is not commercial access".
This dependency adds the missing check: a path that serves commercial data
requires a **commercial capability**, which is derived from the role and
permission model rather than from rank.

Composition note: this never widens access. It only refuses commercial data to
an identity whose roles grant platform administration and no commercial work.
An administrator who also analyses holds a commercial role alongside ADMIN
(overlapping functional assignments), which is the intended V2 model.
"""

from __future__ import annotations

from fastapi import HTTPException, Request

from eurogas_nexus.security.capabilities import commercial_capabilities_for_principal
from eurogas_nexus.security.identity import legacy_public_token_principal
from eurogas_nexus.security.permissions import serves_commercial_data

COMMERCIAL_ACCESS_DENIED = "commercial_access_not_granted"


async def require_commercial_access(request: Request) -> None:
    """Refuse commercial data to an identity without a commercial capability.

    Raises:
        HTTPException: 403 ``commercial_access_not_granted`` when the request
            path serves commercial data and the authenticated identity holds no
            commercial capability.
    """

    if not serves_commercial_data(request.url.path):
        return

    identity = getattr(request.state, "identity", None) or legacy_public_token_principal()
    if commercial_capabilities_for_principal(identity):
        return

    raise HTTPException(
        status_code=403,
        detail={
            "error": COMMERCIAL_ACCESS_DENIED,
            "message": (
                "This path serves commercial data, which platform administration "
                "does not grant. Grant a commercial role (for example ANALYST) "
                "alongside the administration role, or request a data entitlement."
            ),
            "capabilities_required": ["market.read", "portfolio.read"],
        },
    )
