"""Generalized cost-observation domain contract.

The domain model intentionally has no SQLAlchemy or web-framework imports.
The repository/API layers map database rows to this contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

ScopeType = str
ObservationType = str

SCOPE_TYPES = frozenset({"ROUTE", "POINT", "LNG_TERMINAL", "RESOURCE"})

OBSERVATION_TYPES = frozenset(
    {
        "TSO_PUBLISHED",
        "LONG_TERM_CONTRACT",
        "SECONDARY_TRANSFER",
        "AUCTION_BID",
        "LNG_SLOT_BOOKING",
        "MANUAL_OVERRIDE",
    }
)


@dataclass(frozen=True, slots=True)
class CostObservation:
    """One source-attributed, time-windowed cost value."""

    observation_id: str
    scope_type: str
    scope_id: str
    observation_type: str
    value: float
    currency: str
    unit: str
    direction: str | None = None
    capacity_product: str | None = None
    firmness: str | None = None
    gas_year: str | None = None
    effective_from_utc: str = ""
    effective_to_utc: str | None = None
    source_system: str = ""
    source_reference: str = ""
    document_id: str | None = None
    entitlement_scope: tuple[str, ...] = ()
    status: str = "ACTIVE"
    manual_review_required: bool = True
    superseded_by: str | None = None
    created_at_utc: str = ""


def validate_cost_observation(observation: CostObservation) -> None:
    """Validate the domain invariants before persistence or query use."""

    if observation.scope_type not in SCOPE_TYPES:
        raise ValueError(
            f"scope_type must be one of {sorted(SCOPE_TYPES)}; "
            f"got {observation.scope_type!r}"
        )
    if observation.observation_type not in OBSERVATION_TYPES:
        raise ValueError(
            f"observation_type must be one of {sorted(OBSERVATION_TYPES)}; "
            f"got {observation.observation_type!r}"
        )
    if not observation.scope_id.strip():
        raise ValueError("scope_id is required")
    if observation.value < 0:
        raise ValueError("cost observation value must be non-negative")
    if not observation.currency.strip() or not observation.unit.strip():
        raise ValueError("currency and unit are required")


def utc_now_iso() -> str:
    """Return a UTC ISO timestamp for domain/DB compatibility."""

    return datetime.now(UTC).isoformat()
