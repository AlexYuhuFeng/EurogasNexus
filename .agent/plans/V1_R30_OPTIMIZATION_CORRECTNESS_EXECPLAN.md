# Optimization Correctness And Release-Gate ExecPlan

## 1. Goal

Correct the newly merged natural-gas optimization layer and restore a reliable
release gate. The repository must not publish a route-allocation result as
optimal when the underlying greedy network-flow algorithm is only locally
optimal, and all optimization tests must run in normal CI and release
validation.

## 2. Non-goals

- No trade execution, order routing, nomination submission, capacity booking,
  settlement, approval, or ETRM behavior.
- No hydraulic or pressure-flow simulation.
- No multi-commodity model and no non-natural-gas commodity abstractions.
- No new optimization-solver dependency.
- No database migration or UI redesign.
- No automatic external-source calls in tests.

## 3. Product Boundary

The optimization package remains deterministic trader-reviewed decision
support. Results must retain `human_review_required=True`. Optimization API
responses must use the repository's standard `data` and `meta` envelope and
identify operator-supplied input as their source.

## 4. Files To Create Or Modify

- `src/eurogas_nexus/optimization/network_flow.py`
- `src/eurogas_nexus/optimization/storage.py` when validation defects are
  confirmed by focused tests
- `src/eurogas_nexus/optimization/nomination.py` when validation defects are
  confirmed by focused tests
- `src/eurogas_nexus/api/routes/public/optimization.py`
- `tests/optimization/`
- `tests/api/test_optimization_routes.py`
- `.github/workflows/ci.yml`
- `.github/workflows/release.yml`
- validation scripts and their command-contract documentation/tests
- `docs/architecture/PHASE_TWO_OPTIMIZATION.md`

## 5. Dependency Policy

Use the Python standard library and existing project dependencies only. Do not
add HiGHS, OR-Tools, SCIP, Gurobi, PuLP, NetworkX, or another solver/runtime
dependency in this increment.

## 6. Data Policy

All test inputs are small synthetic graphs. No vendor data, customer portfolio,
credential, API key, or live infrastructure value is added. The optimizer
continues to accept backend-derived or operator-provided values and does not
fabricate missing capacity or tariffs.

## 7. API Impact

Keep the existing `/api/optimization/*` paths. Change their recently introduced
raw payloads to the repository-standard response envelope:

```json
{
  "data": {},
  "meta": {
    "research_only": true,
    "human_review_required": true,
    "source_references": ["operator-input"],
    "warnings": []
  }
}
```

This correction is made before an SDK or client contract adopts the raw shape.

## 8. DB Impact

None. No migration is required. Optimization remains import-safe and performs
no database or network I/O during import.

## 9. Tests

- A reverse-residual regression where the previous greedy allocation serves
  less volume and earns a lower objective.
- Shared-edge capacity, TSO access, negative-margin, zero-margin, duplicate-ID,
  finite-number, conservation, accounting, and input-order determinism tests.
- Focused validation tests for storage and nomination prototypes where defects
  are corrected.
- API envelope and metadata tests.
- Contract tests proving `tests/optimization` is present in every standard
  validation command.
- Workflow contract coverage for retrying Linux package installation.

## 10. Validation Commands

```powershell
ruff check .
pytest -q tests/optimization tests/api/test_optimization_routes.py
pytest -q tests/api tests/contract tests/integration tests/ingestion tests/unit tests/optimization tests/sdk tests/cli tests/release tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
npm --prefix clients/web run build
```

PowerShell and shell release scripts must also parse successfully. The GitHub
Actions run is the authority for Windows, Linux x64, and Linux ARM64 packaging.

## 11. Acceptance Criteria

1. Network flow uses forward and reverse residual arcs.
2. A prior allocation can be cancelled and rerouted.
3. Final edge flows respect capacities and node conservation.
4. Final cost/objective accounting is recomputed from final net flows.
5. Invalid identifiers, negative quantities/capacities, and non-finite numbers
   fail explicitly.
6. Optimization API responses match the repository envelope contract.
7. Storage/nomination prototype status is documented accurately; neither is
   falsely advertised as an exposed stable API.
8. `tests/optimization` runs in CI, release validation, local scripts, README,
   and the testing contract.
9. Linux dependency installation retries transient package-source failures.
10. Local acceptance and the resulting remote CI/release run pass.

## 12. Rollback Notes

The correction is isolated to optimization code/tests, response wrapping,
validation commands, documentation, and workflow resilience. Revert the single
focused commit to restore the previous behavior. No database rollback is
needed.
