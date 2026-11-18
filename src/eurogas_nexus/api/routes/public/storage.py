"""Read-only /api/storage routes."""

from datetime import date

from fastapi import APIRouter, HTTPException, Query, Request

from eurogas_nexus.api.routes.public import observation_window
from eurogas_nexus.domain.market.storage_targets import (
    DEFAULT_TARGET_PCT,
    StorageDay,
    StorageTrajectoryError,
    storage_trajectory,
)

router = APIRouter(tags=["storage"])


def _env(data: object, _request: Request) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["runtime-db-not-configured"],
            "warnings": ["Runtime DB is not configured; GIE AGSI data is unavailable."],
        },
    }


def _runtime_env(data: object) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["runtime-postgresql"],
            "warnings": [],
        },
    }


@router.get("/api/storage/sites")
def list_sites(request: Request) -> dict:
    """List storage sites aggregated from runtime observations.

    按 facility_id 聚合最新观测为储气库站点列表；DB 未配置时降级为空。

    Args:
        request: Incoming FastAPI request (unused except wiring).

    Returns:
        Enveloped site list or an empty enveloped response with a warning.

    Raises:
        HTTPException: 503 ``runtime_db_unavailable`` on DB read failure.
    """

    observations = _db_storage_observations()
    if observations is None:
        return _env([], request)
    from eurogas_nexus.api.dependencies.row_entitlement import filter_rows

    observations = filter_rows(request, observations)
    sites: dict[str, dict] = {}
    for row in observations:
        sites.setdefault(
            row["facility_id"],
            {
                "site_id": row["facility_id"],
                "name": row["facility_name"],
                "country": row["country"],
                "working_capacity_twh": row["working_capacity_twh"],
                "fill_pct": row["fill_pct"],
                "observed_at_utc": row["observed_at_utc"],
                "status": "observed",
                "source_system": row["source_system"],
            },
        )
    return _runtime_env(list(sites.values()))


@router.get("/api/storage/observations")
def list_observations(
    request: Request,
    days: int = Query(
        observation_window.DEFAULT_DAYS,
        ge=1,
        le=observation_window.MAX_DAYS,
        description=(
            "Gas days to return, back from the newest observation in the store. The window "
            "is stated in meta.window; nothing before it is implied absent."
        ),
    ),
) -> dict:
    """List storage observations from the runtime DB.

    Bounded to the newest ``days`` gas days in the store (default 45, stated in
    ``meta.window``; see ``observation_window``). A longer series asks for it with ``days``.

    返回储气库观测列表（按设施名 + 周期倒序）；DB 未配置时降级为空。

    Args:
        request: Incoming FastAPI request (unused except wiring).
        days: Gas days back from the newest observation (1..800).

    Returns:
        Enveloped observation rows or an empty enveloped response.

    Raises:
        HTTPException: 503 ``runtime_db_unavailable`` on DB read failure.
    """

    window: dict = {}
    observations = _db_storage_observations(days, window)
    if observations is not None:
        from eurogas_nexus.api.dependencies.row_entitlement import filter_rows

        envelope = _runtime_env(filter_rows(request, observations))
        envelope["meta"]["window"] = window
        return envelope

    return _env([], request)


