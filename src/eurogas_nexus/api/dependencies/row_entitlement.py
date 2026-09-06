"""Shared row-level entitlement helpers for public read routes.

This is the authoritative backend filter. Frontend visibility remains UX-only;
every governed read surface must call one of these helpers before building
counts, aggregates, metadata or exports.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from fastapi import HTTPException, Request

from eurogas_nexus.domain.dataops.entitlement import (
    derived_result_access,
    filter_rows_for_principal,
)
from eurogas_nexus.security.identity import legacy_public_token_principal


def current_principal(request: Request):
    """Return the authenticated principal attached by the API dependency."""

    return getattr(request.state, "identity", legacy_public_token_principal())


def filter_rows(
    request: Request,
    rows: Iterable[dict[str, Any]],
    *,
    source_key: str = "source_system",
):
    """Filter direct rows by the authenticated principal's data scopes."""

    return filter_rows_for_principal(current_principal(request), rows, source_key=source_key)


def require_derived_access(
    request: Request,
    source_systems: Iterable[str],
    *,
    resource: str,
) -> None:
    """Fail closed when a derived result contains a restricted source.

    The caller must supply only a generic resource label; source names are
    never echoed back to an unentitled principal.
    """

    decision = derived_result_access(current_principal(request), source_systems)
    if decision.outcome.value == "ALLOWED":
        return
    raise HTTPException(
        status_code=403,
        detail={
            "error": "entitlement_denied",
            "reason": "Derived result contains restricted source data (fail-closed).",
            "resource": resource,
            "research_only": True,
            "human_review_required": True,
        },
    )
