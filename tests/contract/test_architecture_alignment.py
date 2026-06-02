"""Architecture alignment documentation contract tests."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read_doc(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_project_north_star_preserves_v1_boundaries() -> None:
    text = _read_doc("docs/architecture/PROJECT_NORTH_STAR.md")

    assert "research-only" in text.lower()
    assert "PostgreSQL" in text
    assert "API-first" in text
    assert "SDK-ready" in text
    assert "No frontend runtime implementation belongs" in text
    assert "docs/clients/" in text
    assert "trade execution" in text.lower()


def test_reference_lessons_document_failed_implementation_patterns() -> None:
    text = _read_doc("docs/architecture/REFERENCE_PROJECT_LESSONS.md")

    for phrase in [
        "desktop-first drift",
        "local-file runtime truth",
        "domain sprawl",
        "live connector",
        "LLM",
    ]:
        assert phrase in text


def test_stepwise_roadmap_starts_with_backend_foundations() -> None:
    text = _read_doc("docs/architecture/V1_STEPWISE_DELIVERY_ROADMAP.md")

    assert "Milestone 1" in text
    assert "Milestone 2" in text
    assert "DB runtime hardening" in text
    assert "/api/v1" in text
    assert "research_only" in text
    assert "human_review_required" in text


def test_claude_code_playbook_is_positive_delivery_guidance() -> None:
    text = _read_doc("docs/architecture/CLAUDE_CODE_EXECUTION_PLAYBOOK.md")

    assert "How To Turn A Domain Idea Into A Slice" in text
    assert "Preferred Implementation Order" in text
    assert "Target File Ownership" in text
    assert "Handoff Format" in text


def test_target_product_architecture_explains_workflows() -> None:
    text = _read_doc("docs/architecture/TARGET_PRODUCT_ARCHITECTURE.md")

    assert "Explore The Network" in text
    assert "Understand Market Context" in text
    assert "Compose A Scenario" in text
    assert "Compare Candidates" in text
    assert "Produce A Research Output" in text
    assert "Python SDK" in text
    assert "CLI" in text


def test_architecture_decisions_are_explicit() -> None:
    text = _read_doc("docs/architecture/ARCHITECTURE_DECISION_RECORD.md")

    for phrase in [
        "V1 Is Backend-First And Multi-Surface",
        "PostgreSQL Is Runtime Truth",
        "Live PostgreSQL Validation Is In V1",
        "Stable API Prefix Is `/api/v1`",
        "Domain Work Is Slice-Based",
        "Claude Code Works Offline By Default",
        "Historical Projects Are Evidence, Not Source",
    ]:
        assert phrase in text


def test_offline_guide_marks_internet_requirements() -> None:
    text = _read_doc("docs/architecture/OFFLINE_CLAUDE_CODE_GUIDE.md")

    assert "Assume internet access is not available" in text
    assert "Internet required: yes" in text
    assert "Fallback if offline" in text
    assert "LIVE_POSTGRESQL_V1.md" in text


def test_goal_mode_entrypoint_points_to_next_queue() -> None:
    text = _read_doc("docs/architecture/CLAUDE_CODE_GOAL_MODE.md")

    assert "Copy-Paste Goal Prompt" in text
    assert "CLAUDE_CODE_START_HERE.md" in text
    assert "CLAUDE_CODE_MASTER_EXECUTION_INDEX.md" in text
    assert "NEXT_DEVELOPMENT_QUEUE.md" in text
    assert "CURRENT_PAUSE_POINT.md" in text
    assert "CLAUDE_CODE_START_PROMPTS.md" in text
    assert "Start with Milestone 2" in text
    assert "Assume no internet access" in text
    assert "live local PostgreSQL" in text


def test_next_development_queue_selects_milestone_2() -> None:
    text = _read_doc("docs/architecture/NEXT_DEVELOPMENT_QUEUE.md")

    assert "Milestone 2: DB Runtime Hardening" in text
    assert "Status: `next`" in text
    assert ".agent/plans/V1_M2_DB_RUNTIME_HARDENING_EXECPLAN.md" in text
    assert "Archived Desktop projects are reference evidence only" in text
    assert "live PostgreSQL validation" in text


def test_current_pause_point_records_holistic_runtime_pause_state() -> None:
    text = _read_doc("docs/architecture/CURRENT_PAUSE_POINT.md")

    assert "Holistic local runtime testing" in text
    assert "V1 release candidate" in text
    assert "332 passed" in text
    assert "74 routes" in text
    assert "Windows/Tauri" in text
    assert "Console after interactions: 0 errors, 0 warnings" in text
    assert "screen_order_observations" in text
    assert "operational glossary context" in text
    assert "/api/internal/portfolio/import-observations" in text
    assert "Provider credentials are backend-owned" in text
    assert "data/release_v1/holistic_real_test_report.md" in text


def test_live_postgresql_policy_is_explicit_and_safe() -> None:
    text = _read_doc("docs/operations/LIVE_POSTGRESQL_V1.md")

    assert "Live PostgreSQL is part of V1 runtime readiness" in text
    assert "App import must not connect to PostgreSQL" in text
    assert (
        "Default unit, API, contract, integration, and security tests must pass"
        in text
    )
    assert "must never be printed in full" in text
    assert "python scripts/ops/validate_v1_runtime_db.py --json" in text


def test_client_design_docs_are_ready_for_future_goal_mode() -> None:
    index = _read_doc("docs/clients/README.md")
    sdk = _read_doc("docs/clients/SDK_CLIENT_DESIGN_SPEC.md")
    cli = _read_doc("docs/clients/CLI_CLIENT_DESIGN_SPEC.md")
    web = _read_doc("docs/clients/WEB_CLIENT_DESIGN_SPEC.md")
    windows = _read_doc("docs/clients/WINDOWS_CLIENT_DESIGN_SPEC.md")
    windows_demo = _read_doc("docs/clients/WINDOWS_DEMO_UX_REFERENCE.md")
    design_system = _read_doc("docs/clients/CLIENT_DESIGN_SYSTEM.md")
    api_contract = _read_doc("docs/clients/CLIENT_API_CONTRACT.md")
    layouts = _read_doc("docs/design/UX_LAYOUT_BLUEPRINTS.md")
    web_plan = _read_doc(".agent/plans/WEB_M1_WORKSPACE_SHELL_EXECPLAN.md")
    windows_plan = _read_doc(".agent/plans/WINDOWS_D1_DESKTOP_SHELL_EXECPLAN.md")
    sdk_plan = _read_doc(".agent/plans/SDK_M1_API_CLIENT_EXECPLAN.md")
    cli_plan = _read_doc(".agent/plans/CLI_M1_OPERATOR_COMMANDS_EXECPLAN.md")

    assert "CLIENT_DELIVERY_MILESTONES.md" in index
    assert "Clients are SDK/API consumers" in index
    milestones = _read_doc(
        "docs/clients/CLIENT_DELIVERY_MILESTONES.md"
    )
    assert "Client implementation is separated by surface" in milestones
    assert "SDK_M1_API_CLIENT_EXECPLAN.md" in milestones
    assert "CLI_M1_OPERATOR_COMMANDS_EXECPLAN.md" in milestones
    assert "WEB_M1_WORKSPACE_SHELL_EXECPLAN.md" in milestones
    assert "WINDOWS_D1_DESKTOP_SHELL_EXECPLAN.md" in milestones
    assert "GET /api/v1/health" in api_contract
    assert "Runtime Data Access Rule" in api_contract
    assert "Python SDK -> backend `/api/v1`" in api_contract
    assert "No client may open a PostgreSQL connection" in api_contract
    assert "research_only" in api_contract
    assert "The Python SDK is the programmatic client" in sdk
    assert "The SDK is a required V1 product surface" in sdk
    assert "The CLI is the operator and automation command surface" in cli
    assert "CLI -> Python SDK -> backend /api/v1" in cli
    assert "First screen is the workspace" in design_system
    assert "Top status bar" in web
    assert "Web UI -> web API client -> backend /api/v1" in web
    assert "First Web Implementation Prompt" in web
    assert "Tauri" in windows
    assert "Windows shell -> packaged web workspace/API client" in windows
    assert "First Windows Implementation Prompt" in windows
    assert "Dense terminal-style workspace" in windows_demo
    assert "eurogas-nexus-v0.5.0.exe" in windows_demo
    assert "Web Workspace Desktop Layout" in layouts
    assert "SDK M1 API Client Implementation Plan" in sdk_plan
    assert "CLI M1 Operator Commands Implementation Plan" in cli_plan
    assert "Web M1 Workspace Shell Implementation Plan" in web_plan
    assert "Windows D1 Desktop Shell Implementation Plan" in windows_plan


def test_claude_start_prompts_cover_all_surfaces() -> None:
    text = _read_doc("docs/architecture/CLAUDE_CODE_START_PROMPTS.md")

    assert "Backend Milestone 2 With Live PostgreSQL Readiness" in text
    assert "SDK Client Milestone S1" in text
    assert "CLI Client Milestone C1" in text
    assert "Web Client Milestone W1" in text
    assert "Windows Client Milestone D1" in text
    assert "Full V1 Release Builder" in text
    assert "Full V1 Autonomous Release Loop" in text
    assert "CLAUDE_CODE_START_HERE.md" in text
    assert "V1_FULL_PROJECT_RELEASE_EXECUTION_PLAN.md" in text
    assert "V1_RELEASE_MILESTONE_BACKLOG.md" in text
    assert "V1_RELEASE_ACCEPTANCE_MATRIX.md" in text
    assert "V1_RELEASE_EXECPLAN_TEMPLATE.md" in text
    assert "SDK_M1_API_CLIENT_EXECPLAN.md" in text
    assert "CLI_M1_OPERATOR_COMMANDS_EXECPLAN.md" in text
    assert "WEB_M1_WORKSPACE_SHELL_EXECPLAN.md" in text
    assert "WINDOWS_D1_DESKTOP_SHELL_EXECPLAN.md" in text
    assert "Documentation Polish Pass" in text
    assert "Do not print secrets or full database URLs" in text


def test_whole_project_blueprint_covers_requested_capabilities() -> None:
    text = _read_doc("docs/architecture/WHOLE_PROJECT_CAPABILITY_BLUEPRINT.md")

    for phrase in [
        "market prices",
        "physical flows",
        "LNG/regas",
        "storage",
        "weather",
        "Path Cost And Indicative Netback",
        "Feasibility And Allocation Scenario",
        "Weather-Adjusted Nowcast",
        "Strategy Backtest And Shadow Run",
        "Research Brief And Reporting",
        "not official trading recommendations",
        "docs/data/CANONICAL_DATA_MODEL_BLUEPRINT.md",
        "docs/api/API_SURFACE_BLUEPRINT.md",
        "docs/product/RESEARCH_WORKFLOW_BLUEPRINT.md",
    ]:
        assert phrase in text


def test_reference_evidence_log_records_archived_sources() -> None:
    text = _read_doc("docs/architecture/REFERENCE_EVIDENCE_LOG.md")

    assert "eurogas-nexus-v0.5.0.exe" in text
    assert "real-user-audit-2026-04-02.md" in text
    assert "THREE_LAYER_GRAPH.md" in text
    assert "ROUTE_COST_ENGINE_MODEL.md" in text
    assert "WINDOWS_DEMO_UX_REFERENCE.md" in text


def test_master_execution_index_covers_all_surfaces_and_phases() -> None:
    text = _read_doc("docs/architecture/CLAUDE_CODE_MASTER_EXECUTION_INDEX.md")

    for phrase in [
        "CLAUDE_CODE_START_HERE.md",
        "milestone transaction",
        "Backend Runtime Foundation",
        "Runtime Store, Governance, And Data Model",
        "Reference Network And Relationship Mapping",
        "Research Workflows",
        "SDK",
        "CLI",
        "Web Client",
        "Windows Client",
        "Release",
        "V1_FULL_PROJECT_RELEASE_SCOPE.md",
        "V1_FULL_PROJECT_RELEASE_EXECUTION_PLAN.md",
        "V1_RELEASE_MILESTONE_BACKLOG.md",
        "V1_RELEASE_ACCEPTANCE_MATRIX.md",
        "V1_RELEASE_EXECPLAN_TEMPLATE.md",
    ]:
        assert phrase in text


def test_full_v1_release_docs_are_precise_for_claude_execution() -> None:
    scope = _read_doc("docs/release/V1_FULL_PROJECT_RELEASE_SCOPE.md")
    plan = _read_doc("docs/release/V1_FULL_PROJECT_RELEASE_EXECUTION_PLAN.md")
    matrix = _read_doc("docs/release/V1_RELEASE_ACCEPTANCE_MATRIX.md")
    backlog = _read_doc("docs/release/V1_RELEASE_MILESTONE_BACKLOG.md")
    template = _read_doc("docs/release/V1_RELEASE_EXECPLAN_TEMPLATE.md")

    for phrase in [
        "Backend/API service",
        "Python SDK",
        "All V1 clients access runtime data through SDK/API boundaries",
        "CLI",
        "Web client",
        "Windows client",
        "route cost research workflow",
        "indicative netback research workflow",
        "shadow run paper-evaluation workflow",
    ]:
        assert phrase in scope

    for phrase in [
        "Milestone R1: DB Runtime Foundation",
        "Milestone R7: Route Cost And Indicative Netback",
        "Milestone R12: SDK Release Surface",
        "Milestone R13: CLI Release Surface",
        "Milestone R14: Web Research Workspace",
        "Milestone R15: Windows Client Package Shell",
        "Milestone R16: Release Pack And Final Validation",
        "Stop Rule",
        "create it from",
        "execute the milestone in the",
    ]:
        assert phrase in plan

    for phrase in [
        "Backend Runtime",
        "Data And Domain Slices",
        "SDK",
        "Required V1 surface",
        "CLI",
        "Web Client",
        "Windows Client",
        "Release Pack",
        "Final Release Gate",
    ]:
        assert phrase in matrix

    for phrase in [
        "R0",
        "R1",
        "R16",
        "V1_R7_ROUTE_COST_NETBACK_EXECPLAN.md",
        "V1_R14_WEB_RELEASE_WORKSPACE_EXECPLAN.md",
        "V1_R15_WINDOWS_RELEASE_SHELL_EXECPLAN.md",
        "Do Not Skip",
    ]:
        assert phrase in backlog

    for phrase in [
        "V1 Release ExecPlan Template",
        "plain Claude Code CLI",
        "Files To Create Or Modify",
        "DB Impact",
        "API Impact",
        "Data Policy",
        "Handoff Output",
    ]:
        assert phrase in template


def test_api_surface_blueprint_covers_target_route_groups() -> None:
    text = _read_doc("docs/api/API_SURFACE_BLUEPRINT.md")

    for phrase in [
        "/api/v1/runtime/status",
        "/api/v1/reference-network/nodes",
        "/api/v1/market/observations",
        "/api/v1/lng/observations",
        "/api/v1/storage/observations",
        "/api/v1/weather/observations",
        "/api/v1/research/route-cost",
        "/api/v1/research/netback",
        "/api/v1/research/shadow-run",
        "Forbidden Routes",
    ]:
        assert phrase in text


def test_data_model_blueprint_covers_canonical_entity_families() -> None:
    text = _read_doc("docs/data/CANONICAL_DATA_MODEL_BLUEPRINT.md")

    for phrase in [
        "Source And Lineage",
        "Geometry, Topology, And Market Mapping",
        "Market Observations",
        "LNG And Storage",
        "Weather And Demand Context",
        "Route Cost And Netback",
        "Feasibility And Allocation",
        "Monitoring, Nowcast, Strategy",
        "Research Output And Reporting",
        "Governance And Audit",
    ]:
        assert phrase in text


def test_research_workflow_blueprint_preserves_research_boundary() -> None:
    text = _read_doc("docs/product/RESEARCH_WORKFLOW_BLUEPRINT.md")

    for phrase in [
        "Route Cost",
        "Indicative Netback",
        "Feasibility",
        "Allocation Scenario",
        "Weather-Adjusted Nowcast",
        "Strategy Backtest",
        "Shadow Run",
        "Research Brief",
        "research_only: true",
        "Shadow run creates no orders",
    ]:
        assert phrase in text


def test_documentation_completion_audit_records_evidence_and_image_gap() -> None:
    text = _read_doc("data/documentation_handoff/project_docs_completion_audit.md")

    assert "Requirement Audit" in text
    assert "CLAUDE_CODE_START_HERE.md" in text
    assert "V1 requires SDK and clients use SDK/API" in text
    assert "WHOLE_PROJECT_CAPABILITY_BLUEPRINT.md" in text
    assert "CLAUDE_CODE_MASTER_EXECUTION_INDEX.md" in text
    assert "V1_FULL_PROJECT_RELEASE_SCOPE.md" in text
    assert "V1_RELEASE_MILESTONE_BACKLOG.md" in text
    assert "V1_RELEASE_EXECPLAN_TEMPLATE.md" in text
    assert "V1_RELEASE_ACCEPTANCE_MATRIX.md" in text
    assert "SDK_CLIENT_DESIGN_SPEC.md" in text
    assert "CLI_CLIENT_DESIGN_SPEC.md" in text
    assert "WEB_CLIENT_DESIGN_SPEC.md" in text
    assert "WINDOWS_CLIENT_DESIGN_SPEC.md" in text
    assert "No image file was available" in text


def test_claude_code_start_here_prevents_wrong_worktree_failure() -> None:
    text = _read_doc("CLAUDE_CODE_START_HERE.md")

    for phrase in [
        "Required Working Directory",
        r"C:\Users\qqshu\.codex\worktrees\71e0\EurogasNexus",
        "If Claude Code reports that these files do not exist",
        "Full-Permission Local Launch",
        "--dangerously-skip-permissions",
        r'--add-dir "C:\Users\qqshu\Desktop"',
        "Full V1 Goal Prompt",
        "first incomplete milestone",
        "No client may connect to PostgreSQL directly",
    ]:
        assert phrase in text


def test_execplans_do_not_require_codex_only_skills() -> None:
    paths = [
        ".agent/plans/CLI_M1_OPERATOR_COMMANDS_EXECPLAN.md",
        ".agent/plans/SDK_M1_API_CLIENT_EXECPLAN.md",
        ".agent/plans/WEB_M1_WORKSPACE_SHELL_EXECPLAN.md",
        ".agent/plans/WINDOWS_D1_DESKTOP_SHELL_EXECPLAN.md",
        "docs/release/V1_RELEASE_EXECPLAN_TEMPLATE.md",
    ]

    for path in paths:
        text = _read_doc(path)
        assert "REQUIRED SUB-SKILL" not in text
        assert "plain Claude Code CLI" in text


def test_no_ambiguity_directives_are_authoritative() -> None:
    text = _read_doc("docs/architecture/CLAUDE_CODE_IMPLEMENTATION_DIRECTIVES.md")

    for phrase in [
        "Authority Order",
        "Archived Desktop projects never outrank repository V1 docs",
        "No Ambiguous Implementation Choices",
        "Do not replace",
        "PostgreSQL with SQLite",
        "React/Vite with Next.js",
        "Tauri with Electron",
        "Documents Checkout Policy",
        "Required V1 Product Shape",
        "Fixed Client Stack",
        "Not approved in V1",
    ]:
        assert phrase in text


def test_realtime_market_intelligence_blueprint_covers_user_requirements() -> None:
    text = _read_doc("docs/product/REAL_TIME_MARKET_INTELLIGENCE_BLUEPRINT.md")

    for phrase in [
        "map-first workspace",
        "ECB",
        "ENTSOG",
        "GIE",
        "EEX",
        "Trayport",
        "ICE OCM",
        "Capacity And Contract Management",
        "HDD/CDD",
        "Strategy Shadow Run",
        "LLM-Assisted Analysis Layer",
        "Glossary",
        "candidate_action_for_review",
    ]:
        assert phrase in text


def test_client_stack_i18n_and_theme_are_fixed() -> None:
    stack = _read_doc("docs/clients/CLIENT_TECH_STACK.md")
    i18n = _read_doc("docs/clients/CLIENT_I18N_THEME_SPEC.md")

    for phrase in [
        "authoritative V1 library contract",
        "Library choices are fixed",
        "react",
        "maplibre-gl",
        "@deck.gl/core",
        "zustand",
        "i18next",
        "Do not use `rusqlite`, SQLite",
        "Electron is not approved",
        "not substitute another package or architecture",
    ]:
        assert phrase in stack

    for phrase in [
        "en-US",
        "zh-CN",
        "Simplified Chinese/Mandarin",
        "light",
        "dark",
        "system",
        "data-theme",
        "Missing translation keys fail tests",
    ]:
        assert phrase in i18n


def test_worktree_handoff_prevents_documents_checkout_ambiguity() -> None:
    text = _read_doc("docs/operations/WORKTREE_HANDOFF.md")

    for phrase in [
        r"C:\Users\qqshu\.codex\worktrees\71e0\EurogasNexus",
        r"C:\Users\qqshu\Documents\Eurogasnexus",
        "did not contain",
        "uncommitted work",
        "must not be deleted automatically",
        "Required cleanup path",
        "All five checks must print `True`",
    ]:
        assert phrase in text
