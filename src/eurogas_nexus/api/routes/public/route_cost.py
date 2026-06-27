"""DB-first route-cost and contract decision-support endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from eurogas_nexus.domain.route_cost.contract_economics import (
    EasingtonContractScenario,
    compare_easington_contract_options,
)
from eurogas_nexus.domain.route_cost.live_markets import (
    LiveMarketMark,
    LiveOptionMarkResult,
    mark_option_to_live_market,
)
from eurogas_nexus.domain.route_cost.lng_regas import (
    LngRegasScenario,
    assess_lng_regas_readiness,
)
from eurogas_nexus.domain.route_cost.resource_pool import (
    PortfolioOptimizationScenario,
    optimize_resource_pool,
)
from eurogas_nexus.domain.route_cost.route_cost_service import calculate_route_cost
from eurogas_nexus.domain.route_cost.schemas import RouteCostScenario
from eurogas_nexus.domain.route_cost.uk_rules import (
    UK_ROUTE_COST_SCOPE,
    is_supported_uk_scenario,
)

router = APIRouter(tags=["route-cost"])


class EasingtonLivePnlRequest(BaseModel):
    contract: EasingtonContractScenario
    marks: list[LiveMarketMark] = Field(default_factory=list)


@router.get("/api/route-cost/uk/tariffs/easington")
def list_uk_easington_tariffs(request: Request) -> dict:
    """Return the runtime DB Easington tariff subset when tariff rows are loaded."""

    tariffs, source, warnings = _load_tariffs()
    easington_tariffs = [
        tariff for tariff in tariffs if tariff.source_point_name == "Easington Beach Terminal"
    ]
    return _env(
        {
            "scope": UK_ROUTE_COST_SCOPE,
            "data_source": source,
            "tariffs": [tariff.model_dump(mode="json") for tariff in easington_tariffs],
        },
        request,
        source=source,
        warnings=warnings,
    )


@router.get("/api/route-cost/uk/tariffs")
def list_uk_nts_tariffs(
    request: Request,
    point_name: str | None = None,
    direction: str | None = None,
    gas_year: str | None = None,
) -> dict:
    """Return UK National Gas NTS tariff rows available to the runtime."""

    tariffs, source, warnings = _load_tariffs()
    filtered = tariffs
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
            "scope": UK_ROUTE_COST_SCOPE,
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
        {"scope": UK_ROUTE_COST_SCOPE, "data_source": source, "route_candidates": candidates},
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


@router.post("/api/route-cost/upstream-contracts/easington")
def save_easington_contract(body: EasingtonContractScenario, request: Request) -> dict:
    """Create or update an Easington upstream resource contract profile."""

    if not _db_is_configured():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "runtime_db_not_configured",
                "message": "Runtime DB is required to persist upstream contracts.",
            },
        )

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.repositories.route_cost import upsert_upstream_contract
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            upsert_upstream_contract(session, body)
            session.commit()
        return _env(body.model_dump(mode="json"), request, source="runtime-postgresql")
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


@router.post("/api/route-cost/calculate")
def post_route_cost_calculation(body: RouteCostScenario, request: Request) -> dict:
    """Calculate a UK National Gas NTS route-cost scenario."""

    if not is_supported_uk_scenario(body):
        raise HTTPException(
            status_code=400,
            detail="V1 route-cost calculation is restricted to UK National Gas NTS "
            "scenarios with DB tariff rows for the requested entry/exit points.",
        )
    tariffs, source, warnings = _load_tariffs()
    calculation = calculate_route_cost(body, tariffs)
    return _env(
        calculation.model_dump(mode="json"),
        request,
        source=source,
        warnings=[*warnings, *calculation.warnings],
    )


@router.post("/api/route-cost/uk/easington/options")
def post_easington_contract_options(
    body: EasingtonContractScenario,
    request: Request,
) -> dict:
    """Compare Easington contract selling options and route economics."""

    tariffs, source, warnings = _load_tariffs()
    _persist_contract_if_db(body)
    result = compare_easington_contract_options(body, tariffs)
    return _env(
        result.model_dump(mode="json"),
        request,
        source=source,
        warnings=[*warnings, *result.warnings],
    )


@router.post("/api/route-cost/uk/easington/live-pnl")
def post_easington_live_pnl(body: EasingtonLivePnlRequest, request: Request) -> dict:
    """Mark Easington contract options to live ICE OCM/EEX style bid/ask marks."""

    tariffs, source, warnings = _load_tariffs()
    contract_result = compare_easington_contract_options(body.contract, tariffs)
    live_results: list[LiveOptionMarkResult] = []
    marks = body.marks or _load_live_marks()[0]
    for option in contract_result.options:
        matching_marks = [
            mark for mark in marks if mark.hub.upper() in {"NBP", "UK NBP"}
        ]
        for mark in matching_marks:
            live_results.append(
                mark_option_to_live_market(
                    option,
                    mark,
                    delivery_quantity_mwh_per_day=body.contract.delivery_quantity_mwh_per_day,
                )
            )

    return _env(
        {
            **contract_result.model_dump(mode="json"),
            "live_marks": [result.model_dump(mode="json") for result in live_results],
        },
        request,
        source=source,
        warnings=[*warnings, *contract_result.warnings],
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
            ["No runtime DB configured; UK tariff rows are unavailable."],
        )

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.repositories.route_cost import list_tso_tariffs
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            return list_tso_tariffs(session), "runtime-postgresql", []
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _load_live_marks() -> tuple[list[LiveMarketMark], str, list[str]]:
    if not _db_is_configured():
        return (
            [],
            "runtime-db-not-configured",
            ["No runtime DB configured; live market marks are unavailable."],
        )

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.repositories.route_cost import latest_market_marks
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            return latest_market_marks(session), "runtime-postgresql", []
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


def _persist_contract_if_db(body: EasingtonContractScenario) -> None:
    if not _db_is_configured():
        return

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.repositories.route_cost import upsert_upstream_contract
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            upsert_upstream_contract(session, body)
            session.commit()
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
