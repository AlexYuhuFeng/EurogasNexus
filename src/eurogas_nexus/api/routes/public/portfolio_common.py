"""Request helpers shared by the portfolio, risk and position reads.

Envelope, database availability, the caller's identity and the caller's screen orders and
P&L snapshots, with one error shape for every portfolio read.
"""

from __future__ import annotations

from fastapi import HTTPException, Request

from eurogas_nexus.application.projections.market_reads import runtime_db_configured
from eurogas_nexus.application.projections.portfolio_reads import pnl_snapshots, screen_orders
from eurogas_nexus.domain.market_positioning import PortfolioPnlSnapshot, ScreenOrderObservation


def load_screen_orders(
    principal_id: str | None = None,
) -> tuple[list[ScreenOrderObservation], str, list[str]]:
    if not db_is_configured():
        return (
            [],
            "runtime-db-not-configured",
            ["RUNTIME_DB_NOT_CONFIGURED"],
        )

    sqlalchemy_error = sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            return screen_orders(session, principal_id=principal_id), "runtime-postgresql", []
    except sqlalchemy_error as exc:
        raise db_unavailable(exc) from exc


def load_pnl_snapshots(
    principal_id: str | None = None,
) -> tuple[list[PortfolioPnlSnapshot], str, list[str]]:
    if not db_is_configured():
        return (
            [],
            "runtime-db-not-configured",
            ["RUNTIME_DB_NOT_CONFIGURED"],
        )

    sqlalchemy_error = sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            return pnl_snapshots(session, principal_id=principal_id), "runtime-postgresql", []
    except sqlalchemy_error as exc:
        raise db_unavailable(exc) from exc


def identity_id(request: Request) -> str | None:
    return getattr(getattr(request.state, "identity", None), "principal_id", None)


def db_is_configured() -> bool:
    return runtime_db_configured()


def sqlalchemy_error_type():
    from sqlalchemy.exc import SQLAlchemyError

    return SQLAlchemyError


def db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "runtimedb_unavailable",
            "message": "Runtime database is configured but unavailable for portfolio reads.",
            "error_class": exc.__class__.__name__,
        },
    )


def env(data: object, _request: Request, source: str, warnings: list[str]) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": [source],
            "warnings": list(dict.fromkeys(warnings)),
        },
    }
