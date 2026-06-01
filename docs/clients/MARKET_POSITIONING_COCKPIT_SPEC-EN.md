# Market Positioning Cockpit Spec - EN

## Purpose

This spec defines the V1 read-only order/PnL cockpit extension. It supports a
gas trader reviewing external screen activity, portfolio valuation, route
economics, and strategy output on the map-first workspace without turning
Eurogas Nexus into an execution, order-routing, nomination, or ETRM system.

## Absolute Data Boundary

The source of truth is PostgreSQL behind the backend API. Clients use:

```text
Web/Windows/SDK -> /api/v1/portfolio/* -> backend repositories -> PostgreSQL
```

Clients must not connect to PostgreSQL, store order/PnL files, call exchanges,
or read backend raw data files. External order records are imported observations
only. They are not trade capture and cannot be amended or cancelled from V1.

## Active API Surface

- `GET /api/v1/portfolio/screen-orders`
- `GET /api/v1/portfolio/pnl-snapshots`
- `GET /api/v1/portfolio/live-summary`

All endpoints return `research_only=true` and `human_review_required=true`.

## Active DB Tables

- `screen_order_observations`
- `portfolio_pnl_snapshots`

These tables are introduced by Alembic revision
`0009_market_positioning_foundation`.

## Web/Windows UX Rules

- The home screen remains map-first.
- A highlighted animated route must show the active order/PnL corridor when
  enough node context exists.
- The above-map strip must show live/indicative PnL from runtime observations
  when live mark output is not available.
- The sidebar must include order status, filled quantity, remaining quantity,
  contract code, indicative PnL, early cash value, and open-order count.
- Labels must avoid execution language such as "place order", "route order",
  "approve", "nominate", or "trade now".

## Acceptance Tests

- `tests/api/test_portfolio_api.py`
- `tests/contract/test_market_positioning_models.py`
- `tests/sdk/test_portfolio_client.py`
- `tests/contract/test_client_release_surface.py`

## Next Expansion

Milestone 2 should add importer-controlled upsert paths for customer order/PnL
imports, entitlement-aware filtering, and audited lineage. It must still remain
read-only from client surfaces unless the product boundary is formally changed.
