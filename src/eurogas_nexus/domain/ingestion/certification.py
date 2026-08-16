"""Provider certification gate (simulated-to-live, fail closed).

A licensed (non-simulated) provider adapter may only be treated as native live
after the operator records certification evidence through the simulated-to-live
test gate. The gate is pure logic: callers supply the persisted stage and
checks, and this module returns whether the source may be marked live.

Gate contract:

- stage ``unverified`` or ``simulation_matched``: never live.
- stage ``live_validated``: live only when the checks include BOTH
  ``simulated_shape_match`` (normalized live records match the simulated
  dataset shape) and ``live_sample_validation`` (a live sample was validated
  within tolerance against an independent reference).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from eurogas_nexus.domain.identity.principal import normalize_principal


class CertificationStage(StrEnum):
    """Certification lifecycle for a licensed source system."""

    UNVERIFIED = "unverified"
    SIMULATION_MATCHED = "simulation_matched"
    LIVE_VALIDATED = "live_validated"


REQUIRED_LIVE_CHECKS: tuple[str, ...] = (
    "simulated_shape_match",
    "live_sample_validation",
)

KNOWN_CHECKS: tuple[str, ...] = (
    *REQUIRED_LIVE_CHECKS,
    "credential_verified",
    "entitlement_confirmed",
    "schema_snapshot_attached",
    "sample_archived",
)


@dataclass(frozen=True)
class CertificationGateResult:
    """Outcome of the certification gate for one source system."""

    source_system: str
    stage: str
    allows_live: bool
    reason: str


def certification_gate(
    source_system: str,
    *,
    stage: str,
    checks: list[str] | None = None,
) -> CertificationGateResult:
    """Evaluate whether a source system may be treated as native live."""

    normalized_stage = str(stage or "").strip().lower()
    provided_checks = {str(check or "").strip().lower() for check in (checks or [])}

    if normalized_stage != CertificationStage.LIVE_VALIDATED.value:
        return CertificationGateResult(
            source_system=source_system,
            stage=normalized_stage or CertificationStage.UNVERIFIED.value,
            allows_live=False,
            reason=(
                "certification_stage_not_live_validated"
                if normalized_stage
                else "certification_missing"
            ),
        )

    missing = [check for check in REQUIRED_LIVE_CHECKS if check not in provided_checks]
    if missing:
        return CertificationGateResult(
            source_system=source_system,
            stage=normalized_stage,
            allows_live=False,
            reason=f"missing_required_checks:{','.join(missing)}",
        )
    return CertificationGateResult(
        source_system=source_system,
        stage=normalized_stage,
        allows_live=True,
        reason="certified",
    )


def validate_certification_payload(
    *,
    source_system: str,
    stage: str,
    checks: list[str],
    evidence: dict[str, Any],
    evaluated_by: str,
) -> None:
    """Validate an incoming certification record before persistence."""

    if not str(source_system or "").strip():
        raise ValueError("source_system is required.")
    normalize_principal(evaluated_by)
    try:
        CertificationStage(str(stage or "").strip().lower())
    except ValueError as exc:
        allowed = ", ".join(stage.value for stage in CertificationStage)
        raise ValueError(f"stage must be one of: {allowed}.") from exc
    normalized_checks = [str(check or "").strip().lower() for check in checks]
    unknown = [check for check in normalized_checks if check not in KNOWN_CHECKS]
    if unknown:
        raise ValueError(f"unknown certification checks: {', '.join(unknown)}.")
    if not isinstance(evidence, dict):
        raise ValueError("evidence must be a JSON object.")
    if CertificationStage(stage) is CertificationStage.LIVE_VALIDATED:
        missing = [check for check in REQUIRED_LIVE_CHECKS if check not in normalized_checks]
        if missing:
            raise ValueError(
                "live_validated requires checks: " + ", ".join(missing) + "."
            )
