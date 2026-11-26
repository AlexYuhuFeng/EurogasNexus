"""The desk's reading of a cargo study: units, the cost stack per terminal, the verdict, a reason
per terminal and two-sided sensitivities.

``lng_cargo_economics`` prices the chain (``domain/lng/cargo_economics``); this module adds what
an LNG desk reads off it, each figure with its source and date:

* **units**: the cargo in MMBtu, MWh and therm, and how a DES price was converted;
* **cost stack**: every item in the hub currency per MWh delivered and per cargo, with its input
  class, source, as-of and (for published tariffs) the version used, ending with the netback and
  the net value against the purchase;
* **further costs** (``OtherCost``): the FSRU's CO2 pass-through (DET publishes the factor), EU
  ETS on the voyage of an FOB cargo into an EU terminal, and discharge port costs a DES buyer
  pays under its contract;
* **verdict**: best terminal, or that every terminal nets below the purchase and which loses
  least, by how much, and the break-even purchase price;
* **reason** per terminal: best, or how far behind and the item that explains most of the gap;
* **sensitivity**: each input moved down and up on its own, the margin change and whether the
  best terminal changes.

Carbon (desk assumptions, each stated in the result):

* EU ETS maritime (Directive 2003/87/EC as amended by Directive (EU) 2023/959): a voyage between
  a port outside the EU and an EU port counts 50 % of its emissions; from 2026 emissions the
  phase-in is 100 %. A UK terminal is outside the EU ETS (UK ETS covers domestic voyages only).
  Fuel burnt is the laden boil-off plus the ballast fuel, at 0.05306 tCO2 per MMBtu (US EPA
  default factor for natural gas); the load port is taken as outside the EU.
* EUA: the price entered, else the snapshot's EUA forward, else a desk standard of 70 EUR/t. An
  EUA forward is ICE Endex / EEX data and needs a licence: labelled so.

Research only: nothing here is an offer, a bid or a nomination.

LNG 船货研究：单位换算、逐项成本、结论、各接收站原因及双向敏感性（仅供研究）。
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from typing import Any

from eurogas_nexus.domain.lng.cargo_economics import (
    MMBTU_PER_MWH,
    CargoOffer,
    CargoResult,
    OtherCost,
    TerminalOption,
    TerminalResult,
    Valued,
    evaluate_cargo,
)
from eurogas_nexus.domain.valuation.quality import InputClass

#: Therms in one MMBtu (exact: 1 therm = 100,000 Btu).
THERM_PER_MMBTU = Decimal(10)
#: GJ in one MWh.
GJ_PER_MWH = Decimal("3.6")
#: tCO2 per MMBtu of natural gas burnt (US EPA, 40 CFR Part 98 Table C-1: 53.06 kg/MMBtu).
CO2_T_PER_MMBTU = Decimal("0.05306")
#: Share of an extra-EU voyage's emissions in the EU ETS (Art. 3ga), at the 2026+ phase-in.
ETS_VOYAGE_SHARE = Decimal("0.5")
#: Desk standard EUA when none is entered or held (labelled licence-needed).
EUA_STANDARD_EUR_T = Decimal(70)
_NON_EU = frozenset({"GB"})
_Q4 = Decimal("0.0001")
_Q2 = Decimal("0.01")

#: Two-sided bumps: key, step, unit, terms it applies to.
BUMPS = (
    ("hub", Decimal(1), "per MWh", {"FOB", "DES"}),
    ("des", Decimal(1), "per MWh", {"DES"}),
    ("hire", Decimal(10000), "USD/day", {"FOB"}),
    ("boil_off", Decimal("0.02"), "%/day", {"FOB"}),
    ("hh", Decimal("0.10"), "USD/MMBtu", {"FOB"}),
    ("fx", Decimal("0.01"), "relative", {"FOB", "DES"}),
    ("eua", Decimal(10), "EUR/t", {"FOB", "DES"}),
)


def _f(value: Decimal | None, q: Decimal = _Q4) -> float | None:
    return None if value is None else float(value.quantize(q))


def published_payload(published) -> dict[str, Any] | None:
    """What the reference file says of a terminal: operator, regime, entry point, why no price."""

    if published is None:
        return None
    return {
        "operator": published.operator,
        "country": published.country,
        "regime": published.regime,
        "entry_tso": published.entry_tso,
        "entry_point": published.entry_point,
        "not_published": published.not_published,
        "permission_operator": published.permission_operator,
    }


def eua(reader, request: dict[str, Any], period) -> Valued:
    """EUA in EUR/t for the month: entered, the snapshot's, else the desk standard."""

    entered = request.get("eua_eur_t")
    if entered is not None:
        return Valued(Decimal(str(entered)), InputClass.ASSUMPTION, "entered: EUA")
    try:
        item = reader.price("EUA", period)
    except Exception:  # noqa: BLE001 - a hub the snapshot does not know reads as not held
        item = None
    if item is not None and getattr(item, "held", False):
        return Valued(Decimal(str(item.value)), item.input_class, item.label or "EUA forward")
    return Valued(
        EUA_STANDARD_EUR_T,
        InputClass.ASSUMPTION,
        "desk standard 70 EUR/t; an EUA forward (ICE Endex / EEX) needs a licence",
    )


