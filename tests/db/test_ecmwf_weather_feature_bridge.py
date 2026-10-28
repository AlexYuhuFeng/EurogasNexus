"""SQLite integration from persisted ECMWF forecast rows to degree days.

The test drives the existing typed transport/decoded fixture, explicit
series/entity/mapping rows and append-only persistence.  It then projects the
actual stored ORM rows through the pure bridge; it never constructs a
``ForecastInstantRow`` directly or substitutes a repository value.
"""

from __future__ import annotations

import copy
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from eurogas_nexus.application.research.weather_demand_inputs import (
    LEFT_HOLD_INSTANT,
    ForecastBridgeValidationError,
    ForecastPointBinding,
    WeatherDemandBridgeConfig,
    build_weather_demand_inputs,
    compute_degree_days_from_bundle,
    project_forecast_observation_record,
)
from eurogas_nexus.db.models.research import ForecastObservationRecord
from eurogas_nexus.domain.market.gas_day import DEFAULT_GAS_DAY_CALENDAR
from eurogas_nexus.domain.research.weather_demand import (
    DegreeDayFeaturePolicy,
    DegreeDayPolicy,
    RegionLocationWeight,
)

try:
    from tests.db import test_ecmwf_forecast_repository as _repo
except ModuleNotFoundError:  # pytest prepend mode
    import test_ecmwf_forecast_repository as _repo  # type: ignore[no-redef]

# Reuse the repository's existing SQLite fixture and typed fixture builders.
session = _repo.session

GAS_DAY = date(2026, 1, 2)
ORIGIN = datetime(2026, 1, 2, 6, 0, tzinfo=UTC)
EARLY_RECEIPT = datetime(2026, 1, 2, 3, 0, tzinfo=UTC)
MID_RECEIPT = datetime(2026, 1, 2, 5, 0, tzinfo=UTC)
LATE_RECEIPT = datetime(2026, 1, 2, 7, 0, tzinfo=UTC)
LOCATION_ID = "L1"


def _policy() -> DegreeDayFeaturePolicy:
    return DegreeDayFeaturePolicy(
        region="GB",
        heating_base_c=18.0,
        cooling_base_c=20.0,
        max_gap_minutes=180,
        min_covered_fraction=1.0,
        location_weights=(RegionLocationWeight(LOCATION_ID, Decimal("1")),),
        gas_day_calendar=DEFAULT_GAS_DAY_CALENDAR,
        temporal_method=LEFT_HOLD_INSTANT,
    )


def _degree_policy(policy: DegreeDayFeaturePolicy) -> DegreeDayPolicy:
    return DegreeDayPolicy(
        heating_base_c=policy.heating_base_c,
        cooling_base_c=policy.cooling_base_c,
        max_gap_minutes=policy.max_gap_minutes,
        min_covered_fraction=policy.min_covered_fraction,
    )


def _persist_day_revision(
    session,
    monkeypatch,
    *,
    temperature_c: float,
    receipt: datetime,
    grib_bytes: bytes,
) -> None:
    """Persist a 3-hourly grid that brackets the gas day through the repository."""

    for step_hours in range(3, 31, 3):
        monkeypatch.setattr(_repo, "STEP_HOURS", step_hours)
        transport, decoded, _ = _repo._fixture(
            receipt=receipt,
            locations=_repo.SINGLE_LOCATION,
            temperatures_celsius=(temperature_c,),
            grib_bytes=grib_bytes,
        )
        _repo._append_forecast(
            session,
            transport,
            decoded,
            (_repo._binding("point-a"),),
        )
    session.flush()


def _build(session):
    rows = _repo._rows(session)
    projected = tuple(project_forecast_observation_record(row) for row in rows)
    policy = _policy()
    bundle = build_weather_demand_inputs(
        projected,
        (
            ForecastPointBinding(
                point_id="point-a",
                series_id=_repo.SERIES_ID,
                entity_id=_repo.ENTITY_ID,
                location_id=LOCATION_ID,
                region="GB",
            ),
        ),
        WeatherDemandBridgeConfig(
            feature_policy=policy,
            prediction_origin=ORIGIN,
            gas_days=(GAS_DAY,),
            max_hold_minutes=180,
        ),
    )
    result = compute_degree_days_from_bundle(bundle, _degree_policy(policy))
    return rows, projected, bundle, result


def _snapshot(record: ForecastObservationRecord) -> SimpleNamespace:
    """Copy an actual stored row without attaching it to the session."""

    return SimpleNamespace(
        **{
            column.name: copy.deepcopy(getattr(record, column.name))
            for column in ForecastObservationRecord.__table__.columns
        }
    )


