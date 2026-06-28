"""DB-first European route-cost and decision-support endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from eurogas_nexus.domain.route_cost.lng_regas import (
    LngRegasScenario,
    assess_lng_regas_readiness,
)
from eurogas_nexus.domain.route_cost.resource_pool import (
    PortfolioOptimizationScenario,
    optimize_resource_pool,
)
from eurogas_nexus.domain.route_cost.route_cost_service import calculate_route_cost
from eurogas_nexus.domain.route_cost.route_optimizer import (
    RouteRecommendationRequest,
    recommend_route_allocation,
)
from eurogas_nexus.domain.route_cost.schemas import RouteCostScenario

router = APIRouter(tags=["route-cost"])


@router.get("/api/route-cost/tso-tariffs")
def list_tso_tariffs(
    request: Request,
    country: str | None = None,
    tso: str | None = None,
    market_area: str | None = None,
    point_name: str | None = None,
    direction: str | None = None,
    gas_year: str | None = None,
) -> dict:
    """Return European TSO tariff rows available to the runtime."""

    tariffs, source, warnings = _load_tariffs()
    filtered = tariffs
    if country:
        filtered = [tariff for tariff in filtered if tariff.country.lower() == country.lower()]
    if tso:
        filtered = [tariff for tariff in filtered if tariff.tso.lower() == tso.lower()]
    if market_area:
        filtered = [
            tariff for tariff in filtered if tariff.market_area.lower() == market_area.lower()
        ]
    if point_name:
        filtered = [
            tariff
            for tariff in filtered
            if tariff.source_point_name.lower() == point_name.lower()
        ]
    if direction:
        filtered = [
            tariff
            for tariff in filtered
            if tariff.direction.value.lower() == direction.lower()
        ]
    if gas_year:
        filtered = [tariff for tariff in filtered if tariff.gas_year == gas_year]
    return _env(
        {
            "scope": "EUROPEAN_TSO_TARIFFS",
            "data_source": source,
            "tariffs": [tariff.model_dump(mode="json") for tariff in filtered],
        },
        request,
        source=source,
        warnings=warnings,
    )


@router.get("/api/route-cost/route-candidates")
def list_route_candidates(request: Request) -> dict:
    """List available route candidates from the runtime DB."""

    candidates, source, warnings = _load_route_candidates()
    return _env(
        {
            "scope": "EUROPEAN_ROUTE_CANDIDATES",
            "data_source": source,
            "route_candidates": candidates,
        },
        request,
        source=source,
        warnings=warnings,
    )


@router.get("/api/route-cost/upstream-contracts")
def list_upstream_contracts(request: Request) -> dict:
    """List DB-backed upstream resource contracts."""

    if not _db_is_configured():
        return _env(
            [],
            request,
            source="runtime-db-not-configured",
            warnings=["No runtime DB configured; upstream contracts are unavailable."],
        )

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.repositories.route_cost import list_upstream_contracts
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            return _env(list_upstream_contracts(session), request, source="runtime-postgresql")
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


@router.post("/api/route-cost/calculate")
def post_route_cost_calculation(body: RouteCostScenario, request: Request) -> dict:
    """Calculate a European explicit-leg route-cost scenario."""

    tariffs, source, warnings = _load_tariffs()
    calculation = calculate_route_cost(body, tariffs)
    return _env(
        calculation.model_dump(mode="json"),
        request,
        source=source,
        warnings=[*warnings, *calculation.warnings],
    )


@router.post("/api/route-cost/recommend")
def post_route_recommendation(body: RouteRecommendationRequest, request: Request) -> dict:
    """Recommend route and sale-market allocation using runtime tariff rows."""

    tariffs, source, warnings = _load_tariffs()
    recommendation = recommend_route_allocation(body, tariffs)
    return _env(
        recommendation.model_dump(mode="json"),
        request,
        source=source,
        warnings=[*warnings, *recommendation.warnings],
    )


@router.post("/api/route-cost/lng-regas/assess")
def post_lng_regas_assessment(body: LngRegasScenario, request: Request) -> dict:
    """Assess LNG regas terminal access, slot, delivery mode, and pricing readiness."""

    result = assess_lng_regas_readiness(body)
    return _env(
        result.model_dump(mode="json"),
        request,
        source="operator-input",
        warnings=result.warnings,
    )


@router.post("/api/route-cost/resource-pool/optimize")
def post_resource_pool_optimization(
    body: PortfolioOptimizationScenario,
    request: Request,
) -> dict:
    """Optimize multi-upstream resource-pool allocation across selling options."""

    result = optimize_resource_pool(body)
    return _env(
        result.model_dump(mode="json"),
        request,
        source="operator-input",
        warnings=result.warnings,
    )


def _load_tariffs():
    if not _db_is_configured():
        return (
            [],
            "runtime-db-not-configured",
            ["No runtime DB configured; European TSO tariff rows are unavailable."],
        )

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.repositories.route_cost import list_tso_tariffs
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            return list_tso_tariffs(session), "runtime-postgresql", []
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _load_route_candidates() -> tuple[list[dict], str, list[str]]:
    if not _db_is_configured():
        return (
            [],
            "runtime-db-not-configured",
            ["No runtime DB configured; route candidates are unavailable."],
        )

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.repositories.route_cost import list_route_candidates
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            return list_route_candidates(session), "runtime-postgresql", []
    except sqlalchemy_error as exc:
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
            "message": "Runtime database is configured but unavailable for route-cost reads.",
            "error_class": exc.__class__.__name__,
        },
    )


def _env(
    data: object,
    _request: Request,
    *,
    source: str,
    warnings: list[str] | None = None,
) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": [source],
            "warnings": list(dict.fromkeys(warnings or [])),
        },
    }
