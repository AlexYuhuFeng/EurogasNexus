# Changelog

All notable changes to Eurogas Nexus are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
Application artifacts use package version `0.5.0`; the current public channel is
`preview` and is not a GA/stable release.
Release tags use `vX.Y.Z`, `vX.Y.Z-rc.N`, or
`vX.Y.Z-preview.N.<shortsha>`; legacy `v0.5-preview-<run>-<sha>` tags are
historical and are no longer generated.

## Ontology version changes

Ontology versions are tracked independently of application releases and are
asserted by `tests/contract/test_ontology_version_alignment.py`.

- **0.5.0** — the executable vocabulary under
  `src/eurogas_nexus/domain/ontology/` is the semantic source of truth. It
  models the full GRM role inventory, business processes, commodity taxonomy,
  typed interaction properties, and the human-review decision-support boundary.
  `scripts/ontology/generate_grm_ttl.py` renders the model as OWL/Turtle, and
  `tests/contract/test_ontology_grm_parity.py` verifies that the published
  `docs/ontology/eurogas-nexus-grm.ttl` remains in structural parity with the
  executable vocabulary.

## [Unreleased]

- The degraded-endpoint surface is now truthful and bounded: it renders
  translated endpoint labels and the safe machine code per failure (at most five
  detail rows plus a "showing N of M" line) instead of raw internal loader keys,
  the retry control reports its attempt count and last attempt time, disables
  itself and marks `aria-busy` while a retry is in flight, and the release-blocker
  list in the runtime workspace no longer prints loader keys.
- Accessibility defects found by an axe audit of the current surfaces are fixed:
  the market sparkline's empty state exposed an `aria-label` on an element
  without a role, and the simulated-source pill's accent-on-tint text measured
  about 4.16:1 against the 4.5:1 required for its 11px label. The sign-in screen
  (EN and zh-CN), the market numeric view and the 390px Mandarin System
  workspace now report zero axe violations.
- The desktop shell drops its WebView cookies, caches and local storage after a
  sign-out (`clear_client_session_data`), so a shared workstation keeps no
  session material behind once the backend session has been revoked.

- Research datasets: builds register a format-specific artifact (CSV always,
  Parquet when the optional adapter is installed) with a sha256 under a
  configurable artifact root, and export now matches the requested format
  against a stored artifact instead of answering 200 with a null reference; an
  unavailable format fails closed with `artifact_not_available` and the list of
  available formats. The declared `dataset.export` capability gained its missing
  handler, reusing the same server-derived entitlement policy.
- Research dataset validation and build share one registry resolver: unknown
  feature/target/source/entity/policy ids now fail at validation time with
  structured `{field, code, message}` issues, `entity_ids` actually filters the
  built rows, and the requested resampling policy is applied through the bounded
  resampler (recorded in snapshot metadata) instead of being silently ignored in
  favour of the first registry row.
- Shared task-tab strips no longer wrap their labels per glyph on narrow
  viewports: the rules now target the buttons the navigation primitive actually
  renders, so Mandarin labels stay on one line and the strip scrolls.

- Market views: the combined `overview` dashboard is no longer the mandatory
  landing task. The numeric analysis (`curves`) and the map/network inspection
  (`network`) are separate task views, and each authenticated user's preferred
  view is remembered per principal and shown again after sign-in, with gas day,
  product and hub context retained across the switch. `overview` remains
  available as an explicit opt-in task.
- Portfolio exposure no longer reports a false `GBP 0`: the summary totals are
  nullable, an empty or degraded read returns an explicit unknown with a
  `VALUATION_EVIDENCE_MISSING` warning, and a genuinely measured zero still
  reports zero.
- Fixed a cold-visit misclassification: a real `401` from `/api/me` was read as
  an unreachable backend, which showed an error banner and discarded the
  requested deep link. A plain anonymous visit now keeps its `?workspace=` link
  until sign-in succeeds, while an explicit sign-out or a session lost during
  use still scrubs the protected context from the entry URL.

- Authentication-first entry (UX-01 priority): an unauthenticated visit no
  longer reaches the terminal. `GET /api/me` answers 401 when no credential is
  presented (the verified static deployment token keeps its legacy SDK/CLI
  principal), the Web client resolves identity before any protected read, and a
  dedicated sign-in screen - company SSO plus a development-only credential form
  - stands in front of the workspace until authentication succeeds. Deep links,
  reload, session expiry, browser history, logout and desktop startup all honour
  the gate, and the development credential login exists only in the development
  route profile.
- Just-in-time SSO provisioning no longer grants access: a first login for an
  unknown approved-domain identity registers a `PENDING` principal and is
  rejected with `identity_pending_approval` until an administrator activates it.

