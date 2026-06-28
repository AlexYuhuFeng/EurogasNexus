# V1 R17 Client And Market Practice Polish ExecPlan

## Goal

Move the current V1 release candidate closer to commercial delivery by tightening the desktop startup shell, map-first cockpit behavior, DB-first live order/PnL read models, bilingual documentation, and executable validation evidence.

## Non-goals

- No order entry, order routing, auto-trading, nomination submission, official approval, legal advice, or ETRM replacement.
- No direct PostgreSQL access from Web, Windows, SDK, or CLI clients.
- No direct vendor, LLM, or market-data calls from client code.
- No new Kafka, Redis, Celery, Electron, React framework swap, or GPL-family dependencies.

## Product Boundary

All new market-practice objects are decision-support observations or snapshots. Screen order records are imported/read-only observations of external screen or broker state, not the system of record for execution or trade capture. PnL snapshots are indicative portfolio valuation records, not accounting statements.

## Files To Create Or Modify

- Modify `clients/desktop/src-tauri/tauri.conf.json` for fullscreen borderless main window plus startup splash window.
- Modify `clients/desktop/src-tauri/src/main.rs` to show the main window after the splash interval.
- Modify `clients/web/src/App.tsx`, `clients/web/src/components/GasNetworkMap.tsx`, `clients/web/src/stores/api.ts`, `clients/web/src/api/client.ts`, and `clients/web/src/styles/app.css` for order/PnL panels and animated map corridor highlighting.
- Create `src/eurogas_nexus/domain/market_positioning.py` for read-only screen order and PnL snapshot DTOs. Missing runtime records must return explicit empty or blocked states, not invented trading values.
- Create `src/eurogas_nexus/db/models/market_positioning.py` and `alembic/versions/0009_market_positioning_foundation.py`.
- Create `src/eurogas_nexus/api/routes/v1/portfolio.py` and register it in `src/eurogas_nexus/api/route_registration.py`.
- Create `src/eurogas_nexus/sdk/portfolio.py` and expose import coverage in SDK tests.
- Update `src/eurogas_nexus/db/models/__init__.py` and `src/eurogas_nexus/db/registry.py`.
- Update `docs/clients/WINDOWS_CLIENT_DESIGN_SPEC.md`, `docs/clients/MAP_FIRST_TRADER_COCKPIT_SPEC-EN.md`, `docs/clients/MAP_FIRST_TRADER_COCKPIT_SPEC-CN.md`, `docs/clients/CLIENT_API_CONTRACT.md`, `docs/clients/SDK_CLIENT_DESIGN_SPEC.md`, `docs/architecture/MARKET_PRACTICE_AUDIT-EN.md`, `docs/architecture/MARKET_PRACTICE_AUDIT-CN.md`, `docs/architecture/CURRENT_PAUSE_POINT.md`, `PROJECT_DIRECTORY.md`, and `README.md`.
- Add tests under `tests/api`, `tests/contract`, `tests/sdk`, and desktop client surface tests.

## Dependency Policy

Use only the existing Python, React/Vite, MapLibre, Zustand, and Tauri stack. Do not add dependencies in this milestone. If a verification tool is missing, record the gap and use the existing test/build commands.

## Data Policy

Use synthetic fixture records only. Do not commit real orders, trades, counterparties, API keys, vendor data, internal strategy parameters, `.env`, or raw market data. DB tables are structures only; operators seed/import their own customer data later through controlled ingestion.

## API Impact

Add read-only `/api/v1/portfolio/*` endpoints:

- `/api/v1/portfolio/screen-orders`
- `/api/v1/portfolio/pnl-snapshots`
- `/api/v1/portfolio/live-summary`

All responses must include research/human-review metadata and source references. No mutation endpoint is added.

## DB Impact

Add Alembic revision `0009_market_positioning_foundation` with:

- `screen_order_observations`
- `portfolio_pnl_snapshots`

Register both tables in the required-table registry. Importing the API must remain DB-safe and migration-free.

## Tests

- API tests for fallback payloads and DB-backed reads.
- Contract tests for SQLAlchemy models and registry membership.
- SDK tests for portfolio import and request path correctness.
- Existing client release-surface tests updated for borderless/fullscreen/splash behavior.

## Validation Commands

Run:

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/sdk tests/security
npm run build
cargo check --manifest-path clients/desktop/src-tauri/Cargo.toml --locked
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

For rendered UI:

```powershell
python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
npm --prefix clients/web run dev -- --host 127.0.0.1 --port 3000
```

Then load `http://127.0.0.1:3000`, confirm first screen renders, trigger route economics, live PnL, strategy evaluation, glossary context, and LLM snapshot buttons without client runtime errors.

## Acceptance Criteria

- Windows Tauri main window starts borderless and fullscreen, with a visible startup splash/loading window.
- Web cockpit shows animated/highlighted route/PnL corridor state and labeled order/PnL context.
- Screen order and PnL structures are DB-first, API/SDK-readable, and clearly read-only decision-support data.
- Clients still use API/SDK only and do not connect to PostgreSQL or read backend data files directly.
- Bilingual docs state the new surfaces and product boundary without ambiguity.
- Ruff, targeted Python tests, web build, desktop cargo check, app import, and rendered smoke interactions are verified before commit.

## Rollback Notes

Rollback is isolated: remove the `0009` migration and market-positioning model/route/SDK files, remove route registration, revert web cockpit additions, and restore the Tauri window config to one standard decorated main window. No destructive DB migration is run by this plan.
