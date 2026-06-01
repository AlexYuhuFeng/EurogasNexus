# V1 R19 Market Positioning Import Control ExecPlan

## Goal

Add an internal/operator import control plane for external screen-order
observations and indicative portfolio PnL snapshots. The import path must write
to PostgreSQL-backed runtime tables, fail closed without entitlement records,
and create audit/ingestion-run evidence.

## Non-Goals

- No public client write API.
- No order entry, order routing, order cancellation, trade capture, nomination,
  execution, settlement, accounting, or ETRM replacement behavior.
- No external API calls, live connectors, Docker startup, or LLM provider calls.
- No real vendor/customer data committed to the repository.

## Product Boundary

Imported screen orders are observations of external systems only. Imported PnL
snapshots are indicative decision-support marks only. They do not become an
execution ledger, trade blotter, or accounting book.

## Files To Create/Modify

- `src/eurogas_nexus/domain/market_positioning_import.py`
- `src/eurogas_nexus/db/repositories/market_positioning_import.py`
- `src/eurogas_nexus/db/repositories/__init__.py`
- `src/eurogas_nexus/api/routes/internal/portfolio_import.py`
- `src/eurogas_nexus/api/routes/internal/router.py`
- `tests/integration/test_market_positioning_import_repository.py`
- `tests/api/test_internal_market_positioning_import.py`
- `docs/operations/MARKET_POSITIONING_IMPORTS-EN.md`
- `docs/operations/MARKET_POSITIONING_IMPORTS-CN.md`
- release/client docs and pause point

## Dependency Policy

Use existing Python, FastAPI, Pydantic, SQLAlchemy, pytest, and Ruff only.

## Data Policy

Runtime PostgreSQL is the source of truth. Tests may use SQLite. Import payloads
are synthetic fixtures only. Do not commit real screen data, order IDs, account
labels, strategies, contracts, credentials, or raw vendor data.

## API Impact

Add internal profile route only:

```text
POST /api/internal/portfolio/import-observations
```

The route must not appear in release profile or default client `/api/v1`
surface.

## DB Impact

No migration. Reuse existing tables:

- `screen_order_observations`;
- `portfolio_pnl_snapshots`;
- `entitlement_decisions`;
- `audit_events`;
- `ingestion_runs`.

## Tests

- Repository import succeeds when entitlement rows grant each item source and
  dataset.
- Repository import fails closed and writes audit/failed run when entitlement is
  missing.
- Internal API route can import into a configured runtime DB.
- Release profile does not expose the internal import route.
- App import remains DB-free.

## Validation Commands

```powershell
ruff check .
pytest -q tests/api/test_internal_market_positioning_import.py tests/integration/test_market_positioning_import_repository.py
pytest -q tests/api tests/contract tests/integration tests/sdk tests/security --basetemp C:\Users\qqshu\.codex\memories\pytest-tmp-r19-final -o cache_dir=C:\Users\qqshu\.codex\memories\pytest-cache-r19-final
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

## Acceptance Criteria

- Import writes are internal/operator only.
- Unknown or missing entitlement denies the whole batch.
- Successful imports upsert observations and write audit/ingestion-run records.
- Failed imports write audit/ingestion-run records and no observation rows.
- Stable `/api/v1/portfolio/*` remains read-only.
- Validation passes without a live DB.

## Rollback Notes

Revert this checkpoint. No migration is introduced, so rollback does not require
schema rollback.
