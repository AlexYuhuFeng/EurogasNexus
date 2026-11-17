"""Health check route for the API shell."""

from fastapi import APIRouter, HTTPException, Request

from eurogas_nexus.api.route_profiles import authentication_posture
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
        authentication=authentication_posture(
            settings.api_profile,
            allow_anonymous_callers=settings.allow_anonymous_callers,
        ),
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
        engine = get_engine(database_url)
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
        # Informational, never a readiness failure (providers are optional): public sources
        # the ingestion gate holds back until an administrator approves them, so a fresh
        # installation says at its first probe what stands between it and live data.
        "attention": _public_source_attention(),
    }


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
