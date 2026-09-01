# R14: Web Decision-Support Workspace Report

**Milestone ID:** R14 | **Status:** PARTIAL | **Updated:** 2026-09-01

## Current State

The React 19/Vite/TypeScript workspace is implemented and builds locally. It is
the shared UI embedded by the Windows Tauri client and consumes backend `/api`
routes only. PostgreSQL remains the runtime source of truth.

Active grouped workspaces:

- Decision Workspace: Network, Scenario, Review;
- Commercial Inputs: Resource Terms, Market, Capacity, Market Positioning;
- Analytics: Strategy, Glossary;
- Operations: Data Sources, Runtime, Settings, Manual.

The Network workspace includes verified-versus-indicative topology semantics,
source-labelled route corridors, persisted resources, and resource-pool route
evidence. Market is a terminal-style multi-hub/tenor/FX board. Strategy supports
task-led backtest/shadow monitoring. Capacity, Data Sources, Runtime, Glossary,
Review, Settings, and Manual are implemented rather than placeholders.

## Resource Terms Milestone (2026-09-01)

The former long-form contract page is now a task-led operational workspace:

- command strip with draft/persisted identity, source, PostgreSQL, review, and
  validation state;
- `Source`, `Terms`, `Pool impact`, and `Library` views;
- section navigation that mounts one clause group at a time;
- JSON/plain-text import only; unsupported PDF/DOCX claims were removed;
- validation-gated save and accessible live status feedback;
- editable resource type, entry/exit capacity, exits, and sale modes;
- exact persisted-resource impact rather than draft-derived claims;
- English and Chinese terminology aligned to Resource Terms.

Backend correctness delivered with the UI:

- variable cost, regas fee, and fuel/loss survive PostgreSQL/API readback and
  enter resource-pool economics;
- fuel/loss is a delivered-unit cost uplift;
- sale options expose `eligible_resource_ids`, preventing cross-contract route
  permission leakage;
- screen-sale cash lag remains resource-specific.

Design reference:

- `docs/design/references/resource-terms-workspace-imagegen-2026-09-01.png`
  (GPT Image 2; layout reference only, not runtime data evidence).

## Evidence

- `npm --prefix clients/web run build`: passed on 2026-09-01.
- Focused resource-pool/API tests: 23 passed on 2026-09-01.
- Ruff checks for changed Python modules/tests: passed after formatting fix.
- Browser QA: 1440x1000 desktop and 390x844 responsive captures, task-view
  interaction, validation blocker, pool impact, and persisted library.
- Windows package QA: the fresh Tauri release executable and x64 NSIS installer
  built successfully. The executable was launched and the Resource Terms,
  Library, persisted-record, and Pool Impact flows were exercised against the
  PostgreSQL-backed API.

## Why Status Is Still Partial

R14 is broader than one workspace. Remaining release work includes:

- repeatable browser-flow/accessibility automation rather than screenshot-only
  QA;
- completion of the full-page UI/UX audit across every workspace and both
  languages;
- minimum-take/take-or-pay, effective-window/version history, structured
  currency/unit/premium, and typed SDK Resource Terms support;
- final release-matrix reconciliation after the remaining page-by-page audit.

No internet or package-install blocker remains. The old 2026-05-29 report was
stale and has been replaced by this evidence-based status.

## Next

Continue the page-by-page Web/desktop release audit without marking R14 complete
until the remaining acceptance evidence exists. The Windows package/toolchain is
no longer a blocker.
