"""/api/lng routes: terminal reads, the tariff register and cargo economics."""

from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Query, Request, Response
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
    #: Why the distance changes; shown to the person who approves it (P-17).
    change_reason: str | None = Field(default=None, max_length=500)


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
    # The unit the DES price is stated in: per MWh, per MMBtu, or pence per therm (GBP).
    des_price_unit: str | None = Field(default=None, pattern="^(per_mwh|per_mmbtu|p_th)$")
    # DES: discharge port costs for the buyer's account under its contract, per call.
    discharge_port_cost: float | None = Field(default=None, ge=0, le=10_000_000)
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
    # The desk's own regas cost per MWh unloaded (overrides the published and register figures).
    regas_per_mwh: float | None = Field(default=None, ge=0, le=50)


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
    # EUA price for the carbon items (EUR/t); default the snapshot's, else the desk standard.
    eua_eur_t: float | None = Field(default=None, ge=0, le=500)
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
    from eurogas_nexus.application.maker_checker import provenance_for

    with _register_session() as session:
        rows = cargo.current_routes(session)
        # P-17: who recorded each distance, and who approved it when a second person did.
        provenance = provenance_for(
            session, [(r.row_id, r.recorded_by, r.recorded_at_utc, r.change_id) for r in rows]
        )
        return _runtime_env(
            [{**cargo.route_payload(row), "provenance": provenance[row.row_id]} for row in rows]
        )


@router.put("/api/lng/freight-routes/{route_id}")
def record_freight_route(
    route_id: str, body: FreightRouteBody, request: Request, response: Response
) -> dict:
    """Add a version of one route's distance (LNG desk reference data, audited).

    With four eyes in force (P-17, the default) the version is proposed and answers 202 with
    ``pending_approval``; another person on the desk approves it.
    """

    from eurogas_nexus.application import lng_cargo_economics as cargo
    from eurogas_nexus.application import maker_checker
    from eurogas_nexus.security.authorization import Permission

    if not route_id or len(route_id) > 96:
        raise HTTPException(status_code=422, detail={"code": "route_id_invalid"})
    actor = _actor(request, Permission.PORTFOLIO_WRITE)
    values = body.model_dump()
    reason = values.pop("change_reason", None) or ""
    with _register_session() as session:
        if maker_checker.four_eyes_required(session, "lng.freight_route"):
            try:
                cargo.validate_route(values)
            except cargo.CargoEconomicsError as exc:
                raise _cargo_error(exc) from exc
            names = list(cargo.ROUTE_FIELDS)
            held = maker_checker.route_snapshot(session, route_id, names)
            changed = [
                name for name in names if held is None or held.get(name) != values.get(name)
            ]
            if not changed:
                held_row = cargo.current_route(session, route_id)
                return _runtime_env({**cargo.route_payload(held_row), "pending_approval": False})
            try:
                change = maker_checker.propose_change(
                    session,
                    action="lng.freight_route",
                    target_key=route_id,
                    resource=f"freight_route:{route_id}",
                    subject=f"{values['load_port']} – {values['discharge_port']}",
                    payload={"values": values},
                    before=None if held is None else {name: held[name] for name in changed},
                    after={name: values.get(name) for name in changed},
                    reason=reason,
                    actor=actor,
                )
            except maker_checker.ChangeRequestError as exc:
                raise HTTPException(status_code=exc.status, detail=exc.detail()) from exc
            session.commit()
            response.status_code = 202
            return _runtime_env(
                {
                    "route_id": route_id,
                    "pending_approval": True,
                    "change": maker_checker.describe(
                        session, change, identity=getattr(request.state, "identity", None)
                    ),
                }
            )
        try:
            payload = cargo.record_route(session, route_id, values, actor=actor)
        except cargo.CargoEconomicsError as exc:
            session.rollback()
            raise _cargo_error(exc) from exc
        session.commit()
        return _runtime_env({**payload, "pending_approval": False})


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


# ------------------------------------------------------------------ cargoes in transit


class CargoHedgeLeg(BaseModel):
    """One futures or forward leg that covers part of a cargo's send-out."""

    model_config = ConfigDict(extra="forbid")

    hub: str = Field(min_length=2, max_length=16)
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    #: Signed MWh: a short hedge is negative.
    mwh: float = Field(ge=-10_000_000, le=10_000_000)
    reference: str | None = Field(default=None, max_length=160)


