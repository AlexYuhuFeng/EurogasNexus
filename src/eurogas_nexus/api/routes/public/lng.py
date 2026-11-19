"""/api/lng routes: terminal reads, the tariff register and cargo economics."""

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

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


def _db_lng_observations(days: int | None = None, window: dict | None = None) -> list[dict] | None:
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


# --------------------------------------------------------------- CP-12 cargo economics



class FreightRouteBody(BaseModel):
    """One version of a route's distance; ``source`` says where the distance comes from."""

    model_config = ConfigDict(extra="forbid")
    load_port: str = Field(min_length=1, max_length=96)
    discharge_port: str = Field(min_length=1, max_length=96)
    discharge_terminal_id: str | None = Field(default=None, max_length=64)
    routing: str = Field(pattern="^(direct|suez|panama|cape)$")
    distance_nm: float = Field(gt=0, le=30_000)
    canal: str = Field(default="none", pattern="^(none|suez|panama)$")
    source: str = Field(min_length=1, max_length=256)


class CargoBody(BaseModel):
    """One cargo: FOB with own shipping, or DES. Omitted figures come from the assumption set."""

    model_config = ConfigDict(extra="forbid")
    cargo_id: str = Field(min_length=1, max_length=64)
    label: str | None = Field(default=None, max_length=128)
    term: str = Field(pattern="^(FOB|DES)$")
    pricing_month: str | None = Field(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    q_load_mmbtu: float | None = Field(default=None, gt=0, le=6_000_000)
    hh: float | None = Field(default=None, gt=-10, le=100)
    slope: float | None = Field(default=None, ge=0, le=3)
    fee: float | None = Field(default=None, ge=-5, le=10)
    fob_price: float | None = Field(default=None, gt=-10, le=100)
    des_price: float | None = Field(default=None, gt=-500, le=1000)
    des_currency: str | None = Field(default=None, pattern="^(EUR|GBP|USD)$")
    route_id: str | None = Field(default=None, max_length=96)
    # The voyage as the desk states it when no saved route is named: a distance at a speed, or
    # days laden.
    # The desk's standard cargo fills what neither the request nor the assumption set holds
    # (each figure an assumption labelled "desk standard").
    standard: bool = False
    distance_nm: float | None = Field(default=None, gt=0, le=30_000)
    laden_days: float | None = Field(default=None, gt=0, le=90)
    ballast: str | None = Field(default=None, pattern="^(round|one_way)$")
    speed_kn: float | None = Field(default=None, ge=8, le=22)
    hire_per_day: float | None = Field(default=None, ge=0, le=1_000_000)
    boil_off_pct_per_day: float | None = Field(default=None, ge=0, le=1)
    ballast_fuel_mmbtu_per_day: float | None = Field(default=None, ge=0, le=10_000)
    port_cost: float | None = Field(default=None, ge=0, le=10_000_000)
    canal_cost: float | None = Field(default=None, ge=0, le=10_000_000)
    insurance_pct: float | None = Field(default=None, ge=0, le=2)


class TerminalInputBody(BaseModel):
    """Figures the desk enters for one terminal where the register holds none."""

    model_config = ConfigDict(extra="forbid")
    entry_per_mwh: float | None = Field(default=None, ge=0, le=50)
    gas_in_kind_pct: float | None = Field(default=None, ge=0, le=10)


class CargoEconomicsBody(BaseModel):
    """Cargoes to price for one arrival month, against the held (or the named) terminals."""

    model_config = ConfigDict(extra="forbid")
    arrival_month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    product: str = Field(default="spot", pattern="^(spot|term|prompt|annual)$")
    cargoes: list[CargoBody] = Field(min_length=1, max_length=10)
    terminal_ids: list[str] = Field(default_factory=list, max_length=50)
    terminal_inputs: dict[str, TerminalInputBody] = Field(default_factory=dict, max_length=50)
    # The delivered spread by arrival month for the first FOB cargo (design C.4), 0 for none.
    series_months: int = Field(default=0, ge=0, le=24)
    series_terminal_id: str | None = Field(default=None, max_length=96)
    # Henry Hub against the hub, daily, for the first FOB cargo on a formula (design C.4).
    history_days: int = Field(default=0, ge=0, le=730)
    # Terminals in several currencies are ranked in this currency at the arrival month's FX.
    reporting_currency: str = Field(default="EUR", pattern="^(EUR|GBP|USD)$")
    # The firm's assumption set to read (its approved version); default the organisation's.
    assumption_set_id: str | None = Field(default=None, max_length=64)


def _cargo_error(exc) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"error": exc.code, "code": exc.code, "message": exc.message},
    )


@router.get("/api/lng/freight-routes")
def list_freight_routes() -> dict:
    """Voyage distances the firm holds, latest version of each route (READ)."""

    from eurogas_nexus.application import lng_cargo_economics as cargo

    with _register_session() as session:
        return _runtime_env([cargo.route_payload(row) for row in cargo.current_routes(session)])


@router.put("/api/lng/freight-routes/{route_id}")
def record_freight_route(route_id: str, body: FreightRouteBody, request: Request) -> dict:
    """Add a version of one route's distance (LNG desk reference data, audited)."""

    from eurogas_nexus.application import lng_cargo_economics as cargo
    from eurogas_nexus.security.authorization import Permission

    if not route_id or len(route_id) > 96:
        raise HTTPException(status_code=422, detail={"code": "route_id_invalid"})
    actor = _actor(request, Permission.PORTFOLIO_WRITE)
    with _register_session() as session:
        try:
            payload = cargo.record_route(session, route_id, body.model_dump(), actor=actor)
        except cargo.CargoEconomicsError as exc:
            session.rollback()
            raise _cargo_error(exc) from exc
        session.commit()
        return _runtime_env(payload)


@router.post("/api/lng/cargo-economics")
def post_cargo_economics(body: CargoEconomicsBody, request: Request) -> dict:
    """FOB and DES cargoes in one table: cost at the ship's rail, netback and margin per
    terminal for the arrival month, every input with its class and source (design C.1-C.3).

    Prices cargoes for the desk to decide; nothing is offered, nominated or sent.
    """

    from eurogas_nexus.application import lng_cargo_economics as cargo
    from eurogas_nexus.application.caller import caller_of

    payload = body.model_dump()
    payload["cargoes"] = [
        {key: value for key, value in item.items() if value is not None}
        for item in payload["cargoes"]
    ]
    payload["terminal_inputs"] = {
        key: {k: v for k, v in value.items() if v is not None}
        for key, value in payload["terminal_inputs"].items()
    }
    with _register_session() as session:
        if body.assumption_set_id:
            from eurogas_nexus.db.repositories.commercial_assumptions import (
                assumption_set_book,
            )
            from eurogas_nexus.security.portfolio_scope import visible_book_ids

            exists, book_id = assumption_set_book(session, body.assumption_set_id)
            allowed = visible_book_ids(session)
            if not exists or (book_id and allowed is not None and book_id not in allowed):
                raise HTTPException(status_code=404, detail={"code": "unknown_assumption_set"})
        try:
            result = cargo.cargo_economics(session, payload, caller=caller_of(request))
        except cargo.CargoEconomicsError as exc:
            raise _cargo_error(exc) from exc
        return _runtime_env(result)