def test_actual_persisted_rows_change_hdd_and_late_receipt_is_excluded(
    session, monkeypatch
) -> None:
    _repo._seed_identity(session, point_id="point-a")

    _persist_day_revision(
        session,
        monkeypatch,
        temperature_c=4.0,
        receipt=EARLY_RECEIPT,
        grib_bytes=_repo.GRIB_BYTES + b"-cold-revision",
    )
    rows, projected, bundle, result = _build(session)

    assert len(rows) == 10
    assert {row.temperature_c for row in projected} == {4.0}
    assert {row.valid_end_utc for row in projected} == {None}
    assert {row.model for row in projected} == {"ifs"}
    assert {row.run_id for row in projected} == {"20260102T00Z"}
    assert all(row.available_at_utc <= ORIGIN for row in projected)
    assert bundle.ready
    assert result is not None
    assert result.daily[0].daily_mean_hdd == pytest.approx(14.0)

    _persist_day_revision(
        session,
        monkeypatch,
        temperature_c=6.0,
        receipt=MID_RECEIPT,
        grib_bytes=_repo.GRIB_BYTES + b"-warmer-revision",
    )
    rows, projected, bundle, result = _build(session)

    assert len(rows) == 20
    assert result is not None
    assert result.daily[0].daily_mean_hdd == pytest.approx(12.0)
    assert {interval.mean_temperature_c for interval in bundle.intervals} == {6.0}

    _persist_day_revision(
        session,
        monkeypatch,
        temperature_c=20.0,
        receipt=LATE_RECEIPT,
        grib_bytes=_repo.GRIB_BYTES + b"-late-revision",
    )
    rows, projected, bundle, result = _build(session)

    assert len(rows) == 30
    assert any(row.available_at_utc > ORIGIN for row in projected)
    assert all(interval.available_at <= ORIGIN for interval in bundle.intervals)
    assert result is not None
    assert result.daily[0].daily_mean_hdd == pytest.approx(12.0)
    assert {interval.mean_temperature_c for interval in bundle.intervals} == {6.0}


def test_projection_refuses_malformed_persisted_row_fields(session, monkeypatch) -> None:
    _repo._seed_identity(session, point_id="point-a")
    monkeypatch.setattr(_repo, "STEP_HOURS", 6)
    transport, decoded, _ = _repo._fixture(
        receipt=EARLY_RECEIPT,
        locations=_repo.SINGLE_LOCATION,
        temperatures_celsius=(4.0,),
        grib_bytes=_repo.GRIB_BYTES + b"-malformed-revision",
    )
    _repo._append_forecast(
        session, transport, decoded, (_repo._binding("point-a"),)
    )
    session.flush()
    record = _repo._rows(session)[0]

    good = project_forecast_observation_record(_snapshot(record))
    assert good.valid_end_utc is None
    assert good.temperature_c == pytest.approx(4.0)

    bad = _snapshot(record)
    bad.unit = "K"
    with pytest.raises(ForecastBridgeValidationError, match="record unit"):
        project_forecast_observation_record(bad)

    bad = _snapshot(record)
    bad.source_system = "LEGACY_WEATHER"
    with pytest.raises(ForecastBridgeValidationError, match="record source_system"):
        project_forecast_observation_record(bad)

    bad = _snapshot(record)
    bad.quality_state = "OBSERVED"
    with pytest.raises(ForecastBridgeValidationError, match="record quality_state"):
        project_forecast_observation_record(bad)

    bad = _snapshot(record)
    bad.forecast_valid_end = bad.forecast_valid_start + timedelta(hours=3)
    with pytest.raises(ForecastBridgeValidationError, match="zero-length instant end"):
        project_forecast_observation_record(bad)

    bad = _snapshot(record)
    bad.provenance = {}
    with pytest.raises(ForecastBridgeValidationError, match="non-empty mapping"):
        project_forecast_observation_record(bad)

    bad = _snapshot(record)
    bad.provenance["grib"]["sha256"] = "0" * 64
    with pytest.raises(ForecastBridgeValidationError, match="grib hash"):
        project_forecast_observation_record(bad)

    bad = _snapshot(record)
    bad.provenance["temporal"]["forecast_valid_end"] = (
        bad.forecast_valid_start.isoformat()
    )
    with pytest.raises(ForecastBridgeValidationError, match="absent instant end"):
        project_forecast_observation_record(bad)

    bad = _snapshot(record)
    bad.provenance["binding"]["series_id"] = "other-series"
    with pytest.raises(ForecastBridgeValidationError, match="binding series_id"):
        project_forecast_observation_record(bad)
