# Agentisation evaluation results

> **Research record.** The experiment this describes (`application/agents/decision_research.py`,
> `route_follow_up.py`, the `scripts/research/` harnesses and `tests/evals/test_decision_research.py`)
> is on branch `research/agentic-decision-architecture` at `515f3b9` and is not on `main`; run the
> commands below from that branch.

## Measured comparison

Python 3.12.14 with hash-pinned repository dependencies, in-process workspace benchmark, 3,000 interleaved iterations after 30 warm-ups per operation. All inputs are synthetic. A and B use the same two engines and typed route inputs. Both return 1.30 EUR/MWh and feasible for the supplied scenario. B reports indicative evidence and commercial status `NOT_ASSESSED`.

| Path | p50 µs | p95 µs | Scope |
| --- | ---: | ---: | --- |
| A direct engines | 18.09 | 29.61 | Cost and feasibility, no evidence or authorisation wrapper |
| B evidence-gated workflow | 92.34 | 191.48 | Typed inputs, evidence validation, capability checks and traces |
| B with request validation | 113.38 | 233.77 | Also parses the local fixture payload |
| C agent-assisted | — | — | No provider or planner evaluated |

Measured B overhead at the median was about 74 µs relative to A. These are local orchestration measurements. They exclude process startup, ingestion, network I/O, database work, queues, portfolio optimisation, model latency and trader review. No operational SLA, cost saving or trading uplift can be derived. Provider calls and token spend were zero by design. Event detection, first operational response, final recommendation and analyst time require a representative workload.

```sh
python -m scripts.research.benchmark_decision_research --iterations 3000
python -m pytest -q tests/evals/test_decision_research.py
```

## Scenario coverage

| Case | Result and coverage |
| --- | --- |
| LNG quantity and energy | Existing cargo golden suite ran and validates delivered-energy and cost chain. Outside the new route workflow. |
| Pipeline transportation cost | A/B comparison on identical normalised tariff and fuel components. Dedicated production route-cost regression also ran. Unsupported FX inputs are rejected at the prototype boundary. |
| Standard cargo P&L | Existing LNG golden and integration suites ran. No new cross-path comparison or portfolio P&L claim. |
| ETA delayed by 48 hours | Synthetic delivery timestamp moves outside the evidence window; B refuses dependent results. Vessel ingestion and terminal rebooking are outside the spike. |
| Insufficient Storage or Send-out | B detects insufficient route capacity in the fixture. Actual storage and terminal Send-out readiness are different constraints and remain future integrated evaluations. |
| Two cargoes share limits | Existing resource pool and network solver suites ran on their allocation fixtures. This does not establish multi-cargo berth and storage optimisation. |
| Market event affects an open exposure | Opportunity scheduling regression ran. Event-to-exposure investigation and economics were not benchmarked. |
| Contract term requires verification | Missing contract state produces unknown; explicit inactive synthetic input reaches the engine and produces scenario infeasibility. Clause extraction and human validation were not exercised. |
| Missing or stale market data | Missing costs and unavailable/expired capacity evidence produce unknown without tool calls. Licensed quote freshness was outside the spike. |
| Conflicting capacity | Explicit conflict is retained and produces no calculation. Automated conflict discovery was outside the spike. |
| Malicious external instructions | Unknown free-text field is rejected and no provider runs. This is schema isolation, not an end-to-end prompt-injection evaluation. |
| Provider unavailable or call timed out | An injected registered tool timeout yields a blocked trace and no partial result. A malformed tool result is refused. No model provider or cancellation benchmark was run. |

The spike tests default authority, provenance and replay of input fingerprints, refusal for incomplete evidence, the runtime permission denial (viewer), and deterministic parity. The selected capabilities consume synthetic arguments and declare no licensed-source policy. Existing Runtime and MCP tests exercise governance paths; this spike does not establish commercial data entitlement for a live route integration.

Focused suites passed **208 tests** including 15 new cases, registry/runtime, MCP deployment and adapter, agent persistence/orchestration behavior, agent API/profile behavior, route cost, LNG golden and integration, resource pool, network optimiser and opportunity scheduling. Ruff and Markdown link checks were run locally. Hosted baseline validation was red in Python Tests and browser acceptance. [Baseline hosted run](https://github.com/AlexYuhuFeng/EurogasNexus/actions/runs/44718356229)

## Next comparative trial

Freeze authorised source, input and portfolio snapshot IDs for an analyst-reviewed held-out set of novel investigations. Run A with direct engines, B with the best explicit checklist and C with a single capped plan proposal followed by the same B gates and tools. Give each path equivalent data and available calculations. Permute presentation order and blind reviewers. Score evidence-supported conclusions, recall of commercially material alternatives, critical false positives, time to first feasible and quantitative answer, total resolution time, human corrections, external processing eligibility and actual token/cost. Retain refusals, injected timeout, missing-data and untrusted-document cases. Gate any rollout on zero critical false executable claims in the acceptance set and measurable improvement over B on analyst time or validated alternative discovery. Artifact should include case IDs, versioned expected evidence, prompt/model version and timings. Provider-dependent C and its commercial benchmark remain unmeasured.
