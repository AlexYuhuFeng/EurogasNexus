"""Centralized API route registration."""

from fastapi import FastAPI

from eurogas_nexus.api.route_profiles import ApiRouteProfile, get_route_profile
from eurogas_nexus.api.routes.dev.health import router as dev_router
from eurogas_nexus.api.routes.internal.health import router as internal_router
from eurogas_nexus.api.routes.v1.health import router as health_router


def register_routes(
    app: FastAPI,
    profile: str | ApiRouteProfile = "development",
) -> ApiRouteProfile:
    """Register routes allowed by the selected route profile."""

    route_profile = profile if isinstance(profile, ApiRouteProfile) else get_route_profile(profile)

    if route_profile.include_v1:
        app.include_router(health_router)

    if route_profile.include_internal:
        app.include_router(internal_router)

    if route_profile.include_dev:
        app.include_router(dev_router)

    return route_profile
