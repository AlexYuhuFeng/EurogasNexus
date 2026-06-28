# V1 R20 Intuitive Glossary Context ExecPlan

## Goal

Make the glossary an operational context surface instead of static help text.
When a user selects a glossary term such as `Zeebrugge Interconnector`, `TTF`,
`GATE LNG`, `ICIS Heren`, `NBP`, or `ICE OCM`, the API must return the term
description plus DB-backed capacity, capacity-in-use, prices, live marks,
routes, contracts, data quality, and warnings for the selected duration where
those records exist.

## Non-Goals

- Do not call ENTSOG, GIE, ECB, ICIS, EEX, ICE OCM, Trayport, Kpler, Platts,
  weather, map, or LLM providers.
- Do not create orders, nominations, trade capture, auto-trading, or official
  trading recommendations.
- Do not add new heavy dependencies.
- Do not introduce a new client data path; clients continue to use API/SDK only.
- Do not run live migrations or require a live DB for tests.

## Product Boundary

This release slice is decision-support only. It improves how runtime data is
explained in glossary context cards. It does not approve operational action or
claim licensed market data is available unless customer/imported runtime rows
exist.

## Files To Create Or Modify

- Modify `src/eurogas_nexus/domain/analysis.py`
  - add deterministic context key derivation from the selected term,
    glossary aliases, related terms, and matching runtime entities;
  - aggregate capacity usage across the selected duration;
  - add `matched_entities` and `context_sections` while preserving existing
    response fields.
- Modify `src/eurogas_nexus/api/routes/v1/analysis.py`
  - include glossary aliases and related terms in DB snapshots.
- Modify `src/eurogas_nexus/sdk/glossary.py`
  - expose a typed `GlossaryContext` model and `fetch_glossary_context()`.
- Modify `clients/web/src/api/client.ts`
  - type the new context fields.
- Modify `clients/web/src/App.tsx`
  - render glossary context as grouped operational sections.
- Modify `clients/web/src/styles/app.css`
  - make the grouped context readable in light/dark modes and responsive.
- Modify `clients/web/src/i18n/en.json` and `clients/web/src/i18n/zh.json`
  - add labels for matched entities, capacity, prices, routes, contracts,
    live marks, and data quality.
- Modify `docs/clients/OPERATIONAL_GLOSSARY_CONTEXT_SPEC-EN.md`
  and `docs/clients/OPERATIONAL_GLOSSARY_CONTEXT_SPEC-CN.md`
  - document generalized DB-first behavior and UTF-8 Mandarin content.
- Modify `PROJECT_DIRECTORY.md`,
  `docs/architecture/CURRENT_PAUSE_POINT.md`, and `README.md`
  - update the current capability statement after validation.
- Add/update tests:
  - `tests/integration/test_glossary_operational_context_db.py`
  - `tests/api/test_analysis_api.py`
  - `tests/sdk/test_sdk_clients.py`
  - `tests/contract/test_client_release_surface.py` or equivalent client
    contract test if current contracts cover glossary surface.

## Dependency Policy

Use only existing Python, React, and TypeScript dependencies. No new package
manager installs are required.

## Data Policy

Tests may use synthetic SQLite fixtures only. The repository must not include
real licensed ICIS data, real customer contracts, real vendor records, API
keys, or raw market data. Customer-licensed price context is represented by
synthetic rows with explicit source references.

## API Impact

Preserve:

- `GET /api/v1/glossary`
- `GET /api/v1/glossary/{term}`
- `GET /api/v1/glossary/{term}/context`

Extend `GET /api/v1/glossary/{term}/context` response with:

- `matched_entities`: normalized runtime entities that explain why records were
  attached to the term;
- `context_sections`: grouped sections for `overview`, `capacity`, `prices`,
  `routes`, `contracts`, `live_marks`, and `data_quality`.

Existing fields remain backward compatible:

- `capacity`
- `capacity_usage`
- `metrics`
- `related_prices`
- `related_routes`
- `related_contracts`
- `live_market_marks`
- `warnings`

## DB Impact

No new tables are required. The resolver reads existing runtime tables:

- `glossary_terms`
- `capacity_profiles`
- `flow_observations`
- `market_observations`
- `live_market_marks`
- `route_candidates`
- `upstream_resource_contracts`

## Tests

- Add an integration test for a non-UK European point, proving the resolver
  derives context from runtime rows and aliases instead of a dedicated
  hard-coded profile.
- Add/extend API tests for `ICIS Heren` price-assessment context, grouped
  sections, and licensed-data warning.
- Add SDK tests for `fetch_glossary_context`.
- Preserve the stable response contract while replacing hard-coded point
  expectations with DB-backed European fixtures.

## Validation Commands

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/sdk tests/security
npm run build
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
rg "<real-provider-key-placeholder>" .
```

## Acceptance Criteria

- A runtime point such as `Zeebrugge Interconnector` shows description,
  capacity, capacity-in-use absolute value and percentage, related prices, live
  marks, routes, contracts, warnings, and data-quality metadata when matching DB
  records exist.
- Other European points work without dedicated hard-coded profiles when matching
  DB records exist.
- `ICIS Heren` context shows related price records and retains the licensed
  data warning.
- Web client renders grouped context sections instead of raw unstructured spans.
- SDK exposes glossary context.
- English and Mandarin docs are valid UTF-8 and clear.
- Ruff, targeted Python tests, Web build, app import, and secret search pass.

## Rollback Notes

Rollback can revert this commit without changing DB schema. Existing
`/api/v1/glossary/{term}/context` callers will lose the new grouped fields but
keep the previous route contract.
