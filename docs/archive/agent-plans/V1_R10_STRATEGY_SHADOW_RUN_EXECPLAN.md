# V1 R10 Strategy Backtest and Shadow Run ExecPlan

**Goal:** Implement strategy backtest metrics computation and shadow-run evaluation.

**Architecture:** Backend workflows layer; calls no external services.

**Tech Stack:** Python dataclasses only.

---

## Milestone ID

`R10`

## Status

`complete`

## Goal

Compute backtest metrics (total return, win/loss, Sharpe, max drawdown) from
trade PnL history. Evaluate shadow-run paper-trading signals with research-only
action semantics (research_candidate, candidate_ranking, research_signal,
candidate_action_for_review).

## Non-goals

- No live execution, orders, or trades.
- No DB persistence.

## Files

- `src/eurogas_nexus/workflows/backtest.py` — compute_backtest, BacktestInput, BacktestOutput
- `src/eurogas_nexus/workflows/shadow_run.py` — evaluate_shadow_run, ShadowRunInput, ShadowRunOutput
- `src/eurogas_nexus/api/routes/v1/research.py` — +2 POST endpoints
- `tests/workflows/test_backtest.py`
- `tests/workflows/test_shadow_run.py`

## Validation

- ruff: All checks passed
- pytest: 282 passed
- app: 52 routes

## Rollback

Revert backtest.py, shadow_run.py, API endpoint additions, and tests.
