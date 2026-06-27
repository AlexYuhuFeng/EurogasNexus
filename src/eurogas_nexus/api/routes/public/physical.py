"""Read-only /api/physical routes."""

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["physical"])


@router.get("/api/physical/flows")
def list_flows(request: Request) -> dict:
    flows = _db_flow_observations()
    if flows is not None:
        return _env(flows, source="runtime-postgresql", warnings=[])

    return _env(
        [],
        source="runtime-db-not-configured",
        warnings=["Runtime DB is not configured; ENTSOG flow observations are unavailable."],
    )


@router.get("/api/physical/capacity")
def list_capacity(request: Request) -> dict:
    capacity = _db_capacity_observations()
    if capacity is not None:
        return _env(capacity, source="runtime-postgresql", warnings=[])

    return _env(
        [],
        source="runtime-db-not-configured",
        warnings=["Runtime DB is not configured; ENTSOG capacity observations are unavailable."],
    )


@router.get("/api/physical/outages")
def list_outages(request: Request) -> dict:
    return _env(
        [],
        source="runtime-db-not-configured",
        warnings=["Outage endpoint requires source ingestion; no fallback data returned."],
    )


def _db_flow_observations() -> list[dict] | None:
    if not _db_is_configured():
        return None

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import FlowObservationRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = session.query(FlowObservationRecord).order_by(
                FlowObservationRecord.point_name,
                FlowObservationRecord.direction,
            )
            return [_flow_row(row) for row in rows.all()]
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _db_capacity_observations() -> list[dict] | None:
    if not _db_is_configured():
        return None

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import CapacityObservationRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = session.query(CapacityObservationRecord).order_by(
                CapacityObservationRecord.point_name,
                CapacityObservationRecord.direction,
                CapacityObservationRecord.capacity_type,
            )
            return [_capacity_row(row) for row in rows.all()]
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _flow_row(row) -> dict:
    return {
        "observation_id": row.observation_id,
        "point_id": row.point_id,
        "point_name": row.point_name,
        "direction": row.direction,
        "flow_mcm_d": row.flow_mcm_d,
        "period_start_utc": row.period_start_utc.isoformat(),
        "period_end_utc": row.period_end_utc.isoformat(),
        "observed_at_utc": row.observed_at_utc.isoformat(),
        "source_system": row.source_system,
        "source_reference": row.source_reference,
        "freshness": row.freshness,
        "research_only": row.research_only,
    }


def _capacity_row(row) -> dict:
    return {
        "observation_id": row.observation_id,
        "point_id": row.point_id,
        "point_name": row.point_name,
        "direction": row.direction,
        "capacity_type": row.capacity_type,
        "capacity_mcm_d": row.capacity_mcm_d,
        "original_value": row.original_value,
        "original_unit": row.original_unit,
        "period_start_utc": row.period_start_utc.isoformat(),
        "period_end_utc": row.period_end_utc.isoformat(),
        "observed_at_utc": row.observed_at_utc.isoformat(),
        "source_system": row.source_system,
        "source_reference": row.source_reference,
        "freshness": row.freshness,
        "research_only": row.research_only,
    }


def _db_is_configured() -> bool:
    from eurogas_nexus.db.session import resolve_database_url

    return resolve_database_url() is not None


def _sqlalchemy_error_type():
    from sqlalchemy.exc import SQLAlchemyError

    return SQLAlchemyError


def _db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "runtime_db_unavailable",
            "message": "Runtime database is configured but unavailable for physical flow reads.",
            "error_class": exc.__class__.__name__,
        },
    )


def _env(data: object, *, source: str, warnings: list[str] | None = None) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": [source],
            "warnings": warnings or [],
        },
    }
