"""Tests for the deployment configuration preflight.

The preflight exists because the failure mode without it is silence: a missing
credential-encryption key raised only when the first provider credential was
written, and a half-configured OIDC block answered 503 only when a user clicked
sign-in. Each check below therefore asserts both that the defect is reported and
that a correct environment stays clean.
"""

from __future__ import annotations

import base64
import os

import pytest

from eurogas_nexus.core.preflight import check_environment

VALID_SECRET_KEY = "1mDk0Q0m9K4pXc2rWb7tLzYvHsAeNfRgUjOiPlMnQ4E="

DEV_BASE = {
    "EUROGAS_NEXUS_ENV": "development",
    "EUROGAS_NEXUS_API_PROFILE": "development",
    "EUROGAS_NEXUS_PUBLIC_API_TOKEN": "local-dev-token-not-a-real-credential",
    "EUROGAS_NEXUS_SECRET_KEY": VALID_SECRET_KEY,
    # A development browser is served from the Vite dev server on its own port, so
    # the origin guard cannot derive the browser's Origin from Host. Declaring it is
    # part of a correct development environment, not an optional extra: without it
    # every cookie-authenticated mutation is refused with origin_not_allowed.
    "EUROGAS_NEXUS_CORS_ORIGINS": "http://127.0.0.1:3000",
}

RELEASE_BASE = {
    **DEV_BASE,
    "EUROGAS_NEXUS_ENV": "release",
    "EUROGAS_NEXUS_API_PROFILE": "release",
    "RUNTIME_STORE_DATABASE_URL": "postgresql+pg8000://nexus:pw@db:5432/nexus",
    "FORWARDED_ALLOW_IPS": "172.16.0.0/12",
}


def codes(environ: dict[str, str]) -> list[str]:
    return [finding.code for finding in check_environment(environ).findings]


def finding_for(environ: dict[str, str], code: str):
    matches = [item for item in check_environment(environ).findings if item.code == code]
    assert matches, f"expected a {code} finding, got {codes(environ)}"
    return matches[0]


# --- baseline ---------------------------------------------------------------


def test_a_complete_development_environment_is_clean() -> None:
    report = check_environment(dict(DEV_BASE))
    assert report.findings == []
    assert report.ok is True


def test_a_complete_release_environment_is_clean() -> None:
    report = check_environment(dict(RELEASE_BASE))
    assert report.findings == []
    assert report.ok is True


def test_empty_environment_reports_every_missing_requirement() -> None:
    report = check_environment({})
    missing = {item.variable for item in report.findings if item.code == "missing_required"}
    assert "EUROGAS_NEXUS_PUBLIC_API_TOKEN" in missing
    assert "EUROGAS_NEXUS_SECRET_KEY" in missing
    assert report.ok is False


# --- required variables -----------------------------------------------------


def test_runtime_store_is_required_for_release() -> None:
    environ = dict(RELEASE_BASE)
    environ.pop("RUNTIME_STORE_DATABASE_URL")
    finding = finding_for(environ, "missing_required")
    assert finding.variable == "RUNTIME_STORE_DATABASE_URL"


def test_runtime_store_is_not_required_for_a_dbless_development_session() -> None:
    assert "missing_required" not in codes(dict(DEV_BASE))


def test_internal_profile_requires_its_token() -> None:
    """The internal token is missing; the runtime store is separately required."""

    environ = {**DEV_BASE, "EUROGAS_NEXUS_API_PROFILE": "internal"}
    missing = {
        item.variable
        for item in check_environment(environ).findings
        if item.code == "missing_required"
    }
    assert "EUROGAS_NEXUS_INTERNAL_API_TOKEN" in missing


