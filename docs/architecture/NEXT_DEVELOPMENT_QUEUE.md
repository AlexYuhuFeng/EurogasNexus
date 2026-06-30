# Next Development Queue

## Purpose

This file is the current ordered queue for Eurogas Nexus work. It reflects the
active V1 release-candidate state: backend/API/SDK/CLI/Web/Windows exist and
the next work should improve the live trader-intelligence product rather than
replay early foundation milestones.

## Current Queue Rule

Execute the first item below whose status is not `complete-in-current-worktree`.
Do not skip product-boundary, data-policy, entitlement, or documentation work
to add visible UI features.

## Current Baseline

Status: `complete-in-current-worktree`

The worktree contains:

- FastAPI backend with stable `/api` routes.
- PostgreSQL runtime store and Alembic migrations through
  `0012_entsog_capacity`.
- Python SDK and CLI.
- React/Vite Web workspace.
- Tauri desktop shell around the Web workspace.
- Runtime data posture for reference network, capacity/flow, storage, LNG,
  FX, source posture, route-cost/resource-pool, strategy, glossary, portfolio
  observation, credentials, audit, and entitlement foundations.

## V1 R22: Documentation And Client Cockpit Alignment

Status: `in-progress`

ExecPlan:

- `.agent/plans/V1_R22_DOCS_CLIENT_COCKPIT_ALIGNMENT_EXECPLAN.md`

Goal:

Make documentation and Web structure match the active product:

- update architecture, client, and release docs so they describe Web and
  Windows as active runtime clients;
- repair corrupted Mandarin docs;
- align release evidence with current Alembic and route counts;
- keep the home cockpit map-first and resource-pool-native;
- extract focused Web components where the top-level app file is doing too
  much.

Acceptance:

- docs contract tests pass;
- selected Mandarin docs are readable UTF-8 Chinese;
- Web build passes;
- browser smoke test shows Network and Data Sources without console errors.

Latest delivered slice:

- executable walkthrough confirmed the active Web/Windows page model;
- Market now uses a dedicated terminal component for major European gas hubs,
  regional TTF spreads, observed-row sparklines, ECB FX, and price-source
  posture without fabricating missing licensed prices.
- Contracts now shows an API-backed upstream resource-contract library, can
  load saved rows for edit/upsert, imports operator-owned JSON drafts into the
  EFET-style form, and keeps backend save as the authority for resource-pool
  inputs.
- Settings now uses a dedicated trader preference center for local unit,
  currency, price-basis, timezone, map-density, refresh-profile, service-access
  posture, and backend-boundary guardrails without storing secrets client-side.
- Network now renders a backend-derived resource-path overlay on the map,
  connecting persisted resource delivery points to candidate sale targets with
  quantity, capacity, route cost, sale price, margin, route state, and blockers.
- Network fallback map labels are now budgeted to trader-priority objects:
  active route endpoints, hubs, search matches, and named market points, so the
  backup map remains readable when hundreds of assets are visible.
- Glossary now uses a dedicated wiki surface with category navigation,
  backend-served term definitions, aliases, related terms, source references,
  and operational context from `/api/glossary/{term}/context`.

## R23: Ingestion Scheduling And Source Health

Status: `pending`

Goal:

Productionize live ingestion operation without changing the client data
boundary.

Build:

- scheduler/retry design for operator-controlled ingestion;
- source freshness and failure diagnostics;
- per-source run history and last-success/last-failure visibility;
- no import-time network calls;
- no browser-side provider calls.

Acceptance:

- public/keyed ingestion remains explicit and auditable;
- failures surface in Source Center;
- credentials remain backend-owned and write-only from clients.

## R24: Entitlement, Audit, And Export Governance Hardening

Status: `pending`

Goal:

Make entitlement and export restrictions enforceable for commercial data,
portfolio observations, analysis outputs, and reports.

Build:

- fail-closed entitlement checks for unknown commercial datasets;
- audit event coverage for operator imports and analysis/report generation;
- export-disabled or restricted states in Review;
- tests proving restricted data cannot be silently exposed.

Acceptance:

- unknown entitlement fails closed;
- analysis/report outputs carry warnings, lineage, source references,
  `research_only`, and `human_review_required`;
- clients display restricted state without legal-advice language.

## R25: Persisted Contract And Resource Pool Workflow

Status: `in-progress`

Goal:

Move EFET-style contract capture from a UI draft shell toward persisted
backend/API workflows while preserving the no-ETRM boundary.

Build:

- broaden backend contract/resource validation beyond the first save path;
- explicit missing-input and assumptions model;
- resource-pool persistence or import path beyond upstream resource terms;
- contract-level PnL attribution drill-down;
- UI workflow that stores through `/api`, never direct DB access.

First slice delivered:

- `POST /api/route-cost/upstream-contracts` persists EFET-style upstream
  resource terms into `upstream_resource_contracts`;
- Web Contracts page can save the draft through `/api` and refresh
  `upstreamContracts` plus `resourcePoolOptions`.

Acceptance:

- no order entry or trade capture semantics;
- contracts feed the resource pool;
- home cockpit consumes persisted resources and sale options only.

## R26: Cockpit Review And Warning Evidence

Status: `pending`

Goal:

Improve trader review ergonomics: warning stack, blockers, source evidence,
lineage, and route allocation drill-downs.

Build:

- compact evidence stack on Network;
- full warning/assumption/source review on Review;
- route blocker explanations with source/freshness;
- browser QA across desktop and mobile.

Acceptance:

- warnings are visible before workflow execution;
- route allocation and resource-pool recommendations remain human-review
  decision support;
- no execution language.

## R27: Market Terminal Live Feed Hardening

Status: `pending`

Goal:

Move the Market terminal from source-aware display into a live-market operations
surface after commercial feed credentials and entitlement are approved.

Build:

- provider-specific hub/product normalization for EEX, ICE OCM, Trayport,
  Platts, ICIS, Argus, and Kpler;
- backend spread calculations for TTF-relative and cross-region comparisons;
- stale-data blocking and entitlement warnings in the Market terminal;
- browser and desktop QA against real licensed feed rows.

Acceptance:

- no client-side provider calls or fabricated prices;
- live or delayed state is sourced from backend diagnostics;
- Market remains separated from order entry, order routing, and PnL records.

## Deferred Production Work

These areas remain deferred until explicitly selected:

- company SSO/OIDC;
- enterprise signing and deployment hardening;
- broker/exchange live commercial connector validation;
- LLM provider execution beyond gated backend operator control;
- export/report governance beyond current restricted states.
