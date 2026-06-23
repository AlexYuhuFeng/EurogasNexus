# V1 Release ExecPlan Template

> **For agentic workers:** Optional helper skills may be used if available, but
> this plan is fully executable by plain local CLI. Follow the checkbox
> tasks in order and update them as evidence is produced.

**Goal:** Replace this line with the selected release milestone goal.

**Architecture:** State the layer touched by this milestone and the dependency direction.

**Tech Stack:** List only approved dependencies for this milestone.

---

## Milestone ID

`R<number>`

## Status

`next`

## Required Reading

- `AGENTS.md`
- `docs/release/V1_FULL_PROJECT_RELEASE_SCOPE.md`
- `docs/release/V1_FULL_PROJECT_RELEASE_EXECUTION_PLAN.md`
- `docs/release/V1_RELEASE_MILESTONE_BACKLOG.md`
- `docs/release/V1_RELEASE_ACCEPTANCE_MATRIX.md`
- `docs/api/API_SURFACE_BLUEPRINT.md`
- `docs/data/CANONICAL_DATA_MODEL_BLUEPRINT.md`
- `docs/product/RESEARCH_WORKFLOW_BLUEPRINT.md`

## Internet Requirement

Internet required: no

Reason: Use repository-local docs, source, tests, and synthetic fixtures.

Fallback if offline: Not needed.

If the milestone requires package installation, current external package docs,
license verification, or live connector/API terms, replace this section with:

```text
Internet required: yes
Reason: <specific reason>
Fallback if offline: implement local interfaces, mocks, tests, and gap report only.
```

## Goal

State the concrete milestone objective.

## Non-goals

- No trade execution.
- No order entry.
- No order routing.
- No trade capture.
- No nomination submission.
- No official approval.
- No legal advice.
- No official trading recommendation.
- No auto-trading.
- No ETRM replacement behavior.
- No live external connector/API call unless this milestone explicitly permits
  it and documents entitlement/credential requirements.

## Files To Create Or Modify

List exact paths. Include tests and reports.

Required report path must match `docs/release/V1_RELEASE_MILESTONE_BACKLOG.md`.

## DB Impact

State:

- tables/models created or changed;
- Alembic revision name if schema changes;
- required table registry impact;
- migration command;
- rollback notes.

If no DB impact, write:

```text
No DB schema impact.
```

## API Impact

State:

- routes added or changed;
- request/response models;
- error model;
- profile exposure;
- SDK/CLI/client impact.

If no API impact, write:

```text
No API route impact.
```

## Data Policy

State:

- synthetic fixtures only, or approved live data requirements;
- source references;
- lineage;
- entitlement/export behavior;
- secret handling.

## Task Checklist

### Task 1: Write Failing Tests Or Contract Checks

- [ ] Add tests that prove the required behavior is missing.
- [ ] Run the focused tests and confirm they fail for the expected reason.

### Task 2: Implement Minimal Runtime Or Documentation Changes

- [ ] Implement only the selected milestone scope.
- [ ] Keep imports within contract boundaries.
- [ ] Preserve research-only output metadata.

### Task 3: Update Docs And Reports

- [ ] Update affected docs.
- [ ] Write the milestone report.
- [ ] Update status markers only with evidence.

### Task 4: Validate

- [ ] Run focused tests.
- [ ] Run release-required validation commands.
- [ ] Run app import route count check.

## Validation Commands

Default:

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/security tests/sdk tests/cli
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

Add web or Windows validation only when the milestone activates those toolchains.

## Acceptance Criteria

List objective evidence. Each bullet must be verifiable by file contents,
tests, command output, or report artifacts.

## Rollback Notes

List exact files/changes to revert. Include DB rollback command if a migration
was created.

## Handoff Output

Codex must end with:

- selected milestone;
- files changed;
- tests run;
- validation result;
- route count if checked;
- `COMPLETE`, `PARTIAL`, or `BLOCKED`;
- exact next prompt.
