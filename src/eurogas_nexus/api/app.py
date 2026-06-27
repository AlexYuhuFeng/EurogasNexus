"""FastAPI application factory."""



from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import Response

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

    @app.middleware("http")
    async def normalize_legacy_api_paths(request: Request, call_next) -> Response:
        """Route hidden legacy prefixes to the current public API path."""

        path = request.scope.get("path", "")
        normalized_path: str | None = None
        if path == "/api/v1":
            normalized_path = "/api"
        elif path.startswith("/api/v1/"):
            normalized_path = "/api/" + path.removeprefix("/api/v1/")
        elif path == "/v1/health":
            normalized_path = "/api/health"

        if normalized_path is not None:
            request.scope["path"] = normalized_path
            request.scope["raw_path"] = normalized_path.encode("ascii")

        return await call_next(request)

    register_routes(app, route_profile)

    return app
