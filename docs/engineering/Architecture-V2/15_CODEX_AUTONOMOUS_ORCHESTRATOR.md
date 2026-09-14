# Codex Autonomous Orchestrator Specification

## 1. Role of Astra

Astra is a lightweight control plane for implementation.

Use Astra for:
- repository-level planning;
- architecture reconciliation;
- task graph construction;
- ADR conflict detection;
- security/data boundary review;
- UX architecture review;
- integration review;
- wave acceptance.

Astra should normally avoid routine coding.

## 2. Primary implementation engine

The preferred worker is **DeepSeek Flash V4.1** because the user has high-volume access.

Preferred execution path:
1. DeepSeek Harness Desktop when it has direct workspace/repository access.
2. Otherwise an approved DeepSeek API/CLI/Harness route that can receive a bounded task brief and
   operate against the same repository.
3. Avoid copying large repository context into chat when the worker can inspect files locally.

The exact transport may change. The architectural contract is that DeepSeek receives:
- a bounded objective;
- exact authority documents;
- relevant file/module scope;
- invariants;
- tests;
- non-goals;
- expected report format.

## 3. Task graph

Astra creates a dependency-ordered task graph for the current wave.

Each task must be small enough to finish and validate independently.

Good examples:
- add ExperienceProfile contract and focused tests;
- implement HostCapabilities interface;
- migrate one representative workspace to canonical Inspector pattern;
- add one application projection service;
- add one entitlement check;
- reconcile one documentation family.

Bad example:
- “implement Wave 5”.

## 4. Delegation strategy

Default:
- Astra plans 2–6 bounded tasks ahead.
- DeepSeek executes one task at a time unless tasks are demonstrably independent.
- Parallel work is allowed only when file ownership and architecture boundaries do not overlap.

Do not create simultaneous agents editing the same files or shared contracts without coordination.

## 5. Review depth

### Lightweight Astra review
Use when:
- mechanical/refactor-only;
- no schema/security/numeric behaviour change;
- focused tests pass;
- diff is local.

### Full Astra review
Required for:
- identity/access;
- entitlement;
- DB/schema;
- Analysis Snapshot;
- Decision Case;
- projection architecture;
- cross-platform host behaviour;
- UI shell/navigation;
- release/deployment/security;
- numeric/model semantics.

## 6. Self-correction loop

If DeepSeek fails:
1. classify:
   - implementation bug;
   - contract misunderstanding;
   - missing prerequisite;
   - environment/tooling issue;
   - architecture conflict.
2. If local, issue one corrected worker brief.
3. If it fails again, escalate to Astra.
4. Astra revises the plan rather than brute-forcing.

## 7. Context economy

Astra should not reread the entire repository every turn.

Persist:
- architecture decisions;
- current wave;
- completed tasks;
- touched contracts;
- test evidence;
- next action.

Re-read only:
- architecture authorities;
- files touched since last checkpoint;
- contracts needed for the next decision.

DeepSeek should likewise receive targeted context rather than the whole pack unless the task is
architecture-wide.

## 8. Worker-result ingestion

After each DeepSeek task, Astra must inspect:
- actual diff;
- test output;
- changed docs;
- compatibility impact;
- unresolved assumptions.

Do not accept a worker's prose summary as sufficient evidence when repository inspection is possible.

## 9. Wave completion

At the end of a wave:
- run wave-level validation;
- perform Architecture Constitution audit;
- run UX consistency checks where relevant;
- update execution state;
- record ADR changes;
- prepare next-wave task graph.

If gates pass and no STOP CONDITION exists, autonomous mode may continue.
