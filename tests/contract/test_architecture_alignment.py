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
        "Product Is Backend-First And Multi-Surface",
        "PostgreSQL Is Runtime Truth",
        "Live PostgreSQL Validation Is In The Current Release",
        "Stable API Prefix Is `/api`",
        "Domain Work Is Slice-Based",
        "Offline Work Is The Default For Local Agents",
        "Historical Projects Are Evidence, Not Source",
    ]:
        assert phrase in text

def test_live_postgresql_policy_is_explicit_and_safe() -> None:
    text = _read_doc("docs/operations/LIVE_POSTGRESQL.md")

    assert "Live PostgreSQL is part of runtime readiness" in text
    assert "App import must not connect to PostgreSQL" in text
    assert (
        "Default unit, API, contract, integration, and security tests must pass"
        in text
    )
    assert "must never be printed in full" in text
    assert "python scripts/ops/validate_runtime_db.py --json" in text


def test_client_design_docs_are_ready_for_current_client_runtime() -> None:
    index = _read_doc("docs/clients/README.md")
    sdk = _read_doc("docs/clients/SDK_CLIENT_DESIGN_SPEC.md")
    cli = _read_doc("docs/clients/CLI_CLIENT_DESIGN_SPEC.md")
    web = _read_doc("docs/clients/WEB_CLIENT_DESIGN_SPEC.md")
    windows = _read_doc("docs/clients/WINDOWS_CLIENT_DESIGN_SPEC.md")
    ui_standard = _read_doc("docs/clients/UI_CONTENT_STANDARDS.md")
    api_contract = _read_doc("docs/clients/CLIENT_API_CONTRACT.md")

    assert "CLIENT_DELIVERY_MILESTONES.md" in index
    assert "Clients are SDK/API consumers" in index
    assert "Client implementation is separated by surface" in _read_doc(
        "docs/clients/CLIENT_DELIVERY_MILESTONES.md"
    )
    assert "GET /api/health" in api_contract
    assert "Runtime Data Access Rule" in api_contract
    assert "Python SDK -> backend `/api`" in api_contract
    assert "No client may open a PostgreSQL connection" in api_contract
    assert "research_only" in api_contract
    assert "The Python SDK is the programmatic client" in sdk
    assert "The SDK is a required product surface" in sdk
    assert "The CLI is the operator and automation command surface" in cli
    assert "CLI -> Python SDK -> backend /api" in cli
    assert "single authoritative UI and content standard" in ui_standard
    assert "Top status bar" in web
    assert "Web UI -> web API client -> backend /api" in web
    assert "Tauri" in windows
    assert "Windows shell -> packaged web workspace/API client" in windows

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


def test_client_stack_i18n_and_theme_are_fixed() -> None:
    stack = _read_doc("docs/clients/CLIENT_TECH_STACK.md")
    i18n = _read_doc("docs/clients/CLIENT_I18N_THEME_SPEC.md")

    for phrase in [
        "authoritative client library contract",
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
