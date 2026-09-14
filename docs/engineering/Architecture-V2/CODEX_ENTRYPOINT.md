# AUTONOMOUS MODE OVERRIDE

`AUTONOMOUS_EXECUTION_POLICY.md` is the highest operational authority for this programme.

Any older instruction in this pack requiring human approval, human review, STOP at a wave
boundary, or approval before superseding an ADR is superseded by the Autonomous Execution Policy.

Architecture conflicts SHALL be resolved automatically according to its authority hierarchy.

Do not request human approval for normal Architecture V2 execution.

---

# CODEX ENTRYPOINT — Autonomous Architecture V2 Programme

Use this file as the **single entrypoint** when handing the Eurogas Nexus Architecture V2 pack
to Codex / GPT-6 Astra.

## Operating thesis

GPT-6 Astra is the **architect / planner / integrator**, not the default implementation worker.

DeepSeek Flash V4.1, accessed through **DeepSeek Harness Desktop** or another approved DeepSeek
execution path, is the **primary implementation worker** and should perform as much routine and
bounded development work as possible.

The objective is to minimise expensive Astra usage while preserving architecture consistency.

The programme should run as a sequence of small, validated, resumable work units rather than one
large implementation attempt.

## Authority

Read the V2 documents in numerical order, then read:

1. `15_CODEX_AUTONOMOUS_ORCHESTRATOR.md`
2. `16_MODEL_ROUTING_POLICY.md`
3. `17_EXECUTION_STATE_AND_RESUME_PROTOCOL.md`
4. `18_DEEPSEEK_WORKER_PROTOCOL.md`

Then inspect the live repository before modifying it.

Repository truth wins for **current implemented behaviour**.
Architecture V2 wins for **target direction**.

If V2 conflicts with an accepted ADR, do not silently override it. Propose a superseding ADR or
transition plan.

## High-level division of labour

### Astra
Astra should:
- inspect the current repository at wave/task boundaries;
- plan the next bounded implementation tasks;
- identify architecture/security/data/UX conflicts;
- write precise worker briefs;
- review DeepSeek output and diffs;
- decide whether validation is sufficient;
- update the programme state;
- approve advancement to the next bounded task or wave.

### DeepSeek Flash V4.1
DeepSeek should:
- implement bounded tasks;
- write/modify code;
- write focused tests;
- perform repetitive refactors;
- update documentation for implemented behaviour;
- run focused validation;
- report exact changed files, tests and unresolved issues.

## Core cost rule

**Do not spend Astra tokens on implementation work that DeepSeek Flash V4.1 can perform reliably.**

Astra may implement directly only when:
- the change is extremely small;
- delegation overhead exceeds the task;
- the task is inseparable from an architecture-sensitive decision;
- DeepSeek failed twice and Astra determines direct intervention is cheaper/safer.

## Persistent programme loop

For each bounded task:

1. Astra reads the current execution checkpoint.
2. Astra performs only enough planning to define the next task safely.
3. Astra emits a compact DeepSeek Worker Brief.
4. DeepSeek implements and validates the task.
5. Astra reviews the resulting diff/evidence.
6. If accepted, update the execution checkpoint.
7. Continue.

At allowance/session boundaries, persist state according to
`17_EXECUTION_STATE_AND_RESUME_PROTOCOL.md`.

Do not rely on hidden model memory for continuity.

## Continuous autonomous execution

This pack authorises continuation across waves **only when**:
- the current wave gate passes;
- no STOP CONDITION is present;
- repository state is coherent;
- the hosting environment actually supports another invocation/session.

The documents define deterministic resume behaviour, but they do not assume Codex can wake itself
after an allowance reset if the host product does not provide that capability.

## STOP CONDITIONS

Pause for human review if:
- commercial-data access may broaden;
- a security control weakens;
- an accepted ADR must materially change;
- a destructive DB migration is proposed;
- a new datastore, microservice, Kafka, Kubernetes, service mesh or major infrastructure dependency
  appears necessary;
- Web/Desktop business behaviour would diverge;
- product scope crosses into execution/nomination/settlement;
- provider licence/entitlement interpretation is ambiguous;
- deterministic numerical results materially change unexpectedly;
- a Golden Scenario moves outside tolerance;
- a wave repeatedly fails for architectural reasons;
- release/DR/security foundations would need removal.

## Success criterion

Do not optimise for “finishing all V2 files”.

Optimise for:
- coherent architecture;
- small reversible changes;
- consistent UX;
- preserved numerical correctness;
- explicit evidence;
- low-cost worker utilisation;
- deterministic resume.
