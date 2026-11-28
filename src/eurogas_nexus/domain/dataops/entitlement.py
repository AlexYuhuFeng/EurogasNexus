"""Data-operations entitlement propagation policy.

This module owns fail-closed row/result filtering for the current principal
model. It does not build identity lifecycle; it consumes
``AuthenticatedPrincipal.data_scopes`` and source families.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from eurogas_nexus.domain.dataops.contracts import (
    DerivedAccessDecision,
    EntitlementOutcome,
)
from eurogas_nexus.governance.usage import note_licensed_read
from eurogas_nexus.security.identity import (
    PUBLIC_BASELINE_SOURCE_FAMILIES,
    AuthenticatedPrincipal,
    source_family_for_entitlement,
)

COMMERCIAL_SOURCE_FAMILIES = frozenset(
    {
        "EEX",
        "ICE_OCM",
        "Trayport",
        "ICIS",
        "Argus",
        "Kpler",
        "Platts",
        # Licensed FX benchmark fixes (WM/Reuters via LSEG, Bloomberg BFIX).
        "WMR",
        "BFIX",
    }
)


def principal_allows_source(principal: AuthenticatedPrincipal, source_system: str) -> bool:
    """Fail-closed source-family access for one source label.

    The one rule of ``security.identity.principal_allows_source_family`` (public baseline,
    families fetched under a publisher's consent, then the principal's grants).
    """

    from eurogas_nexus.security.identity import principal_allows_source_family

    return principal_allows_source_family(principal, source_system)


def _note_licensed(source_system: object) -> None:
    """Note a licensed family the compatibility principal reads without a check."""

    if isinstance(source_system, str):
        family = source_family_for_entitlement(source_system)
        if family and family not in PUBLIC_BASELINE_SOURCE_FAMILIES:
            note_licensed_read(family)


def allowed_source_families(principal: AuthenticatedPrincipal) -> set[str]:
    """Return the effective allowed families for a principal."""

    scopes = {str(scope).strip().upper() for scope in principal.data_scopes}
    if "*" in scopes:
        return set(COMMERCIAL_SOURCE_FAMILIES) | set(PUBLIC_BASELINE_SOURCE_FAMILIES)
    return {
        family
        for family in {*COMMERCIAL_SOURCE_FAMILIES, *PUBLIC_BASELINE_SOURCE_FAMILIES}
        if family in PUBLIC_BASELINE_SOURCE_FAMILIES
        or family.upper() in scopes
        or family.casefold() in {scope.casefold() for scope in principal.data_scopes}
    }


def filter_rows_for_principal(
    principal: AuthenticatedPrincipal,
    rows: Iterable[dict[str, Any]],
    *,
    source_key: str = "source_system",
    source_meta_key: str | None = None,
) -> list[dict[str, Any]]:
    """Filter rows by principal data scope.

    Legacy public-token service principals retain the single-trust-domain view
    (compatibility). DB-backed and OIDC principals see only allowed families.
    Counts must be computed by callers after this filter.
    """

    if principal.auth_method == "legacy_public_token":
        from eurogas_nexus.security.identity import consented_row_allowed

        rows = [row for row in rows if consented_row_allowed(principal, row.get(source_key))]
        for row in rows:
            _note_licensed(row.get(source_key))
        return rows
    filtered: list[dict[str, Any]] = []
    for row in rows:
        value = row.get(source_key)
        if source_meta_key and not value:
            metadata = row.get(source_meta_key)
            if isinstance(metadata, dict):
                value = metadata.get(source_key)
        if not isinstance(value, str) or principal_allows_source(principal, value):
            filtered.append(row)
    return filtered


def derived_result_access(
    principal: AuthenticatedPrincipal,
    source_systems: Iterable[str],
) -> DerivedAccessDecision:
    """Decide whether a derived result may be exposed to a principal.

    Default is fail closed: every contributing source family must be allowed.
    CR-09 defines no aggregated transformation policy that permits broader
    access, so any blocked restricted source denies the derived result.
    """

    if principal.auth_method == "legacy_public_token":
        from eurogas_nexus.security.identity import consented_row_allowed

        source_systems = list(source_systems)
        refused = tuple(dict.fromkeys(str(s) for s in source_systems
                                      if not consented_row_allowed(principal, str(s))))
        if refused:
            return DerivedAccessDecision(
                outcome=EntitlementOutcome.DENIED, blocked_sources=refused,
                reason="derived_result_contains_restricted_source")
        for source_system in source_systems:
            _note_licensed(source_system)
        return DerivedAccessDecision(outcome=EntitlementOutcome.ALLOWED)
    blocked: list[str] = []
    for source_system in dict.fromkeys(str(value) for value in source_systems):
        if not source_system:
            continue
        if principal_allows_source(principal, source_system):
            continue
        blocked.append(source_system)
    if not blocked:
        return DerivedAccessDecision(outcome=EntitlementOutcome.ALLOWED)
    return DerivedAccessDecision(
        outcome=EntitlementOutcome.DENIED,
        blocked_sources=tuple(blocked),
        reason="derived_result_contains_restricted_source",
    )


def safe_source_detail(principal: AuthenticatedPrincipal, source_system: str | None) -> str | None:
    """Return a source label only when the principal may see it (no leaks)."""

    if source_system is None:
        return None
    if principal_allows_source(principal, str(source_system)):
        return str(source_system)
    return None
