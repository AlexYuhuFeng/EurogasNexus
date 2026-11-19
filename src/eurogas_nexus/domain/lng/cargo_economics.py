"""The full LNG cargo chain: cost at the ship's rail, netback per terminal, margin (CP-12).

Design C.1. Energy and money are carried as totals and divided at the end, so denominators
are never mixed. Per-unit results are per MMBtu (or per MWh) **delivered at the ship's rail at
discharge**::

    Q_del     = Q_load x (1 - bor x d_laden) - heel_delta
    FOB cost  = P_FOB x Q_load,   P_FOB = a x HH + b (or a fixed FOB price)
    Freight   = hire x (d_laden + d_ballast + d_port) + ballast fuel + canal + ports + insurance
    cost at the ship's rail (DES-equivalent) = (FOB cost + Freight) / Q_del
    sent_out  = Q_del x (1 - gas in kind)
    netback   = [sent_out x (P_hub - entry) - regas charge - other] / Q_del
    margin    = netback - cost at the ship's rail       (hub currency per MWh delivered)

A DES cargo skips the voyage: its cost at the ship's rail is the DES price. Two cost bases are
shown for an FOB cargo with a formula: the **full cost** (a x HH + b) and the **lifting cost**
(a x HH; the fee is sunk for an offtaker with a take-or-pay contract, and decides whether to
lift or cancel).

Every input carries its class (``domain/valuation/quality.py``) and its source text; the
result's class is the weakest on its value path, and it counts the assumptions it rests on.
A missing input is never zero: the cargo, or the terminal, is left out with the reason
(``no_charter_hire`` blocks an FOB cargo; ``no_distance`` names the route). The hub price is
in the terminal hub's currency per MWh (a p/th mark is normalised before it reaches here).

Henry Hub versus the hub at the same delivery point (design C.4) is the same margin read two
ways, both on every FOB row: **delivered** (what the US cargo costs at the hub, per MWh sent
out: ``(cost + regas) / (1 - gas in kind) + entry``, against the hub price) and **netback** (what
the hub is worth FOB, USD/MMBtu loaded: ``FOB price + margin total / Q_load``, against the FOB
price). Both times their volume give the row's margin total, so they agree to rounding.

Pure, Decimal, deterministic. Money is rounded to the cent and per-unit figures to four
decimals only in :func:`serialise`.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from eurogas_nexus.domain.lng.voyage import (
    FreightCosts,
    Voyage,
    VoyageDays,
    boil_off_mmbtu,
    freight_costs,
    voyage_days,
)
from eurogas_nexus.domain.ontology.quantity import convert as _convert_units
from eurogas_nexus.domain.valuation.quality import InputClass, weakest

#: From the ontology's unit table, the one place a conversion factor is written.
MMBTU_PER_MWH = Decimal(str(_convert_units(1.0, "MWh", "MMBtu")))
_CENT = Decimal("0.01")
_UNIT = Decimal("0.0001")
_STEP = Decimal("0.00000001")
_HUNDRED = Decimal(100)
#: Two terminals closer than this (hub currency per MWh) are not ranked against each other.
DEFAULT_TIE_TOLERANCE = Decimal("0.10")


@dataclass(frozen=True)
class Valued:
    """One input: its value (None = not held), class and where it came from."""

    value: Decimal | None
    input_class: InputClass = InputClass.ASSUMPTION
    source: str = ""

    @property
    def held(self) -> bool:
        return self.value is not None and self.input_class != InputClass.MISSING


def missing(source: str = "") -> Valued:
    return Valued(None, InputClass.MISSING, source)


@dataclass(frozen=True)
class CargoOffer:
    """One cargo the desk could buy: FOB (own shipping) or DES."""

    cargo_id: str
    label: str
    term: str  # FOB | DES
    q_load_mmbtu: Valued
    purchase_currency: str = "USD"
    # FOB: a x HH + b, or a fixed FOB price (USD/MMBtu).
    hh: Valued = field(default_factory=missing)
    slope: Valued = field(default_factory=missing)
    fee: Valued = field(default_factory=missing)
    fob_price: Valued = field(default_factory=missing)
    # DES: the price at the ship's rail, in the hub currency per MWh.
    des_price: Valued = field(default_factory=missing)
    des_currency: str = "EUR"
    # Voyage (FOB only).
    voyage: Voyage | None = None
    route_label: str = ""
    route_source: str = ""
    #: A held route is a fact the firm recorded (derived); a voyage the desk types is an assumption.
    voyage_class: InputClass = InputClass.DERIVED
    hire_per_day: Valued = field(default_factory=missing)
    boil_off_pct_per_day: Valued = field(default_factory=missing)
    ballast_fuel_mmbtu_per_day: Valued = field(default_factory=missing)
    canal: Valued = field(
        default_factory=lambda: Valued(Decimal(0), InputClass.DERIVED, "no canal")
    )
    port_load: Valued = field(default_factory=missing)
    port_discharge: Valued = field(default_factory=missing)
    insurance_pct: Valued = field(default_factory=missing)
    heel_delta_mmbtu: Decimal = Decimal(0)


@dataclass(frozen=True)
class TerminalOption:
    """One terminal the cargo could discharge at, for one arrival month."""

    terminal_id: str
    name: str
    hub: str
    currency: str
    arrival_month: str
    hub_price: Valued
    entry: Valued
    gas_in_kind_pct: Valued
    #: The regas charge for this cargo, a total in the hub currency, and its basis
    #: (firm_terms, reviewed_public, candidate_public).
    regas_total: Valued
    regas_basis: str = ""
    #: USD per one unit of the hub currency for the arrival month (EUR/USD 1.16 -> 1.16).
    fx_usd_per_unit: Valued = field(default_factory=missing)
    other_total: Decimal = Decimal(0)
    hub_price_before: Decimal | None = None
    hub_price_after: Decimal | None = None
    excludes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Leg:
    """One row of the arithmetic."""

    key: str
    label: str
    amount: Decimal
    unit: str
    input_class: InputClass
    source: str = ""


@dataclass(frozen=True)
class TerminalResult:
    terminal_id: str
    name: str
    hub: str
    currency: str
    arrival_month: str
    reason: str | None = None
    cost_per_mwh: Decimal | None = None
    netback_per_mwh: Decimal | None = None
    margin_per_mwh: Decimal | None = None
    margin_usd_mmbtu: Decimal | None = None
    margin_total: Decimal | None = None
    lifting_margin_per_mwh: Decimal | None = None
    margin_low_per_mwh: Decimal | None = None
    margin_high_per_mwh: Decimal | None = None
    regas_basis: str = ""
    legs: tuple[Leg, ...] = ()
    grade: InputClass = InputClass.MISSING
    assumptions: int = 0
    excludes: tuple[str, ...] = ()
    #: USD per one unit of the hub currency used for this row (None for a DES row without FX).
    fx_usd_per_unit: Decimal | None = None
    fx_source: str = ""
    #: The margin step by step, hub currency per MWh delivered: (key, amount, kind).
    steps: tuple[tuple[str, Decimal, str], ...] = ()
    #: Design C.4, FOB only: the delivered view (hub currency per MWh sent out) ...
    delivered_per_mwh: Decimal | None = None
    arb_per_mwh: Decimal | None = None
    sent_out_mwh: Decimal | None = None
    # ... and the netback view (USD/MMBtu loaded).
    fob_netback_usd_mmbtu: Decimal | None = None
    #: The margin in the reporting currency per MWh delivered, when terminals in several
    #: currencies are ranked together (``evaluate_cargo(..., reporting=...)``).
    margin_reporting_per_mwh: Decimal | None = None


_BASE_KEYS = (
    "terminal_id",
    "name",
    "hub",
    "currency",
    "arrival_month",
    "regas_basis",
    "excludes",
)


@dataclass(frozen=True)
class CargoResult:
    cargo_id: str
    label: str
    term: str
    blocked: str | None
    q_load_mmbtu: Decimal | None = None
    q_del_mmbtu: Decimal | None = None
    q_del_mwh: Decimal | None = None
    fob_price: Decimal | None = None
    lifting_price: Decimal | None = None
    cost_usd_mmbtu: Decimal | None = None
    lifting_cost_usd_mmbtu: Decimal | None = None
    freight: FreightCosts | None = None
    days: VoyageDays | None = None
    legs: tuple[Leg, ...] = ()
    terminals: tuple[TerminalResult, ...] = ()
    best_terminal_id: str | None = None
    no_winner: bool = False
    grade: InputClass = InputClass.MISSING
    assumptions: int = 0


def _blocked(offer: CargoOffer, reason: str) -> CargoResult:
    return CargoResult(offer.cargo_id, offer.label, offer.term, reason)


def _leg(key: str, label: str, amount: Decimal, unit: str, src: Valued) -> Leg:
    return Leg(key, label, amount, unit, src.input_class, src.source)


def _cost_side(offer: CargoOffer) -> CargoResult:
    """The cost at the ship's rail of one FOB cargo (USD), or the reason it cannot be had."""

    if not offer.q_load_mmbtu.held:
        return _blocked(offer, "no_cargo_size")
    q_load = offer.q_load_mmbtu.value
    assert q_load is not None
    if q_load <= 0:
        return _blocked(offer, "no_cargo_size")
    inputs: list[Valued] = [offer.q_load_mmbtu]
    legs: list[Leg] = []
    if offer.fob_price.held:
        price = offer.fob_price.value
        lifting = price
        inputs.append(offer.fob_price)
        legs.append(_leg("fob_price", "FOB price", price, "USD/MMBtu", offer.fob_price))
    else:
        if not offer.hh.held:
            return _blocked(offer, "no_hh_price")
        if not offer.slope.held or not offer.fee.held:
            return _blocked(offer, "no_fob_formula")
        lifting = offer.slope.value * offer.hh.value
        price = lifting + offer.fee.value
        inputs += [offer.hh, offer.slope, offer.fee]
        legs += [
            _leg("hh", "Henry Hub, pricing month", offer.hh.value, "USD/MMBtu", offer.hh),
            _leg("slope", "Formula slope", offer.slope.value, "x HH", offer.slope),
            _leg(
                "fee",
                "Formula constant (liquefaction fee)",
                offer.fee.value,
                "USD/MMBtu",
                offer.fee,
            ),
            Leg(
                "fob_price",
                "FOB price",
                price,
                "USD/MMBtu",
                weakest(i.input_class for i in inputs[1:]),
            ),
        ]
    if offer.voyage is None:
        return _blocked(offer, "no_distance")
    if not offer.hire_per_day.held:
        return _blocked(offer, "no_charter_hire")
    for name in (
        "boil_off_pct_per_day",
        "ballast_fuel_mmbtu_per_day",
        "port_load",
        "port_discharge",
        "insurance_pct",
        "canal",
    ):
        if not getattr(offer, name).held:
            return _blocked(offer, f"no_{name}")
    days = voyage_days(offer.voyage)
    fob_cost = price * q_load
    lost = boil_off_mmbtu(q_load, offer.boil_off_pct_per_day.value, days.laden)
    q_del = q_load - lost - offer.heel_delta_mmbtu
    freight = freight_costs(
        days,
        hire_per_day=offer.hire_per_day.value,
        ballast_fuel_mmbtu_per_day=offer.ballast_fuel_mmbtu_per_day.value,
        fuel_price_per_mmbtu=price,
        canal=offer.canal.value,
        port_load=offer.port_load.value,
        port_discharge=offer.port_discharge.value,
        insurance_pct=offer.insurance_pct.value,
        cargo_value=fob_cost,
    )
    voyage_src = Valued(offer.voyage.distance_nm, offer.voyage_class, offer.route_source)
    entered_days = offer.voyage.laden_days is not None
    inputs += [
        voyage_src,
        offer.hire_per_day,
        offer.boil_off_pct_per_day,
        offer.ballast_fuel_mmbtu_per_day,
        offer.canal,
        offer.port_load,
        offer.port_discharge,
        offer.insurance_pct,
    ]
    legs += [
        _leg("fob_cost", "FOB cost", fob_cost, "USD", offer.q_load_mmbtu),
        *(
            ()
            if entered_days
            else (
                _leg(
                    "distance",
                    offer.route_label or "Route distance",
                    offer.voyage.distance_nm,
                    "nm",
                    voyage_src,
                ),
            )
        ),
        Leg(
            "days",
            "Days laden / ballast / port",
            days.total,
            "days",
            offer.voyage_class if entered_days else InputClass.DERIVED,
            f"{days.laden} / {days.ballast} / {days.port}",
        ),
        _leg("boil_off", "Boil-off", lost, "MMBtu", offer.boil_off_pct_per_day),
        Leg("delivered", "Delivered", q_del, "MMBtu", InputClass.DERIVED, ""),
        _leg("hire", "Charter hire", freight.hire, "USD", offer.hire_per_day),
        _leg(
            "ballast_fuel",
            "Ballast fuel",
            freight.ballast_fuel,
            "USD",
            offer.ballast_fuel_mmbtu_per_day,
        ),
        _leg("canal", "Canal", freight.canal, "USD", offer.canal),
        _leg(
            "ports",
            "Port costs",
            freight.port_load + freight.port_discharge,
            "USD",
            offer.port_load,
        ),
        _leg("insurance", "Insurance", freight.insurance, "USD", offer.insurance_pct),
        Leg("freight", "Freight total", freight.total, "USD", InputClass.DERIVED, ""),
    ]
    cost = (fob_cost + freight.total) / q_del
    lifting_cost = cost - (price - lifting) * q_load / q_del
    legs.append(Leg("cost", "Cost at the ship's rail", cost, "USD/MMBtu", InputClass.DERIVED, ""))
    classes = [i.input_class for i in inputs]
    return CargoResult(
        offer.cargo_id,
        offer.label,
        offer.term,
        None,
        q_load_mmbtu=q_load,
        q_del_mmbtu=q_del,
        q_del_mwh=q_del / MMBTU_PER_MWH,
        fob_price=price,
        lifting_price=lifting,
        cost_usd_mmbtu=cost,
        lifting_cost_usd_mmbtu=lifting_cost,
        freight=freight,
        days=days,
        legs=tuple(legs),
        grade=weakest(classes),
        assumptions=sum(c == InputClass.ASSUMPTION for c in classes),
    )


