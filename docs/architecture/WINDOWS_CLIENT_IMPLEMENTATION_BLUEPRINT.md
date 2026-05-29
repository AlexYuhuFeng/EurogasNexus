# Windows Client Implementation Blueprint

## Objective

Build the Eurogas Nexus Windows client as a packaged desktop shell for the same
API-backed workspace used by the web client. The Windows client is not a
separate business runtime and is not a source of truth.

## Activation Condition

Start Windows client coding only after:

- backend `/api/v1` contracts are stable for the target workflow;
- the web client has a working workspace shell;
- the user explicitly asks to start the Windows phase.

## Recommended Stack

Use Tauri 2 to package the web client for Windows. Follow
`docs/clients/CLIENT_TECH_STACK.md`.

Reason:

- historical project already proved Tauri can package the concept;
- Tauri keeps the Windows client close to the web codebase;
- the desktop app can remain an API consumer instead of becoming a separate
  backend.

Internet required:

- yes if Tauri, Rust, Node, or package documentation/dependencies must be
  installed or verified.

Offline fallback:

- create Windows client plan, directory structure, config templates, mocked
  packaging docs, and gap report only.

## Directory

Use:

```text
clients/desktop/
  README.md
  src-tauri/
  docs/
  scripts/
```

Do not place Windows client code in historical Desktop folders. Do not copy old
Tauri source directly.

## Required Design Docs

Before coding, read:

- `docs/clients/CLIENT_DELIVERY_MILESTONES.md`
- `docs/clients/CLIENT_API_CONTRACT.md`
- `docs/clients/CLIENT_DESIGN_SYSTEM.md`
- `docs/clients/CLIENT_TECH_STACK.md`
- `docs/clients/CLIENT_I18N_THEME_SPEC.md`
- `docs/product/REAL_TIME_MARKET_INTELLIGENCE_BLUEPRINT.md`
- `docs/clients/WINDOWS_CLIENT_DESIGN_SPEC.md`
- `docs/design/UX_LAYOUT_BLUEPRINTS.md`

## Runtime Model

The Windows client:

- launches a packaged web workspace;
- connects to a configured backend base URL;
- stores only local UI preferences where allowed;
- never stores vendor credentials;
- never reads PostgreSQL directly;
- never reads backend data files directly;
- never calls vendor APIs directly.
- preserves web locale and light/dark/system theme behavior.

## UX Reference

The historical `eurogas nexus.exe` demo is a workflow reference only.

Use it to understand:

- map-centric navigation;
- scenario composition intent;
- route/corridor/facility inspection;
- research result review;
- operator/runtime status expectations.
- English/Mandarin language support;
- light/dark/system theme support.

Redesign:

- visual hierarchy;
- navigation;
- forms;
- result comparison;
- warnings;
- accessibility;
- settings/runtime status.

## Windows Client Features

First milestone:

- app launches;
- backend URL configurable;
- health/runtime status visible;
- web workspace shell loads;
- local storage limited to non-sensitive UI preferences;
- no bundled secrets;
- no local data source.

Later milestones:

- offline-safe UI preferences;
- installer;
- signed build process if certificates are available;
- update channel;
- enterprise deployment notes.

## Packaging Rules

Release artifacts must exclude:

- `.env`;
- API keys;
- tokens;
- raw vendor data;
- internal business data;
- generated market reports;
- historical artifacts.

## Validation

When tooling exists:

```powershell
npm run build
cargo test
cargo tauri build
```

If dependencies or certificates are unavailable, report `PARTIAL` with exact
missing inputs and keep the implementation in plan/config/mock form.

## Relationship To Backend And Web

Backend owns data and APIs.

Web owns shared UI.

Windows owns packaging and OS integration.

No business logic should exist only in the Windows client.
