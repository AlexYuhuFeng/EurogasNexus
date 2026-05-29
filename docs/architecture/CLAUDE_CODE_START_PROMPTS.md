# Claude Code Start Prompts

## Purpose

Use this file when starting a fresh Claude Code goal-mode run. Pick exactly one
prompt. Do not mix backend, SDK, CLI, web, and Windows implementation in one
goal run.

## Prompt 1: Backend Milestone 2 With Live PostgreSQL Readiness

Use now.

```text
Read AGENTS.md first. Then read docs/architecture/CLAUDE_CODE_GOAL_MODE.md, docs/architecture/CLAUDE_CODE_MASTER_EXECUTION_INDEX.md, docs/architecture/CURRENT_PAUSE_POINT.md, docs/architecture/NEXT_DEVELOPMENT_QUEUE.md, docs/operations/LIVE_POSTGRESQL_V1.md, docs/architecture/BACKEND_IMPLEMENTATION_BLUEPRINT.md, and .agent/plans/V1_M2_DB_RUNTIME_HARDENING_EXECPLAN.md. Execute Milestone 2: DB Runtime Hardening only. Assume no internet access. Treat live local PostgreSQL validation as a V1 requirement when a safe DB URL is configured, but keep app import and default tests DB-free. Do not print secrets or full database URLs. Do not start Docker. Do not run migrations automatically. Use tests first for behavior changes. Update docs and milestone reports. Run the listed validation commands and report COMPLETE, PARTIAL, or BLOCKED with evidence.
```

## Prompt 1A: Full V1 Release Builder

Use when you want Claude Code to build the entire V1 release. Claude must still
execute one milestone transaction at a time and stop at any acceptance or
external-approval gate it cannot satisfy.

```text
Read AGENTS.md first. Then read docs/architecture/CLAUDE_CODE_IMPLEMENTATION_DIRECTIVES.md, docs/architecture/CLAUDE_CODE_MASTER_EXECUTION_INDEX.md, docs/product/REAL_TIME_MARKET_INTELLIGENCE_BLUEPRINT.md, docs/release/V1_FULL_PROJECT_RELEASE_SCOPE.md, docs/release/V1_FULL_PROJECT_RELEASE_EXECUTION_PLAN.md, docs/release/V1_RELEASE_MILESTONE_BACKLOG.md, docs/release/V1_RELEASE_ACCEPTANCE_MATRIX.md, docs/release/V1_RELEASE_EXECPLAN_TEMPLATE.md, docs/architecture/CLAUDE_CODE_START_PROMPTS.md, and docs/architecture/CURRENT_PAUSE_POINT.md. Select the first incomplete milestone from docs/release/V1_RELEASE_MILESTONE_BACKLOG.md. If its ExecPlan is missing, create it from the template and execute the milestone in the same run. Keep PostgreSQL as runtime source of truth, use /api/v1 for clients, keep SDK/CLI/web/Windows API-backed, preserve research-only/human-review metadata, do not print secrets, do not copy historical source/data, and do not implement order/trade/nomination/execution/official recommendation behavior. Do not substitute alternative architectures or frameworks for compatibility. Run the milestone validation commands, update reports, and end with COMPLETE, PARTIAL, or BLOCKED plus the exact next prompt.
```

## Prompt 1B: Full V1 Autonomous Release Loop

Use only after starting Claude Code from the correct worktree and granting local
permissions intentionally. This prompt is also stored in
`CLAUDE_CODE_START_HERE.md`.

```text
Read AGENTS.md first. Then read CLAUDE_CODE_START_HERE.md, docs/architecture/CLAUDE_CODE_IMPLEMENTATION_DIRECTIVES.md, docs/architecture/CLAUDE_CODE_MASTER_EXECUTION_INDEX.md, docs/product/REAL_TIME_MARKET_INTELLIGENCE_BLUEPRINT.md, docs/release/V1_FULL_PROJECT_RELEASE_SCOPE.md, docs/release/V1_FULL_PROJECT_RELEASE_EXECUTION_PLAN.md, docs/release/V1_RELEASE_MILESTONE_BACKLOG.md, docs/release/V1_RELEASE_ACCEPTANCE_MATRIX.md, docs/release/V1_RELEASE_EXECPLAN_TEMPLATE.md, docs/architecture/CLAUDE_CODE_START_PROMPTS.md, and docs/architecture/CURRENT_PAUSE_POINT.md. Build Eurogas Nexus V1 from the repository docs. Select the first incomplete milestone from docs/release/V1_RELEASE_MILESTONE_BACKLOG.md. Treat each milestone as a transaction: read or create its ExecPlan, run tests first for behavior changes, implement only that milestone scope, update reports and status markers with evidence, run validation, and record COMPLETE, PARTIAL, or BLOCKED. If the goal-mode session can continue safely after a COMPLETE milestone, proceed to the next incomplete milestone using the same transaction rule. Stop before a milestone that requires unavailable package installation, live external API access, live connector execution, unclear legal/vendor entitlement, or explicit user approval that is not already present. Keep PostgreSQL as runtime source of truth, use /api/v1 for released clients, keep clients SDK/API-backed, require Python SDK for V1, preserve research-only/human-review metadata, do not print secrets, do not copy historical source/data, and do not implement order/trade/nomination/execution/official recommendation behavior. Do not substitute alternative architectures, frameworks, local stores, route shapes, or data paths for compatibility. Default to offline execution and mark internet-required work explicitly.
```

## Prompt 2: SDK Client Milestone S1

Use after backend API response contracts are stable enough for SDK expansion.

