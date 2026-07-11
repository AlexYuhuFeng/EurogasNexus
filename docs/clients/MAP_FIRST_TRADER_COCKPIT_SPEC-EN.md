# Map-First Trader Cockpit Spec - EN

## Purpose

The Eurogas Nexus home screen is a map-first trader decision cockpit, not a
generic dashboard. Its purpose is to let a gas trader understand upstream
portfolio exposure, route availability, live market movement, strategy process
state, warnings, and indicative PnL from one visual surface.

The home screen is resource-pool-native. All active purchase contracts are first
understood as available resource in a portfolio pool. The map and right-hand
decision rail must then show where the pool should be sold, not which one
purchase contract is currently selected.

## Home Screen Layout

The first screen must be dominated by the European gas map. The map must show:

- upstream resource contracts and resource-pool exposure;
- LNG terminals, beach delivery points, hubs, interconnectors, storage, and
  major route corridors;
- route options from resource origin to sale/delivery target;
- available and blocked routes;
- TSO access constraints;
- capacity and outage state when backend data exists;
- live market movement relevant to selected portfolio routes;
- strategy status and warning overlays.

Resource markers must identify where the pool is available: beach delivery
points, LNG terminals, hubs, interconnectors, and other customer-loaded delivery
or title-transfer points. Recommended sale paths must be drawn at the same time
so the trader can see the whole allocation, including split routes and blocked
alternatives.

The Network map also carries a compact resource-path overlay. Each path row is
derived from backend resource-pool options or optimization output and shows the
resource delivery point, recommended sale/delivery target, quantity, capacity
limit, route cost, sale price, net margin, route state, and blocker/warning
state. If source or target nodes can be matched in the reference network, the
map may animate a highlighted corridor. If no persisted contracts or sale
options exist, the overlay must show the blocked/empty state instead of
inventing a route.

Map labels are budgeted, not exhaustive. The default map should keep low-
priority assets as colored points and reserve visible labels for active
resource-path endpoints, hubs, search matches, and named market points. Full
asset identity belongs in search results, hover/click inspectors, and detail
pages, not as hundreds of always-on map labels.

The map must not be a decorative background. It is the main work surface.

## Home Information Architecture

The home screen must remain clean. It has exactly three functional zones:

1. Persistent top bar: workspace menu, global search, runtime status, language,
   and theme.
2. Left rail: resource-pool context, recommended sale-path controls, and active
   portfolio resources.
3. Right rail: pool PnL, route allocation ladder, economics snapshot, and
   strategy/warning signal.

Detailed data-source diagnostics, PostgreSQL health, TSO access tables,
capacity summaries, tariff tables, and provider credentials do not belong on
the home screen. They belong in Data Sources, Runtime, Market, Scenario, or
Contracts.

The home screen may show a compact runtime/input blocker list when the resource
pool cannot be optimized. That list is limited to the missing prerequisites:
runtime PostgreSQL connectivity, persisted contracts, route candidates, TSO
tariffs, and market price observations. It must not become a duplicate Source
Center, Runtime page, or tariff table.

If a compact live tape is later reintroduced, it must not overlap the rails,
MapLibre controls, or map attribution, and it may only show:

- portfolio exposure volume;
- total pool volume and unallocated volume;
- relevant hub/day-ahead reference prices;
- ICE OCM or other intraday marks when entitled;
- ECB FX when cross-currency economics are visible;
- live indicative PnL;
- imported external screen-order posture and portfolio PnL snapshots;
- active strategy process state;
- latest decision-support signal;
- warning count.

Every value must show source/freshness when the backend provides it.

The optimize action must be disabled until the backend confirms all required
PostgreSQL-backed inputs exist. The client must display the blockers, then send
the user to the relevant workspace: Data Sources for provider and ingestion
issues, Runtime for database readiness, Contracts for resource entry, Scenario
for route economics, and Market for price observations.

## Map Interaction

Required interactions:

- search terminal, hub, TSO, balancing point, field, or source;
- toggle network, LNG, interconnector, hub, storage, weather, contract, market,
  route, and warning layers;
- click a route or asset to open an inspector;
- compare route alternatives visually;
- highlight blocked route causes such as missing TSO access, missing tariff,
  missing capacity, missing terminal slot, missing provider credential, or stale
  data;
- launch route-cost, LNG regas readiness, resource-pool, or strategy evaluation
  through backend API calls only.

