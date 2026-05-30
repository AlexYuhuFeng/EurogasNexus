# R2: Runtime Store and Governance Foundation Report

**Milestone ID:** R2
**Status:** COMPLETE
**Date:** 2026-05-29

## Evidence

- `ResultEnvelope` preserves required research metadata fields: assumptions, missing_inputs, warnings, source_references, lineage, research_only, human_review_required.
- `SourceReference` contract exists with provenance fields: reference_id, source_system, source_dataset, retrieval_ts_utc, load_ts_utc, schema_version, freshness, quality_results, is_synthetic, entitlement_scope.
- `LineageRecord` contract exists with event tracking: event_id, event_type, source_reference_id, target_reference_id, detail, event_ts_utc.
- `DataQualityRecord` contract exists with check fields: check_name, severity, passed, detail, source_reference_id, checked_at_utc.
- `FreshnessState` enum: fresh, stale, unknown, unavailable.
- `EntitlementDecision` fails closed by default (granted=False).
- `entitlement_check()` fails closed for unknown commercial data sources.
- `ExportDecision` enum: allowed, restricted, denied, unknown.
- `export_check()` fails closed for unknown entitlement scope (returns denied).
- `AuditEvent` model with severity classification: info, warning, error, critical.
- `RuntimeStoreRepository` abstract base requires ResultEnvelope wrapping.
- `_no_file_fallback_in_trial_or_release` enforceable by tests.
- Governance package does not import FastAPI, web, or client code.
- App import DB-connection free (7 routes).
- Default tests remain DB-free.

## Files Created / Modified

- `src/eurogas_nexus/runtime_store/contracts.py` — Added FreshnessState, DataQualityRecord, SourceReference, LineageRecord, RuntimeStoreRepository ABC
- `src/eurogas_nexus/governance/__init__.py` — New governance package exports
- `src/eurogas_nexus/governance/entitlement.py` — EntitlementDecision, EntitlementScope, ExportDecision, ExportEvaluation, entitlement_check, export_check
- `src/eurogas_nexus/governance/audit.py` — AuditSeverity, AuditEvent
- `.agent/plans/V1_R2_RUNTIME_STORE_GOVERNANCE_EXECPLAN.md` — ExecPlan
- `data/release_v1/r2_runtime_governance_report.md` — This report
- `tests/contract/test_runtime_store_contracts.py` — Contract tests (17 tests)
- `tests/contract/test_governance_foundation.py` — Governance foundation tests (15 tests)

## DB Impact

No DB schema changes. No Alembic revision. No new required tables.
Runtime-store contracts remain import-safe shells.
Governance models are pure dataclass decision shells.

## API Impact

No new API routes.

## Validation

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/security tests/sdk tests/cli
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

Result:
- ruff: All checks passed
- pytest: 132 passed
- app: import ok, 7 routes

## Next Milestone

R3: Reference Network and Relationship Mapping
