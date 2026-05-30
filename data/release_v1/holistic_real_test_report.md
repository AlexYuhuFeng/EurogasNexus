# Holistic Real Runtime Test Report

Date: 2026-05-30

## Scope Tested

This test ran the current Eurogas Nexus worktree as a local V1 runtime:

- Docker PostgreSQL container: `eurogas-nexus-db`
- Alembic migration to repository head
- Synthetic V1 reference-network and observation seed
- Explicit ECB, ENTSOG, and GIE AGSI/ALSI live ingestion into PostgreSQL
- FastAPI backend on localhost
- Runtime DB status route
- API route surface used by a gas market researcher
- SDK and CLI calls against the running local backend
- Web client build and Vite dev proxy against the running local backend
- Browser-level Web interaction checks, including map, live source counts, and
  provider credential panel
- Windows/Tauri shell build and package checks

ECB, ENTSOG, and GIE AGSI/ALSI were called explicitly during this validation.
EEX, Trayport, ICE OCM, Kpler, Platts, weather, broker, and LLM provider APIs
were not called. No secrets or full database URLs were printed. No raw provider
payloads were committed.

## Runtime DB Evidence

- PostgreSQL container: healthy
- Alembic revision: `0005_public_source_credentials`
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
  - `storage_observations`: synthetic records
  - `lng_observations`: synthetic records

Live source ingestion added:

- ECB FX reference rates: 6 normalized rows
- ENTSOG operational flow data: 10 normalized rows
- GIE AGSI storage data: 10 normalized rows
- GIE ALSI LNG data: 10 normalized rows
- GIE credential stored through backend credential API with encrypted DB
  payload and redacted API/UI preview only

The reference-network, market observation, flow observation, storage, and LNG
observation APIs read the configured runtime DB when a DB URL is present.
Fixture fallback remains only for DB-free app import and offline tests.

## API Walkthrough Evidence

The running local backend passed:

- `/v1/health` compatibility
- `/api/v1/health`
- `/api/v1/runtime/db`
- DB-backed `/api/v1/reference-network/*`
- DB-backed `/api/v1/market/observations`
- DB-backed `/api/v1/physical/flows`
- DB-backed `/api/v1/storage/observations`
- DB-backed `/api/v1/lng/observations`
- provider credential routes under `/api/v1/credentials/*`
- source registry with active row counts for ECB, ENTSOG, and GIE
- route-cost, netback, feasibility, allocation, monitoring, nowcast, backtest,
  shadow-run, LLM-analysis placeholder, and research brief routes

Runtime DB status reported revision `0005_public_source_credentials` with no
missing required tables.

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

The Python package declares the CLI entrypoint:

```text
eurogas-nexus = eurogas_nexus.cli.main:main
```

## Web Client Evidence

The Web client includes a MapLibre network workspace backed by `/api/v1`.
The header status says `Runtime DB` when PostgreSQL-backed API data is being
used.

Validated:

- `npm run build`
- Vite dev proxy to `/api/v1`
- English and Mandarin strings load from local JSON files
- Light/dark/system theme control remains local UI preference only
- Browser screenshot QA shows map nodes, route lines, side panels, status,
  language switch, theme switch, node popup, active source counts,
  infrastructure signal counts, and provider credential panel with no console
  errors

Credential UX:

- ECB and ENTSOG show as public/no-key providers.
- GIE shows configured using a redacted preview only.
- EEX, ICE OCM, Trayport, Kpler, Platts, Weather, and LLM providers have
  credential entry surfaces but were not live-called.
- Clients submit credentials to backend `/api/v1`; they do not store plaintext
  provider keys locally.

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
npm run build  # clients/web
cargo check --manifest-path clients/desktop/src-tauri/Cargo.toml --locked
npm run build  # clients/desktop
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
python scripts/ops/validate_v1_runtime_db.py --json
python scripts/ops/ingest_public_sources.py --source all --limit 10 --json
```

Current route count: `56`.

Current Python test count: `325 passed`.

## Fixes Made During Holistic Test

- Fixed pytest collection for duplicate test basenames via importlib mode.
- Converted `eurogas_nexus.db.repositories` into a real package to remove a
  module/package collision.
- Preserved API import safety by making DB imports request-time only.
- Added DB-backed reference-network API reads when a runtime DB URL is present.
- Added synthetic PostgreSQL seed script for V1 reference-network and
  observation data.
- Added public-source normalization for ECB, ENTSOG, GIE AGSI, and GIE ALSI.
- Added explicit live public-source ingestion script.
- Added DB-backed GIE storage and LNG observation routes.
- Added backend-owned provider credential storage and credential API.
- Added Web credential management panel for GIE, EEX, ICE OCM, Trayport,
  Kpler, Platts, Weather, and LLM providers.
- Added `/api/v1/runtime/db` with redacted DB status.
- Added SDK and CLI access to runtime DB status.
- Added an executable CLI entrypoint.
- Replaced the Web map placeholder with a MapLibre network map and workspace
  panels backed by `/api/v1`.
- Renamed the client status badge from `Live` to `Runtime DB`.
- Added a Tauri Windows shell that packages the shared Web bundle.
- Removed unused Web dependencies and kept MapLibre in an explicit vendor map
  chunk.
- Ignored generated Web `node_modules`, `dist`, and Tauri target artifacts.

## Official Release Status

Status: `RELEASE CANDIDATE`

The local backend/API/SDK/CLI/Web/Windows runtime is release-candidate ready for
the tested scope. Official production use still requires operator acceptance of
the remaining limitations below.

## Remaining Release Limitations

- Live ingestion is operator-invoked; no production scheduler, retry policy, or
  monitoring service is active yet.
- EEX, Trayport, ICE OCM, Kpler, Platts, weather, broker, and LLM live
  providers remain untested because credentials/entitlements were not supplied.
- LLM analysis route is a placeholder. No provider integration, prompt logging,
  citation enforcement, or offline/live gating is implemented.
- Auth, audit persistence depth, entitlement enforcement routes, and export
  governance runtime checks remain partial and should be hardened before
  multi-user or production deployment.

## Commit Decision

The current work is suitable for a GitHub release-candidate sync. Do not tag it
as a final production release until the remaining limitations are explicitly
accepted or completed.
