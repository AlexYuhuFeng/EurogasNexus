"""Documentation alignment contract tests."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_ownership_matrix_reflects_db_sdk_cli_status() -> None:
    text = (ROOT / "docs" / "contracts" / "20_MODULE_OWNERSHIP_MATRIX.md").read_text(
        encoding="utf-8"
    )

    assert "Import-safe DB foundation" in text
    assert "Read-only health API client shell" in text
    assert "Read-only health check helper shell" in text


def test_validation_doc_includes_active_test_suites() -> None:
    text = (ROOT / "docs" / "operations" / "VALIDATION.md").read_text(encoding="utf-8")

    assert "tests/integration" in text
    assert "tests/sdk" in text
    assert "tests/cli" in text


def test_readme_mentions_starting_docs_and_extended_validation() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "[Project directory](PROJECT_DIRECTORY.md)" in text
    assert "[Release readiness](docs/release/V1_RELEASE_READINESS.md)" in text
    assert "## Data Sources" in text
    assert "tests/integration tests/sdk tests/cli" in text


def test_resource_pool_contract_defines_home_and_efet_contract_entry() -> None:
    en = (ROOT / "docs" / "contracts" / "21_RESOURCE_POOL_CONTRACT-EN.md").read_text(
        encoding="utf-8"
    )
    cn = (ROOT / "docs" / "contracts" / "21_RESOURCE_POOL_CONTRACT-CN.md").read_text(
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


def test_current_guidance_reflects_active_web_and_windows_runtime() -> None:
    north_star = (ROOT / "docs" / "architecture" / "PROJECT_NORTH_STAR.md").read_text(
        encoding="utf-8"
    )
    queue = (ROOT / "docs" / "architecture" / "NEXT_DEVELOPMENT_QUEUE.md").read_text(
        encoding="utf-8"
    )
    client_index = (ROOT / "docs" / "clients" / "README.md").read_text(encoding="utf-8")
    master_plan = (
        ROOT / "docs" / "architecture" / "PRODUCT_DELIVERY_MASTER_PLAN.md"
    ).read_text(encoding="utf-8")

    assert "Web and Windows client surfaces are active" in north_star
    assert "Status: `complete-in-current-worktree`" in queue
    assert "V1 R22" in queue
    assert "active client runtime code" in client_index
    assert "Default next milestone" not in master_plan
    assert "No frontend runtime implementation belongs" not in north_star
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
