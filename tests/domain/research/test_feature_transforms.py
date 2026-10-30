"""Declarative point-in-time transforms and walk-forward folds for training datasets."""

from datetime import UTC, datetime, timedelta

import pytest

from eurogas_nexus.domain.research.datasets import (
    DatasetEvidenceRecord,
    DatasetSpec,
    build_dataset,
    walk_forward_folds,
)
from eurogas_nexus.domain.research.features import (
    FeatureAvailabilityClass,
    FeatureDefinition,
)
from eurogas_nexus.domain.research.resampling import ResamplingPolicy
from eurogas_nexus.domain.research.targets import TargetDefinition, TargetKind
from eurogas_nexus.domain.research.temporal import DatasetMode, DatasetPointInTimePolicy

TTF = "market.price.TTF.DAY_AHEAD"
NBP = "market.price.NBP.DAY_AHEAD"
DAY0 = datetime(2026, 1, 1, 12, tzinfo=UTC)


def _feature(
    feature_id: str, transformation: str, deps: list[str], **metadata
) -> FeatureDefinition:
    return FeatureDefinition(
        feature_id=feature_id,
        name=feature_id,
        description=feature_id,
        category="market",
        input_dependencies=deps,
        output_unit="EUR/MWh",
        frequency="1d",
        availability_class=FeatureAvailabilityClass.DERIVED_AS_OF,
        transformation=transformation,
        transformation_version="v1",
        metadata=metadata,
    )


def _target() -> TargetDefinition:
    return TargetDefinition(
        target_id="TTF_DA_PRICE_D1",
        name="TTF D1",
        description="TTF D1",
        target_type=TargetKind.PRICE,
        entity_type="market_hub",
        entity_id="TTF",
        metric="TTF_DA_PRICE_D1",
        horizon="1d",
        target_window="1d",
        unit="EUR/MWh",
        aggregation="first",
        label_calculation="first_observation_at_or_after_origin_plus_horizon",
    )


def _records(revised_day: int | None = None) -> list[DatasetEvidenceRecord]:
    rows = []
    for day in range(10):
        at = DAY0 + timedelta(days=day)
        rows.append(
            DatasetEvidenceRecord(
                record_id=f"ttf-{day}",
                series_id=TTF,
                observed_at=at,
                available_at=at,
                value=30.0 + day,
                unit="EUR/MWh",
            )
        )
        rows.append(
            DatasetEvidenceRecord(
                record_id=f"nbp-{day}",
                series_id=NBP,
                observed_at=at,
                available_at=at,
                value=32.0 + 2 * day,
                unit="EUR/MWh",
            )
        )
    if revised_day is not None:
        # A correction to an old close published at the end: as-of earlier cutoffs it
        # did not exist yet, so a lag must not see it.
        at = DAY0 + timedelta(days=revised_day)
        rows.append(
            DatasetEvidenceRecord(
                record_id="ttf-revised",
                series_id=TTF,
                observed_at=at,
                available_at=DAY0 + timedelta(days=9, hours=1),
                value=999.0,
                unit="EUR/MWh",
            )
        )
    return rows


def _build(features, records=None):
    spec = DatasetSpec(
        dataset_spec_id="transforms",
        name="transforms",
        description="transforms",
        target_ids=["TTF_DA_PRICE_D1"],
        feature_ids=[feature.feature_id for feature in features],
        start=DAY0 + timedelta(days=5),
        end=DAY0 + timedelta(days=8),
        forecast_origin_frequency="1d",
        history_lookback=timedelta(days=30),
        point_in_time_policy=DatasetPointInTimePolicy(mode=DatasetMode.EXPLORATORY),
    )
    return build_dataset(
        spec,
        records or _records(),
        {feature.feature_id: feature for feature in features},
        {"TTF_DA_PRICE_D1": _target()},
        ResamplingPolicy(semantic_type="market_price", maximum_carry_seconds=3600),
    )


def _values(result, feature_id):
    return [row["value"] for row in result.rows if row.get("feature_id") == feature_id]