@router.get("/api/storage/target-trajectory")
def target_trajectory(
    request: Request,
    code: str = Query(default="EU", min_length=2, max_length=16),
    target_pct: float = Query(default=DEFAULT_TARGET_PCT, gt=0, le=100),
    deviation_pp: float = Query(default=0.0, ge=0, lt=100),
    pace_days: int = Query(default=7, ge=1, le=60),
) -> dict:
    """Filling trajectory of one AGSI storage code against the EU storage target.

    返回指定 AGSI 代码（EU/国家）相对欧盟储气目标的库存差距、所需日均注入与
    近期注入速度；DB 未配置时降级为空并告警。

    Raises:
        HTTPException: 422 ``storage_series_unavailable`` when rows exist but cannot
            support a trajectory (no capacity); 503 ``runtime_db_unavailable``. No rows
            for the code answer 200 with ``data: null`` and a warning.
    """

    observations = _db_storage_observations()
    if observations is None:
        return _env(None, request)
    from eurogas_nexus.api.dependencies.row_entitlement import filter_rows

    wanted = code.strip().upper()
    series = []
    for row in filter_rows(request, observations):
        if str(row["facility_id"]).upper() != wanted:
            continue
        if row["inventory_twh"] is None or row["working_capacity_twh"] is None:
            continue
        series.append(
            StorageDay(
                gas_day=date.fromisoformat(row["period_start_utc"][:10]),
                inventory_twh=row["inventory_twh"],
                working_capacity_twh=row["working_capacity_twh"],
                injection_twh_d=row["injection_twh_d"],
                withdrawal_twh_d=row["withdrawal_twh_d"],
            )
        )
    try:
        trajectory = storage_trajectory(
            wanted,
            series,
            target_pct=target_pct,
            deviation_pp=deviation_pp,
            pace_days=pace_days,
        )
    except StorageTrajectoryError as exc:
        if not series:
            # No AGSI rows for this code is a data-availability state, answered like every
            # other read here: empty data plus a warning, not an HTTP error.
            return {
                "data": None,
                "meta": {
                    "research_only": True,
                    "human_review_required": True,
                    "source_references": ["runtime-postgresql"],
                    "warnings": [f"storage_series_unavailable: no AGSI series for {wanted}"],
                },
            }
        raise HTTPException(
            status_code=422,
            detail={"code": "storage_series_unavailable", "message": str(exc)},
        ) from exc
    return _runtime_env(trajectory.as_dict())


def _db_storage_observations(
    days: int | None = None, window: dict | None = None
) -> list[dict] | None:
    if not _db_is_configured():
        return None

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.application.identity_resolution import identity_clause
        from eurogas_nexus.db.models import StorageObservationRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = session.query(StorageObservationRecord).filter(
                identity_clause(session, StorageObservationRecord)
            )
            if days is not None:
                rows, stated = observation_window.bound(
                    session, rows, StorageObservationRecord.period_start_utc, days
                )
                if window is not None:
                    window.update(stated)
            rows = rows.order_by(
                StorageObservationRecord.facility_name,
                StorageObservationRecord.period_start_utc.desc(),
            )
            return [_storage_row(row) for row in rows.all()]
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _storage_row(row) -> dict:
    return {
        "observation_id": row.observation_id,
        "source_dataset": row.source_dataset,
        "facility_id": row.facility_id,
        "facility_name": row.facility_name,
        "country": row.country,
        "inventory_twh": row.inventory_twh,
        "working_capacity_twh": row.working_capacity_twh,
        "fill_pct": row.fill_pct,
        "injection_twh_d": row.injection_twh_d,
        "withdrawal_twh_d": row.withdrawal_twh_d,
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
            "message": "Runtime database is configured but unavailable for storage reads.",
            "error_class": exc.__class__.__name__,
        },
    )


#: GIE's reuse condition (agsi.gie.eu "API data usage", checked 2026-11-17): the source must
#: be named with the data. Returned with every storage fundamentals read.
GIE_ATTRIBUTION = "Source: GIE (Gas Infrastructure Europe), AGSI+ transparency platform"


@router.get("/api/fundamentals/storage")
def get_fundamentals_storage(
    request: Request,
    region: str = Query("eu", pattern="^(eu|nwe)$", description="eu (GIE EU aggregate) or nwe"),
    season: str | None = Query(
        None,
        max_length=200,
        description="Comma-separated entity codes (EU, NWE, DE...) whose full gas-year series "
        "and history band are returned; default the region only.",
    ),
    focus: str | None = Query(
        None, max_length=200, description="Comma-separated country codes listed first."
    ),
) -> dict:
    """Storage fill for a region and each of its countries against their own history.

    Fill, stock, working capacity, day and week change, the same gas day last year, the
    N-year average and band (N = complete prior gas years held, stated), injection and
    withdrawal, the EU target where it applies, a 30-day sparkline series and, for the
    entities in ``season``, the full gas-year series (``application/fundamentals_storage``).
    Countries of the region with no data are listed in ``missing`` with the reason.

    Raises:
        HTTPException: 503 ``runtime_db_unavailable`` when the store cannot be read.
    """

    from eurogas_nexus.api.dependencies.row_entitlement import current_principal
    from eurogas_nexus.application.fundamentals_storage import storage_read
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    def codes(text: str | None) -> list[str]:
        return [part.strip().upper() for part in (text or "").split(",") if part.strip()][:30]

    if not resolve_database_url():
        return _env(None, request)
    try:
        with get_session_factory()() as session:
            data = storage_read(
                session,
                current_principal(request),
                region=region,
                season=codes(season),
                focus=codes(focus),
            )
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 - a store failure is a 503, never a partial read
        raise HTTPException(status_code=503, detail="runtime_db_unavailable") from exc
    sources = sorted(
        {s for entity in [data["region"], *data["countries"]] if entity for s in entity["sources"]}
    )
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": sources or ["runtime-postgresql"],
            "attribution": (
                GIE_ATTRIBUTION if any(not s.endswith("_Sim") for s in sources) else None
            ),
            "warnings": list(data.get("warnings") or []),
        },
    }


