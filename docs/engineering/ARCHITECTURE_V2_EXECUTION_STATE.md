# Architecture V2 Execution State

Last updated: NOT_STARTED
Repository HEAD: UNKNOWN
Working tree: UNKNOWN
V2 pack version: 2026-09 autonomous runner
Current wave: Wave 0
Wave status: NOT_STARTED

## Accepted architecture decisions

- V2 documents under `docs/engineering/Architecture-V2/` define target direction.
- Repository truth defines current implemented behaviour.
- GPT-6 Astra plans/reviews; DeepSeek Flash V4.1 implements routine bounded work.
- Modular monolith + worker runtime remains the default product architecture.

## Completed tasks

- None.

## Current / next task

- Task ID: UNASSIGNED
- Objective: begin Wave 0 repository mapping and then Wave 1 Product Experience Architecture foundation.
- Exact next action: inspect current repo and produce the first bounded task brief; do not mass-refactor.

## Deferred / known gaps

- Native OpenAI-parent → DeepSeek-child Codex subagent remains optional until a local smoke test passes.

## Compatibility

- API: preserve unless explicitly reviewed.
- DB: no destructive migration without human gate.
- Client: one React business UI; Tauri thin host.
- Release: preserve existing release/security/DR machinery.

## Validation evidence

- None yet.

## Risks / STOP CONDITIONS

See Architecture V2 Constitution, Migration Roadmap and Master Prompt.

## Resume instruction

Read the V2 entrypoint, inspect Git status/HEAD and current diff, verify no unexpected drift, then continue the exact next bounded task. Never redo a completed task just because the Codex session changed.
