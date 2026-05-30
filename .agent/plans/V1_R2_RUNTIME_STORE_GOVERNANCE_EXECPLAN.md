# V1 R2 Runtime Store and Governance Foundation ExecPlan

## 1. Goal

Establish the repository/runtime-store contract layer and governance decision
shells that future domain milestones will use for DB-first reads and writes.
Define source reference, lineage, freshness, quality, entitlement/export, and
audit metadata contracts. Ensure no-file-fallback policy is enforceable.

## Internet Requirement

Internet required: no

Reason: This milestone uses local Python code, repository docs, and local tests.
No external documentation or live service is required.

Fallback if offline: Not needed.

## 2. Non-goals

- No market data, topology, route-cost, netback, feasibility, allocation,
  strategy, nowcast, monitoring, or reporting business features.
- No frontend, desktop, Node, Rust, Kafka, Redis, Celery, or live connector work.
- No DB schema changes or Alembic migrations (contracts/shells only).
- No new API routes.
- No live DB-dependent tests.
- No actual entitlement/license validation against real vendor terms.
- No audit event persistence (model only).

## 3. Product boundary

This milestone strengthens the runtime-store contract surface and adds governance
decision shells. PostgreSQL remains runtime truth but no new DB tables are created
in this milestone. The contracts defined here will be backed by DB tables in
later milestones (R4 ingestion, R6 governance/audit).

## 4. Files to create/modify

- `src/eurogas_nexus/runtime_store/contracts.py` — enrich with SourceReference,
  LineageRecord, DataQualityRecord, FreshnessState, and RuntimeStoreRepository
  abstract base
- `src/eurogas_nexus/governance/__init__.py` — new package exports
- `src/eurogas_nexus/governance/entitlement.py` — EntitlementDecision,
  ExportDecision, fail-closed check functions
- `src/eurogas_nexus/governance/audit.py` — AuditEvent and audit severity model
- `docs/contracts/05_RUNTIME_STORE_CONTRACT.md` — update for R2 additions
- `docs/contracts/14_GOVERNANCE_ENTITLEMENT_CONTRACT.md` — update for R2 additions
- `data/release_v1/r2_runtime_governance_report.md` — required milestone report
- `tests/contract/test_runtime_store_contracts.py` — contract tests
- `tests/contract/test_governance_foundation.py` — governance contract tests

## 5. Dependency policy

No new dependencies. Pure Python dataclasses and protocols only.

## 6. Data policy

No real data. No vendor data. No raw market data. No committed credentials.
No DB tables created. Synthetic fixtures only if needed for tests.

## 7. API impact

No new public business routes.

## 8. DB impact

No DB schema changes. No Alembic revision. No new required tables.
Runtime-store contracts remain import-safe shells.
Governance models are pure dataclass decision shells — persistence comes
in later milestones.

## 9. Tests

Required tests:

- ResultEnvelope defaults (research_only, human_review_required).
- SourceReference fields are preserved.
- LineageRecord carries source/target/timestamp/event_type.
- DataQualityRecord has severity, check_name, passed, detail fields.
- FreshnessState enum values (fresh, stale, unknown, unavailable).
- EntitlementDecision fail-closed by default.
- ExportDecision fail-closed by default.
- entitlement_check fails closed for unknown commercial data.
- export_check fails closed for unknown commercial data.
- AuditEvent has required fields (event_id, event_type, severity, timestamp).
- no_file_fallback_for_trial_or_release raises in trial/release.
- no_file_fallback_for_trial_or_release allows development/test.
- Governance package is import-safe.
- Runtime store contracts are import-safe.

## 10. Validation commands

```powershell
ruff check .
pytest -q tests/contract/test_runtime_store_contracts.py tests/contract/test_governance_foundation.py
pytest -q tests/api tests/contract tests/integration tests/security tests/sdk tests/cli
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

## 11. Acceptance criteria

- Runtime store ResultEnvelope preserves required metadata fields.
- SourceReference and LineageRecord contracts are importable and typed.
- DataQualityRecord and FreshnessState contracts exist.
- EntitlementDecision and ExportDecision fail closed by default.
- entitlement_check fails closed for unknown commercial data.
- AuditEvent model exists with severity classification.
- No-file-fallback policy is enforceable by tests.
- Governance package does not import FastAPI, web, or client code.
- Default tests remain DB-free.
- App import remains DB-connection free.
- Targeted validation passes.

## 12. Rollback notes

Revert the new governance package files, runtime_store contract additions,
contract tests, and milestone report. No DB rollback is required because
this milestone creates no tables.
