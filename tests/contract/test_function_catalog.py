"""Data-science function catalog contract tests."""

from eurogas_nexus.api.function_catalog import (
    FUNCTION_CATALOG,
    FUNCTIONS_BY_NAME,
    MCP_TOOLS,
)


def test_catalog_has_required_data_science_functions() -> None:
    names = {f.name for f in FUNCTION_CATALOG}

    for expected in [
        "route_cost",
        "route_optimization",
        "resource_pool_optimization",
        "capacity_optimization",
        "contract_optimization",
        "storage_dispatch",
        "nomination_window",
        "portfolio_network",
        "weather_stations",
        "weather_observations",
        "weather_hdd_cdd",
        "optimization_run_evidence",
    ]:
        assert expected in names


def test_catalog_function_names_are_unique() -> None:
    assert len(FUNCTION_CATALOG) == len(FUNCTIONS_BY_NAME)


def test_catalog_mcp_tools_are_expected() -> None:
    assert "calculate_route_cost" in MCP_TOOLS
    assert "optimize_route_sandbox" in MCP_TOOLS
    assert "optimize_resource_pool_sandbox" in MCP_TOOLS
    assert "optimize_capacity_sandbox" in MCP_TOOLS
    assert "optimize_contracts_sandbox" in MCP_TOOLS
    assert "optimize_storage_dispatch_sandbox" in MCP_TOOLS
    assert "optimize_nomination_window_sandbox" in MCP_TOOLS
    assert "get_weather_stations" in MCP_TOOLS
    assert "get_weather_observations" in MCP_TOOLS
    assert "get_hdd_cdd" in MCP_TOOLS
    assert "get_optimization_run" in MCP_TOOLS


def test_runtime_functions_are_not_exposed_as_mcp() -> None:
    assert "portfolio_network" in FUNCTIONS_BY_NAME
    assert FUNCTIONS_BY_NAME["portfolio_network"].mcp is None
