# Risk Challenger (CR-15)

Source: `src/eurogas_nexus/domain/agents/challenge.py`.

## Structured output

`ChallengeReport` contains ordered `ChallengeItem`s: challenge, severity,
evidence, `PASS/CONCERN/FAIL/INSUFFICIENT_EVIDENCE`, recommended follow-up.
`challenge_backtest_result` performs deterministic checks for:

- insufficient sample;
- missing inputs;
- stale carry-forward warnings;
- drawdown vs net PnL;
- unmodeled transaction costs;
- crisis-period concentration.

It never emits an unqualified "looks robust" with no evidence.
