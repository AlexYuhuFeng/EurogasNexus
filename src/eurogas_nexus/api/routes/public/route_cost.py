"""DB-first European route-cost and decision-support endpoints."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError

from eurogas_nexus.domain.route_cost.enums import SourceResourceType
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
    """Upsert payload for one operator-owned upstream resource contract.

    Attributes:
        contract_id: Stable contract id (1-128 chars).
        contract_name: Contract display name.
        resource_type: Resource type tag (e.g. ``BEACH_DELIVERY``).
        delivery_point_name: Delivery point name.
        gas_year: Contract gas year.
        delivery_quantity_mwh_per_day: Daily volume (positive).
        contract_price_gbp_mwh: All-in contract price per MWh.
        settlement_frequency: Settlement frequency tag.
        upstream_payment_lag_days: Upstream payment lag (days).
        screen_sale_cash_lag_days: Screen-sale cash lag (days).
        delivery_tolerance_pct / nomination_tolerance_pct: Tolerances.
        tolerance_risk_allowance_gbp_mwh: Risk allowance, or None.
        annual_financing_rate_pct: Financing rate for early-cash value.
        owned_entry_capacity_mwh_per_day / owned_exit_capacity_mwh_per_day:
            Owned capacity, or None.
        allowed_exit_points: Allowed exit points.
        eligible_sale_modes: Eligible sale modes.
        notes: Operator notes, or None.
    """

    contract_id: str = Field(min_length=1, max_length=128)
    contract_name: str = Field(min_length=1, max_length=256)
    resource_type: SourceResourceType
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
    variable_cost_gbp_mwh: float = Field(default=0, ge=0)
    regas_fee_gbp_mwh: float = Field(default=0, ge=0)
    fuel_loss_allowance_pct: float = Field(default=0, ge=0, lt=100)
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
        from eurogas_nexus.db.models import (
            CompanyTsoAccessRecord,
            FxObservationRecord,
        )
        from eurogas_nexus.db.repositories.market_intelligence import (
            list_market_observations_with_source_coverage,
        )
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
            market_rows = list_market_observations_with_source_coverage(
                session,
                limit=2000,
            )
            fx_rows = (
                session.query(FxObservationRecord)
                .order_by(FxObservationRecord.observed_at_utc.desc())
                .all()
            )
            access_rows = (
                session.query(CompanyTsoAccessRecord)
                .order_by(CompanyTsoAccessRecord.tso)
                .all()
            )

        data = _compose_resource_pool_options(
            contracts=contracts,
            candidates=candidates,
            tariffs=tariffs,
            market_rows=market_rows,
            fx_rows=fx_rows,
            company_accessible_tsos=_active_company_tsos(access_rows),
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
    fx_rows: list,
    company_accessible_tsos: list[str] | None = None,
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
    for candidate in candidates:
        target = str(candidate["target_point_name"]).strip().upper()
        start = str(candidate["start_point_name"]).strip().upper()
        route_topology_kind = _route_topology_kind(candidate)
        market_price = price_by_point.get(target)
        if market_price is None:
            blockers.append(f"MARKET_PRICE_MISSING:{target}")
            continue

        start_contracts = [
            contract
            for contract in contracts
            if str(contract.get("delivery_point_name") or "").strip().upper() == start
        ]
        if contracts and not start_contracts:
            warnings.append(f"ROUTE_START_NOT_IN_RESOURCE_POOL:{candidate['route_id']}")
            continue
        eligible_contracts = [
            contract
            for contract in start_contracts
            if target == start
            or target
            in {
                str(point).strip().upper()
                for point in contract.get("allowed_exit_points", [])
                if str(point).strip()
            }
        ]
        if contracts and not eligible_contracts:
            warnings.append(f"ROUTE_TARGET_NOT_ALLOWED_BY_CONTRACT:{candidate['route_id']}")
            continue

        route_cost, cost_currency, cost_unit, cost_warnings, cost_blockers = (
            _candidate_route_cost(
                candidate,
                tariffs,
                price_currency=market_price["currency"],
                price_unit=market_price["unit"],
                company_accessible_tsos=company_accessible_tsos,
            )
        )
        warnings.extend(cost_warnings)
        blockers.extend(cost_blockers)
        if cost_blockers:
            continue

        capacity_limit = _route_capacity_limit(candidate)
        is_cross_zone = (
            str(candidate.get("business_model") or "").upper()
            in {"CROSS_BORDER_TRANSFER", "BORDER_TRANSFER"}
            or start != target
        )
        if capacity_limit is None and is_cross_zone:
            # Cross-zone route with no known capacity: fail closed. Only a
            # same-point sale (NOT_REQUIRED) may proceed without capacity.
            blockers.append(f"ROUTE_CAPACITY_UNKNOWN:{candidate['route_id']}")
            continue
        capacity_status = "KNOWN" if capacity_limit is not None else "NOT_REQUIRED"

        observed_at_iso = market_price["observed_at_utc"]
        asof_date = _date_from_iso(observed_at_iso)

        sale_price_gbp, sale_fx_info, sale_fx_warning = _value_in_gbp(
            market_price["price"],
            market_price["currency"],
            market_price["unit"],
            asof_date,
            fx_rows,
        )
        if sale_price_gbp is None:
            blockers.append(
                f"MARKET_PRICE_FX_UNAVAILABLE:{target} "
                f"({market_price['currency']}->GBP)"
            )
            continue
        if sale_fx_warning:
            warnings.append(f"{sale_fx_warning}:{target}")

        route_cost_gbp, route_fx_info, route_fx_warning = _value_in_gbp(
            route_cost,
            cost_currency,
            cost_unit,
            asof_date,
            fx_rows,
        )
        if route_cost_gbp is None:
            blockers.append(
                f"ROUTE_COST_FX_UNAVAILABLE:{candidate['route_id']} "
                f"({cost_currency}->GBP)"
            )
            continue
        if route_fx_warning:
            warnings.append(f"{route_fx_warning}:{candidate['route_id']}")

        sale_options.append(
            {
                "option_id": candidate["route_id"],
                "label": candidate["route_name"],
                "delivery_mode": "VIRTUAL_HUB_SALE",
                "target_point_name": candidate["target_point_name"],
                "route_topology_kind": route_topology_kind,
                "sale_price_gbp_mwh": sale_price_gbp,
                "sale_price_currency": "GBP",
                "sale_price_unit": "GBP/MWh",
                "sale_price_source_system": market_price["source_system"],
                "sale_price_source_reference": market_price["source_reference"],
                "sale_price_observed_at_utc": observed_at_iso,
                "sale_price_freshness": market_price["freshness"],
                "sale_price_quality_score": market_price["quality_score"],
                "sale_price_simulated": market_price["simulated"],
                "sale_price_source_family": market_price["source_family"],
                "sale_price_original_currency": market_price["currency"],
                "sale_price_original_unit": market_price["unit"],
                **sale_fx_info,
                "route_cost_gbp_mwh": route_cost_gbp,
                "route_cost_currency": "GBP",
                "route_cost_unit": "GBP/MWh",
                **route_fx_info,
                "capacity_limit_mwh_per_day": capacity_limit,
                "capacity_status": capacity_status,
                "screen_sale_cash_lag_days": _screen_cash_lag_days(eligible_contracts),
                "eligible_resource_ids": [
                    contract["contract_id"] for contract in eligible_contracts
                ],
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
            source_system = getattr(row, "source_system", None)
            metadata = row.metadata_json or {}
            simulated = _is_simulated_market_price(row)
            candidate = {
                "price": row.price,
                "currency": row.currency,
                "unit": row.unit,
                "source_reference": f"market_observation:{row.observation_id}",
                "source_system": source_system,
                "observed_at_utc": _iso_or_none(getattr(row, "observed_at_utc", None)),
                "freshness": getattr(row, "freshness", None),
                "quality_score": getattr(row, "quality_score", None),
                "simulated": simulated,
                "source_family": _market_price_source_family(source_system, metadata),
                "selection_priority": _market_price_selection_priority(row),
            }
            current = prices.get(key)
            if (
                current is None
                or candidate["selection_priority"] < current["selection_priority"]
            ):
                prices[key] = candidate
    for price in prices.values():
        price.pop("selection_priority", None)
    return prices


def _market_price_keys(row) -> list[str]:
    keys = [row.market_venue, row.product]
    metadata = row.metadata_json or {}
    for field in ("hub", "point_name", "market_area"):
        value = metadata.get(field)
        if isinstance(value, str):
            keys.append(value)
    return [value.strip().upper() for value in keys if isinstance(value, str) and value.strip()]


def _market_price_basis_priority(row) -> int:
    metadata = row.metadata_json or {}
    tenor = metadata.get("tenor")
    if not isinstance(tenor, str):
        product = row.product.lower()
        if "within" in product:
            tenor = "within-day"
        elif "day" in product:
            tenor = "day-ahead"
        elif "month" in product:
            tenor = "month-ahead"
        else:
            tenor = ""
    normalized = tenor.strip().lower()
    if normalized in {"day-ahead", "within-day"}:
        return 0
    if normalized in {"weekend", "balance-of-week"}:
        return 1
    if normalized in {"month-ahead", "front-month"}:
        return 2
    return 3


def _market_price_selection_priority(row) -> tuple[int, int, int]:
    """Rank rows for spot-like resource-pool pricing.

    The query already orders newest rows first. This priority keeps that order
    for equal candidates while making the two business rules explicit:
    preferred tenors first, licensed/source-provided rows before simulated
    rows, and exchange observations before broker or assessment sources when
    otherwise tied. The source precedence removes dependence on database row
    order for simulator ticks emitted at the same instant.
    """

    return (
        _market_price_basis_priority(row),
        1 if _is_simulated_market_price(row) else 0,
        _market_price_source_priority(getattr(row, "source_system", None)),
    )


def _market_price_source_priority(source_system: str | None) -> int:
    family = (source_system or "").removesuffix("_Sim").upper()
    return {
        "EEX": 0,
        "ICE_OCM": 0,
        "TRAYPORT": 1,
        "ICIS": 2,
    }.get(family, 3)


def _is_simulated_market_price(row) -> bool:
    metadata = row.metadata_json or {}
    if metadata.get("simulated") is True:
        return True
    source_system = getattr(row, "source_system", None)
    return isinstance(source_system, str) and source_system.endswith("_Sim")


def _market_price_source_family(
    source_system: str | None,
    metadata: dict,
) -> str | None:
    source_family = metadata.get("source_family")
    if isinstance(source_family, str) and source_family.strip():
        return source_family.strip()
    if isinstance(source_system, str) and source_system.endswith("_Sim"):
        return source_system.removesuffix("_Sim")
    return source_system


def _iso_or_none(value) -> str | None:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _portfolio_resource_from_contract(contract: dict) -> dict:
    resource_type = contract["resource_type"]
    notes = _contract_notes_payload(contract.get("notes"))
    variable_cost = _non_negative_number(
        contract.get("variable_cost_gbp_mwh", notes.get("variable_cost_gbp_mwh"))
    )
    regas_fee = _non_negative_number(
        contract.get("regas_fee_gbp_mwh", notes.get("regas_fee_gbp_mwh"))
    )
    fuel_loss = _non_negative_number(
        contract.get("fuel_loss_allowance_pct", notes.get("fuel_loss_allowance_pct"))
    )
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
        "variable_cost_gbp_mwh": round(variable_cost + regas_fee, 4),
        "fuel_loss_allowance_pct": fuel_loss,
        "delivery_tolerance_pct": contract["delivery_tolerance_pct"],
        "nomination_tolerance_pct": contract["nomination_tolerance_pct"],
        "tolerance_risk_allowance_gbp_mwh": contract.get("tolerance_risk_allowance_gbp_mwh") or 0.0,
        "upstream_payment_lag_days": contract["upstream_payment_lag_days"],
        "screen_sale_cash_lag_days": contract["screen_sale_cash_lag_days"],
        "settlement_frequency": contract["settlement_frequency"],
        "required_tso_access": [],
        "accessible_tsos": None,
        "pricing_method": _pricing_method(notes.get("index_basis")),
        "source_refs": _unique(
            [
                f"upstream_resource_contract:{contract['contract_id']}",
                *(
                    [str(notes["source_reference"])]
                    if notes.get("source_reference")
                    else []
                ),
            ]
        ),
    }


def _route_topology_kind(candidate: dict) -> str:
    """Separate non-spatial local sales from network transport routes."""

    start = str(candidate.get("start_point_name") or "").strip().upper()
    target = str(candidate.get("target_point_name") or "").strip().upper()
    if start and start == target and not candidate.get("route_legs"):
        return "LOCAL_MARKET_DISPOSITION"
    return "NETWORK_ROUTE"


def _contract_notes_payload(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _non_negative_number(value: object) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        return 0.0
    return max(float(value), 0.0)


def _pricing_method(value: object) -> str:
    normalized = str(value or "").strip().upper()
    if "DAY-AHEAD" in normalized or "DAY AHEAD" in normalized:
        return "DAILY_INDEX"
    if "MONTH" in normalized:
        return "MONTHLY_INDEX"
    if "FIXED" in normalized:
        return "FIXED_PRICE"
    return "OPERATOR_CONTRACT"


def _candidate_route_cost(
    candidate: dict,
    tariffs: list,
    *,
    price_currency: str,
    price_unit: str,
    company_accessible_tsos: list[str] | None = None,
) -> tuple[float | None, str | None, str | None, list[str], list[str]]:
    if not candidate["route_legs"]:
        return 0.0, None, None, [], []

    try:
        legs = [RouteTariffLeg.model_validate(leg) for leg in candidate["route_legs"]]
    except ValidationError:
        return 0.0, None, None, [], [f"ROUTE_LEG_INVALID:{candidate['route_id']}"]

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
        company_accessible_tsos=(
            company_accessible_tsos if candidate["required_tso_access"] else None
        ),
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
        return 0.0, result.currency, result.unit, result.warnings, blockers
    # Currency/unit harmonisation happens downstream in _value_in_gbp, which
    # converts both sale price and route cost to GBP/MWh with as-of FX and
    # fails closed when conversion is unavailable.
    return result.total_cost, result.currency, result.unit, result.warnings, blockers


def _value_in_gbp(
    value: float | None,
    currency: str | None,
    unit: str | None,
    asof_date: date | None,
    fx_rows: list,
) -> tuple[float | None, dict, str | None]:
    """Convert a value to GBP/MWh with as-of FX provenance (P0-3).

    Values already in GBP pass through unchanged. Non-GBP values are converted
    with FX observations whose value date is not later than ``asof_date``
    (valuation-date as-of join); when no as-of rate exists, the latest rate is
    used and ``fx_as_of_approximated`` is set. Conversion failure returns None
    so callers fail closed.
    """

    if value is None:
        return None, {}, None
    currency_code = (currency or "").strip().upper()
    unit_code = (unit or "").strip().upper()
    if currency_code == "" and value == 0.0:
        # A zero cost carries no currency risk.
        return round(value, 4), {}, None
    if currency_code == "GBP":
        return round(value, 4), {}, None
    if unit_code and not unit_code.endswith("/MWH"):
        return None, {}, None

    asof_rates = _fx_rows_as_of(fx_rows, asof_date)
    converted = _convert_with_rows(value, currency_code, "GBP", asof_rates)
    approximated = converted is None
    if approximated:
        converted = _convert_with_rows(value, currency_code, "GBP", fx_rows)
    if converted is None:
        return None, {}, None

    rate_row = _direct_fx_row(fx_rows, currency_code, "GBP", asof_date)
    provenance = {
        "fx_converted_from": currency_code,
        "fx_rate_used": rate_row.rate if rate_row is not None else None,
        "fx_observation_id": rate_row.observation_id if rate_row is not None else None,
        "fx_value_date": rate_row.value_date if rate_row is not None else None,
        "fx_as_of_approximated": approximated,
    }
    warning = f"FX_AS_OF_APPROXIMATED:{currency_code}->GBP" if approximated else None
    return round(converted, 4), provenance, warning


def _convert_with_rows(value: float, base: str, quote: str, fx_rows: list) -> float | None:
    """Convert ``value`` from ``base`` to ``quote`` using FX rows as rates.

    Rows are turned into ``FxRateInput`` with ``observed_at_utc`` taken from
    the row's value date, so the shared latest-rate graph picks the latest
    value date within the supplied (already as-of filtered) set.
    """

    from eurogas_nexus.domain.market_intelligence.normalized_view import (
        FxRateInput,
        convert_currency,
    )

    rates = [
        FxRateInput(
            pair=row.pair,
            base_currency=row.base_currency,
            quote_currency=row.quote_currency,
            rate=row.rate,
            observed_at_utc=(row.value_date + "T00:00:00+00:00"),
        )
        for row in fx_rows
        if isinstance(row.rate, int | float) and row.rate > 0
    ]
    return convert_currency(value, base, quote, rates)


def _fx_rows_as_of(fx_rows: list, asof_date: date | None) -> list:
    """Keep FX rows whose value date is not later than ``asof_date``."""

    if asof_date is None:
        return list(fx_rows)
    return [
        row
        for row in fx_rows
        if _fx_value_date(row) is not None and _fx_value_date(row) <= asof_date
    ]


def _direct_fx_row(fx_rows: list, base: str, quote: str, asof_date: date | None):
    """Return the latest FX row for a direct currency pair (as-of when given)."""

    matches = []
    for row in fx_rows:
        row_base = str(getattr(row, "base_currency", "") or "").strip().upper()
        row_quote = str(getattr(row, "quote_currency", "") or "").strip().upper()
        pair = str(getattr(row, "pair", "") or "").upper()
        if (row_base == base and row_quote == quote) or pair == f"{base}{quote}":
            row_date = _fx_value_date(row)
            if asof_date is None or (row_date is not None and row_date <= asof_date):
                matches.append(row)
    if not matches:
        return None
    return max(matches, key=lambda row: _fx_value_date(row) or date.min)


def _fx_value_date(row) -> date | None:
    value = getattr(row, "value_date", None)
    if isinstance(value, str):
        return _date_from_iso(value)
    return None


def _date_from_iso(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


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


def _active_company_tsos(rows: list) -> list[str]:
    """Return currently active company TSO access names."""

    now = datetime.now(UTC)
    active: list[str] = []
    for row in rows:
        valid_from = row.valid_from_utc
        if valid_from.tzinfo is None:
            valid_from = valid_from.replace(tzinfo=UTC)
        valid_to = row.valid_to_utc
        if valid_to is not None and valid_to.tzinfo is None:
            valid_to = valid_to.replace(tzinfo=UTC)
        if valid_from > now:
            continue
        if valid_to is not None and valid_to < now:
            continue
        if str(row.status).strip().upper() in {"ACTIVE", "CONFIRMED"}:
            active.append(str(row.tso).strip())
    return active


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