class CargoHedgesBody(BaseModel):
    """The full set of hedge legs for a cargo; it replaces the set held."""

    model_config = ConfigDict(extra="forbid")

    legs: list[CargoHedgeLeg] = Field(max_length=48)


class CargoWhatIfBody(BaseModel):
    """A schedule change to try on a cargo's plan; nothing is stored."""

    model_config = ConfigDict(extra="forbid")

    eta_utc: datetime | None = None
    slot_id: str | None = Field(default=None, max_length=96)
    berth_delay_hours: float = Field(default=0.0, ge=0, le=24 * 30)
    laytime_hours: float = Field(default=36.0, ge=0, le=24 * 10)
    demurrage_per_day: float | None = Field(default=None, ge=0, le=10_000_000)


def _plan_error(exc) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"error": exc.code, "code": exc.code, "message": exc.message},
    )


@router.get("/api/lng/cargoes/plans")
def cargo_plan_board(request: Request) -> dict:
    """The firm's cargoes not yet delivered, one line each: slot status, delivered energy,
    the last schedule change and the first suggestion (READ)."""

    from eurogas_nexus.application import lng_in_transit as transit
    from eurogas_nexus.security.authorization import Permission

    _actor(request, Permission.PORTFOLIO_READ)
    with _register_session() as session:
        return _runtime_env(transit.cargo_plans(session))


@router.get("/api/lng/cargoes/{cargo_id}/plan")
def cargo_plan(
    cargo_id: str,
    request: Request,
    berth_delay_hours: float = Query(default=0.0, ge=0, le=24 * 30),
    laytime_hours: float = Query(default=36.0, ge=0, le=24 * 10),
    demurrage_per_day: float | None = Query(default=None, ge=0, le=10_000_000),
) -> dict:
    """One cargo as a linked plan: berth, boil-off, delivered energy, send-out by gas day,
    hub months, hedge cover and suggestions, plus what the last schedule change did (READ).

    Suggestions are for the desk to decide; nothing is traded or nominated.
    """

    from eurogas_nexus.application import lng_in_transit as transit
    from eurogas_nexus.security.authorization import Permission

    _actor(request, Permission.PORTFOLIO_READ)
    with _register_session() as session:
        try:
            result = transit.cargo_plan(
                session,
                cargo_id,
                berth_delay_hours=berth_delay_hours,
                laytime_hours=laytime_hours,
                demurrage_per_day=demurrage_per_day,
            )
        except transit.CargoPlanError as exc:
            raise _plan_error(exc) from exc
        return _runtime_env(result)


@router.post("/api/lng/cargoes/{cargo_id}/plan/what-if")
def cargo_plan_what_if(cargo_id: str, body: CargoWhatIfBody, request: Request) -> dict:
    """The plan now against the plan under another ETA, slot or berth delay (READ: nothing is
    stored)."""

    from eurogas_nexus.application import lng_in_transit as transit
    from eurogas_nexus.security.authorization import Permission

    _actor(request, Permission.PORTFOLIO_READ)
    with _register_session() as session:
        try:
            result = transit.what_if(session, cargo_id, body.model_dump())
        except transit.CargoPlanError as exc:
            raise _plan_error(exc) from exc
        return _runtime_env(result)


@router.put("/api/lng/cargoes/{cargo_id}/hedges")
def record_cargo_hedges(cargo_id: str, body: CargoHedgesBody, request: Request) -> dict:
    """Record which hedges cover the cargo (replaces the set; the old one is retired). The
    platform never places a hedge; this records the desk's own (PORTFOLIO_WRITE, audited)."""

    from eurogas_nexus.application import lng_in_transit as transit
    from eurogas_nexus.security.authorization import Permission

    actor = _actor(request, Permission.PORTFOLIO_WRITE)
    with _register_session() as session:
        try:
            result = transit.record_hedges(
                session, cargo_id, [leg.model_dump() for leg in body.legs], actor=actor
            )
        except transit.CargoPlanError as exc:
            session.rollback()
            raise _plan_error(exc) from exc
        session.commit()
        return _runtime_env(result)



class DisruptionChoiceBody(BaseModel):
    """Why the desk chose this option (optional); the choice is recorded, nothing booked."""

    model_config = ConfigDict(extra="forbid")

    note: str | None = Field(default=None, max_length=2000)


