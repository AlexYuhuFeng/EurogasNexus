"""Synthetic mechanics for the persisted ECMWF forecast-to-degree-day bridge.

These fixtures exercise explicit point/instant mechanics and provenance refusal.
They are not provider-accuracy evidence and contain no fetched or persisted data.
"""

import hashlib
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest

from eurogas_nexus.application.research.weather_demand_inputs import (
    LEFT_HOLD_INSTANT,
    MODEL_PROVIDER,
    SOURCE_SYSTEM,
    ForecastBridgeAmbiguityError,
    ForecastBridgeNotReadyError,
    ForecastBridgeValidationError,
    ForecastFieldRevisionConflictError,
    ForecastInstantRow,
    ForecastPointBinding,
    WeatherDemandBridgeConfig,
    WeatherDemandDiagnosticCode,
    WeatherDemandInputStatus,
    build_weather_demand_inputs,
    canonical_source_field_hash,
    compute_degree_days_from_bundle,
)
from eurogas_nexus.domain.market.gas_day import (
    DEFAULT_GAS_DAY_CALENDAR,
    gas_day_start_for_date,
)
from eurogas_nexus.domain.research.weather_demand import (
    DegreeDayFeaturePolicy,
    DegreeDayPolicy,
    RegionLocationWeight,
    TemperatureDerivationMethod,
)

GAS_DAY = date(2025, 1, 15)
DAY_START = gas_day_start_for_date(GAS_DAY)
DAY_END = gas_day_start_for_date(GAS_DAY + timedelta(days=1))
ORIGIN = DAY_START - timedelta(hours=1)


def _hash(*parts: object) -> str:
    return hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()


def _weights(*items: tuple[str, str]) -> tuple[RegionLocationWeight, ...]:
    return tuple(
        RegionLocationWeight(location_id, Decimal(weight))
        for location_id, weight in items
    )


def _policy(
    *,
    region: str = "GB",
    weights: tuple[RegionLocationWeight, ...] | None = None,
    max_gap: int = 0,
    temporal_method: TemperatureDerivationMethod = LEFT_HOLD_INSTANT,
) -> DegreeDayFeaturePolicy:
    return DegreeDayFeaturePolicy(
        region=region,
        heating_base_c=18.0,
        cooling_base_c=20.0,
        max_gap_minutes=max_gap,
        min_covered_fraction=1.0,
        location_weights=weights or (RegionLocationWeight("L1", Decimal("1")),),
        gas_day_calendar=DEFAULT_GAS_DAY_CALENDAR,
        temporal_method=temporal_method,
    )


def _binding(
    *,
    point: str = "P1",
    series: str = "S1",
    entity: str = "E1",
    location: str = "L1",
    region: str = "GB",
) -> ForecastPointBinding:
    return ForecastPointBinding(
        point_id=point,
        series_id=series,
        entity_id=entity,
        location_id=location,
        region=region,
    )


def _row(
    valid: datetime,
    temperature: float,
    *,
    point: str = "P1",
    series: str = "S1",
    entity: str = "E1",
    run: str = "run-1",
    model: str = "IFS",
    issued: datetime | None = None,
    available: datetime | None = None,
    field_hash: str | None = None,
    raw_grib: str | None = None,
    content: str | None = None,
    record_id: str | None = None,
    source_system: str = SOURCE_SYSTEM,
    model_provider: str = MODEL_PROVIDER,
    quality_state: str = "FORECAST",
    unit: str = "degC",
    valid_end: datetime | None = None,
    kelvin: float | None = None,
    provenance: dict | None = None,
) -> ForecastInstantRow:
    resolved_issued = issued or (DAY_START - timedelta(days=1))
    resolved_available = available or (resolved_issued + timedelta(hours=1))
    resolved_field = field_hash or _hash("field", run, valid.isoformat())
    resolved_record = record_id or f"rec-{point}-{valid.isoformat()}-{temperature}-{run}"
    return ForecastInstantRow(
        forecast_observation_id=resolved_record,
        point_id=point,
        series_id=series,
        entity_id=entity,
        issued_at_utc=resolved_issued,
        valid_at_utc=valid,
        available_at_utc=resolved_available,
        temperature_c=temperature,
        run_id=run,
        model=model,
        source_field_hash=resolved_field,
        raw_grib_sha256=raw_grib or _hash("grib", run, valid.isoformat()),
        record_content_sha256=content
        or _hash("content", resolved_record, temperature),
        valid_end_utc=valid_end,
        temperature_kelvin=kelvin,
        unit=unit,
        source_system=source_system,
        model_provider=model_provider,
        quality_state=quality_state,
        provenance=provenance,
    )


