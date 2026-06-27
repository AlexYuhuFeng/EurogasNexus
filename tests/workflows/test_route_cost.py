"""Route cost computation tests."""

from eurogas_nexus.workflows.route_cost import (
    CostComponent,
    RouteCostInput,
    compute_route_cost,
)


def test_route_cost_sums_components() -> None:
    result = compute_route_cost(RouteCostInput(
        route_name="TTF-NCG", from_node_id="node-ttf", to_node_id="node-ncg",
        components=[
            CostComponent(component_type="tariff", amount=1.50),
            CostComponent(component_type="fuel", amount=0.85),
        ],
        route_km=200.0,
    ))
    assert result.total_cost_eur_mwh == 2.35
    assert result.total_cost_boe == round(2.35 * 0.1706, 4)
    assert result.research_only is True
    assert not result.is_partial


def test_route_cost_empty_components_warns() -> None:
    result = compute_route_cost(RouteCostInput(
        route_name="Test", from_node_id="n1", to_node_id="n2",
    ))
    assert result.total_cost_eur_mwh == 0.0
    assert len(result.warnings) >= 1
    assert result.is_partial


def test_route_cost_missing_name_reports() -> None:
    result = compute_route_cost(RouteCostInput(
        route_name="", from_node_id="n1", to_node_id="n2",
    ))
    assert len(result.missing_inputs) >= 1
    assert result.human_review_required is True


def test_route_cost_output_has_lineage() -> None:
    result = compute_route_cost(RouteCostInput(
        route_name="TTF-NCG", from_node_id="n1", to_node_id="n2",
    ))
    assert "route-cost-computation" in result.lineage
    assert "operator-input" in result.source_references
