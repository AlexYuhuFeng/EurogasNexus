"""FastAPI application factory."""

from fastapi import FastAPI

from eurogas_nexus.api.route_profiles import get_route_profile
from eurogas_nexus.api.route_registration import register_routes
from eurogas_nexus.core.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an import-safe FastAPI application instance."""

    resolved_settings = settings or get_settings()
    route_profile = get_route_profile(resolved_settings.api_profile)

    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        docs_url="/docs" if route_profile.expose_docs else None,
        redoc_url="/redoc" if route_profile.expose_docs else None,
        openapi_url="/openapi.json" if route_profile.expose_openapi else None,
    )
    app.state.settings = resolved_settings
    app.state.route_profile = route_profile

    register_routes(app, route_profile)
    return app