def _rows_for_day(
    gas_day: date,
    temperature: float,
    *,
    point: str = "P1",
    series: str = "S1",
    entity: str = "E1",
    run: str = "run-1",
    model: str = "IFS",
    issued: datetime | None = None,
    available: datetime | None = None,
    step_hours: int = 3,
) -> list[ForecastInstantRow]:
    start = gas_day_start_for_date(gas_day)
    end = gas_day_start_for_date(gas_day + timedelta(days=1))
    duration_hours = int((end - start).total_seconds() // 3_600)
    offsets = list(range(0, duration_hours, step_hours))
    if not offsets or offsets[-1] != duration_hours:
        offsets.append(duration_hours)
    return [
        _row(
            start + timedelta(hours=offset),
            temperature,
            point=point,
            series=series,
            entity=entity,
            run=run,
            model=model,
            issued=issued,
            available=available,
            record_id=f"{run}-{point}-{offset}-{temperature}",
        )
        for offset in offsets
    ]


def _config(
    policy: DegreeDayFeaturePolicy,
    *,
    days: tuple[date, ...] = (GAS_DAY,),
    origin: datetime = ORIGIN,
    max_hold: int = 180,
    **kwargs: int,
) -> WeatherDemandBridgeConfig:
    return WeatherDemandBridgeConfig(
        feature_policy=policy,
        prediction_origin=origin,
        gas_days=days,
        max_hold_minutes=max_hold,
        **kwargs,
    )


def _degree_policy(policy: DegreeDayFeaturePolicy) -> DegreeDayPolicy:
    return DegreeDayPolicy(
        heating_base_c=policy.heating_base_c,
        cooling_base_c=policy.cooling_base_c,
        max_gap_minutes=policy.max_gap_minutes,
        min_covered_fraction=policy.min_covered_fraction,
    )


def test_future_valid_instant_is_held_left_and_reaches_domain() -> None:
    policy = _policy()
    rows = _rows_for_day(GAS_DAY, 6.0)

    bundle = build_weather_demand_inputs(rows, (_binding(),), _config(policy))

    assert bundle.status is WeatherDemandInputStatus.READY
    assert bundle.ready
    assert bundle.selected_vintage is not None
    assert bundle.selected_vintage.run_id == "run-1"
    assert bundle.window_start_utc == DAY_START
    assert bundle.window_end_utc == DAY_END
    assert len(bundle.intervals) == 8
    assert all(interval.temporal_method is LEFT_HOLD_INSTANT for interval in bundle.intervals)
    assert all(interval.mean_temperature_c == 6.0 for interval in bundle.intervals)
    assert all(interval.available_at <= ORIGIN for interval in bundle.intervals)

    result = compute_degree_days_from_bundle(bundle, _degree_policy(policy))

    assert result is not None
    day = result.daily[0]
    assert day.duration_hours == pytest.approx(24.0)
    assert day.daily_mean_hdd == pytest.approx(12.0)
    assert day.time_integral_heating_degree_day == pytest.approx(12.0)
    assert day.coverage_complete
    assert result.feature_policy == policy
    assert result.feature_policy.temporal_method is LEFT_HOLD_INSTANT


def test_later_issue_and_later_publication_are_excluded() -> None:
    policy = _policy()
    eligible = _rows_for_day(GAS_DAY, 6.0)
    later_publication = [
        replace(
            row,
            available_at_utc=ORIGIN + timedelta(hours=1),
            temperature_c=-40.0,
            source_field_hash=_hash("late-field", row.valid_at_utc.isoformat()),
            record_content_sha256=_hash("late-content", row.forecast_observation_id),
        )
        for row in eligible
    ]
    later_issue = [
        replace(
            row,
            run_id="run-late",
            issued_at_utc=ORIGIN + timedelta(hours=1),
            available_at_utc=ORIGIN + timedelta(hours=2),
            temperature_c=-50.0,
            source_field_hash=_hash("late-issue-field", row.valid_at_utc.isoformat()),
            record_content_sha256=_hash("late-issue-content", row.forecast_observation_id),
        )
        for row in eligible
    ]

    bundle = build_weather_demand_inputs(
        eligible + later_publication + later_issue,
        (_binding(),),
        _config(policy),
    )

    assert bundle.selected_vintage is not None
    assert bundle.selected_vintage.run_id == "run-1"
    assert all(interval.mean_temperature_c == 6.0 for interval in bundle.intervals)
    result = compute_degree_days_from_bundle(bundle, _degree_policy(policy))
    assert result is not None
    assert result.daily[0].daily_mean_hdd == pytest.approx(12.0)


def test_latest_incomplete_run_is_not_filled_from_older_run() -> None:
    policy = _policy(weights=_weights(("L1", "0.5"), ("L2", "0.5")))
    bindings = (
        _binding(),
        _binding(point="P2", series="S2", entity="E2", location="L2"),
    )
    old = _rows_for_day(
        GAS_DAY,
        6.0,
        point="P1",
        series="S1",
        entity="E1",
        run="run-old",
        issued=DAY_START - timedelta(days=2),
        available=DAY_START - timedelta(days=2) + timedelta(hours=1),
    ) + _rows_for_day(
        GAS_DAY,
        6.0,
        point="P2",
        series="S2",
        entity="E2",
        run="run-old",
        issued=DAY_START - timedelta(days=2),
        available=DAY_START - timedelta(days=2) + timedelta(hours=1),
    )
    latest = _rows_for_day(
        GAS_DAY,
        10.0,
        point="P1",
        series="S1",
        entity="E1",
        run="run-latest",
        issued=DAY_START - timedelta(hours=2),
        available=ORIGIN,
    )

    bundle = build_weather_demand_inputs(old + latest, bindings, _config(policy))

    assert bundle.selected_vintage is not None
    assert bundle.selected_vintage.run_id == "run-latest"
    assert bundle.intervals
    assert {interval.location_id for interval in bundle.intervals} == {"L1"}
    codes = {diagnostic.code for diagnostic in bundle.diagnostics}
    assert WeatherDemandDiagnosticCode.NO_POINT_OBSERVATIONS in codes

    result = compute_degree_days_from_bundle(bundle, _degree_policy(policy))
    assert result is not None
    assert result.daily[0].daily_mean_hdd is None
    assert result.daily[0].coverage_complete is False


def test_wrong_region_policy_mapping_source_and_units_are_refused() -> None:
    policy = _policy()
    rows = _rows_for_day(GAS_DAY, 6.0)

    with pytest.raises(ForecastBridgeValidationError, match="region"):
        build_weather_demand_inputs(
            rows,
            (_binding(region="DE"),),
            _config(policy),
        )
    with pytest.raises(ForecastBridgeValidationError, match="temporal_method"):
        _config(
            replace(
                policy,
                temporal_method=TemperatureDerivationMethod.PROVIDER_INTERVAL_MEAN,
            )
        )
    with pytest.raises(ForecastBridgeValidationError, match="identity"):
        build_weather_demand_inputs(
            [replace(rows[0], series_id="SX")],
            (_binding(),),
            _config(policy),
        )
    with pytest.raises(ForecastBridgeValidationError, match="source_system"):
        build_weather_demand_inputs(
            [replace(rows[0], source_system="LEGACY_WEATHER")],
            (_binding(),),
            _config(policy),
        )
    with pytest.raises(ForecastBridgeValidationError, match="unit"):
        build_weather_demand_inputs(
            [replace(rows[0], unit="K")],
            (_binding(),),
            _config(policy),
        )
    with pytest.raises(ForecastBridgeValidationError, match="model_provider"):
        build_weather_demand_inputs(
            [replace(rows[0], model_provider="OTHER")],
            (_binding(),),
            _config(policy),
        )
    with pytest.raises(ForecastBridgeValidationError, match="quality_state"):
        build_weather_demand_inputs(
            [replace(rows[0], quality_state="OBSERVED")],
            (_binding(),),
            _config(policy),
        )
    with pytest.raises(ForecastBridgeValidationError, match="valid_end"):
        build_weather_demand_inputs(
            [replace(rows[0], valid_end_utc=DAY_START)],
            (_binding(),),
            _config(policy),
        )


def _revision_rows(
    *,
    point: str,
    series: str,
    entity: str,
    field_hash: str,
    temperature: float,
    available: datetime,
) -> list[ForecastInstantRow]:
    issued = DAY_START - timedelta(days=1)
    valids = (DAY_START, DAY_START + timedelta(hours=3))
    return [
        _row(
            valid,
            temperature,
            point=point,
            series=series,
            entity=entity,
            run="run-1",
            issued=issued,
            available=available,
            field_hash=field_hash,
            raw_grib=_hash("grib", field_hash, valid.isoformat()),
            content=_hash("content", point, valid.isoformat(), temperature),
            record_id=f"{point}-{field_hash[:8]}-{valid.isoformat()}",
        )
        for valid in valids
    ]


def test_latest_source_field_revision_is_selected_and_not_mixed() -> None:
    policy = _policy(weights=_weights(("L1", "0.5"), ("L2", "0.5")))
    bindings = (
        _binding(),
        _binding(point="P2", series="S2", entity="E2", location="L2"),
    )
    old_field = _hash("field-old")
    new_field = _hash("field-new")
    old = _revision_rows(
        point="P1",
        series="S1",
        entity="E1",
        field_hash=old_field,
        temperature=10.0,
        available=ORIGIN - timedelta(hours=3),
    ) + _revision_rows(
        point="P2",
        series="S2",
        entity="E2",
        field_hash=old_field,
        temperature=10.0,
        available=ORIGIN - timedelta(hours=3),
    )
    p1_new = _revision_rows(
        point="P1",
        series="S1",
        entity="E1",
        field_hash=new_field,
        temperature=2.0,
        available=ORIGIN,
    )

    with pytest.raises(ForecastFieldRevisionConflictError, match="different source-field"):
        build_weather_demand_inputs(old + p1_new, bindings, _config(policy))

    p2_new = _revision_rows(
        point="P2",
        series="S2",
        entity="E2",
        field_hash=new_field,
        temperature=2.0,
        available=ORIGIN,
    )
    bundle = build_weather_demand_inputs(old + p1_new + p2_new, bindings, _config(policy))

    assert bundle.selected_vintage is not None
    assert bundle.selected_vintage.run_id == "run-1"
    assert len(bundle.intervals) == 2
    assert all(interval.mean_temperature_c == 2.0 for interval in bundle.intervals)
    assert all(interval.temporal_method is LEFT_HOLD_INSTANT for interval in bundle.intervals)


def test_equal_latest_receipt_with_different_field_hashes_is_ambiguous() -> None:
    policy = _policy()
    first = _row(
        DAY_START,
        6.0,
        available=ORIGIN - timedelta(hours=1),
        field_hash=_hash("field-a"),
        record_id="record-a",
    )
    second = replace(
        first,
        forecast_observation_id="record-b",
        temperature_c=7.0,
        source_field_hash=_hash("field-b"),
        record_content_sha256=_hash("content-b"),
    )

    with pytest.raises(ForecastBridgeAmbiguityError, match="same latest receipt"):
        build_weather_demand_inputs([first, second], (_binding(),), _config(policy))


def test_hold_gap_and_window_edges_do_not_extrapolate() -> None:
    policy = _policy()
    rows = (
        _row(DAY_START, 6.0, record_id="sample-0"),
        _row(DAY_START + timedelta(hours=3), 12.0, record_id="sample-3"),
        _row(DAY_START + timedelta(hours=9), 15.0, record_id="sample-9"),
    )

    bundle = build_weather_demand_inputs(rows, (_binding(),), _config(policy))

    assert len(bundle.intervals) == 1
    interval = bundle.intervals[0]
    assert interval.start_utc == DAY_START
    assert interval.end_utc == DAY_START + timedelta(hours=3)
    assert interval.mean_temperature_c == 6.0
    codes = {diagnostic.code for diagnostic in bundle.diagnostics}
    assert WeatherDemandDiagnosticCode.HOLD_GAP_EXCEEDED in codes
    assert WeatherDemandDiagnosticCode.NO_RIGHT_BRACKET in codes
    result = compute_degree_days_from_bundle(bundle, _degree_policy(policy))
    assert result is not None
    assert result.daily[0].daily_mean_hdd is None

    later_rows = (
        _row(DAY_START + timedelta(hours=3), 6.0, record_id="later-3"),
        _row(DAY_START + timedelta(hours=6), 9.0, record_id="later-6"),
    )
    later = build_weather_demand_inputs(later_rows, (_binding(),), _config(policy))
    assert later.intervals
    assert later.intervals[0].start_utc == DAY_START + timedelta(hours=3)
    assert all(
        interval.start_utc >= DAY_START + timedelta(hours=3)
        for interval in later.intervals
    )
    assert WeatherDemandDiagnosticCode.NO_LEFT_BRACKET in {
        diagnostic.code for diagnostic in later.diagnostics
    }


@pytest.mark.parametrize(
    ("gas_day", "duration_hours"),
    (
        (date(2025, 3, 29), 23.0),
        (date(2025, 10, 25), 25.0),
    ),
)
def test_dst_gas_day_uses_existing_domain_true_utc_duration(
    gas_day: date, duration_hours: float
) -> None:
    policy = _policy()
    start = gas_day_start_for_date(gas_day)
    origin = start - timedelta(hours=1)
    rows = _rows_for_day(
        gas_day,
        6.0,
        issued=start - timedelta(days=1),
        available=origin,
    )
    bundle = build_weather_demand_inputs(
        rows,
        (_binding(),),
        _config(policy, days=(gas_day,), origin=origin),
    )

    assert bundle.ready
    assert bundle.intervals[-1].end_utc == gas_day_start_for_date(
        gas_day + timedelta(days=1)
    )
    result = compute_degree_days_from_bundle(bundle, _degree_policy(policy))
    assert result is not None
    day = result.daily[0]
    assert day.duration_hours == pytest.approx(duration_hours)
    assert day.daily_mean_hdd == pytest.approx(12.0)
    assert day.time_integral_heating_degree_day == pytest.approx(
        12.0 * duration_hours / 24.0
    )


def test_changing_actual_persisted_temperature_changes_hdd() -> None:
    policy = _policy()
    cold = _rows_for_day(GAS_DAY, 4.0)
    warm = _rows_for_day(GAS_DAY, 6.0)

    cold_bundle = build_weather_demand_inputs(cold, (_binding(),), _config(policy))
    warm_bundle = build_weather_demand_inputs(warm, (_binding(),), _config(policy))
    cold_result = compute_degree_days_from_bundle(cold_bundle, _degree_policy(policy))
    warm_result = compute_degree_days_from_bundle(warm_bundle, _degree_policy(policy))

    assert cold_result is not None
    assert warm_result is not None
    assert cold_result.daily[0].daily_mean_hdd == pytest.approx(14.0)
    assert warm_result.daily[0].daily_mean_hdd == pytest.approx(12.0)
    assert cold_result.daily[0].daily_mean_hdd != warm_result.daily[0].daily_mean_hdd


def test_intervals_are_derived_left_hold_and_reference_both_boundaries() -> None:
    policy = _policy()
    left = _row(
        DAY_START,
        6.0,
        record_id="left",
        field_hash=_hash("field-left"),
        raw_grib=_hash("grib-left"),
        content=_hash("content-left"),
    )
    right = _row(
        DAY_START + timedelta(hours=3),
        12.0,
        record_id="right",
        field_hash=_hash("field-right"),
        raw_grib=_hash("grib-right"),
        content=_hash("content-right"),
    )

    baseline = build_weather_demand_inputs([left, right], (_binding(),), _config(policy))
    interval = baseline.intervals[0]
    assert interval.temporal_method is LEFT_HOLD_INSTANT
    assert interval.temporal_method is not TemperatureDerivationMethod.PROVIDER_INTERVAL_MEAN
    assert interval.mean_temperature_c == 6.0
    assert interval.source_ref.startswith("sha256:")
    assert len(interval.source_ref) == 71

    right_changed = build_weather_demand_inputs(
        [
            left,
            replace(
                right,
                raw_grib_sha256=_hash("grib-right-2"),
                record_content_sha256=_hash("content-right-2"),
            ),
        ],
        (_binding(),),
        _config(policy),
    )
    left_changed = build_weather_demand_inputs(
        [
            replace(left, record_content_sha256=_hash("content-left-2")),
            right,
        ],
        (_binding(),),
        _config(policy),
    )

    assert right_changed.intervals[0].source_ref != interval.source_ref
    assert left_changed.intervals[0].source_ref != interval.source_ref
    assert left_changed.intervals[0].source_ref != right_changed.intervals[0].source_ref


def test_all_missing_returns_not_ready_without_zero_baseline() -> None:
    policy = _policy()
    bundle = build_weather_demand_inputs((), (_binding(),), _config(policy))

    assert bundle.status is WeatherDemandInputStatus.MISSING
    assert bundle.ready is False
    assert bundle.selected_vintage is None
    assert bundle.intervals == ()
    assert WeatherDemandDiagnosticCode.NO_ELIGIBLE_FORECAST in {
        diagnostic.code for diagnostic in bundle.diagnostics
    }
    assert compute_degree_days_from_bundle(bundle, _degree_policy(policy)) is None
    with pytest.raises(ForecastBridgeNotReadyError):
        bundle.to_degree_day_request()


def test_helper_refuses_degree_policy_basis_mismatch() -> None:
    policy = _policy()
    bundle = build_weather_demand_inputs(
        _rows_for_day(GAS_DAY, 6.0),
        (_binding(),),
        _config(policy),
    )
    wrong_heating = replace(_degree_policy(policy), heating_base_c=15.5)
    wrong_gap = replace(_degree_policy(policy), max_gap_minutes=60)

    with pytest.raises(ForecastBridgeValidationError, match="degree-day policy"):
        compute_degree_days_from_bundle(bundle, wrong_heating)
    with pytest.raises(ForecastBridgeValidationError, match="degree-day policy"):
        compute_degree_days_from_bundle(bundle, wrong_gap)

    result = compute_degree_days_from_bundle(bundle, _degree_policy(policy))
    assert result is not None
    assert result.feature_policy == policy
    assert result.feature_policy.location_weights == policy.location_weights


def test_provenance_and_kelvin_metadata_are_validated() -> None:
    policy = _policy()
    version = {
        "grib_sha256": _hash("grib-metadata"),
        "run_date": "2025-01-14",
        "cycle_hour": 0,
        "step_hours": 3,
        "valid_at_utc": DAY_START.isoformat(),
        "param_id": 167,
        "units": "K",
        "grid": {"type": "regular_ll", "ni": 1440, "nj": 721},
    }
    field_hash = canonical_source_field_hash(version)
    issued = DAY_START - timedelta(days=1)
    provenance = {
        "source_system": SOURCE_SYSTEM,
        "provider": MODEL_PROVIDER,
        "content_sha256": _hash("content-metadata"),
        "grib": {"sha256": _hash("grib-metadata")},
        "source_field_version": version,
        "temporal": {"scope": "instant", "forecast_valid_end": None},
        "point": {
            "point_id": "P1",
            "temperature_celsius": 6.0,
            "temperature_kelvin": 279.15,
            "represents_observing_station": False,
        },
        "run": {
            "forecast_issued_at_utc": issued.isoformat(),
            "forecast_valid_at_utc": DAY_START.isoformat(),
        },
    }
    row = _row(
        DAY_START,
        6.0,
        issued=issued,
        available=ORIGIN,
        field_hash=field_hash,
        raw_grib=_hash("grib-metadata"),
        content=_hash("content-metadata"),
        kelvin=279.15,
        provenance=provenance,
    )

    bundle = build_weather_demand_inputs([row], (_binding(),), _config(policy))
    assert bundle.status is WeatherDemandInputStatus.MISSING

    with pytest.raises(ForecastBridgeValidationError, match="kelvin"):
        build_weather_demand_inputs(
            [replace(row, temperature_kelvin=300.0)],
            (_binding(),),
            _config(policy),
        )
    with pytest.raises(ForecastBridgeValidationError, match="source_system"):
        build_weather_demand_inputs(
            [replace(row, provenance={**provenance, "source_system": "LEGACY"})],
            (_binding(),),
            _config(policy),
        )
    with pytest.raises(ForecastBridgeValidationError, match="instant end"):
        build_weather_demand_inputs(
            [
                replace(
                    row,
                    provenance={
                        **provenance,
                        "temporal": {
                            "scope": "instant",
                            "forecast_valid_end": DAY_START.isoformat(),
                        },
                    },
                )
            ],
            (_binding(),),
            _config(policy),
        )
    with pytest.raises(ForecastBridgeValidationError, match="source_field_hash"):
        build_weather_demand_inputs(
            [replace(row, source_field_hash=_hash("other-field"))],
            (_binding(),),
            _config(policy),
        )


def test_row_point_window_and_cross_product_bounds_are_enforced() -> None:
    policy = _policy()
    rows = _rows_for_day(GAS_DAY, 6.0)

    with pytest.raises(ForecastBridgeValidationError, match="max_rows"):
        build_weather_demand_inputs(rows, (_binding(),), _config(policy, max_rows=1))
    with pytest.raises(ForecastBridgeValidationError, match="max_points"):
        build_weather_demand_inputs(
            rows,
            (
                _binding(),
                _binding(point="P2", series="S2", entity="E2"),
            ),
            _config(policy, max_points=1),
        )
    with pytest.raises(ForecastBridgeValidationError, match="window"):
        _config(
            policy,
            days=(GAS_DAY, GAS_DAY + timedelta(days=2)),
            max_window_days=1,
        )
    with pytest.raises(ForecastBridgeValidationError, match="cross product"):
        build_weather_demand_inputs(
            rows,
            (_binding(),),
            _config(policy, max_cross_product=1),
        )
    with pytest.raises(ForecastBridgeValidationError, match="max_intervals"):
        build_weather_demand_inputs(
            rows,
            (_binding(),),
            _config(policy, max_intervals=1),
        )


def test_missing_weighted_point_binding_stays_missing() -> None:
    policy = _policy(weights=_weights(("L1", "0.5"), ("L2", "0.5")))
    bundle = build_weather_demand_inputs(
        _rows_for_day(GAS_DAY, 6.0),
        (_binding(),),
        _config(policy),
    )

    assert bundle.ready
    assert all(interval.location_id == "L1" for interval in bundle.intervals)
    assert WeatherDemandDiagnosticCode.MISSING_POINT_BINDING in {
        diagnostic.code for diagnostic in bundle.diagnostics
    }
    result = compute_degree_days_from_bundle(bundle, _degree_policy(policy))
    assert result is not None
    assert result.daily[0].daily_mean_hdd is None
    assert result.daily[0].coverage_complete is False


def test_interval_availability_is_max_of_both_boundaries_and_never_after_origin() -> None:
    policy = _policy()
    left = _row(
        DAY_START,
        6.0,
        issued=ORIGIN - timedelta(hours=6),
        available=ORIGIN - timedelta(hours=3),
        record_id="available-left",
    )
    right = _row(
        DAY_START + timedelta(hours=3),
        12.0,
        issued=ORIGIN - timedelta(hours=6),
        available=ORIGIN - timedelta(hours=1),
        record_id="available-right",
    )

    bundle = build_weather_demand_inputs([left, right], (_binding(),), _config(policy))

    assert len(bundle.intervals) == 1
    assert bundle.intervals[0].available_at == max(
        left.available_at_utc, right.available_at_utc
    )
    assert bundle.intervals[0].mean_temperature_c == 6.0

    late_right = replace(right, available_at_utc=ORIGIN + timedelta(hours=1))
    not_ready = build_weather_demand_inputs(
        [left, late_right],
        (_binding(),),
        _config(policy),
    )
    assert not_ready.ready is False
    assert not_ready.intervals == ()
    assert WeatherDemandDiagnosticCode.NO_RIGHT_BRACKET in {
        diagnostic.code for diagnostic in not_ready.diagnostics
    }


def test_window_clipping_retains_full_boundary_references() -> None:
    policy = _policy()
    left = _row(
        DAY_START - timedelta(hours=2),
        10.0,
        record_id="pre-window",
        field_hash=_hash("pre-window-field"),
        content=_hash("pre-window-content"),
    )
    right = _row(
        DAY_START + timedelta(hours=1),
        20.0,
        record_id="post-window-start",
        field_hash=_hash("post-window-field"),
    )

    bundle = build_weather_demand_inputs([left, right], (_binding(),), _config(policy))

    assert len(bundle.intervals) == 1
    interval = bundle.intervals[0]
    assert interval.start_utc == DAY_START
    assert interval.end_utc == DAY_START + timedelta(hours=1)
    assert interval.mean_temperature_c == 10.0

    changed = build_weather_demand_inputs(
        [replace(left, record_content_sha256=_hash("pre-window-content-2")), right],
        (_binding(),),
        _config(policy),
    )
    assert changed.intervals[0].start_utc == DAY_START
    assert changed.intervals[0].end_utc == DAY_START + timedelta(hours=1)
    assert changed.intervals[0].source_ref != interval.source_ref