def other_costs(
    reader,
    *,
    request: dict[str, Any],
    cargo: dict[str, Any] | None,
    terminal,
    currency: str,
    period,
    q_del_mwh: Decimal,
    gik: Valued,
    offer: CargoOffer | None,
    cost_side: CargoResult | None,
    fx_usd_per_unit: Valued,
    des_fx: Valued | None,
    meta: dict[str, Any],
) -> tuple[OtherCost, ...]:
    """The further costs at one terminal, each a total in the hub currency."""

    from eurogas_nexus.domain.lng import published_tariffs

    items: list[OtherCost] = []
    published = terminal.published
    carbon_price: Valued | None = None
    eur_per_unit: Decimal | None = None  # hub-currency units per EUR

    def carbon() -> tuple[Valued, Decimal | None]:
        nonlocal carbon_price, eur_per_unit
        if carbon_price is None:
            carbon_price = eua(reader, request, period)
            meta["eua"] = {
                "eur_t": float(carbon_price.value),
                "input_class": str(carbon_price.input_class),
                "source": carbon_price.source,
            }
            if currency == "EUR":
                eur_per_unit = Decimal(1)
            else:
                eur = reader.fx("EUR", "USD", period)
                if getattr(eur, "held", False) and fx_usd_per_unit.held:
                    eur_per_unit = Decimal(str(eur.value)) / fx_usd_per_unit.value
        return carbon_price, eur_per_unit

    arrival = period.start
    # FSRU fuel: the share kept in kind is burnt on board; DET passes its CO2 cost through.
    co2 = (
        published_tariffs.select(published, "fsru_co2", arrival, "any")
        if published is not None
        else []
    )
    if co2 and gik.held and gik.value > 0:
        price, rate = carbon()
        if rate is not None:
            tonnes = q_del_mwh * gik.value / 100 * GJ_PER_MWH * co2[0].charge.value
            items.append(
                OtherCost(
                    "carbon_fsru",
                    "FSRU CO2 pass-through",
                    tonnes * price.value * rate,
                    InputClass.ASSUMPTION
                    if price.input_class == InputClass.ASSUMPTION
                    else InputClass.INDICATIVE,
                    f"{co2[0].charge.source_title}: {co2[0].charge.value} tCO2/GJ on the gas "
                    f"kept in kind; EUA {price.value} EUR/t ({price.source})",
                )
            )
            meta.setdefault("carbon_t", {})["carbon_fsru"] = float(tonnes.quantize(_Q2))
            meta["versions"]["carbon_fsru"] = [use.version() for use in co2]
    # EU ETS on the voyage of an FOB cargo discharged in the EU.
    country = published.country if published is not None else ""
    if (
        offer is not None
        and offer.term == "FOB"
        and cost_side is not None
        and cost_side.days is not None
        and country
        and country not in _NON_EU
    ):
        price, rate = carbon()
        burnt = cost_side.q_load_mmbtu - cost_side.q_del_mmbtu - offer.heel_delta_mmbtu
        burnt += cost_side.days.ballast * offer.ballast_fuel_mmbtu_per_day.value
        tonnes = burnt * CO2_T_PER_MMBTU * ETS_VOYAGE_SHARE
        if rate is not None:
            items.append(
                OtherCost(
                    "carbon_voyage",
                    "EU ETS on the voyage",
                    tonnes * price.value * rate,
                    InputClass.ASSUMPTION,
                    f"{burnt.quantize(Decimal(1))} MMBtu burnt x {CO2_T_PER_MMBTU} tCO2/MMBtu x "
                    f"50 % (extra-EU voyage); EUA {price.value} EUR/t ({price.source})",
                )
            )
            meta.setdefault("carbon_t", {})["carbon_voyage"] = float(tonnes.quantize(_Q2))
    # DES: discharge port costs for the buyer's account, entered in the DES currency.
    entered = (cargo or {}).get("discharge_port_cost")
    if offer is not None and offer.term == "DES" and entered:
        rate = Decimal(1) if des_fx is None else des_fx.value if des_fx.held else None
        if rate is not None:
            items.append(
                OtherCost(
                    "port_discharge",
                    "Discharge port costs (buyer's account)",
                    Decimal(str(entered)) * rate,
                    InputClass.ASSUMPTION,
                    f"entered: {entered:g} {offer.des_currency} per call",
                )
            )
    return tuple(items)


