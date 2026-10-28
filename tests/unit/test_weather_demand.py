"""Focused contracts for the pure weather-to-demand research core.

NumPy-dependent fitting checks are skipped only when the separately reviewed
NumPy lock is absent. Degree-day and lazy-dependency checks do not require NumPy.
"""

import math
import sys
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from eurogas_nexus.domain.market.gas_day import (
    DEFAULT_GAS_DAY_CALENDAR,
    gas_day_start_for_date,
)
from eurogas_nexus.domain.research.weather_demand import (
    DEGREE_DAY_METHOD_VERSION,
    DEGREE_DAY_OUTPUT_NAMES,
    RESIDUAL_INTERVAL_METHOD_VERSION,
    AmbiguousWeatherInputError,
    DailyWeatherFeature,
    DegreeDayFeaturePolicy,
    DegreeDayPolicy,
    DegreeDayRequest,
    DemandModelPolicy,
    DemandPredictionRequest,
    DemandTargetQuality,
    DemandTargetRow,
    ForecastTemperatureInterval,
    ForecastVintageRef,
    MissingNumpyError,
    MissingWeatherFeatureError,
    ModelKind,
    ModelSelectionStatus,
    ModelUseStatus,
    NegativeDemandEstimateError,
    PromotionStatus,
    RealizedTemperatureInterval,
    RegionLocationWeight,
    ResidualUncertainty,
    SelectionEvidenceUnavailableError,
    TargetScope,
    TemperatureDerivationMethod,
    TemperatureInputType,
    ValidationBasis,
    WeatherDemandInputError,
    WeatherFeature,
    compute_degree_days,
    fit_weather_demand_model,
    predict_baseline_demand,
    predict_selected_demand,
)


def _forecast(
    gas_day: date,
    temperature: float,
    *,
    location: str = "L1",
    run_id: str = "run-1",
    issued: datetime | None = None,
    available: datetime | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    temporal_method: TemperatureDerivationMethod = (
        TemperatureDerivationMethod.PROVIDER_INTERVAL_MEAN
    ),
) -> ForecastTemperatureInterval:
    day_start = gas_day_start_for_date(gas_day)
    day_end = gas_day_start_for_date(gas_day + timedelta(days=1))
    return ForecastTemperatureInterval(
        location_id=location,
        start_utc=start or day_start,
        end_utc=end or day_end,
        mean_temperature_c=temperature,
        issued_at=issued or day_start - timedelta(days=1),
        available_at=available or day_start - timedelta(hours=12),
        provider="ecmwf",
        model="ifs",
        run_id=run_id,
        source_ref=f"ecmwf:{run_id}:{gas_day.isoformat()}:{location}",
        temporal_method=temporal_method,
    )


def _single_weight() -> tuple[RegionLocationWeight, ...]:
    return (RegionLocationWeight("L1", Decimal("1")),)


def _degree_policy(
    *, heating: float = 18.0, cooling: float = 20.0, max_gap: int = 0
) -> DegreeDayPolicy:
    return DegreeDayPolicy(
        heating_base_c=heating,
        cooling_base_c=cooling,
        max_gap_minutes=max_gap,
        min_covered_fraction=1.0,
    )


def _feature_policy(
    *,
    region: str,
    weights: tuple[RegionLocationWeight, ...],
    heating: float = 18.0,
    cooling: float = 20.0,
    max_gap: int = 0,
    min_covered_fraction: float = 1.0,
    temporal_method: TemperatureDerivationMethod = (
        TemperatureDerivationMethod.PROVIDER_INTERVAL_MEAN
    ),
) -> DegreeDayFeaturePolicy:
    return DegreeDayFeaturePolicy(
        region=region,
        heating_base_c=heating,
        cooling_base_c=cooling,
        max_gap_minutes=max_gap,
        min_covered_fraction=min_covered_fraction,
        location_weights=weights,
        gas_day_calendar=DEFAULT_GAS_DAY_CALENDAR,
        temporal_method=temporal_method,
    )


def test_daily_mean_threshold_and_time_integral_can_differ() -> None:
    gas_day = date(2025, 1, 15)
    start = gas_day_start_for_date(gas_day)
    middle = start + timedelta(hours=12)
    end = gas_day_start_for_date(gas_day + timedelta(days=1))
    request = DegreeDayRequest(
        region="GB",
        gas_days=(gas_day,),
        prediction_origin=start - timedelta(hours=1),
        location_weights=_single_weight(),
        intervals=(
            _forecast(gas_day, 16.0, start=start, end=middle),
            _forecast(gas_day, 22.0, start=middle, end=end),
        ),
    )

    result = compute_degree_days(request, _degree_policy())

    day = result.daily[0]
    assert result.input_type is TemperatureInputType.FORECAST_VINTAGE
    assert result.method_version == DEGREE_DAY_METHOD_VERSION
    assert day.duration_hours == pytest.approx(24.0)
    assert day.daily_mean_temperature_c == pytest.approx(19.0)
    assert day.daily_mean_hdd == pytest.approx(0.0)
    assert day.daily_mean_cdd == pytest.approx(0.0)
    assert day.time_integral_heating_degree_day == pytest.approx(1.0)
    assert day.time_integral_cooling_degree_day == pytest.approx(1.0)
    assert day.covered_fraction == pytest.approx(1.0)
    assert day.coverage_complete
    assert day.named_values()["TIME_INTEGRAL_HEATING_DEGREE_DAY"] == pytest.approx(1.0)
    assert set(DEGREE_DAY_OUTPUT_NAMES) == set(day.named_values())

    feature = result.feature_rows()[0]
    assert result.feature_policy.region == "GB"
    assert result.feature_policy.heating_base_c == pytest.approx(18.0)
    assert result.feature_policy.cooling_base_c == pytest.approx(20.0)
    assert result.feature_policy.max_gap_minutes == 0
    assert (
        result.feature_policy.temporal_method
        is TemperatureDerivationMethod.PROVIDER_INTERVAL_MEAN
    )
    assert feature.region == "GB"
    assert feature.feature_policy_hash == result.feature_policy_hash
    assert feature.feature_policy_hash == result.feature_policy.policy_hash


