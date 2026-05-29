# Holistic Real Runtime Test Report

Date: 2026-05-29

## Scope Tested

This test ran the current Eurogas Nexus worktree as a local V1 runtime:

- Docker PostgreSQL container: `eurogas-nexus-db`
- Alembic migration to repository head
- Synthetic V1 reference-network and observation seed
- FastAPI backend on localhost
- Runtime DB status route
- API route surface used by a gas market researcher
- SDK and CLI calls against the running local backend
- Web client build and Vite dev proxy against the running local backend
- Browser-level Web interaction checks
- Windows/Tauri shell build and package checks

No external market, weather, exchange, broker, LLM, or vendor API was called.
No secrets or full database URLs were printed.
ECB, ENTSOG, GIE, EEX, Trayport, ICE OCM, and weather entries are registered
source posture records only; their live data transmission, entitlement, and
provider storage flows were not tested.

## Runtime DB Evidence

- PostgreSQL container: healthy
- Alembic revision: `0004_r16_observation_tables`
- Missing required tables: `0`
- Runtime DB validator: passed
- Synthetic runtime seed:
  - `reference_nodes`: 12
  - `reference_edges`: 10
  - `reference_facilities`: 7
  - `reference_market_hubs`: 7
  - `node_facility_mappings`: 5
  - `topology_market_mappings`: 5
  - `market_observations`: synthetic records
  - `flow_observations`: synthetic records

The reference-network, market observation, and flow observation APIs read the
configured runtime DB when a DB URL is present. Fixture fallback remains only
for DB-free app import and offline tests.

## API Walkthrough Evidence

The running local backend passed:

- 39 GET requests
- 8 POST research workflow requests
- `/v1/health` compatibility
- `/api/v1/health`
- `/api/v1/runtime/db`
- DB-backed `/api/v1/reference-network/*`
- source registry and ingestion run fixtures
- market, physical, LNG, storage, weather, contracts, glossary fixtures
- route-cost, netback, feasibility, allocation, monitoring, nowcast, backtest,
  shadow-run, LLM-analysis placeholder, and research brief routes

Reference-network response lineage reported `runtime-postgresql`.

## SDK And CLI Evidence

Local SDK/CLI calls passed against `http://127.0.0.1:8010`:

- `health`
- `runtime-db`
- `nodes`
- `capacity-contracts`
- `routes`
- `hdd-cdd`
- SDK route cost: `2.35`
- SDK netback: `40.7`
- SDK feasibility: `feasible`

The Python package now declares the CLI entrypoint:

```text
eurogas-nexus = eurogas_nexus.cli.main:main
```

## Web Client Evidence

The Web client now includes a MapLibre network workspace backed by `/api/v1`.
The header status says `Runtime DB` when PostgreSQL-backed API data is being
used, to avoid implying live external vendor feed validation.

Validated:

- `npm install --ignore-scripts --no-audit --no-fund --loglevel=warn`
- `npm run build`
- Vite dev proxy `/api/v1/reference-network/nodes`
- Vite dev proxy `/api/v1/runtime/db`
- English and Mandarin strings load from local JSON files
- Light/dark/system theme control remains local UI preference only
- Browser screenshot QA shows map nodes, route lines, side panels, status,
  language switch, theme switch, and node popup with no console errors.

Known Web build note:

- MapLibre is isolated into a dedicated vendor chunk because the map is the
  primary V1 screen.

## Windows Client Evidence

The Windows client is implemented as a Tauri 2 shell around the shared Web
bundle. It does not connect to PostgreSQL or provider systems directly.

Validated:

- `cargo check --manifest-path clients/desktop/src-tauri/Cargo.toml --locked`
- `npm run build` in `clients/desktop`
- NSIS installer generated under
  `clients/desktop/src-tauri/target/release/bundle/nsis/`

## Validation Commands Passed

```text
ruff check .
pytest -q
npm run build
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
python scripts/ops/validate_v1_runtime_db.py --json
```

Current route count: `53`.

Current Python test count: `312 passed`.

## Fixes Made During Holistic Test

- Fixed pytest collection for duplicate test basenames via importlib mode.
- Converted `eurogas_nexus.db.repositories` into a real package to remove a
  module/package collision.
- Preserved API import safety by making DB imports request-time only.
- Added DB-backed reference-network API reads when a runtime DB URL is present.
- Added explicit synthetic PostgreSQL seed script for V1 reference-network data.
- Added `/api/v1/runtime/db` with redacted DB status.
- Added SDK and CLI access to runtime DB status.
- Added an executable CLI entrypoint.
- Replaced the Web map placeholder with a MapLibre network map and workspace
  panels backed by `/api/v1`.
- Ignored generated Web `node_modules` and `dist` artifacts.

## Official Release Status

Status: `NOT READY FOR OFFICIAL V1 RELEASE`

The backend/API/SDK/CLI/Web runtime is materially stronger and passes local
holistic tests, but official V1 release is not proven because required product
surfaces remain partial or mocked.

## Remaining Release Blockers

- Windows client is still documentation-only. No Tauri shell has been built or
  packaged.
- Live ECB, ENTSOG, GIE, EEX, Trayport, ICE OCM, and weather connectors remain
  mocked/offline. Credentials, entitlements, internet policy, and live-source
  tests are not complete.
- LLM analysis route is a placeholder. No provider integration, prompt logging,
  citation enforcement, or offline/live gating is implemented.
- Most non-reference domain data still comes from synthetic route fixtures, not
  persisted runtime DB tables.
- Auth, audit persistence, entitlement enforcement routes, and export-governance
  runtime checks are still shells or local models.
- Web client needs browser-level interaction testing with screenshots/canvas
  checks before UX can be called release-grade.
- Web bundle should be code-split before production packaging.

## Commit Decision

No official-release commit should be made until the blockers above are either
implemented or explicitly accepted as release limitations by the user.
