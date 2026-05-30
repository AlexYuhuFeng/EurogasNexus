"""Centralized API route registration."""

from fastapi import FastAPI

from eurogas_nexus.api.route_profiles import ApiRouteProfile, get_route_profile
from eurogas_nexus.api.routes.dev.router import router as dev_router
from eurogas_nexus.api.routes.internal.router import router as internal_router
from eurogas_nexus.api.routes.v1.contracts import router as contracts_router
from eurogas_nexus.api.routes.v1.credentials import router as credentials_router
from eurogas_nexus.api.routes.v1.glossary import router as glossary_router
from eurogas_nexus.api.routes.v1.health import router as health_router
from eurogas_nexus.api.routes.v1.lng import router as lng_router
from eurogas_nexus.api.routes.v1.market import router as market_router
from eurogas_nexus.api.routes.v1.physical import router as physical_router
from eurogas_nexus.api.routes.v1.reference_network import router as reference_network_router
from eurogas_nexus.api.routes.v1.research import router as research_router
from eurogas_nexus.api.routes.v1.runtime import router as runtime_router
from eurogas_nexus.api.routes.v1.sources import router as sources_router
from eurogas_nexus.api.routes.v1.storage import router as storage_router
from eurogas_nexus.api.routes.v1.weather import router as weather_router
from eurogas_nexus.api.routes.v1.workflows import router as workflows_router


def register_routes(
    app: FastAPI,
    profile: str | ApiRouteProfile = "development",
) -> ApiRouteProfile:
    """Register routes allowed by the selected route profile."""

    route_profile = profile if isinstance(profile, ApiRouteProfile) else get_route_profile(profile)

    if route_profile.include_v1:
        app.include_router(health_router)
        app.include_router(reference_network_router)
        app.include_router(sources_router)
        app.include_router(market_router)
        app.include_router(physical_router)
        app.include_router(lng_router)
        app.include_router(storage_router)
        app.include_router(weather_router)
        app.include_router(contracts_router)
        app.include_router(credentials_router)
        app.include_router(workflows_router)
        app.include_router(glossary_router)
        app.include_router(research_router)
        app.include_router(runtime_router)

    if route_profile.include_internal:
        app.include_router(internal_router)

    if route_profile.include_dev:
        app.include_router(dev_router)

    return route_profile
