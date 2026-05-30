# Claude Code Start Here

## Purpose

Use this file when starting Claude Code CLI for Eurogas Nexus. It prevents the
most common handoff failure: starting Claude in a checkout that does not contain
the generated release docs.

## Required Working Directory

Start Claude Code from this exact repository worktree unless the docs have been
copied or committed into another checkout:

```powershell
C:\Users\qqshu\.codex\worktrees\71e0\EurogasNexus
```

If Claude Code reports that these files do not exist, it is in the wrong
directory:

- `docs/architecture/CLAUDE_CODE_MASTER_EXECUTION_INDEX.md`
- `docs/architecture/CLAUDE_CODE_IMPLEMENTATION_DIRECTIVES.md`
- `docs/product/REAL_TIME_MARKET_INTELLIGENCE_BLUEPRINT.md`
- `docs/release/V1_FULL_PROJECT_RELEASE_SCOPE.md`
- `docs/release/V1_FULL_PROJECT_RELEASE_EXECUTION_PLAN.md`
- `docs/release/V1_RELEASE_MILESTONE_BACKLOG.md`
- `docs/release/V1_RELEASE_ACCEPTANCE_MATRIX.md`
- `docs/release/V1_RELEASE_EXECPLAN_TEMPLATE.md`
- `docs/architecture/CURRENT_PAUSE_POINT.md`

## Full-Permission Local Launch

From PowerShell:

```powershell
cd C:\Users\qqshu\.codex\worktrees\71e0\EurogasNexus
claude --dangerously-skip-permissions --add-dir "C:\Users\qqshu\Desktop" --add-dir "C:\Users\qqshu\Documents\Eurogasnexus"
```

Fallback if the installed Claude Code build expects the named mode form:

```powershell
cd C:\Users\qqshu\.codex\worktrees\71e0\EurogasNexus
claude --permission-mode bypassPermissions --add-dir "C:\Users\qqshu\Desktop" --add-dir "C:\Users\qqshu\Documents\Eurogasnexus"
```

`--add-dir "C:\Users\qqshu\Desktop"` is included so Claude Code can read the
historical Eurogas folders and demo reference that the user identified. Those
folders are reference evidence only.

`--add-dir "C:\Users\qqshu\Documents\Eurogasnexus"` is included so Claude Code
can inspect the normal local checkout. That checkout currently has uncommitted
implementation work and is missing the new handoff docs. Do not use it for V1
implementation until the work is reconciled and the handoff docs have been
synced into it. See `docs/operations/WORKTREE_HANDOFF.md`.

Full local permission is not permission to leak secrets, copy old source, copy
vendor data, print `.env` values, call live external APIs, or run live
connectors. Repository rules in `AGENTS.md` still apply.

## First Verification Command

Before pasting the goal prompt, ask Claude Code to verify:

```text
Confirm your current working directory. Then verify that AGENTS.md,
CLAUDE_CODE_START_HERE.md, docs/architecture/CLAUDE_CODE_MASTER_EXECUTION_INDEX.md,
docs/architecture/CLAUDE_CODE_IMPLEMENTATION_DIRECTIVES.md,
docs/product/REAL_TIME_MARKET_INTELLIGENCE_BLUEPRINT.md,
docs/release/V1_RELEASE_MILESTONE_BACKLOG.md, and
docs/release/V1_RELEASE_EXECPLAN_TEMPLATE.md exist. If any are missing, stop and
report the current working directory only.
```

## Full V1 Goal Prompt

Paste this after the verification succeeds:

```text
Read AGENTS.md first. Then read CLAUDE_CODE_START_HERE.md,
docs/architecture/CLAUDE_CODE_IMPLEMENTATION_DIRECTIVES.md,
docs/architecture/CLAUDE_CODE_MASTER_EXECUTION_INDEX.md,
docs/product/REAL_TIME_MARKET_INTELLIGENCE_BLUEPRINT.md,
docs/release/V1_FULL_PROJECT_RELEASE_SCOPE.md,
docs/release/V1_FULL_PROJECT_RELEASE_EXECUTION_PLAN.md,
docs/release/V1_RELEASE_MILESTONE_BACKLOG.md,
docs/release/V1_RELEASE_ACCEPTANCE_MATRIX.md,
docs/release/V1_RELEASE_EXECPLAN_TEMPLATE.md,
docs/architecture/CLAUDE_CODE_START_PROMPTS.md, and
docs/architecture/CURRENT_PAUSE_POINT.md.

Build Eurogas Nexus V1 from the repository docs. Select the first incomplete milestone
from docs/release/V1_RELEASE_MILESTONE_BACKLOG.md. Treat each
milestone as a transaction: read or create its ExecPlan, run tests first for
behavior changes, implement only that milestone scope, update reports and status
markers with evidence, run validation, and record COMPLETE, PARTIAL, or BLOCKED.

If the goal-mode session can continue safely after a COMPLETE milestone, proceed
to the next incomplete milestone using the same transaction rule. Stop before a
milestone that requires unavailable package installation, live external API
access, live connector execution, unclear legal/vendor entitlement, or explicit
user approval that is not already present. In that case, write the required gap
report and end with the exact next prompt.

Keep PostgreSQL as runtime source of truth. Use /api/v1 for released clients.
The Python SDK is a required V1 surface. Keep SDK, CLI, web, and Windows clients
SDK/API-backed: CLI uses SDK first when available, SDK calls backend /api/v1,
web calls backend /api/v1, and Windows packages or launches the web/API client.
No client may connect to PostgreSQL directly, import backend DB/runtime-store
modules, or read backend local data files. Preserve source references, lineage,
assumptions, missing inputs, warnings, research_only, and
human_review_required metadata in research outputs.
Do not print secrets or full database URLs. Do not copy historical source, data,
credentials, or artifacts. Do not implement order entry, order routing, trade
capture, nomination submission, trade execution, official approval, legal
advice, official trading recommendations, auto-trading, ETRM replacement
behavior, company SSO/OIDC, live vendor connector execution, or LLM provider
calls.

Default to offline execution. Mark internet-required work explicitly with:
Internet required: yes; Reason: ...; Fallback if offline: ...

Do not substitute alternative architectures, frameworks, local stores, route
shapes, or data paths for compatibility. If the required stack or external
access is unavailable, write the gap report and stop at PARTIAL or BLOCKED.
```

## Immediate Backend-Only Prompt

Use this instead if you want the next safe milestone only:

```text
Read AGENTS.md, CLAUDE_CODE_START_HERE.md,
docs/architecture/CLAUDE_CODE_GOAL_MODE.md,
docs/architecture/CURRENT_PAUSE_POINT.md,
docs/architecture/NEXT_DEVELOPMENT_QUEUE.md,
docs/operations/LIVE_POSTGRESQL_V1.md, and
.agent/plans/V1_M2_DB_RUNTIME_HARDENING_EXECPLAN.md. Execute Milestone 2: DB
Runtime Hardening only. Treat live local PostgreSQL validation as part of V1
when a safe DB URL is configured, but keep app import and default tests DB-free.
Do not print secrets or full database URLs. Do not start Docker. Do not run
migrations automatically. Use tests first for behavior changes. Update docs and
milestone reports. Run validation and report COMPLETE, PARTIAL, or BLOCKED with
evidence.
```
