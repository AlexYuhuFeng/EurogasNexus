"""Read-only /api/v1/weather routes (synthetic fixtures only)."""

from fastapi import APIRouter, Request

router = APIRouter(tags=["weather"])


def _env(data: object, _request: Request) -> dict:
    return {"data": data, "meta": {"research_only": True, "human_review_required": True,
            "source_references": ["synthetic-fixture"], "warnings": ["Synthetic data only."]}}


@router.get("/api/v1/weather/stations")
def list_stations(request: Request) -> dict:
    return _env([
        {"station_id": "ws-ams", "name": "Amsterdam", "country": "NL", "lat": 52.37, "lon": 4.90},
        {"station_id": "ws-lon", "name": "London", "country": "GB", "lat": 51.51, "lon": -0.13},
        {"station_id": "ws-ber", "name": "Berlin", "country": "DE", "lat": 52.52, "lon": 13.41},
        {"station_id": "ws-par", "name": "Paris", "country": "FR", "lat": 48.86, "lon": 2.35},
    ], request)


@router.get("/api/v1/weather/observations")
def list_observations(request: Request) -> dict:
    return _env([
        {"observation_id": "wth-001", "station_id": "ws-ams", "station_name": "Amsterdam",
         "temperature_c": 14.5, "period_start_utc": "2026-05-29T00:00:00Z",
         "period_end_utc": "2026-05-30T00:00:00Z"},
        {"observation_id": "wth-002", "station_id": "ws-lon", "station_name": "London",
         "temperature_c": 13.2, "period_start_utc": "2026-05-29T00:00:00Z",
         "period_end_utc": "2026-05-30T00:00:00Z"},
    ], request)


@router.get("/api/v1/weather/hdd-cdd")
def list_hdd_cdd(request: Request) -> dict:
    return _env([
        {"metric_id": "hdd-001", "station_id": "ws-ams", "station_name": "Amsterdam",
         "metric_type": "HDD", "base_temperature_c": 15.5, "value": 1.0,
         "period_start_utc": "2026-05-29T00:00:00Z", "period_end_utc": "2026-05-30T00:00:00Z"},
        {"metric_id": "cdd-001", "station_id": "ws-lon", "station_name": "London",
         "metric_type": "CDD", "base_temperature_c": 18.0, "value": 0.0,
         "period_start_utc": "2026-05-29T00:00:00Z", "period_end_utc": "2026-05-30T00:00:00Z"},
    ], request)
