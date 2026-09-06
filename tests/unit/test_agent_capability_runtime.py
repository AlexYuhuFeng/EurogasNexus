"""CR-15 capability registry/runtime tests (registry and high-value handlers)."""

from __future__ import annotations

from eurogas_nexus.application.agents.runtime import CapabilityRuntime
from eurogas_nexus.domain.agents.contracts import (
    AgentInvocationContext,
    CapabilityFailureCode,
    CapabilityStatus,
    DeterminismClass,
    SideEffectClass,
)


def _runtime():
    from eurogas_nexus.application.agents.capability_handlers import (
        register_core_capabilities,
    )
    from eurogas_nexus.application.agents.registry import CapabilityRegistry
    from eurogas_nexus.application.agents.research_handlers import (
        register_research_capabilities,
    )

    registry = CapabilityRegistry()
    register_core_capabilities(registry)
    register_research_capabilities(registry)
    return registry, CapabilityRuntime(registry)


def _analyst() -> AgentInvocationContext:
    return AgentInvocationContext(
        principal_id="analyst-1",
        role="ANALYST",
        roles=["ANALYST"],
        data_scopes=["*"],
    )


def test_capability_discovery_is_semantic_and_bounded() -> None:
    registry, _ = _runtime()
    definitions = registry.list_definitions()
    assert 30 <= len(definitions) <= 80
    assert "ontology.resolve_entity" in {item.capability_id for item in definitions}
    assert "route.calculate_economics" in {item.capability_id for item in definitions}
    search = registry.search("spread")
    assert any("spread" in item.capability_id for item in search)


def test_capability_metadata_carries_determinism_and_side_effects() -> None:
    registry, _ = _runtime()
    route = registry.get("route.calculate_economics")
    assert route.determinism_class == DeterminismClass.DETERMINISTIC
    assert route.side_effect_class == SideEffectClass.READ_ONLY
    assert route.required_permissions
    assert route.retry_policy.max_attempts >= 0
    assert route.capability_version == "v1"


def test_capability_version_and_schema_are_typed() -> None:
    registry, runtime = _runtime()
    definition = registry.get("market.get_spread")
    assert definition.qualified_id().startswith("market.get_spread@")
    result = runtime.invoke(
        "market.get_spread",
        {"origin_hub": "TTF", "destination_hub": "NBP", "origin_value": 1, "destination_value": 2},
        _analyst(),
    )
    assert result.status == "BLOCKED"
    assert result.failure.code == CapabilityFailureCode.INVALID_PRODUCT

    result = runtime.invoke(
        "market.get_spread",
        {
            "origin_hub": "TTF",
            "destination_hub": "NBP",
            "product": "DAY_AHEAD",
            "origin_value": 1,
            "destination_value": 2,
            "unit": "EUR/MWh",
        },
        _analyst(),
    )
    assert result.status == "SUCCESS"
    assert result.data["value"] == 1.0
    assert result.capability_version == "v1"


def test_unknown_and_disabled_capabilities_fail_closed() -> None:
    registry, runtime = _runtime()
    result = runtime.invoke("does.not_exist", {}, _analyst())
    assert result.failure.code == CapabilityFailureCode.UNKNOWN_CAPABILITY

    registry.disable("analytics.distribution")
    result = runtime.invoke("analytics.distribution", {"values": [1, 2]}, _analyst())
    assert result.failure.code == CapabilityFailureCode.CAPABILITY_DISABLED
    assert registry.get("analytics.distribution").status == CapabilityStatus.DISABLED


def test_permission_denial_is_machine_readable() -> None:
    registry, runtime = _runtime()
    viewer = AgentInvocationContext(
        principal_id="viewer", role="VIEWER", roles=["VIEWER"], data_scopes=[]
    )
    result = runtime.invoke("analytics.distribution", {"values": [1, 2]}, viewer)
    assert result.status == "BLOCKED"
    assert result.failure.code == CapabilityFailureCode.PERMISSION_DENIED


def test_entitlement_denial_is_machine_readable() -> None:
    registry, runtime = _runtime()
    restricted = AgentInvocationContext(
        principal_id="viewer", role="ANALYST", roles=["ANALYST"], data_scopes=[]
    )
    result = runtime.invoke(
        "market.get_history",
        {"start_utc": "2026-01-01T00:00:00Z", "end_utc": "2026-01-02T00:00:00Z"},
        restricted,
    )
    assert result.failure.code == CapabilityFailureCode.ENTITLEMENT_DENIED