def des_per_mwh(cargo: dict[str, Any]) -> tuple[float | None, str, dict[str, Any] | None]:
    """The DES price per MWh in its currency, the currency, and how it was converted."""

    value = cargo.get("des_price")
    unit = cargo.get("des_price_unit") or "per_mwh"
    currency = cargo.get("des_currency") or "EUR"
    if value is None:
        return None, currency, None
    raw = Decimal(str(value))
    if unit == "per_mmbtu":
        per_mwh = raw * MMBTU_PER_MWH
        factor = f"x {MMBTU_PER_MWH.quantize(Decimal('0.000001'))} MMBtu/MWh"
    elif unit == "p_th":
        currency = "GBP"
        per_mwh = raw * MMBTU_PER_MWH * THERM_PER_MMBTU / 100
        factor = f"x {(MMBTU_PER_MWH * THERM_PER_MMBTU).quantize(Decimal('0.0001'))} th/MWh / 100 p"
    else:
        per_mwh = raw
        factor = ""
    return (
        float(per_mwh),
        currency,
        {
            "entered": float(raw),
            "unit": unit,
            "currency": currency,
            "per_mwh": _f(per_mwh),
            "factor": factor,
        },
    )


def units(result: CargoResult, des: dict[str, Any] | None) -> dict[str, Any]:
    """The cargo in MMBtu, MWh and therm, with the factors used."""

    def three(mmbtu: Decimal | None) -> dict[str, float | None] | None:
        if mmbtu is None:
            return None
        return {
            "mmbtu": _f(mmbtu, _Q2),
            "mwh": _f(mmbtu / MMBTU_PER_MWH, _Q2),
            "therm": _f(mmbtu * THERM_PER_MMBTU, Decimal(1)),
        }

    return {
        "mmbtu_per_mwh": float(MMBTU_PER_MWH.quantize(Decimal("0.000001"))),
        "mwh_per_mmbtu": float((1 / MMBTU_PER_MWH).quantize(Decimal("0.000001"))),
        "therm_per_mmbtu": float(THERM_PER_MMBTU),
        "loaded": three(result.q_load_mmbtu),
        "delivered": three(result.q_del_mmbtu),
        "des": des,
    }


def _item(key, per_mwh, q_del_mwh, valued=None, *, source="", klass=None, **extra):
    return {
        "key": key,
        "per_mwh": _f(per_mwh),
        "total": _f(per_mwh * q_del_mwh, _Q2),
        "input_class": str(klass or (valued.input_class if valued is not None else "derived")),
        "source": source or (valued.source if valued is not None else ""),
        **extra,
    }


