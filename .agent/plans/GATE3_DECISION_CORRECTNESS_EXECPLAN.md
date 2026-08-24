# Gate 3: Decision Correctness — Status Unification + Run Persistence — ExecPlan

## 1. Goal

1. Optimizers emit `StatusKind` ontology values (SUCCESS/PARTIAL/BLOCKED) so
   result semantics are single-sourced (resource pool + route optimizer).
2. Every `/api/optimization/*` run persists an immutable input/output snapshot
   (`optimization_runs`) and returns `run_id`; new evidence endpoints
   `GET /api/optimization/runs/{run_id}` allow reconstructing what was decided.
3. Optimization requests carry `decision_context` (SANDBOX_SCENARIO default;
   RUNTIME_DECISION documented as DB-snapshot-only in a later milestone).

## 2. Non-goals

- DB-snapshot-driven runtime optimizer inputs (next Gate 3 milestone).
- LP replacement of remaining heuristics (capacity/contract optimizers already
  exact for their linear models).

## 3. Product boundary

Decision support only; persisted runs are read-only evidence, no execution.

## 4. Files

Create:
- `src/eurogas_nexus/db/models/optimization.py` (OptimizationRunRecord)
- `src/eurogas_nexus/db/repositories/optimization.py`
- `tests/unit/test_optimization_runs_repository.py`
- `tests/api/test_optimization_runs_api.py`

Modify:
- `src/eurogas_nexus/api/routes/public/optimization.py`
- `src/eurogas_nexus/domain/route_cost/resource_pool.py`
- `src/eurogas_nexus/domain/route_cost/route_optimizer.py`
- `src/eurogas_nexus/db/registry.py`, `src/eurogas_nexus/db/models/__init__.py`

## 5. Dependency policy

No new dependencies.

## 6. Data policy

Input snapshot stores only what the client sent (operator-input); no secrets.
Source refs recorded from the optimizer result.

## 7. API impact

- Responses gain `run_id` and `decision_context` in meta.
- `GET /api/optimization/runs/{run_id}` returns the persisted run (404 when
  unknown or DB not configured).

## 8. DB impact

Migration 0019 (same revision as Gate 2) adds `optimization_runs`.

## 9. Tests

- Repository round-trip on SQLite.
- API persists and retrieves a run; BLOCKED runs persist with status.
- Resource pool and route optimizer status values equal StatusKind values.

## 10. Validation

```powershell
ruff check .
pytest -q tests/api tests/unit tests/optimization
```

## 11. Acceptance criteria

- All four optimization endpoints return `run_id` and persist snapshots.
- Evidence endpoint returns input+output+status+warnings.
- No `status` string diverges from `StatusKind`.

## 12. Rollback

Revert commits; migration downgrade drops `optimization_runs`.
