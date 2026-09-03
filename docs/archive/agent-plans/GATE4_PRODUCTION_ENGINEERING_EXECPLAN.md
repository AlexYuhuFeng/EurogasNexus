# Gate 4: Production Data & Release Engineering — ExecPlan (this round)

## 1. Goal

1. CI gains a real PostgreSQL job (service container + alembic upgrade + DB
   integration tests + DB-backed API smoke test).
2. CLI returns non-zero exit codes for BLOCKED/error outcomes (audit item 8).
3. Web gas-day window uses the CAM boundary (04:00 UTC winter / 03:00 UTC DST)
   instead of 00:00 UTC (audit Gate-0 GasDay item, web side).
4. Web workspace first load no longer fails wholesale: each endpoint loads
   independently with per-endpoint retry and error surfacing (audit item 6).

## 2. Non-goals

- Dependency lockfile generation (needs network/pip; separate milestone).
- Backup/restore drills, load/perf testing, CVE/license scanning in this round.
- Desktop installer end-to-end testing.

## 3. Product boundary

Engineering/QA only; no product behavior changes beyond honest statuses.

## 4. Files

Create:
- `scripts/ci/run_postgres_ci.sh` (alembic upgrade + targeted tests)

Modify:
- `.github/workflows/ci.yml` (postgres job)
- `src/eurogas_nexus/cli/main.py` (exit codes)
- `clients/web/src/app/tradingContext.ts` (CAM gas-day boundary)
- `clients/web/src/stores/api.ts` (independent endpoint loading + retry)
- `clients/web/src/app/shell/AppShell.tsx` (failed-endpoint banner/retry)
- `tests/cli/test_main.py`, `tests/contract/test_web_client_structure.py` if needed

## 5. Dependency policy

No new runtime dependencies. CI uses GitHub Actions postgres service.

## 6. Data policy

CI postgres is ephemeral; seeded only by alembic + test fixtures.

## 7. API impact

None (web-only + CLI exit codes).

## 8. DB impact

None beyond existing migrations (CI runs `alembic upgrade head`).

## 9. Tests

- CLI: BLOCKED envelope -> exit 1; exception -> exit 2; success -> 0.
- Web: `tsc --noEmit`; gas-day helper unit assertions in TS (no runner — inline
  sanity via tsc and structure test).
- CI: workflow yaml validated by structure test.

## 10. Validation

```powershell
ruff check .
pytest -q tests/cli tests/contract
cd clients/web && node .\node_modules\typescript\bin\tsc --noEmit
```

## 11. Acceptance criteria

- CI has a job named `integration-postgres` that runs migrations and DB tests
  against PostgreSQL 16.
- `eurogas-nexus route-cost` exits 1 when the result is BLOCKED.
- Web gas-day matching uses 04:00/03:00 UTC boundaries.
- One failing endpoint no longer blanks the whole workspace; failed endpoints
  are listed with a retry action.

## 12. Rollback

Web/CLI changes revert cleanly; CI job removal restores prior pipeline.
