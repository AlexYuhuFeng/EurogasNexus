"""DB-first European route-cost and decision-support endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError

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
from eurogas_nexus.domain.route_cost.schemas import RouteCostScenario, RouteTariffLeg

router = APIRouter(tags=["route-cost"])


class UpstreamContractUpsertRequest(BaseModel):
    contract_id: str = Field(min_length=1, max_length=128)
    contract_name: str = Field(min_length=1, max_length=256)
    resource_type: str = Field(min_length=1, max_length=64)
    delivery_point_name: str = Field(min_length=1, max_length=256)
    gas_year: str = Field(min_length=1, max_length=16)
    delivery_quantity_mwh_per_day: float = Field(gt=0)
    contract_price_gbp_mwh: float = Field(ge=0)
    settlement_frequency: str = Field(min_length=1, max_length=32)
    upstream_payment_lag_days: int = Field(ge=0)
    screen_sale_cash_lag_days: int = Field(ge=0)
    delivery_tolerance_pct: float = Field(ge=0)
    nomination_tolerance_pct: float = Field(ge=0)
    tolerance_risk_allowance_gbp_mwh: float | None = Field(default=None, ge=0)
    annual_financing_rate_pct: float = Field(ge=0)
    owned_entry_capacity_mwh_per_day: float | None = Field(default=None, ge=0)
    owned_exit_capacity_mwh_per_day: float | None = Field(default=None, ge=0)
    allowed_exit_points: list[str] = Field(default_factory=list)
    eligible_sale_modes: list[str] = Field(default_factory=list)
    notes: str | None = None


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


@router.post("/api/route-cost/upstream-contracts")
def upsert_upstream_contract(body: UpstreamContractUpsertRequest, request: Request) -> dict:
    """Persist an upstream resource contract for decision-support workflows."""

    if not _db_is_configured():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "runtime_db_not_configured",
                "message": "Runtime DB is required to persist upstream resource contracts.",
            },
        )

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.repositories.route_cost import upsert_upstream_contract
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            contract = upsert_upstream_contract(session, body.model_dump(mode="json"))
            session.commit()
            data = {
                **contract,
                "research_only": True,
                "human_review_required": True,
            }
            return _env(data, request, source="runtime-postgresql")
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


@router.get("/api/route-cost/resource-pool/options")
def get_resource_pool_options(request: Request) -> dict:
    """Compose DB-backed portfolio resources and executable sale options.

    This endpoint is intentionally read-only. It exists so clients do not
    fabricate route options locally when the runtime DB is missing inputs.
    """

    if not _db_is_configured():
        data = {
            "scope": "RESOURCE_POOL_ROUTE_OPTIONS",
            "data_source": "runtime-db-not-configured",
            "portfolio_resources": [],
            "sale_options": [],
            "blockers": ["RUNTIME_DB_NOT_CONFIGURED"],
            "warnings": [],
        }
        return _env(
            data,
            request,
            source="runtime-db-not-configured",
            warnings=["Runtime DB is not configured; resource-pool options are unavailable."],
        )

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import MarketObservationRecord
        from eurogas_nexus.db.repositories.route_cost import (
            list_route_candidates,
            list_tso_tariffs,
            list_upstream_contracts,
        )
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            contracts = list_upstream_contracts(session)
            candidates = list_route_candidates(session)
            tariffs = list_tso_tariffs(session)
            market_rows = (
                session.query(MarketObservationRecord)
                .order_by(MarketObservationRecord.observed_at_utc.desc())
                .all()
            )

        data = _compose_resource_pool_options(
            contracts=contracts,
            candidates=candidates,
            tariffs=tariffs,
            market_rows=market_rows,
        )
        return _env(data, request, source="runtime-postgresql", warnings=data["warnings"])
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


def _compose_resource_pool_options(
    *,
    contracts: list[dict],
    candidates: list[dict],
    tariffs: list,
    market_rows: list,
) -> dict:
    blockers: list[str] = []
    warnings: list[str] = []
    if not contracts:
        blockers.append("UPSTREAM_CONTRACTS_MISSING")
    if not candidates:
        blockers.append("ROUTE_CANDIDATES_MISSING")

    price_by_point = _latest_market_price_by_point(market_rows)
    resources = [_portfolio_resource_from_contract(contract) for contract in contracts]
    sale_options = []
    allowed_targets = {
        point.strip().upper()
        for contract in contracts
        for point in [contract["delivery_point_name"], *contract.get("allowed_exit_points", [])]
        if isinstance(point, str) and point.strip()
    }
    resource_points = {
        contract["delivery_point_name"].strip().upper()
        for contract in contracts
        if isinstance(contract.get("delivery_point_name"), str)
    }

    for candidate in candidates:
        target = str(candidate["target_point_name"]).strip().upper()
        start = str(candidate["start_point_name"]).strip().upper()
        market_price = price_by_point.get(target)
        if market_price is None:
            blockers.append(f"MARKET_PRICE_MISSING:{target}")
            continue

        if contracts and start not in resource_points:
            warnings.append(f"ROUTE_START_NOT_IN_RESOURCE_POOL:{candidate['route_id']}")
            continue
        if contracts and allowed_targets and target not in allowed_targets:
            warnings.append(f"ROUTE_TARGET_NOT_ALLOWED_BY_CONTRACT:{candidate['route_id']}")
            continue

        route_cost, cost_warnings, cost_blockers = _candidate_route_cost(
            candidate,
            tariffs,
            price_currency=market_price["currency"],
            price_unit=market_price["unit"],
        )
        warnings.extend(cost_warnings)
        blockers.extend(cost_blockers)
        if cost_blockers:
            continue

        sale_options.append(
            {
                "option_id": candidate["route_id"],
                "label": candidate["route_name"],
                "delivery_mode": "VIRTUAL_HUB_SALE",
                "target_point_name": candidate["target_point_name"],
                "sale_price_gbp_mwh": market_price["price"],
                "sale_price_currency": market_price["currency"],
                "sale_price_unit": market_price["unit"],
                "route_cost_gbp_mwh": route_cost,
                "route_cost_currency": market_price["currency"],
                "route_cost_unit": market_price["unit"],
                "capacity_limit_mwh_per_day": _route_capacity_limit(candidate),
                "screen_sale_cash_lag_days": _screen_cash_lag_days(contracts),
                "required_tso_access": candidate["required_tso_access"],
                "source_refs": [
                    f"route_candidate:{candidate['route_id']}",
                    market_price["source_reference"],
                    *candidate.get("source_systems", []),
                ],
            }
        )

    return {
        "scope": "RESOURCE_POOL_ROUTE_OPTIONS",
        "data_source": "runtime-postgresql",
        "portfolio_resources": resources,
        "sale_options": sale_options,
        "blockers": _unique(blockers),
        "warnings": _unique(warnings),
    }


def _latest_market_price_by_point(market_rows: list) -> dict[str, dict]:
    prices: dict[str, dict] = {}
    for row in market_rows:
        keys = _market_price_keys(row)
        for key in keys:
            prices.setdefault(
                key,
                {
                    "price": row.price,
                    "currency": row.currency,
                    "unit": row.unit,
                    "source_reference": f"market_observation:{row.observation_id}",
                },
            )
    return prices


def _market_price_keys(row) -> list[str]:
    keys = [row.market_venue, row.product]
    metadata = row.metadata_json or {}
    for field in ("hub", "point_name", "market_area"):
        value = metadata.get(field)
        if isinstance(value, str):
            keys.append(value)
    return [value.strip().upper() for value in keys if isinstance(value, str) and value.strip()]


def _portfolio_resource_from_contract(contract: dict) -> dict:
    resource_type = contract["resource_type"]
    return {
        "resource_id": contract["contract_id"],
        "resource_name": contract["contract_name"],
        "resource_type": resource_type,
        "delivery_mode": (
            "TERMINAL_TITLE_TRANSFER"
            if resource_type == "LNG_REGAS"
            else "PHYSICAL_ENTRY_DELIVERY"
        ),
        "location_point_name": contract["delivery_point_name"],
        "available_quantity_mwh_per_day": contract["delivery_quantity_mwh_per_day"],
        "contract_cost_gbp_mwh": contract["contract_price_gbp_mwh"],
        "variable_cost_gbp_mwh": 0.0,
        "delivery_tolerance_pct": contract["delivery_tolerance_pct"],
        "nomination_tolerance_pct": contract["nomination_tolerance_pct"],
        "tolerance_risk_allowance_gbp_mwh": contract.get("tolerance_risk_allowance_gbp_mwh") or 0.0,
        "upstream_payment_lag_days": contract["upstream_payment_lag_days"],
        "settlement_frequency": contract["settlement_frequency"],
        "required_tso_access": [],
        "accessible_tsos": None,
        "pricing_method": "OPERATOR_CONTRACT",
        "source_refs": [f"upstream_resource_contract:{contract['contract_id']}"],
    }


def _candidate_route_cost(
    candidate: dict,
    tariffs: list,
    *,
    price_currency: str,
    price_unit: str,
) -> tuple[float, list[str], list[str]]:
    if not candidate["route_legs"]:
        return 0.0, [], []

    try:
        legs = [RouteTariffLeg.model_validate(leg) for leg in candidate["route_legs"]]
    except ValidationError:
        return 0.0, [], [f"ROUTE_LEG_INVALID:{candidate['route_id']}"]

    scenario = RouteCostScenario(
        scenario_id=f"resource-pool-options:{candidate['route_id']}",
        source_resource_type="PIPELINE_IMPORT",
        start_point_id=candidate["start_point_name"],
        target_hub_or_point_id=candidate["target_point_name"],
        business_model="CROSS_BORDER_TRANSFER",
        delivery_mode="BORDER_TRANSFER",
        gas_year=legs[0].gas_year or "2025+",
        capacity_product=legs[0].capacity_product or "ANNUAL",
        firmness=legs[0].firmness or "FIRM",
        required_tso_access=candidate["required_tso_access"],
        tariff_legs=legs,
    )
    result = calculate_route_cost(scenario, tariffs)
    blockers = [
        *[f"ROUTE_COST_MISSING:{candidate['route_id']}:{item}" for item in result.missing_inputs],
        *[
            f"ROUTE_COST_MISSING:{candidate['route_id']}:{warning}"
            for warning in result.warnings
            if warning == "UNIT_CONVERSION_NOT_IMPLEMENTED"
        ],
    ]
    if result.total_cost is None:
        blockers.append(f"ROUTE_COST_MISSING:{candidate['route_id']}")
        return 0.0, result.warnings, blockers
    if result.currency and result.currency != price_currency:
        blockers.append(f"ROUTE_COST_MISSING:{candidate['route_id']}:PRICE_COST_CURRENCY_MISMATCH")
    if result.unit and result.unit != price_unit:
        blockers.append(f"ROUTE_COST_MISSING:{candidate['route_id']}:PRICE_COST_UNIT_MISMATCH")
    return result.total_cost, result.warnings, blockers


def _route_capacity_limit(candidate: dict) -> float | None:
    capacities = [
        float(leg["available_capacity_mwh_per_day"])
        for leg in candidate.get("route_legs", [])
        if isinstance(leg, dict)
        and isinstance(leg.get("available_capacity_mwh_per_day"), int | float)
    ]
    return min(capacities) if capacities else None


def _screen_cash_lag_days(contracts: list[dict]) -> int:
    lags = [
        int(contract["screen_sale_cash_lag_days"])
        for contract in contracts
        if isinstance(contract.get("screen_sale_cash_lag_days"), int)
    ]
    return min(lags) if lags else 1


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


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
