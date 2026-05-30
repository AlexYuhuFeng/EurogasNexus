"""Allocation computation tests."""

from eurogas_nexus.workflows.allocation import (
    AllocationCandidate,
    AllocationInput,
    compute_allocation,
)


def test_allocation_distributes_by_rank() -> None:
    result = compute_allocation(AllocationInput(
        scenario_name="Winter Base", total_demand_boe_d=5000000.0,
        candidates=[
            AllocationCandidate("c1", "TTF-NCG", "n1", "n2", 3000000, 40.5, rank=1),
            AllocationCandidate("c2", "Emden-NCG", "n3", "n2", 3000000, 41.2, rank=2),
        ],
    ))
    assert result.total_allocated_boe_d == 5000000.0
    assert result.unallocated_boe_d == 0.0
    assert result.results[0].candidate_id == "c1"
    assert result.results[0].allocated_boe_d == 3000000.0
    assert result.results[1].allocated_boe_d == 2000000.0


def test_unallocated_demand_reported() -> None:
    result = compute_allocation(AllocationInput(
        scenario_name="Test", total_demand_boe_d=5000000.0,
        candidates=[
            AllocationCandidate("c1", "R1", "n1", "n2", 1000000, 40.0, rank=1),
        ],
    ))
    assert result.total_allocated_boe_d == 1000000.0
    assert result.unallocated_boe_d == 4000000.0
    assert len(result.warnings) >= 1


def test_ineligible_candidates_skipped() -> None:
    result = compute_allocation(AllocationInput(
        scenario_name="Test", total_demand_boe_d=1000000.0,
        candidates=[
            AllocationCandidate("c1", "R1", "n1", "n2", 1000000, 40.0, rank=1, eligible=False),
            AllocationCandidate("c2", "R2", "n3", "n4", 1000000, 41.0, rank=2),
        ],
    ))
    assert result.results[0].candidate_id == "c2"
    assert result.total_allocated_boe_d == 1000000.0


def test_missing_inputs_reported() -> None:
    result = compute_allocation(AllocationInput(scenario_name="", total_demand_boe_d=0.0))
    assert len(result.missing_inputs) >= 1
    assert result.research_only is True
