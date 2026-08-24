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
    """Evaluate whether a source system may be treated as native live.

    模拟转实时认证门禁：只有 stage 为 live_validated 且必需检查齐备时
    才允许 live（fail-closed）。

    Args:
        source_system: Source system being evaluated.
        stage: Persisted certification stage (any casing; normalized).
        checks: Persisted certification check ids, or None.

    Returns:
        A CertificationGateResult with ``allows_live`` False unless the
        stage is ``live_validated`` AND both required checks are present;
        the reason field carries a stable machine-readable code.
    """

    normalized_stage = str(stage or "").strip().lower()
    provided_checks = {str(check or "").strip().lower() for check in (checks or [])}

    if normalized_stage != CertificationStage.LIVE_VALIDATED.value:
        # 未到 live_validated 阶段：一律禁活；缺记录与阶段不足分开报因。
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
        # 阶段达标但检查缺失：仍禁活，缺哪项报哪项。
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
    """Validate an incoming certification record before persistence.

    持久化前的输入校验：来源系统、操作者主体、阶段、检查清单与证据
    逐项验证，任何一项不合法即抛错拒绝写入。

    Args:
        source_system: Non-empty source system id.
        stage: One of the CertificationStage values (any casing).
        checks: Check ids; all must be in KNOWN_CHECKS.
        evidence: JSON object with certification evidence.
        evaluated_by: Operator principal (see identity.principal).

    Returns:
        None when the payload is valid.

    Raises:
        ValueError: When any field violates its rule, including
            ``live_validated`` stages missing a required check.
    """

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
        # live_validated 阶段强制要求两项必需检查（与门禁规则一致）。
        missing = [check for check in REQUIRED_LIVE_CHECKS if check not in normalized_checks]
        if missing:
            raise ValueError(
                "live_validated requires checks: " + ", ".join(missing) + "."
            )
