"""Runtime DB and service status route 鈥?/api/runtime/db."""

from datetime import datetime

from fastapi import APIRouter, Request

router = APIRouter(tags=["runtime"])


@router.get("/api/runtime/db")
def runtime_db_status(request: Request) -> dict:
    """Read-only runtime DB status with research metadata."""
    from eurogas_nexus.db.registry import list_required_tables
    from eurogas_nexus.db.session import redact_database_url, resolve_database_url

    url = resolve_database_url()
    report = {
        "database_url_present": url is not None,
        "redacted_database_url": redact_database_url(url),
        "connectivity": {"ok": False, "error": None},
        "alembic_revision": None,
        "required_tables": list(list_required_tables()),
        "missing_tables": list(list_required_tables()),
        "warnings": [],
    }

    if url is None:
        report["connectivity"]["error"] = "No database URL configured."
        report["warnings"].append(
            "Set RUNTIME_STORE_DATABASE_URL, DATABASE_URL, or EUROGAS_NEXUS_DB_DSN."
        )
    else:
        try:
            from eurogas_nexus.db.health import check_db_connectivity, get_alembic_revision
            from eurogas_nexus.db.session import get_engine

            conn = check_db_connectivity(url)
            report["connectivity"] = {"ok": conn.ok, "error": conn.error}
            if conn.ok:
                report["alembic_revision"] = get_alembic_revision(url)
                engine = get_engine(url)
                try:
                    from eurogas_nexus.db.registry import list_missing_required_tables
                    missing = list(list_missing_required_tables(engine))
                    report["missing_tables"] = missing
                    if missing:
                        report["warnings"].append(f"Missing tables: {', '.join(missing)}")
                finally:
                    engine.dispose()
        except Exception as exc:
            report["connectivity"]["error"] = f"{exc.__class__.__name__}: {exc}"
            report["warnings"].append("DB connectivity check failed.")

    return {
        "data": report,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": [
                "runtime-postgresql" if report["connectivity"]["ok"] else "runtime-unavailable"
            ],
            "warnings": report["warnings"],
        },
    }


@router.get("/api/runtime/dependencies")
def runtime_dependencies(request: Request) -> dict:
    """Return the dependency/failure matrix snapshot (safe, no secrets)."""

    from datetime import UTC, datetime

    from eurogas_nexus.db.registry import list_missing_required_tables
    from eurogas_nexus.db.session import get_engine, resolve_database_url
    from eurogas_nexus.security.oidc import oidc_configured

    now = datetime.now(UTC)
    database_url = resolve_database_url()
    db = {
        "state": "UNAVAILABLE",
        "detail": "Runtime PostgreSQL is not configured.",
    }
    if database_url:
        engine = None
        try:
            engine = get_engine(database_url)
            missing = list(list_missing_required_tables(engine))
            db = {
                "state": "AVAILABLE" if not missing else "DEGRADED",
                "detail": "schema incomplete" if missing else "schema ok",
                "missing_tables": sorted(missing),
                "checked_at_utc": now.isoformat(),
            }
        except Exception as exc:
            db = {
                "state": "UNAVAILABLE",
                "detail": exc.__class__.__name__,
                "checked_at_utc": now.isoformat(),
            }
        finally:
            if engine is not None:
                engine.dispose()

    schedulers = {"dataops": {"state": "UNKNOWN"}, "shadow": {"state": "UNKNOWN"}}
    if database_url:
        try:
            from eurogas_nexus.db.models import (
                DataOperationsHeartbeatRecord,
                StrategyShadowSchedulerHeartbeatRecord,
            )
            from eurogas_nexus.db.session import get_session_factory

            with get_session_factory()() as session:
                dataops = session.get(DataOperationsHeartbeatRecord, "primary")
                shadow = session.get(StrategyShadowSchedulerHeartbeatRecord, "primary")
                schedulers["dataops"] = _heartbeat_state(
                    dataops.last_heartbeat_at_utc if dataops else None, now
                )
                schedulers["shadow"] = _heartbeat_state(
                    shadow.last_heartbeat_at_utc if shadow else None, now
                )
        except Exception:
            pass

    return {
        "data": {
            "generated_at_utc": now.isoformat(),
            "database": db,
            "schedulers": schedulers,
            "oidc": {
                "configured": oidc_configured(),
                "state": "AVAILABLE" if oidc_configured() else "NOT_REQUIRED",
            },
            "llm": {
                "state": "GATED",
                "detail": "external provider calls are profile-gated",
            },
            "streaming": {
                "state": "AVAILABLE",
                "detail": "SSE is advisory; PostgreSQL/API remain canonical",
            },
        },
        "meta": {
            "research_only": True,
            "human_review_required": False,
            "source_references": ["runtime-postgresql", "scheduler-heartbeats"],
            "warnings": [],
        },
    }


def _heartbeat_state(last: datetime | None, now: datetime) -> dict:
    if last is None:
        return {"state": "UNKNOWN", "detail": "no heartbeat recorded"}
    from eurogas_nexus.domain.dataops.contracts import as_utc

    age_seconds = max(0.0, (now - as_utc(last)).total_seconds())
    if age_seconds <= 180:
        state = "AVAILABLE"
    elif age_seconds <= 900:
        state = "DEGRADED"
    else:
        state = "UNAVAILABLE"
    return {
        "state": state,
        "last_heartbeat_at_utc": as_utc(last).isoformat(),
        "age_seconds": round(age_seconds, 1),
    }


@router.get("/api/runtime/pipeline-health")
def pipeline_health_status(request: Request) -> dict:
    """Read-only pipeline health aggregation (freshness/errors/open alerts)."""

    from sqlalchemy.exc import SQLAlchemyError

    from eurogas_nexus.application.pipeline_health import (
        empty_pipeline_health,
        pipeline_health,
    )
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    warnings: list[str] = []
    if resolve_database_url() is None:
        data = empty_pipeline_health()
        warnings.append("RUNTIME_DB_NOT_CONFIGURED")
    else:
        try:
            with get_session_factory()() as session:
                data = pipeline_health(session)
        except SQLAlchemyError:
            data = empty_pipeline_health()
            warnings.append("RUNTIME_POSTGRESQL_UNAVAILABLE")

    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": False,
            "source_references": ["runtime-postgresql"],
            "warnings": warnings,
        },
    }
