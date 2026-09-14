"""Development-only route router (profile-gated).

Registered only when the route profile sets ``include_dev``, which is true for
the development profile alone; the internal and release profiles never mount
``/api/dev/*``.
"""

from fastapi import APIRouter

from eurogas_nexus.api.routes.dev.auth import router as auth_router
from eurogas_nexus.api.routes.dev.health import router as health_router

router = APIRouter(prefix="/api/dev", tags=["dev"])
router.include_router(health_router)
router.include_router(auth_router)
