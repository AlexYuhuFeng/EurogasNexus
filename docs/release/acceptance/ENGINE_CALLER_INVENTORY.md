# Engine replacement caller inventory

Inspected 2026-10-12 against the current working tree. This is static call-path
evidence, not engine acceptance or proof of every dynamic invocation.

| Caller | Current destination | Acceptance implication |
| --- | --- | --- |
| Public strategy registry run route | `execute_backtest_run` in `application/backtest_service.py` | Shared service requires a frozen strategy, historical period and declared per-leg evidence targets, then calls `run_target_backtest`. |
| Agent research backtest capability | Same application service | Service refusal is returned as a blocked capability result; caller identity is passed as principal. Actual negative-permission and successful UI journeys still require evidence. |
| Experiment-linked run | Same service, optional `experiment_id` | Service verifies experiment ownership by strategy and appends the resulting run; this is not a separate engine. Actual experiment workflow remains unverified by this inventory. |
| `scripts/ops/backtest_benchmark.py` | Legacy `run_backtest` | Development benchmark remains a legacy caller. Its performance/Golden evidence must not be presented as target-engine evidence. |
| Public research `/backtest` route | `domain.research.backtest.compute_backtest` | Computes metrics from caller-supplied historical trades; does not dispatch the target evidence-selection engine. Naming alone is not proof of a second production strategy engine. Its separate purpose must be clear to users and clients. |

Search scope: Python sources under `src`, `apps`, `scripts`, `packages`, looking
for `run_backtest(`, `run_target_backtest(` and `execute_backtest_run(`. No other
direct call sites for these names were returned. Aliased, indirect and external
SDK consumers are not ruled out by this text search.

The target service already persists the target engine version in both manifest
and run metadata. This does **not** close the owner's replacement requirement:
target numerical/business acceptance, the remaining delivery-tenor cases,
real-source input qualification, agent/experiment workflows and historical
record compatibility still need verification. Do not delete historical results
or silently relabel legacy runs. See [target engine evidence](10_TARGET_ENGINE2_RECHECK.md).

Contract lifecycle is a separate unresolved gate: current create/edit capture
and optimistic token handling do not implement retirement. The existing
[contract plan](../../engineering/CONTRACT_PAYMENT_INTEGRATION_PLAN.md) requires
auditable retirement rather than hard deletion, with preserved cited revisions.
Hub, Pipeline Tender and LNG workflows each need lifecycle and reference-use
tests; the prior Pipeline Import create/edit run alone is insufficient.
