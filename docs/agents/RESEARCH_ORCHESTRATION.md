# Research Orchestration (CR-15)

Source: `src/eurogas_nexus/application/agents/research_orchestrator.py`.

## State machine

`OBJECTIVE_RECEIVED -> PLAN_DRAFTED -> PLAN_VALIDATED -> DATA_ANALYSIS ->
HYPOTHESIS_FORMED -> STRATEGY_SPEC_DRAFTED -> STRATEGY_VALIDATED ->
BACKTESTED -> ROBUSTNESS_EVALUATED -> CHALLENGED ->
READY_FOR_HUMAN_REVIEW`, plus `BLOCKED`, `FAILED`, `CANCELLED`.

## Policy

- Read/analytic capabilities: `AUTO_ALLOWED`.
- Draft plan/finding/strategy/version: `AGENT_ALLOWED_WITHIN_RESEARCH`.
- Freeze StrategyVersion and Shadow start/pause/resume: `HUMAN_CONFIRMATION`.
- Review decision recording: `HUMAN_ONLY`.

## Deterministic vs LLM ownership

The orchestrator uses a deterministic planner by default. Deterministic
stages own calculations; LLM stages are isolated behind a provider
abstraction and are never used to recalculate PnL or metrics.

## Human gate

Without a pre-frozen strategy version, the pipeline terminates at
`READY_FOR_HUMAN_REVIEW` with `HUMAN_CONFIRMATION_REQUIRED` for freeze/
backtest. The API persists the run and artifacts before returning.
