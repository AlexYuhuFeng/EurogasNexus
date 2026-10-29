"""Tests for the SDK ECMWF forecast fetch helper."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import httpx
import pytest
from eurogas_nexus_sdk import weather_forecasts
from eurogas_nexus_sdk.weather_forecasts import (
    ForecastReadEnvelope,
    fetch_weather_forecasts,
)
from pydantic import ValidationError

_URL = "https://api.example.test/api/weather/forecasts"


class _Response:
    """Minimal httpx.Response stand-in that prefers strict JSON bytes."""

    def __init__(
        self,
        content: bytes,
        *,
        error: httpx.HTTPStatusError | None = None,
    ) -> None:
        self.content = content
        self._error = error

    def raise_for_status(self) -> None:
        if self._error is not None:
            raise self._error

    def json(self) -> object:
        raise AssertionError("fetch must parse response.content, not response.json()")


def _payload() -> dict[str, Any]:
    return {
        "data": [
            {
                "observation_id": "obs-1",
                "point_id": "point-1",
                "series_id": "series-1",
                "entity_id": "entity-1",
                "source_system": "ECMWF_OPEN_DATA",
                "provider": "ECMWF",
                "model": "IFS",
                "run_id": "run-1",
                "issued_at_utc": "2026-01-01T00:00:00Z",
                "valid_at_utc": "2026-01-01T01:00:00Z",
                "available_at_utc": "2026-01-01T00:00:00Z",
                "temperature_c": 5.5,
                "unit": "degC",
                "raw_grib_sha256": "a" * 64,
                "record_content_sha256": "b" * 64,
                "requested_latitude": 50.0,
                "requested_longitude": 8.0,
                "grid_latitude": 50.1,
                "grid_longitude": 8.1,
            }
        ],
        "meta": {
            "research_only": True,
            "source_references": ["ECMWF_OPEN_DATA"],
            "warnings": ["RESEARCH_ONLY", "HUMAN_REVIEW_REQUIRED"],
            "attribution": "ECMWF Open Data (CC BY 4.0)",
            "point_kind": "FORECAST_GRID_POINT",
        },
    }


def _valid_kwargs() -> dict[str, Any]:
    return {
        "series_ids": ["series-1", "series-2"],
        "entity_ids": ["entity-1"],
        "prediction_origin": datetime(2026, 1, 1, tzinfo=UTC),
        "valid_from": datetime(2026, 1, 1, 1, tzinfo=UTC),
        "valid_to": datetime(2026, 1, 2, 1, tzinfo=UTC),
        "limit": 25,
    }


def _json_response() -> _Response:
    return _Response(json.dumps(_payload()).encode("utf-8"))


def test_fetch_sends_expected_query_and_returns_typed_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_get(url: str, **kwargs: Any) -> _Response:
        calls.append((url, kwargs))
        return _json_response()

    monkeypatch.setattr(weather_forecasts._http, "get", fake_get)

    envelope = fetch_weather_forecasts("https://api.example.test", **_valid_kwargs())

    assert isinstance(envelope, ForecastReadEnvelope)
    assert envelope.meta.research_only is True
    assert envelope.meta.source_references == ("ECMWF_OPEN_DATA",)
    assert envelope.meta.warnings == ("RESEARCH_ONLY", "HUMAN_REVIEW_REQUIRED")
    assert envelope.meta.attribution == "ECMWF Open Data (CC BY 4.0)"
    assert envelope.meta.point_kind == "FORECAST_GRID_POINT"
    assert len(envelope.data) == 1
    assert envelope.data[0].observation_id == "obs-1"
    assert envelope.data[0].temperature_c == 5.5
    assert envelope.data[0].issued_at_utc == datetime(2026, 1, 1, tzinfo=UTC)

    assert len(calls) == 1
    url, kwargs = calls[0]
    assert url == _URL
    assert kwargs["timeout"] == 10
    assert kwargs["params"] == {
        "series_ids": ["series-1", "series-2"],
        "entity_ids": ["entity-1"],
        "prediction_origin": "2026-01-01T00:00:00+00:00",
        "valid_from": "2026-01-01T01:00:00+00:00",
        "valid_to": "2026-01-02T01:00:00+00:00",
        "limit": 25,
    }


def test_fetch_normalizes_aware_times_and_whitespace_in_identifiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_get(url: str, **kwargs: Any) -> _Response:
        captured.update(kwargs["params"])
        return _json_response()

    monkeypatch.setattr(weather_forecasts._http, "get", fake_get)

    kwargs = _valid_kwargs()
    kwargs["series_ids"] = [" series-1 "]
    kwargs["prediction_origin"] = datetime(
        2026, 1, 1, 2, tzinfo=timezone(timedelta(hours=2))
    )

    fetch_weather_forecasts("https://api.example.test", **kwargs)

    assert captured["series_ids"] == ["series-1"]
    assert captured["prediction_origin"] == "2026-01-01T00:00:00+00:00"


@pytest.mark.parametrize("limit", [1, 256])
def test_fetch_accepts_limit_and_32_day_window_boundaries(
    monkeypatch: pytest.MonkeyPatch,
    limit: int,
) -> None:
    def fake_get(url: str, **kwargs: Any) -> _Response:
        return _json_response()

    monkeypatch.setattr(weather_forecasts._http, "get", fake_get)

    kwargs = _valid_kwargs()
    kwargs["limit"] = limit
    kwargs["valid_to"] = kwargs["valid_from"] + timedelta(days=32)

    assert isinstance(
        fetch_weather_forecasts("https://api.example.test", **kwargs),
        ForecastReadEnvelope,
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"series_ids": []},
        {"series_ids": "series-1"},
        {"series_ids": [""]},
        {"series_ids": ["series-1"] * 257},
        {"series_ids": [1]},
        {"entity_ids": []},
        {"entity_ids": ["entity-1"] * 257},
        {"prediction_origin": datetime(2026, 1, 1)},
        {"valid_from": datetime(2026, 1, 1, 1)},
        {"valid_to": datetime(2026, 1, 1, 1, tzinfo=UTC)},
        {"valid_to": datetime(2026, 2, 2, 1, 0, 1, tzinfo=UTC)},
        {"limit": 0},
        {"limit": 257},
        {"limit": True},
        {"limit": 1.5},
        {"limit": "10"},
    ],
)
def test_invalid_inputs_are_rejected_before_http(
    monkeypatch: pytest.MonkeyPatch,
    overrides: dict[str, Any],
) -> None:
    called = False

    def unexpected_get(url: str, **kwargs: Any) -> _Response:
        nonlocal called
        called = True
        raise AssertionError("invalid SDK input must not perform HTTP")

    monkeypatch.setattr(weather_forecasts._http, "get", unexpected_get)

    kwargs = _valid_kwargs()
    kwargs.update(overrides)

    with pytest.raises(ValueError):
        fetch_weather_forecasts("https://api.example.test", **kwargs)

    assert called is False


def test_http_status_error_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    request = httpx.Request("GET", _URL)
    error = httpx.HTTPStatusError(
        "service unavailable",
        request=request,
        response=httpx.Response(503, request=request),
    )

    def fake_get(url: str, **kwargs: Any) -> _Response:
        return _Response(b"", error=error)

    monkeypatch.setattr(weather_forecasts._http, "get", fake_get)

    with pytest.raises(httpx.HTTPStatusError) as caught:
        fetch_weather_forecasts("https://api.example.test", **_valid_kwargs())

    assert caught.value is error


def test_strict_envelope_validation_errors_propagate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _payload()
    payload["data"][0]["valid_at_utc"] = "2026-01-01T01:00:00"

    def fake_get(url: str, **kwargs: Any) -> _Response:
        return _Response(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(weather_forecasts._http, "get", fake_get)

    with pytest.raises(ValidationError):
        fetch_weather_forecasts("https://api.example.test", **_valid_kwargs())
