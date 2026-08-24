"""DB-composed portfolio network optimization (R31).

This module is the pure composition contract for ``POST
/api/optimization/portfolio-network``. The API layer reads PostgreSQL rows and
maps them into the typed fact records below; no web-framework, ORM, or client
payload reaches this module.

The composition contract is deliberately strict:

- a route can only be sold when every required input exists and is fresh enough;
- TSO access is ``ACTIVE``/``CONFIRMED`` only and fails closed otherwise;
- route capacity comes from PostgreSQL-owned route-candidate legs, never from
  the API client;
- market and tariff amounts are converted to GBP/MWh as-of the requested gas
  day; unsupported units block rather than approximate.

Optimization reuses the residual shared-capacity network-flow engine. Final
flows are decomposed into source-to-sale paths so each upstream contract
receives an explicit PnL attribution.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time
from typing import Any

from pydantic import ValidationError

from eurogas_nexus.domain.market_intelligence.normalized_view import (
    FxRateInput,
    convert_currency,
)
from eurogas_nexus.domain.route_cost.route_cost_service import calculate_route_cost
from eurogas_nexus.domain.route_cost.schemas import RouteCostScenario, RouteTariffLeg
from eurogas_nexus.domain.route_cost.tariff_models import CapacityTariff
from eurogas_nexus.optimization.models import NetworkEdge, SaleOption, SupplyResource
from eurogas_nexus.optimization.network_flow import (
    FlowDemand,
    FlowSupply,
    NetworkFlowResult,
    optimize_network_flow,
)

_TOLERANCE = 1e-9
_DEFAULT_MARKET_PRICE_MAX_AGE_HOURS = 72.0
_SUPPORTED_CAPACITY_PRODUCTS = {
    "ANNUAL",
    "QUARTERLY",
    "MONTHLY",
    "WEEKLY",
    "DAILY",
    "WITHIN_DAY",
}
_SUPPORTED_FIRMNESS = {"FIRM", "INTERRUPTIBLE", "BACKHAUL", "OFF_PEAK"}


# ---------------------------------------------------------------------------
# Typed PostgreSQL fact records
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ContractFact:
    """One upstream resource contract read from PostgreSQL."""

    contract_id: str
    contract_name: str
    resource_type: str
    delivery_point_name: str
    gas_year: str
    delivery_quantity_mwh_per_day: float
    contract_price_gbp_mwh: float
    tolerance_risk_allowance_gbp_mwh: float = 0.0
    allowed_exit_points: tuple[str, ...] = ()
    eligible_sale_modes: tuple[str, ...] = ()
    updated_at_utc: str | None = None


@dataclass(frozen=True, slots=True)
class RouteLegFact:
    """One route-candidate leg read from PostgreSQL."""

    leg_id: str
    country: str = ""
    tso: str = ""
    market_area: str | None = None
    point_name: str = ""
    direction: str = ""
    capacity_product: str | None = None
    firmness: str | None = None
    gas_year: str | None = None
    available_capacity_mwh_per_day: float | None = None


@dataclass(frozen=True, slots=True)
class RouteCandidateFact:
    """One active route candidate read from PostgreSQL."""

    route_id: str
    route_name: str
    start_point_name: str
    target_point_name: str
    business_model: str
    route_legs: tuple[RouteLegFact, ...] = ()
    required_entry_point_name: str | None = None
    required_exit_point_name: str | None = None
    required_tso_access: tuple[str, ...] = ()
    source_systems: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NetworkNodeFact:
    """One reference-network node read from PostgreSQL."""

    id: str
    name: str
    node_type: str
    country: str = ""
    source_system: str | None = None
    source_reference: str | None = None
    source_record_id: str | None = None
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CompanyTsoAccessFact:
    """One company TSO access posture row read from PostgreSQL."""

    tso: str
    status: str
    valid_from_utc: datetime
    valid_to_utc: datetime | None = None
    source_reference: str = ""


@dataclass(frozen=True, slots=True)
class MarketObservationFact:
    """One market observation read from PostgreSQL."""

    observation_id: str
    market_venue: str
    product: str
    price: float
    unit: str
    currency: str
    period_start_utc: datetime | None
    period_end_utc: datetime | None
    observed_at_utc: datetime
    source_system: str
    source_reference: str
    freshness: str
    quality_score: float
    simulated: bool
    metadata_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FxObservationFact:
    """One FX reference observation read from PostgreSQL."""

    observation_id: str
    pair: str
    base_currency: str
    quote_currency: str
    rate: float
    value_date: str
    observed_at_utc: datetime
    source_system: str
    source_reference: str


# ---------------------------------------------------------------------------
# Composition result
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ComposedPortfolioNetwork:
    """A complete PostgreSQL-owned portfolio network snapshot.

    ``is_complete`` is false when any blocker exists. Blocked snapshots must
    never be passed to the optimizer; the API fails closed before doing so.
    """

    resources: tuple[SupplyResource, ...] = ()
    sale_options: tuple[SaleOption, ...] = ()
    edges: tuple[NetworkEdge, ...] = ()
    resource_lineage: tuple[dict[str, Any], ...] = ()
    sale_option_lineage: tuple[dict[str, Any], ...] = ()
    edge_lineage: tuple[dict[str, Any], ...] = ()
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    missing_inputs: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = ()

    @property
    def is_complete(self) -> bool:
        """True when the snapshot has no blockers."""

        return not self.blockers


# ---------------------------------------------------------------------------
# Composition
# ---------------------------------------------------------------------------


def compose_portfolio_network(
    *,
    contracts: Sequence[ContractFact],
    routes: Sequence[RouteCandidateFact],
    nodes: Sequence[NetworkNodeFact],
    tariffs: Sequence[CapacityTariff],
    access_rows: Sequence[CompanyTsoAccessFact],
    market_rows: Sequence[MarketObservationFact],
    fx_rows: Sequence[FxObservationFact],
    gas_day: date,
    capacity_product: str = "ANNUAL",
    firmness: str = "FIRM",
    max_market_price_age_hours: float = _DEFAULT_MARKET_PRICE_MAX_AGE_HOURS,
    now_utc: datetime | None = None,
) -> ComposedPortfolioNetwork:
    """Compose contracts, sale routes, tariffs, TSO access, and market prices.

    Args:
        contracts: Upstream resource contracts from PostgreSQL.
        routes: Active route candidates from PostgreSQL.
        nodes: Reference network nodes from PostgreSQL.
        tariffs: Effective tariff domain rows from PostgreSQL.
        access_rows: Company TSO access posture rows from PostgreSQL.
        market_rows: Market observations from PostgreSQL.
        fx_rows: FX reference rows from PostgreSQL.
        gas_day: Requested gas day.
        capacity_product: Capacity product for tariff selection.
        firmness: Firmness class for tariff selection.
        max_market_price_age_hours: Maximum market observation age in hours.
        now_utc: Evaluation clock; defaults to the current UTC time.

    Returns:
        A typed composition. Callers must check ``is_complete``.
    """

    normalized_product = (capacity_product or "ANNUAL").strip().upper()
    normalized_firmness = (firmness or "FIRM").strip().upper()
    if normalized_product not in _SUPPORTED_CAPACITY_PRODUCTS:
        raise ValueError(f"unsupported capacity_product: {capacity_product}")
    if normalized_firmness not in _SUPPORTED_FIRMNESS:
        raise ValueError(f"unsupported firmness: {firmness}")

    now = _as_utc(now_utc or datetime.now(UTC))
    gas_day_end_utc = datetime.combine(gas_day, time(23, 59, 59), tzinfo=UTC)
    market_clock = min(now, gas_day_end_utc)
    blockers: list[str] = []
    warnings: list[str] = []
    assumptions: list[str] = []
    source_refs: list[str] = []

    if not contracts:
        blockers.append("UPSTREAM_CONTRACTS_MISSING")
    if not routes:
        blockers.append("ROUTE_CANDIDATES_MISSING")
    if not nodes:
        blockers.append("REFERENCE_NODES_MISSING")

    node_lookup = _build_node_lookup(nodes)
    active_access, denied_access = _access_sets(access_rows, gas_day)
    total_contract_volume = sum(
        float(contract.delivery_quantity_mwh_per_day) for contract in contracts
    )

    resources: list[SupplyResource] = []
    resource_lineage: list[dict[str, Any]] = []
    allowed_targets: set[str] = set()
    for contract in contracts:
        source_node = _resolve_node(node_lookup, contract.delivery_point_name)
        if source_node is None:
            blockers.append(f"SUPPLY_NODE_MISSING:{contract.contract_id}")
            continue
        resources.append(
            SupplyResource(
                resource_id=contract.contract_id,
                available_mwh=float(contract.delivery_quantity_mwh_per_day),
                unit_cost_gbp_mwh=(
                    float(contract.contract_price_gbp_mwh)
                    + float(contract.tolerance_risk_allowance_gbp_mwh)
                ),
                source_node=source_node.id,
            )
        )
        resource_lineage.append(
            {
                "contract_id": contract.contract_id,
                "contract_name": contract.contract_name,
                "delivery_point_name": contract.delivery_point_name,
                "source_node_id": source_node.id,
                "delivery_quantity_mwh_per_day": float(
                    contract.delivery_quantity_mwh_per_day
                ),
                "contract_price_gbp_mwh": float(contract.contract_price_gbp_mwh),
                "tolerance_risk_allowance_gbp_mwh": float(
                    contract.tolerance_risk_allowance_gbp_mwh
                ),
                "updated_at_utc": contract.updated_at_utc,
                "source_refs": [f"upstream_resource_contract:{contract.contract_id}"],
            }
        )
        for point_name in [contract.delivery_point_name, *contract.allowed_exit_points]:
            key = _normalise_key(point_name)
            if key:
                allowed_targets.add(key)

    sale_options: list[SaleOption] = []
    sale_option_lineage: list[dict[str, Any]] = []
    edges: list[NetworkEdge] = []
    edge_lineage: list[dict[str, Any]] = []

    for lineage_item in resource_lineage:
        source_refs.extend(lineage_item["source_refs"])

    resource_node_ids = {
        resource_lineage_item["source_node_id"]
        for resource_lineage_item in resource_lineage
    }

    for route in routes:
        route_id = route.route_id.strip()
        if not route_id:
            blockers.append("ROUTE_ID_EMPTY")
            continue

        start_node = _resolve_node(node_lookup, route.start_point_name)
        target_node = _resolve_node(node_lookup, route.target_point_name)
        if start_node is None or target_node is None:
            blockers.append(f"ROUTE_NODE_MISSING:{route_id}")
            continue

        if resource_node_ids and start_node.id not in resource_node_ids:
            warnings.append(f"ROUTE_START_NOT_IN_RESOURCE_POOL:{route_id}")
            continue

        target_key = _normalise_key(route.target_point_name)
        if allowed_targets and target_key not in allowed_targets:
            warnings.append(f"ROUTE_TARGET_NOT_ALLOWED_BY_CONTRACT:{route_id}")
            continue

        required_access = tuple(
            sorted({tso.strip() for tso in route.required_tso_access if tso.strip()})
        )
        denied = [
            tso for tso in required_access if tso.casefold() in denied_access
        ]
        missing = [
            tso for tso in required_access if tso.casefold() not in active_access
        ]
        if denied:
            blockers.append(f"TSO_ACCESS_DENIED:{route_id}:{','.join(denied)}")
            continue
        if missing:
            blockers.append(f"TSO_ACCESS_MISSING:{route_id}:{','.join(missing)}")
            continue

        market_price = _latest_market_price(
            market_rows,
            target_point_name=route.target_point_name,
            target_node=target_node,
            gas_day=gas_day,
            now_utc=market_clock,
            max_age_hours=max_market_price_age_hours,
        )
        if market_price is None:
            blockers.append(f"MARKET_PRICE_MISSING:{route.target_point_name}")
            continue
        if market_price.get("stale") is True:
            blockers.append(
                f"MARKET_PRICE_STALE:{route.target_point_name}:"
                f"{market_price['observation_id']}"
            )
            continue

        sale_price_gbp, sale_provenance, sale_error = _money_to_gbp_mwh(
            market_price["price"],
            market_price["currency"],
            market_price["unit"],
            fx_rows=fx_rows,
            asof_date=gas_day,
        )
        if sale_price_gbp is None:
            blockers.append(
                f"MARKET_PRICE_CONVERSION_BLOCKED:{route.target_point_name}:{sale_error}"
            )
            continue

        option_id = f"route:{route_id}"
        is_local_sale = start_node.id == target_node.id
        route_capacity: float | None = None
        route_cost_gbp_mwh: float = 0.0
        route_source_refs: list[str] = [
            f"route_candidate:{route_id}",
            *(route.source_systems or []),
        ]

        if is_local_sale:
            sale_capacity = max(total_contract_volume, 0.0)
            edge_ids: list[str] = []
            edge_refs: list[str] = []
        else:
            route_capacity, capacity_refs = _route_capacity(route.route_legs)
            if route_capacity is None or route_capacity <= _TOLERANCE:
                blockers.append(f"ROUTE_CAPACITY_UNKNOWN:{route_id}")
                continue
            route_cost_gbp_mwh, cost_refs, cost_blockers, cost_warnings = (
                _route_cost_gbp_mwh(
                    route=route,
                    tariffs=tariffs,
                    gas_day=gas_day,
                    capacity_product=normalized_product,
                    firmness=normalized_firmness,
                    active_access=active_access,
                    fx_rows=fx_rows,
                )
            )
            warnings.extend(f"{warning}:{route_id}" for warning in cost_warnings)
            route_source_refs.extend(cost_refs)
            if cost_blockers:
                blockers.extend(
                    f"{blocker}:{route_id}" for blocker in cost_blockers
                )
                continue
            edge_id = f"route:{route_id}"
            edges.append(
                NetworkEdge(
                    edge_id=edge_id,
                    source=start_node.id,
                    target=target_node.id,
                    tariff_gbp_mwh=route_cost_gbp_mwh,
                    available_capacity_mwh=route_capacity,
                    tso=required_access[0] if required_access else None,
                )
            )
            edge_lineage.append(
                {
                    "edge_id": edge_id,
                    "route_id": route_id,
                    "route_name": route.route_name,
                    "source_node_id": start_node.id,
                    "target_node_id": target_node.id,
                    "tariff_gbp_mwh": route_cost_gbp_mwh,
                    "available_capacity_mwh": route_capacity,
                    "capacity_source_refs": capacity_refs,
                    "tariff_source_refs": cost_refs,
                    "required_tso_access": list(required_access),
                    "source_refs": route_source_refs,
                }
            )
            sale_capacity = route_capacity
            edge_ids = [edge_id]
            edge_refs = cost_refs

        sale_options.append(
            SaleOption(
                option_id=option_id,
                destination_node=target_node.id,
                sale_price_gbp_mwh=sale_price_gbp,
                capacity_mwh=sale_capacity,
                variable_cost_gbp_mwh=0.0,
                required_tso_access=required_access,
            )
        )
        sale_option_lineage.append(
            {
                "option_id": option_id,
                "route_id": route_id,
                "route_name": route.route_name,
                "delivery_mode": (
                    "VIRTUAL_HUB_SALE" if is_local_sale else "BORDER_TRANSFER"
                ),
                "target_point_name": route.target_point_name,
                "target_node_id": target_node.id,
                "sale_price_gbp_mwh": sale_price_gbp,
                "sale_price_currency": "GBP",
                "sale_price_unit": "GBP/MWh",
                "sale_price_observation_id": market_price["observation_id"],
                "sale_price_observed_at_utc": market_price["observed_at_utc"],
                "sale_price_freshness": market_price["freshness"],
                "sale_price_quality_score": market_price["quality_score"],
                "sale_price_simulated": market_price["simulated"],
                "sale_price_source_family": market_price["source_family"],
                "sale_price_tenor": market_price["tenor"],
                "sale_price_age_hours": market_price["age_hours"],
                **sale_provenance,
                "route_cost_gbp_mwh": route_cost_gbp_mwh,
                "capacity_limit_mwh_per_day": sale_capacity,
                "required_tso_access": list(required_access),
                "source_refs": [
                    *route_source_refs,
                    market_price["source_reference"],
                ],
                "path_edge_ids": edge_ids,
                "path_source_refs": edge_refs,
            }
        )
        source_refs.extend(sale_option_lineage[-1]["source_refs"])

    if not resources:
        blockers.append("PORTFOLIO_RESOURCES_UNAVAILABLE")
    if not sale_options:
        blockers.append("SALE_OPTIONS_UNAVAILABLE")
    if resources and not edges and sale_options and not all(
        option.destination_node == resources[0].source_node
        for option in sale_options
    ):
        blockers.append("ROUTE_EDGES_UNAVAILABLE")

    assumptions.extend(
        [
            "Contract delivery quantity is the available supply for the requested gas day.",
            "Route-candidate leg capacity is authoritative until a fresher DB capacity "
            "observation replaces it.",
            "Market prices are selected from PostgreSQL rows covering the gas day; "
            "simulated rows are ranked after non-simulated rows.",
            "Market-price age is measured against min(now, gas-day end), so a "
            "historical gas-day decision does not become stale merely because "
            "it is evaluated after the gas day.",
            "FX conversion is as-of the requested gas day and fails closed when no "
            "rate is available.",
            "Only tariff rows whose effective window covers the requested gas day "
            "are eligible for selection.",
        ]
    )

    return ComposedPortfolioNetwork(
        resources=tuple(resources),
        sale_options=tuple(sale_options),
        edges=tuple(edges),
        resource_lineage=tuple(resource_lineage),
        sale_option_lineage=tuple(sale_option_lineage),
        edge_lineage=tuple(edge_lineage),
        blockers=tuple(_unique(blockers)),
        warnings=tuple(_unique(warnings)),
        missing_inputs=tuple(_unique(blockers)),
        assumptions=tuple(_unique(assumptions)),
        source_refs=tuple(_unique(source_refs)),
    )


# ---------------------------------------------------------------------------
# Optimization and attribution
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class PortfolioEdgeFlow:
    """Final flow on one composed route edge."""

    edge_id: str
    route_id: str
    quantity_mwh: float
    tariff_gbp_mwh: float
    cost_gbp: float


@dataclass(frozen=True, slots=True)
class PathAllocation:
    """One reconstructed source-to-sale path allocation."""

    resource_id: str
    option_id: str
    quantity_mwh: float
    unit_margin_gbp_mwh: float
    pnl_gbp: float
    path_edge_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class OptionAttribution:
    """Contract-level PnL attribution to one sale option."""

    option_id: str
    quantity_mwh: float
    revenue_gbp: float
    supply_cost_gbp: float
    network_cost_gbp: float
    pnl_gbp: float


@dataclass(frozen=True, slots=True)
class ContractAttribution:
    """PnL attribution for one upstream contract."""

    contract_id: str
    quantity_mwh: float
    revenue_gbp: float
    supply_cost_gbp: float
    network_cost_gbp: float
    pnl_gbp: float
    option_flows: tuple[OptionAttribution, ...] = ()


@dataclass(frozen=True, slots=True)
class PortfolioNetworkOptimizationResult:
    """Trader-reviewed portfolio network optimization result."""

    status: str
    objective_value_gbp: float
    served_demand_mwh: float
    unserved_demand_mwh: float
    total_revenue_gbp: float
    total_supply_cost_gbp: float
    total_network_cost_gbp: float
    edge_flows: tuple[PortfolioEdgeFlow, ...] = ()
    allocations: tuple[PathAllocation, ...] = ()
    contract_attributions: tuple[ContractAttribution, ...] = ()
    warnings: tuple[str, ...] = ()
    diagnostics: dict[str, Any] = field(default_factory=dict)
    human_review_required: bool = True


def optimize_composed_portfolio_network(
    composition: ComposedPortfolioNetwork,
) -> PortfolioNetworkOptimizationResult:
    """Optimize a completed PostgreSQL-owned composition and attribute PnL.

    Args:
        composition: A composition whose ``is_complete`` is true.

    Returns:
        A deterministic result with path-level and contract-level attribution.

    Raises:
        ValueError: When the composition is incomplete or invalid.
    """

    if not composition.is_complete:
        raise ValueError("composition is blocked and must not be optimized")

    resources = list(composition.resources)
    sale_options = list(composition.sale_options)
    edges = list(composition.edges)
    resource_by_id = {resource.resource_id: resource for resource in resources}
    option_by_id = {option.option_id: option for option in sale_options}
    edge_by_id = {edge.edge_id: edge for edge in edges}

    supplies = [
        FlowSupply(
            node=resource.source_node,
            available_mwh=resource.available_mwh,
            unit_cost_gbp_mwh=resource.unit_cost_gbp_mwh,
            supply_id=resource.resource_id,
        )
        for resource in resources
        if resource.source_node
    ]
    demands = [
        FlowDemand(
            node=option.destination_node,
            required_mwh=option.capacity_mwh,
            value_gbp_mwh=option.sale_price_gbp_mwh - option.variable_cost_gbp_mwh,
            demand_id=option.option_id,
            optional=True,
        )
        for option in sale_options
    ]
    if any(resource.source_node is None for resource in resources):
        raise ValueError("every composed resource must have a source node")

    flow = optimize_network_flow(edges, supplies, demands)
    edge_flows = tuple(
        PortfolioEdgeFlow(
            edge_id=item.edge_id,
            route_id=_route_id_from_edge(item.edge_id),
            quantity_mwh=item.quantity_mwh,
            tariff_gbp_mwh=edge_by_id[item.edge_id].tariff_gbp_mwh,
            cost_gbp=_clean_number(
                item.quantity_mwh * edge_by_id[item.edge_id].tariff_gbp_mwh
            ),
        )
        for item in flow.edge_flows
        if item.edge_id in edge_by_id
    )
    allocations, attribution_warnings = _attribute_flows(
        flow=flow,
        resources=resource_by_id,
        options=option_by_id,
        edges=edge_by_id,
    )

    revenue = sum(
        option.sale_price_gbp_mwh * _served_quantity(flow, option.option_id)
        for option in sale_options
    )
    supply_cost = sum(
        resource.unit_cost_gbp_mwh * _used_quantity(flow, resource.resource_id)
        for resource in resources
    )
    network_cost = flow.total_network_cost_gbp - supply_cost

    contract_attributions = _contract_attributions(
        allocations,
        resource_by_id=resource_by_id,
        option_by_id=option_by_id,
        edges=edge_by_id,
    )

    objective = sum(attribution.pnl_gbp for attribution in contract_attributions)
    warnings = _unique([*flow.warnings, *attribution_warnings])
    return PortfolioNetworkOptimizationResult(
        status=flow.status,
        objective_value_gbp=_clean_number(objective),
        served_demand_mwh=_clean_number(flow.served_demand_mwh),
        unserved_demand_mwh=_clean_number(flow.unserved_demand_mwh),
        total_revenue_gbp=_clean_number(revenue),
        total_supply_cost_gbp=_clean_number(supply_cost),
        total_network_cost_gbp=_clean_number(network_cost),
        edge_flows=edge_flows,
        allocations=tuple(allocations),
        contract_attributions=contract_attributions,
        warnings=tuple(warnings),
        diagnostics={
            "resource_count": len(resources),
            "sale_option_count": len(sale_options),
            "edge_count": len(edges),
            "path_count": len(allocations),
            "solver_objective_gbp": _clean_number(flow.total_objective_gbp),
        },
    )


def _attribute_flows(
    *,
    flow: NetworkFlowResult,
    resources: dict[str, SupplyResource],
    options: dict[str, SaleOption],
    edges: dict[str, NetworkEdge],
) -> tuple[list[PathAllocation], list[str]]:
    """Decompose final network flows into deterministic source-to-sale paths."""

    supply_usage = {
        item.supply_id: item.quantity_mwh for item in flow.supply_usage
    }
    demand_service = {
        item.demand_id: item.quantity_mwh for item in flow.demand_service
    }
    edge_flow = {item.edge_id: item.quantity_mwh for item in flow.edge_flows}

    arcs: dict[str, tuple[str, str, float]] = {}
    for supply_id, quantity in supply_usage.items():
        if quantity <= _TOLERANCE:
            continue
        arcs[f"supply:{supply_id}"] = (
            "__source__",
            resources[supply_id].source_node or "",
            quantity,
        )
    for edge_id, quantity in edge_flow.items():
        if quantity <= _TOLERANCE or edge_id not in edges:
            continue
        edge = edges[edge_id]
        arcs[edge_id] = (edge.source, edge.target, quantity)
    for demand_id, quantity in demand_service.items():
        if quantity <= _TOLERANCE or demand_id not in options:
            continue
        option = options[demand_id]
        arcs[f"demand:{demand_id}"] = (
            option.destination_node,
            "__sink__",
            quantity,
        )

    allocations: list[PathAllocation] = []
    warnings: list[str] = []
    remaining = {arc_id: quantity for arc_id, (_, _, quantity) in arcs.items()}

    while True:
        path_ids = _find_positive_flow_path(arcs, remaining)
        if path_ids is None:
            # A pure circulation cannot be attributed to a sale path; report
            # it instead of silently inventing PnL. The validated flow model
            # should not produce one for this single-commodity formulation.
            if any(quantity > _TOLERANCE for quantity in remaining.values()):
                warnings.append("FLOW_ATTRIBUTION_CIRCULATION_REMAINS")
            break

        path_quantity = min(
            remaining[arc_id] for arc_id in path_ids if remaining[arc_id] > 0
        )
        for arc_id in path_ids:
            remaining[arc_id] = _clean_number(remaining[arc_id] - path_quantity)

        supply_id = _arc_business_id(path_ids, "supply:")
        demand_id = _arc_business_id(path_ids, "demand:")
        if supply_id is None or demand_id is None:
            warnings.append("FLOW_ATTRIBUTION_PATH_MISSING_ENDPOINTS")
            continue
        if supply_id not in resources or demand_id not in options:
            continue

        path_edge_ids = tuple(
            arc_id for arc_id in path_ids if not arc_id.startswith(("supply:", "demand:"))
        )
        supply = resources[supply_id]
        option = options[demand_id]
        total_cost = supply.unit_cost_gbp_mwh + sum(
            edges[edge_id].tariff_gbp_mwh for edge_id in path_edge_ids
        )
        unit_margin = (
            option.sale_price_gbp_mwh
            - option.variable_cost_gbp_mwh
            - total_cost
        )
        allocations.append(
            PathAllocation(
                resource_id=supply_id,
                option_id=demand_id,
                quantity_mwh=_clean_number(path_quantity),
                unit_margin_gbp_mwh=_clean_number(unit_margin),
                pnl_gbp=_clean_number(path_quantity * unit_margin),
                path_edge_ids=path_edge_ids,
            )
        )

    allocations.sort(
        key=lambda item: (
            item.resource_id,
            item.option_id,
            item.path_edge_ids,
            item.quantity_mwh,
        )
    )
    return allocations, warnings


def _find_positive_flow_path(
    arcs: dict[str, tuple[str, str, float]],
    remaining: dict[str, float],
) -> list[str] | None:
    """BFS over positive final-flow arcs from the super source to super sink."""

    adjacency: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for arc_id, (source, target, _) in arcs.items():
        if remaining.get(arc_id, 0.0) > _TOLERANCE:
            adjacency[source].append((arc_id, target))
    for arcs_from_node in adjacency.values():
        arcs_from_node.sort(key=lambda item: item[0])

    queue: deque[tuple[str, list[str]]] = deque([("__source__", [])])
    visited = {"__source__"}
    while queue:
        node, path = queue.popleft()
        for arc_id, target in adjacency.get(node, []):
            if target in visited:
                continue
            next_path = [*path, arc_id]
            if target == "__sink__":
                return next_path
            visited.add(target)
            queue.append((target, next_path))
    return None


def _arc_business_id(path_ids: Iterable[str], prefix: str) -> str | None:
    for arc_id in path_ids:
        if arc_id.startswith(prefix):
            return arc_id[len(prefix) :]
    return None


def _contract_attributions(
    allocations: Sequence[PathAllocation],
    *,
    resource_by_id: dict[str, SupplyResource],
    option_by_id: dict[str, SaleOption],
    edges: dict[str, NetworkEdge],
) -> tuple[ContractAttribution, ...]:
    """Aggregate path allocations into contract-level PnL attribution."""

    grouped: dict[str, list[PathAllocation]] = defaultdict(list)
    for allocation in allocations:
        grouped[allocation.resource_id].append(allocation)

    result: list[ContractAttribution] = []
    for contract_id in sorted(grouped):
        allocations_for_contract = grouped[contract_id]
        resource = resource_by_id[contract_id]
        option_flows: list[OptionAttribution] = []
        for option_id in sorted({item.option_id for item in allocations_for_contract}):
            option = option_by_id[option_id]
            paths = [
                item for item in allocations_for_contract if item.option_id == option_id
            ]
            quantity = sum(item.quantity_mwh for item in paths)
            revenue = quantity * (
                option.sale_price_gbp_mwh - option.variable_cost_gbp_mwh
            )
            supply_cost = quantity * resource.unit_cost_gbp_mwh
            network_cost = sum(
                item.quantity_mwh
                * sum(edges[edge_id].tariff_gbp_mwh for edge_id in item.path_edge_ids)
                for item in paths
            )
            option_flows.append(
                OptionAttribution(
                    option_id=option_id,
                    quantity_mwh=_clean_number(quantity),
                    revenue_gbp=_clean_number(revenue),
                    supply_cost_gbp=_clean_number(supply_cost),
                    network_cost_gbp=_clean_number(network_cost),
                    pnl_gbp=_clean_number(revenue - supply_cost - network_cost),
                )
            )
        total_quantity = sum(item.quantity_mwh for item in allocations_for_contract)
        total_revenue = sum(item.revenue_gbp for item in option_flows)
        total_supply_cost = sum(item.supply_cost_gbp for item in option_flows)
        total_network_cost = sum(item.network_cost_gbp for item in option_flows)
        result.append(
            ContractAttribution(
                contract_id=contract_id,
                quantity_mwh=_clean_number(total_quantity),
                revenue_gbp=_clean_number(total_revenue),
                supply_cost_gbp=_clean_number(total_supply_cost),
                network_cost_gbp=_clean_number(total_network_cost),
                pnl_gbp=_clean_number(total_revenue - total_supply_cost - total_network_cost),
                option_flows=tuple(option_flows),
            )
        )
    return tuple(result)


def _served_quantity(flow: NetworkFlowResult, demand_id: str) -> float:
    return next(
        (item.quantity_mwh for item in flow.demand_service if item.demand_id == demand_id),
        0.0,
    )


def _used_quantity(flow: NetworkFlowResult, supply_id: str) -> float:
    return next(
        (item.quantity_mwh for item in flow.supply_usage if item.supply_id == supply_id),
        0.0,
    )


# ---------------------------------------------------------------------------
# Fact mapping and selection helpers
# ---------------------------------------------------------------------------


def _build_node_lookup(nodes: Sequence[NetworkNodeFact]) -> dict[str, NetworkNodeFact]:
    lookup: dict[str, NetworkNodeFact] = {}
    for node in nodes:
        keys = [
            node.id,
            node.name,
            node.source_record_id,
            (node.metadata_json or {}).get("market_code"),
            (node.metadata_json or {}).get("point_key"),
        ]
        for value in keys:
            key = _normalise_key(value)
            if key and key not in lookup:
                lookup[key] = node
    return lookup


def _resolve_node(
    lookup: dict[str, NetworkNodeFact],
    point_name: str,
) -> NetworkNodeFact | None:
    key = _normalise_key(point_name)
    if key and key in lookup:
        return lookup[key]
    # Fallback inside the typed contract: a caller may already pass node ids
    # as the point name (still PostgreSQL-owned, never client payload).
    for node in lookup.values():
        if node.id == point_name or node.name.casefold() == point_name.casefold():
            return node
    return None


def _access_sets(
    rows: Sequence[CompanyTsoAccessFact],
    gas_day: date,
) -> tuple[set[str], set[str]]:
    at_utc = datetime.combine(gas_day, time.min, tzinfo=UTC)
    active: set[str] = set()
    denied: set[str] = set()
    for row in rows:
        valid_from = _as_utc(row.valid_from_utc)
        valid_to = _as_utc(row.valid_to_utc) if row.valid_to_utc is not None else None
        if valid_from > at_utc or (valid_to is not None and valid_to < at_utc):
            continue
        tso = row.tso.strip().casefold()
        status = row.status.strip().upper()
        if status in {"ACTIVE", "CONFIRMED"}:
            active.add(tso)
        elif status in {"DENIED", "INACTIVE", "SUSPENDED"}:
            denied.add(tso)
    return active, denied


def _latest_market_price(
    rows: Sequence[MarketObservationFact],
    *,
    target_point_name: str,
    target_node: NetworkNodeFact,
    gas_day: date,
    now_utc: datetime,
    max_age_hours: float,
) -> dict[str, Any] | None:
    target_keys = {
        _normalise_key(target_point_name),
        _normalise_key(target_node.id),
        _normalise_key(target_node.name),
        _normalise_key((target_node.metadata_json or {}).get("point_key")),
        _normalise_key((target_node.metadata_json or {}).get("market_code")),
    }
    candidates: list[tuple[tuple[int, int, float], MarketObservationFact, float]] = []
    for row in rows:
        if not _market_row_matches(row, target_keys):
            continue
        if not _market_row_covers_gas_day(row, gas_day):
            continue
        observed = _as_utc(row.observed_at_utc)
        age_hours = (now_utc - observed).total_seconds() / 3600.0
        priority = (
            _tenor_priority(row),
            1 if row.simulated else 0,
            -observed.timestamp(),
        )
        candidates.append((priority, row, age_hours))
    if not candidates:
        return None

    candidates.sort(key=lambda item: item[0])
    _, row, age_hours = candidates[0]
    metadata = row.metadata_json or {}
    return {
        "observation_id": row.observation_id,
        "market_venue": row.market_venue,
        "product": row.product,
        "price": row.price,
        "currency": row.currency,
        "unit": row.unit,
        "observed_at_utc": row.observed_at_utc.isoformat(),
        "period_start_utc": (
            row.period_start_utc.isoformat() if row.period_start_utc else None
        ),
        "period_end_utc": (
            row.period_end_utc.isoformat() if row.period_end_utc else None
        ),
        "source_system": row.source_system,
        "source_reference": f"market_observation:{row.observation_id}",
        "freshness": row.freshness,
        "quality_score": row.quality_score,
        "simulated": row.simulated,
        "source_family": metadata.get("source_family") or (
            row.source_system.removesuffix("_Sim")
            if row.source_system.endswith("_Sim")
            else row.source_system
        ),
        "tenor": metadata.get("tenor"),
        "age_hours": round(age_hours, 6),
        "stale": age_hours > max_age_hours,
    }


def _market_row_matches(row: MarketObservationFact, target_keys: set[str]) -> bool:
    metadata = row.metadata_json or {}
    keys = {
        _normalise_key(row.market_venue),
        _normalise_key(row.product.split()[0] if row.product.strip() else ""),
        _normalise_key(metadata.get("hub")),
        _normalise_key(metadata.get("point_name")),
        _normalise_key(metadata.get("market_area")),
    }
    keys.discard("")
    return bool(keys & target_keys)


def _market_row_covers_gas_day(row: MarketObservationFact, gas_day: date) -> bool:
    period_start = _as_date(row.period_start_utc)
    period_end = _as_date(row.period_end_utc)
    if period_start is not None and gas_day < period_start:
        return False
    if period_end is not None and gas_day > period_end:
        return False
    return True


def _tenor_priority(row: MarketObservationFact) -> int:
    metadata = row.metadata_json or {}
    tenor = str(metadata.get("tenor") or "").strip().lower()
    if not tenor:
        product = row.product.strip().lower()
        if "within" in product:
            tenor = "within-day"
        elif "day" in product:
            tenor = "day-ahead"
        elif "month" in product:
            tenor = "month-ahead"
    if tenor in {"day-ahead", "within-day"}:
        return 0
    if tenor in {"weekend", "balance-of-week"}:
        return 1
    if tenor in {"month-ahead", "front-month"}:
        return 2
    return 3


def _route_capacity(
    route_legs: Sequence[RouteLegFact],
) -> tuple[float | None, list[str]]:
    capacities: list[float] = []
    refs: list[str] = []
    for leg in route_legs:
        value = leg.available_capacity_mwh_per_day
        if isinstance(value, int | float) and value > _TOLERANCE:
            capacities.append(float(value))
            refs.append(f"route_leg:{leg.leg_id}")
    return (min(capacities), _unique(refs)) if capacities else (None, [])


def _route_cost_gbp_mwh(
    *,
    route: RouteCandidateFact,
    tariffs: Sequence[CapacityTariff],
    gas_day: date,
    capacity_product: str,
    firmness: str,
    active_access: set[str],
    fx_rows: Sequence[FxObservationFact],
) -> tuple[float, list[str], list[str], list[str]]:
    """Calculate a route's all-in tariff and convert it to GBP/MWh."""

    legs: list[RouteTariffLeg] = []
    for leg in route.route_legs:
        try:
            parsed = RouteTariffLeg.model_validate(
                {
                    "leg_id": leg.leg_id,
                    "country": leg.country,
                    "tso": leg.tso,
                    "market_area": leg.market_area,
                    "point_name": leg.point_name,
                    "direction": leg.direction,
                    "gas_year": leg.gas_year,
                    "capacity_product": leg.capacity_product or capacity_product,
                    "firmness": leg.firmness or firmness,
                }
            )
        except ValidationError as exc:
            return 0.0, [], [f"ROUTE_LEG_INVALID:{leg.leg_id}"], [str(exc)]
        legs.append(parsed)

    if not legs:
        return 0.0, [], ["ROUTE_LEGS_MISSING"], []

    effective_tariffs = [
        tariff
        for tariff in tariffs
        if tariff.effective_from <= gas_day
        and (tariff.effective_to is None or tariff.effective_to >= gas_day)
    ]
    scenario = RouteCostScenario(
        scenario_id=f"portfolio-network:{route.route_id}",
        source_resource_type="PIPELINE_IMPORT",
        start_point_id=route.start_point_name,
        target_hub_or_point_id=route.target_point_name,
        business_model=_business_model(route.business_model),
        delivery_mode=(
            "VIRTUAL_HUB_SALE"
            if route.start_point_name.casefold() == route.target_point_name.casefold()
            else "BORDER_TRANSFER"
        ),
        gas_year=legs[0].gas_year or _gas_year(gas_day),
        capacity_product=capacity_product,  # type: ignore[arg-type]
        firmness=firmness,  # type: ignore[arg-type]
        required_tso_access=list(route.required_tso_access),
        company_accessible_tsos=sorted(active_access) if route.required_tso_access else None,
        tariff_legs=legs,
    )
    result = calculate_route_cost(scenario, effective_tariffs)
    cost_blockers: list[str] = [
        *[f"ROUTE_COST_MISSING:{item}" for item in result.missing_inputs],
        *[
            f"ROUTE_COST_MISSING:{warning}"
            for warning in result.warnings
            if warning == "UNIT_CONVERSION_NOT_IMPLEMENTED"
        ],
    ]
    warnings = list(result.warnings)
    if result.total_cost is None:
        cost_blockers.append("ROUTE_COST_MISSING")
        return 0.0, [], _unique(cost_blockers), _unique(warnings)

    cost_gbp, provenance, conversion_error = _money_to_gbp_mwh(
        result.total_cost,
        result.currency,
        result.unit,
        fx_rows=fx_rows,
        asof_date=gas_day,
    )
    if cost_gbp is None:
        cost_blockers.append(f"ROUTE_COST_CONVERSION_BLOCKED:{conversion_error}")
        return 0.0, [], _unique(cost_blockers), _unique(warnings)

    cost_refs = [
        *[
            f"tariff:{component.tariff_id}"
            for component in result.cost_breakdown
            if component.tariff_id
        ],
        *[
            ref
            for component in result.cost_breakdown
            for ref in (component.source_refs or [])
        ],
        *provenance.get("source_refs", []),
    ]
    return round(cost_gbp, 4), _unique(cost_refs), _unique(cost_blockers), _unique(warnings)