def cost_stack(
    result: CargoResult,
    offer: CargoOffer,
    option: TerminalOption,
    row: TerminalResult,
    meta: dict[str, Any],
) -> dict[str, Any] | None:
    """Every item of one priced terminal, hub currency per MWh delivered and per cargo.

    The value side runs hub price, gas in kind, entry, regas, further costs, netback; the cost
    side runs the purchase (FOB price, boil-off, each freight item; or the DES price, converted
    when in another currency) to the cost at the ship's rail; the net value is netback less cost.
    """

    if row.reason is not None or result.q_del_mwh is None:
        return None
    q = result.q_del_mwh
    steps = {key: amount for key, amount, _kind in row.steps}
    versions = meta.get("versions", {})
    excluded = set(meta.get("excluded", []))
    value = [
        _item(
            "hub",
            steps["hub"],
            q,
            option.hub_price,
            as_of=meta.get("hub_as_of"),
            licence_needed=meta.get("hub_licence_needed", False),
        ),
        _item(
            "gas_in_kind",
            steps["gas_in_kind"],
            q,
            option.gas_in_kind_pct,
            rate=_f(option.gas_in_kind_pct.value),
            versions=versions.get("gas_in_kind"),
            excluded="gas_in_kind" in excluded,
        ),
        _item(
            "entry",
            steps["entry"],
            q,
            option.entry,
            rate=_f(option.entry.value),
            versions=versions.get("entry"),
            excluded="entry" in excluded,
        ),
        _item(
            "regas",
            steps["regas"],
            q,
            option.regas_total,
            basis=option.regas_basis,
            versions=versions.get("regas"),
        ),
        *(
            _item(
                item.key,
                -item.total / q,
                q,
                klass=item.input_class,
                source=item.source,
                versions=versions.get(item.key),
                tonnes=meta.get("carbon_t", {}).get(item.key),
            )
            for item in option.other_items
        ),
        _item("netback", steps["netback"], q),
    ]
    cost: list[dict[str, Any]] = []
    if offer.term == "FOB":
        fx = option.fx_usd_per_unit.value
        to_hub = MMBTU_PER_MWH / fx / result.q_del_mmbtu  # USD per cargo -> hub per MWh

        fob_source = (
            offer.fob_price.source
            if offer.fob_price.held
            else f"{offer.slope.value} x HH {offer.hh.value} + {offer.fee.value}"
            f" ({offer.hh.source})"
        )
        cost += [
            _item(
                "fob",
                -steps["fob"],
                q,
                offer.fob_price if offer.fob_price.held else offer.hh,
                source=fob_source,
                usd_mmbtu=_f(result.fob_price),
            ),
            _item(
                "boil_off",
                -steps["boil_off"],
                q,
                offer.boil_off_pct_per_day,
                rate=_f(offer.boil_off_pct_per_day.value),
                mmbtu=_f(result.q_load_mmbtu - result.q_del_mmbtu, _Q2),
            ),
        ]
        freight = result.freight
        for key, amount, valued in (
            ("hire", freight.hire, offer.hire_per_day),
            ("ballast_fuel", freight.ballast_fuel, offer.ballast_fuel_mmbtu_per_day),
            ("ports", freight.port_load + freight.port_discharge, offer.port_load),
            ("canal", freight.canal, offer.canal),
            ("insurance", freight.insurance, offer.insurance_pct),
        ):
            cost.append(_item(key, amount * to_hub, q, valued, usd=_f(amount, _Q2)))
        fx_line = {
            "pair": f"USD/{option.currency}",
            "usd_per_unit": _f(fx),
            "source": option.fx_usd_per_unit.source,
            "input_class": str(option.fx_usd_per_unit.input_class),
        }
    else:
        des_fx = option.des_fx
        cost.append(
            _item(
                "des",
                row.cost_per_mwh,
                q,
                offer.des_price,
                des_currency=offer.des_currency,
                des_per_mwh=_f(offer.des_price.value),
            )
        )
        fx_line = (
            None
            if des_fx is None
            else {
                "pair": f"{offer.des_currency}/{option.currency}",
                "rate": _f(des_fx.value),
                "source": des_fx.source,
                "input_class": str(des_fx.input_class),
            }
        )
    cost.append(_item("cost", row.cost_per_mwh, q))
    return {
        "currency": option.currency,
        "q_del_mwh": _f(q, _Q2),
        "value": value,
        "cost": cost,
        "fx": fx_line,
        "net": _item("margin", row.margin_per_mwh, q),
        "excluded": sorted(excluded),
    }


def _key(row: TerminalResult) -> Decimal | None:
    return (
        row.margin_reporting_per_mwh
        if row.margin_reporting_per_mwh is not None
        else (row.margin_per_mwh)
    )


def _priced(result: CargoResult) -> list[TerminalResult]:
    return [row for row in result.terminals if row.reason is None]


