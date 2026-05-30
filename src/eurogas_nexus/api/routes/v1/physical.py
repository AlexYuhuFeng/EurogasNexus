"""Read-only /api/v1/physical routes."""

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["physical"])


@router.get("/api/v1/physical/flows")
def list_flows(request: Request) -> dict:
    flows = _db_flow_observations()
    if flows is not None:
        return _env(flows, source="runtime-postgresql")

    return _env(_fixture_flows(), source="synthetic-fixture")


@router.get("/api/v1/physical/capacity")
def list_capacity(request: Request) -> dict:
    return _env(
        [
            {
                "observation_id": "cap-001",
                "point_id": "node-zeebrugge",
                "point_name": "Zeebrugge",
                "capacity_type": "technical",
                "capacity_mcm_d": 100.0,
                "period_start_utc": "2026-05-29T06:00:00Z",
                "period_end_utc": "2026-05-30T06:00:00Z",
            },
            {
                "observation_id": "cap-002",
                "point_id": "node-emden",
                "point_name": "Emden",
                "capacity_type": "technical",
                "capacity_mcm_d": 150.0,
                "period_start_utc": "2026-05-29T06:00:00Z",
                "period_end_utc": "2026-05-30T06:00:00Z",
            },
        ],
        source="synthetic-fixture",
    )


@router.get("/api/v1/physical/outages")
def list_outages(request: Request) -> dict:
    return _env(
        [
            {
                "event_id": "out-001",
                "facility_id": "fac-mallnow",
                "facility_name": "Mallnow",
                "event_type": "planned",
                "status": "scheduled",
                "start_utc": "2026-06-15T06:00:00Z",
                "end_utc": "2026-06-20T06:00:00Z",
                "capacity_impact_mcm_d": 20.0,
                "description": "Scheduled maintenance.",
            },
        ],
        source="synthetic-fixture",
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


def _fixture_flows() -> list[dict]:
    return [
        {
            "observation_id": "flw-001",
            "point_id": "node-zeebrugge",
            "point_name": "Zeebrugge",
            "direction": "entry",
            "flow_mcm_d": 85.0,
            "period_start_utc": "2026-05-29T06:00:00Z",
            "period_end_utc": "2026-05-30T06:00:00Z",
        },
        {
            "observation_id": "flw-002",
            "point_id": "node-emden",
            "point_name": "Emden",
            "direction": "entry",
            "flow_mcm_d": 120.0,
            "period_start_utc": "2026-05-29T06:00:00Z",
            "period_end_utc": "2026-05-30T06:00:00Z",
        },
        {
            "observation_id": "flw-003",
            "point_id": "node-mallnow",
            "point_name": "Mallnow",
            "direction": "entry",
            "flow_mcm_d": 45.0,
            "period_start_utc": "2026-05-29T06:00:00Z",
            "period_end_utc": "2026-05-30T06:00:00Z",
        },
    ]


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


def _env(data: object, *, source: str) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": [source],
            "warnings": ["Synthetic data only. Do not use for commercial decisions."],
        },
    }
