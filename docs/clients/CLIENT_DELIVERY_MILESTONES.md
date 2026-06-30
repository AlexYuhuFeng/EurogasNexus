# Client Delivery Milestones

## Current Status

Client delivery is active in this worktree. The repository already contains:

- SDK API client surface;
- CLI operator surface;
- React/Vite Web workspace;
- Tauri Windows/Linux desktop shell.

The remaining client milestones are improvement and hardening tracks, not
permission gates to begin client work.

Client implementation is separated by surface: SDK, CLI, Web, and Windows each
have distinct responsibilities, but all consume backend API contracts.

Historical and current client execution plans:

- `SDK_M1_API_CLIENT_EXECPLAN.md`
- `CLI_M1_OPERATOR_COMMANDS_EXECPLAN.md`
- `WEB_M1_WORKSPACE_SHELL_EXECPLAN.md`
- `WINDOWS_D1_DESKTOP_SHELL_EXECPLAN.md`
- `V1_R22_DOCS_CLIENT_COCKPIT_ALIGNMENT_EXECPLAN.md`

## Standing Client Rules

- All clients use backend `/api` or SDK boundaries.
- No client reads PostgreSQL directly.
- No client stores provider credentials, service tokens, DB URLs, or raw vendor
  data.
- Missing data is displayed as unavailable, partial, blocked, stale, or
  credential-missing.
- Client code must not create browser-side runtime fixture data for routes,
  capacity, tariffs, market prices, contracts, orders, or PnL.
- UI language remains decision-support and human-review oriented.

## Completed Milestones

### W0: Client Design Package

Status: `complete-in-current-worktree`

Delivered:

- client API contract;
- tech-stack contract;
- Web and Windows design specs;
- cockpit and resource-pool specs;
- i18n/theme specs.

### W1: Web Workspace Shell

Status: `complete-in-current-worktree`

Delivered:

- React + TypeScript + Vite workspace;
- top bar and workspace menu;
- Network, Capacity, Market, Scenario, Contracts, Strategy, Review, Order
  Records, Data Sources, Glossary, Runtime, Settings, and Manual pages;
- backend `/api` client and Zustand state store;
- explicit unavailable/partial/runtime states.

### D1: Windows Desktop Shell

Status: `complete-in-current-worktree`

Delivered:

- Tauri shell wrapping the Web workspace;
- desktop package configuration;
- no direct DB access and no bundled provider credentials.

## Active Improvement Milestones

### W7: Client Structure And Cockpit Evidence

Status: `in-progress`

Goal:

Reduce top-level Web app complexity and improve trader review evidence without
changing the backend API surface.

Build:

- extract focused cockpit/source/topbar components;
- expose compact warning and source-evidence stack on Network;
- show map-level resource paths from active portfolio resources to recommended
  sale targets using backend resource-pool options and optimization outputs;
- preserve Data Sources, Runtime, and Review as deeper investigation surfaces.

Delivered latest slice:

- added `ResourcePoolPathOverlay` on the Network map;
- derives source delivery point, target point, quantity, route cost, sale price,
  net margin, capacity limit, route state, and blockers from backend-loaded
  resource-pool state;
- wires the existing map highlighted-route animation to the first matchable
  resource path when source/target nodes can be resolved;
- limits fallback map labels to trader-priority objects: active resource-path
  endpoints, hubs, search matches, and named market points.

Validation:

```powershell
npm --prefix clients/web run build
pytest -q tests/contract/test_web_client_structure.py
```

### W8: Persisted Contract Workflow

Status: `in-progress`

Goal:

Move contract capture from draft UI state toward persisted backend/API
workflows while preserving the no-ETRM boundary.

Requires:

- broader validation model for missing inputs and assumptions;
- contract-level attribution drill-down.

Delivered first slice:

- Web contract form builds an upstream resource payload;
- `POST /api/route-cost/upstream-contracts` persists the resource terms through
  the backend;
- Web reloads upstream contracts and resource-pool options after save;
- Web shows a persisted contract library from
  `GET /api/route-cost/upstream-contracts`;
- saved contracts can be loaded back into the EFET-style form for an explicit
  edit/upsert;
- JSON contract drafts can be imported into the form, but only backend save
  makes them resource-pool inputs;
- no client-side DB access, trade capture, or execution semantics.

### W9: Market Intelligence Terminal

Status: `in-progress`

Goal:

Move the Market page from a plain observation table toward a gas-trader market
terminal for major European hubs and licensed price-source posture.

Delivered first slice:

- extracted `MarketTerminal` as the Market page owner;
- renders TTF, NBP, THE, PEG, ZTP, and PSV rows without fabricating missing
  prices;
- shows regional comparison against TTF where sourced rows share currency/unit;
- adds compact sparklines from actual observed price rows only;
- shows EEX, ICE OCM, Trayport, Platts, ICIS, Argus, and Kpler source posture
  from backend `/api/sources`;
- keeps ECB FX references separated from gas price marks.

Requires:

- live commercial connector validation after credentials and entitlement are
  approved;
- richer hub/product normalization once provider-specific schemas are loaded;
- browser and desktop QA against real licensed price feeds.

### W10: Trader Settings Center

Status: `in-progress`

Goal:

Move Settings from language/theme only to a trader preference center for
display units, currency, session defaults, source-service posture, and
decision-support guardrails.

Delivered first slice:

- extracted `SettingsCenter` as the Settings page owner;
- stores non-sensitive default currency, energy unit, volume unit, price basis,
  timezone, map-density, and refresh-profile preferences in local browser
  storage;
- shows backend source/API credential posture without returning plaintext keys;
- links API-key management back to Data Sources, where credential entry remains
  backend-owned;
- repeats no-client-DB-url, no-client-secret-storage, human-review, and
  decision-support-only guardrails.

Requires:

- applying display preferences consistently across all Market, Contract,
  Scenario, PnL, and map labels;
- operator validation for which defaults should be desk-wide versus local-only.

### W11: Glossary Operational Wiki

Status: `in-progress`

Goal:

Move Glossary from a compact term list to an operational wiki surface for gas
trading language, institutions, venues, entities, business models, contract
terms, infrastructure, market marks, and source/data-quality context.

Delivered first slice:

- extracted `GlossaryWiki` as the Glossary page owner;
- adds category navigation, term search, active term selection, aliases,
  related-term chips, source references, and localized definitions from
  backend-served glossary records;
- renders `/api/glossary/{term}/context` output as operational context with
  metrics, matched entities, grouped sections, related sources, data quality,
  and warnings;
- keeps glossary content backend/API-owned and read-only in the Web client.

Requires:

- richer backend glossary records for business models, named institutions,
  TSOs, exchanges, brokers, LNG/storage entities, and operator-specific assets;
- desktop QA after rebuilding the Tauri package.

### W12: Review, Entitlement, And Export UX

Status: `pending`

Goal:

Make warnings, restricted data, assumptions, source references, lineage, and
human-review status easier for traders to inspect before acting outside the
system.

### D2: Desktop Packaging And Operations

Status: `pending`

Goal:

Harden desktop release notes, artifact exclusion, enterprise deployment notes,
and smoke-test process. No auto-update, SSO/OIDC, local database, or credential
store unless separately approved.

## Deferred Client Work

- Browser-side provider connectors.
- Direct vendor/LLM calls from Web or Windows.
- Order entry, order amendment, order cancellation, trade capture, nomination,
  official approval, settlement, or auto-trading.
- Client-side DB configuration beyond backend base URL and non-sensitive UI
  preferences.
