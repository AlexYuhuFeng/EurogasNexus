# Web Client Design Spec

## Objective

The Web client is the primary Eurogas Nexus decision-support workspace. It is
map-first and resource-pool-native: the European gas network map is the main work
surface, with market, capacity, resource terms, weather, scenario, strategy, and
review context attached to map objects and route candidates. It accesses runtime
data through the backend `/api` API.

## Product Boundary

The Web client does not own business truth. It must not read PostgreSQL, import
backend DB/runtime-store modules, read local backend files, load raw vendor data,
or handle provider access material directly.

The browser-side data path is:

```text
Web UI -> web API client -> backend /api -> backend repositories -> PostgreSQL
```

The Web client must not implement trade execution, order entry, nomination
submission, official recommendation, settlement/accounting, ETRM replacement, or
auto-trading workflows.

## Recommended Stack

Use the exact library contract in `docs/clients/CLIENT_TECH_STACK.md`:

- React 19;
- TypeScript;
- Vite;
- MapLibre GL;
- deck.gl;
- Zustand;
- TanStack Query;
- i18next and react-i18next;
- lucide-react;
- plain CSS/CSS modules.

Do not use Next.js, Electron, Tailwind, Material UI, Ant Design, Bootstrap, or
Redux unless a later approved milestone changes the tech-stack contract.

## Navigation

Eurogas Nexus uses grouped workspace navigation, not a flat list of equal pages.
Technical workspace ids remain stable for compatibility.

### Decision Workspace

1. Network
2. Scenario
3. Review

### Commercial Inputs

1. Resource Terms, technical id `contracts`
2. Market
3. Capacity
4. Market Positioning, technical id `orders`

### Analytics

1. Strategy
2. Glossary

### Operations

1. Data Sources
2. Runtime
3. Settings
4. Manual

Every workspace must support a direct URL query entry for release QA, customer
support, and customer training. The canonical format is `?workspace=<id>`, where
`<id>` is one of `network`, `scenario`, `review`, `contracts`, `market`,
`capacity`, `orders`, `strategy`, `glossary`, `sources`, `runtime`, `settings`,
or `manual`. Unknown workspace values must fall back to `network`.

Authoritative navigation spec:

- `docs/clients/WORKSPACE_NAVIGATION_SPEC.md`

## App Frame

Use a map-first decision cockpit layout. The home screen must be dominated by the
European gas map and must show portfolio exposure, live prices where available,
indicative PnL, strategy process state, and warnings without forcing the user to
leave the map. The Top status bar remains the persistent runtime and warning
anchor. Active resource terms feed a portfolio resource pool; route cards show
sale allocation for the pool and PnL attribution as drill-down.

Persistent layout:

```text
+--------------------------------------------------------------------------------+
| Top bar: grouped workspace menu, backend/DB status, language/theme, warnings    |
+--------------------------------------------------------------------------------+
+----------------------+----------------------------------+----------------------+
| Resource-pool rail   | European gas map                 | Decision rail        |
| resources, blockers, | nodes, routes, corridors, layers | pool PnL, route      |
| route controls       | and selected route context       | ladder, economics    |
+----------------------+----------------------------------+----------------------+
| Workspace pages: scenario, resource terms, market, capacity, strategy, review   |
+--------------------------------------------------------------------------------+
```

Responsive behavior:

- desktop: top bar, map, left resource rail, and right decision rail visible;
- tablet: inspector becomes a drawer;
- mobile: map/workspace first, nav collapses, bottom panel becomes tabs.

## Screen: Network

Purpose:

- operate the map-first decision cockpit for European gas infrastructure,
  resource-pool exposure, route context, market movement, strategy process state,
  and warning state.

Initial content:

- map surface;
- layer controls;
- resource-path overlay showing persisted resource delivery point, target sale
  point, quantity, capacity limit, route cost, sale price, net margin, route
  state, and blockers from backend resource-pool data;
- pool allocation summary showing total pool volume, allocated quantity,
  unallocated quantity, and weighted net margin;
- route status legend for allocated, candidate, and blocked paths;
- path cards exposing allocation evidence, capacity headroom, path-level PnL/day,
  and capacity bottleneck warnings;
