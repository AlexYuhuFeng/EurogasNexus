"""Repository for generalized cost-observation rows."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.orm import Session

from eurogas_nexus.db.models.cost_observation import CostObservationRecord
from eurogas_nexus.domain.economics.cost_observation import (
    CostObservation,
    validate_cost_observation,
)


def list_cost_observations(
    session: Session,
    *,
    scope_type: str | None = None,
    scope_id: str | None = None,
    status: str = "ACTIVE",
) -> list[CostObservationRecord]:
    """Return active observations for a scope ordered by effective window."""

    query = session.query(CostObservationRecord).filter(
        CostObservationRecord.status == status
    )
    if scope_type:
        query = query.filter(CostObservationRecord.scope_type == scope_type)
    if scope_id:
        query = query.filter(CostObservationRecord.scope_id == scope_id)
    return list(
        query.order_by(
            CostObservationRecord.effective_from_utc,
            CostObservationRecord.created_at_utc,
        ).all()
    )


def upsert_cost_observation(
    session: Session,
    observation: CostObservation,
    *,
    now_utc: datetime | None = None,
) -> CostObservationRecord:
    """Insert or supersede a cost observation.

    New observations are appended with a generated id. Existing rows with the
    same source identity are superseded after repository insertion in a later
    resolver step; this primitive intentionally does not rewrite history.
    """

    validate_cost_observation(observation)
    now = _as_utc(now_utc or datetime.now(UTC))
    row = CostObservationRecord(
        observation_id=observation.observation_id or f"cost-{uuid4().hex[:12]}",
        scope_type=observation.scope_type,
        scope_id=observation.scope_id,
        observation_type=observation.observation_type,
        value=observation.value,
        currency=observation.currency,
        unit=observation.unit,
        direction=observation.direction,
        capacity_product=observation.capacity_product,
        firmness=observation.firmness,
        gas_year=observation.gas_year,
        effective_from_utc=datetime.fromisoformat(observation.effective_from_utc)
        if observation.effective_from_utc
        else now,
        effective_to_utc=(
            datetime.fromisoformat(observation.effective_to_utc)
            if observation.effective_to_utc
            else None
        ),
        source_system=observation.source_system,
        source_reference=observation.source_reference,
        document_id=observation.document_id,
        entitlement_scope=list(observation.entitlement_scope),
        status=observation.status,
        manual_review_required=observation.manual_review_required,
        superseded_by=observation.superseded_by,
        created_at_utc=now,
    )
    session.add(row)
    session.flush()
    return row


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
