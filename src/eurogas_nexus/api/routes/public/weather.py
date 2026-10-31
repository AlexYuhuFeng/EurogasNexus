"""Read-only /api/weather routes.

Weather is a supported data-source integration surface. The API must not invent
weather/HDD/CDD values when no runtime source has been ingested.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder

from eurogas_nexus.api.dependencies.identity import require_identity_for_route
from eurogas_nexus.api.dependencies.row_entitlement import (
    filter_rows,
    require_derived_access,
)
from eurogas_nexus.api.schemas.weather_degree_days import WeatherDegreeDayRequest
from eurogas_nexus.api.schemas.weather_forecasts import (
    ForecastPointReading,
    ForecastReadEnvelope,
    ForecastReadMeta,
)
from eurogas_nexus.application.research.weather_demand_inputs import (
    LEFT_HOLD_INSTANT,
    ForecastPointBinding,
    WeatherDemandBridgeConfig,
    build_weather_demand_inputs,
    compute_degree_days_from_bundle,
    project_forecast_observation_record,
)
from eurogas_nexus.domain.ingestion.certification import certification_gate
from eurogas_nexus.domain.research.weather_demand import (
    DegreeDayFeaturePolicy,
    DegreeDayPolicy,
    RegionLocationWeight,
    WeatherDemandInputError,
)


def get_session_factory():
    """Resolve the DB session factory lazily so API import stays DB-free."""

    from eurogas_nexus.db.session import get_session_factory as _get_session_factory

    return _get_session_factory()


router = APIRouter(tags=["weather"])

_SOURCE = "ECMWF_OPEN_DATA"
_ATTRIBUTION = "ECMWF Open Data (CC BY 4.0)"
_DEFAULT_LIMIT = 100
_MAX_LIMIT = 256
_DEGREE_DAY_MAX_ROWS = 256
_DEGREE_DAY_MAX_POINTS = 64


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


@router.get("/api/weather/forecasts", response_model=ForecastReadEnvelope)
def list_forecasts(
    request: Request,
    series_ids: Annotated[list[str] | None, Query()] = None,
    entity_ids: Annotated[list[str] | None, Query()] = None,
    prediction_origin: Annotated[str | None, Query()] = None,
    valid_from: Annotated[str | None, Query()] = None,
    valid_to: Annotated[str | None, Query()] = None,
    limit: Annotated[str | None, Query()] = None,
    _identity: None = Depends(require_identity_for_route),
) -> ForecastReadEnvelope:
    """Read bounded ECMWF forecast points for explicitly authorized entities."""

    series, entities, origin, start, end, bounded_limit = _forecast_query(
        series_ids, entity_ids, prediction_origin, valid_from, valid_to, limit
    )
    require_derived_access(request, (_SOURCE,), resource="weather_forecasts")

    from eurogas_nexus.db.repositories.ecmwf_forecast_reads import (
        EcmwfForecastReadOverflowError,
        EcmwfForecastReadValidationError,
        read_ecmwf_forecasts,
    )

    try:
        with get_session_factory()() as session:
            _require_certification(session)
            rows = read_ecmwf_forecasts(
                session, series, entities, origin, start, end, bounded_limit
            )
    except (EcmwfForecastReadValidationError, EcmwfForecastReadOverflowError) as exc:
        raise _error(400, "invalid_forecast_query", "Forecast query is out of bounds.") from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise _error(503, "forecast_store_unavailable", "Forecast storage is unavailable.") from exc

    try:
        data = _visible_rows(request, rows)
    except Exception as exc:
        raise _error(503, "forecast_data_malformed", "Stored forecast data is malformed.") from exc

    meta = ForecastReadMeta(
        source_references=(_SOURCE,),
        warnings=("RESEARCH_ONLY", "HUMAN_REVIEW_REQUIRED"),
        attribution=_ATTRIBUTION,
    )
    return ForecastReadEnvelope(data=data, meta=meta)


@router.post("/api/weather/degree-days")
def compute_weather_degree_days(
    payload: WeatherDegreeDayRequest,
    request: Request,
    _identity: None = Depends(require_identity_for_route),
) -> dict:
    """Compute bounded, caller-weighted degree days from persisted forecasts."""

    require_derived_access(request, (_SOURCE,), resource="weather_degree_days")
    from eurogas_nexus.db.repositories.ecmwf_forecast_reads import (
        EcmwfForecastReadOverflowError,
        EcmwfForecastReadValidationError,
        read_ecmwf_forecasts,
    )

    try:
        policy, config, bindings = _degree_day_inputs(payload)
        with get_session_factory()() as session:
            _require_certification(session)
            rows = read_ecmwf_forecasts(
                session,
                tuple(dict.fromkeys(b.series_id for b in bindings)),
                tuple(dict.fromkeys(b.entity_id for b in bindings)),
                payload.prediction_origin,
                config.window_start_utc - timedelta(minutes=payload.max_hold_minutes),
                config.window_end_utc + timedelta(minutes=payload.max_hold_minutes),
                _DEGREE_DAY_MAX_ROWS,
            )
    except WeatherDemandInputError as exc:
        raise _error(422, "invalid_degree_day_inputs", str(exc)) from exc
    except EcmwfForecastReadOverflowError as exc:
        raise _error(400, "forecast_query_overflow", "Degree-day input exceeds 256 rows.") from exc
    except EcmwfForecastReadValidationError as exc:
        raise _error(400, "invalid_degree_day_query", str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        raise _error(503, "forecast_store_unavailable", "Forecast storage is unavailable.") from exc

    try:
        visible = filter_rows(
            request,
            ({"source_system": row.source_system, "record": row} for row in rows),
            source_key="source_system",
        )
        projected = tuple(project_forecast_observation_record(item["record"]) for item in visible)
        bundle = build_weather_demand_inputs(projected, bindings, config)
        result = compute_degree_days_from_bundle(bundle, policy)
    except WeatherDemandInputError as exc:
        raise _error(422, "invalid_degree_day_inputs", str(exc)) from exc
    except Exception as exc:
        raise _error(503, "forecast_data_malformed", "Stored forecast data is malformed.") from exc

    if result is None:
        data = {
            "status": "NOT_READY",
            "diagnostics": jsonable_encoder(
                [asdict(diagnostic) for diagnostic in bundle.diagnostics]
            ),
        }
    else:
        data = jsonable_encoder(asdict(result), custom_encoder={Decimal: str})
    return {
        "data": data,
        "meta": _degree_day_meta(config, bundle, ready=result is not None),
    }


def _degree_day_inputs(payload: WeatherDegreeDayRequest):
    bindings = tuple(
        ForecastPointBinding(**binding.model_dump(exclude={"weight"}))
        for binding in payload.point_bindings
    )
    feature_policy = DegreeDayFeaturePolicy(
        region=payload.region,
        heating_base_c=payload.heating_base_c,
        cooling_base_c=payload.cooling_base_c,
        max_gap_minutes=payload.max_hold_minutes,
        min_covered_fraction=payload.min_covered_fraction,
        location_weights=tuple(
            RegionLocationWeight(location_id=item.location_id, weight=item.weight)
            for item in payload.point_bindings
        ),
        gas_day_calendar=payload.gas_day_calendar,
        temporal_method=LEFT_HOLD_INSTANT,
    )
    policy = DegreeDayPolicy(
        heating_base_c=feature_policy.heating_base_c,
        cooling_base_c=feature_policy.cooling_base_c,
        max_gap_minutes=feature_policy.max_gap_minutes,
        min_covered_fraction=feature_policy.min_covered_fraction,
    )
    config = WeatherDemandBridgeConfig(
        feature_policy=feature_policy,
        prediction_origin=payload.prediction_origin,
        gas_days=tuple(payload.gas_days),
        max_hold_minutes=payload.max_hold_minutes,
        max_rows=_DEGREE_DAY_MAX_ROWS,
        max_points=_DEGREE_DAY_MAX_POINTS,
    )
    return policy, config, bindings


def _degree_day_meta(config, bundle, *, ready: bool) -> dict:
    warnings = [
        "CALLER_DEFINED_REGION_WEIGHTS",
        "LEFT_HOLD_APPROXIMATION",
        "MISSING_COVERAGE_NULL",
        "RESEARCH_ONLY",
        "HUMAN_REVIEW_REQUIRED",
    ]
    if not ready:
        warnings.append("FORECAST_INPUT_NOT_READY")
    vintage = bundle.selected_vintage
    return jsonable_encoder(
        {
            "research_only": True,
            "human_review_required": True,
            "status": "READY" if ready else "NOT_READY",
            "attribution": _ATTRIBUTION,
            "source_references": sorted({_SOURCE, *bundle.source_refs}),
            "feature_policy_hash": config.feature_policy.policy_hash,
            "prediction_origin": bundle.prediction_origin,
            "gas_days": [day.isoformat() for day in bundle.gas_days],
            "max_hold_minutes": bundle.max_hold_minutes,
            "query_limit": _DEGREE_DAY_MAX_ROWS,
            "selected_forecast_vintage": asdict(vintage) if vintage else None,
            "warnings": warnings,
        }
    )


def _forecast_query(
    series_ids: list[str] | None,
    entity_ids: list[str] | None,
    prediction_origin: str | None,
    valid_from: str | None,
    valid_to: str | None,
    limit: str | None,
) -> tuple[tuple[str, ...], tuple[str, ...], datetime, datetime, datetime, int]:
    series = _identifiers(series_ids, "series_ids")
    entities = _identifiers(entity_ids, "entity_ids")
    origin = _utc(prediction_origin, "prediction_origin")
    start = _utc(valid_from, "valid_from")
    end = _utc(valid_to, "valid_to")
    if end <= start:
        raise _error(400, "invalid_forecast_query", "valid_to must follow valid_from.")
    try:
        bounded_limit = _DEFAULT_LIMIT if limit is None else int(limit)
    except (TypeError, ValueError) as exc:
        raise _error(400, "invalid_forecast_query", "limit must be an integer.") from exc
    if not 1 <= bounded_limit <= _MAX_LIMIT:
        raise _error(400, "invalid_forecast_query", "limit must be between 1 and 256.")
    return series, entities, origin, start, end, bounded_limit


def _identifiers(values: list[str] | None, name: str) -> tuple[str, ...]:
    items = tuple(value.strip() for value in (values or ()))
    if not items or any(not value for value in items):
        raise _error(400, "invalid_forecast_query", f"{name} must be non-empty.")
    return items


def _utc(value: str | None, name: str) -> datetime:
    if not value or not value.strip():
        raise _error(400, "invalid_forecast_query", f"{name} is required.")
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise _error(400, "invalid_forecast_query", f"{name} must be an ISO datetime.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise _error(400, "invalid_forecast_query", f"{name} must include a UTC offset.")
    return parsed.astimezone(UTC)


def _require_certification(session) -> None:
    from sqlalchemy import select

    from eurogas_nexus.db.models.certification import ProviderCertificationRecord

    certification = session.scalar(
        select(ProviderCertificationRecord)
        .where(ProviderCertificationRecord.source_system == _SOURCE)
        .order_by(ProviderCertificationRecord.evaluated_at_utc.desc())
        .limit(1)
    )
    if certification is None:
        raise _error(503, "forecast_source_unavailable", "Forecast source unavailable.")
    expires = certification.expires_at_utc
    if expires is not None:
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=UTC)
        if expires <= datetime.now(UTC):
            raise _error(503, "forecast_source_unavailable", "Certification expired.")
    gate = certification_gate(
        certification.source_system,
        stage=certification.stage,
        checks=certification.checks,
    )
    if not gate.allows_live:
        raise _error(503, "forecast_source_unavailable", "Forecast source uncertified.")


def _visible_rows(request: Request, rows) -> list[ForecastPointReading]:
    payloads = [{"source_system": row.source_system, "record": row} for row in rows]
    return [
        _forecast_reading(item["record"])
        for item in filter_rows(request, payloads, source_key="source_system")
    ]


def _forecast_reading(record) -> ForecastPointReading:
    projected = project_forecast_observation_record(record)
    point = (projected.provenance or {}).get("point") or {}
    return ForecastPointReading(
        observation_id=projected.forecast_observation_id,
        point_id=projected.point_id,
        series_id=projected.series_id,
        entity_id=projected.entity_id,
        source_system=projected.source_system,
        provider=projected.model_provider,
        model=projected.model,
        run_id=projected.run_id,
        issued_at_utc=projected.issued_at_utc,
        valid_at_utc=projected.valid_at_utc,
        available_at_utc=projected.available_at_utc,
        temperature_c=projected.temperature_c,
        unit=projected.unit,
        raw_grib_sha256=projected.raw_grib_sha256,
        record_content_sha256=projected.record_content_sha256,
        requested_latitude=_coordinate(point.get("requested_coordinates", {}), "latitude"),
        requested_longitude=_coordinate(point.get("requested_coordinates", {}), "longitude"),
        grid_latitude=_coordinate(point.get("nearest_grid_coordinates", {}), "latitude"),
        grid_longitude=_coordinate(point.get("nearest_grid_coordinates", {}), "longitude"),
    )


def _coordinate(point: dict, key: str) -> float:
    value = point.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("forecast coordinate is missing")
    return float(value)


def _error(status_code: int, error: str, message: str) -> HTTPException:
    detail = {"error": error, "message": message, "research_only": True}
    return HTTPException(status_code=status_code, detail=detail)
