# Claude Code Implementation Directives

## Purpose

This file removes ambiguity for Claude Code. When implementation documents
conflict, this file wins unless `AGENTS.md` is stricter on safety.

Claude Code must implement the V1 architecture defined in this repository. It
must not preserve weak historical architecture for compatibility.

## Authority Order

Use this order when deciding what to build:

1. `AGENTS.md`
2. `docs/architecture/CLAUDE_CODE_IMPLEMENTATION_DIRECTIVES.md`
3. `docs/release/V1_FULL_PROJECT_RELEASE_SCOPE.md`
4. `docs/product/REAL_TIME_MARKET_INTELLIGENCE_BLUEPRINT.md`
5. `docs/release/V1_RELEASE_MILESTONE_BACKLOG.md`
6. selected milestone ExecPlan under `.agent/plans/`
7. contracts under `docs/contracts/`
8. older architecture notes and archived-reference summaries

Archived Desktop projects never outrank repository V1 docs.

## No Ambiguous Implementation Choices

Claude Code must not choose alternative frameworks, local stores, route shapes,
or data paths for convenience.

If the required stack, credentials, entitlement, package installation, or live
service access is unavailable, Claude Code must:

1. implement local interfaces, schemas, mocks, tests, and UI states allowed by
   the milestone;
2. write a gap report with the exact missing input;
3. mark the milestone `PARTIAL` or `BLOCKED`;
4. stop before substituting another architecture.

Do not replace:

- PostgreSQL with SQLite, DuckDB, local JSON, CSV, Parquet, or browser storage
  for runtime truth;
- FastAPI with another backend framework;
- SQLAlchemy/Alembic with ad hoc SQL files;
- React/Vite with Next.js, Remix, Angular, Vue, Svelte, or server-rendered
  templates;
- Tauri with Electron;
- MapLibre/deck.gl with Google Maps, Mapbox proprietary SDKs, Leaflet, or
  custom canvas map engines;
- i18next with live translation APIs;
- backend `/api/v1` with direct DB/client file access.

## Archived Projects Policy

Archived projects under `C:\Users\qqshu\Desktop` are evidence only.

Use them to learn:

- map-first workflow intent;
- route/corridor/facility inspection behavior;
- source and runtime status expectations;
- old dependency evidence;
- failed architecture patterns.

Do not copy or preserve:

- historical Rust backend architecture;
- local SQLite or file-first runtime truth;
- old source files;
- old UI layout as-is;
- old `.env`, credentials, raw/vendor/internal data, reports, or artifacts;
- old package decisions that conflict with this file.

When archived evidence conflicts with V1 docs, implement V1 docs.

## Documents Checkout Policy

`C:\Users\qqshu\Documents\Eurogasnexus` is the normal human-facing local
checkout once the current docs are synced or committed into it.

This Codex worktree remains the authoritative documentation source until that
sync happens:

```text
C:\Users\qqshu\.codex\worktrees\71e0\EurogasNexus
```

Do not start Claude Code in `C:\Users\qqshu\Documents\Eurogasnexus` until
`CLAUDE_CODE_START_HERE.md` and the release docs exist there.

## Required V1 Product Shape

V1 is a map-first European gas research platform with these required surfaces:

- PostgreSQL-backed backend/API;
- required Python SDK;
- CLI backed by SDK/API;
- Web client;
- Windows client shell packaging the Web workspace;
- release documentation and validation pack.

V1 must support, through API-backed and governed milestones:

- reference network map;
- route option display;
- capacity and gas/capacity contract context;
- source posture and ingestion governance;
- ECB FX;
- ENTSOG flow/capacity/outage context;
- GIE storage/LNG context;
- EEX market context;
- Trayport market context;
- ICE OCM market context;
- weather/HDD/CDD signals;
- route cost and indicative netback;
- strategy backtest and shadow run;
- LLM-assisted market movement and route explanation with citations;
- glossary in English and Mandarin Chinese;
- light, dark, and system theme modes.

## Runtime Data Path

The only runtime data path is:

```text
PostgreSQL -> backend repositories -> /api/v1 -> SDK/API clients -> UI/CLI
```

Client-specific rules:

- SDK calls `/api/v1`.
- CLI calls SDK first; direct `/api/v1` calls are allowed only for a documented
  SDK gap.
- Web calls `/api/v1` through its browser API client.
- Windows packages or launches the Web workspace and calls `/api/v1`.

No client opens PostgreSQL connections, imports backend DB/runtime-store
modules, reads backend local data files, stores vendor credentials, or calls
market/LLM providers directly.

## Fixed Client Stack

Use `docs/clients/CLIENT_TECH_STACK.md` exactly.

Approved Web stack:

- React;
- TypeScript;
- Vite;
- MapLibre GL;
- deck.gl;
- Zustand;
- i18next;
- react-i18next;
- lucide-react;
- date-fns;
- zod;
- plain CSS or CSS modules.

Approved Windows stack:

- Tauri 2;
- Rust;
- packaged Web workspace;
- non-sensitive local preference storage only.

Not approved in V1:

- Electron;
- Next.js;
- Remix;
- Angular;
- Vue;
- Svelte;
- Tailwind;
- Material UI;
- Ant Design;
- Bootstrap;
- Redux;
- local SQLite runtime/cache;
- GPL/LGPL/AGPL/SSPL/BUSL/Commons-Clause/PolyForm dependencies.

If a package install fails, do not substitute a framework. Report the exact
failure and stop at a gap report.

## Required Client UX

The first visual screen is the workspace. Do not build a marketing landing page.

The Web and Windows workspace must be:

- map-first;
- dense and professional;
- bilingual: `en-US` and `zh-CN`;
- themeable: light, dark, system;
- explicit about live/delayed/mocked/partial/unavailable data;
- explicit about source, lineage, freshness, quality, entitlement, assumptions,
  missing inputs, warnings, `research_only`, and `human_review_required`;
- optimized for route comparison and analyst review.

## Live Sources And LLM

Live connectors and LLM providers are V1 capabilities, but provider execution is
gated.

Default offline implementation:

- connector definitions;
- provider interfaces;
- schemas;
- mocked transports;
- synthetic fixtures;
- source posture UI;
- entitlement/credential gap reports.

Live execution requires a milestone that records:

- internet requirement;
- credentials;
- entitlement/license review;
- export policy;
- secret handling;
- operator validation command;
- no committed real data.

LLM output must use structured backend input snapshots and must include
citations/source references. LLM providers are not source of truth.

## Forbidden Product Behavior

Never implement:

- order entry;
- order routing;
- trade capture;
- trade execution;
- nomination submission;
- official approval;
- legal advice;
- official trading recommendation;
- auto-trading;
- ETRM replacement records;
- browser/desktop market-provider credentials;
- browser/desktop LLM-provider calls.

Use `research_candidate`, `candidate_ranking`, `research_signal`, and
`candidate_action_for_review`. Do not use `execute`, `place order`,
`submit nomination`, `approve trade`, or `official recommendation` in released
workflow UI/API.
