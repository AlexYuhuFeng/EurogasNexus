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
- The review surface has not migrated onto `ReviewContext`, deliberately: that projection resolves
  evidence per review entity (`evidence_limit`, default 20) and reads the monitoring posture, so
  putting it on the workspace load path would make every session pay for detail only the review
  surface needs. The intended shape is the same as the market lane - fetch `ReviewContext` when the
  review surface opens, not in the workspace batch - and it is the bounded next step for this wave.

## 7. Client migration onto the projections

The market and portfolio lanes are the migrated consumers, and they demonstrate the rule that a
projection is only worth its cost when the client deletes a join rather than adding a fifth read.

- `clients/web/src/stores/api.ts` `refreshMarketData` no longer joins `marketQuotes`,
  `normalizedMarketObservations`, `marketSpreads`, `intradayOpportunities` and `monitoringAlerts`.
  It reads `GET /projections/market-context` (plus the independent source posture and FX reads) and
  maps the slices into the same state fields the surfaces already read, so no downstream model
  changes.
- The workspace batch no longer joins `/portfolio/live-summary`, `/portfolio/screen-orders` and
  `/portfolio/pnl-snapshots`: it reads `GET /projections/portfolio-snapshot` once and fills
  `portfolioSummary`, `screenOrders`, `pnlSnapshots` and `resourcePoolOptions` from its slices. The
  resource-pool block now comes from the `resources` slice, which composes the same
  `application/resource_pool` code the route calls, so the workspace load no longer composes the pool
  twice. That slice is **strictly narrower** than the route: the route applies no row filter, while the
  slice filters both contributing reads (route candidates and market observations) by entitlement, so
  a withheld sale option is absent on the client rather than re-derived there.
- `applyMarketContext()` and `applyPortfolioSnapshot()` are the single mapping points per lane, used
  by both the periodic/workspace read and the bounded retry control. `marketContext` is registered as
  a retry-only loader, so a failed market read stays retryable without making an initial workspace
  load request the projection twice; `portfolioSnapshot` is an ordinary batch loader. A retried
  projection re-derives every field it feeds through `PROJECTION_LANE_APPLIERS` instead of only
  storing the payload.
- `clients/web/src/app/model/projectionModel.ts` owns the one definition of a slice reading, so two
  surfaces cannot disagree about what "unavailable", "stale" or "restricted" means.
  `marketContextModel.ts` and `portfolioSnapshotModel.ts` are the two per-projection views built on
  it. Freshness is the backend's answer; the client never recomputes it from wall-clock time.
- `clients/web/src/components/ProjectionContextStrip.tsx` renders that reading, and
  `MarketContextStrip.tsx` / `PortfolioContextStrip.tsx` are the two thin adapters that mount it at
  the top of the market cockpit and the portfolio workspace. They are presentational: they do not
  fetch, recompute or reconcile timestamps.

Honesty rules the client keeps:

1. A slice the backend marks unavailable reads as *unavailable*, never as an empty market or a flat
   portfolio; the previous values stay in place and the surface qualifies them.
2. A summary the backend did not provide is `null`, never a zero-valued summary: "no exposure" and
   "not measured" are different answers.
3. A slice whose rows an entitlement withheld reads as *restricted with the withheld count*, never
   as a zero. Restriction is reported separately from degradation: the "stale, missing or
   unavailable" count is freshness and availability only.
4. A payload the backend could not serve leaves the projection empty and the strip unmounted rather
   than implying a coherent read that never happened.

## 8. Verification

- `tests/api/test_projections_api.py` (10 tests) and `tests/unit/test_projections_application.py`
  (21 tests): coherent single time basis, per-slice freshness, entitlement at least as strict as the
  underlying route, empty/degraded states, payload stability, and the `gas_day_invalid` 422.
- `clients/web/tests/marketContextProjection.test.ts` (7 tests) and
  `clients/web/tests/portfolioSnapshotProjection.test.ts` (8 tests): as-of/time-basis coherence,
  unavailable-is-not-empty, an unmeasured summary is `null` rather than zero, stale and restricted
  reporting, absent payload, the store's single-read lanes and retry wiring, one shared slice-reading
  implementation, and bilingual strip vocabulary.
- Full suites: `python -m pytest tests -q --ignore=tests/integration` (green) and the client suite in
  `clients/web`; results are recorded in the execution checkpoint.
