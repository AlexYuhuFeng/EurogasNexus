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
from eurogas_nexus.api.middleware.compression import ApiReadCompressionMiddleware
from eurogas_nexus.api.middleware.conditional import ConditionalReadMiddleware
from eurogas_nexus.api.middleware.database_failure import DatabaseFailureMiddleware
from eurogas_nexus.api.middleware.licensed_use import LicensedUseMiddleware
from eurogas_nexus.api.middleware.metrics_endpoint import MetricsEndpointMiddleware
from eurogas_nexus.api.middleware.observability import HttpObservabilityMiddleware
from eurogas_nexus.api.middleware.origin_csrf import OriginCsrfGuardMiddleware
from eurogas_nexus.api.middleware.request_id import RequestIdMiddleware
from eurogas_nexus.api.middleware.runtime_store_state import RuntimeStoreStateMiddleware
from eurogas_nexus.api.middleware.warm_views import WarmViewWriteMiddleware
from eurogas_nexus.api.route_profiles import assert_profile_allowed, get_route_profile
from eurogas_nexus.api.route_registration import register_routes
from eurogas_nexus.api.web_client import (
    SecurityHeadersMiddleware,
    WebClientMiddleware,
    resolve_web_client_dir,
)
from eurogas_nexus.core.config import Settings, get_settings
from eurogas_nexus.security.rate_limit import require_principal_quota


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

    # Logs, traces and this worker's metric files before any request (each worker runs this).
    from eurogas_nexus.application import process_metrics
    from eurogas_nexus.core import structured_logging, tracing

    structured_logging.configure_logging(service="eurogas-nexus-api")
    tracing.initialise("eurogas-nexus-api")
    process_metrics.prepare_process()
    runtime_dependencies.initialize_runtime_dependencies()
    # Request threads sized from the database pool, so a request waits for a thread (no
    # timeout) rather than for a connection (an error after the pool timeout).
    import anyio.to_thread

    from eurogas_nexus.db.session import api_thread_limit, use_api_statement_timeout

    anyio.to_thread.current_default_thread_limiter().total_tokens = api_thread_limit()
    # The API's database connections cancel a runaway statement (db/session.py). Set here,
    # before any request opens the first connection, not when the app is created: importing
    # the API must not load the database layer.
    use_api_statement_timeout()
    # Background jobs run in this process: one that was running when the server last
    # stopped can never finish, so it is failed with a reason now (best effort, never fatal).
    from starlette.concurrency import run_in_threadpool

    from eurogas_nexus.application.background_jobs import fail_orphaned_jobs_quietly

    # Database work never runs on the event loop, at startup and shutdown included.
    await run_in_threadpool(fail_orphaned_jobs_quietly)
    yield
    # Close pooled database connections cleanly on shutdown (no-op when none were opened).
    from eurogas_nexus.db.session import dispose_cached_engines

    await run_in_threadpool(dispose_cached_engines)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create an import-safe FastAPI application instance."""

    resolved_settings = settings or get_settings()

    route_profile = get_route_profile(resolved_settings.api_profile)
    assert_profile_allowed(route_profile.name, resolved_settings.environment)
    # Demo test accounts (a weak shared password) exist only on the hosted demo server.
    from eurogas_nexus.security.local_accounts_policy import assert_demo_accounts_allowed

    assert_demo_accounts_allowed(route_profile.name, resolved_settings.environment)
    # Book isolation is on by default; off only where declared single-office (H1).
    from eurogas_nexus.security.portfolio_scope import assert_isolation_setting_allowed

    assert_isolation_setting_allowed(resolved_settings.environment)
    # The deployment token's mode, role and scopes (H3).
    from eurogas_nexus.security.deployment_token import assert_token_settings_allowed

    assert_token_settings_allowed()
    # A release server needs a deliberate way to sign in (H6), and dual control stays on (H7).
    from eurogas_nexus.api.dual_control import assert_dual_control_setting_allowed
    from eurogas_nexus.security.local_accounts_policy import assert_sign_in_configured

    assert_sign_in_configured(resolved_settings.environment)
    assert_dual_control_setting_allowed()

    dependencies = (
        [
            Depends(require_public_api_auth),
            Depends(require_identity),
            Depends(require_route_permission),
            # Architecture V2: rank alone cannot express "administration is not
            # commercial access", so commercial paths need a commercial capability.
            Depends(require_commercial_access),
            # Per-principal quotas on writes and heavy computations (security review M7).
            Depends(require_principal_quota),
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

    # Innermost: a statement the database cancelled, or a lost store, that no route caught
    # answers the coded 503 with Retry-After instead of a bare 500.
    app.add_middleware(DatabaseFailureMiddleware)
    # A read answered without a runtime database says so in its meta (one rule for every
    # route; a deployment with a database never enters it).
    app.add_middleware(RuntimeStoreStateMiddleware)
    # One licensed-data usage meter per API request (GOV-1, P6).
    app.add_middleware(LicensedUseMiddleware)
    # A successful write makes the kept heavy reads due (application/warm_views.py).
    app.add_middleware(WarmViewWriteMiddleware)
    # Inside the compression: the ETag is a hash of the uncompressed answer.
    app.add_middleware(ConditionalReadMiddleware)
    app.add_middleware(ApiReadCompressionMiddleware)
    # The request id is outside the observability layer, so the access record, the span
    # and every log line of the request carry it.
    app.add_middleware(HttpObservabilityMiddleware)
    app.add_middleware(RequestIdMiddleware)
    app.add_middleware(OriginCsrfGuardMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins(),
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Eurogas-Api-Key",
            "X-Eurogas-Identity",
            "X-Eurogas-Oidc-Access-Token",
            "X-Eurogas-Principal",
            "X-Eurogas-CSRF",
            "X-Eurogas-Session",
            "X-Eurogas-Dual-Control",
            "X-Eurogas-Break-Glass",
        ],
        allow_credentials=True,
    )

    if route_profile.expose_openapi:
        _declare_openapi_security_scheme(app)

    register_routes(app, route_profile)

    # Opt-in single-origin hosting of the built web client (hosted test/demo server).
    # Unset in customer deployments, where nothing below is installed.
    web_client_dir = resolve_web_client_dir()
    if web_client_dir is not None:
        app.add_middleware(WebClientMiddleware, directory=web_client_dir)
    # Security headers on every answer in every deployment (security review M5).
    app.add_middleware(SecurityHeadersMiddleware, serves_pages=web_client_dir is not None)

    # Outermost: ``GET /metrics`` for the configured scrape identity only (404 otherwise),
    # before the sign-in dependencies and the web client's page fallback.
    app.add_middleware(MetricsEndpointMiddleware)

    return app


def _declare_openapi_security_scheme(app: FastAPI) -> None:
    """Declare the public API token security scheme in the OpenAPI document.

    Development docs only (release hides OpenAPI entirely). The scheme mirrors
    the enforcement applied by ``require_public_api_auth`` in release.
    """

    original_openapi = app.openapi

    def openapi_with_security() -> dict:
        schema = original_openapi()
        schema.setdefault("components", {}).setdefault("securitySchemes", {})["ApiKeyAuth"] = {
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
    from eurogas_nexus.api.middleware.origin_csrf import cors_origins

    return cors_origins()
