# Portfolio Network Optimization Runbook

Chinese companion: [PORTFOLIO_NETWORK_OPTIMIZATION-CN.md](PORTFOLIO_NETWORK_OPTIMIZATION-CN.md)

## Purpose

`POST /api/optimization/portfolio-network` is the R31 DB-backed daily
portfolio optimizer. It connects the validated shared-capacity network-flow
engine to PostgreSQL-owned commercial and infrastructure facts. It is
decision support only: every result requires trader review and no result
submits orders, nominations, bookings, or amendments.

## Request contract

```json
{
  "portfolio_id": "portfolio-id",
  "gas_day": "2026-01-01",
  "capacity_product": "ANNUAL",
  "firmness": "FIRM",
  "max_market_price_age_hours": 72,
  "decision_context": "RUNTIME_DECISION"
}
```

- `capacity_product` is one of `ANNUAL`, `QUARTERLY`, `MONTHLY`, `WEEKLY`,
  `DAILY`, `WITHIN_DAY`.
- `firmness` is one of `FIRM`, `INTERRUPTIBLE`, `BACKHAUL`, `OFF_PEAK`.
- No network edges, tariffs, capacities, market prices, contract volumes, or
  TSO access may be supplied. Pydantic rejects extra fields before any DB
  lookup.

## Composed PostgreSQL facts

| Domain input | Source table |
|---|---|
| Upstream resources | `upstream_resource_contracts` |
| Sale destinations | `market_observations` joined to active `route_candidates` |
| Route topology and route capacity | `route_candidates` |
| Canonical node ids | `reference_nodes` |
| Tariff selection | `tso_tariffs` (exact point/TSO/direction/gas-year/product/firmness match) |
| Company TSO access | `company_tso_access` (`ACTIVE`/`CONFIRMED` pass; `DENIED`/`INACTIVE`/`SUSPENDED` block) |
| FX as-of conversion | `fx_observations` (value date not later than `gas_day`) |

Market prices are selected from rows whose period covers `gas_day`, preferring
day-ahead/within-day tenors and non-simulated sources over simulated ones.
Market-price age is measured against `min(now, gas-day end)`, so a historical
gas-day decision is not falsely marked stale after the gas day.

## Solver and attribution

The composition becomes supply arcs, optional sale-option arcs, and route
edges on a shared directed gas network. The residual minimum-cost flow model
can cancel and reroute an earlier allocation when that improves portfolio
value. Final flows are decomposed into source-to-sale paths, and every path is
aggregated into contract-level PnL attribution:

- `quantity_mwh`
- `revenue_gbp`
- `supply_cost_gbp`
- `network_cost_gbp`
- `pnl_gbp`

The sum of contract attribution PnL equals the portfolio objective.

## Failure modes

| HTTP | Code | Meaning | Operator action |
|---|---|---|---|
| 422 | `sandbox_scenario_not_supported` | Sandbox context sent to the DB-only endpoint | Use `/api/optimization/route` or `/resource-pool` for what-if |
| 422 | `runtime_decision_input_blocked` | PostgreSQL snapshot is incomplete or stale | Inspect `blockers`, load/refresh the named tables, retry |
| 503 | `runtime_db_not_configured` | No runtime DB URL configured | Configure `RUNTIME_STORE_DATABASE_URL` |
| 503 | `runtime_db_unavailable` | Runtime DB configured but unavailable | Check PostgreSQL health |

Common blockers include `UPSTREAM_CONTRACTS_MISSING`,
`ROUTE_CANDIDATES_MISSING`, `REFERENCE_NODES_MISSING`,
`SUPPLY_NODE_MISSING:<contract>`, `ROUTE_NODE_MISSING:<route>`,
`MARKET_PRICE_MISSING:<point>`, `MARKET_PRICE_STALE:<point>`,
`MARKET_PRICE_CONVERSION_BLOCKED:<point>`, `TSO_ACCESS_MISSING:<route>`,
`TSO_ACCESS_DENIED:<route>`, `ROUTE_CAPACITY_UNKNOWN:<route>`, and
`ROUTE_COST_MISSING:*`. Blocked compositions never reach the solver.

## Evidence

Every successful run appends one immutable `optimization_runs` row with:

- `optimization_type = "portfolio_network"`
- `decision_context = "RUNTIME_DECISION"`
- the assembled `input_snapshot` (resources, sale options, edges, lineage,
  assumptions, market and FX observation ids)
- the full `output_snapshot`, including path and contract attribution

Retrieve evidence with `GET /api/optimization/runs/{run_id}`.

## Boundary reminders

- Clients never connect to PostgreSQL and never call providers directly.
- This endpoint is trader-reviewed decision support, not execution.
- The response is `research_only=True` and `human_review_required=True` for
  envelope compatibility and governance.
