"""Versioned feature-definition registry.

A FeatureDefinition is semantic metadata plus a deterministic implementation
reference. It is not a commercial feature store.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class FeatureAvailabilityClass(StrEnum):
    PAST_ONLY = "PAST_ONLY"
    KNOWN_FUTURE = "KNOWN_FUTURE"
    STATIC = "STATIC"
    FORECAST = "FORECAST"
    DERIVED_AS_OF = "DERIVED_AS_OF"
    TARGET_ONLY = "TARGET_ONLY"


class FeatureDefinition(BaseModel):
    """One deterministic, versioned analytical feature."""

    feature_id: str
    name: str
    description: str
    category: str
    input_dependencies: list[str] = Field(default_factory=list)
    output_unit: str
    frequency: str
    availability_class: FeatureAvailabilityClass
    transformation: str
    transformation_version: str
    lookback: str = "none"
    missing_data_policy: str = "fail"
    point_in_time_policy: str = "available_at_lt_or_eq_cutoff"
    future_knowledge_policy: str = "none"
    owner: str = "research"
    status: str = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)

    def content_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"metadata"})
        payload["metadata"] = self.metadata
        encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def version(self) -> str:
        return f"{self.feature_id}@{self.transformation_version}@{self.content_hash()[:8]}"


def feature_dependency_closure(
    feature: FeatureDefinition,
    registry: dict[str, FeatureDefinition],
    seen: set[str] | None = None,
) -> list[str]:
    """Resolve transitive feature dependencies deterministically."""

    resolved = seen or set()
    result: list[str] = []
    for dependency in feature.input_dependencies:
        if dependency in resolved:
            continue
        resolved.add(dependency)
        dependency_feature = registry.get(dependency)
        if dependency_feature is not None:
            result.extend(feature_dependency_closure(dependency_feature, registry, resolved))
        result.append(dependency)
    return result