- path cards exposing route ranking evidence: rank, recommendation reason,
  capacity utilization, and required TSO access so traders can understand why a
  path is allocated, still only a candidate, or blocked;
- source/freshness and warning evidence.

The Network home must not contain data-source forms, runtime DB administration,
or LLM report generation panels. Those belong on Data Sources, Runtime, or
Review.

## Screen: Scenario

Purpose:

- run route-cost, LNG readiness, resource-pool, or strategy scenarios against
  already-entered resource-pool and resource-term context, and show what is
  missing before a backend workflow runs.

Sections:

- resource/source;
- destination or market area;
- route preference;
- volume;
- timing;
- price assumptions;
- cost assumptions;
- constraints;
- notes.

Outputs must be labelled as decision support, human review required, and not an
execution instruction.

## Screen: Resource Terms

Technical workspace id: `contracts`.

Purpose:

- capture EFET-style purchase, LNG, hub, and capacity-related resource terms that
  feed the portfolio resource pool without becoming an ETRM, official contract
  master, booking workflow, settlement system, nomination workflow, or
  trade-capture system.

Content:

- import zone for JSON drafts and staged text evidence;
- upload zone for customer-owned contract files, import diagnostics, and
  manual correction before backend persistence;
- beach delivery point, title-transfer point, and terminal access remain visible
  in the manual intake surface;
- agreement and counterparty assumptions;
- product, term, delivery mode, delivery point, title-transfer point, and beach
  delivery point;
- quantity, tolerance, nomination, interruption, and balancing assumptions;
- price formula or index basis, currency, unit, premium/discount, and source;
- variable costs, fuel/loss, fees, regas, storage, and balancing allowances;
- capacity rights, TSO access, terminal access, route eligibility, and expiry;
- settlement timing, invoice/payment lag, screen cash lag, and early-cash-value
  inputs;
- restrictions, permitted sale markets, blocked TSOs/routes, source/freshness,
  entitlement, and warning state;
- persisted resource-term library loaded through backend API.

The page may use API field names such as `contract_id` and
`upstream-contracts` internally for compatibility, but user-facing copy should
say Resource Terms or Resource-Term Assumptions.

Forbidden:

- official contract booking;
- contract lifecycle management;
- nomination submission;
- order entry;
- trade capture;
- settlement/accounting;
- official approval workflow;
- ETRM replacement behavior.

Authority:

- `docs/contracts/21_RESOURCE_POOL_CONTRACT-EN.md`
- `docs/contracts/21_RESOURCE_POOL_CONTRACT-CN.md`

## Screen: Market

Purpose:

- provide market price, FX, weather, demand, outage, and freshness context
  without mixing in imported market-positioning or PnL tables.

Rules:

- show backend-served market observations, ECB FX, and source metadata;
- render a terminal-style gas market board when sourced observations are present;
- show within-day, day-ahead, and month-ahead tenor controls;
- show regional comparison only when both sides have comparable currency/unit
  rows;
- do not invent market data or render client-side fake observations.

## Screen: Capacity

Purpose:

- inspect physical network operating context that affects route feasibility,
  route cost, capacity allocation, and TSO access.

Content:

- ENTSOG flow observations;
- ENTSOG capacity observations;
- TSO access points and available product flags;
- published tariff references by point, direction, product, and TSO;
- GIE AGSI storage and GIE ALSI LNG records;
- unavailable or entitlement states when backend data is missing.

Capacity page data must be read from backend `/api` responses backed by
PostgreSQL. The client must not synthesize capacity, flow, tariff, storage, LNG,
or TSO-access rows locally.

## Screen: Market Positioning

Technical workspace id: `orders`.

Purpose:

- inspect imported screen observations and portfolio PnL snapshots without
  presenting any order-entry, trade-capture, or execution workflow.

Content:

- live portfolio summary;
- read-only screen observation table;
- read-only portfolio PnL snapshot table;
- source, timestamp, account label, venue, hub, quantity, price, and status;
- clear unavailable state when the backend has no imported records.

Market Positioning must consume `/api/portfolio/*`. It must not write orders,
route orders, approve trades, submit nominations, or store provider access
material in the client.

## Screen: Strategy

Purpose:

- inspect strategy backtests and paper shadow runs over approved market,
  physical, capacity, resource-term, and weather context;
