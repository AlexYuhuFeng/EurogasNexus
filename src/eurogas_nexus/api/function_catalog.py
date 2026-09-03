"""Data-science function catalog.

The catalog maps product-facing function names to their canonical REST paths,
SDK methods, MCP tools, and decision contexts. It is the source of truth for
API/MCP encapsulation so LLM agents and programmatic clients expose the same
decision-support vocabulary.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DataScienceFunction:
    """One data-science/trading function exposed through REST and MCP.

    Attributes:
        name: Canonical function name.
        description: Short user/agent-facing description.
        rest_path: Public REST path under ``/api``.
        method: HTTP method used by the canonical path.
        sdk: Python SDK function path.
        mcp: MCP tool name when exposed.
        decision_context: Allowed contexts; ``sandbox`` or ``runtime``.
        persisted_run: Whether the backend persists an optimization run.
    """

    name: str
    description: str
    rest_path: str
    method: str
    sdk: str
    mcp: str | None
    decision_context: str
    persisted_run: bool


FUNCTION_CATALOG: tuple[DataScienceFunction, ...] = (
    DataScienceFunction(
        name="route_cost",
        description="Calculate route cost from explicit tariff legs.",
        rest_path="/api/route-cost/calculate",
        method="POST",
        sdk="eurogas_nexus_sdk.route_cost.calculate_route_cost",
        mcp="calculate_route_cost",
        decision_context="sandbox",
        persisted_run=False,
    ),
    DataScienceFunction(
        name="route_optimization",
        description="Minimum-cost route selection under capacity and TSO access.",
        rest_path="/api/optimization/route",
        method="POST",
        sdk="eurogas_nexus_sdk.optimization.optimize_route",
        mcp="optimize_route_sandbox",
        decision_context="sandbox",
        persisted_run=True,
    ),
    DataScienceFunction(
        name="resource_pool_optimization",
        description="Allocate upstream resources across sale options.",
        rest_path="/api/optimization/resource-pool",
        method="POST",
        sdk="eurogas_nexus_sdk.optimization.optimize_resource_pool",
        mcp="optimize_resource_pool_sandbox",
        decision_context="sandbox",
        persisted_run=True,
    ),
    DataScienceFunction(
        name="capacity_optimization",
        description="Choose lowest-cost capacity products covering required volume.",
        rest_path="/api/optimization/capacity",
        method="POST",
        sdk="eurogas_nexus_sdk.optimization.optimize_capacity",
        mcp="optimize_capacity_sandbox",
        decision_context="sandbox",
        persisted_run=True,
    ),
    DataScienceFunction(
        name="contract_optimization",
        description="Recommend mandatory/discretionary daily contract takes.",
        rest_path="/api/optimization/contracts",
        method="POST",
        sdk="eurogas_nexus_sdk.optimization.optimize_contracts",
        mcp="optimize_contracts_sandbox",
        decision_context="sandbox",
        persisted_run=True,
    ),
    DataScienceFunction(
        name="storage_dispatch",
        description="Assess multi-period storage inject/withdraw/hold dispatch.",
        rest_path="/api/optimization/storage-dispatch",
        method="POST",
        sdk="eurogas_nexus_sdk.optimization.optimize_storage_dispatch",
        mcp="optimize_storage_dispatch_sandbox",
        decision_context="sandbox",
        persisted_run=True,
    ),
    DataScienceFunction(
        name="nomination_window",
        description="Assess nomination windows; never submits a nomination.",
        rest_path="/api/optimization/nomination-window",
        method="POST",
        sdk="eurogas_nexus_sdk.optimization.optimize_nomination_window",
        mcp="optimize_nomination_window_sandbox",
        decision_context="sandbox",
        persisted_run=True,
    ),
    DataScienceFunction(
        name="portfolio_network",
        description="DB-composed portfolio network optimization.",
        rest_path="/api/optimization/portfolio-network",
        method="POST",
        sdk="eurogas_nexus_sdk.optimization.optimize_portfolio_network",
        mcp=None,
        decision_context="runtime",
        persisted_run=True,
    ),
    DataScienceFunction(
        name="weather_stations",
        description="List weather stations.",
        rest_path="/api/weather/stations",
        method="GET",
        sdk="eurogas_nexus_sdk.weather.fetch_weather_stations",
        mcp="get_weather_stations",
        decision_context="runtime",
        persisted_run=False,
    ),
    DataScienceFunction(
        name="weather_observations",
        description="List weather observations.",
        rest_path="/api/weather/observations",
        method="GET",
        sdk="eurogas_nexus_sdk.weather.fetch_weather_observations",
        mcp="get_weather_observations",
        decision_context="runtime",
        persisted_run=False,
    ),
    DataScienceFunction(
        name="weather_hdd_cdd",
        description="List HDD/CDD degree-day series.",
        rest_path="/api/weather/hdd-cdd",
        method="GET",
        sdk="eurogas_nexus_sdk.weather.fetch_hdd_cdd",
        mcp="get_hdd_cdd",
        decision_context="runtime",
        persisted_run=False,
    ),
    DataScienceFunction(
        name="cost_observation_values",
        description="List time-windowed cost observations for route/point/LNG scopes.",
        rest_path="/api/cost-observations/values",
        method="GET",
        sdk="eurogas_nexus_sdk.cost_observations.fetch_cost_observations",
        mcp="get_cost_observations",
        decision_context="runtime",
        persisted_run=False,
    ),
    DataScienceFunction(
        name="applicable_cost_resolution",
        description="Resolve the applicable cost with entitlement priority.",
        rest_path="/api/cost-observations/applicable",
        method="GET",
        sdk="eurogas_nexus_sdk.cost_observations.resolve_cost_observation",
        mcp="get_applicable_cost",
        decision_context="runtime",
        persisted_run=False,
    ),
    DataScienceFunction(
        name="optimization_run_evidence",
        description="Fetch one persisted optimization run.",
        rest_path="/api/optimization/runs/{run_id}",
        method="GET",
        sdk="eurogas_nexus_sdk.optimization.fetch_optimization_run",
        mcp="get_optimization_run",
        decision_context="runtime",
        persisted_run=False,
    ),
)

FUNCTIONS_BY_NAME = {f.name: f for f in FUNCTION_CATALOG}
MCP_TOOLS = tuple(f.mcp for f in FUNCTION_CATALOG if f.mcp)
