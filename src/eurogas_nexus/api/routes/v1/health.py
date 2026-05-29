"""Health check route for the API shell."""

from fastapi import APIRouter, Request

from eurogas_nexus.core.config import Settings
from eurogas_nexus.core.response import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/api/v1/health", response_model=HealthResponse)
@router.get("/v1/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """Return import-safe service health."""

    settings = getattr(request.app.state, "settings", Settings())
    return HealthResponse(
        version=settings.app_version,
        profile=settings.api_profile,
    )


