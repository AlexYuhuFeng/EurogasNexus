"""FastAPI application factory."""

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from eurogas_nexus.api.dependencies.identity import require_identity
from eurogas_nexus.api.dependencies.public_auth import require_public_api_auth
from eurogas_nexus.api.dependencies.route_permission import require_route_permission
from eurogas_nexus.api.middleware.request_id import RequestIdMiddleware
from eurogas_nexus.api.route_profiles import get_route_profile
from eurogas_nexus.api.route_registration import register_routes
from eurogas_nexus.core.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an import-safe FastAPI application instance."""

    resolved_settings = settings or get_settings()

    route_profile = get_route_profile(resolved_settings.api_profile)

    dependencies = (
        [
            Depends(require_public_api_auth),
            Depends(require_identity),
            Depends(require_route_permission),
        ]
        if route_profile.require_auth
        else []
    )
    app = FastAPI(
        title=resolved_settings.app_name,
        version=resolved_settings.app_version,
        docs_url="/docs" if route_profile.expose_docs else None,
        redoc_url="/redoc" if route_profile.expose_docs else None,
        openapi_url="/openapi.json" if route_profile.expose_openapi else None,
        dependencies=dependencies,
    )

    app.state.settings = resolved_settings

    app.state.route_profile = route_profile

    app.add_middleware(RequestIdMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=(
            r"^(https?://(localhost|127\.0\.0\.1)(:\d+)?|"
            r"https?://tauri\.localhost|tauri://localhost)$"
        ),
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        allow_credentials=False,
    )

    if route_profile.expose_openapi:
        _declare_openapi_security_scheme(app)

    register_routes(app, route_profile)

    return app


def _declare_openapi_security_scheme(app: FastAPI) -> None:
    """Declare the public API token security scheme in the OpenAPI document.

    Development docs only (release hides OpenAPI entirely). The scheme mirrors
    the enforcement applied by ``require_public_api_auth`` in release.
    """

    original_openapi = app.openapi

    def openapi_with_security() -> dict:
        schema = original_openapi()
        schema.setdefault("components", {}).setdefault("securitySchemes", {})[
            "ApiKeyAuth"
        ] = {
            "type": "http",
            "scheme": "bearer",
            "description": (
                "Public API token (EUROGAS_NEXUS_PUBLIC_API_TOKEN). Required by "
                "the release profile."
            ),
        }
        schema.setdefault("security", [{"ApiKeyAuth": []}])
        return schema

    app.openapi = openapi_with_security  # type: ignore[method-assign]