def test_database_alias_satisfies_the_runtime_store_requirement() -> None:
    """Any accepted alias satisfies the requirement, not just the canonical name."""

    for alias in ("DATABASE_URL", "EUROGAS_NEXUS_DB_DSN"):
        environ = dict(RELEASE_BASE)
        environ.pop("RUNTIME_STORE_DATABASE_URL")
        environ[alias] = "postgresql+pg8000://nexus:pw@db:5432/nexus"
        missing = {
            item.variable
            for item in check_environment(environ).findings
            if item.code == "missing_required"
        }
        assert "RUNTIME_STORE_DATABASE_URL" not in missing, alias


# --- unknown variables and typos -------------------------------------------


def test_a_misspelled_variable_is_reported_with_the_intended_name() -> None:
    environ = {**DEV_BASE, "EUROGAS_NEXUS_OIDC_ISUER": "https://idp.example.test"}
    finding = finding_for(environ, "unknown_variable")
    assert finding.variable == "EUROGAS_NEXUS_OIDC_ISUER"
    assert "EUROGAS_NEXUS_OIDC_ISSUER" in finding.remedy


def test_a_removed_flag_is_reported_without_a_misleading_suggestion() -> None:
    environ = {**DEV_BASE, "EUROGAS_NEXUS_ALLOW_FILE_FALLBACK": "true"}
    finding = finding_for(environ, "unknown_variable")
    assert finding.variable == "EUROGAS_NEXUS_ALLOW_FILE_FALLBACK"
    assert "did you mean" not in finding.remedy


def test_non_product_variables_are_ignored() -> None:
    environ = {**DEV_BASE, "PATH": "/usr/bin", "RANDOM_THING": "1"}
    assert "unknown_variable" not in codes(environ)


# --- secret quality ---------------------------------------------------------


def test_placeholder_secret_key_is_an_error() -> None:
    environ = {**DEV_BASE, "EUROGAS_NEXUS_SECRET_KEY": "secret"}
    finding = finding_for(environ, "placeholder_secret")
    assert finding.variable == "EUROGAS_NEXUS_SECRET_KEY"


def test_placeholder_api_token_is_an_error() -> None:
    environ = {**DEV_BASE, "EUROGAS_NEXUS_PUBLIC_API_TOKEN": "changeme"}
    finding = finding_for(environ, "placeholder_secret")
    assert finding.variable == "EUROGAS_NEXUS_PUBLIC_API_TOKEN"


def test_non_fernet_secret_key_warns_rather_than_failing() -> None:
    """The product hashes any other value, so this is a warning, not an error."""

    environ = {**DEV_BASE, "EUROGAS_NEXUS_SECRET_KEY": "a-fairly-long-but-not-a-fernet-key"}
    report = check_environment(environ)
    assert "secret_key_not_fernet" in [item.code for item in report.warnings]
    assert report.ok is True


def test_short_secret_key_warns() -> None:
    environ = {**DEV_BASE, "EUROGAS_NEXUS_SECRET_KEY": "short"}
    assert "secret_key_short" in codes(environ)


def test_secret_key_is_reported_once_per_defect_class() -> None:
    """A placeholder key must not be reported twice under different codes."""

    environ = {**DEV_BASE, "EUROGAS_NEXUS_SECRET_KEY": "changeme"}
    key_findings = [
        item
        for item in check_environment(environ).findings
        if item.variable == "EUROGAS_NEXUS_SECRET_KEY"
    ]
    assert len(key_findings) == 1


def test_a_generated_fernet_key_passes() -> None:
    generated = base64.urlsafe_b64encode(os.urandom(32)).decode()
    assert "secret_key_not_fernet" not in codes(
        {**DEV_BASE, "EUROGAS_NEXUS_SECRET_KEY": generated}
    )


# --- production guards ------------------------------------------------------


