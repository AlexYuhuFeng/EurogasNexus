"""Centralized API route registration."""

from fastapi import FastAPI

from eurogas_nexus.api.route_profiles import ApiRouteProfile, get_route_profile
from eurogas_nexus.api.routes.dev.router import router as dev_router
from eurogas_nexus.api.routes.internal.router import router as internal_router
from eurogas_nexus.api.routes.public.access import router as access_router
from eurogas_nexus.api.routes.public.agents import router as agents_router
from eurogas_nexus.api.routes.public.analysis import router as analysis_router
from eurogas_nexus.api.routes.public.assumptions import router as assumptions_router
from eurogas_nexus.api.routes.public.auth import router as auth_router
from eurogas_nexus.api.routes.public.contracts import router as contracts_router
from eurogas_nexus.api.routes.public.cost_observations import router as cost_observations_router
from eurogas_nexus.api.routes.public.credentials import router as credentials_router
from eurogas_nexus.api.routes.public.data_platform import router as data_platform_router
from eurogas_nexus.api.routes.public.decision_cases import router as decision_cases_router
from eurogas_nexus.api.routes.public.desk import router as desk_router
from eurogas_nexus.api.routes.public.discoveries import router as discoveries_router
from eurogas_nexus.api.routes.public.explain import router as explain_router
from eurogas_nexus.api.routes.public.functional import router as functional_router
from eurogas_nexus.api.routes.public.fundamentals import router as fundamentals_router
from eurogas_nexus.api.routes.public.glossary import router as glossary_router
from eurogas_nexus.api.routes.public.health import router as health_router
from eurogas_nexus.api.routes.public.jobs import router as jobs_router
from eurogas_nexus.api.routes.public.lng import router as lng_router
from eurogas_nexus.api.routes.public.market import router as market_router
from eurogas_nexus.api.routes.public.market_normalisation import (
    router as market_normalisation_router,
)
from eurogas_nexus.api.routes.public.market_options import router as market_options_router
from eurogas_nexus.api.routes.public.monitoring import router as monitoring_router
from eurogas_nexus.api.routes.public.opportunities import router as opportunities_router
from eurogas_nexus.api.routes.public.optimization import router as optimization_router
from eurogas_nexus.api.routes.public.physical import router as physical_router
from eurogas_nexus.api.routes.public.portfolio import router as portfolio_router
from eurogas_nexus.api.routes.public.preferences import router as preferences_router
from eurogas_nexus.api.routes.public.projections import router as projections_router
from eurogas_nexus.api.routes.public.reference_network import router as reference_network_router
from eurogas_nexus.api.routes.public.reports import router as reports_router
from eurogas_nexus.api.routes.public.research import router as research_router
from eurogas_nexus.api.routes.public.research_data import router as research_data_router
from eurogas_nexus.api.routes.public.review import router as review_router
from eurogas_nexus.api.routes.public.risk import router as risk_router
from eurogas_nexus.api.routes.public.route_cost import router as route_cost_router
from eurogas_nexus.api.routes.public.runtime import router as runtime_router
from eurogas_nexus.api.routes.public.setup import router as setup_router
from eurogas_nexus.api.routes.public.shadow import router as shadow_router
from eurogas_nexus.api.routes.public.source_operations import router as source_operations_router
from eurogas_nexus.api.routes.public.sources import router as sources_router
from eurogas_nexus.api.routes.public.spread_lab import router as spread_lab_router
from eurogas_nexus.api.routes.public.spreads import router as spreads_router
from eurogas_nexus.api.routes.public.storage import router as storage_router
from eurogas_nexus.api.routes.public.strategy_lab import router as strategy_lab_router
from eurogas_nexus.api.routes.public.strategy_registry import router as strategy_registry_router
from eurogas_nexus.api.routes.public.strategy_tracks import router as strategy_tracks_router
from eurogas_nexus.api.routes.public.streaming import router as streaming_router
from eurogas_nexus.api.routes.public.support import router as support_router
from eurogas_nexus.api.routes.public.weather import router as weather_router

#: Design basis 2, I.3 and decision L4: capabilities kept in the backend, dormant, until a desk
#: use is proven: the dataset builder and the agents workspace. (The strategy registry and the
#: shadow runtime stay served while the Spreads backtest and shadow tracking are rebuilt on
#: StrategySpec; whether they are deferred is decided by that work.) Their routes are not served
#: unless an operator turns them back on, so the attack and maintenance surface shrinks with the
#: UI. The domain and application code stay, with tests.
DEFERRED_CAPABILITIES_ENV = "EUROGAS_NEXUS_DEFERRED_CAPABILITIES"


def deferred_capabilities_enabled() -> bool:
    """Whether the deferred capabilities' routes are served (off unless turned on)."""

    import os

    value = os.environ.get(DEFERRED_CAPABILITIES_ENV, "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def register_routes(
    app: FastAPI,
    profile: str | ApiRouteProfile = "development",
) -> ApiRouteProfile:
    """Register routes allowed by the selected route profile."""

    route_profile = profile if isinstance(profile, ApiRouteProfile) else get_route_profile(profile)

    deferred = deferred_capabilities_enabled()
    if route_profile.include_public:
        if deferred:
            app.include_router(agents_router)
        app.include_router(health_router)
        app.include_router(jobs_router)
        app.include_router(functional_router)
        app.include_router(auth_router)
        app.include_router(access_router)
        app.include_router(analysis_router)
        app.include_router(explain_router)
        app.include_router(desk_router)
        app.include_router(discoveries_router)
        app.include_router(reports_router)
        app.include_router(reference_network_router)
        app.include_router(sources_router)
        app.include_router(source_operations_router)
        app.include_router(market_router)
        app.include_router(market_options_router)
        app.include_router(assumptions_router)
        app.include_router(market_normalisation_router)
        app.include_router(opportunities_router)
        app.include_router(monitoring_router)
        app.include_router(portfolio_router)
        app.include_router(risk_router)
        app.include_router(support_router)
        app.include_router(fundamentals_router)
        app.include_router(physical_router)
        app.include_router(lng_router)
        app.include_router(storage_router)
        app.include_router(weather_router)
        app.include_router(contracts_router)
        app.include_router(cost_observations_router)
        app.include_router(credentials_router)
        app.include_router(data_platform_router)
        app.include_router(decision_cases_router)
        app.include_router(projections_router)
        app.include_router(glossary_router)
        app.include_router(research_router)
        app.include_router(spread_lab_router)
        app.include_router(spreads_router)
        app.include_router(strategy_tracks_router)
        app.include_router(preferences_router)
        app.include_router(setup_router)
        if deferred:
            app.include_router(research_data_router)
        app.include_router(review_router)
        app.include_router(route_cost_router)
        app.include_router(optimization_router)
        app.include_router(strategy_lab_router)
        app.include_router(strategy_registry_router)
        app.include_router(streaming_router)
        app.include_router(runtime_router)
        app.include_router(shadow_router)

    if route_profile.include_internal:
        app.include_router(internal_router)

    if route_profile.include_dev:
        app.include_router(dev_router)

    return route_profile
