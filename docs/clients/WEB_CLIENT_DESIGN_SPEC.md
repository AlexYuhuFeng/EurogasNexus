# Web Client Design Spec

## Objective

The web client is the primary Eurogas Nexus research workspace. It is
map-first: the European gas network map is the main work surface, with market,
capacity, contract, weather, scenario, strategy, and research review context
attached to map objects and route candidates. It accesses runtime data through
the backend `/api/v1` API.

## Product Boundary

The web client does not own business truth. It must not read PostgreSQL, import
backend DB/runtime-store modules, read local backend files, load raw vendor
data, or handle connector credentials directly.

The browser-side data path is:

```text
Web UI -> web API client -> backend /api/v1 -> backend repositories -> PostgreSQL
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

Offline fallback: create structure, types, mocked API client, and gap report.

Internationalization and theme requirements:

- support `en-US` and `zh-CN`;
- all visible strings go through i18n resources;
- support light, dark, and system theme modes;
- use CSS custom properties for themes;
- store only non-sensitive locale/theme preferences.

## App Frame

Use this persistent layout:

```text
+--------------------------------------------------------------------------------+
| Top status bar: workspace name, backend status, DB status, profile, warnings     |
+------+----------------------------------------------+--------------------------+
| Nav  | Main workspace                               | Inspector                |
|      |                                              |                          |
|      | Map / scenario / context surface             | selected asset, sources, |
|      |                                              | assumptions, lineage     |
|      |                                              |                          |
+------+----------------------------------------------+--------------------------+
| Bottom panel: candidates, comparisons, warnings, missing inputs, output review   |
+--------------------------------------------------------------------------------+
```

Responsive behavior:

- desktop: nav, main, inspector, and bottom panel visible;
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
5. Strategy
6. Review
7. Sources
8. Glossary
9. Runtime
10. Settings

Navigation labels are product workflow labels, not implementation names.

## Screen: Runtime

Purpose:

- prove backend/API/DB status before deeper workflows.

Content:

- `/api/v1/health` state;
- runtime status if endpoint exists;
- API base URL;
- active route profile;
- DB validation status from backend when available;
- warning if running against mocks.

States:

- healthy;
- degraded;
- backend unavailable;
- DB unavailable;
- route not implemented.

## Screen: Network

Purpose:

- inspect European gas infrastructure and route context.

Initial content:

- map surface;
- layer controls;
- selected asset inspector;
- source/freshness badges;
- warning banner for synthetic or incomplete data.

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

Interactions:

- select asset;
- search asset;
- toggle layer;
- filter by asset type;
- inspect source and lineage;
- open related scenario draft.

Do not load live vendor data from the browser.

## Screen: Capacity

Purpose:

- manage capacity and contract context for research scenarios without becoming
  an ETRM, booking, nomination, or trade-capture system.

Content:

- capacity contract inventory;
- booked/available capacity context;
- tenor, expiry, direction, and route eligibility;
- tariff, fee, fuel, loss, regas, storage, and transport cost assumptions;
- contract exposure linked to map routes and assets;
- source, freshness, entitlement, and warning state.

Forbidden:

- official booking;
- nomination submission;
- order entry;
- trade capture;
- official approval workflow.

## Screen: Scenario

Purpose:

- capture research scenario inputs and show what is missing before a backend
  workflow runs.

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
- label outputs as research-only.

## Screen: Market

Purpose:

- provide context panels for price, flow, capacity, storage, LNG, weather,
  demand, outages, and freshness.

V1 client behavior:

- show backend metadata only if APIs exist;
- otherwise show mocked panel shells and `PARTIAL: backend API not available`;
- do not invent market data.

Live source panels:

- ECB FX;
- ENTSOG flow/capacity/outage context;
- GIE AGSI/ALSI storage and LNG context;
- EEX exchange market context;
- Trayport market context;
- ICE OCM within-day/OCM context;
- weather/HDD/CDD provider context.

Every live-source panel must show entitlement, freshness, source status,
degraded/offline state, and whether data is live, delayed, mocked, or partial.

## Screen: Strategy

Purpose:

- inspect strategy backtests and paper shadow runs over approved market,
  physical, capacity, contract, and weather context.

Content:

- strategy hypothesis;
- observation window;
- paper state;
- candidate actions for human review;
- hypothetical metrics where supported by licensed data;
- missed/blocked route reasons;
- source snapshots;
- warning stack.

Shadow run creates no orders, trades, nominations, execution records, or
official recommendations.

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

## Screen: Sources

Purpose:

- let users inspect source references and lineage for displayed outputs.

Content:

- source ID;
- source type;
- source family such as ECB, ENTSOG, GIE, EEX, Trayport, ICE OCM, or weather;
- retrieval or observation timestamp;
- transformation stage;
- quality/freshness state;
- entitlement/export state;
- linked outputs.

## Screen: Glossary

Purpose:

- explain gas, LNG, storage, trading venue, capacity, route economics, weather,
  and data-governance terms in a consistent backend-served vocabulary.

Content:

- searchable term list;
- category filters;
- concise and detailed definition;
- related terms;
- source/reference note;
- reviewed timestamp.

## LLM Analysis Panel

Purpose:

- help analysts interpret structured backend data, market movement, route
  changes, missing inputs, and conflicting signals.

Rules:

- use only backend-provided `/api/v1/analysis/*` outputs;
- show citations/source references next to claims;
- show assumptions, missing inputs, warnings, prompt/template version, and
  provider/model metadata when available;
- label outputs as research-only and human-review-required;
- never present LLM text as official trading advice.

## Screen: Settings

Purpose:

- configure client-only preferences.

Allowed:

- backend base URL when the milestone chooses runtime configuration;
- theme density;
- default map layers;
- local UI preferences.

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
- `ResearchOnlyBadge`
- `HumanReviewRequiredBadge`
- `ApiErrorState`
- `FeaturePartialState`

## Mock Data Policy

Mock data must be synthetic and visibly labeled in UI state. It must not be
copied from historical projects, vendor files, market data, or internal reports.

## First Web Implementation Prompt

Use this prompt only after the backend activation gates are met:

```text
Read AGENTS.md, docs/clients/README.md, docs/clients/CLIENT_DELIVERY_MILESTONES.md, docs/clients/CLIENT_API_CONTRACT.md, docs/clients/CLIENT_DESIGN_SYSTEM.md, and docs/clients/WEB_CLIENT_DESIGN_SPEC.md. Implement Web Milestone W1 only. If internet is unavailable or Node dependencies cannot be installed, create the planned file structure, TypeScript interfaces, mocked API client, and a gap report. Do not add trade execution, live vendor calls, direct DB access, or Windows packaging.
```