@pytest.mark.parametrize(
    "name,value",
    [
        ("EUROGAS_NEXUS_ALLOW_ANONYMOUS_CALLERS", "1"),
        ("EUROGAS_NEXUS_OIDC_ALLOW_HTTP", "1"),
        ("EUROGAS_NEXUS_DB_ECHO", "true"),
        ("EUROGAS_NEXUS_UAT_FIXTURE_ALLOWED", "1"),
        ("EUROGAS_NEXUS_DEV_LOGIN_USERNAME", "operator"),
        ("EUROGAS_NEXUS_DEV_LOGIN_PASSWORD", "hunter2"),
    ],
)
def test_development_switches_are_refused_in_release(name: str, value: str) -> None:
    environ = {**RELEASE_BASE, name: value}
    finding = finding_for(environ, "dev_setting_in_production")
    assert finding.variable == name


def test_the_same_switches_are_allowed_in_development() -> None:
    environ = {
        **DEV_BASE,
        "EUROGAS_NEXUS_DEV_LOGIN_USERNAME": "operator",
        "EUROGAS_NEXUS_DEV_LOGIN_PASSWORD": "hunter2",
        "EUROGAS_NEXUS_DB_ECHO": "true",
    }
    assert "dev_setting_in_production" not in codes(environ)


def test_disabled_guards_are_not_reported() -> None:
    environ = {
        **RELEASE_BASE,
        "EUROGAS_NEXUS_ALLOW_ANONYMOUS_CALLERS": "0",
        "EUROGAS_NEXUS_DB_ECHO": "false",
    }
    assert "dev_setting_in_production" not in codes(environ)


# --- LLM egress -------------------------------------------------------------


def test_llm_egress_is_flagged_in_development() -> None:
    environ = {**DEV_BASE, "EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED": "1"}
    finding = finding_for(environ, "llm_egress_enabled")
    assert finding.severity == "warning"


def test_llm_egress_is_not_flagged_in_release() -> None:
    """Trial and release force the provider off, so the variable cannot matter."""

    environ = {**RELEASE_BASE, "EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED": "1"}
    assert "llm_egress_enabled" not in codes(environ)


# --- OIDC -------------------------------------------------------------------


def test_partial_oidc_configuration_is_an_error() -> None:
    """Setting only the issuer leaves the two dependent values unset."""

    environ = {**DEV_BASE, "EUROGAS_NEXUS_OIDC_ISSUER": "https://idp.example.test"}
    finding = finding_for(environ, "oidc_partially_configured")
    # The finding names what is missing, which is what the operator must supply.
    assert "EUROGAS_NEXUS_OIDC_CLIENT_ID" in (finding.variable or "")
    assert "EUROGAS_NEXUS_OIDC_REDIRECT_URI" in (finding.variable or "")
    assert "EUROGAS_NEXUS_OIDC_ISSUER" not in (finding.variable or "")


def test_unconfigured_oidc_is_not_an_error() -> None:
    assert "oidc_partially_configured" not in codes(dict(DEV_BASE))


def test_complete_oidc_configuration_passes() -> None:
    environ = {
        **DEV_BASE,
        "EUROGAS_NEXUS_OIDC_ISSUER": "https://idp.example.test",
        "EUROGAS_NEXUS_OIDC_CLIENT_ID": "nexus",
        "EUROGAS_NEXUS_OIDC_REDIRECT_URI": "https://nexus.example.test/api/auth/oidc/callback",
    }
    assert check_environment(environ).findings == []


def test_unknown_provisioning_mode_is_an_error() -> None:
    environ = {
        **DEV_BASE,
        "EUROGAS_NEXUS_OIDC_ISSUER": "https://idp.example.test",
        "EUROGAS_NEXUS_OIDC_CLIENT_ID": "nexus",
        "EUROGAS_NEXUS_OIDC_REDIRECT_URI": "https://nexus.example.test/api/auth/oidc/callback",
        "EUROGAS_NEXUS_OIDC_PROVISIONING_MODE": "anything-goes",
    }
    assert "oidc_provisioning_mode_invalid" in codes(environ)


# --- topology and posture ---------------------------------------------------


def test_missing_trusted_proxy_hop_warns_in_release() -> None:
    environ = dict(RELEASE_BASE)
    environ.pop("FORWARDED_ALLOW_IPS")
    finding = finding_for(environ, "proxy_hop_not_trusted")
    assert finding.severity == "warning"