def test_future_valid_forecast_is_allowed_when_available_at_origin() -> None:
    gas_day = date(2025, 2, 1)
    start = gas_day_start_for_date(gas_day)
    request = DegreeDayRequest(
        region="GB",
        gas_days=(gas_day,),
        prediction_origin=start - timedelta(hours=2),
        location_weights=_single_weight(),
        intervals=(_forecast(gas_day, 10.0),),
    )

    result = compute_degree_days(request, _degree_policy())

    assert result.daily[0].daily_mean_hdd == pytest.approx(8.0)


def test_dst_gas_days_use_true_utc_duration() -> None:
    # The gas day containing the spring transition starts on the previous date.
    spring = date(2025, 3, 29)
    spring_start = gas_day_start_for_date(spring)
    spring_request = DegreeDayRequest(
        region="GB",
        gas_days=(spring,),
        prediction_origin=spring_start - timedelta(hours=1),
        location_weights=_single_weight(),
        intervals=(_forecast(spring, 10.0),),
    )
    spring_day = compute_degree_days(spring_request, _degree_policy()).daily[0]
    assert spring_day.gas_day_start_utc == datetime(2025, 3, 29, 5, tzinfo=UTC)
    assert spring_day.gas_day_end_utc == datetime(2025, 3, 30, 4, tzinfo=UTC)
    assert spring_day.duration_hours == pytest.approx(23.0)
    assert spring_day.time_integral_heating_degree_day == pytest.approx(8.0 * 23.0 / 24.0)

    # The gas day containing the autumn transition starts on the previous date.
    autumn = date(2025, 10, 25)
    autumn_start = gas_day_start_for_date(autumn)
    autumn_request = DegreeDayRequest(
        region="GB",
        gas_days=(autumn,),
        prediction_origin=autumn_start - timedelta(hours=1),
        location_weights=_single_weight(),
        intervals=(_forecast(autumn, 10.0),),
    )
    autumn_day = compute_degree_days(autumn_request, _degree_policy()).daily[0]
    assert autumn_day.gas_day_start_utc == datetime(2025, 10, 25, 4, tzinfo=UTC)
    assert autumn_day.gas_day_end_utc == datetime(2025, 10, 26, 5, tzinfo=UTC)
    assert autumn_day.duration_hours == pytest.approx(25.0)
    assert autumn_day.time_integral_heating_degree_day == pytest.approx(8.0 * 25.0 / 24.0)


def test_partial_coverage_returns_null_not_zero() -> None:
    gas_day = date(2025, 1, 15)
    start = gas_day_start_for_date(gas_day)
    request = DegreeDayRequest(
        region="GB",
        gas_days=(gas_day,),
        prediction_origin=start - timedelta(hours=1),
        location_weights=_single_weight(),
        intervals=(
            _forecast(gas_day, 8.0, start=start, end=start + timedelta(hours=12)),
        ),
    )

    day = compute_degree_days(request, _degree_policy(max_gap=60)).daily[0]

    assert day.covered_fraction == pytest.approx(0.5)
    assert not day.coverage_complete
    assert day.daily_mean_hdd is None
    assert day.daily_mean_cdd is None
    assert day.time_integral_heating_degree_day is None
    assert day.time_integral_cooling_degree_day is None
    assert day.missing_reason == "INSUFFICIENT_COVERAGE"


def test_weighted_region_is_null_when_one_required_location_is_missing() -> None:
    gas_day = date(2025, 1, 15)
    start = gas_day_start_for_date(gas_day)
    request = DegreeDayRequest(
        region="GB",
        gas_days=(gas_day,),
        prediction_origin=start - timedelta(hours=1),
        location_weights=(
            RegionLocationWeight("L1", Decimal("0.25")),
            RegionLocationWeight("L2", Decimal("0.75")),
        ),
        intervals=(_forecast(gas_day, 8.0, location="L1"),),
    )

    day = compute_degree_days(request, _degree_policy()).daily[0]

    assert day.coverage_complete is False
    assert day.covered_fraction == pytest.approx(0.25)
    assert day.daily_mean_hdd is None
    assert day.locations[1].missing_reason == "NO_LOCATION_INTERVALS"