@router.get("/api/lng/cargoes/{cargo_id}/disruption-options")
def cargo_disruption_options(cargo_id: str, request: Request) -> dict:
    """LNG-3: the book re-optimised around a disrupted cargo or pipeline supply: the options
    that move this cargo, each valued against the plan before the disruption over the ETA and
    price scenarios, the Pareto frontier, the recommended default and why the rest are
    dominated or infeasible, the run timeline and the last recorded choice (READ)."""

    from eurogas_nexus.application import lng_disruption as disruption
    from eurogas_nexus.application.lng_in_transit import CargoPlanError
    from eurogas_nexus.security.authorization import Permission

    _actor(request, Permission.PORTFOLIO_READ)
    with _register_session() as session:
        try:
            result = disruption.disruption_options(session, cargo_id)
        except CargoPlanError as exc:
            raise _plan_error(exc) from exc
        return _runtime_env(result)


@router.get("/api/lng/cargoes/{cargo_id}/disruption-options/{option_id}")
def cargo_disruption_option(cargo_id: str, option_id: str, request: Request) -> dict:
    """LNG-3: one option in full: each supply's leg day by day, the arithmetic per scenario,
    the hedge re-alignment, the obligations it meets or breaks and the mandates it moves
    (READ)."""

    from eurogas_nexus.application import lng_disruption as disruption
    from eurogas_nexus.application.lng_in_transit import CargoPlanError
    from eurogas_nexus.security.authorization import Permission

    _actor(request, Permission.PORTFOLIO_READ)
    with _register_session() as session:
        try:
            result = disruption.option_detail(session, cargo_id, option_id)
        except CargoPlanError as exc:
            raise _plan_error(exc) from exc
        return _runtime_env(result)


@router.post("/api/lng/cargoes/{cargo_id}/disruption-options/{option_id}/choose")
def choose_cargo_disruption_option(
    cargo_id: str, option_id: str, body: DisruptionChoiceBody, request: Request
) -> dict:
    """LNG-3: record the option the desk chose (PORTFOLIO_WRITE, audited
    ``lng.disruption_choice``). A record only: nothing is booked, borrowed, bought, traded or
    nominated. An infeasible option is refused (409)."""

    from eurogas_nexus.application import lng_disruption as disruption
    from eurogas_nexus.application.lng_in_transit import CargoPlanError
    from eurogas_nexus.security.authorization import Permission

    actor = _actor(request, Permission.PORTFOLIO_WRITE)
    with _register_session() as session:
        try:
            result = disruption.choose_option(
                session, cargo_id, option_id, actor=actor, note=body.note
            )
        except CargoPlanError as exc:
            session.rollback()
            raise _plan_error(exc) from exc
        session.commit()
        return _runtime_env(result)


@router.get("/api/lng/disruption/frontier")
def disruption_frontier(
    request: Request,
    book_id: str = Query(..., min_length=1, max_length=64),
    curtail_supply: str | None = Query(default=None, max_length=96),
    curtail_from: date | None = Query(default=None),
    curtail_to: date | None = Query(default=None),
    curtail_mwh_per_day: float | None = Query(default=None, gt=0, le=10_000_000),
) -> dict:
    """LNG-3: the whole book's disruption options and Pareto frontier. With ``curtail_*`` a
    pipeline supply of the book is taken as curtailed on those gas days (a what-if; nothing is
    stored) (READ)."""

    from eurogas_nexus.application import lng_disruption as disruption
    from eurogas_nexus.application.lng_in_transit import CargoPlanError
    from eurogas_nexus.security.authorization import Permission

    _actor(request, Permission.PORTFOLIO_READ)
    curtail = None
    asked = (curtail_supply, curtail_from, curtail_to, curtail_mwh_per_day)
    if any(value is not None for value in asked):
        if any(value is None for value in asked) or curtail_from > curtail_to:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "curtailment_incomplete",
                    "code": "curtailment_incomplete",
                    "message": "A curtailment needs curtail_supply, curtail_from <= curtail_to "
                    "and curtail_mwh_per_day.",
                },
            )
        if (curtail_to - curtail_from).days > 92:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "curtailment_too_long",
                    "code": "curtailment_too_long",
                    "message": "A what-if curtailment covers at most 93 gas days.",
                },
            )
        curtail = {
            "supply_id": curtail_supply,
            "first": curtail_from,
            "last": curtail_to,
            "mwh_per_day": curtail_mwh_per_day,
        }
    with _register_session() as session:
        try:
            result = disruption.frontier(session, book_id, curtail=curtail)
        except CargoPlanError as exc:
            raise _plan_error(exc) from exc
        return _runtime_env(result)
