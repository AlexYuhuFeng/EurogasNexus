"""Cargo economics for the desk: one table for FOB and DES cargoes (CP-12, design C.1-C.3).

Reads every input through the valuation snapshot (``application/valuation_snapshot.py``) or
the LNG reference registers, never guesses one, and hands the pure chain
(``domain/lng/cargo_economics.py``) values that each carry their class and source:

* hub price for the arrival month: ``reader.price(hub, month)`` (licensed quote, settlement,
  the firm's mark; demo price only on a demo desk);
* FX for the arrival month: ``reader.fx(hub currency, USD, month)``;
* Henry Hub for the pricing month: ``reader.price("HH", month)``; else the latest EIA daily spot
  as a flat proxy, class ``indicative`` and labelled "spot proxy" (EIA stopped publishing
  futures settlements on 5 April 2024; a forward comes from the customer's entitlement or the
  firm's mark);
* assumptions (charter hire, boil-off, speed, ballast fuel, insurance, port costs, the FOB
  formula, cargo size): what the request states (class ``assumption``, "entered"), else the
  firm's approved assumption set, else missing;
* route distance: ``freight_route`` (latest version);
* regas charge: the firm's terms, the reviewed public tariff, a candidate (indicative)
  (``application/lng_terminal_tariff_register.py``); gas in kind and entry tariff from the
  firm's terms, the register's in-kind figure, or the request.

Nothing is offered, nominated or sent: this prices cargoes for the desk to decide.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
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
from eurogas_nexus.domain.valuation.quality import InputClass

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


def record_route(session, route_id: str, values: dict[str, Any], *, actor: str) -> dict[str, Any]:
    """Add a version of one route (never overwrites); audited."""

    from eurogas_nexus.db.models import FreightRouteRecord
    from eurogas_nexus.db.repositories.audit import record_audit_event

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
    )
    session.add(row)
    session.flush()
    record_audit_event(
        session,
        event_type="reference_data",
        principal=actor,
        action="lng.freight_route",
        resource=f"freight_route:{route_id}",
        detail=f"version {row.version}",
    )
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


def _assumed(reader, cargo: dict[str, Any], field: str) -> Valued:
    entered = _entered(cargo.get(field), field)
    if entered is not None:
        return entered
    return _valued(reader.assumption(ASSUMPTION_KEYS[field]))


def _month(text: str) -> DeliveryPeriod:
    return DeliveryPeriod.month(int(text[:4]), int(text[5:7]))


def _hh(session, reader, pricing_month: str, entered: float | None) -> Valued:
    if entered is not None:
        return Valued(Decimal(str(entered)), InputClass.ASSUMPTION, "entered: Henry Hub")
    forward = reader.price("HH", _month(pricing_month))
    if forward.held:
        return _valued(forward)
    from eurogas_nexus.db.models import MarketObservationRecord

    row = (
        session.query(MarketObservationRecord)
        .filter(MarketObservationRecord.source_system == "EIA")
        .filter(MarketObservationRecord.product == "HH spot")
        .order_by(MarketObservationRecord.period_start_utc.desc())
        .first()
    )
    if row is None:
        return missing("Henry Hub: no forward or spot held")
    day = row.period_start_utc.date().isoformat()
    return Valued(
        Decimal(str(row.price)),
        InputClass.INDICATIVE,
        f"Henry Hub spot {day} (EIA), spot proxy for {pricing_month}",
    )


@dataclass(frozen=True)
class _Terminal:
    terminal_id: str
    name: str
    hub: str
    gas_in_kind_pct: float | None
    entry_per_mwh: float | None
    excludes: tuple[str, ...]


def _terminals(session, wanted: list[str]) -> list[_Terminal]:
    from eurogas_nexus.db.models import LngTerminalTariffRecord, LngTerminalTermsRecord

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
            found[row.terminal_id] = _Terminal(**{**held.__dict__, "gas_in_kind_pct": in_kind})
    if wanted:
        return [found[key] for key in wanted if key in found]
    return [found[key] for key in sorted(found)]


def _hub_currency(hub: str) -> str:
    from eurogas_nexus.domain.ontology.markets import find_market

    market = find_market(hub)
    return getattr(market, "currency", None) or ("GBP" if hub == "NBP" else "EUR")


def _option(session, reader, terminal: _Terminal, *, request: dict[str, Any], q_del_mwh: float):
    from eurogas_nexus.application import lng_terminal_tariff_register as register

    month = request["arrival_month"]
    period = _month(month)
    currency = _hub_currency(terminal.hub)
    price = reader.price(terminal.hub, period)
    before = after = None
    for shift, slot in ((-1, "before"), (1, "after")):
        year, number = period.start.year, period.start.month + shift
        year, number = (
            (year - 1, 12)
            if number == 0
            else (year + 1, 1)
            if number == 13
            else (
                year,
                number,
            )
        )
        other = reader.price(terminal.hub, DeliveryPeriod.month(year, number))
        if other.held:
            if slot == "before":
                before = other.value
            else:
                after = other.value
    charge = register.price_terminal(
        session,
        terminal.terminal_id,
        arrival_month=month,
        cargo_mwh=q_del_mwh,
        product=request.get("product", "spot"),
    )
    if charge.charge is None:
        regas = missing(charge.reason or "no tariff")
    else:
        klass = {
            "firm_terms": InputClass.FIRM_MARK,
            "reviewed_public": InputClass.SOURCED,
            "candidate_public": InputClass.INDICATIVE,
        }[charge.basis]
        regas = Valued(Decimal(str(charge.charge)), klass, charge.basis)
    overrides = (request.get("terminal_inputs") or {}).get(terminal.terminal_id, {})
    entry = _entered(overrides.get("entry_per_mwh"), "entry tariff") or (
        Valued(Decimal(str(terminal.entry_per_mwh)), InputClass.FIRM_MARK, "your terminal terms")
        if terminal.entry_per_mwh is not None
        else missing("entry tariff")
    )
    gik = _entered(overrides.get("gas_in_kind_pct"), "gas in kind") or (
        Valued(Decimal(str(terminal.gas_in_kind_pct)), InputClass.SOURCED, "tariff register")
        if terminal.gas_in_kind_pct is not None
        else missing("gas in kind")
    )
    fx = reader.fx(currency, "USD", period) if currency != "USD" else None
    return TerminalOption(
        terminal_id=terminal.terminal_id,
        name=terminal.name,
        hub=terminal.hub,
        currency=currency,
        arrival_month=month,
        hub_price=_valued(price),
        entry=entry,
        gas_in_kind_pct=gik,
        regas_total=regas,
        regas_basis=charge.basis,
        fx_usd_per_unit=Valued(Decimal(1), InputClass.SOURCED, "USD")
        if fx is None
        else _valued(fx),
        hub_price_before=before,
        hub_price_after=after,
        excludes=tuple(charge.excludes) or terminal.excludes,
    )


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
        return CargoOffer(
            **common,
            des_price=_entered(cargo.get("des_price"), "DES price") or missing("DES price"),
            des_currency=cargo.get("des_currency") or "EUR",
        )
    voyage = route = None
    if cargo.get("route_id"):
        route = current_route(session, cargo["route_id"])
    speed = _assumed(reader, cargo, "speed_kn")
    if route is not None:
        kn = speed.value if speed.held else Decimal(17)
        voyage = Voyage(
            distance_nm=Decimal(str(route.distance_nm)),
            speed_laden_kn=kn,
            speed_ballast_kn=kn,
            ballast=cargo.get("ballast") or "round",
            routing=route.routing,
        )
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
        route_label=(
            f"{route.load_port} -> {route.discharge_port} ({route.routing})" if route else ""
        ),
        route_source=(f"{route.source}, v{route.version}" if route else ""),
        hire_per_day=_assumed(reader, cargo, "hire_per_day"),
        boil_off_pct_per_day=_assumed(reader, cargo, "boil_off_pct_per_day"),
        ballast_fuel_mmbtu_per_day=_assumed(reader, cargo, "ballast_fuel_mmbtu_per_day"),
        canal=canal,
        port_load=port,
        port_discharge=port,
        insurance_pct=_assumed(reader, cargo, "insurance_pct"),
    )


def cargo_economics(session, request: dict[str, Any], *, caller) -> dict[str, Any]:
    """One result per cargo, each with its terminals best first; the comparison table."""

    from eurogas_nexus.application.valuation_snapshot import open_valuation_snapshot

    arrival = request["arrival_month"]
    if date(int(arrival[:4]), int(arrival[5:7]), 1) < datetime.now(UTC).date().replace(day=1):
        raise CargoEconomicsError("arrival_in_the_past", "The arrival month has passed.")
    reader = open_valuation_snapshot(session, caller=caller)
    terminals = _terminals(session, list(request.get("terminal_ids") or []))
    results = []
    for cargo in request["cargoes"]:
        pricing = cargo.get("pricing_month") or arrival
        offer = _offer(session, reader, cargo, pricing)
        # The regas charge is on the energy unloaded: price the voyage first.
        cost_side = evaluate_cargo(offer, [])
        q_del_mwh = float(cost_side.q_del_mwh) if cost_side.q_del_mwh else 0.0
        options = (
            [
                _option(session, reader, terminal, request=request, q_del_mwh=q_del_mwh)
                for terminal in terminals
            ]
            if cost_side.blocked is None and q_del_mwh > 0
            else []
        )
        results.append(serialise(evaluate_cargo(offer, options)))
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
    }
