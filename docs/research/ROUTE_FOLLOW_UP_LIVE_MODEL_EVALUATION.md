# Route follow-up live model evaluation

> **Research record.** The experiment this describes (`application/agents/decision_research.py`,
> `route_follow_up.py`, the `scripts/research/` harnesses and `tests/evals/test_decision_research.py`)
> is on branch `research/agentic-decision-architecture` at `515f3b9` and is not on `main`; run the
> commands below from that branch.

This experiment ran real model inference locally over HTTP through the existing Nexus
chat-completions adapter. The route calculation, feasibility checks and evidence
validation used the same production engine and capability-runtime code in all arms.
All portfolios, capacity values, routes and source records were synthetic. The planner
saw only the baseline status, evidence issue classes and three candidate purpose labels
with numeric IDs. No live contracts, positions, customer data or provider credentials
were sent to the model.

## Design

The 12 controlled cases cover delivery outside the evidence window, insufficient
capacity and conflicting capacity evidence. For each failure class, three cases
put the sole viable alternative in each of the three positions. The fourth case
has no viable alternative. The cases comprise three failure classes with
counterbalanced order, so they should not be treated as twelve independent
market events.

Each arm received the same cases and used one follow-up calculation. The
fixed-order arm chose candidate 1. The purpose rule mapped the same summary
available to the model to the purpose most relevant to the baseline failure.
It was written for these fixture classes and is an in-scope deterministic
comparator. The model could choose an ID, while typed validation and the
deterministic evidence gate still decided the result. This evaluation does
not establish the rule's coverage of unseen events.

The primary metric counts how often the one selected option was actually
feasible in fixtures with a feasible option. In the three negative cases,
we count false positive feasible results. A negative result after one check
does not establish that all alternatives were infeasible.

## Environment and reproduction

- Python 3.11.12, Intel Xeon Platinum 8573C workspace, CPU inference with two threads.
- Qwen2.5 Instruct Q4_K_M GGUF via node-llama-cpp 3.22.3, loopback HTTP, context size 1024.
- Existing planner prompt version `route-follow-up/v1`, temperature 0, token cap 64,
  three-second adapter HTTP timeout. Wall times cover the full local call and gated checks.
- Model weights and adapter dependencies are external research setup. No production
  dependency, data source or service configuration changes.

```sh
python -m scripts.research.evaluate_route_follow_up
# Set the existing Nexus LLM base URL and model to your approved local endpoint.
# Provide its research credential via EUROGAS_NEXUS_LLM_API_KEY.
python -m scripts.research.evaluate_route_follow_up --live-model
python -m pytest -q tests/evals/test_decision_research.py
```

Model sources: [Qwen2.5 0.5B GGUF](https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF) and
[Qwen2.5 1.5B GGUF](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF).

## Measured results

| Arm | Feasible follow-up found | False feasible in 3 negative cases | Valid model replies | p50 / p95 wall time |
| --- | ---: | ---: | ---: | ---: |
| Fixed first, 0.5B comparison run | 3 / 9 | 0 | — | 0.178 / 0.681 ms |
| Purpose rule, 0.5B comparison run | 9 / 9 | 0 | — | 0.385 / 1.121 ms |
| Qwen2.5 0.5B | 3 / 9 | 0 | 12 / 12 | 1,157 / 1,726 ms |
| Qwen2.5 1.5B, paced after failures | 3 / 9 | 0 | 8 / 12 | 2,254 / 3,092 ms |
| HTTP connection refused | 3 / 9 | 0 | 0 / 12 | 107 / 130 ms |

All valid replies selected candidate 1 for both models. The 0.5B arm gained
zero feasible follow-ups over fixed order and found six fewer than the
purpose rule. The 1.5B arm fell back four times in the paced run. Each paced
failure took approximately 3.1 seconds. In an earlier unpaced run, the single
available inference sequence was sometimes still occupied after a timeout,
giving nine provider failures, some of them immediate HTTP 500s. The paced
run waits four seconds after a failed call, outside the measured wall times.
This distinguishes inference timeout from test-server queue contamination.
The disabled endpoint check used a real refused loopback connection and
recovered via fixed-order fallback in all twelve cases.

The local wrapper counted about 100–103 text input tokens before chat
templating and six completion tokens per completed model generation.
No remote charges were incurred. Hardware cost and human review time were
outside the experiment. The recorded latency is CPU plus local HTTP,
including prompt processing, and is not a managed provider performance estimate.

A valid JSON selection establishes only that the model complied with the tool
interface. It supplies no evidence about feasibility. Equivalent summaries can
describe a case with one viable option and a case with none. The current
prompt has no candidate-level verified findings, so this routing stage cannot
distinguish such cases before the deterministic follow-up. The safe outcomes
in the negative cases came from those existing checks.

[Per-case measurements and statuses](route_follow_up_live_results.csv)

Model file SHA-256 values:

- 0.5B: `74a4da8c9fdbcd15bd1f6d01d621410d31c6fc00986f5eb687824e7b93d7a9db`
- 1.5B: `6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e`

## Decision for Claude

Keep the follow-up model path experimental. The model integration exercised
schema validation and fallback over real HTTP, and preserved the deterministic
feasibility boundary. Those are integration benefits. For these known failure
classes, selection should use deterministic rules. When the candidate set is small
and calculations are cheap, also compare direct evaluation of every candidate in
the next iteration. That removes the need to guess from labels.

Before considering adoption for unfamiliar events, curate held-out cases using
approved evidence, make the permitted summaries rich enough to distinguish the
candidate facts, and compare against the best deterministic workflow with an
equal calculation budget. Count validated alternatives found, false executable
claims, total latency and reviewer work. This pilot does not cover open-ended
research, model discovery of new scenarios, production concurrency, customer
data, or analyst time savings. The 3-second behavior applies to this HTTP adapter
and host, rather than a universal inference deadline.
