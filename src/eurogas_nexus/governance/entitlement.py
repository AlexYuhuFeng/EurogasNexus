"""Entitlement and export decision shells — fail-closed by default."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum


class EntitlementScope(StrEnum):
    """Known entitlement scopes. Unknown scopes fail closed."""

    INTERNAL_RESEARCH = "internal-research"
    PUBLIC = "public"
    LICENSED = "licensed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class EntitlementDecision:
    """Result of an entitlement evaluation against a data source or dataset.

    Defaults to denied — callers must explicitly prove entitlement.
    """

    granted: bool = False
    scope: EntitlementScope = EntitlementScope.UNKNOWN
    reason: str = ""
    source_system: str = ""
    source_dataset: str = ""
    evaluated_at_utc: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    human_review_required: bool = True


class ExportDecision(StrEnum):
    """Export classification for a dataset or result."""

    ALLOWED = "allowed"
    RESTRICTED = "restricted"
    DENIED = "denied"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ExportEvaluation:
    """Result of an export-policy evaluation. Defaults to denied."""

    decision: ExportDecision = ExportDecision.UNKNOWN
    restrictions: list[str] = field(default_factory=list)
    reason: str = ""
    evaluated_at_utc: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    human_review_required: bool = True


# ---------------------------------------------------------------------------
# Fail-closed check functions
# ---------------------------------------------------------------------------


def entitlement_check(
    source_system: str,
    source_dataset: str = "",
    *,
    known_entitled_systems: frozenset[str] = frozenset(),
) -> EntitlementDecision:
    """Evaluate entitlement for a data source. Fails closed for unknowns.

    If the source system is not in the known-entitled set, the decision is
    denied with scope UNKNOWN. This implements the fail-closed policy
    required by the governance contract.
    """
    if source_system in known_entitled_systems:
        return EntitlementDecision(
            granted=True,
            scope=EntitlementScope.INTERNAL_RESEARCH,
            reason=f"Source system '{source_system}' is in the known-entitled set.",
            source_system=source_system,
            source_dataset=source_dataset,
        )

    return EntitlementDecision(
        granted=False,
        scope=EntitlementScope.UNKNOWN,
        reason=(
            f"Source system '{source_system}' is not in the known-entitled set. "
            f"Entitlement must be explicitly reviewed before data access."
        ),
        source_system=source_system,
        source_dataset=source_dataset,
    )


def export_check(
    dataset_scope: EntitlementScope,
    *,
    allow_public_export: bool = False,
) -> ExportEvaluation:
    """Evaluate whether a dataset may be exported. Fails closed for unknowns.

    Internal-research and unknown-scope data is denied export by default.
    Only public or explicitly licensed datasets with allow_public_export
    may be cleared.
    """
    if dataset_scope == EntitlementScope.PUBLIC and allow_public_export:
        return ExportEvaluation(
            decision=ExportDecision.ALLOWED,
            reason="Public dataset with explicit export clearance.",
        )

    if dataset_scope == EntitlementScope.UNKNOWN:
        return ExportEvaluation(
            decision=ExportDecision.DENIED,
            reason="Unknown entitlement scope — export denied (fail-closed).",
        )

    return ExportEvaluation(
        decision=ExportDecision.RESTRICTED,
        restrictions=["internal-research-only", "no-redistribution"],
        reason=f"Dataset scope '{dataset_scope.value}' restricts export.",
    )
