"""Canonical series metadata for research datasets.

A series is the stable analytical identity for one metric/entity/product/
source-class combination. Convenience string ids are derived from structured
fields, not the other way round.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class MetricType(StrEnum):
    PRICE = "price"
    SPREAD = "spread"
    FLOW = "flow"
    CAPACITY = "capacity"
    STORAGE = "storage"
    LNG = "lng"
    FX = "fx"
    WEATHER = "weather"
    DEMAND = "demand"
    MARGIN = "margin"
    UTILIZATION = "utilization"


class TemporalSeriesType(StrEnum):
    OBSERVED = "OBSERVED"
    FORECAST = "FORECAST"
    ASSESSMENT = "ASSESSMENT"
    MODEL_OUTPUT = "MODEL_OUTPUT"
    SIMULATED = "SIMULATED"


class SeriesDefinition(BaseModel):
    """Stable metadata for one analytical series."""

    series_id: str
    name: str
    metric_type: MetricType
    entity_type: str
    entity_id: str
    product_id: str | None = None
    direction: str | None = None
    source_class: str
    native_frequency: str
    native_unit: str
    currency: str | None = None
    temporal_type: TemporalSeriesType = TemporalSeriesType.OBSERVED
    availability_semantics: str = "available_at_required"
    schema_version: str = "series/v1"

    def semantic_key(self) -> tuple[str, ...]:
        return (
            self.metric_type.value,
            self.entity_type,
            self.entity_id,
            self.product_id or "",
            self.direction or "",
            self.temporal_type.value,
        )

    def derived_series_id(self) -> str:
        parts = [self.metric_type.value, self.entity_type, self.entity_id]
        if self.product_id:
            parts.append(self.product_id)
        if self.direction:
            parts.append(self.direction)
        parts.append(self.temporal_type.value)
        return ".".join(part.replace(" ", "_").lower() for part in parts)


def series_id_for(
    *,
    metric_type: MetricType | str,
    entity_type: str,
    entity_id: str,
    product_id: str | None = None,
    direction: str | None = None,
    temporal_type: TemporalSeriesType | str = TemporalSeriesType.OBSERVED,
) -> str:
    return SeriesDefinition(
        series_id="",
        name="",
        metric_type=MetricType(metric_type),
        entity_type=entity_type,
        entity_id=entity_id,
        product_id=product_id,
        direction=direction,
        source_class="derived",
        native_frequency="event",
        native_unit="native",
        temporal_type=TemporalSeriesType(temporal_type),
    ).derived_series_id()
