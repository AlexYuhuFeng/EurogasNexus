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
