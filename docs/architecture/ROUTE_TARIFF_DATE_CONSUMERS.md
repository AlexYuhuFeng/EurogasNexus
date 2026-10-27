# Route tariff date consumers

Status: implemented for the bounded ROUTE-DATE-CONSUMERS slice and the
connected portfolio/Web bridge. This document records which real consumers
carry an explicitly caller-declared gas day or tariff applicability date, where
that date is used, and what happens when the caller declares none.

## The rule

Tariff applicability is decided only by an explicit calendar date supplied by
the caller. The following are **not** delivery dates and must never be
substituted for one:

- `created_at` / `created_at_utc` audit metadata;
- the current clock (`datetime.now`, `detected_at_utc`, an observation instant);
- the gas-year string (`2025+`, `2026/27`);
- a market-observation time;
- the row order of a tariff table.

`observed_at_utc` remains the observation/valuation clock used for freshness and
as-of FX. `detected_at_utc` in an intraday scan remains the valuation instant
used for quote age and access validity. Neither becomes tariff applicability.

When an explicit date is supplied, the exact selector
(`domain/route_cost/tariff_selection.py`) requires exactly one authoritative
tariff row whose inclusive `effective_from`/`effective_to` window covers it. An
out-of-period date, a gap, an inverted window, a conflicting duplicate tariff id
or two final rows covering the date **blocks the candidate**. The blocked route
is excluded from the allocation, no route edge or sale option is created, and it
is never priced as a zero charge. Without a date the legacy selection is kept
for compatibility, but the result carries
`TARIFF_APPLICABILITY_NOT_ASSESSED` and requires human review.

## Consumers and carriers

### Route recommendation

- Request field: `RouteRecommendationRequest.tariff_applicability_date`
  (`date | None`) in `domain/route_cost/route_optimizer.py`.
- The request validator refuses timestamps, numeric values and non-`YYYY-MM-DD`
  strings instead of coercing them.
- The value is passed unchanged to the actual `RouteCostScenario` built for each
  candidate (`RouteCostScenario.tariff_applicability_date`), then to
  `select_latest_tariff`.
- API carrier: `POST /api/route-cost/recommend` body field
  `tariff_applicability_date` (ISO `YYYY-MM-DD`).
- SDK carrier: `eurogas_nexus_sdk.route_cost.recommend_route_allocation(...,
  tariff_applicability_date=date)`.
- Echo: `RouteRecommendationResult.tariff_applicability_date`; each
  `RouteAllocation.source_refs` carries the tariff id, tariff document id and
  the tariff row's own source references actually used.
- With no date, the result echoes `null`, includes
  `TARIFF_APPLICABILITY_NOT_ASSESSED`, and keeps the legacy priced selection.

### Portfolio-network optimization

- Request field: `PortfolioNetworkOptimizationRequest.gas_day` (`date`) in
  `api/routes/public/optimization.py`; already required and already passed to
  `compose_portfolio_network(gas_day=...)`.
- `domain/route_cost/portfolio_network.py` now passes that same caller-declared
  gas day to every route-leg `RouteCostScenario.tariff_applicability_date` and
  lets the exact selector own date eligibility. The clock-derived prefilter is
  gone.
- The selected tariff id/document/source references remain in
  `edge_lineage.tariff_source_refs`; `tariff_applicability_date` is echoed in
  `edge_lineage` and `sale_option_lineage`.
- A gap, overlap or other applicability failure becomes a
  `ROUTE_COST_MISSING:<code>:<leg>:<route>` blocker, so the composition is
  incomplete and never reaches `optimize_composed_portfolio_network`.
- SDK carrier: `optimize_portfolio_network(gas_day=...)`, unchanged field.

### Resource pool

- Composition input: `compose_resource_pool_options(gas_day=...)`
  (`application/resource_pool.py`).
- The gas day is passed to `candidate_route_cost(...,
  tariff_applicability_date=gas_day)`; a route whose tariff does not cover that
  date is blocked before the sale option is appended.
- The same date is the as-of date for FX conversion of sale prices and route
  costs. The market observation instant is only the legacy FX fallback and is
  never used as tariff applicability.
- API carrier (read): `GET /api/route-cost/resource-pool/options?gas_day=YYYY-MM-DD`.
- API carrier (runtime decision): `POST /api/optimization/resource-pool` with
  `decision_context=RUNTIME_DECISION` and optional `gas_day`. Sandbox requests
  refuse `gas_day` with `sandbox_gas_day_not_supported` because sandbox inputs
  are already explicit and do not read DB tariffs.
- SDK carrier: `optimize_resource_pool(..., decision_context="RUNTIME_DECISION",
  gas_day=date)` in `eurogas_nexus_sdk.optimization`.
- Echo: top-level `tariff_applicability_date`; each sale option also carries
  `tariff_applicability_date`, `route_cost_source_refs` and includes the route
  cost sources in `source_refs`. The runtime-decision evidence snapshot records
  `gas_day` when one was supplied.
- With no gas day the composition keeps the legacy selection, adds
  `TARIFF_APPLICABILITY_NOT_ASSESSED`, and echoes `null`.

