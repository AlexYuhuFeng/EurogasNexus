"""Cargo economics for the desk: one table for FOB and DES cargoes (CP-12, design C.1-C.3).

Reads every input through the valuation snapshot (``application/valuation_snapshot.py``) or
the LNG reference registers, never guesses one, and hands the pure chain
(``domain/lng/cargo_economics.py``) values that each carry their class and source:

* hub price for the arrival month: ``reader.price(hub, month)`` (licensed quote, settlement,
  the firm's mark; demo price only on a demo desk);
* FX for the arrival month: ``reader.fx(hub currency, USD, month)``, the snapshot's CP-01
  forward (licensed, else covered interest parity), the spot reference rate only as its
  labelled fallback;
* Henry Hub for the pricing month: ``reader.price("HH", month)``; else the latest EIA daily spot
  as a flat proxy, class ``indicative`` and labelled "spot proxy" (EIA stopped publishing
  futures settlements on 5 April 2024; a forward comes from the customer's entitlement or the
  firm's mark);
* assumptions (charter hire, boil-off, speed, ballast fuel, insurance, port costs, the FOB
  formula, cargo size): what the request states (class ``assumption``, "entered"), else the
  firm's approved assumption set, else missing;
* the voyage: a saved ``freight_route`` (latest version, class derived) when one is named;
  else the voyage the desk enters, as a distance at a speed or as days laden (class
  ``assumption``, "entered"). No sea-distance table ships with the product, so an entered voyage
  is the normal case until the firm records its routes;
* regas charge: the firm's terms, the reviewed public tariff, a candidate (indicative)
  (``application/lng_terminal_tariff_register.py``); gas in kind and entry tariff from the
  firm's terms, the register's in-kind figure, or the request.

Nothing is offered, nominated or sent: this prices cargoes for the desk to decide.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from eurogas_nexus.domain.lng.cargo_economics import (
    CargoOffer,
    TerminalOption,
    Valued,
    evaluate_cargo,
    missing,
    serialise,
)
from eurogas_nexus.domain.lng.voyage import Voyage
from eurogas_nexus.domain.valuation.periods import DeliveryPeriod
from eurogas_nexus.domain.valuation.quality import InputClass, weakest

#: Assumption-set keys and the request field that overrides each.
ASSUMPTION_KEYS = {
    "q_load_mmbtu": "lng.cargo_size",
    "hire_per_day": "lng.charter_hire",
    "boil_off_pct_per_day": "lng.boil_off",
    "port_cost": "lng.port_costs",
    "speed_kn": "lng.speed",
    "ballast_fuel_mmbtu_per_day": "lng.ballast_fuel",
    "insurance_pct": "lng.insurance",
    "slope": "lng.fob_slope",
    "fee": "lng.fob_fee",
}
ROUTINGS = ("direct", "suez", "panama", "cape")


class CargoEconomicsError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


# ------------------------------------------------------------------ freight routes


def route_payload(row) -> dict[str, Any]:
    return {
        "route_id": row.route_id,
        "version": row.version,
        "load_port": row.load_port,
        "discharge_port": row.discharge_port,
        "discharge_terminal_id": row.discharge_terminal_id,
        "routing": row.routing,
        "distance_nm": row.distance_nm,
        "canal": row.canal,
        "source": row.source,
        "recorded_by": row.recorded_by,
        "recorded_at_utc": row.recorded_at_utc.isoformat() if row.recorded_at_utc else None,
    }


def current_routes(session) -> list:
    from eurogas_nexus.db.models import FreightRouteRecord

    latest: dict[str, Any] = {}
    for row in session.query(FreightRouteRecord).all():
        held = latest.get(row.route_id)
        if held is None or row.version > held.version:
            latest[row.route_id] = row
    return [latest[key] for key in sorted(latest)]


def current_route(session, route_id: str):
    from eurogas_nexus.db.models import FreightRouteRecord

    return (
        session.query(FreightRouteRecord)
        .filter(FreightRouteRecord.route_id == route_id)
        .order_by(FreightRouteRecord.version.desc())
        .first()
    )


def validate_route(values: dict[str, Any]) -> str:
    """Check a route's values and return its source text.

    Raises:
        CargoEconomicsError: ``routing_invalid``, ``canal_invalid``, ``distance_invalid`` or
            ``source_required``.
    """

    if values.get("routing") not in ROUTINGS:
        raise CargoEconomicsError("routing_invalid", "routing is direct, suez, panama or cape")
    if values.get("canal", "none") not in {"none", "suez", "panama"}:
        raise CargoEconomicsError("canal_invalid", "canal is none, suez or panama")
    distance = values.get("distance_nm")
    if not isinstance(distance, int | float) or not 0 < distance <= 30_000:
        raise CargoEconomicsError("distance_invalid", "distance_nm must be within 0-30,000 nm")
    source = str(values.get("source") or "").strip()
    if not source:
        raise CargoEconomicsError("source_required", "Say where the distance comes from.")
    return source


#: The fields of a route version a proposal compares and an approval applies (P-17).
ROUTE_FIELDS = (
    "load_port",
    "discharge_port",
    "discharge_terminal_id",
    "routing",
    "distance_nm",
    "canal",
    "source",
)


def record_route(
    session,
    route_id: str,
    values: dict[str, Any],
    *,
    actor: str,
    approved_by: str | None = None,
    change_id: str | None = None,
) -> dict[str, Any]:
    """Add a version of one route (never overwrites); a governed write, audited with it.

    ``actor`` recorded the distance; ``approved_by`` and ``change_id`` name the second person
    and the proposal when one approved it (P-17).
    """

    from eurogas_nexus.application.audit_service import record_governed_audit
    from eurogas_nexus.db.models import FreightRouteRecord

    source = validate_route(values)
    distance = values["distance_nm"]
    held = current_route(session, route_id)
    row = FreightRouteRecord(
        row_id=f"frt-{uuid4().hex[:20]}",
        route_id=route_id,
        version=(held.version + 1) if held else 1,
        load_port=str(values["load_port"]).strip(),
        discharge_port=str(values["discharge_port"]).strip(),
        discharge_terminal_id=values.get("discharge_terminal_id") or None,
        routing=values["routing"],
        distance_nm=float(distance),
        canal=values.get("canal", "none"),
        source=source[:256],
        recorded_by=actor[:128],
        recorded_at_utc=datetime.now(UTC),
        change_id=change_id,
    )
    session.add(row)
    detail = f"version {row.version}"
    if approved_by:
        detail = f"proposed by {actor}, approved by {approved_by} ({change_id}); {detail}"
    # GOV-1 (P5): a route's distance is reference data a cargo's economics reads.
    record_governed_audit(
        session,
        event_type="reference_data",
        principal=approved_by or actor,
        action="lng.freight_route",
        resource=f"freight_route:{route_id}",
        detail=detail,
        after_summary={name: getattr(row, name) for name in ROUTE_FIELDS},
    )
    from eurogas_nexus.application.opportunities.schedule import note_input_changed

    note_input_changed(session, "freight", reason=f"freight route {route_id}")
    return route_payload(row)


# ------------------------------------------------------------------ inputs


def _valued(item) -> Valued:
    """A snapshot input as the chain's ``Valued``."""

    if not item.held:
        return missing(item.label or item.key)
    return Valued(Decimal(str(item.value)), item.input_class, item.label or item.source_ref)


