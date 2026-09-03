"""Read-only /api/cost-observations routes.

These routes expose time-windowed route/point/LNG cost observations and the
entitlement-priority resolver. The backend never invents a value when no
runtime observation is available.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(tags=["cost-observations"])


@router.get("/api/cost-observations/values")
def list_values(
    request: Request,
    scope_type: str | None = Query(None),
    scope_id: str | None = Query(None),
    as_of: str | None = Query(None, description="ISO-8601 timestamp"),
) -> dict:
    """List active cost observations for one scope."""

    from eurogas_nexus.db.repositories.cost_observation import list_cost_observations
    from eurogas_nexus.db.session import get_session_factory

    if not _db_configured():
        return _envelope(
            [],
            request,
            source="runtime-db-not-configured",
            warnings=["COST_OBSERVATIONS_NOT_CONFIGURED"],
        )
    try:
        with get_session_factory()() as session:
            rows = list_cost_observations(
                session,
                scope_type=scope_type,
                scope_id=scope_id,
            )
            values = [_row_dict(row, as_of) for row in rows]
        return _envelope(values, request, source="runtime-postgresql")
    except _sqlalchemy_error_type() as exc:
        raise _db_unavailable(exc) from exc


@router.get("/api/cost-observations/applicable")
def get_applicable(
    request: Request,
    scope_type: str = Query(..., description="ROUTE, POINT, LNG_TERMINAL, or RESOURCE"),
    scope_id: str = Query(..., min_length=1),
    as_of: str = Query(..., description="ISO-8601 evaluation timestamp"),
    entitlement_scope: list[str] | None = None,
) -> dict:
    """Resolve the applicable cost value with entitlement priority."""

    from eurogas_nexus.db.repositories.cost_observation_resolver import (
        resolve_cost_observation,
    )
    from eurogas_nexus.db.session import get_session_factory

    if not _db_configured():
        return _envelope(
            None,
            request,
            source="runtime-db-not-configured",
            warnings=["COST_OBSERVATIONS_NOT_CONFIGURED"],
        )
    try:
        as_of_dt = datetime.fromisoformat(as_of)
        with get_session_factory()() as session:
            resolution = resolve_cost_observation(
                session,
                scope_type=scope_type.upper(),
                scope_id=scope_id,
                as_of_utc=as_of_dt,
                entitled_scopes=entitlement_scope or [],
            )
        return _envelope(
            _resolution_dict(resolution),
            request,
            source="runtime-postgresql",
            warnings=["NO_COST_OBSERVATION"] if resolution.selected is None else [],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except _sqlalchemy_error_type() as exc:
        raise _db_unavailable(exc) from exc


def _db_configured() -> bool:
    from eurogas_nexus.db.session import resolve_database_url

    return resolve_database_url() is not None


def _sqlalchemy_error_type():
    from sqlalchemy.exc import SQLAlchemyError

    return SQLAlchemyError


def _db_unavailable(exc: Exception) -> HTTPException:
    detail = f"Runtime DB unavailable: {exc.__class__.__name__}"
    return HTTPException(status_code=503, detail=detail)


def _envelope(data: object, request: Request, *, source: str, warnings: list[str]) -> dict:
    return {
        "data": data,
        "meta": {
            "request_id": getattr(request.state, "request_id", None),
            "source_references": [source],
            "warnings": warnings,
            "research_only": True,
            "human_review_required": True,
        },
    }


def _row_dict(row, as_of: str | None) -> dict:
    from eurogas_nexus.domain.economics.cost_observation import CostObservation

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
    ).__dict__ if as_of is None else {
        **_row_base_dict(row),
        "as_of": as_of,
    }


def _row_base_dict(row) -> dict:
    return {
        "observation_id": row.observation_id,
        "scope_type": row.scope_type,
        "scope_id": row.scope_id,
        "observation_type": row.observation_type,
        "value": row.value,
        "currency": row.currency,
        "unit": row.unit,
        "effective_from_utc": row.effective_from_utc.isoformat(),
        "effective_to_utc": row.effective_to_utc.isoformat() if row.effective_to_utc else None,
        "source_system": row.source_system,
        "source_reference": row.source_reference,
        "entitlement_scope": row.entitlement_scope,
        "status": row.status,
        "manual_review_required": row.manual_review_required,
    }


def _resolution_dict(resolution) -> dict:
    return {
        "scope_type": resolution.scope_type,
        "scope_id": resolution.scope_id,
        "as_of_utc": resolution.as_of_utc,
        "selected": _obs_dict(resolution.selected),
        "alternatives": [_obs_dict(item) for item in resolution.alternatives],
        "fallback_used": resolution.fallback_used,
        "entitlement_scopes": list(resolution.entitlement_scopes),
    }


def _obs_dict(observation) -> dict | None:
    if observation is None:
        return None
    return {
        "observation_id": observation.observation_id,
        "scope_type": observation.scope_type,
        "scope_id": observation.scope_id,
        "observation_type": observation.observation_type,
        "value": observation.value,
        "currency": observation.currency,
        "unit": observation.unit,
        "effective_from_utc": observation.effective_from_utc,
        "effective_to_utc": observation.effective_to_utc,
        "source_system": observation.source_system,
        "source_reference": observation.source_reference,
        "entitlement_scope": list(observation.entitlement_scope),
        "status": observation.status,
        "manual_review_required": observation.manual_review_required,
    }
