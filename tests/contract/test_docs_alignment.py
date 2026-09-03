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
