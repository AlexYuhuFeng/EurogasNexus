"""Read-only /api/v1/lng routes."""

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["lng"])


def _env(data: object, _request: Request) -> dict:
    return {"data": data, "meta": {"research_only": True, "human_review_required": True,
            "source_references": ["synthetic-fixture"], "warnings": ["Synthetic data only."]}}


def _runtime_env(data: object) -> dict:
    return {"data": data, "meta": {"research_only": True, "human_review_required": True,
            "source_references": ["runtime-postgresql"], "warnings": []}}


@router.get("/api/v1/lng/terminals")
def list_terminals(request: Request) -> dict:
    return _env([
        {"terminal_id": "lng-zeebrugge", "name": "Zeebrugge LNG", "country": "BE",
         "lat": 51.33, "lon": 3.20, "capacity_mcm_d": 30.0, "storage_capacity_mcm": 380.0,
         "status": "operational"},
        {"terminal_id": "lng-gate", "name": "Gate LNG", "country": "NL",
         "lat": 51.90, "lon": 4.30, "capacity_mcm_d": 36.0, "storage_capacity_mcm": 540.0,
         "status": "operational"},
        {"terminal_id": "lng-dunkerque", "name": "Dunkerque LNG", "country": "FR",
         "lat": 51.04, "lon": 2.38, "capacity_mcm_d": 40.0, "storage_capacity_mcm": 600.0,
         "status": "operational"},
    ], request)


@router.get("/api/v1/lng/observations")
def list_observations(request: Request) -> dict:
    observations = _db_lng_observations()
    if observations is not None:
        return _runtime_env(observations)

    return _env([
        {"observation_id": "lng-001", "terminal_id": "lng-gate", "terminal_name": "Gate LNG",
         "observation_type": "send_out", "value_mcm": 28.0,
         "period_start_utc": "2026-05-29T06:00:00Z", "period_end_utc": "2026-05-30T06:00:00Z"},
        {"observation_id": "lng-002", "terminal_id": "lng-zeebrugge",
         "terminal_name": "Zeebrugge LNG", "observation_type": "cargo_arrival",
         "value_mcm": 140.0, "period_start_utc": "2026-05-30T12:00:00Z"},
    ], request)


def _db_lng_observations() -> list[dict] | None:
    if not _db_is_configured():
        return None

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import LngObservationRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = session.query(LngObservationRecord).order_by(
                LngObservationRecord.terminal_name,
                LngObservationRecord.period_start_utc.desc(),
            )
            return [_lng_row(row) for row in rows.all()]
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _lng_row(row) -> dict:
    return {
        "observation_id": row.observation_id,
        "source_dataset": row.source_dataset,
        "terminal_id": row.terminal_id,
        "terminal_name": row.terminal_name,
        "country": row.country,
        "inventory_twh": row.inventory_twh,
        "send_out_twh_d": row.send_out_twh_d,
        "dtmi_pct": row.dtmi_pct,
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
            "message": "Runtime database is configured but unavailable for LNG reads.",
            "error_class": exc.__class__.__name__,
        },
    )
