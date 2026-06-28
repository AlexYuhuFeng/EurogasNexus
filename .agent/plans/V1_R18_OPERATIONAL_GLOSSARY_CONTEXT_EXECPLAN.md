# V1 R18 Operational Glossary Context ExecPlan

## Goal

Make the glossary an operational cockpit surface, not only a dictionary. A trader
opening a term such as `Zeebrugge Interconnector`, `TTF`, `ICIS Heren`, `NBP`,
or `ICE OCM` must see the definition plus current runtime context: capacity,
capacity usage, related prices, live marks, route candidates, and linked
resource contracts when available.

## Non-Goals

- No order entry, order routing, trade capture, nominations, or auto-trading.
- No external provider calls during imports, tests, or client rendering.
- No new proprietary/vendor data committed to the repo.
- No new heavy dependencies or client runtime stack changes.

## Product Boundary

The glossary remains decision-support and human-review-required. Licensed
commercial prices such as ICIS Heren are represented through customer-provided
runtime DB records or synthetic fixtures only.

## Files To Create/Modify

- `src/eurogas_nexus/domain/analysis.py`
- `src/eurogas_nexus/api/routes/v1/analysis.py`
- `src/eurogas_nexus/api/routes/v1/glossary.py`
- `src/eurogas_nexus/sdk/analysis.py`
- `clients/web/src/api/client.ts`
- `clients/web/src/stores/api.ts`
- `clients/web/src/App.tsx`
- `clients/web/src/i18n/en.json`
- `clients/web/src/i18n/zh.json`
- `clients/web/src/styles/app.css`
- `tests/api/test_analysis_api.py`
- `tests/integration/test_glossary_operational_context_db.py`
- client and architecture docs as needed

## Dependency Policy

Use the existing backend/client stack only. Do not add dependencies.

## Data Policy

PostgreSQL-backed runtime records are required for operational context. When no
DB-backed records exist, return explicit data-quality warnings and empty
sections; do not invent runtime values. Tests may still create isolated
source-shaped fixtures. Do not persist or expose provider credentials.

## API Impact

Keep `GET /api/v1/glossary/{term}/context` stable. Add optional query parameters:

- `lang=en|zh|zh-CN`
- `duration_start_utc`
- `duration_end_utc`

Extend the response with additive fields:

- `description_en`
- `description_zh_cn`
- `requested_duration`
- `entity_summary`
- `metrics`
- `related_contracts`
- `live_market_marks`
- `data_quality`

## DB Impact

No migration. Use existing tables:

- `capacity_profiles`
- `flow_observations`
- `market_observations`
- `live_market_marks`
- `route_candidates`
- `upstream_resource_contracts`

## Tests

- DB-free context returns empty operational sections with data-quality warnings
  instead of invented capacity, price, or route values.
- ICIS Heren context includes licensed-data warning and related prices.
- SQLite-backed runtime context reads actual capacity, flow, market, live mark,
  route, and contract rows.
- Web build must pass after DTO/UI additions.

## Validation Commands

```powershell
ruff check .
pytest -q tests/api/test_analysis_api.py tests/integration/test_glossary_operational_context_db.py tests/sdk/test_sdk_clients.py
pytest -q tests/api tests/contract tests/integration tests/sdk tests/security --basetemp C:\Users\qqshu\.codex\memories\pytest-tmp-r18-final -o cache_dir=C:\Users\qqshu\.codex\memories\pytest-cache-r18-final
npm run build
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

## Acceptance Criteria

- Runtime glossary context for a configured European point or hub shows capacity,
  used capacity, usage percentage, related prices, related routes, and linked
  contracts where available.
- ICIS Heren context shows price-assessment context and licensed-data warning.
- Duration filters are represented in the response and applied to DB-backed
  market, flow, and capacity reads.
- Web glossary panel displays operational cards and detailed context metrics.
- No API breaking change.

## Rollback Notes

Revert this plan and the additive glossary-context changes. No migration is
introduced, so rollback does not require DB schema changes.