def test_exact_decimal_weights_and_duplicate_locations_are_refused() -> None:
    gas_day = date(2025, 1, 15)
    start = gas_day_start_for_date(gas_day)
    intervals = (_forecast(gas_day, 8.0, location="L1"), _forecast(gas_day, 9.0, location="L2"))

    with pytest.raises(WeatherDemandInputError, match="sum exactly"):
        DegreeDayRequest(
            region="GB",
            gas_days=(gas_day,),
            prediction_origin=start - timedelta(hours=1),
            location_weights=(
                RegionLocationWeight("L1", Decimal("0.1")),
                RegionLocationWeight("L2", Decimal("0.2")),
            ),
            intervals=intervals,
        )
    with pytest.raises(WeatherDemandInputError, match="duplicate locations"):
        DegreeDayRequest(
            region="GB",
            gas_days=(gas_day,),
            prediction_origin=start - timedelta(hours=1),
            location_weights=(
                RegionLocationWeight("L1", Decimal("0.5")),
                RegionLocationWeight("L1", Decimal("0.5")),
            ),
            intervals=intervals,
        )
    with pytest.raises(WeatherDemandInputError, match="finite"):
        RegionLocationWeight("L1", Decimal("NaN"))


def test_overlapping_intervals_and_mixed_provenance_are_refused() -> None:
    gas_day = date(2025, 1, 15)
    start = gas_day_start_for_date(gas_day)
    first = _forecast(gas_day, 8.0, start=start, end=start + timedelta(hours=18))
    second = _forecast(
        gas_day,
        9.0,
        start=start + timedelta(hours=12),
        end=start + timedelta(hours=24),
    )
    request = DegreeDayRequest(
        region="GB",
        gas_days=(gas_day,),
        prediction_origin=start - timedelta(hours=1),
        location_weights=_single_weight(),
        intervals=(first, second),
    )
    with pytest.raises(AmbiguousWeatherInputError, match="overlapping"):
        compute_degree_days(request, _degree_policy())

    realized = RealizedTemperatureInterval(
        location_id="L1",
        start_utc=start,
        end_utc=start + timedelta(days=1),
        mean_temperature_c=8.0,
        available_at=start + timedelta(days=1, hours=1),
        source_ref="observed:L1",
        temporal_method=TemperatureDerivationMethod.PROVIDER_INTERVAL_MEAN,
    )
    with pytest.raises(WeatherDemandInputError, match="cannot be mixed"):
        DegreeDayRequest(
            region="GB",
            gas_days=(gas_day,),
            prediction_origin=start + timedelta(days=2),
            location_weights=_single_weight(),
            intervals=(first, realized),
        )


def test_one_latest_available_vintage_is_selected_without_filling_gaps() -> None:
    gas_day = date(2025, 1, 15)
    start = gas_day_start_for_date(gas_day)
    origin = start - timedelta(hours=1)
    old = _forecast(
        gas_day,
        7.0,
        location="L1",
        run_id="old",
        issued=start - timedelta(days=2),
        available=start - timedelta(days=2) + timedelta(hours=1),
    )
    old_second_location = _forecast(
        gas_day,
        7.0,
        location="L2",
        run_id="old",
        issued=start - timedelta(days=2),
        available=start - timedelta(days=2) + timedelta(hours=1),
    )
    latest_partial = _forecast(
        gas_day,
        12.0,
        location="L1",
        run_id="latest",
        issued=start - timedelta(hours=6),
        available=start - timedelta(hours=4),
    )
    later_issued = _forecast(
        gas_day,
        1.0,
        location="L1",
        run_id="later",
        issued=start + timedelta(hours=2),
        available=start + timedelta(hours=3),
    )
    request = DegreeDayRequest(
        region="GB",
        gas_days=(gas_day,),
        prediction_origin=origin,
        location_weights=(
            RegionLocationWeight("L1", Decimal("0.5")),
            RegionLocationWeight("L2", Decimal("0.5")),
        ),
        intervals=(old, old_second_location, latest_partial, later_issued),
    )

    result = compute_degree_days(request, _degree_policy())

    assert result.selected_vintage is not None
    assert result.selected_vintage.run_id == "latest"
    assert result.daily[0].covered_fraction == pytest.approx(0.5)
    assert result.daily[0].daily_mean_hdd is None

    with pytest.raises(WeatherDemandInputError, match="not issued and available"):
        compute_degree_days(
            replace(
                request,
                forecast_vintage=ForecastVintageRef(
                    provider="ecmwf",
                    model="ifs",
                    run_id="later",
                    issued_at=start + timedelta(hours=2),
                ),
            ),
            _degree_policy(),
        )