def _entered(value: float | None, label: str) -> Valued | None:
    if value is None:
        return None
    return Valued(Decimal(str(value)), InputClass.ASSUMPTION, f"entered: {label}")


#: The desk's standard US Gulf FOB cargo (design C.3): what a figure is when neither the request
#: nor the firm's approved assumption set holds it and the caller asks for the standard cargo.
#: Each is an assumption, labelled "desk standard" (never a market value).
STANDARD_CARGO: dict[str, float] = {
    "q_load_mmbtu": 3_800_000,
    "slope": 1.15,
    "fee": 2.50,
    "speed_kn": 17,
    "hire_per_day": 45_000,
    "boil_off_pct_per_day": 0.10,
    "ballast_fuel_mmbtu_per_day": 2_000,
    "port_cost": 150_000,
    "insurance_pct": 0.05,
}
#: The standard voyage, US Gulf to north-west Europe, when no route is saved or entered.
STANDARD_DISTANCE_NM = 4_900


def _assumed(reader, cargo: dict[str, Any], field: str) -> Valued:
    entered = _entered(cargo.get(field), field)
    if entered is not None:
        return entered
    held = _valued(reader.assumption(ASSUMPTION_KEYS[field]))
    if not held.held and cargo.get("standard") and field in STANDARD_CARGO:
        return Valued(
            Decimal(str(STANDARD_CARGO[field])), InputClass.ASSUMPTION, f"desk standard: {field}"
        )
    return held


def _month(text: str) -> DeliveryPeriod:
    return DeliveryPeriod.month(int(text[:4]), int(text[5:7]))


#: The demo market's own stream (``scripts/demo/seed_demo_desk.py``): read on a demo desk only.
DEMO_SOURCE = "DEMO_Sim"


def _hh_spot_rows(session, *, demo_desk: bool, since: date | None = None) -> list:
    """Henry Hub daily spot held, one row per day: EIA (public domain, ``ingestion/eia.py``);
    on a demo desk the demo's simulated series where EIA has no row. Oldest first."""

    from eurogas_nexus.db.models import MarketObservationRecord

    sources = ("EIA", DEMO_SOURCE) if demo_desk else ("EIA",)
    query = (
        session.query(MarketObservationRecord)
        .filter(MarketObservationRecord.source_system.in_(sources))
        .filter(MarketObservationRecord.product == "HH spot")
    )
    if since is not None:
        query = query.filter(
            MarketObservationRecord.period_start_utc
            >= datetime.combine(since, datetime.min.time(), tzinfo=UTC)
        )
    by_day: dict[date, Any] = {}
    for row in query.all():
        day = row.period_start_utc.date()
        held = by_day.get(day)
        if held is None or (held.source_system != "EIA" and row.source_system == "EIA"):
            by_day[day] = row
    return [by_day[day] for day in sorted(by_day)]