When an active route/PnL context exists, the map may highlight it only when every
displayed segment has licence-approved line coordinates and a successful geometry
verification result. A route candidate without verified geometry remains available
in route evidence and decision cards, but the map does not draw a source-to-target
shortcut or inferred leg sequence.

The route geometry quality ladder is explicit:

- `surveyed_pipeline_route`: approved polyline geometry that may be rendered;
- `source_derived_leg_sequence`: topology evidence only; not rendered as pipe;
- `source_derived_corridor`: commercial corridor evidence only; not rendered;
- `directLineFallback`: legacy state meaning geometry unavailable; no fallback
  line is drawn.

The resource-path overlay shows the quality label and warning. Physical map layers
accept only `verification_status=verified`, an approved `geometry_authority`, and a
complete `geometry_coordinates` sequence. Approximate physical LNG, IP, or pipeline
coordinates are suppressed; virtual market hubs may use representative market-area
positions when labelled as such.

## Resource-Pool Decision Rail

The right rail on the home screen must summarize the portfolio decision:

- total expected PnL for the pool;
- total allocated and unallocated quantity;
- each recommended sale route with destination market, allocated quantity,
  route cost, sale price, marginal netback, PnL contribution, capacity limit,
  TSO access state, and warning state;
- blocked routes with explicit blockers;
- contract-level PnL attribution as a drill-down, not as the primary decision.

If a cheap route has limited capacity, the UI must show the partial allocation
to that route and the next-best treatment for the remainder. If the remainder is
uneconomic to reroute, the recommendation should show local sale, alternative
market sale, or hold/no-sale rather than forcing a loss-making path.

## Contract Entry

Contract detail work belongs on a separate Contracts page. The page must follow
the EFET-style structure in
`docs/contracts/21_RESOURCE_POOL_CONTRACT-EN.md`: agreement, product and term,
delivery, quantity/tolerance, price, costs, capacity rights, settlement/cash,
and restrictions. The home screen consumes the resulting resource-pool state
after it is persisted in PostgreSQL and exposed by `/api`.

## Separate Detail Tabs Or Windows

Detailed work must not crowd the home map. Provide separate tabs/windows for:

- price monitoring;
- portfolio/resource combinations;
- route-cost and LNG regas analysis;
- strategy backtest, shadow-run, and live monitoring;
- imported external order records;
- warning and alert center;
- source lineage and entitlement;
- glossary;
- user manual;
- credentials and settings.

Order records are imported/reference records only in V1. The product must not
place, route, amend, or cancel orders.

## Strategy UX

Strategy panels must support:

- backtest mode;
- shadow-run mode;
- live-monitor mode;
- configured resource pool;
- selected time window such as 15:00-17:00;
- bar size such as 5 minutes;
- components such as SAP versus ICIS day-ahead versus ICE OCM, mean reversion,
  scoring, best buckets, and weighted combinations;
- risk controls such as max OCM allocation, minimum day-ahead allocation,
  maximum single-market volume, minimum expected margin, stop-loss, stale-data
  blocking, and TSO-access blocking;
- paper allocation targets with rationale, missing inputs, warnings, sources,
  and human-review status.

The UI must use decision-support language: signal, candidate, option, target,
review. Do not use execution language.

## Visual Quality Bar

Commercial delivery quality means:

- dense but readable professional trading-workstation layout;
- restrained colors with clear semantic state;
- no marketing hero, landing page, or decorative filler;
- stable responsive dimensions;
- clear light/dark/system theme support;
- English and Mandarin Chinese strings through i18n;
- map and data panels remain usable on desktop and laptop screens;
- mobile/tablet degrade to map-first tabs, not a squeezed dashboard.

## Data Boundary

The cockpit must consume only backend `/api` or SDK surfaces. It must not
read PostgreSQL, backend files, vendor files, `.env`, or credentials directly.

If data is missing, the client must show the missing state. It must not create
browser-side mock, sample, synthetic, generated, or fallback route/capacity/
tariff/price records. Preview/test rows, when required, must be inserted into
PostgreSQL with explicit source provenance and then read back through `/api`.
Price previews must use `EEX_Sim`, `ICE_OCM_Sim`, and `ICIS_Sim` rows in the
runtime `market_observations` table so the product behaves as if licensed feed
rows are present while still labeling the source as simulated.
