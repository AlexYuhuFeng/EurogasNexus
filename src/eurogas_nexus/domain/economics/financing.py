"""Shared simple-interest convention for funding costs and early-cash credits."""

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FundingTerms(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    principal_gbp_mwh: float = Field(ge=0)
    annual_rate_pct: float = Field(ge=0, le=100)
    actual_days: int = Field(ge=0, le=3660, strict=True)
    day_count: Literal["ACT/365F", "ACT/360"]

    def amount_gbp_mwh(self):
        return simple_interest(
            self.principal_gbp_mwh, self.annual_rate_pct, self.actual_days, self.day_count
        )


def simple_interest(
    principal: float, annual_rate_pct: float, actual_days: int, day_count: str
) -> float:
    if not all(math.isfinite(v) for v in (principal, annual_rate_pct)):
        raise ValueError("financing inputs must be finite")
    if annual_rate_pct < 0 or type(actual_days) is not int or actual_days < 0:
        raise ValueError("rate and actual whole days must be non-negative")
    if day_count not in {"ACT/365F", "ACT/360"}:
        raise ValueError("unsupported financing day-count convention")
    result = (
        principal * (annual_rate_pct / 100) * actual_days / (360 if day_count == "ACT/360" else 365)
    )
    if not math.isfinite(result):
        raise ValueError("financing result exceeds finite numerical range")
    return result
