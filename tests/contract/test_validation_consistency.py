"""Validation command consistency contract tests."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_PYTEST = (
    "pytest -q tests/api tests/contract tests/integration tests/ingestion tests/unit "
    "tests/optimization tests/sdk tests/cli tests/release tests/security"
)


def test_validation_script_contains_expected_commands() -> None:
    text = (ROOT / "scripts" / "ops" / "validate_repo.sh").read_text(encoding="utf-8")
    assert "ruff check ." in text
    assert EXPECTED_PYTEST in text
    assert 'from apps.api.main import app' in text


def test_docs_reference_consistent_pytest_command() -> None:
    for rel in [
        "README.md",
        "docs/operations/VALIDATION.md",
        "docs/contracts/17_TESTING_CONTRACT.md",
    ]:
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert EXPECTED_PYTEST in text