def test_realized_temperature_is_distinct_and_never_a_forecast_vintage() -> None:
    gas_day = date(2025, 1, 15)
    start = gas_day_start_for_date(gas_day)
    end = gas_day_start_for_date(gas_day + timedelta(days=1))
    realized = RealizedTemperatureInterval(
        location_id="L1",
        start_utc=start,
        end_utc=end,
        mean_temperature_c=10.0,
        available_at=end + timedelta(hours=2),
        source_ref="observed:L1",
        temporal_method=TemperatureDerivationMethod.PROVIDER_INTERVAL_MEAN,
    )
    request = DegreeDayRequest(
        region="GB",
        gas_days=(gas_day,),
        prediction_origin=end + timedelta(hours=3),
        location_weights=_single_weight(),
        intervals=(realized,),
    )

    result = compute_degree_days(request, _degree_policy())

    assert result.input_type is TemperatureInputType.REALIZED_OBSERVATION
    assert result.selected_vintage is None
    feature = result.feature_rows()[0]
    assert feature.input_type is TemperatureInputType.REALIZED_OBSERVATION
    assert feature.forecast_vintage is None
    assert feature.region == "GB"
    assert feature.feature_policy_hash == result.feature_policy_hash
    assert feature.temporal_method is TemperatureDerivationMethod.PROVIDER_INTERVAL_MEAN


def _fit_fixture(
    *, rows: int = 40, unit: str = "MSCM", hdd_shift: float = 0.0
) -> tuple[tuple[DemandTargetRow, ...], tuple[DailyWeatherFeature, ...]]:
    start_day = date(2025, 1, 1)
    feature_policy = _feature_policy(region="GB", weights=_single_weight())
    targets: list[DemandTargetRow] = []
    features: list[DailyWeatherFeature] = []
    for index in range(rows):
        gas_day = start_day + timedelta(days=index)
        day_start = gas_day_start_for_date(gas_day)
        hdd = 6.0 + 2.0 * math.sin(index / 3.0) + hdd_shift
        cdd = 0.0
        weekend = 2.0 if gas_day.weekday() >= 5 else 0.0
        demand = 100.0 + 8.0 * hdd + weekend
        targets.append(
            DemandTargetRow(
                gas_day=gas_day,
                scope=TargetScope.REGION,
                region="GB",
                unit=unit,
                value=demand,
                quality=DemandTargetQuality.ACTUAL,
                revision=1,
                revision_id=f"target-{gas_day.isoformat()}",
                available_at=gas_day_start_for_date(gas_day + timedelta(days=1))
                + timedelta(hours=1),
                source_ref=f"target:{gas_day.isoformat()}",
            )
        )
        vintage = ForecastVintageRef(
            provider="ecmwf",
            model="ifs",
            run_id="run-1",
            issued_at=day_start - timedelta(hours=12),
        )
        features.append(
            DailyWeatherFeature(
                gas_day=gas_day,
                input_type=TemperatureInputType.FORECAST_VINTAGE,
                daily_mean_hdd=hdd,
                daily_mean_cdd=cdd,
                heating_degree_day_integral=hdd,
                cooling_degree_day_integral=cdd,
                available_at=day_start - timedelta(hours=6),
                prediction_origin=day_start,
                source_ref=f"weather:{gas_day.isoformat()}",
                feature_policy=feature_policy,
                forecast_vintage=vintage,
            )
        )
    return tuple(targets), tuple(features)


def _fit_policy(
    *,
    unit: str = "MSCM",
    min_residuals: int = 100,
    min_folds: int = 4,
    min_predictions: int = 4,
) -> DemandModelPolicy:
    return DemandModelPolicy(
        target_scope=TargetScope.REGION,
        region="GB",
        target_unit=unit,
        gas_day_calendar=DEFAULT_GAS_DAY_CALENDAR,
        training_cutoff=gas_day_start_for_date(date(2025, 1, 31)),
        validation_as_of=gas_day_start_for_date(date(2025, 2, 12)),
        ridge_lambda=0.5,
        model_version="ridge-demo/v1",
        validation_basis=ValidationBasis.SYNTHETIC_NOT_REAL,
        weather_features=(WeatherFeature.HDD_MEAN,),
        expected_feature_policy=_feature_policy(region="GB", weights=_single_weight()),
        min_training_rows=8,
        min_validation_folds=min_folds,
        min_validation_predictions=min_predictions,
        min_oos_coverage=0.4,
        min_relative_mae_improvement=0.1,
        min_fold_win_fraction=0.5,
        min_residuals_for_interval=min_residuals,
        interval_level=0.8,
        max_folds=20,
    )


def test_numpy_missing_raises_typed_dependency_error(monkeypatch: pytest.MonkeyPatch) -> None:
    targets, features = _fit_fixture(rows=5)
    monkeypatch.setitem(sys.modules, "numpy", None)

    with pytest.raises(MissingNumpyError) as caught:
        fit_weather_demand_model(targets, features, _fit_policy())

    assert caught.value.code == "NUMPY_NOT_INSTALLED"
    assert caught.value.dependency == "numpy"


