"""TSO access fail-closed constraint."""

from __future__ import annotations

from collections.abc import Sequence


def inaccessible_tsos(
    required_tso_access: Sequence[str],
    company_accessible_tsos: Sequence[str] | None,
) -> list[str]:
    """Return required TSOs the company cannot access (fail-closed semantics).

    ``company_accessible_tsos=None`` means the caller did not supply an access
    list, so no additional restriction is imposed. A supplied list (even empty)
    fails closed for any required TSO not present in it.
    """

    if company_accessible_tsos is None:
        return []
    allowed = {item.strip().lower() for item in company_accessible_tsos if item.strip()}
    return [
        tso
        for tso in required_tso_access
        if tso.strip() and tso.strip().lower() not in allowed
    ]
