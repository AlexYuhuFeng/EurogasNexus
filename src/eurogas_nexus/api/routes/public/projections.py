"""Application projection routes (Architecture V2 Wave 5).

Read-only coherent read models under ``/api/projections/...``. They exist so a
client renders one application-layer payload instead of reconstructing critical
commercial state from many low-level endpoints with mixed timestamps
(``02_ARCHITECTURE_CONSTITUTION.md`` rules 34-35,
``03_TARGET_PLATFORM_ARCHITECTURE.md`` section 4).

- ``GET /api/projections/market-context`` - MarketContext.
- ``GET /api/projections/portfolio-snapshot`` - PortfolioSnapshot.
- ``GET /api/projections/review-context`` - ReviewContext.
- ``GET /api/projections/scenario-context`` - ScenarioContext.

Conventions kept deliberately identical to the existing public reads:

- the ``{"data": ..., "meta": {...}}`` envelope, with ``research_only``,
  ``human_review_required``, ``source_references`` and ``warnings`` plus the
  projection's own ``as_of_utc``, ``time_basis`` and ``table_lineage``;
- a runtime database that is configured but unreadable raises the existing
  ``503 runtime_db_unavailable``; an unconfigured runtime degrades to explicit
  ``MISSING`` freshness instead of a fabricated zero;
- commercial entitlement is applied by the application layer with the same
  fail-closed helpers the underlying routes use, so a projection is never wider
  than the endpoint it composes (see each projection module for the exact record
  it reports per slice).

This module mounts no router and changes no app factory; registration and the
permission declaration are applied by the integrator.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Query, Request

from eurogas_nexus.api.dependencies.row_entitlement import current_principal
from eurogas_nexus.application.projections import (
    GasDayInputError,
    build_market_context,
    build_portfolio_snapshot,
    build_review_context,
    build_scenario_context,
)

if TYPE_CHECKING:  # pragma: no cover - import boundary: importing the API must not
    # load SQLAlchemy (tests/contract/test_db_foundation.py).
    from sqlalchemy.orm import Session

router = APIRouter(tags=["projections"])

#: Maximum rows any projection slice may return (mirrors the read-endpoint caps).
MAX_SLICE_ROWS = 2000


@router.get("/api/projections/market-context")
def market_context(
    request: Request,
    gas_day: str | None = Query(default=None, description="ISO gas day (YYYY-MM-DD)."),
    delivery_product: str | None = Query(default=None),
    hub: str | None = Query(default=None),
    as_of_utc: datetime | None = Query(default=None),
    opportunity_status: str | None = Query(default=None),
    alert_status: str | None = Query(default=None),
    observation_limit: int = Query(default=500, ge=1, le=MAX_SLICE_ROWS),
    quote_limit: int = Query(default=500, ge=1, le=MAX_SLICE_ROWS),
    opportunity_limit: int = Query(default=100, ge=1, le=500),
    alert_limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    """Return the MarketContext projection for the calling principal.

    Returns:
        Enveloped payload whose ``data.slices`` carries the market observations,
        the normalized quote view, quotes, intraday opportunities, derived
        spreads, the monitoring summary/alerts and the data-source
        freshness/provenance summary - all on one time basis and one as-of.

    Raises:
        HTTPException: 422 ``gas_day_invalid`` for a malformed gas day; 503
            ``runtime_db_unavailable`` when the runtime database is configured but
            a read fails.
    """

    return _read(
        lambda session: build_market_context(
            current_principal(request),
            session=session,
            gas_day=gas_day,
            delivery_product=delivery_product,
            hub=hub,
            as_of_utc=as_of_utc,
            opportunity_status=opportunity_status,
            alert_status=alert_status,
            observation_limit=observation_limit,
            quote_limit=quote_limit,
            opportunity_limit=opportunity_limit,
            alert_limit=alert_limit,
        )
    )


@router.get("/api/projections/portfolio-snapshot")
def portfolio_snapshot(
    request: Request,
    portfolio_id: str | None = Query(default=None),
    gas_day: str | None = Query(default=None, description="ISO gas day (YYYY-MM-DD)."),
    delivery_product: str | None = Query(default=None),
    hub: str | None = Query(default=None),
    as_of_utc: datetime | None = Query(default=None),
    order_limit: int = Query(default=500, ge=1, le=MAX_SLICE_ROWS),
    snapshot_limit: int = Query(default=500, ge=1, le=MAX_SLICE_ROWS),
    contract_limit: int = Query(default=200, ge=1, le=MAX_SLICE_ROWS),
) -> dict:
    """Return the PortfolioSnapshot projection for the calling principal.

    Returns:
        Enveloped payload whose ``data.slices`` carries the portfolio summary,
        the screen orders, the PnL snapshots, the upstream contract context, the
        declared resource-pool follow-up and the per-slice freshness.

    Raises:
        HTTPException: 422 ``gas_day_invalid`` for a malformed gas day; 503
            ``runtime_db_unavailable`` when the runtime database is configured but
            a read fails.
    """

    return _read(
        lambda session: build_portfolio_snapshot(
            current_principal(request),
            session=session,
            portfolio_id=portfolio_id,
            gas_day=gas_day,
            delivery_product=delivery_product,
            hub=hub,
            as_of_utc=as_of_utc,
            order_limit=order_limit,
            snapshot_limit=snapshot_limit,
            contract_limit=contract_limit,
        )
    )


@router.get("/api/projections/review-context")
def review_context(
    request: Request,
    entity_type: str | None = Query(default=None),
    entity_id: str | None = Query(default=None),
    gas_day: str | None = Query(default=None, description="ISO gas day (YYYY-MM-DD)."),
    delivery_product: str | None = Query(default=None),
    hub: str | None = Query(default=None),
    as_of_utc: datetime | None = Query(default=None),
    decision_limit: int = Query(default=100, ge=1, le=500),
    evidence_limit: int = Query(default=20, ge=1, le=100),
) -> dict:
    """Return the ReviewContext projection for the calling principal.

    Returns:
        Enveloped payload whose ``data.slices`` carries the review decisions, the
        resolved review evidence (one resolver per review entity type), the
        monitoring posture and the review warnings. Evidence that cannot be
        retrieved is reported as an explicit unknown.

    Raises:
        HTTPException: 422 ``gas_day_invalid`` for a malformed gas day; 503
            ``runtime_db_unavailable`` when the runtime database is configured but
            a read fails.
    """

    return _read(
        lambda session: build_review_context(
            current_principal(request),
            session=session,
            entity_type=entity_type,
            entity_id=entity_id,
            gas_day=gas_day,
            delivery_product=delivery_product,
            hub=hub,
            as_of_utc=as_of_utc,
            decision_limit=decision_limit,
            evidence_limit=evidence_limit,
        )
    )


@router.get("/api/projections/scenario-context")
def scenario_context(
    request: Request,
    gas_day: str | None = Query(default=None, description="ISO gas day (YYYY-MM-DD)."),
    delivery_product: str | None = Query(default=None),
    hub: str | None = Query(default=None),
    as_of_utc: datetime | None = Query(default=None),
    country: str | None = Query(default=None),
    tso: str | None = Query(default=None),
    market_area: str | None = Query(default=None),
    tariff_limit: int = Query(default=200, ge=1, le=MAX_SLICE_ROWS),
    candidate_limit: int = Query(default=200, ge=1, le=MAX_SLICE_ROWS),
    contract_limit: int = Query(default=200, ge=1, le=MAX_SLICE_ROWS),
) -> dict:
    """Return the ScenarioContext projection for the calling principal.

    Returns:
        Enveloped payload whose ``data.slices`` carries the entitled route
        candidates, the TSO tariff context and the upstream contracts, plus
        ``data.not_included`` naming every scenario input a read model must not
        synthesise.

    Raises:
        HTTPException: 422 ``gas_day_invalid`` for a malformed gas day; 503
            ``runtime_db_unavailable`` when the runtime database is configured but
            a read fails.
    """

    return _read(
        lambda session: build_scenario_context(
            current_principal(request),
            session=session,
            gas_day=gas_day,
            delivery_product=delivery_product,
            hub=hub,
            as_of_utc=as_of_utc,
            country=country,
            tso=tso,
            market_area=market_area,
            tariff_limit=tariff_limit,
            candidate_limit=candidate_limit,
            contract_limit=contract_limit,
        )
    )


def _read(builder: Callable[[Session | None], dict]) -> dict:
    """Run one projection builder with the runtime session its reads need.

    An unconfigured runtime database is passed through as ``session=None`` so the
    projection reports explicit unknowns; a configured but unreadable database
    raises the runtime read error the other public read routes raise.
    """

    try:
        if not _db_is_configured():
            return builder(None)
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            return builder(session)
    except GasDayInputError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "gas_day_invalid", "message": str(exc)},
        ) from exc
    except _sqlalchemy_error_type() as exc:
        raise _db_unavailable(exc) from exc


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
            "message": "Runtime database is configured but unavailable for projection reads.",
            "error_class": exc.__class__.__name__,
        },
    )
