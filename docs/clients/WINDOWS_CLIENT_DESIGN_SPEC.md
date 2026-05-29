# Windows Client Design Spec

## Objective

The Windows client packages the Eurogas Nexus workspace for desktop use. It
reuses the web workspace and accesses runtime data through the same backend
`/api/v1` API.

The packaged experience must preserve the map-first workflow: route options,
capacity/contract context, live source posture, market/weather signals,
strategy shadow runs, glossary, and LLM-assisted analysis are presented through
the web workspace, not through a separate desktop data layer.

## Product Boundary

The Windows client is not a second backend. It must not read PostgreSQL, backend
local files, raw vendor data, or connector credentials directly.

The desktop data path is:

```text
Windows shell -> packaged web workspace/API client -> backend /api/v1 -> backend repositories -> PostgreSQL
```

It must not implement trade execution, order entry, nomination submission,
official recommendation, auto-trading, company SSO/OIDC, or ETRM replacement
behavior.

It must not call ECB, ENTSOG, GIE, EEX, Trayport, ICE OCM, weather, or LLM
providers directly. All such access is mediated by backend `/api/v1`.

## Recommended Stack

Use Tauri 2 to package the web client when the Windows phase starts. Follow
`docs/clients/CLIENT_TECH_STACK.md` exactly.

Reason:

- keeps web and desktop workflows aligned;
- avoids duplicating business logic;
- allows a small native shell around an API-backed web workspace.

Internet required: yes if Tauri, Rust, Node, package documentation, or installer
tooling must be installed or verified.

Offline fallback: write directory structure, config templates, and gap report.

Do not use Electron. Do not use SQLite or `rusqlite` in V1 unless a later
offline-cache milestone explicitly approves it.

## Desktop App Frame

Startup flow:

```text
Launch
  -> load local UI preferences
  -> show connection screen if backend URL is missing
  -> call /api/v1/health
  -> show runtime status
  -> open workspace shell
```

Window layout:

- standard Windows app frame;
- persistent backend connection indicator;
- same workspace navigation as web;
- settings entry for backend URL and UI preferences;
- safe error screen for backend unavailable.

## Connection Screen

Fields:

- backend base URL;
- connection nickname;
- optional proxy setting only if a future milestone approves it.

Actions:

- test connection;
- save preference;
- continue in disconnected mock mode only if the selected milestone permits
  mock mode and labels it clearly.

Forbidden:

- DB URL;
- vendor API key;
- OAuth client secret;
- service token.

## Runtime Status

The Windows client must show:

- API health;
- backend profile;
- DB/runtime status when exposed by backend;
- live source posture for ECB, ENTSOG, GIE, EEX, Trayport, ICE OCM, weather,
  and LLM analysis when exposed by backend;
- version/build information;
- data/mocking warnings.

## Local Storage Policy

Allowed local storage:

- backend URL preference;
- window size;
- selected theme density;
- selected locale;
- selected light/dark/system theme mode;
- default map layers;
- non-sensitive UI preferences.

Forbidden local storage:

- PostgreSQL URLs;
- vendor credentials;
- API tokens;
- `.env` contents;
- raw vendor files;
- internal business data;
- generated commercial reports.

## Relationship To Historical Demo

The historical `eurogas nexus.exe` is a workflow reference only.

Detailed demo-derived UX notes:

- `docs/clients/WINDOWS_DEMO_UX_REFERENCE.md`

Preserve the intent:

- map-centric exploration;
- route/corridor/facility inspection;
- scenario composition;
- result review;
- runtime status.
- capacity/contract context linked to routes;
- strategy shadow-run review;
- glossary and analyst explanation surfaces.

Redesign completely:

- information hierarchy;
- navigation;
- forms;
- warnings;
- accessibility;
- result comparison;
- settings.

Do not copy old source, assets, data, layout, credentials, or file paths.

## Desktop-Specific States

Design for:

- first launch with no backend configured;
- backend unreachable;
- TLS or certificate error;
- backend healthy but DB degraded;
- local preference file unavailable;
- package build metadata missing;
- update/signing not configured;
- mock mode active.

## Packaging Policy

Release artifacts must exclude:

- `.env`;
- API keys;
- tokens;
- raw vendor data;
- internal commercial data;
- generated market reports;
- historical artifacts;
- local cache files.

## First Windows Implementation Prompt

Use this prompt only after the web workspace shell exists:

```text
Read AGENTS.md, docs/clients/README.md, docs/clients/CLIENT_DELIVERY_MILESTONES.md, docs/clients/CLIENT_API_CONTRACT.md, docs/clients/CLIENT_DESIGN_SYSTEM.md, and docs/clients/WINDOWS_CLIENT_DESIGN_SPEC.md. Implement Windows Milestone D1 only. Use Tauri only if dependencies are available or internet access is explicitly allowed. If unavailable, create config templates and a gap report. The Windows client must consume /api/v1, package the web workspace, and store only non-sensitive UI preferences.
```
