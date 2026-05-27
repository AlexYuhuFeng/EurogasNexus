"""Release-readiness contract tests."""

from pathlib import Path

from eurogas_nexus.api.app import create_app
from eurogas_nexus.core.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def test_release_profile_disables_docs_and_openapi() -> None:
    app = create_app(Settings(api_profile="release"))

    assert app.docs_url is None
    assert app.redoc_url is None
    assert app.openapi_url is None


def test_release_readiness_doc_records_partial_state_and_gates() -> None:
    text = (ROOT / "docs" / "release" / "V1_RELEASE_READINESS.md").read_text(encoding="utf-8")

    assert "`PARTIAL`" in text
    assert "No development-only routes enabled in release profile" in text
    assert "No silent local file fallback in trial or release mode" in text


def test_validation_doc_includes_release_test_suite() -> None:
    text = (ROOT / "docs" / "operations" / "VALIDATION.md").read_text(encoding="utf-8")

    assert "tests/release" in text