def test_controlled_weather_relationship_beats_baseline_and_stays_research_only() -> None:
    pytest.importorskip("numpy")
    targets, features = _fit_fixture()

    result = fit_weather_demand_model(targets, features, _fit_policy())

    assert result.selection_status is ModelSelectionStatus.CANDIDATE_SELECTED
    assert result.selected_model.kind is ModelKind.WEATHER_CALENDAR_RIDGE
    assert result.baseline_oos is not None
    assert result.candidate_oos is not None
    assert result.candidate_oos.mae < result.baseline_oos.mae
    assert result.candidate_oos.rmse <= result.baseline_oos.rmse
    assert result.selected_model.coefficients[-1] > 0.0
    assert result.validation_basis is ValidationBasis.SYNTHETIC_NOT_REAL
    assert result.production_promotion is PromotionStatus.NOT_PROMOTED
    assert result.selected_model.validation_basis is ValidationBasis.SYNTHETIC_NOT_REAL
    assert result.prediction_label == "MODEL_OUTPUT"
    assert result.uncertainty is None
    assert "SYNTHETIC" in (result.uncertainty_reason or "")
    assert result.folds
    assert all(fold.input_type is TemperatureInputType.FORECAST_VINTAGE for fold in result.folds)

    repeated = fit_weather_demand_model(targets, features, _fit_policy())
    assert repeated.selected_model.model_hash == result.selected_model.model_hash

    modified = list(features)
    modified[2] = replace(modified[2], daily_mean_hdd=modified[2].daily_mean_hdd + 2.0)
    changed = fit_weather_demand_model(targets, tuple(modified), _fit_policy())
    assert changed.candidate_model is not None
    assert changed.selected_model.model_hash != result.selected_model.model_hash


def test_later_available_target_and_weather_do_not_enter_earlier_fit() -> None:
    pytest.importorskip("numpy")
    targets, features = _fit_fixture()
    before = fit_weather_demand_model(targets, features, _fit_policy())

    source_target = targets[3]
    later_target = replace(
        source_target,
        value=source_target.value + 50.0,
        revision=2,
        revision_id="late-truth",
        available_at=source_target.available_at + timedelta(days=100),
        source_ref="target:late-revision",
    )
    later_weather = replace(
        features[4],
        daily_mean_hdd=features[4].daily_mean_hdd + 3.0,
        available_at=features[4].available_at + timedelta(days=100),
        prediction_origin=features[4].prediction_origin + timedelta(days=100),
        source_ref="weather:late-revision",
    )
    after = fit_weather_demand_model(
        targets + (later_target,), features + (later_weather,), _fit_policy()
    )

    assert after.baseline_model.model_hash == before.baseline_model.model_hash
    assert after.candidate_model is not None
    assert before.candidate_model is not None
    assert after.candidate_model.model_hash == before.candidate_model.model_hash
    assert after.folds == before.folds


def test_native_unit_mismatch_and_duplicate_revision_are_refused() -> None:
    pytest.importorskip("numpy")
    targets, features = _fit_fixture()
    with pytest.raises(WeatherDemandInputError, match="native unit"):
        fit_weather_demand_model(
            (replace(targets[0], unit="MWH"),) + targets[1:],
            features,
            _fit_policy(),
        )
    with pytest.raises(AmbiguousWeatherInputError, match="duplicate target"):
        fit_weather_demand_model(
            targets + (replace(targets[0], revision_id="duplicate"),),
            features,
            _fit_policy(),
        )


def test_constant_data_and_insufficient_oos_do_not_fake_success() -> None:
    pytest.importorskip("numpy")
    targets, features = _fit_fixture(rows=12)
    constant_targets = tuple(replace(target, value=50.0) for target in targets)
    constant_features = tuple(
        replace(
            feature,
            daily_mean_hdd=5.0,
            daily_mean_cdd=0.0,
            heating_degree_day_integral=5.0,
            cooling_degree_day_integral=0.0,
        )
        for feature in features
    )
    policy = replace(
        _fit_policy(min_folds=1, min_predictions=1),
        training_cutoff=gas_day_start_for_date(date(2025, 1, 9)),
        validation_as_of=gas_day_start_for_date(date(2025, 1, 15)),
        min_validation_folds=1,
        min_validation_predictions=1,
        min_training_rows=4,
        min_oos_coverage=0.1,
        min_residuals_for_interval=2,
    )

    result = fit_weather_demand_model(constant_targets, constant_features, policy)

    assert result.candidate_model is not None
    assert all(math.isfinite(value) for value in result.candidate_model.coefficients)
    assert all(math.isfinite(value) for value in result.candidate_model.feature_scales)
    assert result.selection_status is ModelSelectionStatus.BASELINE_RETAINED
    assert result.uncertainty is None

    no_holdout = replace(
        policy,
        training_cutoff=gas_day_start_for_date(date(2025, 1, 20)),
        validation_as_of=gas_day_start_for_date(date(2025, 2, 1)),
    )
    insufficient = fit_weather_demand_model(constant_targets, constant_features, no_holdout)
    assert insufficient.selection_status is ModelSelectionStatus.INSUFFICIENT_DATA
    assert insufficient.baseline_oos is None
    assert insufficient.candidate_oos is None
    assert insufficient.oos_coverage == 0.0


def test_forecast_and_realized_basis_mismatch_is_refused() -> None:
    pytest.importorskip("numpy")
    targets, features = _fit_fixture()
    with pytest.raises(WeatherDemandInputError, match="realized calibration"):
        fit_weather_demand_model(
            targets,
            features,
            replace(_fit_policy(), validation_basis=ValidationBasis.REALIZED_WEATHER_CALIBRATION),
        )
    with pytest.raises(WeatherDemandInputError, match="genuine forecast"):
        fit_weather_demand_model(
            targets,
            tuple(
                replace(
                    feature,
                    input_type=TemperatureInputType.REALIZED_OBSERVATION,
                    forecast_vintage=None,
                )
                for feature in features
            ),
            replace(_fit_policy(), validation_basis=ValidationBasis.GENUINE_FORECAST_VINTAGE_OOS),
        )


