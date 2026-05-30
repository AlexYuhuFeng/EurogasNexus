"""Development-only route router placeholder (profile-gated)."""

from fastapi import APIRouter

from eurogas_nexus.api.routes.dev.health import router as health_router

router = APIRouter(prefix="/api/dev", tags=["dev"])
router.include_router(health_router)
