"""Target horizons are parsed exactly or refused; nothing falls back to one hour.

The seed catalog registers its targets with ``horizon="D1"``. The parser read only a
lower-case ``h``/``d`` suffix and returned one hour for anything else, so a "D1" target was
labelled one hour after the origin.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

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


@pytest.mark.parametrize(
    ("horizon", "expected"),
    [
        ("H1", timedelta(hours=1)),
        ("6h", timedelta(hours=6)),
        ("D1", timedelta(days=1)),
        ("d2", timedelta(days=2)),
        ("1d", timedelta(days=1)),
        ("24H", timedelta(hours=24)),
    ],
)
def test_target_horizon_forms_are_parsed(horizon: str, expected: timedelta) -> None:
    from eurogas_nexus.domain.research.datasets import _target_delta

    assert _target_delta(_target(horizon)) == expected


@pytest.mark.parametrize("horizon", ["1w", "D", "0d", "next day", "1.5h", ""])
def test_unparseable_horizon_is_refused(horizon: str) -> None:
    with pytest.raises(ValueError, match="horizon"):
        _build(_spec(), [_record(1, 20.0), _record(2, 21.0)], _target(horizon))


def test_day_horizon_labels_one_day_after_the_origin() -> None:
    spec = _spec(start=_dt(1), end=_dt(2))
    result = _build(spec, [_record(1, 1.0), _record(2, 2.0)], _target("D1"))
    (label,) = [row["target_value"] for row in result.rows if row.get("target_id")]
    # Origin 1 January 00:00: one hour ahead would have picked the 1 January print (1.0).
    assert label == 2.0
