# Claude Code Goal Mode Entrypoint

## Use This File First

When using Claude Code goal mode, point Claude at this file first. This file is
the local, offline-safe entrypoint for automatic development.

Current pause marker:

- `docs/architecture/CURRENT_PAUSE_POINT.md`

## Copy-Paste Goal Prompt

Use this prompt in Claude Code goal mode:

```text
Read AGENTS.md and docs/architecture/CLAUDE_CODE_GOAL_MODE.md first. Then follow the local docs exactly and execute the next incomplete Eurogas Nexus backend milestone from docs/architecture/NEXT_DEVELOPMENT_QUEUE.md. Assume no internet access. Work offline from repository files and local command output. Start with Milestone 2 unless it is already complete. Treat live local PostgreSQL as an explicit V1 runtime-readiness requirement when a safe DB URL is configured, but keep app import and default tests DB-free. Keep V1 backend-first, DB-first, API-first, SDK-ready, and research-only. Do not add frontend/desktop/client runtime code during backend milestones. Use tests first for behavior changes, update docs/reports, run the listed validation commands, and report complete/partial/blocked honestly.
```

## Required Reading Order

Claude Code must read these local files in order:

1. `AGENTS.md`
2. `CLAUDE_CODE_START_HERE.md`
3. `docs/architecture/CLAUDE_CODE_GOAL_MODE.md`
4. `docs/architecture/CURRENT_PAUSE_POINT.md`
5. `docs/architecture/CLAUDE_CODE_START_PROMPTS.md`
6. `docs/architecture/CLAUDE_CODE_MASTER_EXECUTION_INDEX.md`
7. `docs/architecture/ARCHITECTURE_DECISION_RECORD.md`
8. `docs/architecture/TARGET_PRODUCT_ARCHITECTURE.md`
9. `docs/architecture/NEXT_DEVELOPMENT_QUEUE.md`
10. `docs/architecture/CLAUDE_CODE_EXECUTION_PLAYBOOK.md`
11. `docs/architecture/OFFLINE_CLAUDE_CODE_GUIDE.md`
12. `docs/operations/LIVE_POSTGRESQL_V1.md`
13. the ExecPlan for the selected milestone under `.agent/plans/`

Optional context after the above:

- `docs/architecture/PROJECT_NORTH_STAR.md`
- `docs/architecture/WHOLE_PROJECT_CAPABILITY_BLUEPRINT.md`
- `docs/api/API_SURFACE_BLUEPRINT.md`
- `docs/data/CANONICAL_DATA_MODEL_BLUEPRINT.md`
- `docs/product/RESEARCH_WORKFLOW_BLUEPRINT.md`
- `docs/architecture/REFERENCE_EVIDENCE_LOG.md`
- `docs/architecture/REFERENCE_PROJECT_LESSONS.md`
- `docs/architecture/V1_DOMAIN_DELIVERY_MAP.md`
- `docs/architecture/V1_STEPWISE_DELIVERY_ROADMAP.md`
- `docs/clients/README.md`
- `docs/clients/CLIENT_DELIVERY_MILESTONES.md`
- `docs/clients/SDK_CLIENT_DESIGN_SPEC.md`
- `docs/clients/CLI_CLIENT_DESIGN_SPEC.md`
- `docs/contracts/00_CONTRACT_INDEX.md`

## Default Next Milestone

Start with Milestone 2: DB runtime hardening.

Do not jump to market data, route cost, netback, nowcast, strategy, reporting,
frontend, or Windows client work until the queue marks the earlier foundation
milestones complete.

## Development Mode

Claude Code should operate in this mode:

- offline-first;
- milestone-scoped;
- tests first for behavior changes;
- docs updated with code;
- no external APIs;
- no live connectors;
- no Docker;
- live local PostgreSQL validation is allowed when the operator has configured
  a safe DB URL;
- no automatic DB migration during import, startup, or default tests;
- live migration execution only by explicit operator command;
- no secrets printed;
- no historical code/data copied from Desktop references.

## Completion Rule

A milestone is complete only when:

- its ExecPlan acceptance criteria are met;
- its tests exist and pass;
- docs and reports are updated;
- validation commands pass or are explicitly reported as `PARTIAL`/`BLOCKED`
  with evidence;
- no required work remains inside that milestone.

## Validation Commands

Default validation:

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

CI-targeted validation:

```powershell
pytest -q tests/api tests/contract tests/integration tests/sdk tests/cli tests/release tests/security
```

## If Claude Code Is Unsure

Claude Code should not ask for clarification until it has checked:

- `NEXT_DEVELOPMENT_QUEUE.md`;
- the milestone ExecPlan;
- existing tests;
- current git status;
- current docs/contracts.

If uncertainty remains, it should create a gap report under
`data/milestone_<n>/` and continue with safe local documentation or tests that
do not invent behavior.

## Handoff Output Format

At the end of a goal-mode run, Claude Code should report:

- selected milestone;
- files changed;
- DB policy impact;
- API policy impact;
- tests run and result;
- app route count if checked;
- what is complete;
- what remains partial;
- recommended next goal-mode prompt.
