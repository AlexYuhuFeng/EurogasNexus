"""Read-only /api/lng routes."""

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["lng"])


def _env(data: object, _request: Request) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["runtime-db-not-configured"],
            "warnings": ["Runtime DB is not configured; GIE ALSI data is unavailable."],
        },
    }


def _runtime_env(data: object) -> dict:
    return {"data": data, "meta": {"research_only": True, "human_review_required": True,
            "source_references": ["runtime-postgresql"], "warnings": []}}


@router.get("/api/lng/terminals")
def list_terminals(request: Request) -> dict:
    observations = _db_lng_observations()
    if observations is None:
        return _env([], request)
    terminals = {
        row["terminal_id"]: {
            "terminal_id": row["terminal_id"],
            "name": row["terminal_name"],
            "country": row["country"],
            "inventory_twh": row["inventory_twh"],
            "send_out_twh_d": row["send_out_twh_d"],
            "dtmi_pct": row["dtmi_pct"],
            "status": "observed",
            "source_system": row["source_system"],
        }
        for row in observations
    }
    return _runtime_env(list(terminals.values()))


@router.get("/api/lng/observations")
def list_observations(request: Request) -> dict:
    observations = _db_lng_observations()
    if observations is not None:
        return _runtime_env(observations)

    return _env([], request)


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
