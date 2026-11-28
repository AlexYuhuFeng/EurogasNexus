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


KNOWN_ENTITLED_SYSTEMS_V1 = frozenset(
    {
        "operator-input",
        "ENTSOG",
        "GIE",
        "ECB",
        "EEX",
        "Trayport",
        "ICE_OCM",
        "Weather",
        "WMR",
        "BFIX",
        "BOE",
        "NYFED",
    }
)


def _consented() -> frozenset[str]:
    """Families fetched under a publisher's written consent: the firm's own use only."""

    from eurogas_nexus.domain.publications.consents import consented_source_families

    return consented_source_families()


def entitlement_scope_for_source(source_system: str) -> str:
    """Classify a source system's entitlement scope for row-level annotation.

    Simulated sources are evaluated by their licensed family (``EEX_Sim`` ->
    ``EEX``) so the annotation follows the same boundary as their commercial
    counterpart; unknown families annotate as UNKNOWN (fail-closed display).
    """

    value = (source_system or "").strip()
    if not value:
        return EntitlementScope.UNKNOWN.value
    family = value.removesuffix("_Sim") if value.endswith("_Sim") else value
    if family in KNOWN_ENTITLED_SYSTEMS_V1 or family in _consented():
        return EntitlementScope.INTERNAL_RESEARCH.value
    return EntitlementScope.UNKNOWN.value


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


#: Restrictions written on a file that carries licensed data the licence does not let
#: leave the firm.
FILE_RESTRICTIONS = ("internal-use-only", "no-redistribution")

_EXPORT_RANK = {
    ExportDecision.ALLOWED: 0,
    ExportDecision.RESTRICTED: 1,
    ExportDecision.UNKNOWN: 2,
    ExportDecision.DENIED: 3,
}


@dataclass(frozen=True)
class FileExportDecision:
    """The export decision for one file (CSV, XLSX, PDF) and the families behind it."""

    decision: ExportDecision
    licensed_families: tuple[str, ...] = ()
    restrictions: tuple[str, ...] = ()
    reason: str = ""


def file_export_decision(
    licensed_families: set[str] | frozenset[str] | tuple[str, ...],
    *,
    redistributable: set[str] | frozenset[str] = frozenset(),
    registered: set[str] | frozenset[str] = frozenset(),
) -> FileExportDecision:
    """Apply :func:`export_check` to each licensed family a file's rows were read from.

    GOV-1 (P6). A file with no licensed data is allowed. A family whose current licence
    lets derived figures leave the firm (``market_data_licences.redistribution_allowed``)
    is exported as public data with clearance. Any other family the governance register
    knows, or the firm holds a current licence for (``registered``), restricts the file to
    internal use; a family known to neither denies it (fail closed). The file's decision is
    the strictest of its families'. A family fetched under a publisher's written consent
    (``domain/publications/consents``) always restricts the file to internal use.
    """

    families = tuple(sorted({f for f in licensed_families if f}))
    if not families:
        return FileExportDecision(ExportDecision.ALLOWED, reason="No licensed data.")
    worst = ExportDecision.ALLOWED
    reasons = []
    consented = _consented()
    for family in families:
        if family in consented:
            # Fetched under a publisher's written consent: the firm's own use, no resale or
            # redistribution, whatever a licence record says. Internal use only.
            evaluation = export_check(EntitlementScope.INTERNAL_RESEARCH)
        elif family in redistributable:
            evaluation = export_check(EntitlementScope.PUBLIC, allow_public_export=True)
        elif family in registered:
            evaluation = export_check(EntitlementScope.INTERNAL_RESEARCH)
        else:
            evaluation = export_check(EntitlementScope(entitlement_scope_for_source(family)))
        if _EXPORT_RANK[evaluation.decision] > _EXPORT_RANK[worst]:
            worst = evaluation.decision
        if evaluation.decision is not ExportDecision.ALLOWED:
            reasons.append(f"{family}: {evaluation.decision.value}")
    if worst is ExportDecision.UNKNOWN:
        worst = ExportDecision.DENIED
    return FileExportDecision(
        decision=worst,
        licensed_families=families,
        restrictions=FILE_RESTRICTIONS if worst is ExportDecision.RESTRICTED else (),
        reason="; ".join(reasons) or "Every licence allows redistribution.",
    )