def _hh_label(row, pricing_month: str | None = None) -> tuple[InputClass, str]:
    day = row.period_start_utc.date().isoformat()
    if row.source_system == "EIA":
        text = f"Henry Hub spot {day} (EIA)"
        klass = InputClass.INDICATIVE
    else:
        text = f"Henry Hub spot {day} (simulated)"
        klass = InputClass.SIMULATED
    return klass, f"{text}, spot proxy for {pricing_month}" if pricing_month else text


def _hh(session, reader, pricing_month: str, entered: float | None) -> Valued:
    if entered is not None:
        return Valued(Decimal(str(entered)), InputClass.ASSUMPTION, "entered: Henry Hub")
    forward = reader.price("HH", _month(pricing_month))
    if forward.held:
        return _valued(forward)
    rows = _hh_spot_rows(
        session,
        demo_desk=reader.demo_desk,
        since=datetime.now(UTC).date() - timedelta(days=31),
    )
    if not rows:
        return missing("Henry Hub: no forward or spot held")
    klass, text = _hh_label(rows[-1], pricing_month)
    return Valued(Decimal(str(rows[-1].price)), klass, text)


@dataclass(frozen=True)
class _Terminal:
    terminal_id: str
    name: str
    hub: str
    gas_in_kind_pct: float | None
    entry_per_mwh: float | None
    excludes: tuple[str, ...]
    #: "firm" (the firm's own terms) or "register" (a public register row): who gave gas in kind.
    gik_from: str = "register"
    #: The published reference (``domain/lng/published_tariffs.py``), when the terminal is in it.
    published: Any = None
    #: Terms the demo desk seeded (``demo-`` ids): fictional, never a default study terminal.
    demo: bool = False


def _terminals(session, wanted: list[str], *, study: bool = False) -> list[_Terminal]:
    """Terminals with firm terms or register rows; with ``study`` also every published terminal,
    and by default (nothing named) the published and the firm's real terminals, not demo ones."""

    from eurogas_nexus.db.models import LngTerminalTariffRecord, LngTerminalTermsRecord
    from eurogas_nexus.domain.lng.published_tariffs import published_terminals

    found: dict[str, _Terminal] = {}
    for row in session.query(LngTerminalTermsRecord).all():
        if row.source_url is not None:
            continue  # written by an earlier refresh from an operator document: not firm terms
        found[row.terminal_id] = _Terminal(
            row.terminal_id,
            row.name,
            row.hub,
            row.fuel_retention_pct,
            row.entry_tariff_per_mwh,
            (),
            gik_from="firm",
            demo=row.terminal_id.startswith("demo-"),
        )
    for row in session.query(LngTerminalTariffRecord).all():
        held = found.get(row.terminal_id)
        in_kind = row.amount if row.charge_basis == "percent_in_kind" else None
        if held is None:
            found[row.terminal_id] = _Terminal(
                row.terminal_id,
                row.terminal_name,
                row.hub,
                in_kind,
                None,
                tuple(row.excludes or ()),
            )
        elif held.gas_in_kind_pct is None and in_kind is not None:
            found[row.terminal_id] = _Terminal(
                **{**held.__dict__, "gas_in_kind_pct": in_kind, "gik_from": "register"}
            )
    if study:
        for published in published_terminals():
            # The firm's own terms for this terminal (by id or alias) stand for it.
            own = next(
                (
                    key
                    for key, terminal in found.items()
                    if not terminal.demo
                    and key != published.terminal_id
                    and published.known_as(key)
                ),
                None,
            )
            if own is not None:
                found[own] = _Terminal(**{**found[own].__dict__, "published": published})
                continue
            held = found.get(published.terminal_id)
            found[published.terminal_id] = (
                _Terminal(
                    published.terminal_id,
                    published.name,
                    published.hub,
                    None,
                    None,
                    (),
                    published=published,
                )
                if held is None
                else _Terminal(**{**held.__dict__, "published": published})
            )
    if wanted:
        return [found[key] for key in wanted if key in found]
    if study:
        order = {t.terminal_id: index for index, t in enumerate(published_terminals())}
        chosen = [t for t in found.values() if not t.demo]
        return sorted(chosen, key=lambda t: (order.get(t.terminal_id, len(order)), t.terminal_id))
    return [found[key] for key in sorted(found)]


def known_terminals(session) -> list[_Terminal]:
    """Every terminal the firm's terms or the tariff register names, with its hub and gas in
    kind (the cargo-in-transit plan resolves a slot's terminal through this)."""

    return _terminals(session, [])


def _hub_currency(hub: str) -> str:
    from eurogas_nexus.domain.ontology.markets import find_market

    market = find_market(hub)
    return getattr(market, "currency", None) or ("GBP" if hub == "NBP" else "EUR")


