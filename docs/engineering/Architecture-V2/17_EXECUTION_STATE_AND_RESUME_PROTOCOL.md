# Execution State and Resume Protocol

## Purpose

Long-running autonomous work must survive session and allowance boundaries without relying on model
memory.

Maintain:

`docs/engineering/ARCHITECTURE_V2_EXECUTION_STATE.md`

or, if repository policy forbids committing temporary programme state, an equivalent workspace-local
file whose path is recorded explicitly.

## Required checkpoint

```markdown
# Architecture V2 Execution State

Last updated:
Repository HEAD:
Working tree:
V2 pack version:
Current wave:
Wave status:

## Accepted architecture decisions
- ...

## Completed tasks
- [x] ID — outcome — validation

## Current/next task
- ID:
- objective:
- assigned worker:
- relevant files/contracts:
- focused tests:
- exact next action:

## Deferred / known gaps
- ...

## Compatibility
- API:
- DB:
- Client:
- Release:

## Validation evidence
- ...

## Risks / STOP CONDITIONS
- ...

## Resume instruction
- exact next action
```

## Checkpoint frequency

Update:
- after each material task;
- before/after migrations;
- after validation;
- before allowance/session exhaustion;
- at wave boundaries;
- whenever blocked.

## Before allowance exhaustion

Do not start a task that cannot be completed safely.

Instead:
1. finish current bounded task;
2. validate it;
3. update checkpoint;
4. note any intentional uncommitted work;
5. record exact next action;
6. stop cleanly.

## Resume

On the next session:
1. read `CODEX_ENTRYPOINT.md`;
2. read checkpoint;
3. verify HEAD and working tree;
4. inspect any drift;
5. run smallest relevant sanity check;
6. continue from exact next action.

## Host limitation

This protocol supports autonomous continuation **when a host invokes a new session**.

It does not assume Codex can schedule or wake itself after a Plus allowance reset. If the host does
not provide automatic resumption, the user only needs to relaunch/resume the programme; the
checkpoint should make continuation deterministic and low-effort.
