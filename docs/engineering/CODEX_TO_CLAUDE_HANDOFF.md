> **Research record (2026-11-26).** The handoff of branch `research/agentic-decision-architecture`
> (`515f3b9`). Its verdicts are in
> [Commercial-Intelligence-V3/18](Commercial-Intelligence-V3/18_CODEX_ASSESSMENT_REVIEW.md): the
> documents are on this branch; the experiment (`application/agents/decision_research.py`,
> `route_follow_up.py`, the two `scripts/research/` harnesses and `tests/evals/test_decision_research.py`)
> stays on the research branch. Its 23 tests pass against this branch's agent runtime (checked
> 2026-11-26); taking it in would need it moved out of the product package, without the
> `IngestionInvalidationV1` wiring of `opportunities/schedule.py`.

# Codex to Claude handoff

**Objective:** Determine where dynamic planning adds value beyond calculations and fixed workflows, and leave an isolated, testable experiment for independent review.

**Branch:** `research/agentic-decision-architecture`, from latest fetched `origin/main` at `6d21b898661d6466418b3aaeab505a7bc4fb4013`. A separate worktree protected the prior innovation worktree. No LNG or architecture development branch was used as a dependency. The approved local DeepSeek harness was unavailable, so Codex implemented the offline experiment directly.

**Commits:** `a3d45afad2f9dff4f454f8145a979cade04b75ad` contains the experimental code, harness and tests. The documentation commit contains this handoff. Resolve that commit by running `git log -1 --format=%H -- docs/engineering/CODEX_TO_CLAUDE_HANDOFF.md`.

| Files | Review |
| --- | --- |
| `src/eurogas_nexus/application/agents/decision_research.py` | Strict synthetic route study, cost-only or route investigation dispatch, versioned evidence and time gates, invocation of two existing read-only deterministic capabilities, denial/refusal trace. |
| `scripts/research/benchmark_decision_research.py`, `tests/evals/test_decision_research.py` | Reusable synthetic fixture, A/B harness, refusal, parity, authorisation and failure checks. |
| [Architecture review](../research/AGENTISATION_ARCHITECTURE_REVIEW.md), [Proposal](../architecture/AGENTIC_DECISION_ARCHITECTURE_PROPOSAL.md), [ADR](../architecture/decisions/2026-11-25-governed-agent-research-boundary.md), [Evaluation](../research/AGENTISATION_EVALUATION_RESULTS.md) | Evidence for conclusions, integration proposal and measured limitations. |

**Interface and operations impact:** No public interface amendments. The research module is unwired. No migration, new dependency, production configuration, permission changes, API registration or MCP export. No provider or execution path. The runtime preserves its own capability permissions and the wrapper kept all results synthetic and indicative.

**Validation:** 208 focused tests passed, including 15 new cases. A/B returned the same 1.30 EUR/MWh and scenario feasibility. Direct p50 18.09 µs, governed p50 92.34 µs. Model value and costs are unmeasured. The date/time and conflict checks consume fixture metadata, and do not certify provenance or discover source conflicts. The scenario assessment does not verify current rights, cash or actual portfolio allocation.

**Selective integration:** Consider adopting the architecture review, ADR boundaries and evaluation criteria. Leave the offline module and fixture harness experimental. Establish canonical data sourcing, scoped identity and user-authorised analytical paths before using a similar workflow live. Defer one-agent-per-cargo design, tick-path LLMs, orchestration replacement, and customer MCP exposure. Resolve missing-identity behavior and proof-of-approval separately before broadening commercial workflows.

**LNG coordination:** Retain the ongoing LNG programme's portfolio snapshot, shared-resource constraints, rights and capacity models. Integrate through a future read-only adapter around its existing service after that interface stabilises. No observed code overlap beyond relying on the existing agent runtime and route domain services.

**Review and rollback:** Compare the branch to the base SHA and run the evaluation commands. Inspect worktrees with `git worktree list`. If approved, cherry-pick the documentation or extract the evidence policy independently. The code commit can be reverted independently after integration. It carries no stored state.


**Foundational follow-up:** The typed v1 invalidation contract and scheduler consumer
are in `src/eurogas_nexus/streaming/contracts.py` and
`src/eurogas_nexus/application/opportunities/schedule.py`, with JSON fixtures in
`tests/contract/test_ingestion_invalidation_contract.py`. Review this separately
from the research module. It preserves existing debounce and database shape.
The lifecycle proposal records licensing, upgrade and rollback considerations
for each infrastructure candidate. No new optional deployment profile is proposed.
Review `git log --oneline origin/main..HEAD` for the foundational follow-up SHA.

## Follow-up planner component

`application/agents/route_follow_up.py` implements one optional plan choice after
a baseline route investigation. The caller supplies one to three complete
synthetic scenarios using a shared cutoff. The provider receives generated IDs,
purpose enums and baseline status codes. Its reply can select one ID. The chosen
scenario runs through the same runtime, authority checks and evidence gates.
A disabled or unavailable provider, out-of-range ID or malformed reply takes
the first alternative in the caller's fixed order. A blocked baseline ends
the investigation. The existing approved adapter enforces the installation
profile and is called with a 64-token output cap and a three-second HTTP
timeout. Planner latency and branch status appear in the result.

Run the fixed workflow locally with
`python -m scripts.research.benchmark_decision_research --follow-up`.
On a permitted installation, append `--provider` to compare the single-choice
model path on the identical synthetic scenario. The harness prompts for an
approved key. Tests cover controlled responses, timeout, malformed/overreaching
replies and permission denial. Live provider usefulness and commercial
validation remain unmeasured. Keep the component offline during review.

## Live model evidence

The follow-up planner has now run against two local Qwen models through the
actual HTTP adapter. Both matched fixed-order selection at 3 of 9 feasible
cases. The fixture-specific deterministic purpose rule found 9 of 9. The
models added seconds of latency, and the larger one also hit timeouts.
Retain the evidence gates and optional research harness. Leave model-based
routing disabled unless a held-out evaluation establishes incremental value.
[Protocol, results and raw case data](../research/ROUTE_FOLLOW_UP_LIVE_MODEL_EVALUATION.md)
