# V1 R8 Feasibility and Allocation ExecPlan

## 1. Goal

Implement feasibility check and allocation scenario computation. Feasibility
evaluates route constraints (capacity, eligibility, contracts) and returns
feasible/infeasible/conditional/unknown. Allocation distributes demand volume
across eligible routes by rank.

## 2. Non-goals

- No live market data. No optimization solver. No trade/nomination execution.

## 3. Internet required: no

## 4. Files

- `src/eurogas_nexus/workflows/feasibility.py`
- `src/eurogas_nexus/workflows/allocation.py`
- `src/eurogas_nexus/api/routes/v1/research.py` — add POST endpoints
- `data/release_v1/r8_feasibility_allocation_report.md`
- `tests/workflows/test_feasibility.py`
- `tests/workflows/test_allocation.py`
- `tests/api/test_feasibility_allocation_api.py`

## 5. Acceptance

- Feasibility checks capacity, eligibility, contracts.
- Returns feasible/infeasible/conditional/unknown with blockers/conditions.
- Allocation distributes demand by ranked candidates.
- Unallocated volume reported.
- Research metadata on all outputs.
