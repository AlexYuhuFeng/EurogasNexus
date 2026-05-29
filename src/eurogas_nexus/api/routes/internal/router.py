"""Internal route router placeholder (profile-gated)."""

from fastapi import APIRouter

from eurogas_nexus.api.routes.internal.health import router as health_router

router = APIRouter(prefix="/api/internal", tags=["internal"])
router.include_router(health_router)