def _money_to_gbp_mwh(
    value: float,
    currency: str | None,
    unit: str | None,
    *,
    fx_rows: Sequence[FxObservationFact],
    asof_date: date,
) -> tuple[float | None, dict[str, Any], str | None]:
    """Convert an amount to GBP/MWh with as-of FX provenance."""

    currency_code = _normalise_code(currency)
    compact_unit = re.sub(r"\s+", "", (unit or "")).upper()
    if not compact_unit.endswith("/MWH") and compact_unit != "P/(KWH/H)/H":
        return None, {}, f"TARIFF_UNIT_UNSUPPORTED:{unit}"

    if currency_code == "GBP":
        if compact_unit == "P/(KWH/H)/H":
            # pence per kWh is a standard UK capacity-tariff basis:
            # p/kWh * 1000 kWh/MWh / 100 pence per GBP = GBP/MWh * 10.
            return (
                round(value * 10.0, 4),
                {
                    "fx_converted_from": None,
                    "unit_conversion": "P/(KWH/H)/H->GBP/MWH",
                    "assumption": "1 p/kWh = 10 GBP/MWh (explicit unit conversion).",
                },
                None,
            )
        return round(value, 4), {}, None

    fx_rate_inputs = _fx_rate_inputs_as_of(fx_rows, asof_date)
    converted = convert_currency(value, currency_code, "GBP", fx_rate_inputs)
    if converted is None:
        return None, {}, f"FX_RATE_MISSING:{currency_code}->GBP"
    rate_row = _direct_fx_row(fx_rows, currency_code, "GBP", asof_date)
    provenance: dict[str, Any] = {
        "fx_converted_from": currency_code,
        "fx_rate_used": rate_row.rate if rate_row is not None else None,
        "fx_observation_id": (
            rate_row.observation_id if rate_row is not None else None
        ),
        "fx_value_date": rate_row.value_date if rate_row is not None else None,
        "source_refs": (
            [f"fx_observation:{rate_row.observation_id}"]
            if rate_row is not None
            else []
        ),
    }
    return round(converted, 4), provenance, None


