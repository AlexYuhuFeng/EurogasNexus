# R31-Strategy: Shadow-Run Persistence And Correctness ExecPlan

## 1. Goal

Make the Strategy Lab shadow-run evaluation a DB-backed, accumulating paper
evaluation instead of a stateless one-shot computation, and correct the
low-frequency day-ahead versus intraday shadow-run semantics.

Concretely:

- Persist every `POST /api/strategy-lab/evaluate` result to the existing
  `strategy_runs` and `strategy_allocation_targets` tables.
- Expose read-only run history and a cumulative performance summary (paper PnL,
  hit rate, max drawdown, run count, time span).
- Correct the low-frequency shadow-run logic: cumulative stop-loss accounting,
  honest `PARTIAL` candidate action, and legacy `elapsed_days` semantics.
- Wire SDK, CLI, and Web so risk controls are editable, cumulative PnL feeds
  back into the next evaluation, and run history / performance are visible.

## 2. Non-goals

- No background/daemon shadow-run worker (on-demand accumulation only).
- No high-frequency/tick-level engine, order book, or microstructure signals.
- No live execution, order entry, nomination submission, or trade capture.
- No client-side PostgreSQL access or backend file reads.
- No new strategy component types beyond the existing enum.
- No CLI `strategy-evaluate` POST command (scenario JSON body entry is out of
  scope; the SDK evaluate method remains the programmatic path).

## 3. Product boundary

Shadow runs remain research-only paper evaluations requiring human review. The
only change is that evaluations now persist and accumulate in PostgreSQL, which
is already the runtime source of truth. Outputs stay non-executable.

## 4. Files to create/modify

- Modify `src/eurogas_nexus/domain/strategy_lab/evaluation.py`
  - Add `paper_pnl_gbp`, `cumulative_pnl_gbp`, `hit` to `StrategyLabResult`.
  - Compute paper PnL from allocation targets; cumulative = existing + paper.
  - Cumulative stop-loss check; `REVIEW_PARTIAL_STRATEGY` candidate action.
- Create `src/eurogas_nexus/db/repositories/strategy.py`
  - `persist_strategy_run`, `list_strategy_runs`, `get_strategy_run`,
    `strategy_summary`, `strategy_run_payload`.
- Modify `src/eurogas_nexus/api/routes/public/strategy_lab.py`
  - Persist on evaluate (graceful, warning on failure), add `run_id` to data.
  - Add `GET /api/strategy-lab/runs`, `GET /api/strategy-lab/runs/{run_id}`,
    `GET /api/strategy-lab/summary`.
- Modify `src/eurogas_nexus/sdk/strategy_lab.py`
  - Add `StrategyRunDTO`, `StrategySummaryDTO`; add list/get/summary methods.
  - Add `run_id`/`paper_pnl_gbp`/`cumulative_pnl_gbp`/`hit` to `StrategyLabResult`.
- Modify `src/eurogas_nexus/cli/main.py`, `src/eurogas_nexus/cli/commands.py`
  - Add `strategy-runs`, `strategy-summary` commands.
- Modify `clients/web/src/api/client.ts`
  - Add DTOs and `strategyRuns`/`strategyRun`/`strategySummary` methods.
- Modify `clients/web/src/stores/api.ts`
  - Add `strategyRuns`/`strategySummary` state and fetch actions; refresh
    summary after evaluate.
- Modify `clients/web/src/app/model/usePortfolioDecisionModel.ts`
  - Expose `strategySummary` and `strategyRuns`.
- Modify `clients/web/src/app/workspaces/WorkspaceRenderer.tsx`
  - Pass summary/history and an override-aware `onEvaluate`.
- Modify `clients/web/src/components/StrategyShadowRunTerminal.tsx`
  - Editable risk controls, cumulative PnL / hit rate / drawdown display,
    run-history table.
- Modify `clients/web/src/i18n/en.json`, `clients/web/src/i18n/zh.json`
  - New labels for cumulative metrics, history, editable controls.
- Modify tests:
  - `tests/unit/test_strategy_lab_evaluation.py`
  - `tests/workflows/test_shadow_run.py` (if `elapsed_days` semantics change)
  - `tests/api/test_strategy_lab_api.py` (new)
  - `tests/contract/test_strategy_db_models.py` (extend if needed)
  - `tests/sdk/test_strategy_lab.py` (new)
  - `tests/cli/test_cli.py` (extend)
- Modify docs:
  - `docs/architecture/CURRENT_PAUSE_POINT.md`
  - `docs/architecture/NEXT_DEVELOPMENT_QUEUE.md`

## 5. Dependency policy

No new dependencies. Uses the allowed stack (FastAPI, Pydantic, SQLAlchemy,
httpx, pytest). No GPL/AGPL/SSPL/BUSL/Redis-RSAL/Commons-Clause/PolyForm.

## 6. Data policy

- Runtime truth stays in PostgreSQL. Persisted shadow-run rows are runtime data.
- DB unavailability never blocks the paper evaluation: the result is returned
  with an explicit `STRATEGY_RUN_NOT_PERSISTED` warning (no silent fallback).
- No local file fallback for runtime data.
- `paper_pnl_gbp` is an indicative single-gas-day estimate
  (`sum(expected_margin * target_quantity)`) and is labeled an assumption.

## 7. API impact

- `POST /api/strategy-lab/evaluate`: response data gains `run_id`,
  `paper_pnl_gbp`, `cumulative_pnl_gbp`, `hit`; result is persisted.
- New `GET /api/strategy-lab/runs`, `GET /api/strategy-lab/runs/{run_id}`,
  `GET /api/strategy-lab/summary`.
- Public unversioned `/api` prefix preserved; no `/v1` aliases.

## 8. DB impact

- No migration required: `strategy_runs` and `strategy_allocation_targets`
  already exist (`0007_strategy_lab_foundation`) and are currently write-less.
- This increment starts writing to them via a repository boundary.

## 9. Tests

- Unit: paper PnL computation, cumulative stop-loss, PARTIAL candidate action,
  hit flag.
- Workflow: legacy shadow-run `elapsed_days` corrected.
- API: evaluate persists (with mocked session), runs/summary read endpoints,
  graceful DB-unavailable warning.
- SDK: list/get/summary client methods.
- CLI: new commands serialize correctly.
- Contract: schema tables and client release surface unchanged/updated.

## 10. Validation commands

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/ingestion tests/unit tests/optimization tests/sdk tests/cli tests/release tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
npm --prefix clients/web run build
```

## 11. Acceptance criteria

- Evaluating a shadow run persists a `strategy_runs` row and allocation targets
  when the runtime DB is available.
- Summary returns cumulative paper PnL, hit rate, max drawdown, run count, and
  time span from persisted rows.
- Stop-loss triggers against cumulative (existing + this run) PnL.
- `PARTIAL` results report `REVIEW_PARTIAL_STRATEGY`, not a positive allocation
  recommendation.
- Legacy shadow-run `elapsed_days` reflects time, not signal count.
- Web allows editing risk controls and shows history/cumulative metrics.
- All validation commands pass; API import stays safe (no socket/DB on import).

## 12. Rollback notes

- No schema change, so no Alembic downgrade is required.
- The strategy-lab evaluate endpoint remains backward-compatible (same request
  shape); new fields are additive on the response.
- Repositories are import-safe; removal only requires deleting the new route
  and SDK/CLI wiring.
