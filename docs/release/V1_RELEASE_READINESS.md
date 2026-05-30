# V1 Release Readiness

## Current Status

Status: `RELEASE CANDIDATE`

Eurogas Nexus passes a local Docker PostgreSQL runtime test for the
backend/API/SDK/CLI, Web workspace, and Windows/Tauri shell. The official V1
local release-candidate scope is complete.

`Runtime DB` in the client means the UI is reading the local runtime
PostgreSQL-backed API. In the latest local validation, ECB public FX, ENTSOG
public operational flow, and GIE AGSI/ALSI keyed feeds were called explicitly
and normalized into PostgreSQL. It does **not** mean EEX, Trayport, ICE OCM,
Kpler, Platts, weather, broker, or LLM provider feeds have been called or
validated.

Authoritative current evidence:

- `data/release_v1/holistic_real_test_report.md`
- `docs/architecture/CURRENT_PAUSE_POINT.md`

## Validated Gates

- App import remains DB-free and network-free.
- Release API profile disables docs/openapi endpoints.
- No development-only routes enabled in release profile.
- No silent local file fallback in trial or release mode.
- `/v1/health` compatibility remains available.
- `/api/v1` is the released client prefix.
- PostgreSQL runtime validation passes against local Docker PostgreSQL.
- Alembic revision is `0005_public_source_credentials`.
- Required runtime tables are present.
- Reference-network API reads runtime PostgreSQL when configured.
- ECB FX, ENTSOG flow, and GIE AGSI/ALSI rows can be explicitly live-ingested
  into PostgreSQL through `scripts/ops/ingest_public_sources.py`.
- Python SDK and CLI use `/api/v1`.
- Web client builds and uses `/api/v1` through the backend only.
- Windows client builds as a Tauri shell around the shared Web bundle.
- No client connects directly to PostgreSQL.
- Source posture panels show active ECB, ENTSOG, and GIE row counts after live
  ingestion.
- Provider credentials are backend-owned: clients can submit keys, but plaintext
  credentials are never returned by the API or persisted in client storage.
- No raw provider data, provider credentials, full DB URLs, `.env` files, or
  real commercial strategy parameters were added to the repository.

## Latest Validation Results

```text
ruff check .        -> passed
pytest -q           -> 346 passed
npm run build       -> passed for Web and Windows/Tauri
app import          -> app import ok, 56 routes
runtime DB          -> revision 0005_public_source_credentials, missing_tables=0
API live sources    -> ECB=6, ENTSOG=10, GIE AGSI=10, GIE ALSI=10
SDK/CLI walkthrough -> passed against local localhost API
Web browser QA      -> Runtime DB label, map render, live counts, credentials passed
Windows build       -> Tauri cargo check and NSIS package passed
```

## Required Before Production Deployment

- Production scheduling/retry/monitoring for live ingestion should be added.
- Commercial live connector execution for EEX, ICE OCM, Trayport, Kpler,
  Platts, weather, broker, and other keyed providers must remain gated until
  credentials, entitlement, internet policy, and operator validation are
  complete.
- LLM provider execution must remain gated until API keys, prompt/citation
  policy, and audit posture are complete.
- Auth, audit persistence, entitlement routes, and export-governance runtime
  enforcement must be completed or explicitly accepted as release limitations.

## Commit Policy

The current work may be committed and pushed as a V1 release-candidate sync.
It should not be tagged as production-ready until the remaining production
limitations are completed or explicitly accepted.

## Rollback

No destructive runtime migration was added. The local Docker PostgreSQL database
was migrated to repository head, seeded with synthetic baseline data, and then
updated with live ECB, ENTSOG, and GIE AGSI/ALSI normalized observations.
