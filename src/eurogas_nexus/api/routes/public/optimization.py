"""Public phase-two optimization endpoints."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from eurogas_nexus.optimization import (
    CapacityProduct,
    NetworkEdge,
    PhaseTwoOptimizer,
    SaleOption,
    SupplyResource,
)

router = APIRouter(prefix="/api/optimization", tags=["optimization"])


class SupplyResourceRequest(BaseModel):
    resource_id: str = Field(min_length=1, max_length=128)
    available_mwh: float = Field(ge=0)
    unit_cost_gbp_mwh: float
    minimum_take_mwh: float = Field(default=0, ge=0)
    maximum_take_mwh: float | None = Field(default=None, ge=0)
    source_node: str | None = None
    required_tso_access: list[str] = Field(default_factory=list)

    def to_domain(self) -> SupplyResource:
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
    option_id: str = Field(min_length=1, max_length=128)
    destination_node: str = Field(min_length=1, max_length=128)
    sale_price_gbp_mwh: float
    capacity_mwh: float = Field(ge=0)
    variable_cost_gbp_mwh: float = 0
    required_tso_access: list[str] = Field(default_factory=list)

    def to_domain(self) -> SaleOption:
        return SaleOption(
            option_id=self.option_id,
            destination_node=self.destination_node,
            sale_price_gbp_mwh=self.sale_price_gbp_mwh,
            capacity_mwh=self.capacity_mwh,
            variable_cost_gbp_mwh=self.variable_cost_gbp_mwh,
            required_tso_access=tuple(self.required_tso_access),
        )


class NetworkEdgeRequest(BaseModel):
    edge_id: str = Field(min_length=1, max_length=128)
    source: str = Field(min_length=1, max_length=128)
    target: str = Field(min_length=1, max_length=128)
    tariff_gbp_mwh: float = Field(ge=0)
    available_capacity_mwh: float = Field(ge=0)
    tso: str | None = None
    enabled: bool = True

    def to_domain(self) -> NetworkEdge:
        return NetworkEdge(**self.model_dump())


class CapacityProductRequest(BaseModel):
    product_id: str = Field(min_length=1, max_length=128)
    capacity_mwh: float = Field(ge=0)
    fixed_cost_gbp: float = Field(ge=0)
    variable_cost_gbp_mwh: float = Field(default=0, ge=0)
    firmness: str = Field(default="firm", pattern="^(firm|interruptible)$")

    def to_domain(self) -> CapacityProduct:
        return CapacityProduct(
            product_id=self.product_id,
            capacity_mwh=self.capacity_mwh,
            fixed_cost_gbp=self.fixed_cost_gbp,
            variable_cost_gbp_mwh=self.variable_cost_gbp_mwh,
            firmness=self.firmness,  # type: ignore[arg-type]
        )


class RouteOptimizationRequest(BaseModel):
    source: str = Field(min_length=1, max_length=128)
    target: str = Field(min_length=1, max_length=128)
    required_capacity_mwh: float = Field(ge=0)
    accessible_tsos: list[str] | None = None
    edges: list[NetworkEdgeRequest]


class ResourcePoolOptimizationRequest(BaseModel):
    resources: list[SupplyResourceRequest]
    sale_options: list[SaleOptionRequest]
    accessible_tsos: list[str] | None = None


class CapacityOptimizationRequest(BaseModel):
    products: list[CapacityProductRequest]
    required_capacity_mwh: float = Field(ge=0)
    expected_throughput_mwh: float | None = Field(default=None, ge=0)
    allow_interruptible: bool = True


class ContractOptimizationRequest(BaseModel):
    resources: list[SupplyResourceRequest]
    market_price_gbp_mwh: float
    demand_limit_mwh: float = Field(ge=0)


@router.post("/route")
def optimize_route(body: RouteOptimizationRequest) -> dict:
    """Return a minimum-cost route satisfying capacity and TSO-access constraints."""

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
    return _envelope(asdict(result), warnings=result.warnings)


@router.post("/resource-pool")
def optimize_resource_pool(body: ResourcePoolOptimizationRequest) -> dict:
    """Allocate upstream resources across sale options under commercial constraints."""

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
    return _envelope(asdict(result), warnings=result.warnings)


@router.post("/capacity")
def optimize_capacity(body: CapacityOptimizationRequest) -> dict:
    """Choose the lowest-cost capacity product combination covering required capacity."""

    try:
        result = PhaseTwoOptimizer().optimize_capacity(
            products=[product.to_domain() for product in body.products],
            required_capacity_mwh=body.required_capacity_mwh,
            expected_throughput_mwh=body.expected_throughput_mwh,
            allow_interruptible=body.allow_interruptible,
        )
    except ValueError as exc:
        raise _invalid_input(exc) from exc
    return _envelope(asdict(result), warnings=result.warnings)


@router.post("/contracts")
def optimize_contracts(body: ContractOptimizationRequest) -> dict:
    """Recommend mandatory and discretionary daily contract takes."""

    try:
        result = PhaseTwoOptimizer().optimize_contracts(
            resources=[resource.to_domain() for resource in body.resources],
            market_price_gbp_mwh=body.market_price_gbp_mwh,
            demand_limit_mwh=body.demand_limit_mwh,
        )
    except ValueError as exc:
        raise _invalid_input(exc) from exc
    return _envelope(asdict(result), warnings=result.warnings)


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
