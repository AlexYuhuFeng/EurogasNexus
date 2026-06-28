# Web Client Design Spec

## Objective

The web client is the primary Eurogas Nexus research workspace. It is
map-first and resource-pool-native: the European gas network map is the main
work surface, with market, capacity, contract, weather, scenario, strategy, and
review context attached to map objects and route candidates. It accesses
runtime data through the backend `/api` API.

## Product Boundary

The web client does not own business truth. It must not read PostgreSQL, import
backend DB/runtime-store modules, read local backend files, load raw vendor
data, or handle connector credentials directly.

The browser-side data path is:

```text
Web UI -> web API client -> backend /api -> backend repositories -> PostgreSQL
```

The web client must not implement trade execution, order entry, nomination
submission, official recommendation, or auto-trading workflows.

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
Redux in V1 unless a later milestone explicitly changes the tech-stack contract.

Internet required: yes if dependencies must be installed or current package
documentation must be verified.

If dependencies or backend endpoints are unavailable, create only structure,
types, interface contracts, and a gap report. Trial and release builds must not
replace missing PostgreSQL-backed data with client-side mock runtime data.

Internationalization and theme requirements:

- support `en-US` and `zh-CN`;
- all visible strings go through i18n resources;
- support light, dark, and system theme modes;
- use CSS custom properties for themes;
- store only non-sensitive locale/theme preferences.

## App Frame

Use a map-first trader cockpit layout. The home screen must be dominated by the
European gas map and must show portfolio exposure, live prices, indicative PnL,
strategy process state, and warnings without forcing the trader to leave the
map. The Top status bar remains the persistent runtime and warning anchor.
All active purchase contracts are represented as a resource pool on the home
screen; route cards show sale allocation for the pool and contract PnL appears
as attribution drill-down.

Use this persistent layout:

```text
+--------------------------------------------------------------------------------+
| Top bar: workspace, backend/DB status, language/theme, warnings                 |
+--------------------------------------------------------------------------------+
+----------------------+----------------------------------+----------------------+
| Resource-pool rail   | European gas map                 | Decision rail        |
| resources, blockers, | nodes, routes, corridors, layers | pool PnL, route      |
| route controls       | and selected route context       | ladder, economics    |
+----------------------+----------------------------------+----------------------+
| Dedicated pages: market, scenario, contracts, strategy, data sources, runtime   |
+--------------------------------------------------------------------------------+
```

Responsive behavior:

- desktop: top bar, map, left resource rail, and right decision rail visible;
- tablet: inspector becomes a drawer;
- mobile: map/workspace first, nav collapses, bottom panel becomes tabs.

For terminal-density lessons from the historical Windows demo QA evidence, read
`docs/clients/WINDOWS_DEMO_UX_REFERENCE.md`.

## Navigation

Primary navigation items:

1. Network
2. Capacity
3. Market
4. Scenario
5. Contracts
6. Strategy
7. Review
8. Data Sources
9. Glossary
10. Runtime
11. Settings
12. Manual
13. Order Records

Navigation labels are product workflow labels, not implementation names.

Home-screen authority:

- `docs/clients/MAP_FIRST_TRADER_COCKPIT_SPEC-EN.md`
- `docs/clients/MAP_FIRST_TRADER_COCKPIT_SPEC-CN.md`

## Screen: Runtime

Purpose:

- prove backend/API/DB status before deeper workflows.

Content:

- `/api/health` state;
- runtime status if endpoint exists;
- API base URL;
- active route profile;
- DB validation status from backend when available;
- warning if demo provenance, stale data, missing DB tables, or unavailable
  backend capabilities are reported by the API.

States:

- healthy;
- degraded;
- backend unavailable;
- DB unavailable;
- route not implemented.

## Screen: Network

Purpose:

- operate the map-first trader cockpit for European gas infrastructure,
  resource-pool exposure, route context, live market movement, strategy process
  state, and warning state.

Initial content:

- map surface;
- layer controls;
- left resource-pool rail with active resources, blockers, and route controls;
- right decision rail with net PnL, allocation ladder, economics snapshot, and
  strategy/warning signal;
- selected route context and route blocking/warning overlay.

Not allowed on the Network home:

- data-source diagnostics tables;
- runtime DB health panels;
- TSO access/capacity/tariff summary tables;
- credentials forms;
- glossary detail;
- LLM report generation panels.

Those belong on Data Sources, Runtime, Market, Scenario, Contracts, Glossary,
or Strategy pages.

Layers:

- hubs and market areas;
- pipelines and corridors;
- LNG terminals;
- storage sites;
- beach delivery points;
- interconnectors;
- zones and countries.
- flow, capacity, outage, and constraint overlays;
- ECB FX, EEX, Trayport, ICE OCM market overlays when licensed and exposed by
  backend;