def _fx_rate_inputs_as_of(
    fx_rows: Sequence[FxObservationFact],
    asof_date: date,
) -> list[FxRateInput]:
    rows = [row for row in fx_rows if _fx_value_date(row) <= asof_date]
    return [
        FxRateInput(
            pair=row.pair,
            base_currency=row.base_currency,
            quote_currency=row.quote_currency,
            rate=row.rate,
            observed_at_utc=f"{row.value_date}T00:00:00+00:00",
        )
        for row in rows
        if row.rate > 0
    ]


def _direct_fx_row(
    fx_rows: Sequence[FxObservationFact],
    base: str,
    quote: str,
    asof_date: date,
) -> FxObservationFact | None:
    matches = [
        row
        for row in fx_rows
        if row.base_currency.casefold() == base.casefold()
        and row.quote_currency.casefold() == quote.casefold()
        and _fx_value_date(row) <= asof_date
    ]
    return max(matches, key=_fx_value_date, default=None)


def _fx_value_date(row: FxObservationFact) -> date:
    return _date_from_iso(row.value_date) or date.min


def _business_model(value: str) -> str:
    normalized = (value or "CROSS_BORDER_TRANSFER").strip().upper()
    return normalized if normalized in {
        "VIRTUAL_HUB_SALE",
        "PHYSICAL_DELIVERY",
        "STORAGE_INJECTION",
        "CROSS_BORDER_TRANSFER",
    } else "CROSS_BORDER_TRANSFER"


def _gas_year(gas_day: date) -> str:
    year = gas_day.year if gas_day.month >= 10 else gas_day.year - 1
    return f"{year}+"


def _route_id_from_edge(edge_id: str) -> str:
    return edge_id.removeprefix("route:")


# ---------------------------------------------------------------------------
# Shared small helpers
# ---------------------------------------------------------------------------


def _normalise_key(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"[^a-z0-9]+", "", str(value).casefold())


def _normalise_code(value: str | None) -> str:
    return (value or "").strip().upper()


def _as_utc(value: datetime | None) -> datetime:
    if value is None:
        raise ValueError("expected a datetime value")
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _as_date(value: datetime | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _as_utc(value).date()
    return _date_from_iso(value)


def _date_from_iso(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _clean_number(value: float) -> float:
    return 0.0 if abs(value) <= _TOLERANCE else round(float(value), 10)
