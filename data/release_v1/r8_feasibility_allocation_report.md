# R8: Feasibility and Allocation Report

**Milestone ID:** R8
**Status:** COMPLETE
**Date:** 2026-05-29

## Evidence

- Feasibility check evaluates route capacity, eligibility, and contract status.
  Returns feasible/infeasible/conditional/unknown with blockers and conditions.
- Allocation distributes demand across eligible candidates by rank order.
  Reports total allocated, unallocated volume, and per-candidate results.
- 2 new POST endpoints: /api/research/feasibility, /api/research/allocation.
- All outputs include research metadata (assumptions, missing_inputs, warnings,
  source_references, lineage, research_only, human_review_required).

## Files

- `src/eurogas_nexus/workflows/feasibility.py` 鈥?check_feasibility
- `src/eurogas_nexus/workflows/allocation.py` 鈥?compute_allocation
- `src/eurogas_nexus/api/routes/public/research.py` 鈥?+2 POST endpoints
- `.agent/plans/V1_R8_FEASIBILITY_ALLOCATION_EXECPLAN.md`
- `data/release_v1/r8_feasibility_allocation_report.md`
- `tests/workflows/test_feasibility.py` (5)
- `tests/workflows/test_allocation.py` (4)
- `tests/api/test_feasibility_allocation_api.py` (5)

## API impact

2 POST routes: /api/research/feasibility, /api/research/allocation.
Route count: 46 鈫?48.

## Validation

- ruff: All checks passed
- pytest: 267 passed (was 253; +14)
- app: import ok, 48 routes

## Next

R9: Monitoring and Weather-Adjusted Nowcast
