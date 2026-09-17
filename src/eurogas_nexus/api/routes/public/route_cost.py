"""DB-first European route-cost and decision-support endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from eurogas_nexus.api.dependencies.analysis_snapshot import (
    require_known_analysis_snapshot,
)
from eurogas_nexus.application.resource_pool import (
    active_company_tsos,
    compose_resource_pool_options,
    latest_market_price_by_point,
    read_resource_pool_inputs,
    value_in_gbp,
)
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
from eurogas_nexus.domain.route_cost.schemas import RouteCostScenario

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
            tariff for tariff in filtered if tariff.source_point_name.lower() == point_name.lower()
        ]
    if direction:
        filtered = [
            tariff for tariff in filtered if tariff.direction.value.lower() == direction.lower()
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
    """List route candidates the principal may see (entitlement filtered)."""

    from eurogas_nexus.api.dependencies.row_entitlement import current_principal
    from eurogas_nexus.domain.dataops.entitlement import derived_result_access

    candidates, source, warnings = _load_route_candidates()
    principal = current_principal(request)
    candidates = [
        candidate
        for candidate in candidates
        if derived_result_access(
            principal,
            candidate.get("source_systems") or [],
        ).outcome.value
        == "ALLOWED"
    ]
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

    The composition itself lives in
    :mod:`eurogas_nexus.application.resource_pool`, so the Wave 5
    ``PortfolioSnapshot`` projection composes the identical payload from the same
    read instead of duplicating it (Architecture V2 Wave 5 follow-up).
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
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            data = compose_resource_pool_options(**read_resource_pool_inputs(session))
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
    """Recommend route and sale-market allocation using runtime tariff rows.

    When the caller supplies an ``analysis_snapshot_id`` (Architecture V2 Wave 4)
    the reference is verified against persisted Analysis Snapshots before the run
    and echoed on the result, so a produced recommendation cites the snapshot it
    was computed against instead of carrying an unverified string.
    """

    _require_known_analysis_snapshot(body.analysis_snapshot_id)
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
    """Optimize multi-upstream resource-pool allocation across selling options.

    When the caller supplies an ``analysis_snapshot_id`` (Architecture V2 Wave 4)
    the reference is verified against persisted Analysis Snapshots before the run
    and echoed on the result, so a produced allocation cites the version set it
    was computed against instead of carrying an unverified string.

    Architecture V2 Wave 8: the run is tracked under the shared job lifecycle, so
    ``/api/jobs`` shows what the deployment actually optimised, against which
    snapshot, and with a stable code when it fails. Tracking never changes what
    this handler returns or raises.
    """

    _require_known_analysis_snapshot(body.analysis_snapshot_id)

    from eurogas_nexus.api.dependencies.row_entitlement import current_principal
    from eurogas_nexus.application.jobs import run_tracked_job

    def _optimize(handle) -> dict:
        # A pure computation persists no artefact, so the job records the
        # snapshot it cites and its inputs; there is no output reference to
        # invent. ``add_output`` is the seam the day this result is persisted.
        result = optimize_resource_pool(body)
        payload = result.model_dump(mode="json")
        if body.analysis_snapshot_id:
            payload["analysis_snapshot_id"] = body.analysis_snapshot_id
        else:
            # A caller that cites no snapshot keeps the previous payload exactly:
            # the reference is additive and appears only when it carries a value.
            payload.pop("analysis_snapshot_id")
        return payload

    payload = run_tracked_job(
        _optimize,
        kind="OPTIMISATION",
        principal=current_principal(request).name,
        scope_refs=(f"PORTFOLIO:{body.portfolio_id}",),
        snapshot_id=body.analysis_snapshot_id or "",
        inputs=body.model_dump(mode="json"),
        correlation_id=getattr(request.state, "request_id", None),
        provenance=("route-cost-resource-pool",),
    )
    return _env(
        payload,
        request,
        source="operator-input",
        warnings=payload["warnings"],
    )


def _require_known_analysis_snapshot(snapshot_id: str | None) -> None:
    """Verify a supplied Analysis Snapshot reference (compatibility alias).

    The check itself lives in
    :mod:`eurogas_nexus.api.dependencies.analysis_snapshot`, so every run path
    that accepts an optional ``analysis_snapshot_id`` refuses an unknown
    reference with the same status codes and error codes.
    """

    require_known_analysis_snapshot(snapshot_id)


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


# --- Application-layer seams (Architecture V2 Wave 5 follow-up) -------------
#
# The composition below now lives in
# ``eurogas_nexus.application.resource_pool``, so the PortfolioSnapshot
# projection's ``resources`` slice composes the identical payload from the same
# read instead of duplicating it. The private names stay as compatibility
# aliases for the repository's existing test seams, exactly as ``market.py``
# keeps ``_market_row`` / ``_fx_row``.


def _compose_resource_pool_options(
    *,
    contracts: list[dict],
    candidates: list[dict],
    tariffs: list,
    market_rows: list,
    fx_rows: list,
    company_accessible_tsos: list[str] | None = None,
) -> dict:
    """Compose portfolio resources and sale options (compatibility alias)."""

    return compose_resource_pool_options(
        contracts=contracts,
        candidates=candidates,
        tariffs=tariffs,
        market_rows=market_rows,
        fx_rows=fx_rows,
        company_accessible_tsos=company_accessible_tsos,
    )


def _latest_market_price_by_point(market_rows: list) -> dict[str, dict]:
    """Return the selected market price per point (compatibility alias)."""

    return latest_market_price_by_point(market_rows)


def _value_in_gbp(
    value: float | None,
    currency: str | None,
    unit: str | None,
    asof_date,
    fx_rows: list,
) -> tuple[float | None, dict, str | None]:
    """Convert a value to GBP/MWh with as-of FX provenance (compatibility alias)."""

    return value_in_gbp(value, currency, unit, asof_date, fx_rows)


def _active_company_tsos(rows: list) -> list[str]:
    """Return currently active company TSO access names (compatibility alias)."""

    return active_company_tsos(rows)


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
