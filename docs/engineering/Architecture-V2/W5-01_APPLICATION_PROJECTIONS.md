# W5-01 — Application Projections

Status: **delivered (Wave 5)**. Authority:
[03_TARGET_PLATFORM_ARCHITECTURE.md](03_TARGET_PLATFORM_ARCHITECTURE.md) section 4,
[08_DECISION_APPLICATION_AI.md](08_DECISION_APPLICATION_AI.md) section 2,
[02_ARCHITECTURE_CONSTITUTION.md](02_ARCHITECTURE_CONSTITUTION.md) rules 7, 34-35 and 43, and
[W0-01_CLIENT_INVENTORY.md](W0-01_CLIENT_INVENTORY.md) section 6 (the client waterfalls and
timestamp joins this wave removes).

## 1. Why

React was reconstructing critical commercial state by joining many low-level endpoints with mixed
timestamps: the market cockpit, the portfolio views and the review surface each combined several
reads whose as-of instants disagreed. Architecture V2 asks for coherent, server-composed read models
behind the same `/api` boundary, with the existing endpoints preserved.

## 2. Delivered projections

| Projection | Path | Floor | Slices |
|---|---|---|---|
| MarketContext | `GET /api/projections/market-context` | READ | market observations, normalized quotes, quotes, intraday opportunities, spreads, monitoring, data sources |
| PortfolioSnapshot | `GET /api/projections/portfolio-snapshot` | READ | summary, screen orders, PnL snapshots, contracts, resources, data sources |
| ReviewContext | `GET /api/projections/review-context` | READ | decisions, evidence, monitoring |
| ScenarioContext | `GET /api/projections/scenario-context` | GOVERNED | route candidates, TSO tariffs, upstream contracts, plus an explicit `not_included` block |

Every response keeps the repository envelope (`data`/`meta`). `meta` carries `projection`,
`projection_version`, `as_of_utc`, `time_basis`, `research_only`, `human_review_required`,
`source_references`, `warnings` and `table_lineage`. Every slice carries `available`,
`source_references`, `row_count`, `rows`/`payload`, `freshness`, `entitlement`, `context_filter`,
`limits`, `warnings` and `notes`.

Freshness is not invented: it reuses `domain.monitoring.freshness`,
`domain.dataops.contracts.FreshnessState` and the source registry's declared expectations, and
reports `FRESH`/`STALE`/`MISSING`/`UNKNOWN` with the basis, the measurement and the expectation it
was measured against.

## 3. Duplication removed, not added

The wave's real content is the extraction, not the four new routes:

- `application/projections/market_reads.py` and `portfolio_reads.py` now own the loaders, shapers,
  spread derivation and row-entitlement filtering that `/api/market/*` and `/api/portfolio/*` used
  to hold privately. Both the existing routes and the projections call them, so a projection can
  never become a second implementation of the same query with different filtering.
- `market.py` and `portfolio.py` keep every existing response field and their test seams
  (`_db_is_configured`, `_market_row`, `_fx_row`, `_load_screen_orders`, `_load_pnl_snapshots`).
- `db/repositories/market_intelligence.py` gained an additive `get_intraday_opportunity()` reusing
  the existing row shaper.

## 4. Rules the projections must keep

1. **Never wider than the endpoint they compose.** Market and portfolio slices apply the same
   fail-closed row filters the routes apply; the normalized view uses the same source-family
   predicate; review evidence is withheld when `derived_result_access` denies it. A slice whose
   underlying route applies no filter declares `row_filter_applied: false` instead of inventing one.
2. **ScenarioContext keeps the GOVERNED floor** of the endpoints it composes, so a read projection
   cannot become a way around the analyst floor.
3. **Projections sit inside the commercial boundary** (`COMMERCIAL_DATA_PREFIXES` includes
   `/api/projections/`), so a platform-administration identity without a commercial role is refused
   exactly as it is on `/api/market/*`.
4. **Deterministic engines own results.** ScenarioContext never synthesises an optimisation, route
   recommendation or economics result; it lists them under `data.not_included` with the endpoint that
   produces them.
5. **No client joins.** The projections exist so the client stops joining; a slice that cannot be
   composed honestly is declared unavailable rather than approximated.

## 5. Compatibility

- Additive: four new GET paths, pinned in `tests/contract/test_api_surface_stability.py`, recorded
  in `docs/architecture/API_CONTRACT_EVOLUTION_POLICY.md`, and counted in the security acceptance
  surface bound (175 paths).
- No schema, migration, datastore, dependency, permission widening or numerical change. Existing
  `/api/market/*` and `/api/portfolio/*` payloads are byte-identical (their suites still pass).
- The projections import no `eurogas_nexus.api` module and keep SQLAlchemy behind `TYPE_CHECKING`,
  so "API import must not load the DB layer" still holds.

## 6. Deferred (honest gaps, declared in the payload)

- The portfolio `resources` slice reports `RESOURCE_POOL_COMPOSITION_IS_ROUTE_LOCAL`: composing
  resource-pool options is still private to `route_cost.py`. Extracting
  `_compose_resource_pool_options` (with its tariff, market, FX and access reads) into the
  application layer is the bounded next step, after which both the existing route and the
  `resources` slice call it.
- Scenario results are deliberately never synthesised; the endpoints that produce them are listed
  in `data.not_included`.
- The client has not yet migrated onto the projections. That is the next half of the wave: point the
  market cockpit and portfolio views at `MarketContext`/`PortfolioSnapshot` and delete the
  corresponding multi-endpoint joins and timestamp arithmetic in `clients/web`.

## 7. Verification

- `tests/api/test_projections_api.py` (10 tests) and `tests/unit/test_projections_application.py`
  (21 tests): coherent single time basis, per-slice freshness, entitlement at least as strict as the
  underlying route, empty/degraded states, payload stability, and the `gas_day_invalid` 422.
- Full suites: `python -m pytest tests -q --ignore=tests/integration` (green) and the client suite in
  `clients/web`; results are recorded in the execution checkpoint.
