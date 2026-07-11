# V1 R25 Trader Correctness, UX, and Decomposition ExecPlan

## 1. Goal

Make the current release candidate materially safer and faster for a gas trader
to interpret while continuing the frontend architecture cleanup. This round
must correct strategy price and FX normalization, remove misleading source and
network states, reduce map obstruction, finish the shared workspace-navigation
migration, keep English and Mandarin UI labels complete, package a local
Windows executable, and publish only after real PostgreSQL-backed interaction
tests pass.

## 2. Non-Goals

- Do not add order entry, trade execution, order routing, trade capture,
  nomination submission, auto-trading, settlement, approval, or ETRM behavior.
- Do not connect any client directly to PostgreSQL.
- Do not call licensed providers or LLMs during tests.
- Do not fabricate missing physical pipeline geometry or tariff coverage.
- Do not introduce a new UI framework, state library, or heavy dependency.

## 3. Product Boundary

Eurogas Nexus remains a PostgreSQL-backed, API-first decision-support product.
Strategy evaluation is a paper/shadow-run workflow requiring human review.
Simulated price feeds are permitted only when they are explicit runtime records
with source and data-quality labels. Public infrastructure, tariff, and FX data
must not be presented as complete when the persisted coverage is partial.

## 4. Files To Create Or Modify

- `.agent/plans/V1_R25_TRADER_CORRECTNESS_UX_DECOMPOSITION_EXECPLAN.md`
- `clients/web/src/App.tsx`
- `clients/web/src/app/index.ts`
- `clients/web/src/app/marketPriceNormalization.ts`
- `clients/web/src/app/strategyScenario.ts`
- `clients/web/src/app/workspaceDerivedData.ts`
- `clients/web/src/components/GasNetworkMap.tsx`
- `clients/web/src/components/ResourcePoolPathOverlay.tsx`
- `clients/web/src/components/SettingsCenter.tsx`
- `clients/web/src/components/StrategyShadowRunTerminal.tsx`
- `clients/web/src/components/WorkspaceTopBar.tsx`
- `clients/web/src/i18n/en.json`
- `clients/web/src/i18n/zh.json`
- `clients/web/src/styles/app.css`
- `src/eurogas_nexus/api/routes/public/market.py`
- Focused API and contract tests.
- Temporary completed cleanup patch notes and their transitional test may be
  removed after the navigation migration is implemented.

## 5. Dependency Policy

No new dependency is allowed. Use the existing React, TypeScript, Vite,
MapLibre, FastAPI, SQLAlchemy, pytest, and Ruff stack.

## 6. Data Policy

- PostgreSQL remains the runtime source of truth.
- Convert market observations to GBP/MWh using persisted FX rows before a
  GBP-denominated strategy calculation.
- Preserve native source currency and provenance in source data; conversion is
  a client decision-support view, not a database rewrite.
- Do not turn unavailable values into zero.
- Do not commit credentials, live vendor data, or browser artifacts.

## 7. API Impact

No API path change is planned. The market-observation endpoint may return the
same schema in newest-first order so clients do not mistake alphabetical row
order for recency.

## 8. DB Impact

No migration and no destructive DB write is planned. Existing PostgreSQL test
data is read through the API. Runtime validation remains read-only.

## 9. Tests

Add or update focused checks for:

- newest-first market observations;
- shared workspace navigation with no App-owned legacy menu;
- explicit currency normalization and no zero-price strategy fallback;
- complete English and Mandarin translation keys for visible client labels;
- public credential providers display `Not required`, not `Missing`;
- resource-path details start collapsed and remain keyboard accessible;
- partial route-corridor geometry is not labelled as a complete network.

## 10. Validation Commands

```powershell
ruff check .
pytest -q tests/api tests/contract
npm --prefix clients/web run build
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
python scripts/ops/validate_v1_runtime_db.py --json
npm --prefix clients/desktop run build -- --bundles nsis
```

Run the web client against the existing local PostgreSQL runtime and verify the
Network, Data Sources, Strategy, and Settings flows at 2560x1440. Launch the
packaged Windows executable and confirm it remains running and interactive.

## 11. Acceptance Criteria

- Strategy paper evaluation consumes positive, currency-normalized persisted
  observations and no longer returns zero averages while the UI shows live
  positive prices.
- Market tape excludes FX rows and labels converted values as GBP/MWh.
- Public credential providers are shown as not requiring credentials.
- No raw i18n key or corrupted Mandarin placeholder is visible in the audited
  flows.
- The central map is no longer covered by an expanded route evidence panel by
  default; details remain one action away.
- The map distinguishes complete geometry from route-corridor-only coverage.
- App no longer owns or renders the legacy duplicate workspace menu and uses
  shared navigation guards.
- Targeted tests, web build, lint, API import, live DB validation, Windows
  packaging, and real UI interaction all pass.
- The verified commit is pushed to `main` and release workflows complete.

## 12. Rollback Notes

All DB behavior changes are read ordering only and require no rollback
migration. Frontend changes can be reverted by restoring the affected helper,
component, i18n, and CSS files. If currency normalization fails, rollback the
shared normalization helper and strategy-scenario call together so display and
paper evaluation cannot diverge.
