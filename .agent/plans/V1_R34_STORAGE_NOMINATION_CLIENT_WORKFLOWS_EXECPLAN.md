# R34: Storage And Nomination Assessment Workflows ExecPlan

## 1. Goal

Expose the validated multi-period storage dispatch and nomination-window
prototypes through the stable API and SDK as trader-reviewed, assessment-only
workflows. No nomination or storage booking submission action exists.

## 2. Non-goals

- No nomination submission, storage booking, official approval, or execution.
- No DB-owned storage facility/nomination master in this increment; runtime
  DB composition remains a later follow-up and RUNTIME_DECISION fails closed.
- No hydraulic/pressure simulation.

## 3. Product boundary

Two additive public POST endpoints under `/api/optimization/`:

- `POST /api/optimization/storage-dispatch`
- `POST /api/optimization/nomination-window`

Both accept SANDBOX_SCENARIO only and persist immutable `optimization_runs`
evidence. Responses require human review.

## 4. Files to create/modify

Create:

- `tests/api/test_storage_nomination_workflow_api.py`
- `tests/sdk/test_storage_nomination_workflow_client.py`
- `docs/operations/STORAGE_NOMINATION_ASSESSMENT.md` and `-CN.md`

Modify:

- `src/eurogas_nexus/api/routes/public/optimization.py`
- `src/eurogas_nexus/sdk/optimization.py`
- `tests/contract/test_api_surface_stability.py`
- `tests/contract/test_sdk_backend_parity.py`
- `docs/release/PRODUCTION_READINESS_BACKLOG.md`
- `docs/architecture/CURRENT_PAUSE_POINT*.md`
- `docs/architecture/PHASE_TWO_OPTIMIZATION*.md`
- `docs/architecture/API_CONTRACT_EVOLUTION_POLICY*.md`

## 5. Dependency policy

No new dependency. Reuses the existing deterministic optimization engines.

## 6. Data policy

Sandbox operator inputs only. No customer storage or nomination data is read
from PostgreSQL in this increment; outputs are marked research_only at the
envelope and are never executable.

## 7. API impact

Additive public paths; pinned surface grows from 92 to 94. Existing paths and
field meanings are unchanged.

## 8. DB impact

No migration. Successful runs append `optimization_runs` rows when a runtime DB
is configured.

## 9. Tests

- API DTO validation and engine behavior for storage and nomination.
- RUNTIME_DECISION is rejected fail-closed for both endpoints.
- SDK methods send SANDBOX_SCENARIO and parse typed results.
- Path stability and SDK parity tests updated.

## 10. Validation commands

```powershell
ruff check src tests scripts apps alembic
pytest -q tests/api/test_storage_nomination_workflow_api.py tests/sdk/test_storage_nomination_workflow_client.py tests/optimization/test_storage_nomination.py tests/contract/test_api_surface_stability.py tests/contract/test_sdk_backend_parity.py
pytest -q tests/api tests/contract tests/integration tests/ingestion tests/unit tests/optimization tests/sdk tests/cli tests/release tests/security
```

## 11. Acceptance criteria

1. Storage dispatch and nomination-window engines are reachable through
   stable `/api/optimization/*` endpoints and SDK.
2. Nomination endpoint returns assessment decisions only; no submission verb,
   route, or action exists.
3. RUNTIME_DECISION fails closed until DB-owned storage/nomination inputs are
   delivered.
4. Results persist evidence and always require human review.
5. Public surface count and docs are updated deliberately.

## 12. Rollback notes

Remove the two routes/SDK methods and revert the pinned path set to 92. No
migration rollback.
