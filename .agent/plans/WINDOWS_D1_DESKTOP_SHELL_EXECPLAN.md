# Windows D1 Desktop Shell Implementation Plan

> **For agentic workers:** Optional helper skills may be used if available, but
> this plan is fully executable by plain Claude Code CLI. Follow the checkbox
> tasks in order and update them as evidence is produced.

**Goal:** Build the first Windows desktop shell that packages the Eurogas Nexus web workspace as an API-consuming client.

**Architecture:** The Windows client lives only under `clients/desktop`. It wraps the web workspace, stores only non-sensitive UI preferences, and consumes `/api/v1`.

**Tech Stack:** Use `docs/clients/CLIENT_TECH_STACK.md` exactly: Tauri 2,
Rust, Node only for packaging the Web workspace, packaged web assets, and local
config for non-sensitive UI preferences. Do not use Electron, SQLite, or a
separate desktop data layer.

---

## Activation Gate

Do not execute this plan until the user explicitly selects the Windows phase.

Required state before execution:

- Web M1 workspace shell exists or the selected milestone provides a packaged
  web asset source.
- Backend `/api/v1/health` is available.
- `docs/clients/WINDOWS_CLIENT_DESIGN_SPEC.md` has been read.
- The user approves Tauri/Rust/Node tooling for this phase.

## Internet Requirement

Internet required: yes if Tauri, Rust, Node, package documentation, installer
tooling, or signing guidance must be installed or verified.

Fallback if offline:

- create directory structure and config templates;
- write `data/windows_d1/windows_d1_gap_report.md`;
- do not claim package/build commands pass if dependencies are unavailable.

## Non-goals

- No second backend.
- No direct DB access.
- No vendor API calls from the desktop client.
- No bundled secrets or `.env`.
- No company SSO/OIDC.
- No trade execution, order entry, nomination, official recommendation, or
  auto-trading.
- No copied historical Desktop source.

## Files To Create Or Modify

- `clients/desktop/README.md`
- `clients/desktop/package.json`
- `clients/desktop/src-tauri/tauri.conf.json`
- `clients/desktop/src-tauri/Cargo.toml`
- `clients/desktop/src-tauri/src/main.rs`
- `clients/desktop/src/config/connection.ts`
- `clients/desktop/src/config/preferences.ts`
- `clients/desktop/docs/packaging.md`
- `clients/desktop/docs/security.md`
- `clients/desktop/scripts/smoke-test.ps1`
- `data/windows_d1/windows_d1_report.md`

## Task 1: Confirm Desktop Docs And Gates

- [ ] Read `AGENTS.md`.
- [ ] Read `docs/clients/README.md`.
- [ ] Read `docs/clients/CLIENT_DELIVERY_MILESTONES.md`.
- [ ] Read `docs/clients/CLIENT_API_CONTRACT.md`.
- [ ] Read `docs/clients/CLIENT_DESIGN_SYSTEM.md`.
- [ ] Read `docs/clients/CLIENT_TECH_STACK.md`.
- [ ] Read `docs/clients/CLIENT_I18N_THEME_SPEC.md`.
- [ ] Read `docs/product/REAL_TIME_MARKET_INTELLIGENCE_BLUEPRINT.md`.
- [ ] Read `docs/clients/WINDOWS_CLIENT_DESIGN_SPEC.md`.
- [ ] Read `docs/design/UX_LAYOUT_BLUEPRINTS.md`.
- [ ] Confirm the web workspace shell exists or report `BLOCKED`.

## Task 2: Scaffold Desktop Shell

- [ ] Create the listed `clients/desktop` files.
- [ ] Configure Tauri only if dependencies are available or internet access is
  explicitly allowed.
- [ ] If dependencies are unavailable, create config templates and gap report
  only.

## Task 3: Implement Connection Preference Model

- [ ] Store backend base URL, connection nickname, window size, theme density,
  selected locale, selected light/dark/system theme mode, and default map layers
  only.
- [ ] Reject DB URLs, tokens, API keys, and `.env` content.
- [ ] Add safe validation messages for forbidden secret-like inputs.

## Task 4: Implement Startup Flow

- [ ] Load local non-sensitive preferences.
- [ ] Show connection screen if backend URL is missing.
- [ ] Call `/api/v1/health` through the packaged web/API client path.
- [ ] Show backend unavailable, DB degraded, and mock-mode states safely.

## Task 5: Packaging And Security Docs

- [ ] Write `clients/desktop/docs/packaging.md` with build, artifact, signing,
  and installer notes.
- [ ] Write `clients/desktop/docs/security.md` with excluded files and secret
  handling rules.
- [ ] Write `clients/desktop/scripts/smoke-test.ps1` for local launch checks
  when tooling exists.

## Task 6: Validate

When dependencies are available:

```powershell
npm run build
cargo test
cargo tauri build
```

Always run backend import check:

```powershell
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

## Acceptance Criteria

- Desktop client files live only under `clients/desktop`.
- The desktop shell packages or points to the web workspace.
- Backend base URL is configurable.
- Only non-sensitive UI preferences are stored.
- English/Mandarin locale and light/dark/system theme behavior are preserved
  from the Web workspace.
- No direct DB, vendor API, or secret access exists.
- Historical Desktop code is not copied.
- Validation passes or a gap report states exactly what is blocked.

## Rollback Notes

Remove `clients/desktop` runtime files created by this plan and
`data/windows_d1` reports. Backend and web code are not affected.
