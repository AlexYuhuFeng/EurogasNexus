# V1 R7 Route Cost and Indicative Netback ExecPlan

## 1. Goal

Implement the route cost calculation and indicative netback research workflow.
This is the first milestone that computes research results from input data rather
than serving static fixtures. Route cost sums tariff, fuel, transport, and other
components. Indicative netback computes market_price - route_cost.

## 2. Non-goals

- No live market data integration (uses synthetic inputs).
- No route optimization or ranking.
- No feasibility, allocation, or strategy logic.
- No DB persistence of results (stateless computation).

## 3. Internet Requirement

Internet required: no. All computation is local Python. Inputs are synthetic.

## 4. Files

- `src/eurogas_nexus/workflows/route_cost.py` — compute route cost from components
- `src/eurogas_nexus/workflows/netback.py` — compute indicative netback
- `src/eurogas_nexus/api/routes/v1/research.py` — POST routes for computation
- `src/eurogas_nexus/api/route_registration.py` — register research router
- `data/release_v1/r7_route_cost_netback_report.md`
- `tests/workflows/test_route_cost.py`
- `tests/workflows/test_netback.py`
- `tests/api/test_research_api.py`

## 5. Validation
```
ruff check .
pytest -q tests/workflows tests/api tests/contract tests/integration tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

## 6. Acceptance

- Route cost computation sums components correctly.
- Missing required inputs returns PARTIAL with warnings.
- Netback = market_price - route_cost with FX conversion.
- Research metadata preserved in all outputs.
- No execution/trade/nomination semantics.
