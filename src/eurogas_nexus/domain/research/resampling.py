"""Versioned, bounded resampling policies.

No global ``ffill`` is allowed. Every carry-forward/interpolation choice is
part of a versioned policy and carries an explicit maximum age.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ResamplingAggregation(StrEnum):
    LAST = "last"
    MEAN = "mean"
    SUM = "sum"
    MIN = "min"
    MAX = "max"
    FIRST = "first"


class MissingDataPolicy(StrEnum):
    FAIL = "FAIL"
    DROP = "DROP"
    CARRY_FORWARD = "CARRY_FORWARD"
    INTERPOLATE = "INTERPOLATE"


@dataclass(frozen=True)
class ResampledValue:
    timestamp: datetime
    value: float
    is_observed: bool
    is_imputed: bool = False
    imputation_method: str | None = None
    source_age_seconds: float | None = None
    quality_state: str = "OBSERVED"


class ResamplingPolicy(BaseModel):
    """One versioned resampling policy for a semantic series type."""

    policy_id: str = "resampling/v1"
    semantic_type: str
    aggregation: ResamplingAggregation = ResamplingAggregation.LAST
    alignment_timezone: str = "UTC"
    carry_forward_policy: MissingDataPolicy = MissingDataPolicy.DROP
    maximum_carry_seconds: int = Field(default=0, ge=0)
    interpolation_policy: MissingDataPolicy = MissingDataPolicy.DROP
    maximum_interpolation_seconds: int = Field(default=0, ge=0)
    forecast_vintage_selection: str = "latest_available_at_origin"
    missing_data_policy: MissingDataPolicy = MissingDataPolicy.DROP

    def content_hash(self) -> str:
        encoded = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, default=str
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def version(self) -> str:
        return self.policy_id

    def qualified_version(self) -> str:
        return f"{self.policy_id}@{self.content_hash()[:8]}"


# The point-in-time dataset builder resolves one series value per forecast origin
# through ``bounded_resample``. These are the policy choices that function can
# honour exactly; anything else is rejected with a structured field error rather
# than silently ignored, because a dataset built under a policy it does not
# actually apply would misrepresent its own provenance.
BUILDER_SUPPORTED_AGGREGATIONS: frozenset[ResamplingAggregation] = frozenset(
    {ResamplingAggregation.LAST}
)
BUILDER_SUPPORTED_MISSING_POLICIES: frozenset[MissingDataPolicy] = frozenset(
    {
        MissingDataPolicy.DROP,
        MissingDataPolicy.FAIL,
        MissingDataPolicy.CARRY_FORWARD,
    }
)
BUILDER_SUPPORTED_ALIGNMENT_TIMEZONE = "UTC"
BUILDER_SUPPORTED_FORECAST_VINTAGE_SELECTION = "latest_available_at_origin"


def builder_support_issues(policy: ResamplingPolicy) -> list[str]:
    """Return why the point-in-time builder cannot honour this policy exactly."""

    reasons: list[str] = []
    if policy.aggregation not in BUILDER_SUPPORTED_AGGREGATIONS:
        reasons.append(
            f"aggregation {policy.aggregation.value!r} is not supported; the "
            "builder resolves one point-in-time value per origin and supports "
            "'last' only"
        )
    if policy.missing_data_policy not in BUILDER_SUPPORTED_MISSING_POLICIES:
        reasons.append(
            f"missing_data_policy {policy.missing_data_policy.value!r} is not supported"
        )
    if (
        policy.missing_data_policy is MissingDataPolicy.CARRY_FORWARD
        and policy.carry_forward_policy is not MissingDataPolicy.CARRY_FORWARD
    ):
        reasons.append(
            "missing_data_policy 'CARRY_FORWARD' requires carry_forward_policy "
            "'CARRY_FORWARD'"
        )
    if policy.interpolation_policy is not MissingDataPolicy.DROP:
        reasons.append("interpolation is not supported by the point-in-time builder")
    if policy.maximum_interpolation_seconds > 0:
        reasons.append(
            "maximum_interpolation_seconds is set but interpolation is not supported"
        )
    if (
        policy.carry_forward_policy is MissingDataPolicy.CARRY_FORWARD
        and policy.maximum_carry_seconds <= 0
    ):
        reasons.append(
            "carry_forward_policy 'CARRY_FORWARD' requires a positive "
            "maximum_carry_seconds bound"
        )
    if policy.alignment_timezone != BUILDER_SUPPORTED_ALIGNMENT_TIMEZONE:
        reasons.append(f"alignment_timezone {policy.alignment_timezone!r} is not supported")
    if policy.forecast_vintage_selection != BUILDER_SUPPORTED_FORECAST_VINTAGE_SELECTION:
        reasons.append(
            f"forecast_vintage_selection {policy.forecast_vintage_selection!r} is not supported"
        )
    return reasons


def bounded_resample(
    records: list[ResampledValue],
    target_timestamps: list[datetime],
    policy: ResamplingPolicy,
) -> list[ResampledValue | None]:
    """Resample to explicit target timestamps with bounded carry-forward.

    ``None`` means missing/not expected; the caller preserves masks. A record
    older than ``maximum_carry_seconds`` is never carried forward, so an old
    intraday price cannot masquerade as a current observation.
    """

    ordered = sorted(records, key=lambda item: item.timestamp)
    result: list[ResampledValue | None] = []
    for target in target_timestamps:
        target_utc = _utc(target)
        eligible = [
            item
            for item in ordered
            if _utc(item.timestamp) <= target_utc
            and (
                policy.maximum_carry_seconds == 0
                or (target_utc - _utc(item.timestamp)).total_seconds()
                <= policy.maximum_carry_seconds
            )
        ]
        if not eligible:
            result.append(None)
            continue
        latest = max(eligible, key=lambda item: _utc(item.timestamp))
        if policy.missing_data_policy is MissingDataPolicy.FAIL:
            result.append(None)
            continue
        if latest.is_observed:
            result.append(latest)
            continue
        if policy.carry_forward_policy is MissingDataPolicy.CARRY_FORWARD:
            age = (target_utc - _utc(latest.timestamp)).total_seconds()
            result.append(
                ResampledValue(
                    timestamp=target,
                    value=latest.value,
                    is_observed=False,
                    is_imputed=True,
                    imputation_method="carry_forward",
                    source_age_seconds=age,
                    quality_state="FORWARD_FILLED",
                )
            )
            continue
        result.append(None)
    return result


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
