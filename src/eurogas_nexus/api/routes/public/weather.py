"""Read-only /api/weather routes.

Weather is a V1 data-source integration surface. The API must not invent
weather/HDD/CDD values when no runtime source has been ingested.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["weather"])


@router.get("/api/weather/stations")
def list_stations(request: Request) -> dict:
    return _env([], request)


@router.get("/api/weather/observations")
def list_observations(request: Request) -> dict:
    return _env([], request)


@router.get("/api/weather/hdd-cdd")
def list_hdd_cdd(request: Request) -> dict:
    return _env([], request)


def _env(data: object, _request: Request) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["runtime-db-not-configured"],
            "warnings": ["WEATHER_SOURCE_NOT_CONFIGURED"],
        },
    }