def test_trusted_proxy_hop_is_not_required_in_development() -> None:
    assert "proxy_hop_not_trusted" not in codes(dict(DEV_BASE))


def test_development_profile_without_a_browser_origin_warns() -> None:
    """A development browser session would have every mutation refused.

    The Vite dev server runs on its own port, so the browser's Origin names that
    port while the origin guard derives the expected value from Host. Without
    ``EUROGAS_NEXUS_CORS_ORIGINS`` the guard refuses with ``origin_not_allowed``,
    which the browser reports as a console error that does not name the cause. The
    CI browser-acceptance job sets the variable; this warns the developer who does
    not.
    """

    finding = finding_for(
        {k: v for k, v in DEV_BASE.items() if k != "EUROGAS_NEXUS_CORS_ORIGINS"},
        "dev_origin_not_declared",
    )
    assert finding.severity == "warning"
    assert finding.variable == "EUROGAS_NEXUS_CORS_ORIGINS"
    assert "http://127.0.0.1:3000" in finding.remedy


def test_declaring_the_browser_origin_clears_the_warning() -> None:
    environ = {**DEV_BASE, "EUROGAS_NEXUS_CORS_ORIGINS": "http://127.0.0.1:3000"}
    assert "dev_origin_not_declared" not in codes(environ)


def test_release_does_not_need_a_declared_browser_origin() -> None:
    """In production the guard derives the origin from Host, so nothing is required."""

    environ = dict(RELEASE_BASE)
    environ.pop("EUROGAS_NEXUS_CORS_ORIGINS", None)
    assert "dev_origin_not_declared" not in codes(environ)


def test_a_non_development_profile_does_not_need_a_browser_origin() -> None:
    """Only the development route profile mounts a browser sign-in."""

    environ = {**DEV_BASE, "EUROGAS_NEXUS_API_PROFILE": "internal"}
    assert "dev_origin_not_declared" not in codes(environ)


def test_security_posture_without_evidence_is_an_error() -> None:
    environ = {**RELEASE_BASE, "EUROGAS_NEXUS_DEPLOYMENT_POSTURE": "security_accepted"}
    assert "security_evidence_missing" in codes(environ)


def test_security_posture_with_a_missing_file_is_an_error() -> None:
    environ = {
        **RELEASE_BASE,
        "EUROGAS_NEXUS_DEPLOYMENT_POSTURE": "security_accepted",
        "EUROGAS_NEXUS_SECURITY_ACCEPTANCE_EVIDENCE": "/nonexistent/acceptance.md",
    }
    assert "security_evidence_not_found" in codes(environ)


def test_security_posture_with_a_real_file_passes(tmp_path) -> None:
    evidence = tmp_path / "acceptance.md"
    evidence.write_text("reviewed", encoding="utf-8")
    environ = {
        **RELEASE_BASE,
        "EUROGAS_NEXUS_DEPLOYMENT_POSTURE": "security_accepted",
        "EUROGAS_NEXUS_SECURITY_ACCEPTANCE_EVIDENCE": str(evidence),
    }
    assert check_environment(environ).findings == []


# --- report shape -----------------------------------------------------------


def test_report_exposes_severities() -> None:
    environ = {**RELEASE_BASE, "EUROGAS_NEXUS_DB_ECHO": "true"}
    environ.pop("FORWARDED_ALLOW_IPS")
    report = check_environment(environ)
    assert report.environment == "release"
    assert report.api_profile == "release"
    assert len(report.errors) == 1
    assert len(report.warnings) == 1
    assert report.ok is False


def test_findings_render_with_a_remedy() -> None:
    environ = {**DEV_BASE, "EUROGAS_NEXUS_SECRET_KEY": "changeme"}
    rendered = finding_for(environ, "placeholder_secret").render()
    assert "ERROR" in rendered
    assert "fix:" in rendered