```text
Read AGENTS.md first. Then read docs/clients/README.md, docs/clients/CLIENT_DELIVERY_MILESTONES.md, docs/clients/CLIENT_API_CONTRACT.md, docs/clients/SDK_CLIENT_DESIGN_SPEC.md, docs/contracts/15_SDK_CLI_CONTRACT.md, and .agent/plans/SDK_M1_API_CLIENT_EXECPLAN.md. Implement SDK Milestone S1 only in src/eurogas_nexus/sdk and tests/sdk. Use /api/v1 as the only stable client prefix. Keep the SDK as an API client only. Do not import domain/application/runtime_store/db internals, read PostgreSQL directly, call vendor APIs, call LLM providers, add package publishing, or add trade/order/nomination/execution methods.
```

## Prompt 3: CLI Client Milestone C1

Use after SDK S1 exists or when the current SDK health helper is sufficient for
the selected CLI work.

```text
Read AGENTS.md first. Then read docs/clients/README.md, docs/clients/CLIENT_DELIVERY_MILESTONES.md, docs/clients/CLIENT_API_CONTRACT.md, docs/clients/CLI_CLIENT_DESIGN_SPEC.md, docs/clients/SDK_CLIENT_DESIGN_SPEC.md, docs/contracts/15_SDK_CLI_CONTRACT.md, and .agent/plans/CLI_M1_OPERATOR_COMMANDS_EXECPLAN.md. Implement CLI Milestone C1 only in src/eurogas_nexus/cli and tests/cli. Keep commands API/SDK-backed, read-only by default, secret-redacted, and explicit about COMPLETE/PARTIAL/BLOCKED states. Do not add mutating commands without --execute guards, live connector calls, direct DB business access, or trade/order/nomination/execution commands.
```

## Prompt 4: Web Client Milestone W1

Use only after the backend activation gates in
`docs/clients/CLIENT_DELIVERY_MILESTONES.md` are met and the user explicitly
selects the web phase.

```text
Read AGENTS.md first. Then read docs/architecture/CLAUDE_CODE_IMPLEMENTATION_DIRECTIVES.md, docs/architecture/PRODUCT_DELIVERY_MASTER_PLAN.md, docs/product/REAL_TIME_MARKET_INTELLIGENCE_BLUEPRINT.md, docs/clients/README.md, docs/clients/CLIENT_TECH_STACK.md, docs/clients/CLIENT_I18N_THEME_SPEC.md, docs/clients/CLIENT_DELIVERY_MILESTONES.md, docs/clients/CLIENT_API_CONTRACT.md, docs/clients/CLIENT_DESIGN_SYSTEM.md, docs/clients/WEB_CLIENT_DESIGN_SPEC.md, docs/design/UX_LAYOUT_BLUEPRINTS.md, docs/architecture/WEB_CLIENT_IMPLEMENTATION_BLUEPRINT.md, and .agent/plans/WEB_M1_WORKSPACE_SHELL_EXECPLAN.md. Implement Web Milestone W1 only in clients/web. Use /api/v1 as the client API prefix. Use the fixed React/Vite/MapLibre/deck.gl/Zustand/i18next stack. Implement English/Mandarin and light/dark/system foundations. If internet is unavailable or Node dependencies cannot be installed, create the planned file structure, TypeScript interfaces, i18n/theme resources, mocked API client, and gap report instead of claiming a working build. Do not add direct DB access, browser-side vendor/LLM provider calls, browser secrets, order/nomination/execution workflows, or Windows packaging.
```

## Prompt 5: Windows Client Milestone D1

Use only after the web workspace shell exists and the user explicitly selects
the Windows phase.

```text
Read AGENTS.md first. Then read docs/architecture/CLAUDE_CODE_IMPLEMENTATION_DIRECTIVES.md, docs/architecture/PRODUCT_DELIVERY_MASTER_PLAN.md, docs/product/REAL_TIME_MARKET_INTELLIGENCE_BLUEPRINT.md, docs/clients/README.md, docs/clients/CLIENT_TECH_STACK.md, docs/clients/CLIENT_I18N_THEME_SPEC.md, docs/clients/CLIENT_DELIVERY_MILESTONES.md, docs/clients/CLIENT_API_CONTRACT.md, docs/clients/CLIENT_DESIGN_SYSTEM.md, docs/clients/WINDOWS_CLIENT_DESIGN_SPEC.md, docs/design/UX_LAYOUT_BLUEPRINTS.md, docs/architecture/WINDOWS_CLIENT_IMPLEMENTATION_BLUEPRINT.md, and .agent/plans/WINDOWS_D1_DESKTOP_SHELL_EXECPLAN.md. Implement Windows Milestone D1 only in clients/desktop. Use Tauri 2 only; do not use Electron or SQLite. Package the web workspace as an API consumer of /api/v1. Preserve English/Mandarin and light/dark/system behavior. Store only non-sensitive UI preferences. If Tauri/Rust/Node dependencies are unavailable, write config templates and a gap report instead of substituting another desktop stack. Do not add direct DB access, vendor/LLM provider calls, bundled secrets, order/nomination/execution workflows, company SSO/OIDC, or copied historical Desktop code.
```

## Prompt 6: Documentation Polish Pass

Use later if you want a focused documentation cleanup without implementation.

```text
Read AGENTS.md and docs/architecture/CLAUDE_CODE_START_PROMPTS.md first. Perform a documentation-only polish pass. Do not change runtime code. Check that backend, SDK, CLI, web, Windows, live PostgreSQL, API path, product boundary, and offline Claude Code instructions are consistent. Update broken links, stale status markers, and ambiguous wording. Run docs contract tests and ruff if available. Report changed files and any remaining gaps.
```