def _terminal(cargo: CargoResult, offer: CargoOffer, option: TerminalOption) -> TerminalResult:
    base = {
        "terminal_id": option.terminal_id,
        "name": option.name,
        "hub": option.hub,
        "currency": option.currency,
        "arrival_month": option.arrival_month,
        "regas_basis": option.regas_basis,
        "excludes": option.excludes,
    }
    for key, value in (
        ("no_hub_price", option.hub_price),
        ("no_entry_tariff", option.entry),
        ("no_gas_in_kind", option.gas_in_kind_pct),
        ("no_regas_tariff", option.regas_total),
    ):
        if not value.held:
            return TerminalResult(**base, reason=key)
    if offer.term == "DES" and offer.des_currency != option.currency:
        return TerminalResult(**base, reason="currency_mismatch")
    fx_needed = offer.term == "FOB"
    if fx_needed and not option.fx_usd_per_unit.held:
        return TerminalResult(**base, reason="no_fx")
    inputs = [option.hub_price, option.entry, option.gas_in_kind_pct, option.regas_total]
    q_del_mwh = cargo.q_del_mwh
    if offer.term == "FOB":
        fx = option.fx_usd_per_unit.value
        inputs.append(option.fx_usd_per_unit)
        cost = cargo.cost_usd_mmbtu * MMBTU_PER_MWH / fx
        lifting_cost = cargo.lifting_cost_usd_mmbtu * MMBTU_PER_MWH / fx
    else:
        cost = lifting_cost = offer.des_price.value
        fx = option.fx_usd_per_unit.value if option.fx_usd_per_unit.held else None
    keep = 1 - option.gas_in_kind_pct.value / _HUNDRED
    sent_out = q_del_mwh * keep

    def netback(hub_price: Decimal) -> Decimal:
        revenue = sent_out * (hub_price - option.entry.value)
        return (revenue - option.regas_total.value - option.other_total) / q_del_mwh

    value = netback(option.hub_price.value)
    margin = value - cost
    neighbours = [margin] + [
        netback(p) - cost
        for p in (option.hub_price_before, option.hub_price_after)
        if p is not None
    ]
    unit = f"{option.currency}/MWh"
    legs = (
        Leg("cost", "Cost at the ship's rail", cost, unit, cargo.grade, ""),
        _leg(
            "hub",
            f"{option.hub} {option.arrival_month}",
            option.hub_price.value,
            unit,
            option.hub_price,
        ),
        _leg("entry", "Entry tariff", option.entry.value, unit, option.entry),
        _leg(
            "gas_in_kind", "Gas in kind", option.gas_in_kind_pct.value, "%", option.gas_in_kind_pct
        ),
        _leg(
            "regas",
            "Regas charge",
            option.regas_total.value / q_del_mwh,
            unit,
            option.regas_total,
        ),
        Leg("netback", "Netback at the ship's rail", value, unit, InputClass.DERIVED, ""),
        Leg("margin", "Margin", margin, unit, InputClass.DERIVED, ""),
    )
    regas_per_mwh = option.regas_total.value / q_del_mwh
    hub_value = option.hub_price.value
    netback_steps: list[tuple[str, Decimal, str]] = [
        ("hub", hub_value, "total"),
        ("gas_in_kind", -hub_value * (1 - keep), "delta"),
        ("entry", -option.entry.value * keep, "delta"),
        ("regas", -regas_per_mwh, "delta"),
        ("netback", value, "total"),
    ]
    delivered = arb = fob_netback = None
    if offer.term == "FOB":
        to_hub = MMBTU_PER_MWH / fx
        fob_at_load = cargo.fob_price * to_hub
        fob_delivered = cargo.fob_price * cargo.q_load_mmbtu / cargo.q_del_mmbtu * to_hub
        freight_per = cargo.freight.total / cargo.q_del_mmbtu * to_hub
        cost_steps = [
            ("fob", -fob_at_load, "delta"),
            ("boil_off", -(fob_delivered - fob_at_load), "delta"),
            ("freight", -freight_per, "delta"),
        ]
        delivered = (cost + regas_per_mwh) / keep + option.entry.value
        arb = hub_value - delivered
        fob_netback = cargo.fob_price + margin * q_del_mwh * fx / cargo.q_load_mmbtu
    else:
        cost_steps = [("des", -cost, "delta")]
    steps = (*netback_steps, *cost_steps, ("margin", margin, "total"))
    classes = [cargo.grade, *(i.input_class for i in inputs)]
    return TerminalResult(
        **base,
        fx_usd_per_unit=fx,
        fx_source=option.fx_usd_per_unit.source if fx is not None else "",
        steps=steps,
        delivered_per_mwh=delivered,
        arb_per_mwh=arb,
        sent_out_mwh=sent_out,
        fob_netback_usd_mmbtu=fob_netback,
        cost_per_mwh=cost,
        netback_per_mwh=value,
        margin_per_mwh=margin,
        margin_usd_mmbtu=None if fx is None else margin * fx / MMBTU_PER_MWH,
        margin_total=margin * q_del_mwh,
        lifting_margin_per_mwh=value - lifting_cost,
        margin_low_per_mwh=min(neighbours),
        margin_high_per_mwh=max(neighbours),
        legs=legs,
        grade=weakest(classes),
        assumptions=cargo.assumptions + sum(i.input_class == InputClass.ASSUMPTION for i in inputs),
    )


