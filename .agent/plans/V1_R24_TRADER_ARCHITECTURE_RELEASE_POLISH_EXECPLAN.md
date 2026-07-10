# V1 R24 Trader Architecture and Release Polish ExecPlan

## 1. Goal

Improve Eurogas Nexus from two objective viewpoints: trader usability and
software-engineering maintainability. This round must keep the DB-first,
API-first product boundary intact, make Strategy/resource-pool evidence clearer,
reduce concentrated frontend code where the change is low risk, add Linux ARM
release validation coverage, locally package the Windows desktop executable, and
publish the verified changes to GitHub.

## 2. Non-Goals

- Do not add order entry, order routing, trade capture, nomination submission,
  auto-trading, settlement, approval, or ETRM replacement behavior.
- Do not make clients connect directly to PostgreSQL.
- Do not call external market, infrastructure, or LLM APIs from tests or import
  paths.
- Do not redesign the whole application in one pass.
- Do not introduce heavy UI frameworks or incompatible licenses.

## 3. Product Boundary

The product remains a trader-reviewed decision-support workspace. Strategy
outputs are shadow-run, backtest, monitoring, and advisory evidence surfaces;
they are not execution instructions. All runtime truth is loaded through the
backend API and PostgreSQL runtime store.

## 4. Files To Create Or Modify

- `.github/workflows/ci.yml`
- `.agent/plans/V1_R24_TRADER_ARCHITECTURE_RELEASE_POLISH_EXECPLAN.md`
- `tests/contract/test_client_release_surface.py`
- `clients/web/src/components/StrategyShadowRunTerminal.tsx`
- Optional low-risk split files under `clients/web/src/components/strategy/`
- `clients/web/src/styles/app.css`
- `clients/web/src/i18n/en.json`
- `clients/web/src/i18n/zh.json`
- Relevant docs only if the UI contract changes.

## 5. Dependency Policy

No new dependencies are planned. Existing stack remains FastAPI, SQLAlchemy,
Alembic, React, TypeScript, Vite, MapLibre, Rust, and Tauri.

## 6. Data Policy

No secrets, vendor data, customer data, or real strategy parameters may be
committed. Preview/simulated price rows are allowed only when they are explicit
runtime records with source provenance. Missing live data must remain visible as
a source-health or data-quality issue.

## 7. API Impact

No API path expansion is planned. The client must continue to use the backend
API surface only.

## 8. DB Impact

No migration is planned. No live migration should run in this round.

## 9. Tests

Add or adjust contract tests for:

- CI desktop matrix includes Windows x64, Linux x64, and Linux ARM64.
- Strategy UI exposes price-basis evidence, resource-pool PnL, data quality,
  and contract attribution with stable component classes and bilingual labels.

## 10. Validation Commands

Run before handoff:

```powershell
ruff check .
pytest -q tests/api tests/contract
npm --prefix clients/web run build
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
npm --prefix clients/desktop run build -- --bundles nsis
```

## 11. Acceptance Criteria

- CI desktop build matrix validates Linux ARM64 in addition to Windows and Linux
  x64.
- Strategy page remains API/SDK-bound and displays clearer trader evidence:
  selected price basis, pool cost, pool volume, source posture, stale/simulated
  warnings, and contract-level PnL attribution.
- Web build passes.
- API import remains DB-optional and import safe.
- A local Windows NSIS executable is produced.
- GitHub main receives the verified commit and workflows are checked.

## 12. Rollback Notes

Frontend UI polish can be reverted by restoring the modified Strategy component,
CSS, and i18n entries. CI matrix rollback only removes the Linux ARM64 entry from
`.github/workflows/ci.yml`. No DB rollback is needed because this plan does not
apply migrations or seed data.
