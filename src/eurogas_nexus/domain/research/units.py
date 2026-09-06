"""Explicit, versioned unit/conversion semantics for research data."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class UnitConversion(BaseModel):
    """One versioned conversion applied to a value."""

    conversion_id: str
    method: str
    source_unit: str
    target_unit: str
    factor: float = Field(gt=0)
    version: str
    basis: str | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    source: str = "domain-contract"
    evidence: dict[str, Any] = Field(default_factory=dict)

    def applies_to(self, value_time: datetime) -> bool:
        if self.effective_from is not None and value_time < self.effective_from:
            return False
        if self.effective_to is not None and value_time > self.effective_to:
            return False
        return True


def convert_value(value: float, conversion: UnitConversion) -> float:
    """Apply an explicit conversion; returns the numeric converted value.

    Source-native evidence is preserved by callers (``original_value`` plus
    ``original_unit``); this function never silently re-interprets units.
    """

    return value * conversion.factor
