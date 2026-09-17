"""Read-only /api/market routes.

The loading and shaping code for every slice lives in
``eurogas_nexus.application.projections.market_reads`` so the Wave 5
MarketContext projection composes exactly these reads instead of re-implementing
them. This module keeps the HTTP concerns: the runtime-database guard, the
``503 runtime_db_unavailable`` translation and the response envelope. Every
response field of every endpoint below is unchanged.
"""

from fastapi import APIRouter, HTTPException, Query, Request

from eurogas_nexus.api.dependencies.row_entitlement import current_principal
from eurogas_nexus.application.projections.market_reads import (
    derive_intraday_spreads,
    filter_entitled_rows,
    fx_observation_row,
    fx_observations,
    fx_row_from_market_observation,
    intraday_opportunities,
    market_observation_row,
    market_observations,
    market_quotes,
    normalized_market_view,
    source_family_filter,
)

router = APIRouter(tags=["market"])


@router.get("/api/market/observations")
def list_observations(request: Request) -> dict:
    """List market observations from the runtime DB.

    返回市场观测列表；DB 未配置时降级为空并告警（fail-closed）。

    Args:
        request: Incoming FastAPI request (used for row entitlement).

    Returns:
        Enveloped observation rows or an empty enveloped response.

    Raises:
        HTTPException: 503 ``runtime_db_unavailable`` on DB read failure.
    """

    if not _db_is_configured():
        return _env(
            [],
            source="runtime-db-not-configured",
            warnings=["Runtime DB is not configured; market observations are unavailable."],
        )

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = market_observations(session)
        return _env(
            _filter_entitled_rows(request, rows, source_key="source_system"),
            source="runtime-postgresql",
        )
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


@router.get("/api/market/fx")
def list_fx(request: Request) -> dict:
    """List ECB FX observations from the runtime DB.

    返回汇率观测列表；DB 未配置时降级为空并告警。

    Args:
        request: Incoming FastAPI request (unused except wiring).

    Returns:
        Enveloped FX rows or an empty enveloped response.

    Raises:
        HTTPException: 503 ``runtime_db_unavailable`` on DB read failure.
    """

    if not _db_is_configured():
        return _env(
            [],
            source="runtime-db-not-configured",
            warnings=["Runtime DB is not configured; ECB FX observations are unavailable."],
        )

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = fx_observations(session)
        return _env(rows, source="runtime-postgresql")
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


@router.get("/api/market/quotes")
def list_quotes(
    request: Request,
    hub: str | None = None,
    product: str | None = None,
    source_system: str | None = None,
    limit: int = Query(default=500, ge=1, le=2000),
) -> dict:
    """Return normalized L1 quotes from the runtime DB."""

    if not _db_is_configured():
        return _env(
            [],
            source="runtime-db-not-configured",
            warnings=["Runtime DB is not configured; market quotes are unavailable."],
        )
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = market_quotes(
                session,
                hub=hub,
                product=product,
                source_system=source_system,
                limit=limit,
            )
        return _env(
            _filter_entitled_rows(request, rows, source_key="source_system"),
            source="runtime-postgresql",
        )
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


@router.get("/api/market/opportunities")
def list_opportunities(
    request: Request,
    status: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    """Return backend-calculated intraday decision snapshots."""

    if not _db_is_configured():
        return _env(
            [],
            source="runtime-db-not-configured",
            warnings=["Runtime DB is not configured; intraday opportunities are unavailable."],
        )
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = intraday_opportunities(session, status=status, limit=limit)
        return _env(rows, source="runtime-postgresql")
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


@router.get("/api/market/normalized")
def list_normalized_view(
    request: Request,
    limit: int = Query(default=500, ge=1, le=2000),
) -> dict:
    """Return the backend-normalized market view (hub/tenor/FX->GBP per row)."""

    if not _db_is_configured():
        return _env(
            [],
            source="runtime-db-not-configured",
            warnings=["Runtime DB is not configured; normalized market view is unavailable."],
        )
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.session import get_session_factory

        identity = current_principal(request)
        with get_session_factory()() as session:
            view = normalized_market_view(
                session,
                limit=limit,
                source_filter=source_family_filter(identity),
            )
        return _env(
            view["rows"],
            source="runtime-postgresql",
            warnings=view["warnings"],
        )
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


@router.get("/api/market/spreads")
def list_spreads(request: Request) -> dict:
    """List intraday cross-hub spreads derived from runtime opportunities.

    返回由日内机会派生的跨枢纽价差（gross spread）；DB 未配置或未采集
    价格时降级为空并告警。

    Args:
        request: Incoming FastAPI request (unused except wiring).

    Returns:
        Enveloped spread rows or an empty enveloped response.

    Raises:
        HTTPException: 503 ``runtime_db_unavailable`` on DB read failure.
    """

    if not _db_is_configured():
        return _env(
            [],
            source="runtime-db-not-configured",
            warnings=["Spread calculation requires sourced prices in runtime DB."],
        )
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            opportunities = intraday_opportunities(session, limit=100)
        return _env(derive_intraday_spreads(opportunities), source="runtime-postgresql")
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _filter_entitled_rows(request: Request, rows: list[dict], *, source_key: str) -> list[dict]:
    """Apply row-level commercial entitlement to DB-identity callers.

    Legacy public-token deployments retain the single-trust-domain view. A
    DB-backed identity sees only rows whose source family is in its data
    scopes (public baseline families remain visible to all).

    The rule itself lives in the application layer
    (:func:`eurogas_nexus.application.projections.market_reads.filter_entitled_rows`)
    so the MarketContext projection applies exactly the same filter.
    """

    return filter_entitled_rows(current_principal(request), rows, source_key=source_key)


def _market_row(row):
    """Shape one market observation row (compatibility alias, see market_reads)."""

    return market_observation_row(row)


def _fx_row(row):
    """Shape one FX observation row (compatibility alias, see market_reads)."""

    return fx_observation_row(row)


def _fx_row_from_market_observation(row):
    """Shape one ECB market observation as FX (compatibility alias)."""

    return fx_row_from_market_observation(row)


def _db_is_configured() -> bool:
    from eurogas_nexus.db.session import resolve_database_url

    return resolve_database_url() is not None


def _sqlalchemy_error_type():
    from sqlalchemy.exc import SQLAlchemyError

    return SQLAlchemyError


def _db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "runtime_db_unavailable",
            "message": "Runtime database is configured but unavailable for market reads.",
            "error_class": exc.__class__.__name__,
        },
    )


def _env(data: object, *, source: str, warnings: list[str] | None = None) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": [source],
            "warnings": warnings or [],
        },
    }
