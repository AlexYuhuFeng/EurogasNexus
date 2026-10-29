"""API-to-SDK contract tests for serialized grid-forecast DTOs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest
from eurogas_nexus_sdk.weather_forecasts import (
    ForecastPointReading,
    ForecastReadEnvelope,
)
from pydantic import ValidationError

from eurogas_nexus.api.schemas.weather_forecasts import (
    ForecastReadEnvelope as ApiForecastReadEnvelope,
)

HASH_A = "a" * 64
HASH_B = "b" * 64
PLUS_TWO = timezone(timedelta(hours=2))


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


def _api_envelope_json() -> str:
    api_envelope = ApiForecastReadEnvelope.model_validate(
        {
            "data": [_reading()],
            "meta": {
                "source_references": ["ecmwf-open-data"],
                "warnings": ["research-only"],
                "attribution": "ECMWF",
            },
        }
    )
    return api_envelope.model_dump_json()


def test_api_json_round_trips_into_typed_sdk_and_preserves_contract() -> None:
    serialized = _api_envelope_json()

    envelope = ForecastReadEnvelope.model_validate_json(serialized)

    assert isinstance(envelope, ForecastReadEnvelope)
    assert len(envelope.data) == 1
    reading = envelope.data[0]
    assert isinstance(reading, ForecastPointReading)
    assert (
        reading.requested_latitude,
        reading.requested_longitude,
        reading.grid_latitude,
        reading.grid_longitude,
    ) == (51.5, -0.1, 51.5, 0.0)
    assert reading.raw_grib_sha256 == HASH_A
    assert reading.record_content_sha256 == HASH_B
    for timestamp in (
        reading.issued_at_utc,
        reading.valid_at_utc,
        reading.available_at_utc,
    ):
        assert timestamp.tzinfo is not None
        assert timestamp.utcoffset() == timedelta(0)
    assert envelope.meta.attribution == "ECMWF"
    assert envelope.meta.warnings == ("research-only",)
    assert envelope.meta.source_references == ("ecmwf-open-data",)


def test_future_valid_instant_is_allowed() -> None:
    reading = ForecastPointReading.model_validate(_reading())

    assert reading.valid_at_utc == datetime(2099, 1, 1, tzinfo=UTC)
    assert reading.valid_at_utc > reading.issued_at_utc


@pytest.mark.parametrize(
    ("field", "value"),
    [
        pytest.param("temperature_c", float("nan"), id="nan-temperature"),
        pytest.param("temperature_c", float("inf"), id="infinite-temperature"),
        pytest.param("unit", "K", id="wrong-unit"),
        pytest.param("raw_grib_sha256", "A" * 64, id="uppercase-raw-hash"),
        pytest.param("record_content_sha256", "b" * 63, id="short-record-hash"),
        pytest.param(
            "issued_at_utc",
            datetime(2025, 1, 1),
            id="naive-issued-at",
        ),
        pytest.param(
            "valid_at_utc",
            datetime(2099, 1, 1, tzinfo=PLUS_TWO),
            id="non-utc-offset-valid-at",
        ),
        pytest.param(
            "valid_at_utc",
            datetime(2024, 12, 31, tzinfo=UTC),
            id="valid-before-issued",
        ),
        pytest.param(
            "available_at_utc",
            datetime(2024, 12, 31, tzinfo=UTC),
            id="available-before-issued",
        ),
    ],
)
def test_sdk_refuses_invalid_contract_values(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        ForecastPointReading.model_validate(_reading(**{field: value}))
