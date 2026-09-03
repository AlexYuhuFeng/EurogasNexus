# V1 R15 Windows Desktop Client Package ExecPlan

**Milestone ID:** `R15`

**Status:** `complete`

**Completed:** 2026-09-01

## Goal

Package the shared React/Vite decision-support workspace as a Tauri 2 Windows
client with a configurable backend `/api` URL and no direct database, vendor, or
LLM-provider access.

## Delivered Architecture

- Tauri 2/Rust shell in `clients/desktop/src-tauri`.
- Shared Web production bundle built by `beforeBuildCommand`.
- Desktop API default `http://127.0.0.1:8000/api` with deployment-config support.
- English/Mandarin and light/dark/system behavior from the shared Web client.
- Windows x64 NSIS packaging; Linux package work is handled by release workflows.

## Completed Acceptance Checks

- [x] Web production build passes.
- [x] Tauri optimized release build passes.
- [x] Windows application executable is produced.
- [x] Windows x64 Client-only NSIS installer is produced.
- [x] Fresh release executable launches and remains interactive.
- [x] Workspace navigation opens Resource Terms.
- [x] Persisted PostgreSQL Resource Terms load through `/api` only.
- [x] Exact Pool Impact values render in the packaged desktop client.
- [x] Decision-support and no-direct-PostgreSQL boundaries remain visible.

## Non-goals

- No Electron or SQLite runtime.
- No direct PostgreSQL access from the client.
- No vendor credentials or LLM provider calls from the client.
- No claim of MSI, code signing, SSO/OIDC, or official V1 readiness.

## Evidence

- `docs/archive/reports/release_v1/r15_windows_release_shell_report.md`
- `clients/desktop/src-tauri/target/release/eurogas-nexus-desktop.exe`
- `clients/desktop/src-tauri/target/release/bundle/nsis/Eurogas Nexus_0.5.0_x64-setup.exe`

## Rollback

Revert the desktop package configuration and shared-Web change that caused a
regression, rebuild, and rerun executable interaction QA. Do not remove the
desktop directory or substitute another client architecture.