def test_feature_policy_hash_changes_with_bases_weights_coverage_and_method() -> None:
    policy = _feature_policy(region="GB", weights=_single_weight())
    original = policy.policy_hash

    assert len(original) == 64
    assert replace(policy, region="DE").policy_hash != original
    assert replace(policy, heating_base_c=15.5).policy_hash != original
    assert replace(policy, cooling_base_c=18.0).policy_hash != original
    assert (
        replace(
            policy,
            location_weights=(
                RegionLocationWeight("L1", Decimal("0.5")),
                RegionLocationWeight("L2", Decimal("0.5")),
            ),
        ).policy_hash
        != original
    )
    assert replace(policy, max_gap_minutes=60).policy_hash != original
    assert replace(policy, min_covered_fraction=0.95).policy_hash != original
    assert (
        replace(
            policy,
            temporal_method=TemperatureDerivationMethod.EXPLICIT_DERIVED_HOLD,
        ).policy_hash
        != original
    )

    # Exact Decimal identity is canonicalized, so equivalent weights hash equally.
    equivalent = replace(
        policy,
        location_weights=(RegionLocationWeight("L1", Decimal("1.000")),),
    )
    assert equivalent.policy_hash == original


def test_cross_region_feature_policy_is_refused() -> None:
    pytest.importorskip("numpy")
    targets, features = _fit_fixture()
    german_policy = _feature_policy(region="DE", weights=_single_weight())
    german_features = tuple(
        replace(feature, feature_policy=german_policy) for feature in features
    )

    with pytest.raises(WeatherDemandInputError, match="region"):
        fit_weather_demand_model(targets, german_features, _fit_policy())

    with pytest.raises(WeatherDemandInputError, match="region"):
        replace(_fit_policy(), expected_feature_policy=german_policy)


def test_cross_policy_prediction_feature_is_refused() -> None:
    pytest.importorskip("numpy")
    targets, features = _fit_fixture()
    # This row is outside the training cutoff, so a training-only check would miss it.
    cross_policy = _feature_policy(region="GB", weights=_single_weight(), heating=15.5)
    cross_features = features[:-1] + (
        replace(features[-1], feature_policy=cross_policy),
    )

    with pytest.raises(WeatherDemandInputError, match="fingerprint"):
        fit_weather_demand_model(targets, cross_features, _fit_policy())


def _future_feature(
    feature_policy: DegreeDayFeaturePolicy,
    gas_day: date,
    hdd: float | None,
    *,
    origin: datetime,
    available_at: datetime | None = None,
    prediction_origin: datetime | None = None,
    run_id: str = "future-run",
    input_type: TemperatureInputType = TemperatureInputType.FORECAST_VINTAGE,
) -> DailyWeatherFeature:
    available = available_at or (origin - timedelta(hours=2))
    feature_origin = prediction_origin or (origin - timedelta(hours=1))
    vintage = None
    if input_type is TemperatureInputType.FORECAST_VINTAGE:
        vintage = ForecastVintageRef(
            provider="ecmwf",
            model="ifs",
            run_id=run_id,
            issued_at=available - timedelta(hours=6),
        )
    return DailyWeatherFeature(
        gas_day=gas_day,
        input_type=input_type,
        daily_mean_hdd=hdd,
        daily_mean_cdd=0.0,
        heating_degree_day_integral=hdd,
        cooling_degree_day_integral=0.0,
        available_at=available,
        prediction_origin=feature_origin,
        source_ref=f"future:{run_id}:{gas_day.isoformat()}",
        feature_policy=feature_policy,
        forecast_vintage=vintage,
    )


def _prediction_request(
    gas_day: date, origin: datetime, feature: DailyWeatherFeature | None
) -> DemandPredictionRequest:
    return DemandPredictionRequest(
        gas_day=gas_day,
        prediction_origin=origin,
        target_scope=TargetScope.REGION,
        region="GB",
        target_unit="MSCM",
        gas_day_calendar=DEFAULT_GAS_DAY_CALENDAR,
        weather_feature=feature,
    )


def _future_context() -> tuple[
    object, date, datetime, DegreeDayFeaturePolicy
]:
    pytest.importorskip("numpy")
    targets, features = _fit_fixture()
    result = fit_weather_demand_model(targets, features, _fit_policy())
    gas_day = date(2025, 2, 15)
    origin = gas_day_start_for_date(gas_day) - timedelta(days=2)
    feature_policy = _feature_policy(region="GB", weights=_single_weight())
    return result, gas_day, origin, feature_policy


