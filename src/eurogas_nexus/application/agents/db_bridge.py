"""Read-only DB bridges for capability handlers (never exposed as SQL)."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Any

from eurogas_nexus.db.session import resolve_database_url
from eurogas_nexus.security.identity import (
    AuthenticatedPrincipal,
    principal_allows_source_family,
)


def db_configured() -> bool:
    return resolve_database_url() is not None


@contextmanager
def session_scope():
    if not db_configured():
        yield None
        return
    from eurogas_nexus.db.session import get_session_factory

    with get_session_factory()() as session:
        yield session


def principal_from_context(context) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id=context.principal_id,
        name=context.principal_id,
        principal_type="USER",
        role=context.role,
        status="ACTIVE",
        data_scopes=tuple(context.data_scopes),
        roles=tuple(context.roles or [context.role]),
    )


def entitled(context, source_system: str) -> bool:
    return principal_allows_source_family(principal_from_context(context), source_system)


def market_rows(
    session,
    *,
    start_utc: datetime | None = None,
    end_utc: datetime | None = None,
    hub: str | None = None,
    product: str | None = None,
    limit: int = 500,
) -> list[dict[str, Any]]:
    from eurogas_nexus.db.models import MarketObservationRecord

    query = session.query(MarketObservationRecord)
    if start_utc is not None:
        query = query.filter(MarketObservationRecord.observed_at_utc >= start_utc)
    if end_utc is not None:
        query = query.filter(MarketObservationRecord.observed_at_utc < end_utc)
    query = query.order_by(MarketObservationRecord.observed_at_utc.desc()).limit(
        max(1, min(limit, 2000))
    )
    hub_key = (hub or "").strip().upper()
    product_key = (product or "").strip().upper().replace("-", "_").replace(" ", "_")
    rows = []
    for row in query.all():
        metadata = row.metadata_json or {}
        row_hub = str(metadata.get("hub") or row.market_venue).upper()
        row_product = (
            str(metadata.get("tenor") or row.product).upper().replace("-", "_").replace(" ", "_")
        )
        if hub_key and row_hub != hub_key:
            continue
        if product_key and product_key not in row_product:
            continue
        rows.append(
            {
                "observation_id": row.observation_id,
                "hub": row_hub,
                "product": row_product,
                "value": row.price,
                "unit": row.unit,
                "currency": row.currency,
                "observed_at": row.observed_at_utc.isoformat(),
                "source_system": row.source_system,
                "source_reference": row.source_reference,
                "freshness": row.freshness,
                "quality_score": row.quality_score,
            }
        )
        if len(rows) >= limit:
            break
    return rows


def latest_market_snapshot(
    session, *, hub: str | None = None, product: str | None = None
) -> dict[str, Any]:
    rows = market_rows(session, hub=hub, product=product, limit=100)
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        key = (row["hub"], row["product"])
        latest.setdefault(key, row)
    return {"rows": list(latest.values()), "count": len(latest)}


def flow_rows(session, *, point_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    from eurogas_nexus.db.models import FlowObservationRecord

    query = session.query(FlowObservationRecord)
    if point_id:
        query = query.filter(FlowObservationRecord.point_id == point_id)
    query = query.order_by(FlowObservationRecord.observed_at_utc.desc()).limit(
        max(1, min(limit, 500))
    )
    return [
        {
            "observation_id": row.observation_id,
            "point_id": row.point_id,
            "point_name": row.point_name,
            "direction": row.direction,
            "kind": row.kind,
            "flow_mcm_d": row.flow_mcm_d,
            "period_start": row.period_start_utc.isoformat(),
            "period_end": row.period_end_utc.isoformat(),
            "observed_at": row.observed_at_utc.isoformat(),
            "source_system": row.source_system,
            "source_reference": row.source_reference,
        }
        for row in query.all()
    ]


def capacity_rows(
    session, *, point_id: str | None = None, limit: int = 200
) -> list[dict[str, Any]]:
    from eurogas_nexus.db.models import CapacityObservationRecord

    query = session.query(CapacityObservationRecord)
    if point_id:
        query = query.filter(CapacityObservationRecord.point_id == point_id)
    query = query.order_by(CapacityObservationRecord.observed_at_utc.desc()).limit(
        max(1, min(limit, 500))
    )
    return [
        {
            "observation_id": row.observation_id,
            "point_id": row.point_id,
            "point_name": row.point_name,
            "direction": row.direction,
            "capacity_type": row.capacity_type,
            "capacity_mcm_d": row.capacity_mcm_d,
            "period_start": row.period_start_utc.isoformat(),
            "period_end": row.period_end_utc.isoformat(),
            "observed_at": row.observed_at_utc.isoformat(),
            "source_system": row.source_system,
            "source_reference": row.source_reference,
        }
        for row in query.all()
    ]


def resource_rows(session, *, resource_id: str | None = None) -> list[dict[str, Any]]:
    from eurogas_nexus.db.repositories.route_cost import list_upstream_contracts

    rows = list_upstream_contracts(session)
    if resource_id:
        rows = [row for row in rows if row.get("contract_id") == resource_id]
    return rows


def route_candidate_rows(session) -> list[dict[str, Any]]:
    from eurogas_nexus.db.repositories.route_cost import list_route_candidates

    return list_route_candidates(session)
