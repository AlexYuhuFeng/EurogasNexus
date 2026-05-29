# Client Delivery Milestones

## Decision

Client implementation is separated by surface after backend API contracts are
ready. Client design documentation may exist now. Runtime client code starts
only when the user selects a client milestone.

## Activation Gates

Before Web Milestone W1:

- `/api/v1/health` exists;
- API path policy is stable;
- backend runtime status API is implemented or explicitly mocked for W1;
- reference-network API contract exists or is mocked with a documented gap;
- research output envelope is documented;
- user explicitly asks to start web client work.

Before live-source, LLM, capacity/contract, or strategy client screens are
marked complete:

- matching `/api/v1` contracts exist or are explicitly mocked with a gap report;
- source entitlement and credential requirements are documented;
- no browser or desktop client stores vendor/LLM credentials;
- backend distinguishes live, delayed, mocked, partial, and unavailable states.

Before SDK Milestone S1:

- `/api/v1/health` exists;
- API response/error model is documented;
- SDK/CLI boundary contract exists;
- user explicitly asks to expand SDK beyond the health shell.

Before CLI Milestone C1:

- SDK M1 exists or the current SDK health helper is sufficient for the selected
  CLI work;
- CLI command safety policy is documented;
- user explicitly asks to expand CLI commands.

Before Windows Milestone D1:

- web workspace shell exists;
- backend URL configuration behavior is stable;
- Windows packaging stack is approved;
- user explicitly asks to start Windows client work.

## Milestone W0: Client Design Package

Status: documentation-only

Deliver:

- client API contract;
- design system;
- web design spec;
- Windows design spec;
- delivery milestones;
- implementation blueprints.

No runtime code.

## Milestone W1: Web Workspace Shell

ExecPlan:

- `.agent/plans/WEB_M1_WORKSPACE_SHELL_EXECPLAN.md`

Internet required: yes if React, TypeScript, Vite, or package documentation must
be installed or verified.

Offline fallback:

- create planned file structure;
- write API client interfaces;
- write mocked response fixtures;
- write gap report for missing dependencies.

Build:

- React + TypeScript + Vite shell in `clients/web`;
- app frame with left navigation, top status bar, main workspace, right
  inspector, bottom results panel;
- `/api/v1/health` client;
- runtime status view using real API if present, otherwise documented mock;
- map-first placeholders for Network, Capacity, Market, Scenario, Strategy,
  Review, Sources, Glossary, Runtime, and Settings;
- no live vendor calls from the browser.

Validation:

```powershell
npm run lint
npm run test
npm run build
```

If Node dependencies are unavailable offline, report `PARTIAL` and run only
available static checks.

## Milestone S1: Python SDK API Client

ExecPlan:

- `.agent/plans/SDK_M1_API_CLIENT_EXECPLAN.md`

Internet required: no

Build:

- typed API client shell;
- `/api/v1` path normalization;
- health and runtime status client methods where backend routes exist;
- safe exception model;
- metadata preservation;
- boundary tests proving the SDK does not import backend internals.

Do not build:

- package publishing;
- direct DB access;
- vendor API calls;
- execution/order/trade/nomination methods.

## Milestone C1: CLI Operator Commands

ExecPlan:

- `.agent/plans/CLI_M1_OPERATOR_COMMANDS_EXECPLAN.md`

Internet required: no

Build:

- health command/helper;
- runtime status or DB validation helper;
- human and JSON output helpers;
- secret redaction;
- read-only-by-default command posture.

Do not build:

- mutating commands without explicit `--execute`;
- command groups that imply trade execution or nomination submission;
- live connector execution.

## Milestone W2: Reference Network Explorer

Build:

- map-centric network view;
- reference-network API client;
- synthetic fixture fallback only for development mode;
- layer controls for hubs, facilities, corridors, LNG, storage, and beach
  delivery points;
- source, freshness, warning, and lineage display.

Do not build:

- live connector calls from browser;
- route optimization;
- trade or nomination workflows.

## Milestone W3: Scenario Workspace Shell

Build:

- scenario input form;
- missing-input validation;
- assumptions panel;
- no calculation beyond backend-provided mocked or approved responses;
- research-only language.

## Milestone W4: Research Output Review

Build:

- candidate comparison table;
- warning stack;
- source references;
- lineage panel;
- `research_only` and `human_review_required` display;
- export disabled until governance/export policy is implemented.

## Milestone W5: Live Market Intelligence Panels

Build:

- live-source posture panels for ECB, ENTSOG, GIE, EEX, Trayport, ICE OCM, and
  weather;
- map overlays for price/spread/FX, flow/capacity/outage, storage/LNG, and
  HDD/CDD signals when backend routes exist;
- clear `LIVE`, `DELAYED`, `MOCKED`, `PARTIAL`, and `UNAVAILABLE` states.

Do not build:

- browser-side connector calls;
- browser-side vendor credentials;
- official recommendation or execution language.

## Milestone W6: Capacity, Contract, Strategy, LLM, And Glossary

Build:

- capacity/contract management views backed by `/api/v1`;
- route option review with cost, contract, and capacity constraints;
- strategy shadow-run review;
- glossary drawer;
- LLM-assisted analysis panel with citations/source references.

Do not build:

- trade capture;
- order entry;
- nomination submission;
- uncited LLM market claims;
- direct LLM provider calls from client code.

## Milestone D1: Windows Desktop Shell

ExecPlan:

- `.agent/plans/WINDOWS_D1_DESKTOP_SHELL_EXECPLAN.md`

Internet required: yes if Tauri, Rust, Node, or package documentation must be
installed or verified.

Offline fallback:

- create desktop plan, config templates, and gap report only.

Build:

- Tauri package shell in `clients/desktop`;
- backend URL configuration;
- health/runtime status screen;
- packaged web workspace;
- no bundled secrets or local data source.

## Milestone D2: Windows Packaging And Release Notes

Build:

- installer notes;
- signing requirements;
- artifact exclusion checklist;
- enterprise deployment notes;
- smoke test checklist.

No auto-update or enterprise SSO unless separately approved.