def verdict(
    result: CargoResult,
    offer: CargoOffer,
    stacks: dict[str, dict[str, Any] | None],
    reporting: str,
    mixed: bool,
) -> dict[str, Any]:
    """Best terminal or least-bad, by how much, and the break-even purchase."""

    priced = _priced(result)
    left_out = [
        {"terminal_id": row.terminal_id, "name": row.name, "reason": row.reason}
        for row in result.terminals
        if row.reason is not None
    ]
    if result.blocked or not priced:
        return {"state": "none_priced", "blocked": result.blocked, "left_out": left_out}
    best = priced[0]
    runner = priced[1] if len(priced) > 1 else None
    margin = _key(best)
    currency = reporting if mixed else best.currency
    breakeven: dict[str, Any]
    if offer.term == "FOB" and best.fob_netback_usd_mmbtu is not None:
        breakeven = {"basis": "fob", "value": _f(best.fob_netback_usd_mmbtu), "unit": "USD/MMBtu"}
    else:
        # The DES price, in the DES currency per MWh, at which the best terminal nets zero.
        rate = Decimal(1)
        stack = stacks.get(best.terminal_id) or {}
        if stack.get("fx") and stack["fx"].get("rate"):
            rate = Decimal(str(stack["fx"]["rate"]))
        breakeven = {
            "basis": "des",
            "value": _f(best.netback_per_mwh / rate),
            "unit": f"{offer.des_currency}/MWh",
        }
    partial = [
        {"terminal_id": row.terminal_id, "name": row.name, "excluded": stack["excluded"]}
        for row in priced
        if (stack := stacks.get(row.terminal_id)) and stack["excluded"]
    ]
    return {
        "state": "positive" if margin > 0 else "all_negative",
        "best_terminal_id": best.terminal_id,
        "best_name": best.name,
        "margin_per_mwh": _f(margin),
        "margin_total": _f(margin * result.q_del_mwh, _Q2),
        "currency": currency,
        "runner_up_id": runner.terminal_id if runner else None,
        "runner_up_name": runner.name if runner else None,
        "lead_per_mwh": _f(margin - _key(runner)) if runner else None,
        "no_winner": result.no_winner,
        "breakeven": breakeven,
        "priced": len(priced),
        "partial": partial,
        "left_out": left_out,
    }


def _to_reporting(row: TerminalResult) -> Decimal:
    """Factor from the row's own per-MWh figures to the ranking's (1 in one currency)."""

    if row.margin_reporting_per_mwh is None or not row.margin_per_mwh:
        return Decimal(1)
    return row.margin_reporting_per_mwh / row.margin_per_mwh


def reasons(result: CargoResult, stacks: dict[str, dict[str, Any] | None]) -> dict[str, Any]:
    """Per terminal: best, or how far behind the best and the item explaining most of it."""

    priced = _priced(result)
    out: dict[str, Any] = {}
    if not priced:
        return out
    best = priced[0]
    best_stack = stacks.get(best.terminal_id) or {}
    best_items = {
        item["key"]: Decimal(str(item["per_mwh"])) * _to_reporting(best)
        for item in (*best_stack.get("value", []), *best_stack.get("cost", []))
        if item["key"] not in {"netback", "cost"} and item["per_mwh"] is not None
    }
    for row in priced:
        stack = stacks.get(row.terminal_id) or {}
        if row.terminal_id == best.terminal_id:
            out[row.terminal_id] = {"kind": "best", "excluded": stack.get("excluded", [])}
            continue
        factor = _to_reporting(row)
        gaps = []
        for item in (*stack.get("value", []), *stack.get("cost", [])):
            if item["key"] in {"netback", "cost"} or item["per_mwh"] is None:
                continue
            mine = Decimal(str(item["per_mwh"])) * factor
            # Value items add to the margin, cost items take from it.
            sign = 1 if item in stack.get("value", []) else -1
            theirs = best_items.get(item["key"], Decimal(0))
            gaps.append((sign * (mine - theirs), item["key"]))
        for key, theirs in best_items.items():
            if not any(key == item["key"] for item in (*stack["value"], *stack["cost"])):
                sign = 1 if any(i["key"] == key for i in best_stack["value"]) else -1
                gaps.append((sign * -theirs, key))
        worst = min(gaps) if gaps else (Decimal(0), None)
        out[row.terminal_id] = {
            "kind": "behind",
            "behind_per_mwh": _f(_key(best) - _key(row)),
            "driver": worst[1],
            "driver_per_mwh": _f(-worst[0]),
            "excluded": stack.get("excluded", []),
        }
    return out


