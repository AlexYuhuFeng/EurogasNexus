# Autonomous Execution Policy

Status: BINDING
Authority: Highest operational authority for the Architecture V2 autonomous programme.

## 1. Operating mode

The Architecture V2 programme operates in FULL AUTONOMOUS MODE.

Human approval is NOT required for:
- architecture reconciliation;
- ADR supersession;
- wave progression;
- task decomposition;
- UI/UX authority reconciliation;
- bounded refactoring;
- compatibility-preserving API evolution;
- non-destructive schema migration;
- documentation changes;
- automated test and validation changes;
- implementation sequencing.

The orchestrator SHALL NOT stop merely to request approval.

## 2. Authority precedence

When authorities conflict, apply this precedence:

1. Hard Product and Security Invariants
2. Architecture V2 Target Architecture and Constitution
3. Automatically superseding ADR/RFC decisions generated under this policy
4. Existing accepted ADR/RFC decisions
5. Existing implementation behaviour
6. Historical documentation

Existing accepted ADRs remain historical evidence but MAY be automatically superseded
when they conflict with Architecture V2.

Do not silently rewrite accepted ADR history.
Instead:
- generate a superseding ADR;
- record the reason and transition;
- preserve the previous decision;
- continue execution automatically.

No human approval is required for this supersession.

## 3. Product and security invariants

The following remain non-negotiable:

- no trade execution;
- no order entry/routing;
- no nomination submission;
- no settlement implementation;
- no automatic trading authority;
- no permission or entitlement bypass;
- no client-side provider credentials;
- no secret leakage;
- no direct client-to-database or client-to-vendor architecture;
- deterministic numerical engines remain authoritative for calculations.

## 4. Architecture conflict handling

On architecture conflict:

1. identify the conflict;
2. determine the target according to the authority precedence;
3. draft/update a superseding ADR;
4. define a bounded migration;
5. run automated validation;
6. continue.

Do NOT emit `wait_human` for architecture or governance conflicts.

## 5. Risk handling

Risk does not automatically stop the whole programme.

Prefer:
- isolate;
- branch/worktree;
- dry-run;
- backup;
- test;
- rollback;
- defer the individual task;
- continue independent tasks.

If a task cannot be safely completed automatically:
- mark that task DEFERRED or BLOCKED_EXTERNAL;
- record exact evidence;
- continue with other independent work.

## 6. External blockers

The programme may wait automatically only for external conditions such as:

- Codex allowance exhaustion;
- provider/API outage;
- missing external credential;
- inaccessible external service;
- OS/environment unavailable;
- unrecoverable repository lock.

Such states are not approval gates.

Use:
- WAITING_ALLOWANCE
- RETRYING
- BLOCKED_EXTERNAL
- DEFERRED

Do not use WAITING_HUMAN as a normal programme state.

## 7. Wave progression

Wave gates are machine-evaluated.

When acceptance criteria pass:
- checkpoint;
- commit according to repository policy;
- advance automatically to the next wave.

Do not stop for human review merely because a wave completed.

## 8. Model division of labour

GPT-6 Astra:
- lightweight planning;
- architecture decisions;
- task decomposition;
- worker review;
- integration gates.

DeepSeek Flash V4.1:
- repository inspection;
- inventories;
- implementation;
- tests;
- repetitive migration;
- documentation;
- focused validation.

Repository-wide discovery SHOULD be delegated to DeepSeek whenever possible.

## 9. Context economy

Astra should normally use fresh sessions.

Persistent programme memory lives in:
- Git;
- Architecture V2 Execution State;
- task/result artefacts;
- ADRs;
- validation evidence.

Do not grow a single Astra conversation indefinitely.

## 10. Success condition

Continue until:
- all Architecture V2 waves are complete; or
- all remaining tasks are objectively BLOCKED_EXTERNAL/DEFERRED with no independent work available.

No architecture approval from the user is required during normal execution.
