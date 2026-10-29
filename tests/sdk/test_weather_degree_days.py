"""Contract tests for the typed weather degree-day SDK client."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from inspect import getsource

import httpx
import pytest
from eurogas_nexus_sdk import weather_degree_days as sdk
from pydantic import ValidationError


def _request() -> sdk.WeatherDegreeDayRequest:
    return sdk.WeatherDegreeDayRequest(
        bindings=[
            {
                "point_id": "point-1",
                "series_id": "series-1",
                "entity_id": "entity-1",
                "location_id": "loc-1",
                "region": "DE",
                "weight": Decimal("0.6"),
            },
            {
                "point_id": "point-2",
                "series_id": "series-2",
                "entity_id": "entity-2",
                "location_id": "loc-2",
                "region": "DE",
                "weight": Decimal("0.4"),
            },
        ],
        gas_days=[date(2026, 1, 2), date(2026, 1, 1)],
        prediction_origin=datetime(
            2025, 12, 31, 13, 0, tzinfo=timezone(timedelta(hours=1))
        ),
        heating_base_c=15.5,
        cooling_base_c=18.0,
        calendar="EU-CAM-UTC-2025",
        max_hold_minutes=360,
        min_covered_fraction=0.5,
    )


def _expected_body() -> dict:
    return {
        "region": "DE",
        "point_bindings": [
            {
                "point_id": "point-1",
                "series_id": "series-1",
                "entity_id": "entity-1",
                "location_id": "loc-1",
                "region": "DE",
                "weight": "0.6",
            },
            {
                "point_id": "point-2",
                "series_id": "series-2",
                "entity_id": "entity-2",
                "location_id": "loc-2",
                "region": "DE",
                "weight": "0.4",
            },
        ],
        "gas_days": ["2026-01-01", "2026-01-02"],
        "prediction_origin": "2025-12-31T12:00:00Z",
        "heating_base_c": 15.5,
        "cooling_base_c": 18.0,
        "gas_day_calendar": "EU-CAM-UTC-2025",
        "max_hold_minutes": 360,
        "min_covered_fraction": 0.5,
    }


def _vintage() -> dict:
    return {
        "provider": "ECMWF",
        "model": "IFS",
        "run_id": "run-1",
        "issued_at": "2025-12-31T06:00:00Z",
    }


def _meta(status: str, warnings: list[str]) -> dict:
    return {
        "research_only": True,
        "human_review_required": True,
        "status": status,
        "attribution": "ECMWF Open Data (CC BY 4.0)",
        "source_references": ["ECMWF_OPEN_DATA", "fixture:run-1"],
        "feature_policy_hash": "sha256:fixture-policy",
        "prediction_origin": "2025-12-31T12:00:00Z",
        "gas_days": ["2026-01-01", "2026-01-02"],
        "max_hold_minutes": 360,
        "query_limit": 256,
        "selected_forecast_vintage": _vintage(),
        "warnings": warnings,
        "vendor_trace": {"cursor": "abc"},
    }


def _ready_payload() -> dict:
    return {
        "data": {
            "region": "DE",
            "input_type": "FORECAST_VINTAGE",
            "prediction_origin": "2025-12-31T12:00:00Z",
            "gas_day_calendar": "EU-CAM-UTC-2025",
            "feature_policy": {
                "region": "DE",
                "heating_base_c": 15.5,
                "cooling_base_c": 18.0,
                "max_gap_minutes": 360,
                "min_covered_fraction": 0.5,
                "location_weights": [
                    {"location_id": "loc-1", "weight": "0.6"},
                    {"location_id": "loc-2", "weight": "0.4"},
                ],
                "gas_day_calendar": "EU-CAM-UTC-2025",
                "temporal_method": "EXPLICIT_DERIVED_HOLD",
                "method_version": "degree-day-mean-and-integral/v1",
            },
            "heating_base_c": 15.5,
            "cooling_base_c": 18.0,
            "max_gap_seconds": 21600.0,
            "min_covered_fraction": 0.5,
            "selected_vintage": _vintage(),
            "method_version": "degree-day-mean-and-integral/v1",
            "daily": [
                {
                    "gas_day": "2026-01-01",
                    "gas_day_start_utc": "2026-01-01T05:00:00Z",
                    "gas_day_end_utc": "2026-01-02T05:00:00Z",
                    "duration_hours": 24.0,
                    "daily_mean_temperature_c": 2.5,
                    "daily_mean_hdd": 13.0,
                    "daily_mean_cdd": 0.0,
                    "time_integral_heating_degree_day": 312.0,
                    "time_integral_cooling_degree_day": 0.0,
                    "covered_fraction": 1.0,
                    "coverage_complete": True,
                    "missing_reason": None,
                    "available_at": "2025-12-31T12:00:00Z",
                    "source_refs": ["ECMWF_OPEN_DATA:run-1:loc-1"],
                    "locations": [
                        {
                            "location_id": "loc-1",
                            "weight": "0.6",
                            "covered_fraction": 1.0,
                            "largest_gap_seconds": 0.0,
                            "available_at": "2025-12-31T12:00:00Z",
                            "mean_temperature_c": 2.5,
                            "daily_mean_hdd": 13.0,
                            "daily_mean_cdd": 0.0,
                            "heating_degree_day_integral": 312.0,
                            "cooling_degree_day_integral": 0.0,
                            "complete": True,
                            "missing_reason": None,
                            "source_refs": ["ECMWF_OPEN_DATA:run-1:loc-1"],
                        }
                    ],
                },
                {
                    "gas_day": "2026-01-02",
                    "gas_day_start_utc": "2026-01-02T05:00:00Z",
                    "gas_day_end_utc": "2026-01-03T05:00:00Z",
                    "duration_hours": 24.0,
                    "daily_mean_temperature_c": None,
                    "daily_mean_hdd": None,
                    "daily_mean_cdd": None,
                    "time_integral_heating_degree_day": None,
                    "time_integral_cooling_degree_day": None,
                    "covered_fraction": 0.25,
                    "coverage_complete": False,
                    "missing_reason": "INSUFFICIENT_COVERAGE",
                    "available_at": None,
                    "source_refs": [],
                    "locations": [],
                },
            ],
            "source_refs": ["ECMWF_OPEN_DATA:run-1"],
        },
        "meta": _meta(
            "READY",
            [
                "CALLER_DEFINED_REGION_WEIGHTS",
                "LEFT_HOLD_APPROXIMATION",
                "MISSING_COVERAGE_NULL",
                "RESEARCH_ONLY",
                "HUMAN_REVIEW_REQUIRED",
            ],
        ),
    }


def _not_ready_payload() -> dict:
    return {
        "data": {
            "status": "NOT_READY",
            "diagnostics": [
                {
                    "code": "NO_ELIGIBLE_FORECAST",
                    "detail": "No forecast vintage is available at the origin.",
                    "location_id": "loc-1",
                    "valid_at_utc": "2025-12-31T12:00:00Z",
                }
            ],
        },
        "meta": _meta(
            "NOT_READY",
            [
                "CALLER_DEFINED_REGION_WEIGHTS",
                "LEFT_HOLD_APPROXIMATION",
                "MISSING_COVERAGE_NULL",
                "RESEARCH_ONLY",
                "HUMAN_REVIEW_REQUIRED",
                "FORECAST_INPUT_NOT_READY",
            ],
        ),
    }


class _FakeResponse:
    def __init__(self, payload: dict | None = None, error: Exception | None = None):
        self.content = json.dumps(payload or {}).encode()
        self._error = error

    def raise_for_status(self) -> None:
        if self._error is not None:
            raise self._error


def test_request_json_is_backend_compatible_and_weights_are_strings() -> None:
    request = _request()
    body = request.model_dump(mode="json")

    assert body == _expected_body()
    assert body["region"] == "DE"
    assert body["prediction_origin"] == "2025-12-31T12:00:00Z"
    assert body["gas_days"] == ["2026-01-01", "2026-01-02"]
    assert all(
        isinstance(binding["weight"], str)
        for binding in body["point_bindings"]
    )
    assert [binding["weight"] for binding in body["point_bindings"]] == ["0.6", "0.4"]


def test_request_body_is_accepted_by_the_backend_schema() -> None:
    schema = pytest.importorskip("eurogas_nexus.api.schemas.weather_degree_days")

    schema.WeatherDegreeDayRequest.model_validate(_request().model_dump(mode="json"))


def test_request_requires_explicit_bases_and_origin() -> None:
    fields = _request().model_dump(mode="json")
    fields.pop("heating_base_c")

    with pytest.raises(ValidationError):
        sdk.WeatherDegreeDayRequest(**fields)

    fields = _request().model_dump(mode="json")
    fields.pop("prediction_origin")
    with pytest.raises(ValidationError):
        sdk.WeatherDegreeDayRequest(**fields)


def test_module_has_no_backend_imports_or_clock_defaults() -> None:
    source = getsource(sdk)

    assert '"/api/weather/degree-days"' in source
    assert sdk.WEATHER_DEGREE_DAYS_PATH == "/api/weather/degree-days"
    assert "eurogas_nexus.api" not in source
    assert "eurogas_nexus.domain" not in source
    assert "eurogas_nexus.application" not in source
    assert "datetime.now" not in source
    assert "date.today" not in source


def test_mocked_http_parses_full_coverage_and_preserves_missing_nulls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict, float]] = []

    def fake_post(url: str, *, json: dict, timeout: float) -> _FakeResponse:
        calls.append((url, json, timeout))
        return _FakeResponse(_ready_payload())

    monkeypatch.setattr(sdk._http, "post", fake_post)

    envelope = sdk.compute_weather_degree_days("http://backend:8000/", _request())

    assert calls == [
        (
            "http://backend:8000/api/weather/degree-days",
            _expected_body(),
            30,
        )
    ]
    assert isinstance(envelope, sdk.WeatherDegreeDayEnvelope)
    assert envelope.status == "READY"
    assert envelope.data.status == "READY"
    assert envelope.policy_hash == "sha256:fixture-policy"
    assert envelope.data.daily[0].coverage_complete is True
    assert envelope.data.daily[0].covered_fraction == 1.0
    assert envelope.data.daily[0].gas_day_boundaries == (
        datetime(2026, 1, 1, 5, tzinfo=UTC),
        datetime(2026, 1, 2, 5, tzinfo=UTC),
    )
    assert envelope.data.daily[1].coverage_complete is False
    assert envelope.data.daily[1].covered_fraction == 0.25
    assert envelope.data.daily[1].missing_reason == "INSUFFICIENT_COVERAGE"
    assert envelope.data.daily[1].daily_mean_temperature_c is None
    assert envelope.data.daily[1].daily_mean_hdd is None
    assert envelope.data.daily[1].daily_mean_cdd is None
    assert envelope.data.daily[1].time_integral_heating_degree_day is None
    assert envelope.data.daily[1].time_integral_cooling_degree_day is None
    assert envelope.meta.caller_weights is True
    assert envelope.meta.left_hold_warnings == ["LEFT_HOLD_APPROXIMATION"]
    assert "RESEARCH_ONLY" in envelope.meta.warnings
    assert envelope.meta.model_extra == {"vendor_trace": {"cursor": "abc"}}

    dumped = envelope.model_dump(mode="json")
    assert (
        dumped["data"]["feature_policy"]["location_weights"][0]["weight"] == "0.6"
    )
    assert dumped["data"]["daily"][0]["locations"][0]["weight"] == "0.6"


def test_mocked_http_parses_not_ready_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_post(url: str, *, json: dict, timeout: float) -> _FakeResponse:
        return _FakeResponse(_not_ready_payload())

    monkeypatch.setattr(sdk._http, "post", fake_post)

    envelope = sdk.compute_weather_degree_days("http://backend", _request())

    assert envelope.status == "NOT_READY"
    assert envelope.data.status == "NOT_READY"
    assert envelope.data.daily == []
    assert envelope.diagnostics[0].code == "NO_ELIGIBLE_FORECAST"
    assert envelope.diagnostics[0].location_id == "loc-1"
    assert envelope.meta.status == "NOT_READY"
    assert "FORECAST_INPUT_NOT_READY" in envelope.meta.warnings


def test_http_errors_propagate(monkeypatch: pytest.MonkeyPatch) -> None:
    request = httpx.Request("POST", "http://backend/api/weather/degree-days")
    error = httpx.HTTPStatusError(
        "refused", request=request, response=httpx.Response(422)
    )

    def fake_post(url: str, *, json: dict, timeout: float) -> _FakeResponse:
        return _FakeResponse(error=error)

    monkeypatch.setattr(sdk._http, "post", fake_post)

    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        sdk.compute_weather_degree_days("http://backend", _request())

    assert exc_info.value is error