def evaluate_cargo(
    offer: CargoOffer,
    terminals: Iterable[TerminalOption],
    *,
    tie_tolerance: Decimal = DEFAULT_TIE_TOLERANCE,
    reporting: tuple[str, Decimal] | None = None,
) -> CargoResult:
    """Cost, then one row per terminal, best margin first.

    Terminals priced in one currency rank by their margin per MWh. With ``reporting`` (the
    reporting currency and USD per one unit of it, e.g. ``("EUR", 1.09)``), terminals in
    several currencies rank by the margin in the reporting currency at that rate (each row's
    margin in USD/MMBtu brought to the reporting currency per MWh), and the tie tolerance is
    read in the reporting currency; without it they rank as before.
    """

    if offer.term not in {"FOB", "DES"}:
        raise ValueError("term is FOB or DES")
    if offer.term == "FOB":
        cargo = _cost_side(offer)
        if cargo.blocked:
            return cargo
    else:
        if not offer.q_load_mmbtu.held or offer.q_load_mmbtu.value <= 0:
            return _blocked(offer, "no_cargo_size")
        if not offer.des_price.held:
            return _blocked(offer, "no_des_price")
        q = offer.q_load_mmbtu.value - offer.heel_delta_mmbtu
        classes = [offer.q_load_mmbtu.input_class, offer.des_price.input_class]
        cargo = CargoResult(
            offer.cargo_id,
            offer.label,
            offer.term,
            None,
            q_load_mmbtu=offer.q_load_mmbtu.value,
            q_del_mmbtu=q,
            q_del_mwh=q / MMBTU_PER_MWH,
            legs=(
                _leg(
                    "des_price",
                    "DES price",
                    offer.des_price.value,
                    f"{offer.des_currency}/MWh",
                    offer.des_price,
                ),
            ),
            grade=weakest(classes),
            assumptions=sum(c == InputClass.ASSUMPTION for c in classes),
        )
    rows = [_terminal(cargo, offer, option) for option in terminals]
    currencies = {row.currency for row in rows if row.reason is None}
    if reporting is not None and len(currencies) > 1:
        code, usd_per_unit = reporting
        rows = [
            row
            if row.reason is not None
            else TerminalResult(
                **{
                    **row.__dict__,
                    "margin_reporting_per_mwh": row.margin_per_mwh
                    if row.currency == code
                    else None
                    if row.margin_usd_mmbtu is None
                    else row.margin_usd_mmbtu * MMBTU_PER_MWH / usd_per_unit,
                }
            )
            for row in rows
        ]
        rows = [
            row
            if row.reason is not None or row.margin_reporting_per_mwh is not None
            else TerminalResult(
                **{k: row.__dict__[k] for k in _BASE_KEYS},
                reason="no_fx",
            )
            for row in rows
        ]
        key = lambda row: row.margin_reporting_per_mwh  # noqa: E731
        comparable = True
    else:
        key = lambda row: row.margin_per_mwh  # noqa: E731
        comparable = False
    priced = sorted((row for row in rows if row.reason is None), key=key, reverse=True)
    left_out = [row for row in rows if row.reason is not None]
    best = priced[0] if priced else None
    no_winner = bool(
        len(priced) > 1
        and (comparable or priced[0].currency == priced[1].currency)
        and key(priced[0]) - key(priced[1]) < tie_tolerance
    )
    return CargoResult(
        **{
            **cargo.__dict__,
            "terminals": tuple(priced + left_out),
            "best_terminal_id": best.terminal_id if best else None,
            "no_winner": no_winner,
            "grade": weakest([cargo.grade, *(row.grade for row in priced)])
            if priced
            else cargo.grade,
        }
    )


