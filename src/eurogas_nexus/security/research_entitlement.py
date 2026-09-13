"""Shared research source authorization and snapshot provenance policy."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from eurogas_nexus.domain.dataops.registry import (
    SourceDefinition,
    definition_for_source,
    source_definitions,
)
from eurogas_nexus.governance.entitlement import (
    EntitlementScope,
    ExportDecision,
    entitlement_scope_for_source,
    export_check,
)
from eurogas_nexus.security.identity import (
    AuthenticatedPrincipal,
    principal_allows_source_family,
    source_family_for_entitlement,
)


def authorized_source_definitions(
    principal: AuthenticatedPrincipal,
    source_restrictions: Sequence[str] = (),
) -> tuple[SourceDefinition, ...]:
    """Return exact registered runtime sources allowed by the principal.

    Restrictions select concrete registry provider labels such as ``EEX_Sim``.
    The family mapping is deliberately used only for the principal entitlement
    check; it does not rewrite a simulation source into its live provider.
    """

    restrictions = {str(value).strip().casefold() for value in source_restrictions}
    return tuple(
        definition
        for definition in source_definitions()
        if principal_allows_source_family(principal, definition.provider)
        and (
            not restrictions
            or definition.provider.casefold() in restrictions
        )
    )


def definition_for_runtime_source(source_system: str) -> SourceDefinition | None:
    """Resolve a runtime label only through the canonical concrete registry."""

    needle = str(source_system).strip().casefold()
    return next(
        (
            definition
            for definition in source_definitions()
            if definition.provider.casefold() == needle
        ),
        None,
    )


def effective_entitlement_envelope(
    definitions: Sequence[SourceDefinition],
) -> dict[str, str]:
    """Derive export policy from canonical governance, never request metadata."""

    evaluations = []
    unknown_scope = False
    for definition in definitions:
        try:
            scope = EntitlementScope(
                entitlement_scope_for_source(
                    source_family_for_entitlement(definition.provider)
                )
            )
        except ValueError:
            scope = EntitlementScope.UNKNOWN
            unknown_scope = True
        evaluations.append(
            export_check(
                scope,
                allow_public_export=definition.licensed_data.export_allowed,
            )
        )
    if not evaluations or unknown_scope:
        policy = "UNKNOWN"
    elif all(item.decision is ExportDecision.ALLOWED for item in evaluations):
        policy = "EXPORT_ALLOWED"
    else:
        policy = "EXPORT_RESTRICTED"
    return {"export_policy": policy, "policy_source": "dataops"}


def row_export_policy(definition: SourceDefinition) -> str:
    """Return the export policy derived from one canonical source definition."""

    try:
        scope = EntitlementScope(
            entitlement_scope_for_source(source_family_for_entitlement(definition.provider))
        )
    except ValueError:
        return "UNKNOWN"
    evaluation = export_check(
        scope,
        allow_public_export=definition.licensed_data.export_allowed,
    )
    if evaluation.decision is ExportDecision.ALLOWED:
        return "EXPORT_ALLOWED"
    if evaluation.decision is ExportDecision.UNKNOWN:
        return "UNKNOWN"
    return "EXPORT_RESTRICTED"


def trusted_source_definitions(
    metadata: Mapping[str, Any] | None,
) -> tuple[SourceDefinition, ...] | None:
    """Resolve trusted source IDs; absent or unknown provenance fails closed."""

    if not isinstance(metadata, Mapping):
        return None
    source_ids = (metadata or {}).get("trusted_source_ids")
    if not isinstance(source_ids, list) or not source_ids:
        return None
    definitions: list[SourceDefinition] = []
    for source_id in source_ids:
        if not isinstance(source_id, str):
            return None
        definition = definition_for_source(source_id)
        if definition is None:
            return None
        definitions.append(definition)
    return tuple(definitions)


def principal_can_read_snapshot(
    principal: AuthenticatedPrincipal,
    metadata: Mapping[str, Any] | None,
) -> tuple[SourceDefinition, ...] | None:
    """Authorize a snapshot from its persisted canonical source provenance."""

    definitions = trusted_source_definitions(metadata)
    if definitions is None:
        return None
    if not all(
        principal_allows_source_family(principal, definition.provider)
        for definition in definitions
    ):
        return None
    return definitions
