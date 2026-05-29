# V1 R15 Windows Client Package Shell ExecPlan

**Goal:** Package the web workspace as a Windows desktop application using Tauri 2.

**Architecture:** Desktop client layer; wraps web workspace; configurable backend URL.

**Tech Stack:** Tauri 2, Rust, packaged web workspace (React/Vite build).

---

## Milestone ID

`R15`

## Status

`partial`

## Internet Requirement

Internet required: yes — Rust toolchain, Tauri CLI, and web workspace build
(npm install) must be available. Offline fallback: documented prerequisites and
project structure.

## Goal

Package the web workspace into a Windows desktop shell with Tauri 2. The desktop
app must: consume /api/v1 through the web workspace, allow configurable backend
base URL, store only non-sensitive UI preferences, preserve English/Mandarin
and light/dark/system modes, and never connect to PostgreSQL directly.

## Non-goals

- No Electron, SQLite, or copied historical Desktop code.
- No direct DB access, vendor credentials, or LLM provider calls.
- No company SSO/OIDC.

## Files Created (partial)

- `clients/desktop/README.md` — prerequisites and setup instructions

## Remaining

- Install Rust toolchain and Tauri CLI (`cargo install tauri-cli`)
- Build web workspace (`npm run build` in clients/web)
- `tauri init` in clients/desktop
- Configure backend base URL
- Build Windows .msi/.exe

## Rollback

Remove `clients/desktop/` directory. No backend impact.