### Connected portfolio projection and Web recommendation bridge

The PortfolioSnapshot projection is a real consumer, not a calculator
substitute:

- `application/projections/portfolio_snapshot.py` resolves one
  `ProjectionContext` and passes `date.fromisoformat(context.gas_day)` to the
  shared `compose_resource_pool_options(gas_day=...)`. `context.gas_day` is the
  canonical label of the caller's declared trading context (or the calendar gas
  day containing the one as-of instant); no `datetime.now`, observation clock or
  second calendar is used.
- The resource-pool composition performs the tariff selection, entitlement
  narrowing and FX conversion exactly once from the existing single read. The
  projection echoes the composition's own `tariff_applicability_date` in the
  `resources` slice payload and each sale option; it does not derive a parallel
  date.
- If the selected tariff does not cover that date (gap, overlap, inverted
  window or conflict), the route is blocked and no sale option is fabricated as
  a zero charge.

The Web route-comparison request now carries the same explicit date:

- `buildRouteRecommendationRequest(..., gasDay)` sets
  `RouteRecommendationRequest.tariff_applicability_date` from the caller's
  current gas day, and `RouteRecommendationRequestDTO` /
  `RouteRecommendationResultDTO` declare the field. Because the date is part of
  the composed request and the caller-known input identity, changing the gas day
  invalidates a held comparison instead of reusing it.
- `route_cost_gbp_mwh: null`/absent becomes `manual_cost: null` (unknown), never
  `0`; only an explicit `0` is forwarded as a known zero. The domain excludes a
  candidate with no manual cost and no priceable leg with
  `ROUTE_COST_MISSING`, and refuses manual cost without currency/energy-unit
  metadata (`ROUTE_COST_METADATA_MISSING`, `ROUTE_COST_UNIT_INCOMPATIBLE`).
- The backend-normalized `*_gbp_mwh` values travel with explicit
  `GBP`/`GBP/MWh` identities, so an already-GBP value is never defaulted to EUR
  or converted twice. A direct caller that supplies a sale price without a
  currency/energy-unit basis is blocked with `SALE_PRICE_METADATA_MISSING`
  instead of being compared.
- `capacity_status` is forwarded unchanged (`NOT_REQUIRED` stays
  `NOT_REQUIRED`); a missing state becomes `UNKNOWN`, and the allocator fails
  closed unless capacity is declared `NOT_REQUIRED`.
- A candidate whose source-option date disagrees with the request's current gas
  day is blocked with `TARIFF_APPLICABILITY_DATE_MISMATCH:<date>`, so a stale
  pool read cannot be re-presented as an allocation for the new gas day.
- Candidate `source_refs` (including the source option's
  `route_cost_source_refs`) are echoed on a selected allocation prefixed
  `unverified_input:` in `source_refs`, and verbatim in the separate
  `unverified_input_source_refs` field. They are caller-supplied provenance
  only: no entitlement is granted and they are not used as an economic input.

The Web resource-pool optimiser request remains a `SANDBOX_SCENARIO`: its
resources and sale options are explicit backend-normalized data already derived
from the projection context, so the request deliberately adds no runtime
`gas_day` (the sandbox gate refuses one). Its explicit values and basis are
passed through unchanged.

Focused bridge evidence lives in
`tests/unit/test_portfolio_snapshot_tariff_date_bridge.py`,
`tests/unit/test_route_cost_route_recommendation.py` and
`clients/web/tests/routeTariffDateBridge.test.ts`.

### Intraday opportunity route economics

- `db/repositories/market_intelligence.py` `_route_economics(session, at_utc,
  tariff_applicability_date=...)` now accepts the explicit date and passes it to
  `RouteCostScenario.tariff_applicability_date`.
- `scan_and_persist_intraday_opportunities(...,
  tariff_applicability_date=...)` exposes the same field to its caller.
- `at_utc` remains the valuation instant for TSO-access validity; it is no
  longer turned into a tariff date/filter.
- With no explicit date, every route's `RouteEconomics.warnings` carries
  `TARIFF_APPLICABILITY_NOT_ASSESSED`. If the legacy selection still cannot
  price the route, `total_cost` stays `None` and the opportunity evaluator adds
  `ROUTE_COST_MISSING`; it does not become a zero charge.
- No public intraday-scan API or SDK method exists in this slice, so there is no
  API request field to add. The repository/scan callers are the carrier.

## Preserved boundaries

- Capacity-billing guard: a `p/(kWh/h)/h` or capacity-hour tariff is still
  refused as an energy price (`TARIFF_CAPACITY_BILLING_REQUIRED`); no billing
  formula was added or rewritten.
- Exact price normalization and FX conversion are unchanged except that the
  resource-pool as-of date can now be the explicit delivery gas day.
- No unit conversion, FX rule, financial formula, source ownership, permission or
  snapshot contract was changed. The projection only echoes the composition's own
  date payload; it adds no second calendar or date authority.
- Source/entitlement filtering in the resource-pool composition is unchanged.
