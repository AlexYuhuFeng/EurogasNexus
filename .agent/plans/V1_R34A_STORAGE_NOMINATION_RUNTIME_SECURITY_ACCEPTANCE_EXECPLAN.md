# R34A: Storage/Nomination Runtime Composition And Security Acceptance ExecPlan

## 1. Goal

Close the R34 partial increment: compose storage dispatch and nomination-window
inputs from PostgreSQL master data for RUNTIME_DECISION, and add an automated
security-acceptance evidence script. No nomination submission action is added.

## 2. Non-goals

- No storage booking, nomination submission, approval, or execution action.
- No hydraulic/pressure simulation.
- No removal of the private-network/VPN-only deployment posture; final
  acceptance requires an operator-managed review of a real deployment.
- No OIDC login/session work (R32A covers access tokens only).

## 3. Product boundary

`POST /api/optimization/storage-dispatch` and
`POST /api/optimization/nomination-window` gain RUNTIME_DECISION when DB
masters and market/FX observations are available. Clients still cannot
fabricate facility or window parameters in RUNTIME_DECISION; nomination
instructions remain assessment inputs only.

## 4. Files to create/modify

Create:

- `alembic/versions/0023_storage_nomination_masters.py`
- `src/eurogas_nexus/db/models/storage_nomination.py`
- `src/eurogas_nexus/db/repositories/storage_nomination.py`
- `src/eurogas_nexus/application/storage_nomination_composition.py`
- `scripts/security/run_security_acceptance.py`
- `tests/unit/test_storage_nomination_composition.py`
- `tests/api/test_storage_nomination_runtime_api.py`
- `docs/release/SECURITY_ACCEPTANCE_EVIDENCE.md`
- `docs/operations/STORAGE_NOMINATION_ASSESSMENT.md` update
- `docs/operations/STORAGE_NOMINATION_ASSESSMENT-CN.md` update

Modify:

- `src/eurogas_nexus/db/models/__init__.py`
- `src/eurogas_nexus/db/registry.py`
- `src/eurogas_nexus/api/routes/public/optimization.py`
- `src/eurogas_nexus/sdk/optimization.py`
- `tests/contract/test_db_migrations_contract.py`
- `tests/contract/test_architecture_alignment.py`
- `docs/architecture/NEXT_DEVELOPMENT_QUEUE*.md`
- `docs/architecture/CURRENT_PAUSE_POINT*.md`
- `docs/release/RELEASE_READINESS.md`

## 5. Dependency policy

Existing stack only. No new Python or client dependency.

## 6. Data policy

Tests use synthetic rows marked `test_fixture:not_customer_data`. Runtime
composition reads PostgreSQL only; missing/stale facts return blockers. No
customer or live-provider data is contacted.

## 7. API impact

No new public paths. Existing two R34 paths accept RUNTIME_DECISION in an
additive request extension. Public path count remains 84.

## 8. DB impact

Migration `0023_storage_nomination_masters` adds three tables:
`storage_facility_masters`, `storage_inventory_observations`,
`nomination_window_masters`. Required table count grows 42 -> 45.

## 9. Tests

- Master composition: facility/inventory/window selection, validity windows,
  missing/stale blockers.
- Market-price conversion for dispatch periods fails closed on missing FX.
- API RUNTIME_DECISION succeeds with seeded SQLite and rejects client
  facility/window inputs.
- Security acceptance script exits 0 when all automated checks pass and writes
  a JSON report with external-review blockers.

## 10. Validation commands

```powershell
ruff check src tests scripts apps alembic
pytest -q tests/unit/test_storage_nomination_composition.py tests/api/test_storage_nomination_runtime_api.py tests/api/test_storage_nomination_workflow_api.py tests/sdk/test_storage_nomination_workflow_client.py tests/contract/test_architecture_alignment.py
python scripts/security/run_security_acceptance.py --json
pytest -q tests/api tests/contract tests/integration tests/ingestion tests/unit tests/optimization tests/sdk tests/cli tests/release tests/security
```

## 11. Acceptance criteria

1. RUNTIME_DECISION storage dispatch uses DB facility, inventory, market, and
   FX facts only.
2. RUNTIME_DECISION nomination windows use DB window masters.
3. Missing/stale/incompatible facts return explicit blockers.
4. Automated security-acceptance evidence is executable and honest:
   external/manual review remains BLOCKED.
5. Private-network/VPN-only posture is unchanged in code.

## 12. Rollback notes

Revert increment and run `alembic downgrade 0022`. No public path removal.
