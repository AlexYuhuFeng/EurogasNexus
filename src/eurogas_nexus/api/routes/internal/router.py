"""Internal route router placeholder (profile-gated)."""

from fastapi import APIRouter

from eurogas_nexus.api.routes.internal.health import router as health_router
from eurogas_nexus.api.routes.internal.portfolio_import import router as portfolio_import_router
from eurogas_nexus.api.routes.internal.source_certification import (
    router as source_certification_router,
)

router = APIRouter(prefix="/api/internal", tags=["internal"])
router.include_router(health_router)
router.include_router(portfolio_import_router)
router.include_router(source_certification_router)
