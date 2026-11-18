"""Read-only /api/lng routes."""

from fastapi import APIRouter, HTTPException, Query, Request

from eurogas_nexus.api.routes.public import observation_window

router = APIRouter(tags=["lng"])


def _env(data: object, _request: Request) -> dict:
    return {
        "data": data,
        "meta": {
            "research_only": True,
            "human_review_required": True,
            "source_references": ["runtime-db-not-configured"],
            "warnings": ["Runtime DB is not configured; GIE ALSI data is unavailable."],
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


@router.get("/api/lng/terminals")
def list_terminals(request: Request) -> dict:
    """List LNG terminals aggregated from runtime observations.

    按 terminal_id 聚合最新观测为终端列表；DB 未配置时降级为空并告警。

    Args:
        request: Incoming FastAPI request (unused except wiring).

    Returns:
        Enveloped terminal list (one entry per terminal) or an empty
        enveloped response with a warning.

    Raises:
        HTTPException: 503 ``runtime_db_unavailable`` on DB read failure.
    """

    observations = _db_lng_observations()
    if observations is None:
        return _env([], request)
    from eurogas_nexus.api.dependencies.row_entitlement import filter_rows

    observations = filter_rows(request, observations)
    terminals: dict[str, dict] = {}
    for row in observations:
        terminals.setdefault(
            row["terminal_id"],
            {
                "terminal_id": row["terminal_id"],
                "name": row["terminal_name"],
                "country": row["country"],
                "inventory_twh": row["inventory_twh"],
                "send_out_twh_d": row["send_out_twh_d"],
                "dtmi_twh": row["dtmi_twh"],
                "observed_at_utc": row["observed_at_utc"],
                "status": "observed",
                "source_system": row["source_system"],
            },
        )
    return _runtime_env(list(terminals.values()))


@router.get("/api/lng/observations")
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
    """List LNG terminal observations from the runtime DB.

    Bounded to the newest ``days`` gas days in the store (default 45, stated in
    ``meta.window``; see ``observation_window``). A longer series asks for it with ``days``.

    返回 LNG 观测列表（按终端名 + 周期倒序）；DB 未配置时降级为空并告警。

    Args:
        request: Incoming FastAPI request (unused except wiring).
        days: Gas days back from the newest observation (1..800).

    Returns:
        Enveloped observation rows or an empty enveloped response.

    Raises:
        HTTPException: 503 ``runtime_db_unavailable`` on DB read failure.
    """

    window: dict = {}
    observations = _db_lng_observations(days, window)
    if observations is not None:
        from eurogas_nexus.api.dependencies.row_entitlement import filter_rows

        envelope = _runtime_env(filter_rows(request, observations))
        envelope["meta"]["window"] = window
        return envelope

    return _env([], request)


def _db_lng_observations(
    days: int | None = None, window: dict | None = None
) -> list[dict] | None:
    if not _db_is_configured():
        return None

    sqlalchemy_error = _sqlalchemy_error_type()
    try:
        from eurogas_nexus.application.identity_resolution import identity_clause
        from eurogas_nexus.db.models import LngObservationRecord
        from eurogas_nexus.db.session import get_session_factory

        with get_session_factory()() as session:
            rows = session.query(LngObservationRecord).filter(
                identity_clause(session, LngObservationRecord)
            )
            if days is not None:
                rows, stated = observation_window.bound(
                    session, rows, LngObservationRecord.period_start_utc, days
                )
                if window is not None:
                    window.update(stated)
            rows = rows.order_by(
                LngObservationRecord.terminal_name,
                LngObservationRecord.period_start_utc.desc(),
            )
            return [_lng_row(row) for row in rows.all()]
    except sqlalchemy_error as exc:
        raise _db_unavailable(exc) from exc


def _lng_row(row) -> dict:
    return {
        "observation_id": row.observation_id,
        "source_dataset": row.source_dataset,
        "terminal_id": row.terminal_id,
        "terminal_name": row.terminal_name,
        "country": row.country,
        "inventory_twh": row.inventory_twh,
        "send_out_twh_d": row.send_out_twh_d,
        "dtmi_twh": row.dtmi_twh,
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
            "message": "Runtime database is configured but unavailable for LNG reads.",
            "error_class": exc.__class__.__name__,
        },
    )


# --- the public LNG terminal tariff register (CP-11) -----------------------------------------


def _register_error(exc) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"error": exc.code, "code": exc.code, "message": exc.message},
    )


