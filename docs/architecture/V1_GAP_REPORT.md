# V1 Gap Report

This report records known gaps instead of inventing behavior.

## RESOLVED: Product North-Star Alignment

Historical local Eurogas Nexus implementations clarify the long-term product
goal: a governed, map-centric European gas decision-support workspace served by
DB-first backend APIs. The repository now documents that north star and ships a
V1 release-candidate slice for backend/API/SDK/CLI/Web/Windows.

Credential requirements: none.

Next action: keep historical frontend, desktop, connector, LLM, and local-file
runtime behavior as reference evidence only.

## RESOLVED: Python Tooling Validation

The repository declares the Python runtime and development dependencies needed
for validation. Current evidence shows Ruff and the full pytest suite passing.

Credential requirements: none.

Next action: keep validation commands in `docs/operations/VALIDATION.md`
aligned with CI and release reports.

## RESOLVED: PostgreSQL Runtime Foundation

PostgreSQL is the runtime source of truth. The DB foundation layer
configuration, lazy engine/session factories, declarative models, Alembic
scaffolding, and runtime validator are implemented and import-safe. Live DB
connections remain explicit: engines are created only through factory calls or
operator scripts.

Credential requirements: operator-provided database URL through
`RUNTIME_STORE_DATABASE_URL`, `DATABASE_URL`, or legacy
`EUROGAS_NEXUS_DB_DSN`. Do not commit or print the URL.

Next action: productionize scheduled live ingestion and DB operations.

## PARTIAL: External Data Sources

ECB public FX, ENTSOG public operational flow, and GIE AGSI/ALSI keyed data have
been explicitly tested through local PostgreSQL ingestion. EEX, Trayport,
ICE OCM, Kpler, Platts, weather, broker, and LLM providers remain untested
until credentials, entitlement review, and operator approval exist.

Credential requirements: backend credential API and encrypted PostgreSQL-backed
credential store are implemented. Provider keys must not be stored in clients or
repo files.

Next action: implement provider-specific live tests one provider at a time.

## PARTIAL: Analysis Output Schema

The required analysis-output metadata fields are documented, and early
research-only workflow routes exist. Production-grade LLM analysis, prompt
logging, citation enforcement, and final report governance remain deferred.

Next action: create a hardened analysis-output contract and tests when the
first LLM-backed research workflow is approved.
