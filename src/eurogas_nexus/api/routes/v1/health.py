"""Health check route for the API shell."""

from fastapi import APIRouter, Request

from eurogas_nexus.core.config import Settings
from eurogas_nexus.core.response import HealthResponse

router = APIRouter(prefix="/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    """Return import-safe service health."""

    settings = getattr(request.app.state, "settings", Settings())
    return HealthResponse(
        version=settings.app_version,
        profile=settings.api_profile,
    )

