"""Public phase-two optimization endpoints.

Every run is persisted as an immutable input/output snapshot (Gate 3) so
evidence can be reconstructed; responses carry ``run_id`` and
``decision_context``. ``SANDBOX_SCENARIO`` accepts operator-supplied inputs for
what-if analysis; ``RUNTIME_DECISION`` consumes PostgreSQL-owned snapshots; the
DB-composed portfolio-network endpoint is the R31 production path. All runs
persist identically in ``optimization_runs``.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, date, datetime, time
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from eurogas_nexus.domain.ontology.vocabulary import StatusKind
from eurogas_nexus.domain.route_cost.portfolio_network import (
    CompanyTsoAccessFact,
    ContractFact,
    FxObservationFact,
    MarketObservationFact,
    NetworkNodeFact,
    RouteCandidateFact,
    RouteLegFact,
    compose_portfolio_network,
    optimize_composed_portfolio_network,
)
from eurogas_nexus.optimization import (
    CapacityProduct,
    NetworkEdge,
    PhaseTwoOptimizer,
    SaleOption,
    SupplyResource,
)

router = APIRouter(prefix="/api/optimization", tags=["optimization"])

DecisionContext = Literal["SANDBOX_SCENARIO", "RUNTIME_DECISION"]


class SupplyResourceRequest(BaseModel):
    """One supply resource in an optimization request.

    Attributes:
        resource_id: Stable resource id.
        available_mwh: Available volume, MWh.
        unit_cost_gbp_mwh: Unit cost, GBP/MWh.
        minimum_take_mwh: Minimum take, MWh.
        maximum_take_mwh: Maximum take, or None (unbounded).
        source_node: Source node, or None.
        required_tso_access: TSO access codes required.
    """

    resource_id: str = Field(min_length=1, max_length=128)
    available_mwh: float = Field(ge=0)
    unit_cost_gbp_mwh: float
    minimum_take_mwh: float = Field(default=0, ge=0)
    maximum_take_mwh: float | None = Field(default=None, ge=0)
    source_node: str | None = None
    required_tso_access: list[str] = Field(default_factory=list)

    def to_domain(self) -> SupplyResource:
        """Map to the domain SupplyResource (tuple-ized access list)."""

        return SupplyResource(
            resource_id=self.resource_id,
            available_mwh=self.available_mwh,
            unit_cost_gbp_mwh=self.unit_cost_gbp_mwh,
            minimum_take_mwh=self.minimum_take_mwh,
            maximum_take_mwh=self.maximum_take_mwh,
            source_node=self.source_node,
            required_tso_access=tuple(self.required_tso_access),
        )


class SaleOptionRequest(BaseModel):
    """One sale option in an optimization request.

    Attributes:
        option_id: Stable option id.
        destination_node: Destination node.
        sale_price_gbp_mwh: Sale price, GBP/MWh.
        capacity_mwh: Sale capacity, MWh.
        variable_cost_gbp_mwh: Variable cost, GBP/MWh.
        required_tso_access: TSO access codes required.
    """

    option_id: str = Field(min_length=1, max_length=128)
    destination_node: str = Field(min_length=1, max_length=128)
    sale_price_gbp_mwh: float
    capacity_mwh: float = Field(ge=0)
    variable_cost_gbp_mwh: float = 0
    required_tso_access: list[str] = Field(default_factory=list)

    def to_domain(self) -> SaleOption:
        """Map to the domain SaleOption (tuple-ized access list)."""

        return SaleOption(
            option_id=self.option_id,
            destination_node=self.destination_node,
            sale_price_gbp_mwh=self.sale_price_gbp_mwh,
            capacity_mwh=self.capacity_mwh,
            variable_cost_gbp_mwh=self.variable_cost_gbp_mwh,
            required_tso_access=tuple(self.required_tso_access),
        )


class NetworkEdgeRequest(BaseModel):
    """One directed network edge in an optimization request.

    Attributes:
        edge_id: Stable edge id.
        source: Source node.
        target: Target node.
        tariff_gbp_mwh: Per-MWh tariff.
        available_capacity_mwh: Edge capacity, MWh.
        tso: Operating TSO, or None.
        enabled: Whether the edge participates.
    """

    edge_id: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=128)
    target: str = Field(min_length=1, max_length=128)
    tariff_gbp_mwh: float = Field(ge=0)
    available_capacity_mwh: float = Field(ge=0)
    tso: str | None = None
    enabled: bool = True

    def to_domain(self) -> NetworkEdge:
        """Map to the domain NetworkEdge (same field names)."""

        return NetworkEdge(**self.model_dump())


class CapacityProductRequest(BaseModel):
    """One capacity product in a capacity-optimization request.

    Attributes:
        product_id: Stable product id.
        capacity_mwh: Product capacity, MWh.
        fixed_cost_gbp: Fixed cost, GBP.
        variable_cost_gbp_mwh: Variable cost, GBP/MWh.
        firmness: ``firm`` or ``interruptible``.
    """

    product_id: str = Field(min_length=1, max_length=128)
    capacity_mwh: float = Field(ge=0)
    fixed_cost_gbp: float = Field(ge=0)
    variable_cost_gbp_mwh: float = Field(default=0, ge=0)
    firmness: str = Field(default="firm", pattern="^(firm|interruptible)$")

    def to_domain(self) -> CapacityProduct:
        """Map to the domain CapacityProduct."""

        return CapacityProduct(
            product_id=self.product_id,
            capacity_mwh=self.capacity_mwh,
            fixed_cost_gbp=self.fixed_cost_gbp,
            variable_cost_gbp_mwh=self.variable_cost_gbp_mwh,
            firmness=self.firmness,  # type: ignore[arg-type]
        )


class RouteOptimizationRequest(BaseModel):
    """Route-optimization request (network + capacity + access).

    Attributes:
        source: Source node.
        target: Target node.
        required_capacity_mwh: Volume to route, MWh.
        accessible_tsos: Company's accessible TSOs, or None.
        edges: Candidate network edges.
        decision_context: SANDBOX_SCENARIO or RUNTIME_DECISION.
    """

    source: str = Field(min_length=1, max_length=128)
    target: str = Field(min_length=1, max_length=128)
    required_capacity_mwh: float = Field(ge=0)
    accessible_tsos: list[str] | None = None
    edges: list[NetworkEdgeRequest]
    decision_context: DecisionContext = "SANDBOX_SCENARIO"


class ResourcePoolOptimizationRequest(BaseModel):
    """Resource-pool optimization request (resources + sale options).

    Attributes:
        portfolio_id: Portfolio id, or None.
        resources: Supply resources.
        sale_options: Sale options.
        accessible_tsos: Company's accessible TSOs, or None.
        decision_context: SANDBOX_SCENARIO or RUNTIME_DECISION.
    """

    portfolio_id: str | None = Field(default=None, max_length=128)
    resources: list[SupplyResourceRequest] = Field(default_factory=list)
    sale_options: list[SaleOptionRequest] = Field(default_factory=list)
    accessible_tsos: list[str] | None = None
    decision_context: DecisionContext = "SANDBOX_SCENARIO"


class CapacityOptimizationRequest(BaseModel):
    """Capacity-optimization request (product mix selection).

    Attributes:
        products: Candidate capacity products.
        required_capacity_mwh: Volume to cover, MWh.
        expected_throughput_mwh: Expected throughput, or None.
        allow_interruptible: Whether interruptible products may be chosen.
        decision_context: SANDBOX_SCENARIO or RUNTIME_DECISION.
    """

    products: list[CapacityProductRequest]
    required_capacity_mwh: float = Field(ge=0)
    expected_throughput_mwh: float | None = Field(default=None, ge=0)
    allow_interruptible: bool = True
    decision_context: DecisionContext = "SANDBOX_SCENARIO"


class ContractOptimizationRequest(BaseModel):
    """Contract-optimization request (resource selection against a market).

    Attributes:
        resources: Supply resources.
        market_price_gbp_mwh: Market price, GBP/MWh.
        demand_limit_mwh: Demand cap, MWh.
        decision_context: SANDBOX_SCENARIO or RUNTIME_DECISION.
    """

    resources: list[SupplyResourceRequest]
    market_price_gbp_mwh: float
    demand_limit_mwh: float = Field(ge=0)
    decision_context: DecisionContext = "SANDBOX_SCENARIO"


class StoragePeriodRequest(BaseModel):
    """One storage dispatch period with a market price.

    Attributes:
        period_id: Stable period id.
        market_price_gbp_mwh: Market price for the period, GBP/MWh.
    """

    period_id: str = Field(min_length=1, max_length=128)
    market_price_gbp_mwh: float


class StorageFacilityRequest(BaseModel):
    """Storage facility parameters for multi-period dispatch assessment."""

    initial_inventory_mwh: float = Field(ge=0)
    minimum_inventory_mwh: float = Field(ge=0)
    maximum_inventory_mwh: float = Field(ge=0)
    maximum_injection_mwh: float = Field(ge=0)
    maximum_withdrawal_mwh: float = Field(ge=0)
    injection_efficiency: float = Field(default=1.0, gt=0, le=1)
    withdrawal_efficiency: float = Field(default=1.0, gt=0, le=1)
    injection_cost_gbp_mwh: float = Field(default=0, ge=0)
    withdrawal_cost_gbp_mwh: float = Field(default=0, ge=0)
    terminal_inventory_mwh: float | None = Field(default=None, ge=0)


class StorageDispatchOptimizationRequest(BaseModel):
    """Storage dispatch assessment request.

    SANDBOX_SCENARIO accepts explicit facility/period inputs. RUNTIME_DECISION
    composes facility, inventory, market prices, and FX from PostgreSQL and
    rejects client-supplied facility/period facts.
    """

    facility: StorageFacilityRequest | None = None
    periods: list[StoragePeriodRequest] = Field(default_factory=list)
    inventory_step_mwh: float = Field(default=1.0, gt=0)
    facility_id: str | None = Field(default=None, max_length=128)
    gas_day: date | None = None
    max_periods: int = Field(default=5, ge=1, le=24)
    decision_context: DecisionContext = "SANDBOX_SCENARIO"


class NominationWindowRequest(BaseModel):
    """One nomination/renomination window (assessment rule)."""

    window_id: str = Field(min_length=1, max_length=128)
    opens_at: time
    closes_at: time
    maximum_change_mwh: float | None = Field(default=None, ge=0)
    maximum_change_pct: float | None = Field(default=None, ge=0)


class NominationInstructionRequest(BaseModel):
    """One nomination/renomination instruction under assessment."""

    submitted_at: datetime
    requested_quantity_mwh: float = Field(ge=0)


class NominationWindowOptimizationRequest(BaseModel):
    """Nomination-window assessment request.

    The endpoint evaluates instructions and returns accepted/adjusted
    quantities. It never submits a nomination. RUNTIME_DECISION loads window
    rules from PostgreSQL; instructions remain assessment inputs.
    """

    initial_quantity_mwh: float = Field(ge=0)
    instructions: list[NominationInstructionRequest] = Field(default_factory=list)
    windows: list[NominationWindowRequest] = Field(default_factory=list)
    gas_day: date | None = None
    decision_context: DecisionContext = "SANDBOX_SCENARIO"


class PortfolioNetworkOptimizationRequest(BaseModel):
    """DB-composed portfolio network optimization request (R31).

    Only decision metadata is accepted. Network geometry, tariffs, capacities,
    market prices, and contract volumes are assembled from the runtime DB.
    """

    model_config = ConfigDict(extra="forbid")

    portfolio_id: str = Field(min_length=1, max_length=128)
    gas_day: date
    capacity_product: str = Field(
        default="ANNUAL",
        pattern="^(ANNUAL|QUARTERLY|MONTHLY|WEEKLY|DAILY|WITHIN_DAY)$",
    )
    firmness: str = Field(
        default="FIRM",
        pattern="^(FIRM|INTERRUPTIBLE|BACKHAUL|OFF_PEAK)$",
    )
    max_market_price_age_hours: float = Field(default=72, gt=0, le=720)
    decision_context: DecisionContext = "RUNTIME_DECISION"


@router.post("/route")
def optimize_route(body: RouteOptimizationRequest) -> dict:
    """Return a minimum-cost route satisfying capacity and TSO-access constraints."""

    _reject_runtime_decision(body.decision_context, "route")
    optimizer = PhaseTwoOptimizer(
        accessible_tsos=set(body.accessible_tsos) if body.accessible_tsos is not None else None
    )
    try:
        result = optimizer.optimize_route(
            edges=[edge.to_domain() for edge in body.edges],
            source=body.source,
            target=body.target,
            required_capacity_mwh=body.required_capacity_mwh,
        )
    except ValueError as exc:
        raise _invalid_input(exc) from exc
    return _envelope_run(
        "route",
        body,
        result.status,
        asdict(result),
        result.warnings,
    )


@router.post("/resource-pool")
def optimize_resource_pool(body: ResourcePoolOptimizationRequest) -> dict:
    """Allocate upstream resources across sale options under commercial constraints.

    ``SANDBOX_SCENARIO`` accepts operator-supplied inputs for what-if analysis.
    ``RUNTIME_DECISION`` rejects client-supplied prices/volumes and assembles
    the inputs exclusively from the runtime DB snapshot (contracts, route
    candidates, market prices with as-of FX), persisting the input snapshot id.
    """

    if body.decision_context == "RUNTIME_DECISION":
        return _runtime_resource_pool(body)
    optimizer = PhaseTwoOptimizer(
        accessible_tsos=set(body.accessible_tsos) if body.accessible_tsos is not None else None
    )
    try:
        result = optimizer.optimize_resource_pool(
            resources=[resource.to_domain() for resource in body.resources],
            sale_options=[option.to_domain() for option in body.sale_options],
        )
    except ValueError as exc:
        raise _invalid_input(exc) from exc
    return _envelope_run(
        "resource_pool",
        body,
        result.status,
        asdict(result),
        result.warnings,
    )


@router.post("/capacity")
def optimize_capacity(body: CapacityOptimizationRequest) -> dict:
    """Choose the lowest-cost capacity product combination covering required capacity."""

    _reject_runtime_decision(body.decision_context, "capacity")
    try:
        result = PhaseTwoOptimizer().optimize_capacity(
            products=[product.to_domain() for product in body.products],
            required_capacity_mwh=body.required_capacity_mwh,
            expected_throughput_mwh=body.expected_throughput_mwh,
            allow_interruptible=body.allow_interruptible,
        )
    except ValueError as exc:
        raise _invalid_input(exc) from exc
    return _envelope_run(
        "capacity",
        body,
        result.status,
        asdict(result),
        result.warnings,
    )


@router.post("/contracts")
def optimize_contracts(body: ContractOptimizationRequest) -> dict:
    """Recommend mandatory and discretionary daily contract takes."""

    _reject_runtime_decision(body.decision_context, "contracts")
    try:
        result = PhaseTwoOptimizer().optimize_contracts(
            resources=[resource.to_domain() for resource in body.resources],
            market_price_gbp_mwh=body.market_price_gbp_mwh,
            demand_limit_mwh=body.demand_limit_mwh,
        )
    except ValueError as exc:
        raise _invalid_input(exc) from exc
    return _envelope_run(
        "contracts",
        body,
        result.status,
        asdict(result),
        result.warnings,
    )


@router.post("/storage-dispatch")
def optimize_storage_dispatch(body: StorageDispatchOptimizationRequest) -> dict:
    """Assess multi-period storage inject/withdraw/hold dispatch.

    Assessment only: this endpoint never submits a storage booking or
    nomination. RUNTIME_DECISION is rejected until DB-owned storage facility
    and price inputs are delivered.
    """

    if body.decision_context == "RUNTIME_DECISION":
        return _runtime_storage_dispatch(body)
    if body.facility is None or not body.periods:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "optimization_input_invalid",
                "message": "SANDBOX_SCENARIO requires facility and periods.",
            },
        )
    from eurogas_nexus.optimization.storage import (
        StorageFacility,
        StoragePeriod,
    )
    from eurogas_nexus.optimization.storage import (
        optimize_storage_dispatch as _optimize,
    )

    try:
        result = _optimize(
            StorageFacility(**body.facility.model_dump()),
            [StoragePeriod(**period.model_dump()) for period in body.periods],
            inventory_step_mwh=body.inventory_step_mwh,
        )
    except ValueError as exc:
        raise _invalid_input(exc) from exc
    return _envelope_run(
        "storage_dispatch",
        body,
        result.status,
        asdict(result),
        result.warnings,
    )


@router.post("/nomination-window")
def optimize_nomination_window(body: NominationWindowOptimizationRequest) -> dict:
    """Assess nomination/renomination windows against submitted instructions.

    Assessment only: this endpoint returns accepted/adjusted quantities and
    never submits a nomination. RUNTIME_DECISION is rejected until DB-owned
    nomination windows are delivered.
    """

    if body.decision_context == "RUNTIME_DECISION":
        return _runtime_nomination_window(body)
    from eurogas_nexus.optimization.nomination import (
        NominationInstruction,
        NominationWindow,
    )
    from eurogas_nexus.optimization.nomination import (
        optimize_nomination_schedule as _optimize,
    )

    try:
        result = _optimize(
            body.initial_quantity_mwh,
            [
                NominationInstruction(
                    submitted_at=instruction.submitted_at,
                    requested_quantity_mwh=instruction.requested_quantity_mwh,
                )
                for instruction in body.instructions
            ],
            [
                NominationWindow(
                    window_id=window.window_id,
                    opens_at=window.opens_at,
                    closes_at=window.closes_at,
                    maximum_change_mwh=window.maximum_change_mwh,
                    maximum_change_pct=window.maximum_change_pct,
                )
                for window in body.windows
            ],
        )
    except ValueError as exc:
        raise _invalid_input(exc) from exc
    return _envelope_run(
        "nomination_window",
        body,
        result.status,
        asdict(result),
        result.warnings,
    )


@router.post("/portfolio-network")
def optimize_portfolio_network(body: PortfolioNetworkOptimizationRequest) -> dict:
    """Optimize all DB-owned contracts and routes over a shared network.

    The client supplies only decision metadata. Contracts, reference nodes,
    active routes, TSO access, tariffs, market observations, and FX rows are
    assembled from PostgreSQL; a blocked or stale snapshot returns 422 and
    never reaches the solver.
    """

    if body.decision_context != "RUNTIME_DECISION":
        raise HTTPException(
            status_code=422,
            detail={
                "code": "sandbox_scenario_not_supported",
                "message": (
                    "/api/optimization/portfolio-network is a DB-composed "
                    "RUNTIME_DECISION surface; use /api/optimization/route or "
                    "/api/optimization/resource-pool for sandbox what-if runs."
                ),
                "research_only": True,
                "human_review_required": True,
            },
        )
    if not _db_is_configured():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "runtime_db_not_configured",
                "message": (
                    "Portfolio network optimization requires the runtime DB; "
                    "no local-file fallback is permitted."
                ),
                "research_only": True,
                "human_review_required": True,
            },
        )

    try:
        from eurogas_nexus.db.models import (
            CompanyTsoAccessRecord,
            FxObservationRecord,
            MarketObservationRecord,
        )
        from eurogas_nexus.db.repositories.reference_network import (
            SqlAlchemyNodeRepository,
        )
        from eurogas_nexus.db.repositories.route_cost import (
            list_route_candidates,
            list_tso_tariffs,
            list_upstream_contracts,
        )
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            contract_rows = list_upstream_contracts(session)
            route_rows = list_route_candidates(session)
            tariff_rows = list_tso_tariffs(session)
            node_rows = SqlAlchemyNodeRepository(session).list_all()
            access_rows = (
                session.query(CompanyTsoAccessRecord)
                .order_by(CompanyTsoAccessRecord.tso)
                .all()
            )
            market_rows = (
                session.query(MarketObservationRecord)
                .order_by(MarketObservationRecord.observed_at_utc.desc())
                .all()
            )
            fx_rows = (
                session.query(FxObservationRecord)
                .order_by(FxObservationRecord.observed_at_utc.desc())
                .all()
            )
    except _sqlalchemy_error_type() as exc:
        raise _db_unavailable(exc) from exc

    composition = compose_portfolio_network(
        contracts=[_contract_fact(row) for row in contract_rows],
        routes=[_route_fact(row) for row in route_rows],
        nodes=[_node_fact(row) for row in node_rows],
        tariffs=tariff_rows,
        access_rows=[_access_fact(row) for row in access_rows],
        market_rows=[_market_fact(row) for row in market_rows],
        fx_rows=[_fx_fact(row) for row in fx_rows],
        gas_day=body.gas_day,
        capacity_product=body.capacity_product,
        firmness=body.firmness,
        max_market_price_age_hours=body.max_market_price_age_hours,
        now_utc=datetime.now(UTC),
    )
    if not composition.is_complete:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "runtime_decision_input_blocked",
                "message": (
                    "Runtime DB snapshot cannot assemble portfolio-network inputs."
                ),
                "blockers": list(composition.blockers),
                "warnings": list(composition.warnings),
                "missing_inputs": list(composition.missing_inputs),
                "research_only": True,
                "human_review_required": True,
            },
        )

    try:
        result = optimize_composed_portfolio_network(composition)
    except ValueError as exc:
        raise _invalid_input(exc) from exc

    input_snapshot = _portfolio_input_snapshot(
        body=body,
        composition=composition,
        market_rows=market_rows,
        fx_rows=fx_rows,
    )
    run_id = _persist_run(
        optimization_type="portfolio_network",
        decision_context="RUNTIME_DECISION",
        status=_status_kind(result.status),
        input_snapshot=input_snapshot,
        output_snapshot=asdict(result),
        warnings=list(result.warnings),
        source_refs=list(composition.source_refs),
    )
    return {
        "data": asdict(result),
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["runtime-postgresql"],
            "lineage": list(composition.source_refs),
            "assumptions": list(composition.assumptions),
            "missing_inputs": [],
            "warnings": list(result.warnings),
            "run_id": run_id,
            "snapshot_id": run_id,
            "decision_context": "RUNTIME_DECISION",
            "gas_day": body.gas_day.isoformat(),
        },
    }


@router.get("/runs/{run_id}")
def get_optimization_run(run_id: str) -> dict:
    """Return one persisted optimization run for evidence reconstruction."""

    if not _db_is_configured():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "runtime_db_not_configured",
                "message": "Runtime DB is required to read optimization runs.",
            },
        )
    try:
        from eurogas_nexus.db.repositories.optimization import get_optimization_run as _get
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            run = _get(session, run_id)
    except _sqlalchemy_error_type() as exc:
        raise _db_unavailable(exc) from exc
    if run is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "optimization_run_not_found",
                "message": f"No optimization run with id {run_id!r}.",
            },
        )
    return {
        "data": {column.name: getattr(run, column.name) for column in run.__table__.columns},
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["optimization_runs"],
            "warnings": [],
        },
    }


def _reject_runtime_decision(decision_context: str, endpoint: str) -> None:
    """Fail closed when an endpoint has no RUNTIME_DECISION implementation."""

    if decision_context != "RUNTIME_DECISION":
        return
    raise HTTPException(
        status_code=422,
        detail={
            "code": "runtime_decision_not_supported",
            "message": (
                f"/api/optimization/{endpoint} does not implement RUNTIME_DECISION "
                "yet; use SANDBOX_SCENARIO or the DB-backed route-cost endpoints."
            ),
            "research_only": True,
            "human_review_required": True,
        },
    )


def _runtime_storage_dispatch(body: StorageDispatchOptimizationRequest) -> dict:
    """Compose storage dispatch inputs from PostgreSQL masters/observations."""

    if body.facility is not None or body.periods:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "runtime_decision_client_input_forbidden",
                "message": "RUNTIME_DECISION storage inputs come from PostgreSQL only.",
                "research_only": True,
                "human_review_required": True,
            },
        )
    if not body.facility_id or body.gas_day is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "runtime_decision_storage_master_required",
                "message": "RUNTIME_DECISION storage dispatch requires facility_id and gas_day.",
                "research_only": True,
                "human_review_required": True,
            },
        )
    _require_runtime_db("storage-dispatch")
    at_utc = datetime.combine(body.gas_day, time(12, 0), tzinfo=UTC)
    try:
        from eurogas_nexus.application.storage_nomination_composition import (
            compose_storage_dispatch,
        )
        from eurogas_nexus.db.models import FxObservationRecord, MarketObservationRecord
        from eurogas_nexus.db.repositories.storage_nomination import (
            active_storage_facility,
            latest_storage_inventory,
        )
        from eurogas_nexus.db.session import get_session_factory
        from eurogas_nexus.optimization.storage import (
            optimize_storage_dispatch as _optimize,
        )

        with get_session_factory()() as session:
            facility = active_storage_facility(
                session, body.facility_id, at_utc=at_utc
            )
            inventory = latest_storage_inventory(
                session, body.facility_id, asof_utc=at_utc
            )
            market_rows = (
                session.query(MarketObservationRecord)
                .order_by(MarketObservationRecord.period_start_utc.asc())
                .all()
            )
            fx_rows = (
                session.query(FxObservationRecord)
                .order_by(FxObservationRecord.observed_at_utc.desc())
                .all()
            )
    except _sqlalchemy_error_type() as exc:
        raise _db_unavailable(exc) from exc

    composed = compose_storage_dispatch(
        facility=facility,
        inventory=inventory,
        market_rows=market_rows,
        fx_rows=fx_rows,
        gas_day=body.gas_day,
        max_periods=body.max_periods,
    )
    if not composed.is_complete or composed.facility is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "runtime_decision_input_blocked",
                "message": "PostgreSQL cannot assemble storage dispatch inputs.",
                "blockers": list(composed.blockers),
                "warnings": list(composed.warnings),
                "research_only": True,
                "human_review_required": True,
            },
        )
    try:
        result = _optimize(
            composed.facility,
            list(composed.periods),
            inventory_step_mwh=body.inventory_step_mwh,
        )
    except ValueError as exc:
        raise _invalid_input(exc) from exc
    run_id = _persist_run(
        optimization_type="storage_dispatch",
        decision_context="RUNTIME_DECISION",
        status=_status_kind(result.status),
        input_snapshot={
            "facility_id": body.facility_id,
            "gas_day": body.gas_day.isoformat(),
            "max_periods": body.max_periods,
            "facility": asdict(composed.facility),
            "periods": [asdict(period) for period in composed.periods],
            "source_refs": list(composed.source_refs),
            "blockers": [],
        },
        output_snapshot=asdict(result),
        warnings=list(result.warnings),
        source_refs=list(composed.source_refs),
    )
    return {
        "data": asdict(result),
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["runtime-postgresql"],
            "lineage": list(composed.source_refs),
            "warnings": list(result.warnings),
            "run_id": run_id,
            "snapshot_id": run_id,
            "decision_context": "RUNTIME_DECISION",
        },
    }


def _runtime_nomination_window(body: NominationWindowOptimizationRequest) -> dict:
    """Compose nomination window rules from PostgreSQL masters."""

    if body.windows:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "runtime_decision_client_input_forbidden",
                "message": "RUNTIME_DECISION nomination windows come from PostgreSQL only.",
                "research_only": True,
                "human_review_required": True,
            },
        )
    if body.gas_day is None:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "runtime_decision_window_master_required",
                "message": "RUNTIME_DECISION nomination assessment requires gas_day.",
                "research_only": True,
                "human_review_required": True,
            },
        )
    _require_runtime_db("nomination-window")
    at_utc = datetime.combine(body.gas_day, time(12, 0), tzinfo=UTC)
    try:
        from eurogas_nexus.application.storage_nomination_composition import (
            compose_nomination_windows,
        )
        from eurogas_nexus.db.repositories.storage_nomination import (
            active_nomination_windows,
        )
        from eurogas_nexus.db.session import get_session_factory
        from eurogas_nexus.optimization.nomination import (
            NominationInstruction,
        )
        from eurogas_nexus.optimization.nomination import (
            optimize_nomination_schedule as _optimize,
        )

        with get_session_factory()() as session:
            window_rows = active_nomination_windows(session, at_utc=at_utc)
    except _sqlalchemy_error_type() as exc:
        raise _db_unavailable(exc) from exc

    composed = compose_nomination_windows(window_rows=window_rows)
    if not composed.is_complete:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "runtime_decision_input_blocked",
                "message": "PostgreSQL cannot assemble nomination window inputs.",
                "blockers": list(composed.blockers),
                "warnings": list(composed.warnings),
                "research_only": True,
                "human_review_required": True,
            },
        )
    try:
        result = _optimize(
            body.initial_quantity_mwh,
            [
                NominationInstruction(
                    submitted_at=instruction.submitted_at,
                    requested_quantity_mwh=instruction.requested_quantity_mwh,
                )
                for instruction in body.instructions
            ],
            list(composed.windows),
        )
    except ValueError as exc:
        raise _invalid_input(exc) from exc
    run_id = _persist_run(
        optimization_type="nomination_window",
        decision_context="RUNTIME_DECISION",
        status=_status_kind(result.status),
        input_snapshot={
            "gas_day": body.gas_day.isoformat(),
            "initial_quantity_mwh": body.initial_quantity_mwh,
            "instructions": [
                instruction.model_dump(mode="json") for instruction in body.instructions
            ],
            "windows": [
                {
                    "window_id": window.window_id,
                    "opens_at": window.opens_at.isoformat(),
                    "closes_at": window.closes_at.isoformat(),
                    "maximum_change_mwh": window.maximum_change_mwh,
                    "maximum_change_pct": window.maximum_change_pct,
                }
                for window in composed.windows
            ],
            "source_refs": list(composed.source_refs),
            "blockers": [],
        },
        output_snapshot=asdict(result),
        warnings=list(result.warnings),
        source_refs=list(composed.source_refs),
    )
    return {
        "data": asdict(result),
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["runtime-postgresql"],
            "lineage": list(composed.source_refs),
            "warnings": list(result.warnings),
            "run_id": run_id,
            "snapshot_id": run_id,
            "decision_context": "RUNTIME_DECISION",
        },
    }


def _runtime_resource_pool(body: ResourcePoolOptimizationRequest) -> dict:
    """DB-snapshot-only resource-pool optimization (Gate 3).

    Client-supplied prices/volumes are rejected; inputs come exclusively from
    the runtime DB snapshot, and the input snapshot id is persisted and
    returned so the decision can be reconstructed later.
    """

    if body.resources or body.sale_options:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "runtime_decision_client_input_forbidden",
                "message": (
                    "RUNTIME_DECISION consumes the DB snapshot only; client-supplied "
                    "resources/sale_options are not accepted."
                ),
                "research_only": True,
                "human_review_required": True,
            },
        )
    if not body.portfolio_id:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "runtime_decision_portfolio_required",
                "message": "RUNTIME_DECISION requires a portfolio_id.",
                "research_only": True,
                "human_review_required": True,
            },
        )
    if not _db_is_configured():
        raise HTTPException(
            status_code=503,
            detail={
                "code": "runtime_db_not_configured",
                "message": (
                    "RUNTIME_DECISION requires the runtime DB; no silent fallback "
                    "to local files."
                ),
                "research_only": True,
                "human_review_required": True,
            },
        )

    try:
        from eurogas_nexus.db.models import (
            CompanyTsoAccessRecord,
            FxObservationRecord,
            MarketObservationRecord,
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
            market_rows = (
                session.query(MarketObservationRecord)
                .order_by(MarketObservationRecord.observed_at_utc.desc())
                .all()
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
    except _sqlalchemy_error_type() as exc:
        raise _db_unavailable(exc) from exc

    from eurogas_nexus.api.routes.public import route_cost as route_cost_module

    composed = route_cost_module._compose_resource_pool_options(
        contracts=contracts,
        candidates=candidates,
        tariffs=tariffs,
        market_rows=market_rows,
        fx_rows=fx_rows,
        company_accessible_tsos=route_cost_module._active_company_tsos(access_rows),
    )
    blockers = list(composed["blockers"])
    warnings = list(composed["warnings"])

    total_volume = sum(
        float(resource["available_quantity_mwh_per_day"])
        for resource in composed["portfolio_resources"]
    )
    resources: list[SupplyResource] = []
    for resource in composed["portfolio_resources"]:
        resources.append(
            SupplyResource(
                resource_id=resource["resource_id"],
                available_mwh=float(resource["available_quantity_mwh_per_day"]),
                unit_cost_gbp_mwh=(
                    float(resource["contract_cost_gbp_mwh"])
                    + float(resource.get("tolerance_risk_allowance_gbp_mwh") or 0.0)
                ),
                minimum_take_mwh=0.0,
                required_tso_access=tuple(resource.get("required_tso_access") or []),
            )
        )
    sale_options: list[SaleOption] = []
    for option in composed["sale_options"]:
        capacity = option.get("capacity_limit_mwh_per_day")
        sale_options.append(
            SaleOption(
                option_id=option["option_id"],
                destination_node=option["target_point_name"],
                sale_price_gbp_mwh=float(option["sale_price_gbp_mwh"]),
                capacity_mwh=float(capacity) if capacity is not None else total_volume,
                variable_cost_gbp_mwh=float(option.get("route_cost_gbp_mwh") or 0.0),
                required_tso_access=tuple(option.get("required_tso_access") or []),
            )
        )

    if not resources:
        blockers.append("UPSTREAM_CONTRACTS_MISSING")
    if not sale_options:
        blockers.append("SALE_OPTIONS_UNAVAILABLE")
    if blockers:
        # Fail closed: never run a "decision" on inputs the DB cannot assemble.
        raise HTTPException(
            status_code=422,
            detail={
                "code": "runtime_decision_input_blocked",
                "message": "Runtime DB snapshot cannot assemble optimization inputs.",
                "blockers": sorted(set(blockers)),
                "warnings": sorted(set(warnings)),
                "research_only": True,
                "human_review_required": True,
            },
        )

    optimizer = PhaseTwoOptimizer(accessible_tsos=None)
    try:
        result = optimizer.optimize_resource_pool(
            resources=resources,
            sale_options=sale_options,
        )
    except ValueError as exc:
        raise _invalid_input(exc) from exc

    input_snapshot = {
        "portfolio_id": body.portfolio_id,
        "decision_context": "RUNTIME_DECISION",
        "resources": [asdict(resource) for resource in resources],
        "sale_options": [asdict(option) for option in sale_options],
        "fx_observation_ids": [fx_row.observation_id for fx_row in fx_rows],
        "blockers": blockers,
    }
    run_id = _persist_run(
        optimization_type="resource_pool",
        decision_context="RUNTIME_DECISION",
        status=_status_kind(result.status),
        input_snapshot=input_snapshot,
        output_snapshot=asdict(result),
        warnings=list(result.warnings),
    )
    return {
        "data": asdict(result),
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["runtime-postgresql"],
            "warnings": list(result.warnings),
            "run_id": run_id,
            "snapshot_id": run_id,
            "decision_context": "RUNTIME_DECISION",
        },
    }


def _envelope_run(
    optimization_type: str,
    body: BaseModel,
    solver_status: str,
    output: object,
    warnings: tuple[str, ...],
) -> dict:
    run_id = _persist_run(
        optimization_type=optimization_type,
        decision_context=body.decision_context,
        status=_status_kind(solver_status),
        input_snapshot=body.model_dump(mode="json"),
        output_snapshot=output,
        warnings=list(warnings),
    )
    return {
        "data": output,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["operator-input"],
            "warnings": list(warnings),
            "run_id": run_id,
            "decision_context": body.decision_context,
        },
    }


def _status_kind(solver_status: str) -> str:
    """Map solver statuses onto the unified ontology StatusKind."""

    mapping = {
        "optimal": StatusKind.SUCCESS.value,
        "feasible": StatusKind.PARTIAL.value,
        "infeasible": StatusKind.BLOCKED.value,
        "success": StatusKind.SUCCESS.value,
        "partial": StatusKind.PARTIAL.value,
        "blocked": StatusKind.BLOCKED.value,
    }
    return mapping.get(solver_status, StatusKind.UNKNOWN.value)


def _persist_run(
    *,
    optimization_type: str,
    decision_context: str,
    status: str,
    input_snapshot: dict,
    output_snapshot: object,
    warnings: list[str],
    source_refs: list[str] | None = None,
) -> str | None:
    """Persist one run when the runtime DB is available; return its id."""

    if not _db_is_configured():
        return None
    run_id = f"opt-{uuid4().hex[:16]}"
    try:
        from eurogas_nexus.db.repositories.optimization import (
            persist_optimization_run as _persist,
        )
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            _persist(
                session,
                run_id=run_id,
                optimization_type=optimization_type,
                decision_context=decision_context,
                status=status,
                input_snapshot=input_snapshot,
                output_snapshot=_jsonable(output_snapshot),
                source_refs=source_refs or ["operator-input"],
                warnings=warnings,
                created_at_utc=datetime.now(UTC),
            )
            session.commit()
        return run_id
    except Exception:
        return None


def _portfolio_input_snapshot(
    *,
    body: PortfolioNetworkOptimizationRequest,
    composition: object,
    market_rows: list,
    fx_rows: list,
) -> dict:
    """Serialize the assembled DB facts for immutable evidence storage."""

    return {
        "portfolio_id": body.portfolio_id,
        "decision_context": "RUNTIME_DECISION",
        "gas_day": body.gas_day.isoformat(),
        "capacity_product": body.capacity_product,
        "firmness": body.firmness,
        "max_market_price_age_hours": body.max_market_price_age_hours,
        "resources": [asdict(resource) for resource in composition.resources],
        "sale_options": [asdict(option) for option in composition.sale_options],
        "edges": [asdict(edge) for edge in composition.edges],
        "resource_lineage": list(composition.resource_lineage),
        "sale_option_lineage": list(composition.sale_option_lineage),
        "edge_lineage": list(composition.edge_lineage),
        "assumptions": list(composition.assumptions),
        "blockers": [],
        "market_observation_ids": [row.observation_id for row in market_rows],
        "fx_observation_ids": [row.observation_id for row in fx_rows],
    }


def _contract_fact(payload: dict) -> ContractFact:
    return ContractFact(
        contract_id=payload["contract_id"],
        contract_name=payload["contract_name"],
        resource_type=payload["resource_type"],
        delivery_point_name=payload["delivery_point_name"],
        gas_year=payload["gas_year"],
        delivery_quantity_mwh_per_day=float(
            payload["delivery_quantity_mwh_per_day"]
        ),
        contract_price_gbp_mwh=float(payload["contract_price_gbp_mwh"]),
        tolerance_risk_allowance_gbp_mwh=float(
            payload.get("tolerance_risk_allowance_gbp_mwh") or 0.0
        ),
        allowed_exit_points=tuple(payload.get("allowed_exit_points") or []),
        eligible_sale_modes=tuple(payload.get("eligible_sale_modes") or []),
        updated_at_utc=payload.get("updated_at_utc"),
    )


def _route_fact(payload: dict) -> RouteCandidateFact:
    return RouteCandidateFact(
        route_id=payload["route_id"],
        route_name=payload["route_name"],
        start_point_name=payload["start_point_name"],
        target_point_name=payload["target_point_name"],
        business_model=payload["business_model"],
        route_legs=tuple(
            RouteLegFact(
                leg_id=str(leg.get("leg_id") or ""),
                country=str(leg.get("country") or ""),
                tso=str(leg.get("tso") or ""),
                market_area=leg.get("market_area"),
                point_name=str(leg.get("point_name") or ""),
                direction=str(leg.get("direction") or ""),
                capacity_product=leg.get("capacity_product"),
                firmness=leg.get("firmness"),
                gas_year=leg.get("gas_year"),
                available_capacity_mwh_per_day=(
                    float(leg["available_capacity_mwh_per_day"])
                    if isinstance(leg.get("available_capacity_mwh_per_day"), int | float)
                    else None
                ),
            )
            for leg in payload.get("route_legs") or []
        ),
        required_entry_point_name=payload.get("required_entry_point_name"),
        required_exit_point_name=payload.get("required_exit_point_name"),
        required_tso_access=tuple(payload.get("required_tso_access") or []),
        source_systems=tuple(payload.get("source_systems") or []),
    )


def _node_fact(row) -> NetworkNodeFact:
    return NetworkNodeFact(
        id=row.id,
        name=row.name,
        node_type=row.node_type,
        country=row.country,
        source_system=row.source_system,
        source_reference=row.source_reference,
        source_record_id=row.source_record_id,
        metadata_json=row.metadata_json or {},
    )


def _access_fact(row) -> CompanyTsoAccessFact:
    return CompanyTsoAccessFact(
        tso=row.tso,
        status=row.status,
        valid_from_utc=row.valid_from_utc,
        valid_to_utc=row.valid_to_utc,
        source_reference=row.source_reference,
    )


def _market_fact(row) -> MarketObservationFact:
    return MarketObservationFact(
        observation_id=row.observation_id,
        market_venue=row.market_venue,
        product=row.product,
        price=row.price,
        unit=row.unit,
        currency=row.currency,
        period_start_utc=row.period_start_utc,
        period_end_utc=row.period_end_utc,
        observed_at_utc=row.observed_at_utc,
        source_system=row.source_system,
        source_reference=row.source_reference,
        freshness=row.freshness,
        quality_score=row.quality_score,
        simulated=_is_simulated_market_row(row),
        metadata_json=row.metadata_json or {},
    )


def _fx_fact(row) -> FxObservationFact:
    return FxObservationFact(
        observation_id=row.observation_id,
        pair=row.pair,
        base_currency=row.base_currency,
        quote_currency=row.quote_currency,
        rate=row.rate,
        value_date=row.value_date,
        observed_at_utc=row.observed_at_utc,
        source_system=row.source_system,
        source_reference=row.source_reference,
    )


def _is_simulated_market_row(row) -> bool:
    metadata = row.metadata_json or {}
    if metadata.get("simulated") is True:
        return True
    source_system = getattr(row, "source_system", None)
    return isinstance(source_system, str) and source_system.endswith("_Sim")


def _jsonable(value: object) -> object:
    """Convert dataclass outputs to JSON-safe containers."""

    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, time):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        from dataclasses import fields

        return {
            field.name: _jsonable(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _envelope(data: object, *, warnings: tuple[str, ...]) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["operator-input"],
            "warnings": list(warnings),
        },
    }


def _invalid_input(exc: ValueError) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={
            "code": "optimization_input_invalid",
            "message": str(exc),
        },
    )


def _require_runtime_db(endpoint: str) -> None:
    if _db_is_configured():
        return
    raise HTTPException(
        status_code=503,
        detail={
            "code": "runtime_db_not_configured",
            "message": f"/api/optimization/{endpoint} RUNTIME_DECISION requires the runtime DB.",
            "research_only": True,
            "human_review_required": True,
        },
    )


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
            "message": "Runtime database is configured but unavailable for optimization reads.",
            "error_class": exc.__class__.__name__,
        },
    )
