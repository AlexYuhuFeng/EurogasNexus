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

The currently implemented component is the backend Python service:

- API entrypoint: `apps/api/main.py`
- API package: `src/eurogas_nexus/api`
- DB foundation: `src/eurogas_nexus/db`
- SDK shell: `src/eurogas_nexus/sdk`
- CLI shell: `src/eurogas_nexus/cli`

Future client and deployment targets are represented by directory-level
instructions plus detailed docs under `docs/clients/`.

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
