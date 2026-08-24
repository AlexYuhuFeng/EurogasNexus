# R33: Production Source Operations ExecPlan

## 1. Goal

Add production-shaped source-operation controls to the public ingestion
worker: explicit retry/backoff policy, bounded timeouts, freshness-SLA
evaluation, and operator diagnostics. No client may call a provider directly.

## 2. Non-goals

- No Kafka/Redis/Celery scheduler.
- No new provider dependencies or live provider calls in tests.
- No replacement of the OS/deployment scheduler; the worker remains an
  operator-invoked recurring process.
- No commercial-provider production run without credentials and certification.

## 3. Product boundary

`src/eurogas_nexus/application/source_operations.py` is the single policy
module. `scripts/ops/run_public_ingestion_worker.py` consumes it. Source
Center diagnostics remain the operator view.

## 4. Files to create/modify

Create:

- `src/eurogas_nexus/application/source_operations.py`
- `tests/unit/test_source_operations.py`
- `docs/operations/PRODUCTION_SOURCE_OPERATIONS.md` and `-CN.md`

Modify:

- `scripts/ops/run_public_ingestion_worker.py`
- `tests/unit/test_public_ingestion_worker.py`
- `docs/architecture/NEXT_DEVELOPMENT_QUEUE*.md`
- `docs/architecture/CURRENT_PAUSE_POINT*.md`

## 5. Dependency policy

Standard library + existing stack only. Sleep/clock are injected for tests.

## 6. Data policy

Public sources only for automated runs. Each attempt appends or reuses the
existing `ingestion_runs` row written by `ingest_public_sources.py`; this
module does not write business rows.

## 7. API impact

None. Public path count remains 92.

## 8. DB impact

None.

## 9. Tests

- Retry succeeds on second attempt and stops at max.
- Failure preserves source supervision.
- Backoff sequence uses injected sleep.
- Freshness SLA returns live/stale/unknown.
- Worker passes retry arguments to the policy runner.
- Import-safety remains unchanged.

## 10. Validation commands

```powershell
ruff check src tests scripts apps alembic
pytest -q tests/unit/test_source_operations.py tests/unit/test_public_ingestion_worker.py
pytest -q tests/api tests/contract tests/integration tests/ingestion tests/unit tests/optimization tests/sdk tests/cli tests/release tests/security
```

## 11. Acceptance criteria

1. Public ingestion retries transient failures with bounded backoff.
2. Source SLA freshness is evaluated from declared expectations.
3. Operator can inspect attempts/errors without client-side provider calls.
4. No new dependency or DB migration.
5. Production scheduling by a deployment supervisor is documented honestly.

## 12. Rollback notes

Revert worker and source_operations module; no DB or API rollback.
