# V1 R14 Web Decision-Support Workspace ExecPlan

## Status

`partial` (updated 2026-09-01)

## Goal

Deliver the shared React/Vite workspace used by Web and Windows Tauri clients as
a professional European gas-trading decision-support product. All runtime data
must come through backend `/api` services backed by PostgreSQL.

## Architecture

- React 19, TypeScript, Vite, Zustand, i18next, MapLibre GL, plain CSS;
- grouped task navigation rather than a flat demo dashboard;
- no direct database, vendor credential, or LLM provider access in clients;
- no trade execution, order routing, nominations, settlement, or ETRM claims;
- verified infrastructure geometry when licensed evidence exists, otherwise
  explicitly labelled indicative route/asset representations.

## Delivered Evidence

- production Web build passes;
- full workspace shell and grouped navigation exist;
- Network, Scenario, Review, Resource Terms, Market, Capacity, Market
  Positioning, Strategy, Glossary, Data Sources, Runtime, Settings, and Manual
  are implemented;
- English/Chinese and light/dark/system modes exist;
- Web build is embedded by the Tauri Windows client;
- Resource Terms received task-led UI, validation-gated PostgreSQL persistence,
  exact cost/restriction semantics, and browser QA on 2026-09-01;
- current report: `data/release_v1/r14_web_release_workspace_report.md`.

## Remaining Work

1. Complete the page-by-page visual, responsive, bilingual, keyboard, and
   accessibility audit with durable browser-flow tests.
2. Reconcile every operational claim with backend data and explicit unavailable
   states; remove any remaining placeholder or invented fallback.
3. Finish Resource Terms obligations/versioning/currency-unit gaps and typed SDK
   support in separate bounded milestones.
4. Rebuild and inspect the Windows executable after each major shared-Web UI
   milestone.
5. Update the acceptance matrix and mark R14 complete only when the required
   evidence covers the whole workspace, not one page.

## Validation

```text
npm --prefix clients/web run build
python -m pytest tests/api tests/contract tests/integration tests/unit -q
python -m ruff check src tests
```

Risk-proportionate focused suites may be used during implementation, but final
R14 acceptance requires the broader release suite plus real browser and Windows
desktop evidence.

## Rollback

Revert only the bounded milestone commit. Do not remove `clients/web`, reset the
worktree, discard user changes, introduce SQLite runtime storage, or bypass the
backend API.
