"""Read-only /api/market routes.

The loading and shaping code for every slice lives in
``eurogas_nexus.application.projections.market_reads`` so the Wave 5
MarketContext projection composes exactly these reads instead of re-implementing
them. This module keeps the HTTP concerns: the runtime-database guard, the
``503 runtime_db_unavailable`` translation and the response envelope. Every
response field of every endpoint below is unchanged.
"""

from datetime import UTC, date, datetime

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
from eurogas_nexus.domain.market.products import (
    ProductCodeError,
    resolve_product,
    standard_strip,
)
from eurogas_nexus.domain.market.units import (
    ENERGY_UNITS_PER_MWH,
    PRICE_UNITS,
    UnitConversionError,
    canonical_price_unit,
    convert_price,
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


@router.get("/api/market/products")
def list_products(
    trade_date: date | None = None,
    code: list[str] | None = Query(default=None, max_length=32),
) -> dict:
    """Resolve gas product codes (DA, WE, BOM, M+1, Q+1, Sum-27, Cal-27...) to delivery.

    Without ``code`` the standard desk strip is returned. Pure calendar logic; no DB.
    无 code 参数时返回标准交易曲线条（WD→Cal+1）；纯日历计算，不读数据库。

    Raises:
        HTTPException: 422 ``unknown_product_code`` for an unknown/expired code.
    """

    anchor = trade_date or datetime.now(UTC).date()
    if not code:
        periods = standard_strip(anchor)
    else:
        try:
            periods = [resolve_product(item, anchor) for item in code]
        except ProductCodeError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "unknown_product_code", "message": str(exc)},
            ) from exc
    return _env(
        {"trade_date": anchor.isoformat(), "products": [p.as_dict() for p in periods]},
        source="gas-product-calendar",
        warnings=["Exchange holiday calendars are not applied to DA."],
    )


@router.get("/api/market/price-conversion")
def convert_market_price(
    value: float = Query(..., allow_inf_nan=False),
    from_unit: str = Query(..., max_length=16),
    to_unit: str | None = Query(default=None, max_length=16),
    gbp_per_eur: float | None = Query(default=None, gt=0),
    usd_per_eur: float | None = Query(default=None, gt=0),
) -> dict:
    """Convert a gas price between EUR/MWh, GBp/th, USD/MMBtu and related quotations.

    FX is the explicit ``*_per_eur`` override when given, otherwise the latest ECB
    EUR-based rate in the runtime DB; the rates used are returned with their source.
    汇率优先使用显式参数，否则取数据库最新 ECB 汇率，并回传所用汇率及来源。

    Raises:
        HTTPException: 422 ``unsupported_price_unit`` / ``fx_rate_unavailable``.
    """

    rates: dict[str, dict[str, object]] = {}
    if gbp_per_eur is not None:
        rates["GBP"] = {"rate": gbp_per_eur, "source": "request"}
    if usd_per_eur is not None:
        rates["USD"] = {"rate": usd_per_eur, "source": "request"}
    if len(rates) < 2 and _db_is_configured():
        rates = {**_latest_eur_rates(), **rates}
    targets = [to_unit] if to_unit else list(PRICE_UNITS)
    eur_rates = {currency: float(entry["rate"]) for currency, entry in rates.items()}
    converted: dict[str, float | None] = {}
    try:
        source_unit = canonical_price_unit(from_unit)
        for target in targets:
            try:
                converted[canonical_price_unit(target)] = convert_price(
                    value, source_unit, target, eur_rates=eur_rates
                )
            except UnitConversionError:
                if to_unit:
                    raise
                converted[canonical_price_unit(target)] = None
    except UnitConversionError as exc:
        code = "fx_rate_unavailable" if "FX" in str(exc) else "unsupported_price_unit"
        raise HTTPException(status_code=422, detail={"code": code, "message": str(exc)}) from exc
    return _env(
        {
            "value": value,
            "from_unit": source_unit,
            "converted": converted,
            "fx": rates,
            "factors": {"therm_per_mwh": ENERGY_UNITS_PER_MWH["therm"],
                        "mmbtu_per_mwh": ENERGY_UNITS_PER_MWH["MMBtu"]},
        },
        source="gas-unit-conversion",
        warnings=[] if len(rates) == 2 else ["Some FX rates are unavailable; null values."],
    )


def _latest_eur_rates() -> dict[str, dict[str, object]]:
    """Latest EUR-based GBP/USD rates from the runtime DB, newest first."""

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = fx_observations(session)
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc
    found: dict[str, dict[str, object]] = {}
    for row in rows:
        pair = str(row.get("pair") or "").upper()
        base = str(row.get("base_currency") or pair[:3]).upper()
        quote = str(row.get("quote_currency") or pair[3:6]).upper()
        rate = row.get("rate")
        if base != "EUR" or quote not in ("GBP", "USD") or quote in found:
            continue
        if isinstance(rate, (int, float)) and rate > 0:
            found[quote] = {
                "rate": float(rate),
                "source": row.get("source_system"),
                "observed_at_utc": row.get("observed_at_utc"),
            }
    return found


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
