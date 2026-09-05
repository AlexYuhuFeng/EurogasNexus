"""Documentation alignment contract tests."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_ownership_matrix_reflects_db_sdk_cli_status() -> None:
    text = (ROOT / "docs" / "architecture" / "MODULE_OWNERSHIP_MATRIX.md").read_text(
        encoding="utf-8"
    )

    assert "Import-safe DB foundation" in text
    assert "Read-only health API client shell" in text
    assert "Read-only health check helper shell" in text


def test_validation_doc_includes_full_suite_command() -> None:
    text = (ROOT / "docs" / "operations" / "VALIDATION.md").read_text(encoding="utf-8")

    assert "pytest -q tests" in text
    assert "ruff check ." in text


def test_readme_mentions_starting_docs_and_full_suite_validation() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "[Project directory and ownership](PROJECT_DIRECTORY.md)" in text
    assert "[Release readiness](docs/release/RELEASE_READINESS.md)" in text
    assert "## Documentation map" in text
    assert "pytest -q tests" in text
    assert "中文说明：" in text


def test_governance_documents_and_indexes_are_registered() -> None:
    """Public governance documents must exist and be reachable from both indexes."""
    governance = [
        "engineering/README.md",
        "engineering/RFC_PROCESS.md",
        "engineering/RFC_INDEX.md",
        "engineering/RFC_TEMPLATE.md",
        "engineering/EXECPLAN_INDEX.md",
        "engineering/EXECPLAN_TEMPLATE.md",
    ]
    english = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    mandarin = (ROOT / "docs" / "README-CN.md").read_text(encoding="utf-8")

    for relative_path in governance:
        assert (ROOT / "docs" / relative_path).is_file()
        assert f"]({relative_path})" in english
        assert f"]({relative_path})" in mandarin

    assert "RFC 2119" in (ROOT / "docs" / "engineering" / "RFC_PROCESS.md").read_text(
        encoding="utf-8"
    )
    assert "RFC 8174" in (ROOT / "docs" / "engineering" / "RFC_PROCESS.md").read_text(
        encoding="utf-8"
    )
    adr = (ROOT / "docs" / "architecture" / "ARCHITECTURE_DECISION_RECORD.md").read_text(
        encoding="utf-8"
    )
    assert "ADR-0013" in adr
    assert "ADR-0014" in adr


def test_documentation_indexes_have_required_bilingual_inventory() -> None:
    """English and Mandarin navigation must expose the same release-critical docs."""
    english = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    mandarin = (ROOT / "docs" / "README-CN.md").read_text(encoding="utf-8")
    required_paths = [
        "api/DATA_SCIENCE_FUNCTIONS.md",
        "architecture/TESTING_CONTRACT.md",
        "operations/INCIDENT_RESPONSE.md",
        "operations/RELEASE_SIGNING.md",
        "operations/PROVIDER_VALIDATION.md",
        "operations/COST_OBSERVATION_SOURCES.md",
    ]

    for relative_path in required_paths:
        assert f"]({relative_path})" in english
        assert f"]({relative_path})" in mandarin


def test_documented_root_layout_matches_tracked_source_tree() -> None:
    """The directory map must cover tracked roots without requiring generated paths."""
    directory_map = (ROOT / "PROJECT_DIRECTORY.md").read_text(encoding="utf-8")
    tracked_roots = [
        "apps",
        "clients",
        "data",
        "deploy",
        "dist/releases",
        "docs",
        "infra",
        "packages",
        "packages/python-sdk",
        "scripts",
        "src",
        "tests",
    ]

    for name in tracked_roots:
        assert (ROOT / name).is_dir(), name
    assert "dist/releases/" in directory_map
    assert "packages/" in directory_map
    assert "packages/python-sdk/" in directory_map

    assert "packaging/" not in directory_map
    assert "\nrelease/" not in directory_map
    optional_paths = ("release-assets/", "output/", "tmp/")
    assert all(path in directory_map for path in optional_paths)
    deployment = (ROOT / "docs" / "release" / "DEPLOYMENT_CONTRACT.md").read_text(
        encoding="utf-8"
    )
    assert "release-assets/" in deployment
    assert "clients/desktop/src-tauri/target/release/bundle/" in deployment


def test_current_docs_use_public_plan_workflow_and_preview_version() -> None:
    """Current guidance must not point at deleted plans or imply GA status."""
    current_docs = [
        ROOT / "docs" / "architecture" / "API_CONTRACT_EVOLUTION_POLICY.md",
        ROOT / "docs" / "architecture" / "API_CONTRACT_EVOLUTION_POLICY-CN.md",
        ROOT / "docs" / "clients" / "SDK_CLI_CONTRACT.md",
        ROOT / "docs" / "clients" / "CLIENT_DELIVERY_MILESTONES.md",
        ROOT / "docs" / "clients" / "CLI_CLIENT_DESIGN_SPEC.md",
        ROOT / "docs" / "clients" / "SDK_CLIENT_DESIGN_SPEC.md",
    ]
    stale_plan_names = (
        "SDK_M1_API_CLIENT_EXECPLAN.md",
        "CLI_M1_OPERATOR_COMMANDS_EXECPLAN.md",
        "WEB_M1_WORKSPACE_SHELL_EXECPLAN.md",
        "WINDOWS_D1_DESKTOP_SHELL_EXECPLAN.md",
        "V1_R22_DOCS_CLIENT_COCKPIT_ALIGNMENT_EXECPLAN.md",
    )
    for path in current_docs:
        text = path.read_text(encoding="utf-8")
        assert "docs/engineering/plans/" not in text
        assert not any(name in text for name in stale_plan_names)

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "Package version: `0.5.0`" in readme
    assert "Channel: `preview`" in readme
    assert "not a production or GA release" in readme
    assert "package version `0.5.0`" in changelog
    assert "not a production multi-user or GA deployment" in changelog
    deployment_contract = (ROOT / "docs" / "release" / "DEPLOYMENT_CONTRACT.md").read_text(
        encoding="utf-8"
    )
    assert "separate Client-only Windows NSIS asset" in deployment_contract
    assert "Server" in deployment_contract and "operator ZIP asset" in deployment_contract
    assert "not a Server NSIS installer" in deployment_contract
    assert "does not" in deployment_contract
    assert "embed the desktop Client or API image" in deployment_contract
    assert "one-click" not in deployment_contract
    for deployment_doc in ("DEPLOYMENT_ROLES-EN.md", "DEPLOYMENT_ROLES-CN.md"):
        deployment = (ROOT / "docs" / "deployment" / deployment_doc).read_text(
            encoding="utf-8"
        )
        assert "0.5.0" in deployment
    english_roles = (ROOT / "docs" / "deployment" / "DEPLOYMENT_ROLES-EN.md").read_text(
        encoding="utf-8"
    )
    mandarin_roles = (ROOT / "docs" / "deployment" / "DEPLOYMENT_ROLES-CN.md").read_text(
        encoding="utf-8"
    )
    assert "published as a separate GitHub Release asset" in english_roles
    assert "not included in the Server operator ZIP" in english_roles
    assert "作为独立的 GitHub Release 产物发布" in mandarin_roles
    assert "不包含在 Server 运维 ZIP 包中" in mandarin_roles
    assert "Server therefore\nrequire" not in english_roles
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    assert 'TAG="v0.5-${CHANNEL}-${GITHUB_RUN_NUMBER}-${SHORT_SHA}"' in workflow


def test_resource_pool_contract_defines_home_and_efet_contract_entry() -> None:
    en = (ROOT / "docs" / "architecture" / "RESOURCE_POOL_CONTRACT-EN.md").read_text(
        encoding="utf-8"
    )
    cn = (ROOT / "docs" / "architecture" / "RESOURCE_POOL_CONTRACT-CN.md").read_text(
        encoding="utf-8"
    )
    cockpit = (
        ROOT / "docs" / "clients" / "MAP_FIRST_TRADER_COCKPIT_SPEC-EN.md"
    ).read_text(encoding="utf-8")

    assert "resource-pool-native" in en
    assert "EFET-style term-sheet" in en
    assert "contract-level attribution" in en
    assert "cheapest path has only partial capacity" in en
    assert "资源池原生" in cn
    assert "EFET" in cn
    assert "合同层面的归因" in cn
    assert "Resource-Pool Decision Rail" in cockpit
    assert "contract-level PnL attribution" in cockpit


def test_current_guidance_reflects_active_client_runtime() -> None:
    client_index = (ROOT / "docs" / "clients" / "README.md").read_text(encoding="utf-8")
    release = (ROOT / "docs" / "release" / "RELEASE_READINESS.md").read_text(
        encoding="utf-8"
    )

    assert "RELEASE CANDIDATE" in release
    assert "Validated Gates" in release
    assert "active client runtime code" in client_index
    assert "runtime client implementation starts only" not in client_index


def test_selected_mandarin_docs_are_readable_not_mojibake() -> None:
    docs = [
        ROOT / "docs" / "clients" / "MARKET_POSITIONING_COCKPIT_SPEC-CN.md",
        ROOT / "docs" / "operations" / "MARKET_POSITIONING_IMPORTS-CN.md",
    ]
    forbidden_markers = ["涓", "鍐", "鏁", "鐢", "鏃", "绠", "璺", "銆"]

    for doc in docs:
        text = doc.read_text(encoding="utf-8")
        assert "\ufffd" not in text
        assert not any("\ue000" <= char <= "\uf8ff" for char in text)
        assert not any(marker in text for marker in forbidden_markers)
        assert "Eurogas Nexus" in text
        assert "PostgreSQL" in text
        assert "决策支持" in text
