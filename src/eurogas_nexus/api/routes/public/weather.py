"""Read-only /api/weather routes.

Weather is a V1 data-source integration surface. The API must not invent
weather/HDD/CDD values when no runtime source has been ingested.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(tags=["weather"])


@router.get("/api/weather/stations")
def list_stations(request: Request) -> dict:
    """List weather stations (empty until a runtime source is ingested)."""

    return _env([], request)


@router.get("/api/weather/observations")
def list_observations(request: Request) -> dict:
    """List weather observations (empty until a runtime source is ingested)."""

    return _env([], request)


@router.get("/api/weather/hdd-cdd")
def list_hdd_cdd(request: Request) -> dict:
    """List HDD/CDD series (empty until a runtime source is ingested)."""

    return _env([], request)


def _env(data: object, _request: Request) -> dict:
    """Envelope with research-only markers and a source-not-configured warning.

    无运行时来源时返回空数据 + WEATHER_SOURCE_NOT_CONFIGURED 告警：
    绝不编造天气/HDD/CDD 数值（fail-closed）。
    """

    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["runtime-db-not-configured"],
            "warnings": ["WEATHER_SOURCE_NOT_CONFIGURED"],
        },
    }
