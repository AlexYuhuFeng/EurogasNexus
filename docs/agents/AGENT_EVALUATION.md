# Agent Evaluation (CR-15)

Deterministic business-task suite: `tests/evals/agent_task_evals.json` and
`tests/evals/test_agent_evals.py`.

## Coverage

30 cases spanning market, network, capacity, portfolio, route, strategy,
backtest, dataset, and adversarial security. Each case asserts required
semantic capabilities exist and forbidden execution/SQL tools never exist.

## Scoring dimensions

- correct tool selection and order contract;
- unit/determinism metadata;
- source/freshness/provenance contract;
- entitlement fail-closed behavior;
- blocked-route and missing-data refusal;
- prompt-injection safety;
- no hallucinated numerical tool.

Live LLM scoring remains out of scope until a provider is provisioned; the
suite is the contract future model upgrades must pass.
