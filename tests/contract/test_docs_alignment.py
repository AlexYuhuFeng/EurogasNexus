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


def test_readme_mentions_execplans_and_extended_validation() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "ExecPlans: `.agent/plans/`" in text
    assert "tests/integration tests/sdk tests/cli" in text
