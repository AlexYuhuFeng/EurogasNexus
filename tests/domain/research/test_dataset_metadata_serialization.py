"""Dataset snapshot metadata must be storable as JSON, warnings included.

An EXPLORATORY build with a missing input yields TEMPORAL_INSUFFICIENT_EXPLORATORY warnings
that carry their row, whose ``forecast_origin`` is a datetime. ``as_metadata()`` goes into a
JSON column, so every such materialisation failed with an unhandled 500
(``Object of type datetime is not JSON serializable``). A STRICT build left a ``None`` entry
in its warnings.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from eurogas_nexus.domain.research.datasets import (
    DatasetEvidenceRecord,
    DatasetPointInTimePolicy,
    DatasetSpec,
    build_dataset,
)
from eurogas_nexus.domain.research.features import FeatureDefinition
from eurogas_nexus.domain.research.resampling import ResamplingPolicy
from eurogas_nexus.domain.research.targets import TargetDefinition, TargetKind
from eurogas_nexus.domain.research.temporal import DatasetMode

NBP = "market.price.NBP.DAY_AHEAD"


def _dt(day: int, hour: int = 0) -> datetime:
    return datetime(2026, 1, day, hour, tzinfo=UTC)


def _feature() -> FeatureDefinition:
    return FeatureDefinition(
        feature_id="NBP_DA",
        name="NBP day-ahead",
        description="Test feature.",
        category="market",
        input_dependencies=[NBP],
        output_unit="GBP/MWh",
        frequency="1d",
        availability_class="DERIVED_AS_OF",
        transformation="identity",
        transformation_version="v1",
        missing_data_policy="mask",
    )


def _target(horizon: str) -> TargetDefinition:
    return TargetDefinition(
        target_id="NBP_NEXT",
        name="NBP next",
        description="Test target.",
        target_type=TargetKind.PRICE,
        entity_type="market_hub",
        entity_id="NBP",
        metric=NBP,
        horizon=horizon,
        target_window="1d",
        unit="GBP/MWh",
        aggregation="first",
        label_calculation="first_observation_at_or_after_origin_plus_horizon",
    )


def _record(day: int, value: float, hour: int = 16) -> DatasetEvidenceRecord:
    return DatasetEvidenceRecord(
        record_id=f"nbp-{day}",
        series_id=NBP,
        entity_id="ent:market_hub:NBP",
        observed_at=_dt(day, hour),
        available_at=_dt(day, hour),
        value=value,
        unit="GBP/MWh",
    )


def _spec(*, mode: DatasetMode = DatasetMode.STRICT, start=None, end=None) -> DatasetSpec:
    return DatasetSpec(
        dataset_spec_id="spec-test",
        name="t",
        description="t",
        target_ids=["NBP_NEXT"],
        feature_ids=["NBP_DA"],
        start=start or _dt(2),
        end=end or _dt(4),
        forecast_origin_frequency="1d",
        point_in_time_policy=DatasetPointInTimePolicy(mode=mode),
    )


def _build(spec, records, target, policy=None):
    feature = _feature()
    return build_dataset(
        spec,
        records,
        {feature.feature_id: feature},
        {target.target_id: target},
        policy or ResamplingPolicy(semantic_type="market_price"),
    )


def test_exploratory_metadata_with_leakage_warnings_serialises() -> None:
    # Day 3 has no print and the policy carries at most 1 h, so origin 3 is missing.
    spec = _spec(mode=DatasetMode.EXPLORATORY)
    records = [_record(1, 20.0, hour=23), _record(3, 22.0, hour=23)]
    result = _build(
        spec, records, _target("1d"),
        ResamplingPolicy(semantic_type="market_price", maximum_carry_seconds=3600),
    )
    assert any(isinstance(item, dict) for item in result.warnings)
    metadata = result.as_metadata()
    json.dumps(metadata)  # used to raise TypeError
    assert all(isinstance(item, (str, dict)) for item in metadata["warnings"])


def test_strict_build_warnings_hold_no_none_entry() -> None:
    result = _build(_spec(), [_record(1, 20.0), _record(2, 21.0), _record(3, 22.0)], _target("1d"))
    assert None not in result.warnings
