"""Read-only /api/physical routes."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request

from eurogas_nexus.api.dependencies.row_entitlement import (
    filter_rows,
    require_derived_access,
)
from eurogas_nexus.application.physical_native_rates import (
    NativeRateProjectionError,
    project_native_rate_row,
    row_volume_admissible,
)

router = APIRouter(tags=["physical"])

QuantityBasis = Literal["volume", "native"]

LEGACY_ENTSOG_EXCLUDED_WARNING = (
    "Legacy ENTSOG rows with an unverified assumed volume are excluded; their "
    "absence does not mean the source reported no flow or zero volume."
)
_NATIVE_RATE_INVALID_CODE = "native_rate_invalid"
_NATIVE_QUERY_OVERFLOW_CODE = "native_query_overflow"
_MAX_POINT_ID_LENGTH = 128


@router.get("/api/physical/flows")
def list_flows(
    request: Request,
    quantity_basis: QuantityBasis = Query("volume"),
    limit: int = Query(200, ge=1, le=2000),
    point_id: str | None = Query(None, min_length=1, max_length=_MAX_POINT_ID_LENGTH),
) -> dict:
    """List physical flow observations from the runtime DB.

    返回物理流量观测列表；默认只返回可证明的体积值，原生模式只返回严格校验的
    ENTSOG 原生速率。DB 未配置时降级为空数据并告警（fail-closed）。

    Args:
        request: Incoming FastAPI request (identity/entitlement wiring).
        quantity_basis: ``volume`` for admitted legacy/non-ENTSOG volumes, or
            ``native`` for strict ENTSOG native-rate projections.
        limit: Maximum authorized native rows to return (1..2000); volume mode
            returns all admitted rows.
        point_id: Optional exact point filter.

    Returns:
        Enveloped flow rows, or an empty enveloped response with a warning.

    Raises:
        HTTPException: 400 ``native_query_overflow`` when a native query exceeds
            the requested limit, 403 on denied derived access, 503
            ``runtime_db_unavailable`` on DB read failure, or 503
            ``native_rate_invalid`` on an invalid stored native payload.
    """

    require_derived_access(
        request,
        ("ENTSOG",),
        resource="physical_flow_observations",
    )

    loaded = _load_flow_observations(
        request=request,
        quantity_basis=quantity_basis,
        limit=limit,
        point_id=point_id,
    )
    if loaded is not None:
        flows, warnings = loaded
        if quantity_basis == "native" and len(flows) > limit:
            raise _native_query_overflow()
        return _env(flows, source="runtime-postgresql", warnings=warnings)

    return _env(
        [],
        source="runtime-db-not-configured",
        warnings=["Runtime DB is not configured; ENTSOG flow observations are unavailable."],
    )


@router.get("/api/physical/capacity")
def list_capacity(
    request: Request,
    quantity_basis: QuantityBasis = Query("volume"),
    limit: int = Query(200, ge=1, le=2000),
    point_id: str | None = Query(None, min_length=1, max_length=_MAX_POINT_ID_LENGTH),
) -> dict:
    """List capacity observations from the runtime DB.

    返回容量观测列表；默认只返回可证明的体积值，原生模式只返回严格校验的
    ENTSOG 原生速率。DB 未配置时降级为空数据并告警（fail-closed）。

    Args:
        request: Incoming FastAPI request (identity/entitlement wiring).
        quantity_basis: ``volume`` for admitted legacy/non-ENTSOG volumes, or
            ``native`` for strict ENTSOG native-rate projections.
        limit: Maximum authorized native rows to return (1..2000); volume mode
            returns all admitted rows.
        point_id: Optional exact point filter.

    Returns:
        Enveloped capacity rows, or an empty enveloped response with a warning.

    Raises:
        HTTPException: 400 ``native_query_overflow`` when a native query exceeds
            the requested limit, 403 on denied derived access, 503
            ``runtime_db_unavailable`` on DB read failure, or 503
            ``native_rate_invalid`` on an invalid stored native payload.
    """

    require_derived_access(
        request,
        ("ENTSOG",),
        resource="physical_capacity_observations",
    )

    loaded = _load_capacity_observations(
        request=request,
        quantity_basis=quantity_basis,
        limit=limit,
        point_id=point_id,
    )
    if loaded is not None:
        capacity, warnings = loaded
        if quantity_basis == "native" and len(capacity) > limit:
            raise _native_query_overflow()
        return _env(capacity, source="runtime-postgresql", warnings=warnings)

    return _env(
        [],
        source="runtime-db-not-configured",
        warnings=["Runtime DB is not configured; ENTSOG capacity observations are unavailable."],
    )


@router.get("/api/physical/outages")
def list_outages(request: Request) -> dict:
    """List outage records (requires source ingestion; no fallback data).

    故障（outage）端点依赖来源采集；未配置时不返回任何回退数据。
    """

    return _env(
        [],
        source="runtime-db-not-configured",
        warnings=["Outage endpoint requires source ingestion; no fallback data returned."],
    )


def _db_flow_observations(
    *,
    quantity_basis: QuantityBasis = "volume",
    limit: int = 200,
    point_id: str | None = None,
) -> list[dict] | None:
    """Legacy-compatible helper returning admitted rows without response metadata."""

    loaded = _load_flow_observations(
        quantity_basis=quantity_basis,
        limit=limit,
        point_id=point_id,
    )
    if loaded is None:
        return None
    rows, _warnings = loaded
    return rows


def _db_capacity_observations(
    *,
    quantity_basis: QuantityBasis = "volume",
    limit: int = 200,
    point_id: str | None = None,
) -> list[dict] | None:
    """Legacy-compatible helper returning admitted rows without response metadata."""

    loaded = _load_capacity_observations(
        quantity_basis=quantity_basis,
        limit=limit,
        point_id=point_id,
    )
    if loaded is None:
        return None
    rows, _warnings = loaded
    return rows


def _filter_raw_rows(raw_rows, *, request: Request | None):
    if request is None:
        return raw_rows
    wrapped = [
        {"source_system": getattr(row, "source_system", None), "record": row}
        for row in raw_rows
    ]
    return [entry["record"] for entry in filter_rows(request, wrapped)]


def _load_flow_observations(
    *,
    quantity_basis: QuantityBasis = "volume",
    limit: int = 200,
    point_id: str | None = None,
    request: Request | None = None,
) -> tuple[list[dict], list[str]] | None:
    if not _db_is_configured():
        return None

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from sqlalchemy import func, or_

        from eurogas_nexus.db.models import FlowObservationRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            query = session.query(FlowObservationRecord)
            if point_id:
                query = query.filter(FlowObservationRecord.point_id == point_id)
            if quantity_basis == "native":
                query = query.filter(
                    func.upper(func.trim(FlowObservationRecord.source_system)) == "ENTSOG",
                    or_(
                        FlowObservationRecord.normalizer_version.is_not(None),
                        FlowObservationRecord.native_rate_json.is_not(None),
                    ),
                )
                query = query.order_by(
                    FlowObservationRecord.observed_at_utc.desc(),
                    FlowObservationRecord.observation_id.asc(),
                )
                raw_rows = query.limit(limit + 1).all()
            else:
                query = query.order_by(
                    FlowObservationRecord.point_name.asc(),
                    FlowObservationRecord.direction.asc(),
                    FlowObservationRecord.observed_at_utc.desc(),
                    FlowObservationRecord.observation_id.asc(),
                )
                raw_rows = query.all()
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc

    return _project_rows(
        _filter_raw_rows(raw_rows, request=request),
        quantity_basis=quantity_basis,
        volume_field="flow_mcm_d",
    )


def _load_capacity_observations(
    *,
    quantity_basis: QuantityBasis = "volume",
    limit: int = 200,
    point_id: str | None = None,
    request: Request | None = None,
) -> tuple[list[dict], list[str]] | None:
    if not _db_is_configured():
        return None

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from sqlalchemy import func, or_

        from eurogas_nexus.db.models import CapacityObservationRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            query = session.query(CapacityObservationRecord)
            if point_id:
                query = query.filter(CapacityObservationRecord.point_id == point_id)
            if quantity_basis == "native":
                query = query.filter(
                    func.upper(func.trim(CapacityObservationRecord.source_system)) == "ENTSOG",
                    or_(
                        CapacityObservationRecord.normalizer_version.is_not(None),
                        CapacityObservationRecord.native_rate_json.is_not(None),
                    ),
                )
                query = query.order_by(
                    CapacityObservationRecord.observed_at_utc.desc(),
                    CapacityObservationRecord.observation_id.asc(),
                )
                raw_rows = query.limit(limit + 1).all()
            else:
                query = query.order_by(
                    CapacityObservationRecord.point_name.asc(),
                    CapacityObservationRecord.direction.asc(),
                    CapacityObservationRecord.capacity_type.asc(),
                    CapacityObservationRecord.observed_at_utc.desc(),
                    CapacityObservationRecord.observation_id.asc(),
                )
                raw_rows = query.all()
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc

    return _project_rows(
        _filter_raw_rows(raw_rows, request=request),
        quantity_basis=quantity_basis,
        volume_field="capacity_mcm_d",
    )


def _project_rows(
    raw_rows,
    *,
    quantity_basis: QuantityBasis,
    volume_field: str,
) -> tuple[list[dict], list[str]]:
    rows: list[dict] = []
    legacy_entsog_withheld = False

    for row in raw_rows:
        if quantity_basis == "native":
            try:
                rows.append(project_native_rate_row(row, volume_field=volume_field))
            except NativeRateProjectionError as exc:
                raise _native_rate_unavailable() from exc
            continue

        try:
            admissible = row_volume_admissible(row, volume_field=volume_field)
        except NativeRateProjectionError as exc:
            raise _native_rate_unavailable() from exc
        if admissible:
            rows.append(
                _flow_row(row) if volume_field == "flow_mcm_d" else _capacity_row(row)
            )
        elif _is_legacy_entsog(row):
            legacy_entsog_withheld = True

    warnings = [LEGACY_ENTSOG_EXCLUDED_WARNING] if legacy_entsog_withheld else []
    return rows, warnings


def _is_legacy_entsog(row) -> bool:
    source = getattr(row, "source_system", None)
    return (
        isinstance(source, str)
        and source.strip().casefold() == "entsog"
        and getattr(row, "normalizer_version", None) is None
        and getattr(row, "native_rate_json", None) is None
    )


def _flow_row(row) -> dict:
    return {
        "observation_id": row.observation_id,
        "point_id": row.point_id,
        "point_name": row.point_name,
        "direction": row.direction,
        "flow_mcm_d": row.flow_mcm_d,
        "period_start_utc": row.period_start_utc.isoformat(),
        "period_end_utc": row.period_end_utc.isoformat(),
        "observed_at_utc": row.observed_at_utc.isoformat(),
        "source_system": row.source_system,
        "source_reference": row.source_reference,
        "freshness": row.freshness,
        "research_only": row.research_only,
    }


def _capacity_row(row) -> dict:
    return {
        "observation_id": row.observation_id,
        "point_id": row.point_id,
        "point_name": row.point_name,
        "direction": row.direction,
        "capacity_type": row.capacity_type,
        "capacity_mcm_d": row.capacity_mcm_d,
        "original_value": row.original_value,
        "original_unit": row.original_unit,
        "period_start_utc": row.period_start_utc.isoformat(),
        "period_end_utc": row.period_end_utc.isoformat(),
        "observed_at_utc": row.observed_at_utc.isoformat(),
        "source_system": row.source_system,
        "source_reference": row.source_reference,
        "freshness": row.freshness,
        "research_only": row.research_only,
    }


def _db_is_configured() -> bool:
    from eurogas_nexus.db.session import resolve_database_url

    return resolve_database_url() is not None


def _sqlalchemy_error_type():
    from sqlalchemy.exc import SQLAlchemyError

    return SQLAlchemyError


def _db_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "code": "runtime_db_unavailable",
            "message": "Runtime database is configured but unavailable for physical flow reads.",
            "error_class": exc.__class__.__name__,
        },
    )


def _native_rate_unavailable() -> HTTPException:
    """Typed refusal with a fixed code and no stored value or exception text."""

    return HTTPException(
        status_code=503,
        detail={
            "code": _NATIVE_RATE_INVALID_CODE,
            "message": "Stored native rate data failed strict validation and was not returned.",
        },
    )


def _native_query_overflow() -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "code": _NATIVE_QUERY_OVERFLOW_CODE,
            "message": "Native quantity query exceeds the requested limit; narrow the query.",
        },
    )


def _env(data: object, *, source: str, warnings: list[str] | None = None) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": [source],
            "warnings": warnings or [],
        },
    }
