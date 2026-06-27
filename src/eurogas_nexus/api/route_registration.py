"""Centralized API route registration."""

from fastapi import FastAPI

from eurogas_nexus.api.route_profiles import ApiRouteProfile, get_route_profile
from eurogas_nexus.api.routes.dev.router import router as dev_router
from eurogas_nexus.api.routes.internal.router import router as internal_router
from eurogas_nexus.api.routes.public.analysis import router as analysis_router
from eurogas_nexus.api.routes.public.contracts import router as contracts_router
from eurogas_nexus.api.routes.public.credentials import router as credentials_router
from eurogas_nexus.api.routes.public.glossary import router as glossary_router
from eurogas_nexus.api.routes.public.health import router as health_router
from eurogas_nexus.api.routes.public.lng import router as lng_router
from eurogas_nexus.api.routes.public.market import router as market_router
from eurogas_nexus.api.routes.public.physical import router as physical_router
from eurogas_nexus.api.routes.public.portfolio import router as portfolio_router
from eurogas_nexus.api.routes.public.reference_network import router as reference_network_router
from eurogas_nexus.api.routes.public.research import router as research_router
from eurogas_nexus.api.routes.public.route_cost import router as route_cost_router
from eurogas_nexus.api.routes.public.runtime import router as runtime_router
from eurogas_nexus.api.routes.public.sources import router as sources_router
from eurogas_nexus.api.routes.public.storage import router as storage_router
from eurogas_nexus.api.routes.public.strategy_lab import router as strategy_lab_router
from eurogas_nexus.api.routes.public.weather import router as weather_router
from eurogas_nexus.api.routes.public.workflows import router as workflows_router


def register_routes(
    app: FastAPI,
    profile: str | ApiRouteProfile = "development",
) -> ApiRouteProfile:
    """Register routes allowed by the selected route profile."""

    route_profile = profile if isinstance(profile, ApiRouteProfile) else get_route_profile(profile)

    if route_profile.include_public:
        app.include_router(health_router)
        app.include_router(analysis_router)
        app.include_router(reference_network_router)
        app.include_router(sources_router)
        app.include_router(market_router)
        app.include_router(portfolio_router)
        app.include_router(physical_router)
        app.include_router(lng_router)
        app.include_router(storage_router)
        app.include_router(weather_router)
        app.include_router(contracts_router)
        app.include_router(credentials_router)
        app.include_router(workflows_router)
        app.include_router(glossary_router)
        app.include_router(research_router)
        app.include_router(route_cost_router)
        app.include_router(strategy_lab_router)
        app.include_router(runtime_router)

    if route_profile.include_internal:
        app.include_router(internal_router)

    if route_profile.include_dev:
        app.include_router(dev_router)

    return route_profile