def _move(value: Valued, delta: Decimal, *, relative: bool = False) -> Valued:
    if not value.held:
        return value
    moved = value.value * (1 + delta) if relative else value.value + delta
    return Valued(moved, value.input_class, value.source)


def sensitivity(
    offer: CargoOffer,
    options: list[TerminalOption],
    base: CargoResult,
    *,
    reporting: tuple[str, Decimal] | None,
    eua_eur_t: Decimal | None,
) -> list[dict[str, Any]]:
    """Each input moved down and up on its own: the best terminal's margin change (hub currency
    per MWh delivered) and the best terminal after the move (a flip when it changes).

    Terminal totals (regas, carbon) are held at the base cargo's figures when boil-off moves
    the energy delivered: a second-order effect, said here rather than hidden.

    The old one-sided fields (``bump``, ``margin_change_per_mwh``) carry the upward move.
    """

    priced = _priced(base)
    if not priced:
        return []
    best = priced[0]
    rows = []
    for key, step, unit, terms in BUMPS:
        if offer.term not in terms:
            continue
        if key == "hh" and (offer.fob_price.held or not offer.hh.held):
            continue
        if key == "fx" and offer.term == "DES" and not any(o.des_fx for o in options):
            continue
        if key == "fx" and offer.term == "FOB" and all(o.currency == "USD" for o in options):
            continue
        if key == "eua" and (
            eua_eur_t is None
            or not any(i.key.startswith("carbon") for o in options for i in o.other_items)
        ):
            continue
        sides = {}
        for side, sign in (("down", -1), ("up", 1)):
            delta = step * sign
            moved_offer, moved = offer, list(options)
            if key == "hub":
                moved = [replace(o, hub_price=_move(o.hub_price, delta)) for o in options]
            elif key == "des":
                moved_offer = replace(offer, des_price=_move(offer.des_price, delta))
            elif key == "hire":
                moved_offer = replace(offer, hire_per_day=_move(offer.hire_per_day, delta))
            elif key == "boil_off":
                moved_offer = replace(
                    offer, boil_off_pct_per_day=_move(offer.boil_off_pct_per_day, delta)
                )
            elif key == "hh":
                moved_offer = replace(offer, hh=_move(offer.hh, delta))
            elif key == "fx" and offer.term == "FOB":
                moved = [
                    replace(o, fx_usd_per_unit=_move(o.fx_usd_per_unit, delta, relative=True))
                    for o in options
                ]
            elif key == "fx":
                moved = [
                    o
                    if o.des_fx is None
                    else replace(o, des_fx=_move(o.des_fx, delta, relative=True))
                    for o in options
                ]
            elif key == "eua":
                scale = (eua_eur_t + delta) / eua_eur_t
                moved = [
                    replace(
                        o,
                        other_items=tuple(
                            replace(i, total=i.total * scale) if i.key.startswith("carbon") else i
                            for i in o.other_items
                        ),
                    )
                    for o in options
                ]
            result = evaluate_cargo(moved_offer, moved, reporting=reporting)
            mine = next((r for r in result.terminals if r.terminal_id == best.terminal_id), None)
            top = next((r for r in result.terminals if r.reason is None), None)
            if mine is None or mine.margin_per_mwh is None:
                break
            sides[side] = {
                "margin_change_per_mwh": _f(mine.margin_per_mwh - best.margin_per_mwh),
                "best_terminal_id": top.terminal_id if top else None,
                "flips": bool(top and top.terminal_id != best.terminal_id),
            }
        if len(sides) != 2:
            continue
        if not any(side["margin_change_per_mwh"] or side["flips"] for side in sides.values()):
            continue  # moves nothing for this cargo (an FX the best terminal does not use)
        rows.append(
            {
                "key": key,
                "bump": float(step * 100) if key == "fx" else float(step),
                "unit": "%" if key == "fx" else unit,
                "margin_change_per_mwh": sides["up"]["margin_change_per_mwh"],
                "down": sides["down"],
                "up": sides["up"],
                "currency": best.currency,
            }
        )
    return rows


__all__ = [
    "BUMPS",
    "CO2_T_PER_MMBTU",
    "ETS_VOYAGE_SHARE",
    "EUA_STANDARD_EUR_T",
    "cost_stack",
    "des_per_mwh",
    "eua",
    "other_costs",
    "published_payload",
    "reasons",
    "sensitivity",
    "units",
    "verdict",
]
