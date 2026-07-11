# V1 R26 Trader Workspace Information Architecture ExecPlan

## 1. Goal

Replace the remaining preview-style workspace patterns with a coherent trader-facing
product: resource-pool-native Network home, truthful topology presentation, visible
runtime freshness, explicit time context, explainable route allocation, operational
source monitoring, and a compact strategy evaluation terminal. Preserve the shared
Web/Windows client implementation and PostgreSQL-backed API boundary.

## 2. Non-goals

- No order submission, trade execution, nomination submission, or auto-trading.
- No direct client database access.
- No new vendor connector or credential acquisition.
- No claim that route-candidate corridors are surveyed pipeline geometry.
- No fabricated public infrastructure, tariff, FX, or market observations.

## 3. Product boundary

This milestone improves decision-support presentation and interaction only. Simulated
licensed-market substitutes remain explicitly labelled. Every strategy or allocation
output remains reviewable, non-executing, and backed by runtime API data.

## 4. Files to create/modify

- `clients/web/src/App.tsx`
- `clients/web/src/app/workspaceDerivedData.ts`
- `clients/web/src/components/WorkspaceTopBar.tsx`
- `clients/web/src/components/NetworkWorkspace.tsx`
- `clients/web/src/components/GasNetworkMap.tsx`
- `clients/web/src/components/ResourcePoolPathOverlay.tsx`
- `clients/web/src/components/SourceCenter.tsx`
- `clients/web/src/components/StrategyShadowRunTerminal.tsx`
- `clients/web/src/i18n/en.json`
- `clients/web/src/i18n/zh.json`
- `clients/web/src/styles/app.css`
- focused API/contract/unit tests where UI contracts or freshness semantics change

## 5. Dependency policy

Use the current React, TypeScript, MapLibre, Tauri, FastAPI, SQLAlchemy, and test
stack. Add no runtime dependency.

## 6. Data policy

- PostgreSQL remains authoritative.
- Market substitutes are read from PostgreSQL and labelled `Simulated`.
- Freshness is calculated from the latest observation per basis/source.
- Unknown topology, capacity, tariff, access, or price inputs remain unavailable.
- The UI must not imply that route-candidate corridors are complete network geometry.

## 7. API impact

No breaking API change is planned. Existing endpoint metadata, source posture,
market observations, portfolio options, and strategy evaluation contracts remain the
input surface. Any new client time context is local display/filter state until a
backend endpoint explicitly accepts it.

## 8. DB impact

No migration. The runtime database is read during interactive validation. The
existing simulated-market worker may write source-shaped licensed-market substitutes
to the test database only.

## 9. Tests

- Contract tests for default map density and truthful geometry status.
- Contract tests for non-duplicated Network responsibilities.
- Contract tests for operational Sources table structure.
- Contract tests for Strategy workspace hierarchy and warning translation.
- Existing API, integration, SDK, CLI, release, security, and unit suites.
- 2K light/dark and English/Mandarin browser interaction.
- Packaged Windows EXE interaction across Network, Sources, Strategy, and Settings.

## 10. Validation commands

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/sdk tests/cli tests/release tests/security tests/unit
npm --prefix clients/web run build
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
npm --prefix clients/desktop run build -- --bundles nsis
```

Run `scripts/ops/validate_runtime_db.py --json` against the configured test runtime
without printing the unredacted DSN.

## 11. Acceptance criteria

- Network defaults to a resource-pool decision view, not all-node visual noise.
- Full-network, LNG, IP, and hub layers remain user-selectable and colour-distinct.
- Commercial corridors, highlighted recommendations, and reference edges have
  different map semantics.
- Left rail contains resources/constraints; right rail contains ranked decisions,
  economics, and evidence without duplicate route cards.
- Global time context and last-update/source posture are visible.
- Every displayed price identifies currency, source mode, and freshness.
- Route decisions expose capacity, TSO access, cost, allocation, rationale, and
  warnings through a compact disclosure.
- Sources uses an operational, filterable table with issue-first scanning.
- Strategy presents state, controls, comparison, targets, PnL, and evidence in a
  deliberate hierarchy and translates known machine warnings.
- Light/dark and English/Mandarin pass at the Windows 2K high-DPI viewport.
- Web build, tests, runtime validation, NSIS build, and packaged EXE interaction pass.

## 12. Rollback notes

The shared client can be rolled back as one commit. No migration or persistent schema
change is introduced. Stop the local simulated-market worker to return the test DB to
operator-controlled updates; historical simulated rows remain explicitly identified.
