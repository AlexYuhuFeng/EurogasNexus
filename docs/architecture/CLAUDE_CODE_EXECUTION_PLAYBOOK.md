# Claude Code Execution Playbook

## Purpose

This playbook tells future Claude Code sessions how to move Eurogas Nexus from
documentation to implementation. It is written as a practical delivery guide,
not as a historical summary.

## Read First

Before coding, read these files in order:

1. `AGENTS.md`
2. `docs/architecture/TARGET_PRODUCT_ARCHITECTURE.md`
3. `docs/architecture/PROJECT_NORTH_STAR.md`
4. `docs/architecture/CLAUDE_CODE_DELIVERY_BRIEF.md`
5. `docs/architecture/OFFLINE_CLAUDE_CODE_GUIDE.md`
6. `docs/architecture/V1_STEPWISE_DELIVERY_ROADMAP.md`
7. the relevant `.agent/plans/*EXECPLAN.md`

If the plan and the architecture conflict, update the plan first and explain the
change in the milestone report.

## Working Style

Claude Code should work milestone by milestone. Each milestone should leave the
repo more coherent than it found it.

Assume internet access is not available. Normal milestones should be executable
from repository-local docs, source, tests, and installed dependencies. If a task
requires current external documentation, live vendor terms, or package metadata
that is not present locally, mark the task with `Internet required: yes` and
provide an offline fallback.

For each milestone:

1. Confirm the scope.
2. Identify the files to touch.
3. Add or update tests for the boundary.
4. Implement the smallest working slice.
5. Update docs and reports.
6. Run the validation commands.
7. Report what is complete, partial, blocked, and recommended next.

## Documentation Before Code

For any new area, create documentation before runtime code:

- contract doc under `docs/contracts/`;
- architecture or policy doc if ownership changes;
- DB impact note if schemas or migrations change;
- API impact note if routes change;
- data policy note if files, fixtures, source data, or exports are involved;
- internet requirement note using `Internet required: no` or
  `Internet required: yes`;
- ExecPlan under `.agent/plans/`.

The documentation should be concrete enough that another engineer can implement
without guessing file names, responsibilities, or validation commands.

## How To Turn A Domain Idea Into A Slice

Use this template:

```text
Idea:
  What business/research question does this help answer?

Boundary:
  Which module owns it?
  Which module must not own it?

Data:
  What tables or fixtures are needed?
  What lineage/source/freshness metadata is required?

API:
  Which /api/v1 path exposes it?
  What request/response model is returned?

Output:
  Does it need assumptions, missing inputs, warnings, source references,
  lineage, research_only, human_review_required?

Validation:
  Which tests prove the boundary?
  Which command proves app import remains safe?
```

## Preferred Implementation Order

### Step 1: Stabilize Foundation

Work on:

- DB runtime readiness;
- Alembic lifecycle;
- API path normalization;
- import boundaries;
- SDK/CLI API-only behavior;
- validation scripts.

Avoid broad domain behavior here. The goal is to make future work safe.

### Step 2: Build Runtime Store

Work on:

- repository interfaces;
- session lifecycle;
- DB unavailable behavior;
- table registry;
- no-file-fallback enforcement;
- result metadata.

### Step 3: Add Canonical Reference Network

Work on:

- canonical IDs;
- synthetic fixtures;
- nodes/facilities/segments schema plan;
- read-only `/api/v1/reference-network/*`;
- lineage and source references.

### Step 4: Add Ingestion Metadata

Work on:

- ingestion job/run models;
- connector definition records;
- normalization result records;
- data quality/freshness records.

Use mocked connectors. Do not require live source credentials.

### Step 5: Add Governance And Audit

Work on:

- entitlement model;
- audit event model;
- export policy checks;
- user/action/context metadata.

### Step 6: Add First Research Workflow

Choose a narrow workflow, preferably one of:

- route-cost input validation;
- reference topology read model;
- scenario input contract;
- research output envelope.

Do not start with a complex end-to-end strategy, allocation, or nowcast engine.

## Target File Ownership

Use these ownership rules:

| Area | Path | Owns |
| --- | --- | --- |
| API app/routes | `src/eurogas_nexus/api` | FastAPI route registration and HTTP models |
| Application | `src/eurogas_nexus/application` | workflow orchestration |
| Domain | `src/eurogas_nexus/domain` | pure research concepts and rules |
| Runtime store | `src/eurogas_nexus/runtime_store` | repository interfaces and DB-backed stores |
| DB | `src/eurogas_nexus/db` | SQLAlchemy models, sessions, health, registry |
| Ingestion | `src/eurogas_nexus/ingestion` | source/job/run contracts and normalization entrypoints |
| Data quality | `src/eurogas_nexus/data_quality` | freshness and quality result models |
| Governance | `src/eurogas_nexus/governance` | entitlement and export policy |
| Audit | `src/eurogas_nexus/audit` | audit event models and sinks |
| SDK | `src/eurogas_nexus/sdk` | API client facade |
| CLI | `src/eurogas_nexus/cli` | CLI calling SDK/API |

## API Design Rules

Prefer stable routes under `/api/v1`.

Each route should specify:

- route family;
- method and path;
- profile exposure;
- request model;
- response model;
- error model;
- source-of-truth expectation;
- whether it is read-only or write-capable;
- whether audit is required.

Keep initial routes read-only unless the milestone is explicitly about writes.

## DB Design Rules

Each table should specify:

- owner module;
- purpose;
- primary key;
- natural/canonical identifiers;
- source reference fields;
- lineage fields;
- timestamps;
- schema version;
- data scope;
- indexes;
- migration revision;
- rollback behavior.

## Response Design Rules

Research outputs should use a predictable envelope:

```json
{
  "data": {},
  "assumptions": [],
  "missing_inputs": [],
  "warnings": [],
  "source_references": [],
  "lineage": [],
  "research_only": true,
  "human_review_required": true
}
```

Health and simple metadata routes may stay smaller when appropriate.

## Testing Strategy

Use focused tests:

- API route tests for route behavior;
- contract tests for architecture boundaries;
- integration tests for DB helpers and import safety;
- security tests for redaction and secret handling;
- SDK/CLI tests for API-only client behavior.

Do not depend on live external services in tests.

## Validation Commands

Default handoff validation:

```powershell
ruff check .
pytest -q tests/api tests/contract tests/integration tests/security
python -c "from apps.api.main import app; print('app import ok'); print(len(app.routes))"
```

CI-targeted validation:

```powershell
pytest -q tests/api tests/contract tests/integration tests/sdk tests/cli tests/release tests/security
```

## How To Use Historical References

Use historical projects to answer:

- What workflow was the user trying to support?
- Which domain terms are important?
- Which UI concepts should future clients preserve after redesign?
- Which architecture choices created maintenance problems?
- Which docs contain useful boundary language?

Do not use them as:

- source code to paste;
- data source;
- secret source;
- proof that a feature belongs in the current milestone;
- reason to add heavy dependencies.

## Internet Requirement Notes

Use this block in future milestone docs:

```text
Internet required: no
Reason: <why local repository context is sufficient>
Fallback if offline: Not needed.
```

If external verification is truly required:

```text
Internet required: yes
Reason: <specific external source needed>
Fallback if offline: <mock/interface/gap-report-only path>
```

Do not block local architecture, tests, or interface work just because live
external verification is unavailable. Build the offline-safe boundary and record
the gap.

## Handoff Format

Final responses after implementation should include:

- files changed;
- architecture boundary affected;
- DB policy;
- API policy;
- tests run and result;
- route count if app import was checked;
- remaining gaps;
- recommended next milestone.
