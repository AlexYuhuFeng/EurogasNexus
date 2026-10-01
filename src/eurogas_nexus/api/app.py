"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from eurogas_nexus.api import runtime_dependencies
from eurogas_nexus.api.dependencies.commercial_access import require_commercial_access
from eurogas_nexus.api.dependencies.identity import require_identity
from eurogas_nexus.api.dependencies.public_auth import require_public_api_auth
from eurogas_nexus.api.dependencies.route_permission import require_route_permission
from eurogas_nexus.api.error_handlers import register_error_handlers
from eurogas_nexus.api.middleware.observability import HttpObservabilityMiddleware
from eurogas_nexus.api.middleware.origin_csrf import OriginCsrfGuardMiddleware
from eurogas_nexus.api.middleware.request_id import RequestIdMiddleware
from eurogas_nexus.api.route_profiles import get_route_profile
from eurogas_nexus.api.route_registration import register_routes
from eurogas_nexus.core.config import Settings, get_settings


@asynccontextmanager
async def _application_lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Complete runtime dependency initialization before requests are served.

    The runtime database imports stay lazy at each call site so importing the
    API does not load the DB layer; running them here, once and
    single-threaded, keeps concurrent first requests from racing in the import
    machinery (CI run ``36878083383``, CPython 3.11 ``_ModuleLock`` deadlock).
    The documented deployment server (uvicorn) runs this startup before it
    accepts work, so no request thread is ever the first importer.
    """

    runtime_dependencies.initialize_runtime_dependencies()
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an import-safe FastAPI application instance."""

    resolved_settings = settings or get_settings()

    route_profile = get_route_profile(resolved_settings.api_profile)

    dependencies = (
        [
            Depends(require_public_api_auth),
            Depends(require_identity),
            Depends(require_route_permission),
            # Architecture V2: rank alone cannot express "administration is not
            # commercial access", so commercial paths need a commercial capability.
            Depends(require_commercial_access),
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
        lifespan=_application_lifespan,
    )

    app.state.settings = resolved_settings

    app.state.route_profile = route_profile

    # Architecture V2 error envelope: every HTTPException keeps its original
    # ``detail`` and gains the stable code, family, severity, recoverability and
    # correlation id alongside it.
    register_error_handlers(app)

    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(HttpObservabilityMiddleware)
    app.add_middleware(OriginCsrfGuardMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Eurogas-Api-Key",
                       "X-Eurogas-Identity", "X-Eurogas-Oidc-Access-Token",
                       "X-Eurogas-Principal", "X-Eurogas-CSRF"],
        allow_credentials=True,
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


def _cors_origins() -> list[str]:
    import os

    configured = [
        value.strip().rstrip("/")
        for value in os.environ.get("EUROGAS_NEXUS_CORS_ORIGINS", "").split(",")
        if value.strip()
    ]
    return [
        "http://localhost",
        "http://127.0.0.1",
        "http://tauri.localhost",
        "tauri://localhost",
        *configured,
    ]
