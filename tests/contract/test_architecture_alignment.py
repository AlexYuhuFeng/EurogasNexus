"""Architecture alignment documentation contract tests."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read_doc(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_repository_has_no_legacy_handoff_surface() -> None:
    legacy_prefix = "CLAU" + "DE_CODE"
    forbidden_names = [
        f"{legacy_prefix}_START_HERE.md",
        f"{legacy_prefix}_DELIVERY_BRIEF.md",
        f"{legacy_prefix}_EXECUTION_PLAYBOOK.md",
        f"{legacy_prefix}_GOAL_MODE.md",
        f"{legacy_prefix}_IMPLEMENTATION_DIRECTIVES.md",
        f"{legacy_prefix}_MASTER_EXECUTION_INDEX.md",
        f"{legacy_prefix}_START_PROMPTS.md",
        "OFFLINE_" + legacy_prefix + "_GUIDE.md",
        "WORKTREE" + "_HANDOFF.md",
    ]

    for name in forbidden_names:
        assert not any(path.name == name for path in ROOT.rglob(name))

    searchable = [ROOT / "README.md", ROOT / "PROJECT_DIRECTORY.md", ROOT / "docs", ROOT / "data"]
    matches: list[str] = []
    for target in searchable:
        if not target.exists():
            continue
        files = [target] if target.is_file() else target.rglob("*.md")
        for file_path in files:
            if "node_modules" in file_path.parts:
                continue
            content = file_path.read_text(encoding="utf-8")
            lowered = content.lower()
            if "clau" + "de code" in lowered or legacy_prefix in content:
                matches.append(str(file_path.relative_to(ROOT)))

    assert matches == []


def test_project_north_star_preserves_v1_boundaries() -> None:
    text = _read_doc("docs/architecture/PROJECT_NORTH_STAR.md")

    assert "decision-support, market-intelligence, and" in text.lower()
    assert "strategy shadow-run workspace" in text.lower()
    assert "PostgreSQL" in text
    assert "API-first" in text
    assert "SDK-ready" in text
    assert "Web and Windows client surfaces are active" in text
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
    assert "/api" in text
    assert "research_only" in text
    assert "human_review_required" in text

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
        "Stable API Prefix Is `/api`",
        "Domain Work Is Slice-Based",
        "Offline Work Is The Default For Local Agents",
        "Historical Projects Are Evidence, Not Source",
    ]:
        assert phrase in text

def test_next_development_queue_records_r30_and_selects_db_backed_optimization() -> None:
    text = _read_doc("docs/architecture/NEXT_DEVELOPMENT_QUEUE.md")

    assert "R30: Optimization Correctness And Release Gate" in text
    assert ".agent/plans/V1_R30_OPTIMIZATION_CORRECTNESS_EXECPLAN.md" in text
    assert "R30B: Intraday Decision Feed" in text
    assert ".agent/plans/V1_R30B_INTRADAY_DECISION_FEED_EXECPLAN.md" in text
    assert "R31: DB-Backed Portfolio Network Optimization" in text
    assert "Status: `pending`" in text
    assert "R32: Authentication, Entitlement, Audit, And Export Governance" in text


def test_current_pause_point_records_holistic_runtime_pause_state() -> None:
    text = _read_doc("docs/architecture/CURRENT_PAUSE_POINT.md")

    assert "`0.5.0` preview-release worktree" in text
    assert "0013_gie_lng_dtmi_energy" in text
    assert "0014_intraday_decision_feed" in text
    assert "33" in text
    assert "36" in text
    assert "82" in text
    assert "Windows/Linux desktop clients" in text
    assert "Linux ARM64" in text
    assert "screen_order_observations" in text
    assert "/api/internal" in text
    assert "Provider credentials are backend-owned" in text
    assert "DB-backed portfolio network optimization" in text


def test_live_postgresql_policy_is_explicit_and_safe() -> None:
    text = _read_doc("docs/operations/LIVE_POSTGRESQL.md")

    assert "Live PostgreSQL is part of runtime readiness" in text
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
    assert "GET /api/health" in api_contract
    assert "Runtime Data Access Rule" in api_contract
    assert "Python SDK -> backend `/api`" in api_contract
    assert "No client may open a PostgreSQL connection" in api_contract
    assert "research_only" in api_contract
    assert "The Python SDK is the programmatic client" in sdk
    assert "The SDK is a required V1 product surface" in sdk
    assert "The CLI is the operator and automation command surface" in cli
    assert "CLI -> Python SDK -> backend /api" in cli
    assert "First screen is the workspace" in design_system
    assert "Top status bar" in web
    assert "Web UI -> web API client -> backend /api" in web
    assert "Web UI -> web API client -> backend /api" in web
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

def test_full_v1_release_docs_are_precise_for_local_execution() -> None:
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
        "plain local CLI",
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
        "/api/runtime/status",
        "/api/reference-network/nodes",
        "/api/market/observations",
        "/api/lng/observations",
        "/api/storage/observations",
        "/api/weather/observations",
        "/api/route-cost/calculate",
        "/api/route-cost/resource-pool/options",
        "/api/research/netback",
        "/api/research/shadow-run",
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