- present the strategy workspace as a shadow-run terminal for trader-reviewed
  signal monitoring and scenario comparison;
- expose market tape, paper state, allocation ladder, risk stack, source
  evidence, warning stack, and candidate action in one terminal surface;
- include a price-basis comparison board for within-day, day-ahead, monthly,
  ICIS assessment, ICE OCM mark, EEX curve, and FX contexts;
- cover within-day, day-ahead, monthly, ICIS assessments, ICE OCM marks, EEX
  curves, and ECB FX as explicit basis families;
- Basis families: within-day, day-ahead, monthly, ICIS assessments, ICE OCM marks, EEX curves, and ECB FX.
- include a selected price-basis control for switching active basis context;
- show contract-level PnL attribution so resource-pool strategy output can be
  traced back to persisted resource terms;
- include a stale/simulated/unavailable data banner whenever price bases or
  market observations are not live and fully sourced;
- show a resource-pool PnL curve for comparing shadow-run outcomes across the
  selected portfolio resources;
- monitor live signal processes when the backend has authorized data and
  operator-configured inputs.

Shadow run creates no orders, trades, nominations, execution records, or official
recommendations.

Current endpoint:

```text
POST /api/strategy-lab/evaluate
```

## Screen: Review

Purpose:

- compare candidates and inspect decision-support output metadata before any
  human commercial decision.

Required panels:

- candidate comparison table;
- route option map/table with cost stack, capacity/resource-term constraints,
  and market/weather signal state;
- warning stack;
- assumptions;
- missing inputs;
- source references;
- lineage;
- freshness/data quality;
- export status;
- LLM-assisted explanation with citations when backend analysis exists.

Export remains disabled until governance/export policy is implemented.

## Screen: Data Sources

Purpose:

- inspect and maintain source references, categories, access posture, health,
  freshness, and lineage for displayed outputs.

Provider categories include prices, FX, infrastructure, TSO tariffs, weather, and
LLM. Every live-source panel must show entitlement, freshness, source status,
degraded/offline state, and whether data is live, delayed, demo, partial, or
unavailable.

## Screen: Glossary

Purpose:

- explain gas, LNG, storage, trading venue, capacity, route economics, weather,
  and data-governance terms in a consistent backend-served vocabulary;
- render the selected term as a wiki-style article with context, evidence,
  related entities, and source references instead of a generic card;
- cover institutions, entities, venues, business models, contracts, prices,
  hubs, terminals, clearing, finance, and operational concepts;
- support English and Mandarin Chinese from the same backend term contract;
- show operational context for high-value terms such as TTF, NBP, ICE OCM, ICIS
  Heren, GATE LNG, and Zeebrugge Entry Point when PostgreSQL contains matching
  runtime rows.

## Screen: Runtime

Purpose:

- prove backend/API/DB status before deeper workflows.

Content:

- `/api/health` state;
- runtime status if endpoint exists;
- API base URL;
- active route profile;
- DB validation status from backend when available;
- warning if simulated/preview provenance, stale data, missing DB tables, or
  unavailable backend capabilities are reported by the API.

## Screen: Settings

Purpose:

- configure client-only display preferences, default units, currency, session
  defaults, source-access posture, and operating guardrails.

Allowed:

- backend base URL when the milestone chooses runtime configuration;
- theme density;
- default map layers;
- local UI preferences;
- language switch with English and Mandarin Chinese;
- light, dark, and system theme switch;
- default display currency, energy unit, flow/volume unit, and price basis;
- service-access posture summary read from backend API.

Forbidden:

- DB URL;
- provider access material;
- raw file paths to backend data.

## LLM Analysis Panel

LLM output should help analysts interpret structured backend data, market
movement, route changes, missing inputs, and conflicting signals. It must show
source references, assumptions, missing inputs, warnings, prompt/template version,
and provider/model metadata when available. It must never present LLM text as
official trading advice.

## Runtime Data Policy

Trial and release clients must read runtime data through the backend API. If the
customer has not connected a provider or loaded portfolio records, the UI must
show explicit empty, unavailable, stale, access-missing, or table-missing states.

Demo or test records are allowed only when they are inserted into PostgreSQL with
clear demo/test provenance and are visible as such in API responses and UI state.
They must not be copied from historical projects, vendor files, licensed market
data, or internal reports.
