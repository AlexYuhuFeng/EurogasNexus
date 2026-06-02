"""Internal operator routes for governed market-positioning imports."""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request

from eurogas_nexus.domain.market_positioning_import import MarketPositioningImportBatch
from eurogas_nexus.security.internal_api import (
    InternalApiAuthError,
    validate_internal_operator_headers,
)

router = APIRouter(prefix="/portfolio", tags=["internal-portfolio-import"])


@router.post("/import-observations")
def import_market_positioning_observations(
    body: MarketPositioningImportBatch,
    request: Request,
    x_eurogas_principal: str | None = Header(default=None, alias="X-Eurogas-Principal"),
    x_eurogas_internal_token: str | None = Header(
        default=None,
        alias="X-Eurogas-Internal-Token",
    ),
) -> dict:
    """Import external order/PnL observations into PostgreSQL-backed runtime tables."""

    try:
        principal = validate_internal_operator_headers(
            token=x_eurogas_internal_token,
            principal=x_eurogas_principal,
        )
    except InternalApiAuthError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    if not _db_is_configured():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "runtime_db_required",
                "message": "RUNTIME_STORE_DATABASE_URL is required for internal imports.",
            },
        )

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.repositories.market_positioning_import import (
            upsert_market_positioning_import_batch,
        )
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            result = upsert_market_positioning_import_batch(
                session,
                body,
                principal=principal,
            )
        return _env(result.model_dump(mode="json"), request, warnings=result.warnings)
    except sqlalchemy_error as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "runtime_db_unavailable",
                "message": "Runtime database is unavailable for internal imports.",
                "error_class": exc.__class__.__name__,
            },
        ) from exc


def _db_is_configured() -> bool:
    from eurogas_nexus.db.session import resolve_database_url

    return resolve_database_url() is not None


def _sqlalchemy_error_type():
    from sqlalchemy.exc import SQLAlchemyError

    return SQLAlchemyError


def _env(data: object, _request: Request, warnings: list[str]) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["runtime-postgresql"],
            "warnings": list(dict.fromkeys(warnings)),
        },
    }
