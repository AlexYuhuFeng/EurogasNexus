"""Health check route for the API shell."""

from fastapi import APIRouter, HTTPException, Request

from eurogas_nexus.core.config import Settings
from eurogas_nexus.core.response import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/api/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """Return import-safe service health (process liveness)."""

    settings = getattr(request.app.state, "settings", Settings())
    return HealthResponse(
        version=settings.app_version,
        profile=settings.api_profile,
    )


@router.get("/api/health/live")
def health_live(request: Request) -> dict:
    """Process liveness only. Never depends on PostgreSQL or providers."""

    settings = getattr(request.app.state, "settings", Settings())
    return {
        "status": "ok",
        "scope": "liveness",
        "version": settings.app_version,
        "profile": settings.api_profile,
    }


@router.get("/api/health/ready")
def health_ready(request: Request) -> dict:
    """Mandatory-dependency readiness.

    PostgreSQL is mandatory for data service. External providers are optional
    and deliberately excluded from readiness.
    """

    from eurogas_nexus.db.registry import list_missing_required_tables
    from eurogas_nexus.db.session import get_engine, resolve_database_url

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
        engine = get_engine(database_url)
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
    }


