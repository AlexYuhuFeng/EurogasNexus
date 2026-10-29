"""Focused contract tests for the additive grid-forecast DTOs."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from eurogas_nexus.api.schemas.weather_forecasts import (
    ForecastPointReading,
    ForecastReadEnvelope,
)

HASH_A = "a" * 64
HASH_B = "b" * 64


def _reading(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "observation_id": "obs-1",
        "point_id": "london",
        "series_id": "ecmwf-2m-temperature",
        "entity_id": "weather",
        "source_system": "ECMWF_OPEN_DATA",
        "provider": "ECMWF",
        "model": "ifs",
        "run_id": "20250101T00",
        "issued_at_utc": datetime(2025, 1, 1, tzinfo=UTC),
        "valid_at_utc": datetime(2099, 1, 1, tzinfo=UTC),
        "available_at_utc": datetime(2025, 1, 1, 1, tzinfo=UTC),
        "temperature_c": 9.177087402343773,
        "unit": "degC",
        "raw_grib_sha256": HASH_A,
        "record_content_sha256": HASH_B,
        "requested_latitude": 51.5,
        "requested_longitude": -0.1,
        "grid_latitude": 51.5,
        "grid_longitude": 0.0,
    }
    values.update(overrides)
    return values


def _envelope(readings: list[dict[str, object]]) -> dict[str, object]:
    return {
        "data": readings,
        "meta": {
            "source_references": ["ecmwf-open-data"],
            "warnings": ["research-only"],
            "attribution": "ECMWF",
        },
    }


def test_future_valid_is_allowed_and_json_round_trip_preserves_utc() -> None:
    reading = ForecastPointReading.model_validate(_reading())
    assert reading.valid_at_utc.year == 2099
    encoded = json.loads(reading.model_dump_json())
    for field in ("issued_at_utc", "valid_at_utc", "available_at_utc"):
        assert encoded[field].endswith(("Z", "+00:00"))
    assert ForecastPointReading.model_validate_json(
        reading.model_dump_json()
    ) == reading


def test_naive_and_non_utc_timestamps_are_refused() -> None:
    with pytest.raises(ValidationError):
        ForecastPointReading.model_validate(
            _reading(issued_at_utc=datetime(2025, 1, 1))
        )
    plus_two = timezone(timedelta(hours=2))
    with pytest.raises(ValidationError):
        ForecastPointReading.model_validate(
            _reading(valid_at_utc=datetime(2099, 1, 1, tzinfo=plus_two))
        )


@pytest.mark.parametrize(
    "override",
    [{"unit": "K"}, {"source_system": "ERA5"}, {"provider": "OTHER"}],
)
def test_unit_source_and_provider_literals_are_refused(
    override: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ForecastPointReading.model_validate(_reading(**override))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("temperature_c", float("nan")),
        ("temperature_c", float("inf")),
        ("requested_latitude", 90.1),
        ("grid_latitude", -90.1),
        ("requested_longitude", 180.1),
        ("grid_longitude", -180.1),
    ],
)
def test_nonfinite_temperature_and_out_of_bounds_coordinates_are_refused(
    field: str, value: float
) -> None:
    with pytest.raises(ValidationError):
        ForecastPointReading.model_validate(_reading(**{field: value}))


@pytest.mark.parametrize("field", ["raw_grib_sha256", "record_content_sha256"])
def test_both_source_hashes_are_required(field: str) -> None:
    values = _reading()
    del values[field]
    with pytest.raises(ValidationError):
        ForecastPointReading.model_validate(values)


def test_source_hashes_must_be_exact_lowercase_hex64() -> None:
    with pytest.raises(ValidationError):
        ForecastPointReading.model_validate(_reading(raw_grib_sha256="A" * 64))
    with pytest.raises(ValidationError):
        ForecastPointReading.model_validate(_reading(record_content_sha256="b" * 63))


def test_available_at_cannot_precede_issued_at() -> None:
    issued = datetime(2025, 1, 1, tzinfo=UTC)
    with pytest.raises(ValidationError):
        ForecastPointReading.model_validate(
            _reading(
                issued_at_utc=issued,
                available_at_utc=issued - timedelta(microseconds=1),
            )
        )
    accepted = ForecastPointReading.model_validate(
        _reading(issued_at_utc=issued, available_at_utc=issued)
    )
    assert accepted.available_at_utc == issued


def test_envelope_is_bounded_and_typed_meta_is_immutable() -> None:
    reading = _reading()
    accepted = ForecastReadEnvelope.model_validate(_envelope([reading] * 256))
    assert len(accepted.data) == 256
    assert accepted.meta.research_only is True
    assert accepted.meta.point_kind == "FORECAST_GRID_POINT"
    assert isinstance(accepted.meta.source_references, tuple)
    with pytest.raises(ValidationError):
        ForecastReadEnvelope.model_validate(_envelope([reading] * 257))
    with pytest.raises(ValidationError):
        accepted.meta.research_only = False
    with pytest.raises(ValidationError):
        accepted.meta = accepted.meta


def test_contract_is_separate_from_legacy_station_observations() -> None:
    fields = set(ForecastPointReading.model_fields)
    assert "station_id" not in fields
    assert not fields & {"interval_mean_c", "interval_start_utc", "interval_end_utc"}
    with pytest.raises(ValidationError):
        ForecastPointReading.model_validate(_reading(station_id="station-1"))

def test_validity_before_issue_is_refused() -> None:
    with pytest.raises(ValidationError, match='valid_at_utc must not precede'):
        ForecastPointReading(**_reading(valid_at_utc=datetime(2024, 12, 31, tzinfo=UTC)))
