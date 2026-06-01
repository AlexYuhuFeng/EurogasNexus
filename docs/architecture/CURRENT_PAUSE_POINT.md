# Current Pause Point

## Status

Holistic local runtime testing has been performed against the current worktree.
The project is now a **V1 release candidate for the tested local scope**:
backend/API/SDK/CLI, PostgreSQL runtime schema, Web client, and Windows/Tauri
client shell.

Read the full evidence report:

```text
data/release_v1/holistic_real_test_report.md
```

## Runtime Evidence

Validated on 2026-06-01:

```text
ruff check .
pytest -q tests/api tests/contract tests/integration tests/sdk tests/security
npm run build  # clients/web
cargo check --manifest-path clients/desktop/src-tauri/Cargo.toml --locked
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

Results:

```text
Ruff: passed
Python targeted tests: 318 passed
Web build: passed
Desktop cargo check: passed
App import: app import ok, 74 routes
```

Rendered Web client smoke tested on Microsoft Edge through Playwright CLI:

```text
URL: http://127.0.0.1:3000/
API: http://127.0.0.1:8000/api/v1/health
Console after interactions: 0 errors, 0 warnings
Screenshot: C:\Users\qqshu\.codex\memories\eurogas-r17-cockpit.png
```

The smoke test loaded the cockpit, compared UK NTS route options, marked live
PnL, evaluated the paper strategy, opened glossary context, and ran snapshot
analysis without page errors.

## Current Implementation Status

- PostgreSQL is the runtime source of truth for reference network, market
  observations, flow observations, storage observations, LNG observations,
  ingestion run metadata, and provider credential metadata.
- ECB public FX, ENTSOG public operational flow, and GIE AGSI/ALSI keyed feeds
  were explicitly fetched and normalized into local PostgreSQL.
- Provider credentials are backend-owned. Clients can submit keys through
  `/api/v1`, but plaintext keys are not returned and are not stored in client
  state, browser storage, Tauri config, reports, or repo files.
- Web is the single UI source. Windows wraps the built Web bundle through
  Tauri, so future UI/UX work should update Web first and then rebuild Windows.
- Browser QA shows Runtime DB status, active source counts, infrastructure
  signal counts, credential management panel, rendered gas network map,
  animated route/PnL highlighting, route-cost comparison, strategy-lab output,
  glossary context, and report-analysis output.
- The Windows/Tauri shell now starts with a borderless splash window and then
  shows the shared Web client in a borderless fullscreen main window.

## Work Completed Since Previous Pause

- Added Alembic revision `0009_market_positioning_foundation`.
- Added `screen_order_observations` and `portfolio_pnl_snapshots` runtime tables
  for read-only imported screen-order state and portfolio PnL marks.
- Added `/api/v1/portfolio/screen-orders`,
  `/api/v1/portfolio/pnl-snapshots`, and
  `/api/v1/portfolio/live-summary`.
- Added SDK helpers in `eurogas_nexus.sdk.portfolio`.
- Added Web Orders & Live PnL cockpit panel, animated route/PnL overlay, and
  map-first market-positioning documents in English and Mandarin.
- Hardened the Windows client startup contract for splashscreen-to-fullscreen
  transition.
- Added Alembic revision `0005_public_source_credentials`.
- Added storage, LNG, and provider credential tables.
- Added public-source normalization for ECB, ENTSOG, GIE AGSI, and GIE ALSI.
- Added explicit operator script `scripts/ops/ingest_public_sources.py`.
- Added credential API under `/api/v1/credentials/*`.
- Added Web Provider Credentials panel for GIE, EEX, ICE OCM, Trayport, Kpler,
  Platts, Weather, and LLM providers.
- Added DB-backed storage and LNG observation routes.
- Corrected ENTSOG metadata to public/no-key for supported Transparency
  Platform access.
- Built and packaged the Tauri Windows client.
- Verified the shared Web/Windows UI path.

## Remaining Release Limitations

1. Live ingestion is manual/operator-invoked; scheduler/retry/monitoring is not
   productionized.
2. EEX, ICE OCM, Trayport, Kpler, Platts, weather, broker, and LLM provider
   live calls remain untested until credentials and entitlement approval exist.
3. Screen-order and portfolio PnL endpoints are read-only import surfaces. V1
   does not perform order entry, order routing, trade capture, or auto-trading.
4. LLM analysis remains optional and must only invoke a configured backend
   provider credential under explicit operator control.
5. Auth, audit persistence depth, entitlement enforcement routes, and export
   governance runtime checks need hardening before multi-user or production use.
6. Route-cost coverage is still UK National Gas NTS only. The model supports
   broader European TSO tariff expansion, but non-UK audited tariff ingestion is
   not in this checkpoint.

## Route-Cost And Glossary Addendum

Current in-progress route-cost and market-practice hardening adds:

- UK National Gas NTS route-cost calculation from audited tariff rows without
  hard-coding to Easington/Bacton examples;
- DB tables for TSO tariffs, upstream resource contracts, capacity profiles,
  route candidates, live market marks, glossary terms, strategy definitions,
  strategy runs, strategy allocation targets, and strategy alerts;
- `/api/v1/route-cost/*` endpoints and SDK helpers for route candidates,
  generic UK NTS tariff rows, route-cost calculation, Easington option
  comparison, live bid-based PnL marking, LNG regas readiness, and resource-pool
  optimization;
- `/api/v1/strategy-lab/evaluate` and SDK helpers for backtest, shadow-run, and
  live-monitor paper strategy evaluation;
- `/api/v1/glossary` and `/api/v1/glossary/{term}` bilingual glossary routes
  with English, `zh`, and `zh-CN` support;
- Web client panels for map layer/search, above-map portfolio/price/PnL/strategy
  strip, UK NTS contract economics, live PnL, strategy lab, glossary, settings
  language, and light/dark/system theme;
- market-practice audit documents:
  `docs/architecture/MARKET_PRACTICE_AUDIT-EN.md` and
  `docs/architecture/MARKET_PRACTICE_AUDIT-CN.md`;
- map-first trader cockpit UX documents:
  `docs/clients/MAP_FIRST_TRADER_COCKPIT_SPEC-EN.md` and
  `docs/clients/MAP_FIRST_TRADER_COCKPIT_SPEC-CN.md`.
- market-positioning cockpit documents:
  `docs/clients/MARKET_POSITIONING_COCKPIT_SPEC-EN.md` and
  `docs/clients/MARKET_POSITIONING_COCKPIT_SPEC-CN.md`.

This addendum is the current pause marker for continuing the route-cost,
glossary, strategy, cockpit UX, and market-practice work. Preserve UK National
Gas NTS as the route-cost jurisdiction until a later milestone adds audited
European TSO tariff coverage and route optimizer support.

## Next Prompt

```text
Read AGENTS.md, docs/architecture/CURRENT_PAUSE_POINT.md, and
data/release_v1/holistic_real_test_report.md.

Continue Eurogas Nexus from the V1 release-candidate state. Preserve the
single shared Web UI source for both Web and Windows/Tauri. Use PostgreSQL as
the runtime source of truth. Do not store provider credentials in clients.
Start with productionizing live ingestion scheduling, credential health tests,
entitlement/export-governance hardening, and DB-backed import pipelines for
screen orders, portfolio PnL marks, and audited non-UK TSO tariffs selected by
the operator.
```