def test_future_forecast_hdd_changes_weather_prediction_and_is_reproducible() -> None:
    result, gas_day, origin, feature_policy = _future_context()
    cold_feature = _future_feature(
        feature_policy, gas_day, 12.0, origin=origin, run_id="cold-run"
    )
    warm_feature = _future_feature(
        feature_policy, gas_day, 2.0, origin=origin, run_id="warm-run"
    )

    cold = predict_selected_demand(
        result, _prediction_request(gas_day, origin, cold_feature)
    )
    warm = predict_selected_demand(
        result, _prediction_request(gas_day, origin, warm_feature)
    )

    assert cold.value > warm.value
    assert math.isfinite(cold.value)
    assert cold.model_kind is ModelKind.WEATHER_CALENDAR_RIDGE
    assert cold.prediction_label == "MODEL_OUTPUT"
    assert cold.target_unit == "MSCM"
    assert cold.model_hash == result.selected_model.model_hash
    assert cold.selection_hash == result.selection_hash
    assert cold.selection_as_of == result.validation_as_of
    assert cold.feature_policy_hash == result.selected_model.feature_policy_hash
    assert cold.feature_refs[0].name == "weather_hdd_mean"
    assert cold.feature_refs[0].value == pytest.approx(12.0)
    assert cold.weather_source_ref == cold_feature.source_ref
    assert cold.forecast_vintage == cold_feature.forecast_vintage
    assert cold.interval is None
    assert "SYNTHETIC" in (cold.interval_reason or "")

    repeated = predict_selected_demand(
        result, _prediction_request(gas_day, origin, cold_feature)
    )
    assert repeated.value == cold.value
    assert repeated.model_hash == cold.model_hash
    assert repeated.selection_hash == cold.selection_hash


def test_explicit_baseline_prediction_is_labelled_and_ignores_weather() -> None:
    result, gas_day, origin, feature_policy = _future_context()
    request = _prediction_request(gas_day, origin, None)

    prediction = predict_baseline_demand(result, request)

    expected = next(
        (value for month, value in result.baseline_model.month_means if month == gas_day.month),
        result.baseline_model.overall_mean,
    )
    assert prediction.value == pytest.approx(expected)
    assert prediction.model_kind is ModelKind.CALENDAR_BASELINE
    assert prediction.use_status is ModelUseStatus.CALENDAR_BASELINE_REFERENCE
    assert prediction.prediction_label == "CALENDAR_BASELINE_REFERENCE"
    assert prediction.model_hash == result.baseline_model.model_hash
    assert prediction.feature_refs == ()
    assert prediction.weather_source_ref is None
    assert prediction.forecast_vintage is None
    assert prediction.interval is None
    assert "BASELINE" in (prediction.interval_reason or "")

    weather_feature = _future_feature(feature_policy, gas_day, 8.0, origin=origin)
    with pytest.raises(WeatherDemandInputError, match="does not consume"):
        predict_baseline_demand(
            result, replace(request, weather_feature=weather_feature)
        )


def test_prediction_refuses_before_selection_evidence_and_late_features() -> None:
    result, gas_day, _origin, feature_policy = _future_context()
    selection_as_of = result.selection_as_of
    assert selection_as_of is not None
    assert result.selected_model.training_cutoff < selection_as_of

    before = selection_as_of - timedelta(seconds=1)
    early_feature = _future_feature(feature_policy, gas_day, 8.0, origin=before)
    with pytest.raises(SelectionEvidenceUnavailableError, match="validation_as_of"):
        predict_selected_demand(
            result, _prediction_request(gas_day, before, early_feature)
        )
    with pytest.raises(SelectionEvidenceUnavailableError, match="validation_as_of"):
        predict_baseline_demand(result, _prediction_request(gas_day, before, None))

    origin = selection_as_of + timedelta(hours=2)
    late_feature = _future_feature(
        feature_policy,
        gas_day,
        8.0,
        origin=origin,
        available_at=origin + timedelta(hours=1),
        prediction_origin=origin + timedelta(hours=2),
    )
    with pytest.raises(WeatherDemandInputError, match="available at the prediction origin"):
        predict_selected_demand(
            result, _prediction_request(gas_day, origin, late_feature)
        )


def test_prediction_refuses_region_unit_and_feature_policy_mismatch() -> None:
    result, gas_day, origin, feature_policy = _future_context()
    feature = _future_feature(feature_policy, gas_day, 8.0, origin=origin)
    request = _prediction_request(gas_day, origin, feature)

    with pytest.raises(WeatherDemandInputError, match="region"):
        predict_selected_demand(result, replace(request, region="DE"))
    with pytest.raises(WeatherDemandInputError, match="native unit"):
        predict_selected_demand(result, replace(request, target_unit="MWH"))

    cross_policy = _feature_policy(region="GB", weights=_single_weight(), heating=15.5)
    cross_feature = replace(feature, feature_policy=cross_policy)
    with pytest.raises(WeatherDemandInputError, match="fingerprint"):
        predict_selected_demand(
            result, _prediction_request(gas_day, origin, cross_feature)
        )
    with pytest.raises(WeatherDemandInputError, match="gas day"):
        predict_selected_demand(
            result,
            _prediction_request(gas_day + timedelta(days=1), origin, feature),
        )


