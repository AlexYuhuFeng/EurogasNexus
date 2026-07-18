"""Read-only /api/market routes."""

from fastapi import APIRouter, HTTPException, Query, Request

router = APIRouter(tags=["market"])


@router.get("/api/market/observations")
def list_observations(request: Request) -> dict:
    observations = _db_market_observations()
    if observations is not None:
        return _env(observations, source="runtime-postgresql")

    return _env(
        [],
        source="runtime-db-not-configured",
        warnings=["Runtime DB is not configured; market observations are unavailable."],
    )


@router.get("/api/market/fx")
def list_fx(request: Request) -> dict:
    fx_rows = _db_fx_observations()
    if fx_rows is not None:
        return _env(fx_rows, source="runtime-postgresql")

    return _env(
        [],
        source="runtime-db-not-configured",
        warnings=["Runtime DB is not configured; ECB FX observations are unavailable."],
    )


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
        from eurogas_nexus.db.repositories.market_intelligence import list_market_quotes
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = list_market_quotes(
                session,
                hub=hub,
                product=product,
                source_system=source_system,
                limit=limit,
            )
        return _env(rows, source="runtime-postgresql")
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
        from eurogas_nexus.db.repositories.market_intelligence import (
            list_intraday_opportunities,
        )
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = list_intraday_opportunities(session, status=status, limit=limit)
        return _env(rows, source="runtime-postgresql")
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


@router.get("/api/market/spreads")
def list_spreads(request: Request) -> dict:
    if not _db_is_configured():
        return _env(
            [],
            source="runtime-db-not-configured",
            warnings=["Spread calculation requires sourced prices in runtime DB."],
        )
    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.repositories.market_intelligence import (
            list_intraday_opportunities,
        )
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            opportunities = list_intraday_opportunities(session, limit=100)
        rows = [
            {
                "spread_id": row["opportunity_id"],
                "name": f"{row['buy_hub']} -> {row['sell_hub']} {row['product']}",
                "from_venue": row["buy_venue"],
                "to_venue": row["sell_venue"],
                "spread_eur_mwh": row["gross_spread"],
                "period": row["product"],
            }
            for row in opportunities
        ]
        return _env(rows, source="runtime-postgresql")
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _db_market_observations() -> list[dict] | None:
    if not _db_is_configured():
        return None

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import MarketObservationRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = session.query(MarketObservationRecord).order_by(
                MarketObservationRecord.observed_at_utc.desc(),
                MarketObservationRecord.market_venue,
                MarketObservationRecord.product,
            )
            return [_market_row(row) for row in rows.all()]
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _db_fx_observations() -> list[dict] | None:
    if not _db_is_configured():
        return None

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import FxObservationRecord, MarketObservationRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = session.query(FxObservationRecord).order_by(
                FxObservationRecord.observed_at_utc.desc(),
                FxObservationRecord.pair,
            ).all()
            if rows:
                return [_fx_row(row) for row in rows]
            market_rows = session.query(MarketObservationRecord).filter(
                MarketObservationRecord.source_system == "ECB"
            ).order_by(MarketObservationRecord.observed_at_utc.desc())
            return [_fx_row_from_market_observation(row) for row in market_rows.all()]
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _market_row(row) -> dict:
    return {
        "observation_id": row.observation_id,
        "market_venue": row.market_venue,
        "product": row.product,
        "price": row.price,
        "unit": row.unit,
        "currency": row.currency,
        "period_start_utc": row.period_start_utc.isoformat(),
        "period_end_utc": row.period_end_utc.isoformat(),
        "observed_at_utc": row.observed_at_utc.isoformat(),
        "source_system": row.source_system,
        "source_reference": row.source_reference,
        "source_record_id": row.source_record_id,
        "freshness": row.freshness,
        "quality_score": row.quality_score,
        "research_only": row.research_only,
        "metadata_json": row.metadata_json or {},
    }


def _fx_row(row) -> dict:
    return {
        "observation_id": row.observation_id,
        "pair": row.pair,
        "base_currency": row.base_currency,
        "quote_currency": row.quote_currency,
        "rate": row.rate,
        "rate_type": row.rate_type,
        "value_date": row.value_date,
        "observed_at_utc": row.observed_at_utc.isoformat(),
        "source_system": row.source_system,
        "source_reference": row.source_reference,
        "freshness": row.freshness,
        "research_only": row.research_only,
    }


def _fx_row_from_market_observation(row) -> dict:
    quote = row.currency
    pair = row.product.replace("/", "")
    return {
        "observation_id": row.observation_id,
        "pair": pair,
        "base_currency": "EUR",
        "quote_currency": quote,
        "rate": row.price,
        "rate_type": "reference",
        "value_date": row.period_start_utc.date().isoformat(),
        "observed_at_utc": row.observed_at_utc.isoformat(),
        "source_system": row.source_system,
        "source_reference": row.source_reference,
        "freshness": row.freshness,
        "research_only": row.research_only,
    }


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
