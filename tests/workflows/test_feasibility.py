"""Feasibility check computation tests."""

from eurogas_nexus.workflows.feasibility import (
    FeasibilityInput,
    FeasibilityStatus,
    check_feasibility,
)


def test_feasible_route() -> None:
    result = check_feasibility(FeasibilityInput(
        route_name="TTF-NCG", from_node_id="n1", to_node_id="n2",
        capacity_available_mcm_d=100.0, required_capacity_mcm_d=50.0,
        route_eligible=True, contract_active=True,
    ))
    assert result.status == FeasibilityStatus.FEASIBLE
    assert not result.blockers


def test_infeasible_capacity_exceeded() -> None:
    result = check_feasibility(FeasibilityInput(
        route_name="Test", from_node_id="n1", to_node_id="n2",
        capacity_available_mcm_d=10.0, required_capacity_mcm_d=100.0,
    ))
    assert result.status == FeasibilityStatus.INFEASIBLE
    assert any("exceeds" in b for b in result.blockers)


def test_infeasible_not_eligible() -> None:
    result = check_feasibility(FeasibilityInput(
        route_name="Test", from_node_id="n1", to_node_id="n2",
        route_eligible=False,
    ))
    assert result.status == FeasibilityStatus.INFEASIBLE


def test_conditional_with_constraints() -> None:
    result = check_feasibility(FeasibilityInput(
        route_name="Test", from_node_id="n1", to_node_id="n2",
        capacity_available_mcm_d=100.0, required_capacity_mcm_d=50.0,
        constraints=["transit-fee-unknown"],
    ))
    assert result.status == FeasibilityStatus.CONDITIONAL


def test_research_metadata() -> None:
    result = check_feasibility(FeasibilityInput(
        route_name="Test", from_node_id="n1", to_node_id="n2",
    ))
    assert result.research_only is True
    assert "feasibility-check" in result.lineage
