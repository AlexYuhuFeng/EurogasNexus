"""DB-first /api/contracts routes for capacity and route context."""

from fastapi import APIRouter, HTTPException, Request

router = APIRouter(tags=["contracts"])


@router.get("/api/contracts/capacity")
def list_capacity_contracts(request: Request) -> dict:
    """List capacity profile contracts from the runtime DB.

    返回容量档案契约列表（按生效时间倒序）；DB 未配置或不可用时
    降级为空数据并告警，绝不返回编造的容量。

    Args:
        request: Incoming FastAPI request (envelope context).

    Returns:
        Enveloped capacity rows with ``runtime-postgresql`` source tag,
        or an empty enveloped response with a warning.

    Raises:
        HTTPException: 503 ``runtime_db_unavailable`` when the DB is
            configured but the read fails.
    """

    if not _db_is_configured():
        return _env(
            [],
            request,
            source="runtime-db-not-configured",
            warnings=["Runtime DB is required for capacity profile context."],
        )

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.db.models import CapacityProfileRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = (
                session.query(CapacityProfileRecord)
                .order_by(CapacityProfileRecord.valid_from_utc.desc())
                .all()
            )
            data = [
                {
                    "contract_id": row.contract_id,
                    "route_name": row.point_name,
                    "from_node_id": row.point_name,
                    "to_node_id": row.point_name,
                    "capacity_boe_d": row.capacity_mwh_per_day,
                    "unit": "MWh/d",
                    "start_utc": row.valid_from_utc.isoformat(),
                    "end_utc": row.valid_to_utc.isoformat(),
                    "status": row.firmness,
                    "source_reference": row.source_reference,
                }
                for row in rows
            ]
            warnings = [] if data else ["No capacity profiles are stored in the runtime DB."]
            return _env(data, request, source="runtime-postgresql", warnings=warnings)
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


@router.get("/api/contracts/routes")
def list_route_eligibility(request: Request) -> dict:
    """List route eligibility context (no generated routes are returned).

    返回路线资格上下文：路由发现必须由源拓扑/TSO 准入/容量/费率推导，
    本端点不生成路线，未配置 DB 时降级为空并告警。

    Args:
        request: Incoming FastAPI request (envelope context).

    Returns:
        Enveloped empty list with a derivation warning.
    """

    if not _db_is_configured():
        return _env(
            [],
            request,
            source="runtime-db-not-configured",
            warnings=["Runtime DB is required for route eligibility context."],
        )

    return _env(
        [],
        request,
        source="runtime-postgresql",
        warnings=[
            "Route discovery must be derived from source topology, TSO access, "
            "capacity profiles, and tariff rows; no generated routes are returned."
        ],
    )


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
            "message": "Runtime database is configured but unavailable for contract reads.",
            "error_class": exc.__class__.__name__,
        },
    )


def _env(
    data: object,
    _request: Request,
    *,
    source: str,
    warnings: list[str] | None = None,
) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": [source],
            "warnings": warnings or [],
        },
    }
