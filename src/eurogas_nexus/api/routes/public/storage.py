"""Read-only /api/storage routes."""

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["storage"])


def _env(data: object, _request: Request) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["runtime-db-not-configured"],
            "warnings": ["Runtime DB is not configured; GIE AGSI data is unavailable."],
        },
    }


def _runtime_env(data: object) -> dict:
    return {"data": data, "meta": {"research_only": True, "human_review_required": True,
            "source_references": ["runtime-postgresql"], "warnings": []}}


@router.get("/api/storage/sites")
def list_sites(request: Request) -> dict:
    observations = _db_storage_observations()
    if observations is None:
        return _env([], request)
    sites = {
        row["facility_id"]: {
            "site_id": row["facility_id"],
            "name": row["facility_name"],
            "country": row["country"],
            "working_capacity_twh": row["working_capacity_twh"],
            "fill_pct": row["fill_pct"],
            "status": "observed",
            "source_system": row["source_system"],
        }
        for row in observations
    }
    return _runtime_env(list(sites.values()))


@router.get("/api/storage/observations")
def list_observations(request: Request) -> dict:
    observations = _db_storage_observations()
    if observations is not None:
        return _runtime_env(observations)

    return _env([], request)


def _db_storage_observations() -> list[dict] | None:
    if not _db_is_configured():
        return None

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import StorageObservationRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = session.query(StorageObservationRecord).order_by(
                StorageObservationRecord.facility_name,
                StorageObservationRecord.period_start_utc.desc(),
            )
            return [_storage_row(row) for row in rows.all()]
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _storage_row(row) -> dict:
    return {
        "observation_id": row.observation_id,
        "source_dataset": row.source_dataset,
        "facility_id": row.facility_id,
        "facility_name": row.facility_name,
        "country": row.country,
        "inventory_twh": row.inventory_twh,
        "working_capacity_twh": row.working_capacity_twh,
        "fill_pct": row.fill_pct,
        "injection_twh_d": row.injection_twh_d,
        "withdrawal_twh_d": row.withdrawal_twh_d,
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
            "message": "Runtime database is configured but unavailable for storage reads.",
            "error_class": exc.__class__.__name__,
        },
    )