- ENTSOG and GIE source posture overlays when licensed/exposed by backend;
- weather/HDD/CDD and demand-pressure overlays;
- contract/capacity exposure overlays;
- research route candidate and warning overlays.
- upstream resource contracts, resource pools, and external order records when
  imported through backend API.

Interactions:

- select asset;
- search asset;
- toggle layer;
- filter by asset type;
- inspect source and lineage;
- open related scenario draft.
- run backend route-cost, LNG regas, resource-pool, or strategy evaluation for
  the selected route/resource context.

Do not load live vendor data from the browser.

External order records:

- may be imported and displayed as reference context only;
- must not become order entry, order amendment, order cancellation, trade
  capture, or execution workflow.

Home decision rail:

- total pool PnL, allocated quantity, and unallocated quantity;
- each recommended sale path with quantity, sale market, route cost, sale
  price, netback, PnL contribution, capacity limit, TSO access, and blockers;
- contract-level attribution only as drill-down below the route decision;
- explicit empty or blocked state if PostgreSQL has no portfolio, price,
  capacity, or tariff rows.

## Screen: Contracts

Purpose:

- capture EFET-style purchase, LNG, hub, and capacity-related terms that feed
  the portfolio resource pool without becoming an ETRM, booking, nomination, or
  trade-capture system.

Content:

- agreement and counterparty metadata;
- product, term, delivery mode, delivery point, and title-transfer point;
- quantity, tolerance, nomination, interruption, and balancing terms;
- price formula or index basis, currency, unit, premium/discount, and source;
- variable costs, fuel/loss, fees, regas, storage, and balancing allowances;
- capacity rights, TSO access, terminal access, route eligibility, and expiry;
- settlement frequency, invoice/payment lag, screen cash lag, and early cash
  value inputs;
- restrictions, permitted sale markets, blocked TSOs/routes, source/freshness,
  entitlement, and warning state.

Authority:

- `docs/contracts/21_RESOURCE_POOL_CONTRACT-EN.md`
- `docs/contracts/21_RESOURCE_POOL_CONTRACT-CN.md`

Forbidden:

- official booking;
- nomination submission;
- order entry;
- trade capture;
- official approval workflow.

## Screen: Scenario

Purpose:

- run route-cost, LNG readiness, resource-pool, or strategy scenarios against
  already-entered resource-pool and contract context, and show what is missing
  before a backend workflow runs.

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

Validation:

- show missing required inputs inline;
- show assumptions before submission;
- disable workflow actions when backend capability is missing;
- label outputs as decision support, human review required, and not an
  execution instruction.

## Screen: Market

Purpose:

- provide context panels for price, flow, capacity, storage, LNG, weather,
  demand, outages, and freshness.

V1 client behavior:

- show backend-served market, FX, capacity, tariff, and source metadata;
- if an endpoint or table is missing, show an explicit unavailable state with
  the backend error code and required operator action;
- do not invent market data or render client-side fake observations.

Live source panels:

- ECB FX;
- ENTSOG flow/capacity/outage context;
- GIE AGSI/ALSI storage and LNG context;
- EEX exchange market context;
- Trayport market context;
- ICE OCM within-day/OCM context;
- weather/HDD/CDD provider context.

Every live-source panel must show entitlement, freshness, source status,
degraded/offline state, and whether data is live, delayed, demo, partial, or
unavailable.

## Screen: Strategy

Purpose:

- inspect strategy backtests and paper shadow runs over approved market,
  physical, capacity, contract, and weather context.
- monitor live strategy processes when the backend has authorized data and
  operator-configured inputs.

Content:

- strategy hypothesis;
- observation window;
- paper state;
- candidate actions for human review;
- hypothetical metrics where supported by licensed data;
- missed/blocked route reasons;
- source snapshots;
- warning stack.
- time window such as 15:00-17:00;
- bar size such as 5 minutes;
- components such as SAP/ICIS day-ahead versus ICE OCM, mean reversion,
  scoring, best buckets, and weighted combinations;
- risk controls such as max OCM allocation, minimum day-ahead allocation,
  maximum single-market volume, minimum expected margin, stop-loss, stale-data
  blocking, and TSO-access blocking.

Shadow run creates no orders, trades, nominations, execution records, or
official recommendations.

Current endpoint:

```text
POST /api/strategy-lab/evaluate
```

## Screen: Review

Purpose:

- compare candidates and inspect research output metadata.

Required panels:

- candidate comparison table;
- route option map/table with cost stack, capacity/contract constraints, and
  market/weather signal state;
- warning stack;
- assumptions;
- missing inputs;
- source references;
- lineage;
- freshness/data quality;
- export status.
- LLM-assisted explanation with citations when backend analysis exists.

Export:

- disabled until governance/export policy is implemented;
- explain restricted state without legal advice.

## Screen: Data Sources

Purpose:

