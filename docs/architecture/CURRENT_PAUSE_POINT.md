# Current Pause Point

## Status

Holistic local runtime testing has been performed against the current worktree.
The project is now a **V1 release candidate for the tested local scope**:
backend/API/SDK/CLI, Docker PostgreSQL runtime, Web client, and Windows/Tauri
client.

Read the full evidence report:

```text
data/release_v1/holistic_real_test_report.md
```

## Runtime Evidence

Validated on 2026-05-30:

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

Results:

```text
Ruff: passed
Python tests: 346 passed
Web build: passed
Desktop cargo check: passed
Desktop package build: passed
App import: app import ok, 56 routes
Runtime DB: revision 0005_public_source_credentials, missing_tables=0
Live ingestion: ECB=6, ENTSOG=10, GIE AGSI=10, GIE ALSI=10
```

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
  signal counts, credential management panel, and rendered gas network map.

## Work Completed Since Previous Pause

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
3. LLM analysis is still a placeholder.
4. Auth, audit persistence depth, entitlement enforcement routes, and export
   governance runtime checks need hardening before multi-user or production use.

## Next Prompt

```text
Read AGENTS.md, docs/architecture/CURRENT_PAUSE_POINT.md, and
data/release_v1/holistic_real_test_report.md.

Continue Eurogas Nexus from the V1 release-candidate state. Preserve the
single shared Web UI source for both Web and Windows/Tauri. Use PostgreSQL as
the runtime source of truth. Do not store provider credentials in clients.
Start with productionizing live ingestion scheduling, credential health tests,
and entitlement/export-governance hardening for the next provider selected by
the operator.
```