def test_human_confirmation_and_human_only_policies() -> None:
    _, runtime = _runtime()
    analyst = _analyst()
    freeze = runtime.invoke("strategy.freeze_version", {"strategy_version_id": "v1"}, analyst)
    assert freeze.failure.code == CapabilityFailureCode.HUMAN_CONFIRMATION_REQUIRED
    review = runtime.invoke("review.record_analytical_decision", {}, analyst)
    assert review.failure.code == CapabilityFailureCode.PERMISSION_DENIED


def test_ontology_resolve_and_ambiguity() -> None:
    _, runtime = _runtime()
    result = runtime.invoke(
        "ontology.resolve_entity",
        {"source_id": "x", "source_entity_type": "market_hub", "source_identifier": "NBP"},
        _analyst(),
    )
    assert result.data["canonical_entity_id"] == "ent:market_hub:NBP"
    ambiguous = runtime.invoke(
        "ontology.resolve_entity",
        {
            "source_id": "x",
            "source_entity_type": "infrastructure",
            "source_identifier": "Bacton",
            "candidate_identifiers": ["BBL", "IUK"],
        },
        _analyst(),
    )
    assert ambiguous.data["status"] == "AMBIGUOUS_ENTITY"
    assert ambiguous.data["candidates"] == ["BBL", "IUK"]


def test_market_spread_is_deterministic_and_typed() -> None:
    _, runtime = _runtime()
    result = runtime.invoke(
        "market.get_spread",
        {
            "origin_hub": "NBP",
            "destination_hub": "TTF",
            "product": "DAY_AHEAD",
            "origin_value": 30.0,
            "destination_value": 28.0,
            "unit": "GBP/MWh",
        },
        _analyst(),
    )
    assert result.data["value"] == -2.0
    assert result.data["unit"] == "GBP/MWh"
    assert result.data["freshness"] == "CALCULATED"


def test_flow_context_and_capacity_feasibility() -> None:
    _, runtime = _runtime()
    result = runtime.invoke("network.get_flow_context", {"point_id": "missing"}, _analyst())
    assert result.status == "BLOCKED" and result.failure.code == CapabilityFailureCode.DATA_MISSING
    feasibility = runtime.invoke(
        "capacity.check_route_feasibility",
        {
            "route_name": "A->B",
            "required_capacity_mcm_d": 10,
            "available_capacity_mcm_d": 5,
            "required_tso_access": ["TSO1"],
            "accessible_tsos": [],
        },
        _analyst(),
    )
    assert feasibility.data["feasible"] is False
    assert feasibility.data["blockers"]


def test_route_economics_uses_backend_engine() -> None:
    _, runtime = _runtime()
    result = runtime.invoke(
        "route.calculate_economics",
        {
            "route_name": "A->B",
            "from_node_id": "A",
            "to_node_id": "B",
            "components": [
                {"component_type": "tariff", "amount": 0.8, "unit": "EUR/MWh"},
                {"component_type": "fuel", "amount": 0.2, "unit": "EUR/MWh"},
            ],
        },
        _analyst(),
    )
    assert result.data["total_cost_eur_mwh"] == 1.0
    assert result.data["components"][0]["component_type"] == "tariff"


def test_portfolio_resource_economics_and_impacted_resources() -> None:
    _, runtime = _runtime()
    result = runtime.invoke(
        "portfolio.get_resource_economics",
        {"resource_price_gbp_mwh": 20.0, "market_price_gbp_mwh": 25.0},
        _analyst(),
    )
    assert result.data["indicative_margin_gbp_mwh"] == 5.0


def test_backtest_validate_rejects_bad_period() -> None:
    _, runtime = _runtime()
    result = runtime.invoke(
        "backtest.validate",
        {
            "strategy_version_id": "v",
            "period_start_utc": "2026-01-02T00:00:00Z",
            "period_end_utc": "2026-01-01T00:00:00Z",
        },
        _analyst(),
    )
    assert result.data["ok"] is False


def test_strategy_ir_validation_has_no_arbitrary_code() -> None:
    _, runtime = _runtime()
    result = runtime.invoke(
        "strategy.validate_spec",
        {"strategy_ir": {"hypothesis": "x", "code": "import os"}},
        _analyst(),
    )
    assert result.data["ok"] is False