@router.get("/api/fundamentals/lng")
def get_fundamentals_lng(
    request: Request,
    season: str | None = Query(
        None,
        max_length=200,
        description="Comma-separated codes (EU, DE...) whose full gas-year series and history "
        "band are returned; default the EU total only.",
    ),
) -> dict:
    """LNG send-out (7-day mean) for the EU total and each GIE ALSI country against history.

    Send-out today and as a 7-day mean, against the same gas day last year and the N-year
    average and band (N = complete prior gas years held, stated), inventory and its share of
    the declared maximum, a 30-day sparkline series and, for the codes in ``season``, the
    full gas-year series (``application/fundamentals_lng``). Countries with no rows are
    listed in ``missing``.

    Raises:
        HTTPException: 503 ``runtime_db_unavailable`` when the store cannot be read.
    """

    from eurogas_nexus.api.dependencies.row_entitlement import current_principal
    from eurogas_nexus.application.fundamentals_lng import lng_read
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    codes = [part.strip().upper() for part in (season or "").split(",") if part.strip()][:30]
    if not resolve_database_url():
        return _env(None, request)
    try:
        with get_session_factory()() as session:
            data = lng_read(session, current_principal(request), season=codes)
    except Exception as exc:  # noqa: BLE001 - a store failure is a 503, never a partial read
        raise HTTPException(status_code=503, detail="runtime_db_unavailable") from exc
    sources = sorted(
        {s for entity in [data["region"], *data["countries"]] if entity for s in entity["sources"]}
    )
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": sources or ["runtime-postgresql"],
            "attribution": (
                "Source: GIE (Gas Infrastructure Europe), ALSI transparency platform"
                if any(not s.endswith("_Sim") for s in sources)
                else None
            ),
            "warnings": [],
        },
    }


@router.get("/api/fundamentals/flows")
def get_fundamentals_flows(
    request: Request,
    season: str | None = Query(
        None,
        max_length=200,
        description="Comma-separated codes (norway, uk_terminal, dornum, emden...) whose full "
        "gas-year series and history band are returned; default none.",
    ),
) -> dict:
    """Norwegian and UK pipeline gas landed, totals then each landing, against history.

    The 7-day mean of the daily energy landed (GWh/d) and the day's own value, against the
    same gas day last year and the N-year average and band (N = complete prior gas years
    held, stated), a 30-day sparkline series and, for the codes in ``season``, the full
    gas-year series (``application/fundamentals_flows``). Provider and simulated rows are
    never added together.

    Raises:
        HTTPException: 503 ``runtime_db_unavailable`` when the store cannot be read.
    """

    from eurogas_nexus.api.dependencies.row_entitlement import current_principal
    from eurogas_nexus.application.fundamentals_flows import flows_read
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    codes = [part.strip().lower() for part in (season or "").split(",") if part.strip()][:30]
    if not resolve_database_url():
        return _env(None, request)
    try:
        with get_session_factory()() as session:
            data = flows_read(session, current_principal(request), season=codes)
    except Exception as exc:  # noqa: BLE001 - a store failure is a 503, never a partial read
        raise HTTPException(status_code=503, detail="runtime_db_unavailable") from exc
    provider = bool(data["totals"] or data["landings"]) and not data["simulated"]
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["ENTSOG"] if provider else ["runtime-postgresql"],
            # ENTSOG TP Terms of Use Art. 5: the source and the download date are cited; the
            # stored rows carry their download date.
            "attribution": "Source: ENTSOG Transparency Platform https://transparency.entsog.eu/"
            if provider
            else None,
            "warnings": list(data.get("warnings") or []),
        },
    }
