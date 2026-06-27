# V1 Release Readiness

## Current Status

Status: `RELEASE CANDIDATE`

Eurogas Nexus passes a local Docker PostgreSQL runtime test for the
backend/API/SDK/CLI, Web workspace, and Windows/Tauri shell. The official V1
local release-candidate scope is complete.

`Runtime DB` in the client means the UI is reading the local runtime
PostgreSQL-backed API. In the latest local validation, ECB public FX, ENTSOG
public operational flow, ENTSOG connection point / TSO access metadata, and GIE
AGSI/ALSI keyed feeds were called explicitly and normalized into PostgreSQL. It
does **not** mean EEX, Trayport, ICE OCM, Kpler, Platts, ICIS, Argus, weather,
broker, or LLM provider feeds have been called or validated.

Authoritative current evidence:

- `data/release_v1/holistic_real_test_report.md`
- `docs/architecture/CURRENT_PAUSE_POINT.md`

## Validated Gates

- App import remains DB-free and network-free.
- Release API profile disables docs/openapi endpoints.
- No development-only routes enabled in release profile.
- No silent local file fallback in trial or release mode.
- `/api/health` compatibility remains available.
- `/api` is the released client prefix.
- PostgreSQL runtime validation passes against local Docker PostgreSQL.
- Alembic revision is `0011_reference_source_lineage`.
- Required runtime tables are present.
- Reference-network API reads runtime PostgreSQL when configured.
- ECB FX, ENTSOG flow, ENTSOG reference-network / TSO access, and GIE
  AGSI/ALSI rows can be explicitly live-ingested into PostgreSQL through
  `scripts/ops/ingest_public_sources.py`.
- Python SDK and CLI use `/api`.
- Web client builds and uses `/api` through the backend only.
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
pytest target set   -> 326 passed plus 47 focused route/workflow tests
npm web build       -> passed
app import          -> app import ok, 78 routes
runtime DB          -> revision 0011_reference_source_lineage, missing_tables=0
API live sources    -> ECB=12, ENTSOG flows=1000, ENTSOG reference=2448, GIE AGSI=300, GIE ALSI=300
UK NTS tariffs      -> 1315 rows in PostgreSQL, Easington -> Bacton GDN calculation passed
Web build           -> passed
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
was migrated to repository head and updated with normalized ECB, ENTSOG, and GIE
observations plus audited public tariff rows and operator-owned local test
price/contract records.
