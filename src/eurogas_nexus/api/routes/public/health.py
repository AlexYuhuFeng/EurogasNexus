"""Health check route for the API shell."""

from fastapi import APIRouter, HTTPException, Request

from eurogas_nexus.api.route_profiles import authentication_posture
from eurogas_nexus.core.config import Settings
from eurogas_nexus.core.response import HealthResponse
from eurogas_nexus.release.versioning import display_version

router = APIRouter(tags=["health"])


@router.get("/api/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    """Return import-safe service health (process liveness).

    Answered on the event loop (it reads settings only, never the database): a load balancer's
    check measures the process, not the queue of request threads behind a busy minute.
    """

    from datetime import UTC, datetime

    from eurogas_nexus.application.clock_check import clock_status

    settings = getattr(request.app.state, "settings", Settings())
    # People read the display spelling (1.0.0-beta); /api/runtime/release carries the
    # SemVer one (1.0.0-beta.1) that client/server compatibility compares.
    return HealthResponse(
        server_time_utc=datetime.now(UTC).isoformat(timespec="milliseconds"),
        # The last clock check (never waits: a due check runs in the background).
        clock=clock_status(),
        version=display_version(settings.app_version),
        profile=settings.api_profile,
        authentication=authentication_posture(
            settings.api_profile,
            allow_anonymous_callers=settings.allow_anonymous_callers,
        ),
    )


@router.get("/api/health/live")
async def health_live(request: Request) -> dict:
    """Process liveness only. Never depends on PostgreSQL or providers."""

    settings = getattr(request.app.state, "settings", Settings())
    return {
        "status": "ok",
        "scope": "liveness",
        "version": display_version(settings.app_version),
        "profile": settings.api_profile,
        # The same posture the shell status reports: a probe can see whether this deployment
        # identifies its callers, and finding C5 stops being a document-only fact.
        "authentication": authentication_posture(
            settings.api_profile,
            allow_anonymous_callers=settings.allow_anonymous_callers,
        ),
    }


@router.get("/api/health/ready")
def health_ready(request: Request) -> dict:
    """Mandatory-dependency readiness.

    PostgreSQL is mandatory for data service. External providers are optional
    and deliberately excluded from readiness.
    """

    from eurogas_nexus.db.health import get_alembic_revision
    from eurogas_nexus.db.registry import list_missing_required_tables
    from eurogas_nexus.db.session import get_engine, resolve_database_url
    from eurogas_nexus.db.timescale import engine_state
    from eurogas_nexus.release.constants import DB_SCHEMA_REVISION

    database_url = resolve_database_url()
    if database_url is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "runtime_db_not_configured",
                "message": "Runtime PostgreSQL is not configured.",
            },
        )

    engine = None
    try:
        # A one-off engine (no pool): a probe every few seconds must not count in the request
        # pool's metrics, and it holds no connection between probes.
        engine = get_engine(database_url, one_off=True)
        # Reachability first: the revision read below swallows a connection failure, which
        # used to report an unreachable database (a failover) as "migrations not current".
        _require_writable_primary(engine)
        revision = get_alembic_revision(database_url)
        if revision != DB_SCHEMA_REVISION:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "runtime_schema_revision_mismatch",
                    "message": "Runtime PostgreSQL migrations are not current.",
                    "current_revision": revision,
                    "required_revision": DB_SCHEMA_REVISION,
                },
            )
        missing = list(list_missing_required_tables(engine))
        if missing:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "runtime_schema_incomplete",
                    "message": "Required PostgreSQL tables are missing.",
                    "missing_tables": sorted(missing),
                },
            )
        # Informational, never a readiness failure: TimescaleDB is an optional extension
        # and plain PostgreSQL is a complete runtime store (ADR Decision 39).
        timescale = engine_state(engine)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "runtime_db_unavailable",
                "message": "Runtime PostgreSQL is unreachable.",
                "error_class": exc.__class__.__name__,
            },
        ) from exc
    finally:
        if engine is not None:
            engine.dispose()

    return {
        "status": "ready",
        "scope": "readiness",
        "checks": {
            "runtime_db": "ok",
            "required_tables": "ok",
        },
        "extensions": {"timescaledb": timescale},
        # Informational, never a readiness failure (providers are optional): public sources
        # the ingestion gate holds back until an administrator approves them, so a fresh
        # installation says at its first probe what stands between it and live data.
        "attention": _public_source_attention(),
    }


def _require_writable_primary(engine) -> None:
    """Raise unless the database answers and accepts writes.

    A hot standby answers reads and holds the current schema, so it would pass every other
    check while refusing every write; during a failover the application must report not ready
    until it reaches the promoted primary (db/resilience.py).
    """

    from sqlalchemy import text

    from eurogas_nexus.db.resilience import in_recovery

    with engine.connect() as connection:
        connection.execute(text("SELECT 1")).scalar_one()
        if in_recovery(connection):
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "runtime_db_read_only",
                    "message": "Runtime PostgreSQL is a standby in recovery and refuses writes.",
                },
            )


def _public_source_attention() -> dict:
    try:
        from eurogas_nexus.application.public_source_approval import held_back_sources
        from eurogas_nexus.db.session import get_session_factory
        from eurogas_nexus.domain.ingestion.source_approval import (
            APPROVAL_ACTION,
            APPROVAL_SOURCE_IDS,
        )

        with get_session_factory()() as session:
            held = held_back_sources(session)
    except Exception:  # noqa: BLE001 - informational; readiness stays the DB checks
        return {}
    if not held:
        return {}
    return {
        "public_sources_held_back": [
            {"source_id": APPROVAL_SOURCE_IDS[item["source_system"]], "state": item["state"]}
            for item in held
        ],
        "action": f"{APPROVAL_ACTION} (or scripts/ops/approve_public_source.py)",
    }
