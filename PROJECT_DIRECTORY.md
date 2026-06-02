# Project Directory

## Purpose

This file is the quick directory map for Eurogas Nexus. It reflects the intended
architecture for the current V1 phased multi-surface repository.

## Root Layout

```text
.agent/                 Agent ExecPlans and planning artifacts
.github/                CI and contribution governance
alembic/                Alembic migration boundary
apps/                   Process entrypoints
clients/                API-consuming Web and Windows clients when selected
data/                   Local artifacts, fixtures, reports, and milestone outputs
docs/                   Architecture, contracts, policies, operations, release docs
docs/clients/           Web and Windows client specs, stack, i18n, theme
docs/data/              Canonical data model blueprints
docs/design/            Text wireframes and UX layout blueprints
docs/product/           Research workflow and product semantics
infra/                  Deployment templates and operator notes
packages/               Future distributable packages
release/                Source-controlled release blueprint
scripts/                Local operations and validation scripts
src/eurogas_nexus/      Backend Python package
tests/                  API, contract, integration, security, SDK, CLI, release tests
```

## Product Surfaces

Eurogas Nexus is delivered through five surfaces, in this order:

1. Backend service
2. Python SDK
3. CLI
4. Web client
5. Windows client

The backend service is the active foundation. The Python SDK is required for
V1. SDK and CLI shells exist as API-backed helpers. Web and Windows client docs
are explicit implementation targets. Runtime client code is expanded only after
the relevant milestone is selected.

## Current Implementation Shape

The current V1 release-candidate worktree implements backend, SDK, CLI, Web,
and Windows shell surfaces for the tested local scope:

- API entrypoint: `apps/api/main.py`
- API package: `src/eurogas_nexus/api`
- DB foundation: `src/eurogas_nexus/db`
- route-cost domain: `src/eurogas_nexus/domain/route_cost`
- market-positioning domain: `src/eurogas_nexus/domain/market_positioning.py`
- market-positioning import domain:
  `src/eurogas_nexus/domain/market_positioning_import.py`
- glossary domain: `src/eurogas_nexus/domain/glossary.py`
- operational glossary context: `src/eurogas_nexus/domain/analysis.py` and
  `/api/v1/glossary/{term}/context`
- strategy-lab domain: `src/eurogas_nexus/domain/strategy_lab`
- SDK clients: `src/eurogas_nexus/sdk`
- CLI client: `src/eurogas_nexus/cli`
- Web workspace: `clients/web`
- Windows shell: `clients/desktop`

UK route-cost is active only for National Gas NTS in this release, but it must
not be artificially limited to Easington/Bacton examples. Any UK NTS entry/exit
point may be priced when audited tariff rows exist in PostgreSQL. Route cost,
LNG regas readiness, resource-pool optimization, strategy lab, FX, market
marks, credentials, and glossary surfaces are exposed through API/SDK/Web
contracts. Imported external screen-order observations and indicative portfolio
PnL snapshots are exposed through `/api/v1/portfolio/*` and
`src/eurogas_nexus/sdk/portfolio.py`. Clients must not read PostgreSQL directly.
Operational glossary context is also API-only and combines runtime matched
entities, capacity, selected-duration usage, prices, live marks, routes, and
linked contracts for terms such as Easington Entry Point, ICIS Heren, NBP, ICE
OCM, and customer-loaded points such as St Fergus Entry Point. It is no longer
limited to Easington/Bacton examples when PostgreSQL records exist.
Internal/operator market-positioning imports use
`/api/internal/portfolio/import-observations`; release clients continue to use
read-only `/api/v1/portfolio/*` endpoints.

## Development Direction

Claude Code should use:

- `CLAUDE_CODE_START_HERE.md` as the local CLI launch and full V1 prompt file;
- `docs/architecture/CLAUDE_CODE_IMPLEMENTATION_DIRECTIVES.md` as the
  no-ambiguity implementation authority;
- `docs/architecture/CLAUDE_CODE_GOAL_MODE.md` as the goal-mode entrypoint;
- `docs/architecture/NEXT_DEVELOPMENT_QUEUE.md` as the ordered queue;
- `docs/architecture/PRODUCT_DELIVERY_MASTER_PLAN.md` as the full
  backend/SDK/CLI/web/Windows delivery plan;
- `docs/architecture/WHOLE_PROJECT_CAPABILITY_BLUEPRINT.md` as the full
  capability map;
- `docs/architecture/CLAUDE_CODE_MASTER_EXECUTION_INDEX.md` as the phase
  execution map;
- `docs/architecture/REFERENCE_EVIDENCE_LOG.md` as the historical-reference
  evidence log;
- `docs/product/REAL_TIME_MARKET_INTELLIGENCE_BLUEPRINT.md` as the map-first
  live-source, capacity/contract, strategy, weather, glossary, and LLM
  requirement source;
- `docs/architecture/MARKET_PRACTICE_AUDIT-EN.md` and
  `docs/architecture/MARKET_PRACTICE_AUDIT-CN.md` as the latest
  market-practice audit for route cost, market marks, FX, physical signals,
  contract/capacity, strategy, and glossary;
- `docs/clients/MAP_FIRST_TRADER_COCKPIT_SPEC-EN.md` and
  `docs/clients/MAP_FIRST_TRADER_COCKPIT_SPEC-CN.md` as the no-ambiguity
  home-screen UX contract;
- `docs/clients/MARKET_POSITIONING_COCKPIT_SPEC-EN.md` and
  `docs/clients/MARKET_POSITIONING_COCKPIT_SPEC-CN.md` as the read-only
  imported order/PnL cockpit contract;
- `docs/clients/OPERATIONAL_GLOSSARY_CONTEXT_SPEC-EN.md` and
  `docs/clients/OPERATIONAL_GLOSSARY_CONTEXT_SPEC-CN.md` as the glossary
  context and metric-rendering contract;
- `docs/operations/MARKET_POSITIONING_IMPORTS-EN.md` and
  `docs/operations/MARKET_POSITIONING_IMPORTS-CN.md` as the internal
  entitlement/audit import runbook;
- `docs/clients/README.md` as the client design index;
- `docs/clients/CLIENT_TECH_STACK.md` as the fixed Web/Windows library
  authority;
- `docs/clients/CLIENT_I18N_THEME_SPEC.md` as the English/Mandarin and
  light/dark/system implementation authority;
- `docs/operations/WORKTREE_HANDOFF.md` to decide whether Claude should run in
  this Codex worktree or `C:\Users\qqshu\Documents\Eurogasnexus`;
- `docs/architecture/CLAUDE_CODE_START_PROMPTS.md` for copy-paste goal-mode
  prompts;
- `.agent/plans/` for milestone execution plans.

## Directory Rule

If a directory does not have an active milestone, keep it as documentation or
placeholder only. Do not add runtime behavior just because a folder exists.

## Directory Activation Rule

- Backend work activates `apps/api`, `src/eurogas_nexus`, `alembic`, `scripts`,
  `tests`, and backend docs.
- SDK work activates `src/eurogas_nexus/sdk`, `packages/python-sdk`, and
  `tests/sdk`.
- CLI work activates `src/eurogas_nexus/cli` and `tests/cli`.
- Web client work activates `clients/web` only after a web milestone is selected.
- Windows client work activates `clients/desktop` only after backend and web
  API contracts are stable enough for packaging.
