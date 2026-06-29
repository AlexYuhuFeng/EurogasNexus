# Web Client Implementation Blueprint

## Objective

Build the Eurogas Nexus web client as the primary research workspace after the
backend exposes stable `/api` contracts. The web client is a browser UI, not
a source of truth.

## Activation Condition

Start web client coding only when the user explicitly asks to start the web
phase or Codex selects a web milestone from a future queue.

Required backend readiness before coding:

- `/api/health` works;
- backend runtime status API exists or is planned in the selected milestone;
- reference-network API contract exists;
- research output envelope is documented;
- SDK/API client path policy is stable.

## Recommended Stack

Use `docs/clients/CLIENT_TECH_STACK.md` as the authoritative library list:

- React 19;
- TypeScript;
- Vite;
- MapLibre GL;
- deck.gl;
- Zustand;
- TanStack Query;
- i18next/react-i18next;
- lucide-react;
- plain CSS/CSS modules;
- HTTP client that targets `/api`.

Internet required:

- yes if dependencies must be installed or current package docs must be
  verified.

Offline fallback:

- create file structure, UI contracts, typed API clients, and implementation
  plan only.

## Directory

Use:

```text
clients/web/
  README.md
  package.json
  index.html
  src/
    app/
    api/
    components/
    features/
    map/
    styles/
    test/
```

Do not put web code under `apps/api` or `src/eurogas_nexus`.

## Required Design Docs

Before coding, read:

- `docs/clients/CLIENT_DELIVERY_MILESTONES.md`
- `docs/clients/CLIENT_API_CONTRACT.md`
- `docs/clients/CLIENT_DESIGN_SYSTEM.md`
- `docs/clients/CLIENT_TECH_STACK.md`
- `docs/clients/CLIENT_I18N_THEME_SPEC.md`
- `docs/product/REAL_TIME_MARKET_INTELLIGENCE_BLUEPRINT.md`
- `docs/clients/WEB_CLIENT_DESIGN_SPEC.md`
- `docs/design/UX_LAYOUT_BLUEPRINTS.md`

## User Experience Target

The web client should implement a map-centric research workspace.

Primary screens:

1. Network Map
2. Capacity And Contracts
3. Market Context
4. Scenario Workspace
5. Strategy Shadow Run
6. Research Output Review
7. Glossary
8. Settings and Runtime Status

Required global UI:

- English/Mandarin language switch;
- light/dark/system theme switch;
- visible live/delayed/demo/partial/unavailable source states.

## Network Map

Purpose:

- show hubs, facilities, routes, corridors, zones, and selected assets.

Data:

- consume `/api/reference-network/*`;
- display source/freshness/warning state;
- do not load raw vendor data directly.

## Scenario Workspace

Purpose:

- capture research scenario inputs and show missing inputs before calculation.

Inputs:

- resource/source;
- destination or market intent;
- route preference;
- volume;
- price assumptions;
- cost assumptions;
- timing;
- notes.

Rules:

- no trade execution language;
- no order entry;
- no official recommendation language.

## Market Context

Purpose:

- show market, tariff, flow, storage, LNG, weather, and freshness context after
  backend APIs exist.

Initial milestone:

- mock or backend metadata only until market-data APIs are approved.

## Research Output Review

Purpose:

- display candidate results, warnings, assumptions, missing inputs, source
  references, lineage, and human-review-required state.

Required UI states:

- loading;
- empty;
- missing input;
- stale data;
- restricted data;
- degraded backend;
- research-only output.

## Settings And Runtime Status

Show:

- backend base URL;
- API health;
- DB/runtime status;
- active profile;
- data freshness warnings.

## Design Direction

Use the historical Windows demo only for workflow understanding. Redesign the UI
for clarity:

- dense but readable operational layout;
- map as primary surface;
- right-side detail rail;
- bottom comparison/results area;
- clear warning and missing-input panels;
- minimal decorative styling.

## API Client Rules

- all backend calls target `/api`;
- no direct DB access;
- no local backend file reads;
- no vendor API calls from the browser;
- no browser-side secrets.

## Web Validation

When web tooling is added, expected validation should include:

```powershell
npm run lint
npm run test
npm run build
```

If npm/Node dependencies are not installed and internet is unavailable, report
`PARTIAL` and validate only static docs/contracts.

## First Web Milestone

Recommended first web milestone:

- create the React/Vite shell;
- implement runtime status page;
- implement `/api/health` client;
- render a DB/API-driven network map layout with explicit unavailable states
  when reference-network data is missing;
- implement required loading, empty, degraded, missing-input, and research-only
  states from the design spec;
- no business calculations.
