"""Provider certification gate tests (fail-closed simulated-to-live)."""

import pytest

from eurogas_nexus.domain.ingestion.certification import (
    REQUIRED_LIVE_CHECKS,
    CertificationStage,
    certification_gate,
    validate_certification_payload,
)


def test_unverified_and_simulation_matched_never_allow_live() -> None:
    for stage in (
        CertificationStage.UNVERIFIED.value,
        CertificationStage.SIMULATION_MATCHED.value,
        "",
    ):
        result = certification_gate("EEX", stage=stage, checks=list(REQUIRED_LIVE_CHECKS))
        assert result.allows_live is False
        assert result.stage in {"unverified", "simulation_matched"}


def test_live_validated_requires_both_required_checks() -> None:
    missing_one = certification_gate(
        "EEX",
        stage=CertificationStage.LIVE_VALIDATED.value,
        checks=[REQUIRED_LIVE_CHECKS[0]],
    )
    assert missing_one.allows_live is False
    assert "missing_required_checks" in missing_one.reason

    complete = certification_gate(
        "EEX",
        stage=CertificationStage.LIVE_VALIDATED.value,
        checks=list(REQUIRED_LIVE_CHECKS),
    )
    assert complete.allows_live is True
    assert complete.reason == "certified"


def test_missing_certification_row_fails_closed() -> None:
    result = certification_gate("EEX", stage="unverified", checks=None)
    assert result.allows_live is False
    assert result.reason == "certification_stage_not_live_validated"


def test_validate_certification_payload_rejects_invalid_records() -> None:
    base = {
        "source_system": "EEX",
        "stage": CertificationStage.LIVE_VALIDATED.value,
        "checks": list(REQUIRED_LIVE_CHECKS),
        "evidence": {"reference": "eex-replay-2026-07"},
        "evaluated_by": "ops-user",
    }
    validate_certification_payload(**base)

    with pytest.raises(ValueError, match="source_system is required"):
        validate_certification_payload(**{**base, "source_system": "  "})
    with pytest.raises(ValueError, match="stage must be one of"):
        validate_certification_payload(**{**base, "stage": "blessed"})
    with pytest.raises(ValueError, match="unknown certification checks"):
        validate_certification_payload(**{**base, "checks": ["vibes"]})
    with pytest.raises(ValueError, match="requires checks"):
        validate_certification_payload(**{**base, "checks": [REQUIRED_LIVE_CHECKS[0]]})
    with pytest.raises(ValueError, match="evidence must be a JSON object"):
        validate_certification_payload(**{**base, "evidence": ["not", "a", "dict"]})