- Client contract tests re-aligned with the current Web client (generic
  `loadWorkspaceEndpoint` store loaders, `workspaceTaskSearch` URL sync, current
  shell/topbar grid rows, plain glossary sticky offset, `ApiRequestOptions`
  client methods). The `contracts.edit_confirm` English confirmation was
  rephrased to satisfy the translation quality gate.

- Served-instance load smoke: `scripts/ops/load_smoke.py` accepts `--base-url`
  to send the smoke workload over real HTTP, and
  `scripts/ops/run_served_load_smoke.sh` starts a uvicorn process, waits for
  `/api/health/live`, and runs the smoke against it in CI alongside the
  in-process smoke.

- Agent-native capability layer (CR-15 / P14):
  - first-class Capability Registry with 68 versioned semantic capabilities
    (determinism, side effects, permissions, entitlement, provenance,
    timeout/retry metadata) and capability discovery API;
  - governed CapabilityRuntime with typed failure codes and
    AUTO/RESEARCH/HUMAN_CONFIRMATION/HUMAN_ONLY action policy;
  - registry-driven MCP adapter with legacy read/sandbox tool compatibility;
  - AgentRun, ToolInvocation, ResearchPlan, ResearchFinding, ResearchBudget,
    ChallengeReport, and ReviewPack persistence plus observable Agent Replay
    (no hidden chain-of-thought);
  - Strategy IR with semantic validation and compilation into the CR-03
    StrategyVersionDefinition;
  - governed ResearchOrchestrator, bounded research budget/final-holdout
    controls, Risk Challenger, and human review pack;
  - System > Agent Research UI; migration `0032_agent_capability_layer`;
    162 OpenAPI paths; 30-case deterministic agent evaluation suite.
- Research data foundation (CR-14 / P13):
  - executable `energy-ontology/v1`, canonical entities, and point-in-time
    source mappings;
  - observed_at/available_at/ingested_at temporal semantics, forecast
    vintages, and actual/forecast/assessment/simulated observation kinds;
  - versioned FeatureDefinition/TargetDefinition/ResamplingPolicy/DatasetSpec
    registries with bounded carry-forward (no unlimited ffill);
  - immutable dataset snapshots, point-in-time builder, leakage validation,
    time splits, quality reports, lineage, and entitlement-gated
    Parquet/CSV export;
  - migration `0031_research_data_foundation`, seeded research catalog,
    restrained System > Research Data UI, and MCP-free agent capability
    contracts;
  - 151 OpenAPI paths with legacy `/api/research/*` sandbox routes preserved.
- Commercial UAT convergence (CR-13):
  - PostgreSQL 16 browser Golden Workflows for Market → Scenario,
    Portfolio → Optimize → Review, and Strategy create/freeze/backtest;
  - P0 fixed: backtest attribution persistence now flushes decision events
    before attribution rows (PostgreSQL FK ordering);
  - P1 fixed: legacy Review deep link, human-readable warning labels, TSO
    access propagation, heading/landmark/contrast accessibility across all
    workspaces;
  - deterministic development-gated UAT fixture pack, AI eval corpus (13/13
    critical cases), axe-core 0 violations, EN/zh-CN 1,259-key parity;
  - user/UAT documentation and internal GA RC acceptance report.
- Supply-chain and release hardening (CR-12):
  - single canonical version contract enforced by
    `scripts/release/check_version_consistency.py`;
  - preview/RC/stable channel semantics with tag-only stable promotion;
  - machine-readable `release-manifest.json`, final `SHA256SUMS`, SPDX SBOMs,
    dependency vulnerability evidence, and GitHub OIDC attestations;
  - policy-aware Windows/Linux signing with explicit unsigned-pending state;
  - tag/version-derived artifact names; immutable container `sha-*` tags and
    multi-arch digest acceptance;
  - client/server compatibility contract (`/api/runtime/release`) and a
    blocking client compatibility screen;
  - managed/offline desktop update policy (no Tauri updater ships);
  - pinned runners, toolchains, and GitHub Actions in release/CI workflows.
- Standardized backend project structure:
  - consolidated research calculations under `src/eurogas_nexus/domain/research`;
  - removed empty source placeholder packages;
  - archived orphaned documentation;
  - updated directory ownership and testing documentation.
- Aligned release validation commands with the stable OpenAPI path count.

## [0.5.0] - Preview release line

The current preview line is package version `0.5.0`. It is a release candidate
for the tested local scope, not a production multi-user or GA deployment.

Highlights:

- PostgreSQL-first backend, API, Python SDK, CLI, Web client, and Tauri desktop shells.
- DB-composed portfolio network optimization and contract-level PnL attribution.
- Intraday opportunity monitoring with persisted alerts and DeepSeek enrichment.
- Storage/nomination assessment workflows (assessment only).
- Local identities, hashed API keys, role authorization, data scopes, and OIDC verification.
- Server and Client-only deployment roles.

See `docs/release/RELEASE_READINESS.md` for the current release status and
production gaps.
