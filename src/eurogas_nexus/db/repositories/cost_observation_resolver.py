"""Repository-level cost-observation resolver adapter."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from eurogas_nexus.db.repositories.cost_observation import list_cost_observations
from eurogas_nexus.domain.economics.cost_observation import CostObservation
from eurogas_nexus.domain.economics.resolver import (
    CostResolution,
    resolve_cost_observations,
)


def resolve_cost_observation(
    session: Session,
    *,
    scope_type: str,
    scope_id: str,
    as_of_utc: datetime,
    entitled_scopes: list[str] | tuple[str, ...] | set[str] | None = None,
) -> CostResolution:
    """Load candidate rows and apply entitlement-priority resolution."""

    rows = list_cost_observations(
        session,
        scope_type=scope_type,
        scope_id=scope_id,
    )
    observations = [_to_domain(row) for row in rows]
    return resolve_cost_observations(
        observations,
        scope_type=scope_type,
        scope_id=scope_id,
        as_of_utc=as_of_utc,
        entitled_scopes=entitled_scopes,
    )


def _to_domain(row) -> CostObservation:
    return CostObservation(
        observation_id=row.observation_id,
        scope_type=row.scope_type,
        scope_id=row.scope_id,
        observation_type=row.observation_type,
        value=row.value,
        currency=row.currency,
        unit=row.unit,
        direction=row.direction,
        capacity_product=row.capacity_product,
        firmness=row.firmness,
        gas_year=row.gas_year,
        effective_from_utc=row.effective_from_utc.isoformat(),
        effective_to_utc=row.effective_to_utc.isoformat() if row.effective_to_utc else None,
        source_system=row.source_system,
        source_reference=row.source_reference,
        document_id=row.document_id,
        entitlement_scope=tuple(row.entitlement_scope or []),
        status=row.status,
        manual_review_required=row.manual_review_required,
        superseded_by=row.superseded_by,
        created_at_utc=row.created_at_utc.isoformat(),
    )