- let users inspect and maintain source references, categories, credentials,
  health, freshness, and lineage for displayed outputs.

Content:

- category rail: prices, FX, infrastructure, TSO tariffs, weather, and LLM;
- providers such as Platts, ICIS, Argus, EEX, ICE OCM, Trayport, Kpler, ECB,
  ENTSOG, GIE AGSI/ALSI, weather, and DeepSeek;
- source status, connectivity status, credential state, last success, last
  failure, expected freshness, diagnostics, and record count;
- backend-owned credential entry and redacted status display;
- infrastructure record previews for ENTSOG capacity/flows, GIE storage/LNG,
  TSO access, and tariff rows;
- degraded, credential-missing, no-records, and runtime-DB-missing states.

## Screen: Glossary

Purpose:

- explain gas, LNG, storage, trading venue, capacity, route economics, weather,
  and data-governance terms in a consistent backend-served vocabulary.
- support English and Mandarin Chinese from the same backend term contract.

Content:

- searchable term list;
- category filters;
- concise and detailed definition;
- related terms;
- source/reference note;
- reviewed timestamp.

Current V1 contract:

- use `GET /api/glossary?lang=en`;
- use `GET /api/glossary?lang=zh-CN`;
- use `GET /api/glossary/{term}/context?lang=...&duration_start_utc=...&duration_end_utc=...`;
- show term, category, localized definition, aliases when useful, and related
  terms;
- show quick operational context buttons for high-value terms such as `TTF`,
  `GATE LNG`, `Zeebrugge Entry Point`, `ICIS Heren`, `NBP`, and `ICE OCM`;
- show the selected duration, capacity, capacity in use, utilization percent,
  related prices, live marks, routes, linked contracts, and warnings returned by
  the backend context endpoint;
- do not hard-code glossary definitions in the client beyond test fixtures.

## LLM Analysis Panel

Purpose:

- help analysts interpret structured backend data, market movement, route
  changes, missing inputs, and conflicting signals.

Rules:

- use only backend-provided `/api/analysis/*`, `/api/reports/*`, and
  `/api/glossary/{term}/context` outputs;
- DeepSeek is the first supported V1 live provider, invoked only by backend when
  the operator enables provider invocation and a credential is configured;
- show citations/source references next to claims;
- show assumptions, missing inputs, warnings, prompt/template version, and
  provider/model metadata when available;
- label outputs as decision support and human-review-required;
- never present LLM text as official trading advice.

Current endpoints:

```text
GET /api/analysis/ontology
POST /api/analysis/query
POST /api/reports/portfolio
GET /api/glossary/{term}/context
```

## Screen: Settings

Purpose:

- configure client-only preferences.

Allowed:

- backend base URL when the milestone chooses runtime configuration;
- theme density;
- default map layers;
- local UI preferences.
- language switch with English and Mandarin Chinese;
- light, dark, and system theme switch.

Forbidden:

- DB URL;
- vendor API keys;
- service tokens;
- raw file paths to backend data.

## Component Inventory

Build these components before business screens become complex:

- `AppShell`
- `TopStatusBar`
- `PrimaryNavigation`
- `WorkspaceTabs`
- `MapWorkspace`
- `LayerControlPanel`
- `CapacityContractPanel`
- `InspectorRail`
- `BottomResultsPanel`
- `RouteCandidateMapOverlay`
- `StrategyShadowRunPanel`
- `WeatherSignalPanel`
- `MarketMovementAnalysisPanel`
- `GlossaryDrawer`
- `RuntimeStatusPanel`
- `WarningStack`
- `MissingInputsList`
- `SourceReferenceTable`
- `LineageTimeline`
- `HumanReviewRequiredBadge`
- `ApiErrorState`
- `FeaturePartialState`

## Runtime Data Policy

Trial and release clients must read runtime data through the backend API. If
the customer has not connected a provider or loaded portfolio records, the UI
must show explicit empty, unavailable, stale, credential-missing, or
table-missing states.

Demo or test records are allowed only when they are inserted into PostgreSQL
with clear demo/test provenance and are visible as such in API responses and UI
state. They must not be copied from historical projects, vendor files, licensed
market data, or internal reports.

## First Web Implementation Prompt

Use this prompt only after the backend activation gates are met:

```text
Read AGENTS.md, docs/clients/README.md, docs/clients/CLIENT_DELIVERY_MILESTONES.md, docs/clients/CLIENT_API_CONTRACT.md, docs/clients/CLIENT_DESIGN_SYSTEM.md, and docs/clients/WEB_CLIENT_DESIGN_SPEC.md. Implement Web Milestone W1 only. If internet is unavailable or Node dependencies cannot be installed, create the planned file structure, TypeScript interfaces, API contracts, and a gap report. Do not add trade execution, live vendor calls from the browser, direct DB access, client-side runtime mock data, or Windows packaging.
```