def _actor(request: Request, permission) -> str:
    from eurogas_nexus.security.authorization import authorize

    principal = getattr(request.state, "identity", None)
    if principal is None:
        raise HTTPException(status_code=401, detail={"error": "principal_missing"})
    if not authorize(principal, permission).allowed:
        raise HTTPException(status_code=403, detail={"error": "permission_denied"})
    return principal.principal_id


def _register_session():
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    if resolve_database_url() is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "runtime_db_required", "message": "The register needs the runtime DB."},
        )
    return get_session_factory()()


@router.get("/api/lng/terminal-tariffs")
def terminal_tariff_register(request: Request) -> dict:
    """The public terminal tariff register: figures with provenance and review state, and each
    operator's reuse terms (whether the firm recorded permission). Public data; READ."""

    from eurogas_nexus.application import lng_terminal_tariff_register as register

    with _register_session() as session:
        return _runtime_env(register.register_view(session))


@router.get("/api/lng/terminal-tariffs/price")
def terminal_tariff_price(
    terminal_id: str = Query(min_length=1, max_length=64),
    arrival_month: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    cargo_mwh: float = Query(gt=0, le=3_000_000),
    product: str = Query(default="spot", pattern="^(spot|term|prompt|annual)$"),
) -> dict:
    """What landing one cargo costs and on which basis: the firm's terms, the reviewed public
    tariff, a candidate (indicative), or left out with the reason (design C.5)."""

    from dataclasses import asdict

    from eurogas_nexus.application import lng_terminal_tariff_register as register

    with _register_session() as session:
        charge = register.price_terminal(
            session, terminal_id, arrival_month=arrival_month, cargo_mwh=cargo_mwh, product=product
        )
        return _runtime_env(asdict(charge))


@router.post("/api/lng/terminal-tariffs/{tariff_id}/review")
def review_terminal_tariff(tariff_id: str, request: Request) -> dict:
    """Mark a candidate figure reviewed (OPERATOR; four eyes: never by whoever recorded it)."""

    from eurogas_nexus.application import lng_terminal_tariff_register as register
    from eurogas_nexus.security.authorization import Permission

    actor = _actor(request, Permission.SOURCE_RUN)
    with _register_session() as session:
        try:
            payload = register.review_tariff(session, tariff_id, reviewer=actor)
        except register.TariffRegisterError as exc:
            session.rollback()
            raise _register_error(exc) from exc
        session.commit()
        return _runtime_env(payload)


@router.put("/api/lng/terminal-tariffs/operators/{operator}")
def record_terminal_operator_terms(operator: str, body: dict, request: Request) -> dict:
    """Record (or withdraw) the firm's permission to reuse an operator's documents (ADMIN).

    Body ``{"permitted": bool, "reference": str}``: the reference names what the firm holds
    (a letter, a contract clause). The product never records a permission by itself.
    """

    from eurogas_nexus.application import lng_terminal_tariff_register as register
    from eurogas_nexus.security.authorization import Permission

    actor = _actor(request, Permission.IDENTITY_MANAGE)
    permitted = body.get("permitted")
    reference = body.get("reference") or ""
    if not isinstance(permitted, bool) or not isinstance(reference, str) or len(reference) > 256:
        raise HTTPException(status_code=422, detail={"code": "body_invalid"})
    with _register_session() as session:
        try:
            payload = register.record_operator_permission(
                session, operator, permitted=permitted, reference=reference, actor=actor
            )
        except register.TariffRegisterError as exc:
            session.rollback()
            raise _register_error(exc) from exc
        session.commit()
        return _runtime_env(payload)