def _money(value: Decimal | None) -> float | None:
    return None if value is None else float(value.quantize(_CENT, rounding=ROUND_HALF_UP))


def _unit(value: Decimal | None) -> float | None:
    return None if value is None else float(value.quantize(_UNIT, rounding=ROUND_HALF_UP))


def _leg_payload(leg: Leg) -> dict[str, object]:
    money = leg.unit in {"USD", "EUR", "GBP"}
    return {
        "key": leg.key,
        "label": leg.label,
        "amount": _money(leg.amount) if money else _unit(leg.amount),
        "unit": leg.unit,
        "input_class": str(leg.input_class),
        "source": leg.source,
    }


def serialise(result: CargoResult) -> dict[str, object]:
    """The API shape: money to the cent, per-unit figures to four decimals."""

    return {
        "cargo_id": result.cargo_id,
        "label": result.label,
        "term": result.term,
        "blocked": result.blocked,
        "q_load_mmbtu": _unit(result.q_load_mmbtu),
        "q_del_mmbtu": _unit(result.q_del_mmbtu),
        "q_del_mwh": _unit(result.q_del_mwh),
        "fob_price_usd_mmbtu": _unit(result.fob_price),
        "lifting_price_usd_mmbtu": _unit(result.lifting_price),
        "cost_usd_mmbtu": _unit(result.cost_usd_mmbtu),
        "lifting_cost_usd_mmbtu": _unit(result.lifting_cost_usd_mmbtu),
        "freight_usd": _money(result.freight.total) if result.freight else None,
        "days": None
        if result.days is None
        else {
            "laden": float(result.days.laden),
            "ballast": float(result.days.ballast),
            "port": float(result.days.port),
        },
        "legs": [_leg_payload(leg) for leg in result.legs],
        "terminals": [
            {
                "terminal_id": row.terminal_id,
                "name": row.name,
                "hub": row.hub,
                "currency": row.currency,
                "arrival_month": row.arrival_month,
                "reason": row.reason,
                "cost_per_mwh": _unit(row.cost_per_mwh),
                "netback_per_mwh": _unit(row.netback_per_mwh),
                "margin_per_mwh": _unit(row.margin_per_mwh),
                "margin_reporting_per_mwh": _unit(row.margin_reporting_per_mwh),
                "margin_usd_mmbtu": _unit(row.margin_usd_mmbtu),
                "margin_total": _money(row.margin_total),
                "lifting_margin_per_mwh": _unit(row.lifting_margin_per_mwh),
                "margin_low_per_mwh": _unit(row.margin_low_per_mwh),
                "margin_high_per_mwh": _unit(row.margin_high_per_mwh),
                "regas_basis": row.regas_basis,
                "grade": str(row.grade),
                "assumptions": row.assumptions,
                "excludes": list(row.excludes),
                "legs": [_leg_payload(leg) for leg in row.legs],
                "fx_usd_per_unit": _unit(row.fx_usd_per_unit),
                "fx_source": row.fx_source,
                "steps": [
                    # Eight decimals, not four: the steps must add up to their totals.
                    {"key": key, "amount": float(amount.quantize(_STEP)), "kind": kind}
                    for key, amount, kind in row.steps
                ],
                "delivered_spread": None
                if row.delivered_per_mwh is None
                else {
                    "delivered_per_mwh": _unit(row.delivered_per_mwh),
                    "hub_per_mwh": _unit(row.delivered_per_mwh + row.arb_per_mwh),
                    "arb_per_mwh": _unit(row.arb_per_mwh),
                    "arb_total": _money(row.arb_per_mwh * row.sent_out_mwh),
                    "sent_out_mwh": _unit(row.sent_out_mwh),
                    "fob_netback_usd_mmbtu": _unit(row.fob_netback_usd_mmbtu),
                    "fob_price_usd_mmbtu": _unit(result.fob_price),
                    "lifting_price_usd_mmbtu": _unit(result.lifting_price),
                    "netback_margin_usd_mmbtu": _unit(row.fob_netback_usd_mmbtu - result.fob_price),
                    "netback_lifting_margin_usd_mmbtu": _unit(
                        row.fob_netback_usd_mmbtu - result.lifting_price
                    ),
                    "netback_total": _money(
                        (row.fob_netback_usd_mmbtu - result.fob_price)
                        * result.q_load_mmbtu
                        / row.fx_usd_per_unit
                    ),
                },
            }
            for row in result.terminals
        ],
        "best_terminal_id": result.best_terminal_id,
        "no_winner": result.no_winner,
        "grade": str(result.grade),
        "assumptions": result.assumptions,
    }
