# Milestone 1 Report

## Status

PARTIAL bootstrap alignment with existing repository state. The worktree already
contained later-milestone DB, Alembic, SDK, CLI, and ingestion scaffolding. This
milestone preserved those files and hardened the requested Milestone 1
foundation without adding business features.

## Completed

- Added repository governance files and CI workflow.
- Added public-repository warnings for secrets, vendor data, internal
  commercial data, raw market data, contracts, and strategy parameters.
- Implemented DB URL resolution with the required precedence:
  `RUNTIME_STORE_DATABASE_URL`, `DATABASE_URL`, then legacy
  `EUROGAS_NEXUS_DB_DSN`.
- Implemented DB URL redaction.
- Added lazy `get_engine()` and `get_session_factory()` helpers.
- Added read-only DB connectivity and Alembic revision helpers.
- Added required-table registry.
- Added non-destructive runtime DB validation script with `--json`.
- Hardened Alembic metadata import safety.
- Added `/api/v1/health` alias while preserving `/v1/health`.
- Normalized internal/dev route prefixes to `/api/internal` and `/api/dev`.
- Updated the SDK health client to target `/api/v1/health`.
- Added API path policy and normalization plan.
- Added integration, security, API, and contract tests.

## Validation Evidence

- Focused new and updated tests: `28 passed`.
- CI-targeted tests: `61 passed`.
- `ruff check .`: passed.
- `pytest -q tests/api tests/contract tests/integration tests/security`:
  `56 passed`.
- App import: `app import ok`, route count `7`.
- Runtime DB validation script missing-URL mode: controlled non-zero condition
  with redacted JSON output and no DB contact.

## Assumptions

- Existing `ingestion_runs` model and migration are accepted as already-present
  repository state.
- Required runtime tables currently include `ingestion_runs`.
- `/v1/health` remains a compatibility endpoint through the bootstrap phase.

## Warnings

- No live DB was used.
- No migrations were executed.
- Runtime DB validation exits non-zero when no DB URL is configured, by design.
- Development OpenAPI may show both `/v1/health` and `/api/v1/health` during
  the compatibility period.

## Source References

- `.agent/plans/V1_M1_GOVERNANCE_DB_API_PATH_EXECPLAN.md`
- `docs/api/API_PATH_POLICY.md`
- `docs/operations/LOCAL_DEVELOPMENT.md`
- `scripts/ops/validate_v1_runtime_db.py`

## Lineage

Generated during Milestone 1 implementation on 2026-05-28 from repository
tests, local source inspection, and local validation commands only.

## Review Flags

- `research_only`: true
- `human_review_required`: true
