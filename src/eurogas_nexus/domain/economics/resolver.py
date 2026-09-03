"""Entitlement-priority resolver for generalized cost observations.

The resolver is pure domain logic: it receives a sequence of
:class:`CostObservation` objects and returns the most applicable value plus
the remaining alternatives. This keeps the pricing decision testable without
a database session.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from eurogas_nexus.domain.economics.cost_observation import CostObservation

# Operator-specific values outrank published tariffs. MANUAL_OVERRIDE is
# highest because it records an explicitly reviewed commercial decision.
_OBSERVATION_PRIORITY = {
    "MANUAL_OVERRIDE": 100,
    "AUCTION_BID": 90,
    "SECONDARY_TRANSFER": 85,
    "LONG_TERM_CONTRACT": 80,
    "LNG_SLOT_BOOKING": 75,
    "TSO_PUBLISHED": 10,
}

_PUBLIC_SCOPE = "*"


@dataclass(frozen=True, slots=True)
class CostResolution:
    """Result of resolving one scoped cost at a point in time.

    Attributes:
        scope_type: Resolved scope type.
        scope_id: Resolved scope id.
        as_of_utc: Evaluation timestamp.
        selected: Highest-priority applicable observation.
        alternatives: Other applicable observations in descending priority.
        fallback_used: True when no operator-specific value applied.
        entitlement_scopes: Entitlement scopes used for resolution.
    """

    scope_type: str
    scope_id: str
    as_of_utc: str
    selected: CostObservation | None
    alternatives: tuple[CostObservation, ...] = ()
    fallback_used: bool = False
    entitlement_scopes: tuple[str, ...] = ()


def resolve_cost_observations(
    observations: list[CostObservation] | tuple[CostObservation, ...],
    *,
    scope_type: str,
    scope_id: str,
    as_of_utc: datetime | str,
    entitled_scopes: list[str] | tuple[str, ...] | set[str] | None = None,
) -> CostResolution:
    """Resolve the applicable cost value for a scoped object.

    Only observations whose scope matches and whose effective window contains
    ``as_of_utc`` are considered. Entitlement filtering is fail-closed:
    observations with an explicit entitlement scope are considered only when
    one of ``entitled_scopes`` matches, while public observations always
    remain available as fallbacks.

    Args:
        observations: Candidate observations.
        scope_type: Expected ``scope_type``.
        scope_id: Expected ``scope_id``.
        as_of_utc: Evaluation timestamp.
        entitled_scopes: Entitlement scopes available to the caller.

    Returns:
        CostResolution with selected and alternatives.
    """

    normalized_scopes = _normalize_entitled_scopes(entitled_scopes)
    as_of = _as_utc(as_of_utc)

    applicable: list[tuple[int, float, CostObservation]] = []
    for observation in observations:
        if observation.scope_type != scope_type or observation.scope_id != scope_id:
            continue
        if observation.status not in {"ACTIVE", "SUPERSEDED"}:
            continue
        if not _effective_at(observation, as_of):
            continue
        if not _entitlement_matches(observation, normalized_scopes):
            continue
        priority = _OBSERVATION_PRIORITY.get(observation.observation_type, 0)
        effective_ts = _as_utc(observation.effective_from_utc).timestamp()
        applicable.append((priority, effective_ts, observation))

    applicable.sort(key=lambda row: (row[0], row[1]), reverse=True)

    if not applicable:
        return CostResolution(
            scope_type=scope_type,
            scope_id=scope_id,
            as_of_utc=as_of.isoformat(),
            selected=None,
            fallback_used=True,
            entitlement_scopes=normalized_scopes,
        )

    selected = applicable[0][2]
    alternatives = tuple(row[2] for row in applicable[1:])
    fallback_used = selected.observation_type == "TSO_PUBLISHED"
    return CostResolution(
        scope_type=scope_type,
        scope_id=scope_id,
        as_of_utc=as_of.isoformat(),
        selected=selected,
        alternatives=alternatives,
        fallback_used=fallback_used,
        entitlement_scopes=normalized_scopes,
    )


def _normalize_entitled_scopes(
    entitled_scopes: list[str] | tuple[str, ...] | set[str] | None,
) -> tuple[str, ...]:
    if entitled_scopes is None:
        return ()
    return tuple(sorted({str(value).strip() for value in entitled_scopes if str(value).strip()}))


def _entitlement_matches(
    observation: CostObservation,
    entitled_scopes: tuple[str, ...],
) -> bool:
    scopes = {str(value).strip() for value in observation.entitlement_scope}
    if not scopes or _PUBLIC_SCOPE in scopes:
        return True
    if not entitled_scopes:
        return False
    return _PUBLIC_SCOPE in entitled_scopes or bool(scopes & set(entitled_scopes))


def _effective_at(observation: CostObservation, as_of: datetime) -> bool:
    effective_from = _as_utc(observation.effective_from_utc)
    if effective_from > as_of:
        return False
    if observation.effective_to_utc:
        effective_to = _as_utc(observation.effective_to_utc)
        if effective_to < as_of:
            return False
    return True


def _as_utc(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