def test_lag_difference_rolling_and_linear_combination():
    result = _build(
        [
            _feature("TTF_NOW", "identity", [TTF]),
            _feature("TTF_LAG2", "lag", [TTF], lag_steps=2),
            _feature("TTF_CHG1", "difference", [TTF]),
            _feature("TTF_MA3", "rolling_mean", [TTF], window=3),
            _feature("TTF_SD3", "rolling_std", [TTF], window=3),
            _feature("NBP_TTF", "linear_combination", [NBP, TTF], weights=[1, -1]),
        ]
    )
    # Origins are days 5, 6, 7; TTF on day d is 30 + d.
    assert _values(result, "TTF_NOW") == [35.0, 36.0, 37.0]
    assert _values(result, "TTF_LAG2") == [33.0, 34.0, 35.0]
    assert _values(result, "TTF_CHG1") == [1.0, 1.0, 1.0]
    assert _values(result, "TTF_MA3") == [34.0, 35.0, 36.0]
    assert _values(result, "TTF_SD3") == [1.0, 1.0, 1.0]
    assert _values(result, "NBP_TTF") == [7.0, 8.0, 9.0]
    lag_row = next(row for row in result.rows if row.get("feature_id") == "TTF_LAG2")
    assert lag_row["source_refs"] == ["synthetic"]
    assert not [issue for issue in result.leakage_issues if issue["severity"] == "BLOCKER"]


def test_a_lag_reads_what_was_known_then_not_a_later_revision():
    result = _build([_feature("TTF_LAG2", "lag", [TTF], lag_steps=2)], _records(revised_day=3))
    # Origin day 5 lags to day 3; the 999 correction became available on day 9.
    assert _values(result, "TTF_LAG2")[0] == 33.0


def test_missing_history_masks_the_value():
    records = [r for r in _records() if r.record_id != "ttf-4"]
    result = _build([_feature("TTF_MA3", "rolling_mean", [TTF], window=3)], records)
    assert _values(result, "TTF_MA3")[:2] == [None, None]


@pytest.mark.parametrize(
    "feature",
    [
        _feature("BAD1", "lag", [TTF, NBP]),
        _feature("BAD2", "linear_combination", [TTF, NBP], weights=[1]),
        _feature("BAD3", "rolling_std", [TTF], window=1),
        _feature("BAD4", "lag", [TTF], step="1w"),
    ],
)
def test_bad_declarations_are_refused(feature):
    with pytest.raises(ValueError):
        _build([feature])


def test_walk_forward_folds_with_embargo():
    start = datetime(2025, 1, 1, tzinfo=UTC)
    folds = walk_forward_folds(
        start,
        start + timedelta(days=100),
        train=timedelta(days=60),
        test=timedelta(days=10),
        embargo=timedelta(days=2),
    )
    assert len(folds) == 3
    train, test = folds[0]
    assert train.start == start and train.end == start + timedelta(days=60)
    assert test.start == start + timedelta(days=62) and test.end == start + timedelta(days=72)
    assert folds[-1][1].end <= start + timedelta(days=100)
    assert folds[1][0].start == start  # expanding window
    rolling = walk_forward_folds(
        start,
        start + timedelta(days=100),
        train=timedelta(days=60),
        test=timedelta(days=10),
        expanding=False,
    )
    assert rolling[1][0].start == start + timedelta(days=10)
    with pytest.raises(ValueError):
        walk_forward_folds(start, start, train=timedelta(0), test=timedelta(days=1))


def test_residual_load_from_power_series_respects_publication_time():
    load, wind = "power.load_actual.GB", "power.wind_onshore_generation.GB"
    start = datetime(2026, 1, 5, 0, tzinfo=UTC)
    records = []
    for hour in range(6):
        at = start + timedelta(hours=hour)
        # Actuals are published an hour after the period (Transparency Regulation deadline).
        for series, value in ((load, 30_000 + 100 * hour), (wind, 8_000)):
            records.append(
                DatasetEvidenceRecord(
                    record_id=f"{series}-{hour}",
                    series_id=series,
                    observed_at=at,
                    available_at=at + timedelta(hours=1),
                    value=value,
                    unit="MW",
                )
            )
    feature = _feature("GB_RESIDUAL_LOAD", "linear_combination", [load, wind], weights=[1, -1])
    spec = DatasetSpec(
        dataset_spec_id="power",
        name="power",
        description="power",
        target_ids=["TTF_DA_PRICE_D1"],
        feature_ids=["GB_RESIDUAL_LOAD"],
        start=start + timedelta(hours=2),
        end=start + timedelta(hours=5),
        forecast_origin_frequency="1h",
        history_lookback=timedelta(days=1),
        point_in_time_policy=DatasetPointInTimePolicy(mode=DatasetMode.EXPLORATORY),
    )
    result = build_dataset(
        spec,
        records,
        {"GB_RESIDUAL_LOAD": feature},
        {"TTF_DA_PRICE_D1": _target()},
        ResamplingPolicy(semantic_type="market_price", maximum_carry_seconds=7200),
    )
    # At origin 02:00 the latest published hour is 01:00 (load 30,100): 30,100 - 8,000.
    assert _values(result, "GB_RESIDUAL_LOAD") == [22_100.0, 22_200.0, 22_300.0]