def test_missing_or_realized_weather_refuses_for_weather_model() -> None:
    result, gas_day, origin, feature_policy = _future_context()

    with pytest.raises(MissingWeatherFeatureError, match="requires"):
        predict_selected_demand(result, _prediction_request(gas_day, origin, None))

    missing_hdd = _future_feature(feature_policy, gas_day, None, origin=origin)
    with pytest.raises(MissingWeatherFeatureError, match="HDD_MEAN"):
        predict_selected_demand(
            result, _prediction_request(gas_day, origin, missing_hdd)
        )

    realized = _future_feature(
        feature_policy,
        gas_day,
        8.0,
        origin=origin,
        input_type=TemperatureInputType.REALIZED_OBSERVATION,
    )
    with pytest.raises(WeatherDemandInputError, match="realized"):
        predict_selected_demand(result, _prediction_request(gas_day, origin, realized))


def test_negative_estimate_is_refused_instead_of_clamped() -> None:
    result, gas_day, origin, _feature_policy = _future_context()
    negative = replace(
        result,
        baseline_model=replace(
            result.baseline_model,
            month_means=(),
            overall_mean=-1.0,
        ),
    )

    with pytest.raises(NegativeDemandEstimateError, match="negative"):
        predict_baseline_demand(
            negative, _prediction_request(gas_day, origin, None)
        )


def test_selection_hash_binds_validation_evidence_and_thresholds() -> None:
    pytest.importorskip("numpy")
    targets, features = _fit_fixture()
    policy = _fit_policy()
    result = fit_weather_demand_model(targets, features, policy)
    repeated = fit_weather_demand_model(targets, features, policy)
    stricter = fit_weather_demand_model(
        targets,
        features,
        replace(policy, min_relative_mae_improvement=0.5),
    )

    assert result.selection_hash is not None
    assert len(result.selection_hash) == 64
    assert result.selection_as_of == policy.validation_as_of
    assert result.validation_as_of == policy.validation_as_of
    assert repeated.selection_hash == result.selection_hash
    assert stricter.selection_hash != result.selection_hash
    assert stricter.selection_hash != stricter.selected_model.model_hash


def test_selection_hash_binds_fold_and_uncertainty_evidence() -> None:
    result, _gas_day, _origin, _feature_policy = _future_context()
    evidence = result.selection_evidence
    assert evidence is not None
    assert evidence.folds

    first_fold = evidence.folds[0]
    changed_fold = replace(
        first_fold,
        actual_value=first_fold.actual_value + 1.0,
    )
    changed_folds = (changed_fold,) + evidence.folds[1:]
    assert (
        replace(evidence, folds=changed_folds).selection_hash
        != evidence.selection_hash
    )

    uncertainty = ResidualUncertainty(
        level=0.8,
        lower_offset=-4.0,
        upper_offset=6.0,
        residual_count=max(1, result.residual_count),
        method_version=RESIDUAL_INTERVAL_METHOD_VERSION,
    )
    uncertainty_evidence = replace(evidence, uncertainty=uncertainty)
    assert uncertainty_evidence.selection_hash != evidence.selection_hash
    reason_changed = replace(
        uncertainty_evidence,
        uncertainty_reason="changed",
    )
    assert reason_changed.selection_hash != uncertainty_evidence.selection_hash


def test_inference_refuses_stale_uncertainty_baseline_status_and_folds() -> None:
    result, gas_day, origin, feature_policy = _future_context()
    evidence = result.selection_evidence
    assert evidence is not None
    assert result.candidate_model is not None
    request = _prediction_request(
        gas_day,
        origin,
        _future_feature(feature_policy, gas_day, 8.0, origin=origin),
    )

    uncertainty = ResidualUncertainty(
        level=0.8,
        lower_offset=-4.0,
        upper_offset=6.0,
        residual_count=max(1, result.residual_count),
        method_version=RESIDUAL_INTERVAL_METHOD_VERSION,
    )
    bound = replace(
        result,
        selection_evidence=replace(
            evidence,
            uncertainty=uncertainty,
            uncertainty_reason=None,
        ),
        uncertainty=uncertainty,
        uncertainty_reason=None,
    )
    changed_offsets = replace(
        bound,
        uncertainty=replace(uncertainty, lower_offset=-40.0),
    )
    with pytest.raises(WeatherDemandInputError, match="uncertainty payload"):
        predict_selected_demand(changed_offsets, request)

    baseline_reference = replace(result, baseline_model=result.candidate_model)
    with pytest.raises(WeatherDemandInputError, match="baseline-model"):
        predict_baseline_demand(
            baseline_reference,
            _prediction_request(gas_day, origin, None),
        )

    changed_status = (
        ModelSelectionStatus.BASELINE_RETAINED
        if result.selection_status is ModelSelectionStatus.CANDIDATE_SELECTED
        else ModelSelectionStatus.CANDIDATE_SELECTED
    )
    status_tampered = replace(result, selection_status=changed_status)
    with pytest.raises(WeatherDemandInputError, match="selection status"):
        predict_selected_demand(status_tampered, request)

    basis_tampered = replace(
        result,
        validation_basis=ValidationBasis.REALIZED_WEATHER_CALIBRATION,
    )
    with pytest.raises(WeatherDemandInputError, match="validation basis"):
        predict_selected_demand(basis_tampered, request)

    folds_tampered = replace(result, folds=result.folds[:-1])
    with pytest.raises(WeatherDemandInputError, match="fold evidence"):
        predict_selected_demand(folds_tampered, request)
