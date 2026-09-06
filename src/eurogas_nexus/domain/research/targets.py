"""Versioned target-definition registry.

Targets are labels a model is trained/evaluated against. They are never
training features; DatasetSpec validation rejects target-feature overlap.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum

from pydantic import BaseModel


class TargetKind(StrEnum):
    PRICE = "price"
    SPREAD = "spread"
    RETURN = "return"
    FLOW = "flow"
    DEMAND = "demand"
    REGIME = "regime"
    MARGIN = "margin"


class TargetDefinition(BaseModel):
    """One precise forecast/evaluation target."""

    target_id: str
    name: str
    description: str
    target_type: TargetKind
    entity_type: str
    entity_id: str
    metric: str
    forecast_origin_semantics: str = "research_origin"
    horizon: str
    target_window: str
    unit: str
    aggregation: str
    label_calculation: str
    availability_delay: str = "0h"
    quality_policy: str = "strict"
    version: str = "target/v1"

    def content_hash(self) -> str:
        encoded = json.dumps(self.model_dump(mode="json"), sort_keys=True, default=str).encode(
            "utf-8"
        )
        return hashlib.sha256(encoded).hexdigest()

    def qualified_version(self) -> str:
        return f"{self.target_id}@{self.version}@{self.content_hash()[:8]}"

    def feature_prohibited_ids(self) -> set[str]:
        return {self.target_id}
