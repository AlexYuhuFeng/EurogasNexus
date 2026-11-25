# Codex to Claude handoff

**Objective:** Determine where dynamic planning adds value beyond calculations and fixed workflows, and leave an isolated, testable experiment for independent review.

**Branch:** `research/agentic-decision-architecture`, from latest fetched `origin/main` at `6d21b898661d6466418b3aaeab505a7bc4fb4013`. A separate worktree protected the prior innovation worktree. No LNG or architecture development branch was used as a dependency. The approved local DeepSeek harness was unavailable, so Codex implemented the offline experiment directly.

**Commits:** `a3d45afad2f9dff4f454f8145a979cade04b75ad` contains the experimental code, harness and tests. The documentation commit contains this handoff. Resolve that commit by running `git log -1 --format=%H -- docs/engineering/CODEX_TO_CLAUDE_HANDOFF.md`.

| Files | Review |
| --- | --- |
| `src/eurogas_nexus/application/agents/decision_research.py` | Strict synthetic route study, cost-only or route investigation dispatch, versioned evidence and time gates, invocation of two existing read-only deterministic capabilities, denial/refusal trace. |
| `scripts/research/benchmark_decision_research.py`, `tests/evals/test_decision_research.py` | Reusable synthetic fixture, A/B harness, refusal, parity, authorisation and failure checks. |
| [Architecture review](../research/AGENTISATION_ARCHITECTURE_REVIEW.md), [Proposal](../architecture/AGENTIC_DECISION_ARCHITECTURE_PROPOSAL.md), [ADR](../architecture/decisions/2026-11-25-governed-agent-research-boundary.md), [Evaluation](../research/AGENTISATION_EVALUATION_RESULTS.md) | Evidence for conclusions, integration proposal and measured limitations. |

**Interface and operations impact:** No existing interface amendments. The research module is unwired. No migration, new dependency, production configuration, permission changes, API registration or MCP export. No provider or execution path. The runtime preserves its own capability permissions and the wrapper kept all results synthetic and indicative.

**Validation:** 208 focused tests passed, including 15 new cases. A/B returned the same 1.30 EUR/MWh and scenario feasibility. Direct p50 18.09 µs, governed p50 92.34 µs. Model value and costs are unmeasured. The date/time and conflict checks consume fixture metadata, and do not certify provenance or discover source conflicts. The scenario assessment does not verify current rights, cash or actual portfolio allocation.

**Selective integration:** Consider adopting the architecture review, ADR boundaries and evaluation criteria. Leave the offline module and fixture harness experimental. Establish canonical data sourcing, scoped identity and user-authorised analytical paths before using a similar workflow live. Defer one-agent-per-cargo design, tick-path LLMs, orchestration replacement, and customer MCP exposure. Resolve missing-identity behavior and proof-of-approval separately before broadening commercial workflows.

**LNG coordination:** Retain the ongoing LNG programme's portfolio snapshot, shared-resource constraints, rights and capacity models. Integrate through a future read-only adapter around its existing service after that interface stabilises. No observed code overlap beyond relying on the existing agent runtime and route domain services.

**Review and rollback:** Compare the branch to the base SHA and run the evaluation commands. Inspect worktrees with `git worktree list`. If approved, cherry-pick the documentation or extract the evidence policy independently. The code commit can be reverted independently after integration. It carries no stored state.
