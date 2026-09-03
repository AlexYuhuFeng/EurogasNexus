"""Explicit deployment-posture switch tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from eurogas_nexus.core.config import (
    DEPLOYMENT_POSTURE_ENV,
    SECURITY_ACCEPTANCE_EVIDENCE_ENV,
    DeploymentConfig,
    Settings,
    public_network_deployment_allowed,
    simulated_sources_allowed,
)


def test_default_deployment_posture_is_private_network_preview(monkeypatch) -> None:
    monkeypatch.delenv(DEPLOYMENT_POSTURE_ENV, raising=False)
    monkeypatch.delenv(SECURITY_ACCEPTANCE_EVIDENCE_ENV, raising=False)

    settings = Settings.from_env()

    assert settings.deployment.posture == "private_network_preview"
    allowed, reason = public_network_deployment_allowed(settings)
    assert allowed is False
    assert "private_network_preview" in reason


def test_security_accepted_requires_evidence_file(monkeypatch) -> None:
    monkeypatch.setenv(DEPLOYMENT_POSTURE_ENV, "security_accepted")
    monkeypatch.delenv(SECURITY_ACCEPTANCE_EVIDENCE_ENV, raising=False)

    settings = Settings.from_env()

    allowed, reason = public_network_deployment_allowed(settings)
    assert allowed is False
    assert "evidence path is not configured" in reason


def test_security_accepted_with_existing_evidence_file(monkeypatch, tmp_path) -> None:
    evidence = tmp_path / "acceptance.md"
    evidence.write_text("external review complete", encoding="utf-8")
    monkeypatch.setenv(DEPLOYMENT_POSTURE_ENV, "security_accepted")
    monkeypatch.setenv(SECURITY_ACCEPTANCE_EVIDENCE_ENV, str(evidence))

    settings = Settings.from_env()

    allowed, reason = public_network_deployment_allowed(settings)
    assert allowed is True
    assert str(evidence) in reason


def test_security_accepted_with_missing_evidence_file(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv(DEPLOYMENT_POSTURE_ENV, "security_accepted")
    monkeypatch.setenv(
        SECURITY_ACCEPTANCE_EVIDENCE_ENV,
        str(tmp_path / "does-not-exist.md"),
    )

    settings = Settings.from_env()

    allowed, reason = public_network_deployment_allowed(settings)
    assert allowed is False
    assert "evidence file not found" in reason


def test_invalid_deployment_posture_fails_validation(monkeypatch) -> None:
    monkeypatch.setenv(DEPLOYMENT_POSTURE_ENV, "public_internet")

    with pytest.raises(ValidationError):
        Settings.from_env()


def test_deployment_config_defaults() -> None:
    config = DeploymentConfig()

    assert config.posture == "private_network_preview"
    assert config.security_acceptance_evidence_path is None


def test_simulated_sources_allowed_in_development(monkeypatch) -> None:
    monkeypatch.setenv("EUROGAS_NEXUS_ENV", "development")
    monkeypatch.delenv("EUROGAS_NEXUS_ENABLE_SIMULATED_SOURCES", raising=False)

    assert simulated_sources_allowed() is True


def test_simulated_sources_denied_in_release(monkeypatch) -> None:
    monkeypatch.setenv("EUROGAS_NEXUS_ENV", "release")
    monkeypatch.setenv("EUROGAS_NEXUS_ENABLE_SIMULATED_SOURCES", "true")

    assert simulated_sources_allowed() is False


def test_simulated_sources_denied_in_trial(monkeypatch) -> None:
    monkeypatch.setenv("EUROGAS_NEXUS_ENV", "trial")
    monkeypatch.setenv("EUROGAS_NEXUS_ENABLE_SIMULATED_SOURCES", "true")

    assert simulated_sources_allowed() is False
