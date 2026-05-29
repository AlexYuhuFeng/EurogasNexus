# R10: Strategy Backtest and Shadow Run Report

**Milestone ID:** R10 | **Status:** COMPLETE | **Date:** 2026-05-29

## Evidence

- Strategy backtest: computes total return, win/loss counts, win rate, Sharpe
  ratio, max drawdown from trade PnL history. Reports partial/error status.
- Shadow run: evaluates paper-trading signals with paper PnL. All signals use
  research-only action semantics (research_candidate, candidate_ranking,
  research_signal, candidate_action_for_review). No execute/order/trade actions.
- 2 POST endpoints: /api/v1/research/backtest, /api/v1/research/shadow-run.

## Files

- `src/eurogas_nexus/workflows/backtest.py`
- `src/eurogas_nexus/workflows/shadow_run.py`
- `src/eurogas_nexus/api/routes/v1/research.py` — +2 endpoints
- `tests/workflows/test_backtest.py` (3)
- `tests/workflows/test_shadow_run.py` (3)

## Validation

- ruff: All checks passed
- pytest: 282 passed
- app: import ok, 52 routes

## Next: R12 SDK Release Surface
