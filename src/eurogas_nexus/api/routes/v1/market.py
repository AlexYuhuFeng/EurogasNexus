"""Read-only /api/v1/market routes."""

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["market"])


@router.get("/api/v1/market/observations")
def list_observations(request: Request) -> dict:
    observations = _db_market_observations()
    if observations is not None:
        return _env(observations, source="runtime-postgresql")

    return _env(_fixture_market_observations(), source="synthetic-fixture")


@router.get("/api/v1/market/fx")
def list_fx(request: Request) -> dict:
    fx_rows = _db_fx_observations()
    if fx_rows is not None:
        return _env(fx_rows, source="runtime-postgresql", synthetic=False)

    return _env(
        [
            {
                "pair": "EURUSD",
                "base_currency": "EUR",
                "quote_currency": "USD",
                "rate": 1.0850,
                "rate_type": "reference",
                "value_date": "2026-05-29",
                "observed_at_utc": "2026-05-29T12:00:00Z",
                "source_system": "ECB",
                "source_reference": "synthetic-ecb-fallback",
                "freshness": "synthetic",
            },
            {
                "pair": "EURGBP",
                "base_currency": "EUR",
                "quote_currency": "GBP",
                "rate": 0.8510,
                "rate_type": "reference",
                "value_date": "2026-05-29",
                "observed_at_utc": "2026-05-29T12:00:00Z",
                "source_system": "ECB",
                "source_reference": "synthetic-ecb-fallback",
                "freshness": "synthetic",
            },
        ],
        source="synthetic-fixture",
    )


@router.get("/api/v1/market/spreads")
def list_spreads(request: Request) -> dict:
    return _env(
        [
            {
                "spread_id": "spd-001",
                "name": "TTF-NBP",
                "from_venue": "TTF",
                "to_venue": "NBP",
                "spread_eur_mwh": 1.50,
                "period": "2026-06",
            },
            {
                "spread_id": "spd-002",
                "name": "TTF-PEG",
                "from_venue": "TTF",
                "to_venue": "PEG",
                "spread_eur_mwh": 0.80,
                "period": "2026-06",
            },
        ],
        source="synthetic-fixture",
    )


def _db_market_observations() -> list[dict] | None:
    if not _db_is_configured():
        return None

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import MarketObservationRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = session.query(MarketObservationRecord).order_by(
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
        "freshness": row.freshness,
        "quality_score": row.quality_score,
        "research_only": row.research_only,
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


def _fixture_market_observations() -> list[dict]:
    return [
        {
            "observation_id": "mkt-001",
            "market_venue": "TTF",
            "product": "month-ahead",
            "price": 42.50,
            "unit": "EUR/MWh",
            "currency": "EUR",
            "period_start_utc": "2026-06-01T00:00:00Z",
            "period_end_utc": "2026-07-01T00:00:00Z",
        },
        {
            "observation_id": "mkt-002",
            "market_venue": "NBP",
            "product": "day-ahead",
            "price": 105.20,
            "unit": "p/th",
            "currency": "GBP",
            "period_start_utc": "2026-05-30T06:00:00Z",
            "period_end_utc": "2026-05-31T06:00:00Z",
        },
        {
            "observation_id": "mkt-003",
            "market_venue": "PEG",
            "product": "month-ahead",
            "price": 41.00,
            "unit": "EUR/MWh",
            "currency": "EUR",
            "period_start_utc": "2026-06-01T00:00:00Z",
            "period_end_utc": "2026-07-01T00:00:00Z",
        },
    ]


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


def _env(data: object, *, source: str, synthetic: bool | None = None) -> dict:
    warnings = []
    if synthetic is not False:
        warnings.append("Synthetic data only. Do not use for commercial decisions.")
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": [source],
            "warnings": warnings,
        },
    }
