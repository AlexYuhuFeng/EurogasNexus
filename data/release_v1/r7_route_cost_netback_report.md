# R7: Route Cost and Indicative Netback Report

**Milestone ID:** R7
**Status:** COMPLETE
**Date:** 2026-05-29

## Evidence

- Route cost computation: sums tariff, fuel, transport, and other components.
  Returns total_cost_eur_mwh and total_cost_boe (1 MWh 鈮?0.1706 boe).
- Indicative netback: market_price - route_cost with optional FX conversion.
  Computes netback_eur_mwh and netback_local_mwh.
- Both computations validate inputs: missing route_name, non-positive market
  price, negative route cost all reported as missing_inputs or warnings.
- Non-positive netback produces a warning (route may be uneconomical).
- All outputs include research metadata: assumptions, missing_inputs, warnings,
  source_references, lineage, research_only, human_review_required.
- 2 POST API routes: /api/research/route-cost, /api/research/netback
  accept typed JSON request bodies and return research envelope.
- No execution, trade, order, or nomination semantics.

## Files Created / Modified

- `src/eurogas_nexus/workflows/route_cost.py` 鈥?compute_route_cost, CostComponent,
  RouteCostInput, RouteCostOutput
- `src/eurogas_nexus/workflows/netback.py` 鈥?compute_netback, NetbackInput,
  NetbackOutput
- `src/eurogas_nexus/api/routes/public/research.py` 鈥?2 POST endpoints
- `src/eurogas_nexus/api/route_registration.py` 鈥?+research router
- `.agent/plans/V1_R7_ROUTE_COST_NETBACK_EXECPLAN.md`
- `data/release_v1/r7_route_cost_netback_report.md`
- `tests/workflows/test_route_cost.py` (4 tests)
- `tests/workflows/test_netback.py` (5 tests)
- `tests/api/test_research_api.py` (5 tests)

## API Impact

2 POST routes: /api/research/route-cost, /api/research/netback.
Route count: 44 鈫?46.

## Validation

- ruff: All checks passed
- pytest: 253 passed (was 239; +14 new tests)
- app: import ok, 46 routes

## Next Milestone

R8: Feasibility and Allocation
