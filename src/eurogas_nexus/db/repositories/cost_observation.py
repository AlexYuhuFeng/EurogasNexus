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


def cost_observation_freshness(
    session: Session,
    *,
    scope_type: str,
    scope_id: str,
    now_utc: datetime,
    expectation_minutes: int = 1440,
) -> dict:
    """Return freshness metadata for one cost-observation scope.

    The result is deliberately read-only and source-honest. A scope with no
    observations is ``unavailable`` rather than fabricated.
    """

    rows = list_cost_observations(
        session,
        scope_type=scope_type,
        scope_id=scope_id,
    )
    if not rows:
        return {
            "scope_type": scope_type,
            "scope_id": scope_id,
            "status": "unavailable",
            "latest_created_at_utc": None,
            "age_minutes": None,
            "expectation_minutes": expectation_minutes,
        }
    latest = max(row.created_at_utc for row in rows)
    latest = _as_utc(latest)
    age_minutes = max(0.0, (now_utc - latest).total_seconds() / 60.0)
    status = "live" if age_minutes <= expectation_minutes else "stale"
    return {
        "scope_type": scope_type,
        "scope_id": scope_id,
        "status": status,
        "latest_created_at_utc": latest.isoformat(),
        "age_minutes": round(age_minutes, 2),
        "expectation_minutes": expectation_minutes,
    }


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
