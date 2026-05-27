"""Security boundary contract tests."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_auth_audit_contract_keeps_bootstrap_forbidden_items() -> None:
    text = (ROOT / "docs" / "contracts" / "13_AUTH_AUDIT_CONTRACT.md").read_text(
        encoding="utf-8"
    )

    assert "Company SSO/OIDC" in text
    assert "Production identity-provider calls" in text
    assert "Importing the API must not contact identity providers" in text


def test_governance_contract_requires_fail_closed_entitlement() -> None:
    text = (ROOT / "docs" / "contracts" / "14_GOVERNANCE_ENTITLEMENT_CONTRACT.md").read_text(
        encoding="utf-8"
    )

    assert "fail closed" in text.lower()
    assert "research-only" in text
    assert "Official trading recommendations" in text


def test_validation_doc_includes_security_suite() -> None:
    text = (ROOT / "docs" / "operations" / "VALIDATION.md").read_text(encoding="utf-8")

    assert "tests/security" in text
