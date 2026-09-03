# V1 Release Milestone Backlog

## Purpose

This backlog is the exact queue Codex should use for the full V1 release.
It complements `docs/release/V1_FULL_PROJECT_RELEASE_EXECUTION_PLAN.md` by
listing the required ExecPlan path, report path, and proof for each milestone.

If an ExecPlan listed here does not exist, Codex must create it from
`docs/release/V1_RELEASE_EXECPLAN_TEMPLATE.md` and execute that milestone in the
same goal-mode run unless the user explicitly asks for planning only.

## Status Values

- `complete`: all acceptance evidence exists and validation passed.
- `next`: first incomplete milestone.
- `pending`: waiting for earlier milestones.
- `partial`: some implementation exists, gap report required.
- `blocked`: cannot proceed without user input or external state.

## Backlog

| ID | Status | Milestone | ExecPlan | Required Report |
| --- | --- | --- | --- | --- |
| R0 | pending | Orientation and gap audit | `docs/archive/agent-plans/V1_R0_ORIENTATION_GAP_AUDIT_EXECPLAN.md` | `docs/archive/reports/release_v1/r0_orientation_gap_audit.md` |
| R1 | complete | DB runtime foundation | `docs/archive/agent-plans/V1_M2_DB_RUNTIME_HARDENING_EXECPLAN.md` | `docs/archive/reports/release_v1/r1_db_runtime_report.md` |
| R2 | complete | Runtime store and governance foundation | `docs/archive/agent-plans/V1_R2_RUNTIME_STORE_GOVERNANCE_EXECPLAN.md` | `docs/archive/reports/release_v1/r2_runtime_governance_report.md` |
| R3 | complete | Reference network and relationship mapping | `docs/archive/agent-plans/V1_R3_REFERENCE_NETWORK_EXECPLAN.md` | `docs/archive/reports/release_v1/r3_reference_network_report.md` |
| R4 | complete | Source registry and ingestion control plane | `docs/archive/agent-plans/V1_R4_INGESTION_CONTROL_EXECPLAN.md` | `docs/archive/reports/release_v1/r4_ingestion_control_report.md` |
| R5 | complete | Context observation slices | `docs/archive/agent-plans/V1_R5_CONTEXT_OBSERVATIONS_EXECPLAN.md` | `docs/archive/reports/release_v1/r5_context_observations_report.md` |
| R6 | complete | Research workflow models | `docs/archive/agent-plans/V1_R6_RESEARCH_WORKFLOW_MODELS_EXECPLAN.md` | `docs/archive/reports/release_v1/r6_research_workflow_models_report.md` |
| R7 | complete | Route cost and indicative netback | `docs/archive/agent-plans/V1_R7_ROUTE_COST_NETBACK_EXECPLAN.md` | `docs/archive/reports/release_v1/r7_route_cost_netback_report.md` |
| R8 | complete | Feasibility and allocation | `docs/archive/agent-plans/V1_R8_FEASIBILITY_ALLOCATION_EXECPLAN.md` | `docs/archive/reports/release_v1/r8_feasibility_allocation_report.md` |
| R9 | complete | Monitoring and weather-adjusted nowcast | `docs/archive/agent-plans/V1_R9_MONITORING_NOWCAST_EXECPLAN.md` | `docs/archive/reports/release_v1/r9_monitoring_nowcast_report.md` |
| R10 | complete | Strategy backtest and shadow run | `docs/archive/agent-plans/V1_R10_STRATEGY_SHADOW_RUN_EXECPLAN.md` | `docs/archive/reports/release_v1/r10_strategy_shadow_run_report.md` |
| R11 | complete | Research brief and reporting | `docs/archive/agent-plans/V1_R11_RESEARCH_BRIEF_REPORTING_EXECPLAN.md` | `docs/archive/reports/release_v1/r11_research_brief_reporting_report.md` |
| R12 | complete | SDK release surface | `docs/archive/agent-plans/V1_R12_SDK_RELEASE_SURFACE_EXECPLAN.md` | `docs/archive/reports/release_v1/r12_sdk_release_surface_report.md` |
| R13 | complete | CLI release surface | `docs/archive/agent-plans/V1_R13_CLI_RELEASE_SURFACE_EXECPLAN.md` | `docs/archive/reports/release_v1/r13_cli_release_surface_report.md` |
| R14 | partial | Web decision-support workspace | `docs/archive/agent-plans/V1_R14_WEB_RELEASE_WORKSPACE_EXECPLAN.md` | `docs/archive/reports/release_v1/r14_web_release_workspace_report.md` |
| R15 | partial | Windows client package shell | `docs/archive/agent-plans/V1_R15_WINDOWS_RELEASE_SHELL_EXECPLAN.md` | `docs/archive/reports/release_v1/r15_windows_release_shell_report.md` |
| R16 | complete | Release pack and final validation | `docs/archive/agent-plans/V1_R16_RELEASE_PACK_EXECPLAN.md` | `docs/archive/reports/release_v1/r16_release_pack_report.md` |

## Backlog Rule

Codex must select the first milestone whose status is not `complete`.

If status markers are stale, Codex must inspect evidence:

- required report exists;
- acceptance criteria are satisfied;
- validation commands passed;
- no required gap remains.

Only then may it update the status in this backlog.

## Required Evidence Per Milestone

Every milestone report must include:

- selected milestone ID;
- files changed;
- DB impact;
- API impact;
- SDK/CLI impact when relevant;
- web/Windows impact when relevant;
- data policy;
- tests run;
- validation result;
- route count if app import was checked;
- `COMPLETE`, `PARTIAL`, or `BLOCKED`;
- next recommended prompt.

## Do Not Skip

Do not jump from backend foundation directly to web or Windows work. The web and
Windows clients depend on stable API, data, and research-output contracts.