def _neighbour(period: DeliveryPeriod, shift: int) -> DeliveryPeriod:
    index = period.start.year * 12 + period.start.month - 1 + shift
    return DeliveryPeriod.month(index // 12, index % 12 + 1)


def _usd_per(reader, currency: str, period: DeliveryPeriod) -> Valued:
    """USD per one unit of ``currency`` for the month (1 for USD)."""

    if currency == "USD":
        return Valued(Decimal(1), InputClass.SOURCED, "USD")
    return _valued(reader.fx(currency, "USD", period))


def _cross(reader, base: str, quote: str, period: DeliveryPeriod) -> Valued:
    """Units of ``quote`` per one ``base`` for the month, through USD; missing when either is."""

    if base == quote:
        return Valued(Decimal(1), InputClass.SOURCED, base)
    a, b = _usd_per(reader, base, period), _usd_per(reader, quote, period)
    if not a.held or not b.held:
        return missing(f"FX {base}/{quote}")
    return Valued(
        a.value / b.value,
        weakest([a.input_class, b.input_class]),
        f"{base}/{quote} via USD: {a.source}; {b.source}",
    )


def _option(
    session,
    reader,
    terminal: _Terminal,
    *,
    request: dict[str, Any],
    q_del_mwh: float,
    offer: CargoOffer | None = None,
    cost_side=None,
    cargo: dict[str, Any] | None = None,
):
    """One terminal for the arrival month, and what the result says about where each figure
    came from (the regas version, the entry tariff, the hub price's date, what is excluded)."""

    from eurogas_nexus.application import lng_cargo_netback as desk
    from eurogas_nexus.application import lng_terminal_tariff_register as register
    from eurogas_nexus.domain.lng import published_tariffs as published_tariffs

    month = request["arrival_month"]
    period = _month(month)
    currency = _hub_currency(terminal.hub)
    price_item = reader.price(terminal.hub, period)
    before = after = None
    for shift, slot in ((-1, "before"), (1, "after")):
        other = reader.price(terminal.hub, _neighbour(period, shift))
        if other.held:
            if slot == "before":
                before = other.value
            else:
                after = other.value
    product = request.get("product", "spot")
    overrides = (request.get("terminal_inputs") or {}).get(terminal.terminal_id, {})
    published = terminal.published
    meta: dict[str, Any] = {
        "hub_as_of": price_item.as_of_utc.isoformat() if price_item.as_of_utc else None,
        "hub_licence_needed": price_item.input_class == InputClass.SIMULATED,
        "excluded": [],
        "versions": {},
        "demo": terminal.demo,
        "published": desk.published_payload(published),
    }
    charge = register.price_terminal(
        session,
        terminal.terminal_id,
        arrival_month=month,
        cargo_mwh=q_del_mwh,
        product=product,
    )
    basis = charge.basis
    excludes = tuple(charge.excludes) or terminal.excludes
    entered_regas = overrides.get("regas_per_mwh")
    arrival_day = period.start
    if entered_regas is not None:
        regas = Valued(
            Decimal(str(entered_regas)) * Decimal(str(q_del_mwh)),
            InputClass.ASSUMPTION,
            "entered: regas cost",
        )
        basis = "entered"
    elif charge.charge is not None:
        klass = {
            "firm_terms": InputClass.FIRM_MARK,
            "reviewed_public": InputClass.SOURCED,
            "candidate_public": InputClass.INDICATIVE,
        }[charge.basis]
        regas = Valued(Decimal(str(charge.charge)), klass, charge.basis)
    else:
        uses = (
            published_tariffs.select(published, "regas", arrival_day, product)
            if published is not None
            else []
        )
        total = published_tariffs.regas_total(uses, Decimal(str(q_del_mwh)))
        if total is not None and uses[0].charge.currency == currency:
            status = published_tariffs.weakest_status(uses)
            regas = Valued(
                total,
                InputClass.SOURCED if status == "FINAL" else InputClass.INDICATIVE,
                f"published: {uses[0].charge.source_title}",
            )
            basis = "published_final" if status == "FINAL" else "published_indicative"
            meta["versions"]["regas"] = [use.version() for use in uses]
        else:
            regas = missing(
                "not_published"
                if published is not None and not published.permission_operator
                else charge.reason or "no tariff"
            )
            if published is not None and published.permission_operator:
                basis = "needs_firm_terms"
    entry = _entered(overrides.get("entry_per_mwh"), "entry tariff")
    if entry is None and terminal.entry_per_mwh is not None:
        entry = Valued(
            Decimal(str(terminal.entry_per_mwh)), InputClass.FIRM_MARK, "your terminal terms"
        )
    if entry is None and published is not None:
        uses = published_tariffs.select(
            published, "entry_capacity", arrival_day, "firm"
        ) + published_tariffs.select(published, "entry_commodity", arrival_day, "firm")
        value = published_tariffs.entry_per_mwh(uses)
        if value is not None and uses[0].charge.currency == currency:
            status = published_tariffs.weakest_status(uses)
            entry = Valued(
                value,
                InputClass.SOURCED if status == "FINAL" else InputClass.INDICATIVE,
                f"published: {published.entry_tso}, {published.entry_point}",
            )
            meta["versions"]["entry"] = [use.version() for use in uses]
        else:
            # A published terminal is still compared; the entry it lacks is excluded and said.
            entry = Valued(Decimal(0), InputClass.ASSUMPTION, "entry capacity not held: excluded")
            meta["excluded"].append("entry")
    if entry is None:
        entry = missing("entry tariff")
    gik = _entered(overrides.get("gas_in_kind_pct"), "gas in kind")
    if gik is None and terminal.gas_in_kind_pct is not None:
        gik = Valued(
            Decimal(str(terminal.gas_in_kind_pct)),
            InputClass.FIRM_MARK if terminal.gik_from == "firm" else InputClass.SOURCED,
            "your terminal terms" if terminal.gik_from == "firm" else "tariff register",
        )
    gik_uses = (
        published_tariffs.select(published, "gas_in_kind", arrival_day, product)
        if published is not None
        else []
    )
    if gik is None and gik_uses:
        status = published_tariffs.weakest_status(gik_uses)
        gik = Valued(
            published_tariffs.percent(gik_uses),
            InputClass.SOURCED if status == "FINAL" else InputClass.INDICATIVE,
            f"published: {gik_uses[0].charge.source_title}",
        )
        meta["versions"]["gas_in_kind"] = [use.version() for use in gik_uses]
    if gik is None and published is not None:
        gik = Valued(Decimal(0), InputClass.ASSUMPTION, "gas in kind not published: excluded")
        meta["excluded"].append("gas_in_kind")
    if gik is None:
        gik = missing("gas in kind")
    fx = reader.fx(currency, "USD", period) if currency != "USD" else None
    fx_value = Valued(Decimal(1), InputClass.SOURCED, "USD") if fx is None else _valued(fx)
    des_fx = None
    if offer is not None and offer.term == "DES" and offer.des_currency != currency:
        des_fx = _cross(reader, offer.des_currency, currency, period)
    others = desk.other_costs(
        reader,
        request=request,
        cargo=cargo,
        terminal=terminal,
        currency=currency,
        period=period,
        q_del_mwh=Decimal(str(q_del_mwh)),
        gik=gik,
        offer=offer,
        cost_side=cost_side,
        fx_usd_per_unit=fx_value,
        des_fx=des_fx,
        meta=meta,
    )
    option = TerminalOption(
        terminal_id=terminal.terminal_id,
        name=terminal.name,
        hub=terminal.hub,
        currency=currency,
        arrival_month=month,
        hub_price=_valued(price_item),
        entry=entry,
        gas_in_kind_pct=gik,
        regas_total=regas,
        regas_basis=basis,
        fx_usd_per_unit=fx_value,
        hub_price_before=before,
        hub_price_after=after,
        excludes=excludes,
        other_items=others,
        des_fx=des_fx,
    )
    return option, meta


def _offer(session, reader, cargo: dict[str, Any], pricing_month: str) -> CargoOffer:
    term = cargo["term"]
    q_load = _assumed(reader, cargo, "q_load_mmbtu")
    common = {
        "cargo_id": cargo["cargo_id"],
        "label": cargo.get("label") or cargo["cargo_id"],
        "term": term,
        "q_load_mmbtu": q_load,
    }
    if term == "DES":
        from eurogas_nexus.application.lng_cargo_netback import des_per_mwh

        per_mwh, currency, _how = des_per_mwh(cargo)
        return CargoOffer(
            **common,
            des_price=_entered(per_mwh, "DES price") or missing("DES price"),
            des_currency=currency,
        )
    voyage = route = None
    voyage_class = InputClass.DERIVED
    route_label = route_source = ""
    if cargo.get("route_id"):
        route = current_route(session, cargo["route_id"])
    speed = _assumed(reader, cargo, "speed_kn")
    kn = speed.value if speed.held else Decimal(17)
    ballast = cargo.get("ballast") or "round"
    if route is not None:
        voyage = Voyage(
            distance_nm=Decimal(str(route.distance_nm)),
            speed_laden_kn=kn,
            speed_ballast_kn=kn,
            ballast=ballast,
            routing=route.routing,
        )
        route_label = f"{route.load_port} -> {route.discharge_port} ({route.routing})"
        route_source = f"{route.source}, v{route.version}"
    elif cargo.get("distance_nm") is not None:
        voyage = Voyage(
            distance_nm=Decimal(str(cargo["distance_nm"])),
            speed_laden_kn=kn,
            speed_ballast_kn=kn,
            ballast=ballast,
        )
        voyage_class = InputClass.ASSUMPTION
        route_label = "Entered voyage"
        route_source = f"entered: {cargo['distance_nm']:g} nm at {kn:f} kn"
    elif cargo.get("laden_days") is not None:
        voyage = Voyage(
            distance_nm=Decimal(0),
            ballast=ballast,
            laden_days=Decimal(str(cargo["laden_days"])),
        )
        voyage_class = InputClass.ASSUMPTION
        route_label = "Entered voyage"
        route_source = f"entered: {cargo['laden_days']:g} days laden"
    elif cargo.get("standard"):
        voyage = Voyage(
            distance_nm=Decimal(STANDARD_DISTANCE_NM),
            speed_laden_kn=kn,
            speed_ballast_kn=kn,
            ballast=ballast,
        )
        voyage_class = InputClass.ASSUMPTION
        route_label = "Standard voyage, US Gulf to NW Europe"
        route_source = f"desk standard: {STANDARD_DISTANCE_NM} nm at {kn:f} kn"
    port = _assumed(reader, cargo, "port_cost")
    canal_entered = _entered(cargo.get("canal_cost"), "canal toll")
    if canal_entered is not None:
        canal = canal_entered
    elif route is not None and route.canal != "none":
        canal = missing(f"{route.canal} toll")
    else:
        canal = Valued(Decimal(0), InputClass.DERIVED, "no canal on this routing")
    fob = _entered(cargo.get("fob_price"), "FOB price")
    return CargoOffer(
        **common,
        hh=_hh(session, reader, pricing_month, cargo.get("hh")),
        slope=_assumed(reader, cargo, "slope"),
        fee=_assumed(reader, cargo, "fee"),
        fob_price=fob or missing(),
        voyage=voyage,
        route_label=route_label,
        route_source=route_source,
        voyage_class=voyage_class,
        hire_per_day=_assumed(reader, cargo, "hire_per_day"),
        boil_off_pct_per_day=_assumed(reader, cargo, "boil_off_pct_per_day"),
        ballast_fuel_mmbtu_per_day=_assumed(reader, cargo, "ballast_fuel_mmbtu_per_day"),
        canal=canal,
        port_load=port,
        port_discharge=port,
        insurance_pct=_assumed(reader, cargo, "insurance_pct"),
    )


def _shift(month: str, months: int) -> str:
    index = int(month[:4]) * 12 + int(month[5:7]) - 1 + months
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def _months_between(earlier: str, later: str) -> int:
    return (int(later[:4]) * 12 + int(later[5:7])) - (int(earlier[:4]) * 12 + int(earlier[5:7]))


def _voyage_payload(offer: CargoOffer, cargo: dict[str, Any]) -> dict[str, Any] | None:
    """How the voyage was stated: a saved route, or the desk's own figures."""

    if offer.term != "FOB":
        return None
    if offer.voyage is None:
        return {"basis": "none", "route_id": cargo.get("route_id")}
    basis = (
        "saved_route"
        if offer.voyage_class == InputClass.DERIVED
        else "entered_days"
        if offer.voyage.laden_days is not None
        else "standard"
        if offer.route_source.startswith("desk standard")
        else "entered_distance"
    )
    return {
        "basis": basis,
        "route_id": cargo.get("route_id") if basis == "saved_route" else None,
        "label": offer.route_label,
        "source": offer.route_source,
        "distance_nm": None if basis == "entered_days" else float(offer.voyage.distance_nm),
        "speed_kn": None if basis == "entered_days" else float(offer.voyage.speed_laden_kn),
        "ballast": offer.voyage.ballast,
    }


def _desk_reading(result, offer, options, evaluated, metas, reporting, cargo, request) -> None:
    """Add the desk's reading to one serialised cargo: units, the cost stack, the reason per
    terminal, the verdict and two-sided sensitivities (``lng_cargo_netback``)."""

    from eurogas_nexus.application import lng_cargo_netback as desk

    by_id = {option.terminal_id: option for option in options}
    stacks = {
        row.terminal_id: desk.cost_stack(
            evaluated, offer, by_id[row.terminal_id], row, metas.get(row.terminal_id, {})
        )
        for row in evaluated.terminals
        if row.terminal_id in by_id
    }
    why = desk.reasons(evaluated, stacks)
    for row in result["terminals"]:
        meta = metas.get(row["terminal_id"], {})
        row["cost_stack"] = stacks.get(row["terminal_id"])
        row["why"] = why.get(row["terminal_id"])
        row["hub_as_of"] = meta.get("hub_as_of")
        row["hub_licence_needed"] = meta.get("hub_licence_needed", False)
        row["excluded"] = meta.get("excluded", [])
        row["demo"] = meta.get("demo", False)
        row["published"] = meta.get("published")
        row["versions"] = meta.get("versions", {})
    code = request.get("reporting_currency") or "EUR"
    result["verdict"] = desk.verdict(evaluated, offer, stacks, code, reporting is not None)
    _per_mwh, _currency, how = desk.des_per_mwh(cargo) if offer.term == "DES" else (None, "", None)
    result["units"] = desk.units(evaluated, how)
    eua = next((meta["eua"] for meta in metas.values() if meta.get("eua")), None)
    result["eua"] = eua
    result["sensitivity"] = desk.sensitivity(
        offer,
        options,
        evaluated,
        reporting=reporting,
        eua_eur_t=None if eua is None else Decimal(str(eua["eur_t"])),
    )


def _price_one(session, reader, request, terminals, cargo, arrival, *, full=False):
    pricing = cargo.get("pricing_month") or arrival
    offer = _offer(session, reader, cargo, pricing)
    # The regas charge is on the energy unloaded: price the voyage first.
    cost_side = evaluate_cargo(offer, [])
    q_del_mwh = float(cost_side.q_del_mwh) if cost_side.q_del_mwh else 0.0
    priced = (
        [
            _option(
                session,
                reader,
                terminal,
                request={**request, "arrival_month": arrival},
                q_del_mwh=q_del_mwh,
                offer=offer,
                cost_side=cost_side,
                cargo=cargo,
            )
            for terminal in terminals
        ]
        if cost_side.blocked is None and q_del_mwh > 0
        else []
    )
    options = [option for option, _meta in priced]
    metas = {option.terminal_id: meta for option, meta in priced}
    # Terminals in several currencies rank in the reporting currency at the arrival month's FX.
    reporting = None
    code = request.get("reporting_currency") or "EUR"
    if len({option.currency for option in options}) > 1:
        rate = (
            Valued(Decimal(1), InputClass.SOURCED, "USD")
            if code == "USD"
            else _valued(reader.fx(code, "USD", _month(arrival)))
        )
        if rate.held:
            reporting = (code, rate.value)
    evaluated = evaluate_cargo(offer, options, reporting=reporting)
    if full:
        return offer, options, evaluated, metas, reporting
    return offer, options, evaluated


def _series(session, reader, request, terminals, cargo, terminal_id, months):
    """Design C.4 as a line: the delivered spread by arrival month, the same chain each month,
    freight and fees held at the request's figures; the pricing month keeps its lag."""

    arrival = request["arrival_month"]
    lag = _months_between(cargo.get("pricing_month") or arrival, arrival)
    wanted = [terminal for terminal in terminals if terminal.terminal_id == terminal_id]
    points = []
    for step in range(months):
        month = _shift(arrival, step)
        moved = {**cargo, "pricing_month": _shift(month, -lag)}
        _offer_, _options, result = _price_one(session, reader, request, wanted, moved, month)
        row = result.terminals[0] if result.terminals else None
        hh = next((leg for leg in result.legs if leg.key == "hh"), None)
        priced = row is not None and row.reason is None and row.arb_per_mwh is not None
        points.append(
            {
                "arrival_month": month,
                "pricing_month": moved["pricing_month"],
                "reason": result.blocked or (row.reason if row is not None else "no_terminal"),
                "hh": None if hh is None else float(hh.amount),
                "hh_class": None if hh is None else str(hh.input_class),
                "hub_per_mwh": float(row.delivered_per_mwh + row.arb_per_mwh) if priced else None,
                "delivered_per_mwh": float(row.delivered_per_mwh.quantize(Decimal("0.0001")))
                if priced
                else None,
                "arb_per_mwh": float(row.arb_per_mwh.quantize(Decimal("0.0001")))
                if priced
                else None,
                "grade": str(row.grade) if priced else "missing",
            }
        )
        if priced:
            points[-1]["reason"] = None
    return {"terminal_id": terminal_id, "cargo_id": cargo["cargo_id"], "points": points}


def _hub_closes(
    caller, hub: str, since: date, *, demo_desk: bool
) -> dict[date, tuple[float, bool]]:
    """The hub's front-month close per trade date, per MWh in its currency: a provider's
    series wins over a simulated one; simulated closes only on a demo desk."""

    from eurogas_nexus.application.projections.daily_closes import daily_rows

    series: dict[tuple[str, bool], dict[date, float]] = {}
    for row in daily_rows(caller, since, datetime.now(UTC).date()):
        if row["hub"] != hub or row["tenor"] != "month-ahead" or row.get("price_mwh") is None:
            continue
        if row["simulated"] and not demo_desk:
            continue
        series.setdefault((row["source_system"], bool(row["simulated"])), {})[row["day"]] = row[
            "price_mwh"
        ]
    if not series:
        return {}
    (_source, simulated), closes = max(
        series.items(), key=lambda item: (not item[0][1], len(item[1]))
    )
    return {day: (price, simulated) for day, price in closes.items()}


def _history(session, reader, caller, offer: CargoOffer, option: TerminalOption, days: int):
    """Design C.4 as a daily line: Henry Hub against the hub, the same chain each trade date.

    Henry Hub is that day's spot (EIA; the demo's simulated series on a demo desk), the hub
    its front-month close that day; freight, fees, regas and FX are held at the request's
    figures, so the line moves with the two prices only. Days with only one price are skipped.
    """

    from dataclasses import replace

    since = datetime.now(UTC).date() - timedelta(days=days)
    hh_rows = {
        row.period_start_utc.date(): row
        for row in _hh_spot_rows(session, demo_desk=reader.demo_desk, since=since)
    }
    closes = _hub_closes(caller, option.hub, since, demo_desk=reader.demo_desk)
    points = []
    for day in sorted(set(hh_rows) & set(closes)):
        hh_row = hh_rows[day]
        hub_price, hub_simulated = closes[day]
        klass, text = _hh_label(hh_row)
        moved_offer = replace(
            offer, fob_price=missing(), hh=Valued(Decimal(str(hh_row.price)), klass, text)
        )
        moved_option = replace(
            option,
            hub_price=Valued(
                Decimal(str(hub_price)),
                InputClass.SIMULATED if hub_simulated else InputClass.INDICATIVE,
                f"{option.hub} front month {day.isoformat()}",
            ),
            hub_price_before=None,
            hub_price_after=None,
        )
        result = evaluate_cargo(moved_offer, [moved_option])
        row = result.terminals[0] if result.terminals else None
        if row is None or row.arb_per_mwh is None:
            continue
        points.append(
            {
                "day": day.isoformat(),
                "hh": float(hh_row.price),
                "hub_per_mwh": round(hub_price, 4),
                "delivered_per_mwh": float(row.delivered_per_mwh.quantize(Decimal("0.0001"))),
                "arb_per_mwh": float(row.arb_per_mwh.quantize(Decimal("0.0001"))),
                "simulated": klass == InputClass.SIMULATED or hub_simulated,
            }
        )
    hh_sources = {row.source_system for row in hh_rows.values()}
    return {
        "terminal_id": option.terminal_id,
        "hub": option.hub,
        "currency": option.currency,
        "fx": option.fx_usd_per_unit.source if option.fx_usd_per_unit.held else "",
        "hh_source": "EIA" if hh_sources == {"EIA"} else "demo" if hh_sources else None,
        "hh_days": len(hh_rows),
        "points": points,
    }


def cargo_economics(session, request: dict[str, Any], *, caller) -> dict[str, Any]:
    """One result per cargo, each with its terminals best first; the comparison table; for the
    first FOB cargo, optionally, the delivered spread by arrival month."""

    from eurogas_nexus.application.valuation_snapshot import open_valuation_snapshot

    arrival = request["arrival_month"]
    if date(int(arrival[:4]), int(arrival[5:7]), 1) < datetime.now(UTC).date().replace(day=1):
        raise CargoEconomicsError("arrival_in_the_past", "The arrival month has passed.")
    # FX for the arrival month: the snapshot's own forward (valuation_snapshot.ForwardFx, CP-01:
    # licensed, else interest parity), stated per month; the spot rate only as its labelled
    # fallback.
    reader = open_valuation_snapshot(
        session,
        caller=caller,
        assumption_set_id=request.get("assumption_set_id") or None,
    )
    terminals = _terminals(session, list(request.get("terminal_ids") or []), study=True)
    results = []
    series = history = None
    for cargo in request["cargoes"]:
        offer, options, evaluated, metas, reporting = _price_one(
            session, reader, request, terminals, cargo, arrival, full=True
        )
        result = serialise(evaluated)
        result["voyage"] = _voyage_payload(offer, cargo)
        _desk_reading(result, offer, options, evaluated, metas, reporting, cargo, request)
        results.append(result)
        history_days = int(request.get("history_days") or 0)
        if (
            history is None
            and history_days
            and offer.term == "FOB"
            and evaluated.blocked is None
            and not offer.fob_price.held
        ):
            wanted = request.get("series_terminal_id") or evaluated.best_terminal_id
            chosen = next((o for o in options if o.terminal_id == wanted), None)
            if chosen is not None:
                history = _history(session, reader, caller, offer, chosen, history_days)
        months = int(request.get("series_months") or 0)
        if series is None and months and offer.term == "FOB" and evaluated.blocked is None:
            wanted = request.get("series_terminal_id") or evaluated.best_terminal_id
            if wanted:
                series = _series(session, reader, request, terminals, cargo, wanted, months)
    table = []
    for result in results:
        best = next(
            (
                row
                for row in result["terminals"]
                if row["terminal_id"] == result["best_terminal_id"]
            ),
            None,
        )
        table.append(
            {
                "cargo_id": result["cargo_id"],
                "label": result["label"],
                "term": result["term"],
                "arrives": arrival,
                "blocked": result["blocked"],
                "cost_per_mwh": best["cost_per_mwh"] if best else None,
                "best_terminal": best["name"] if best else None,
                "netback_per_mwh": best["netback_per_mwh"] if best else None,
                "margin_per_mwh": best["margin_per_mwh"] if best else None,
                "lifting_margin_per_mwh": best["lifting_margin_per_mwh"] if best else None,
                "currency": best["currency"] if best else None,
                "no_winner": result["no_winner"],
                "grade": result["grade"],
                "assumptions": result["assumptions"],
            }
        )
    return {
        "arrival_month": arrival,
        "fx_method": reader.fx_method,
        "cargoes": results,
        "table": table,
        "terminals_considered": [terminal.terminal_id for terminal in terminals],
        "delivered_spread_series": series,
        "delivered_spread_history": history,
        "reporting_currency": request.get("reporting_currency") or "EUR",
        "assumption_version": reader.assumption_version,
    }


# ------------------------------------------------------------------ for the regas auction desk


def terminal_choices(session) -> list[dict[str, Any]]:
    """Every terminal the firm's terms, the tariff register or the published tariffs name, for
    a picker: id, name, hub and whether a regas figure can be read for it (demo terms only on a
    demo desk, never as a default)."""

    out = []
    for terminal in _terminals(session, [], study=True):
        published = terminal.published
        out.append(
            {
                "terminal_id": terminal.terminal_id,
                "name": terminal.name,
                "hub": terminal.hub,
                "operator": getattr(published, "operator", None),
                "country": getattr(published, "country", None),
                "link_only": bool(published is not None and published.permission_operator),
                "firm_terms": terminal.gik_from == "firm",
            }
        )
    return out


def terminal_charges(session, reader, terminal_id: str, *, arrival_month: str,
                     energy_mwh: float):
    """The desk engine's own terminal figures for one slot: regas charge (a total), entry
    tariff and gas in kind, each with its class and source, and the further published costs
    (``_option``); ``None`` when the terminal is in no register."""

    found = _terminals(session, [terminal_id], study=True)
    if not found:
        return None
    return _option(
        session,
        reader,
        found[0],
        request={"arrival_month": arrival_month, "product": "spot"},
        q_del_mwh=energy_mwh,
    )
