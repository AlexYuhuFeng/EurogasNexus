"""Research → Spreads opens on the desk's spread board (owner, 2026-11-19; AGENTS.md rule 19).

Computed on load from what the store holds (prices, FX, the tariff register, the firm's
assumption set), with no typing:

- **Locational**: each focus hub against TTF, front month and day-ahead: gross (hub − TTF, EUR
  per MWh at the day's FX), net of the cheapest route in the direction gas would move
  (``route_tariff_cost.cheapest_route``; "route not fully priced" names the missing legs), where
  today's gross sits in its one-year range (percentile) and its last 30 closes;
- **Time**: per focus hub, DA − MA, M+1 − M+2, Win − Sum (next summer to the winter after it,
  against the storage carry where the firm's assumption set holds it), Cal+1 − Cal+2, in the
  hub's currency per MWh with the native-unit figures beside;
- **Cross-commodity**: Henry Hub against TTF delivered (the cargo chain on the desk's standard
  cargo, every assumption labelled) and the clean spark spread where power and carbon are held
  (said so where not).

Each row carries the StrategySpec that opens it in the Spreads workbench. Nothing is stored; no
order or nomination exists.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from typing import Any

from eurogas_nexus.application.instrument_catalogue import source_class
from eurogas_nexus.application.market_normalisation import NormalisationError, conversion
from eurogas_nexus.application.route_tariff_cost import cheapest_route, weakest
from eurogas_nexus.application.spreads_workbench import Holdings, _curve_points, _native
from eurogas_nexus.domain.market.fx_forward import Delivery

#: The majors the board always shows (with the user's focus hubs first).
MAJOR_HUBS = ("TTF", "NBP", "THE", "PEG", "ZTP", "PSV")
REFERENCE_HUB = "TTF"
UNIT = "EUR/MWh"
HISTORY_DAYS = 365
SPARK_DAYS = 30


# ----------------------------------------------------------------------------- series


def _daily(holdings: Holdings, hub: str, tenor: str) -> dict[date, dict[str, Any]]:
    """One close per trade date for a hub and tenor: a real series beats a simulated one."""

    best: dict[date, dict[str, Any]] = {}
    for row in holdings.rows:
        if row.get("hub") != hub or str(row.get("tenor")) != tenor:
            continue
        if not row.get("hub_resolved", True):
            continue
        day = row["day"]
        held = best.get(day)
        rank = (not row.get("simulated"), row["observed_at_utc"])
        if held is None or rank > held["_rank"]:
            best[day] = {**row, "_rank": rank}
    return best


def _eur(holdings: Holdings, row: Mapping[str, Any], *, delivery: Delivery | None = None):
    """A close in EUR/MWh at that day's FX (forward for a forward ``delivery``), or None."""

    try:
        conv = conversion(
            str(row["unit"]), UNIT, holdings=holdings.fx, as_of=row["day"], delivery=delivery
        )
    except NormalisationError:
        return None, None
    return float(row["price"]) * conv.factor, conv.fx


def _klass(row: Mapping[str, Any]) -> str:
    return source_class(
        str(row.get("source_system") or ""),
        simulated=bool(row.get("simulated")),
        settlement=bool(row.get("settlement")),
    )


def _percentile(values: Sequence[float], value: float) -> float | None:
    if len(values) < 20:
        return None
    return round(100.0 * sum(1 for item in values if item <= value) / len(values), 1)


# ----------------------------------------------------------------------------- routes


def _route(holdings: Holdings, start: str, end: str, delivery: Delivery):
    """The cheapest route on firm annual capacity (the register rows Spreads reads), legs in
    another currency at the stated FX."""

    from eurogas_nexus.application.spreads_workbench import _fx_factors

    currencies = {str(row.get("currency") or "").upper() for row in holdings.tariffs} - {""}
    fx = _fx_factors(holdings, currencies, "EUR", delivery)
    return cheapest_route(start, end, delivery, holdings.tariffs, fx=fx), "ANNUAL"


def _route_cost_eur(holdings: Holdings, route: Any, delivery: Delivery) -> float | None:
    if route.total is None or not route.currency:
        return None
    try:
        return (
            route.total
            * conversion(
                f"{route.currency}/MWh",
                UNIT,
                holdings=holdings.fx,
                as_of=holdings.today,
                delivery=delivery,
            ).factor
        )
    except NormalisationError:
        return None


# ----------------------------------------------------------------------------- locational


def _pair(holdings: Holdings, hub: str, tenor: str) -> dict[str, Any]:
    """One locational row: ``hub`` − TTF for the tenor (``month-ahead`` or ``day-ahead``)."""

    code = "MA" if tenor == "month-ahead" else "DA"
    mine, ref = _daily(holdings, hub, tenor), _daily(holdings, REFERENCE_HUB, tenor)
    days = sorted(set(mine) & set(ref))
    out: dict[str, Any] = {"tenor": code, "available": False}
    if not days:
        out["reason"] = f"no {code} close held for both {hub} and {REFERENCE_HUB}"
        return out
    since = holdings.today - timedelta(days=HISTORY_DAYS)
    series: list[tuple[date, float]] = []
    for day in days:
        if day < since:
            continue
        a, _fx_a = _eur(holdings, mine[day])
        b, _fx_b = _eur(holdings, ref[day])
        if a is not None and b is not None:
            series.append((day, a - b))
    last_day = days[-1]
    last, last_ref = mine[last_day], ref[last_day]
    start = last.get("period_start_utc")
    end = last.get("period_end_utc")
    if code == "MA" and start is not None and end is not None:
        first = start.date() if hasattr(start, "date") else start
        final = (end.date() if hasattr(end, "date") else end) - timedelta(days=1)
        delivery = Delivery(first, final, "month", f"{first:%b}-{first:%y}")
    else:
        tomorrow = holdings.today + timedelta(days=1)
        delivery = Delivery(tomorrow, tomorrow, "day_ahead", tomorrow.isoformat())
    a, fx_a = _eur(holdings, last, delivery=delivery if code == "MA" else None)
    b, _ = _eur(holdings, last_ref, delivery=delivery if code == "MA" else None)
    if a is None or b is None:
        out["reason"] = "FX for the delivery period not held"
        return out
    gross = a - b
    start_hub, end_hub = (REFERENCE_HUB, hub) if gross >= 0 else (hub, REFERENCE_HUB)
    choice, product = _route(holdings, start_hub, end_hub, delivery)
    route = choice.chosen
    cost = _route_cost_eur(holdings, route, delivery)
    values = [value for _day, value in series]
    native_a, unit_a = _native(hub, last)
    native_b, unit_b = _native(REFERENCE_HUB, last_ref)
    classes = [_klass(last), _klass(last_ref)]
    if fx_a is not None:
        classes.append(fx_a.input_class)
    if cost is not None:
        classes.append(route.input_class)
    out.update(
        {
            "available": True,
            "close_day": last_day.isoformat(),
            "delivery": delivery.label if code == "MA" else "DA",
            "legs": [
                {"hub": hub, "native_value": native_a, "native_unit": unit_a, "value": a},
                {"hub": REFERENCE_HUB, "native_value": native_b, "native_unit": unit_b, "value": b},
            ],
            "gross": gross,
            "direction": f"{start_hub} → {end_hub}",
            "cost": cost,
            "net": None if cost is None else abs(gross) - cost,
            "route": {
                "hubs": list(route.hubs),
                "through": list(route.hubs[1:-1]),
                "complete": route.complete,
                "missing": route.missing_legs(),
                "product": product,
                "gas_years": route.gas_years,
                "issues": list(choice.issues),
            },
            "percentile": _percentile(values, gross),
            "range": {"low": min(values), "high": max(values), "days": len(values)}
            if values
            else None,
            "spark": {
                "days": [day.isoformat() for day, _v in series[-SPARK_DAYS:]],
                "values": [value for _d, value in series[-SPARK_DAYS:]],
            },
            "input_class": weakest(classes),
            "simulated": "simulated" in classes,
        }
    )
    return out


def locational_rows(holdings: Holdings, hubs: Sequence[str]) -> list[dict[str, Any]]:
    rows = []
    for hub in hubs:
        if hub == REFERENCE_HUB:
            continue
        rows.append(
            {
                "pair": f"{hub}–{REFERENCE_HUB}",
                "hub": hub,
                "reference": REFERENCE_HUB,
                "tenors": [_pair(holdings, hub, "month-ahead"), _pair(holdings, hub, "day-ahead")],
                "spec": {
                    "kind": "curve",
                    "legs": [{"hub": hub, "weight": 1}, {"hub": REFERENCE_HUB, "weight": -1}],
                    "unit": UNIT,
                    "fx": "forward",
                    "cost": {"from_hub": REFERENCE_HUB, "to_hub": hub},
                },
            }
        )
    return rows


# ----------------------------------------------------------------------------- time


def _latest(holdings: Holdings, hub: str, tenor: str) -> dict[str, Any] | None:
    closes = _daily(holdings, hub, tenor)
    return closes[max(closes)] if closes else None


def _per_mwh(row: Mapping[str, Any]) -> float | None:
    value = row.get("price_mwh")
    return float(value) if value is not None else None


def _season_months(today: date) -> tuple[list[date], list[date]]:
    """The next summer that has not begun (Apr–Sep) and the winter after it (Oct–Mar)."""

    year = today.year if today.month < 4 else today.year + 1
    summer = [date(year, month, 1) for month in range(4, 10)]
    winter = [date(year, month, 1) for month in (10, 11, 12)]
    winter += [date(year + 1, month, 1) for month in (1, 2, 3)]
    return summer, winter


def _average(curve: Mapping[str, Mapping[str, Any]], months: Sequence[date]):
    rows = [curve.get(month.isoformat()) for month in months]
    if any(row is None or _per_mwh(row) is None for row in rows):
        return None, [
            m.strftime("%b-%y") for m, row in zip(months, rows, strict=True) if row is None
        ]
    return sum(_per_mwh(row) for row in rows) / len(rows), []  # type: ignore[misc]


def time_rows(holdings: Holdings, hub: str, carry: Mapping[str, Any] | None) -> dict[str, Any]:
    curve = _curve_points(holdings.rows, hub, holdings.today)
    months = sorted(curve)
    currency = None
    out: list[dict[str, Any]] = []

    def add(key: str, label: str, near, far, *, spec=None, extra=None):
        nonlocal currency
        if near is None or far is None:
            out.append({"key": key, "label": label, "available": False, **(extra or {})})
            return
        value = near - far
        out.append(
            {
                "key": key,
                "label": label,
                "available": True,
                "value": value,
                "near": near,
                "far": far,
                "spec": spec,
                **(extra or {}),
            }
        )

    da, ma = _latest(holdings, hub, "day-ahead"), _latest(holdings, hub, "month-ahead")
    for row in (da, ma, *(curve[m] for m in months[:1])):
        if row is not None and currency is None:
            currency = str(row.get("unit_mwh") or "").split("/")[0] or None

    def history(near: str, far: str) -> dict[str, Any]:
        return {
            "kind": "history",
            "legs": [
                {"hub": hub, "tenor": near, "weight": 1},
                {"hub": hub, "tenor": far, "weight": -1},
            ],
        }

    add(
        "da_ma",
        "DA − MA",
        _per_mwh(da) if da else None,
        _per_mwh(ma) if ma else None,
        spec=history("DA", "MA"),
        extra={} if da and ma else {"reason": "DA or MA close not held"},
    )
    if len(months) >= 2:
        m1, m2 = curve[months[0]], curve[months[1]]
        add(
            "m1_m2",
            f"{m1['_label']} − {m2['_label']}",
            _per_mwh(m1),
            _per_mwh(m2),
            spec=history("M+1", "M+2"),
        )
    else:
        add("m1_m2", "M+1 − M+2", None, None, extra={"reason": "two forward months not held"})
    summer, winter = _season_months(holdings.today)
    sum_avg, sum_gap = _average(curve, summer)
    win_avg, win_gap = _average(curve, winter)
    season = f"Win-{winter[0]:%y} − Sum-{summer[0]:%y}"
    extra: dict[str, Any] = {}
    if sum_avg is None or win_avg is None:
        extra["reason"] = "months not held: " + ", ".join(sum_gap + win_gap)
    elif carry is not None:
        cost = carry_cost(carry, sum_avg)
        extra["carry"] = cost
        if cost.get("total") is not None:
            extra["net_of_carry"] = win_avg - sum_avg - cost["total"]
    else:
        extra["carry"] = {"total": None, "reason": "storage costs not in the firm's assumption set"}
    add("win_sum", season, win_avg, sum_avg, extra=extra)
    cal1 = [date(holdings.today.year + 1, m, 1) for m in range(1, 13)]
    cal2 = [date(holdings.today.year + 2, m, 1) for m in range(1, 13)]
    c1, gap1 = _average(curve, cal1)
    c2, gap2 = _average(curve, cal2)
    add(
        f"cal{cal1[0]:%y}_cal{cal2[0]:%y}",
        f"Cal-{cal1[0]:%y} − Cal-{cal2[0]:%y}",
        c1,
        c2,
        extra={}
        if c1 is not None and c2 is not None
        else {"reason": f"{len(gap1) + len(gap2)} months not held"},
    )
    simulated = any(
        row is not None and row.get("simulated")
        for row in (da, ma, *(curve[m] for m in months[:24]))
    )
    return {
        "hub": hub,
        "unit": f"{currency}/MWh" if currency else UNIT,
        "rows": out,
        "simulated": simulated,
    }


#: The firm's assumption keys a storage carry reads.
CARRY_KEYS = (
    "storage.capacity_fee",
    "storage.injection_fee",
    "storage.withdrawal_fee",
    "storage.fuel",
    "financing.rate",
)


def carry_cost(carry: Mapping[str, Any], summer_price: float) -> dict[str, Any]:
    """Win − Sum's cost of holding gas, per MWh: fees, fuel at the summer price, financing of
    the summer price for six months; only the assumption keys held count (named)."""

    parts: dict[str, float] = {}
    for key in ("storage.capacity_fee", "storage.injection_fee", "storage.withdrawal_fee"):
        if carry.get(key) is not None:
            parts[key] = float(carry[key])
    if carry.get("storage.fuel") is not None:
        parts["storage.fuel"] = float(carry["storage.fuel"]) / 100 * summer_price
    if carry.get("financing.rate") is not None:
        parts["financing.rate"] = float(carry["financing.rate"]) / 100 * 0.5 * summer_price
    if not parts:
        return {"total": None, "reason": "storage costs not in the firm's assumption set"}
    return {
        "total": sum(parts.values()),
        "parts": parts,
        "missing": [key for key in CARRY_KEYS if key not in parts],
    }


# ----------------------------------------------------------------------------- the board


def board(
    holdings: Holdings,
    hubs: Sequence[str],
    *,
    carry: Mapping[str, Any] | None,
    cross: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    """The whole board for ``hubs`` (focus hubs first, then the majors)."""

    order = list(dict.fromkeys([*hubs, *MAJOR_HUBS]))
    held = set(holdings.hubs())
    shown = [hub for hub in order if hub in held] or [hub for hub in order][:6]
    locational = locational_rows(holdings, shown)
    time = [time_rows(holdings, hub, carry) for hub in shown[:4]]
    simulated = (
        any(t.get("simulated") for row in locational for t in row["tenors"])
        or any(item["simulated"] for item in time)
        or any(item.get("simulated") for item in cross)
    )
    return {
        "as_of": holdings.today.isoformat(),
        "unit": UNIT,
        "reference": REFERENCE_HUB,
        "hubs": shown,
        "locational": locational,
        "time": time,
        "cross": list(cross),
        "simulated": simulated,
    }


# ----------------------------------------------------------------------------- reads


def carry_inputs(session, caller) -> dict[str, Any] | None:
    """The firm's storage carry assumptions held in its approved set (None when none)."""

    from eurogas_nexus.application.valuation_snapshot import open_valuation_snapshot

    reader = open_valuation_snapshot(session, caller=caller)
    held = {}
    for key in CARRY_KEYS:
        item = reader.assumption(key)
        if item.held and item.value is not None:
            held[key] = float(item.value)
    return held or None


def _month_after(today: date, months: int) -> str:
    index = today.year * 12 + today.month - 1 + months
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def cross_rows(session, caller, today: date) -> list[dict[str, Any]]:
    """Henry Hub against TTF delivered (the desk's standard cargo through the CP-12 chain) and
    the clean spark spread where power and carbon are held."""

    from eurogas_nexus.application.lng_cargo_economics import CargoEconomicsError, cargo_economics

    arrival = _month_after(today, 2)
    rows: list[dict[str, Any]] = []
    try:
        result = cargo_economics(
            session,
            {
                "arrival_month": arrival,
                "cargoes": [
                    {
                        "cargo_id": "standard",
                        "term": "FOB",
                        "standard": True,
                        "pricing_month": _month_after(today, 1),
                    }
                ],
            },
            caller=caller,
        )
    except CargoEconomicsError as exc:
        result = None
        reason = exc.message
    cargo = (result or {}).get("cargoes", [None])[0] if result else None
    row: dict[str, Any] = {
        "key": "hh_ttf",
        "label": "HH − TTF delivered",
        "available": False,
        "arrival": arrival,
    }
    if cargo is None:
        row["reason"] = reason if result is None else "no cargo priced"
    elif cargo.get("blocked"):
        row["reason"] = cargo["blocked"]
    else:
        priced = [
            t for t in cargo["terminals"] if t.get("reason") is None and t.get("delivered_spread")
        ]
        first = priced[0] if priced else None
        chosen = next((t for t in priced if t["hub"] == REFERENCE_HUB), first)
        if chosen is None:
            row["reason"] = "no terminal priced"
        else:
            spread = chosen["delivered_spread"]
            hh = next((leg for leg in cargo["legs"] if leg["key"] == "hh"), None)
            row.update(
                {
                    "available": True,
                    "terminal": chosen["name"],
                    "hub": chosen["hub"],
                    "currency": chosen["currency"],
                    "hh": None if hh is None else hh["amount"],
                    "hh_source": None if hh is None else hh["source"],
                    "hub_price": spread["hub_per_mwh"],
                    "delivered": spread["delivered_per_mwh"],
                    "value": spread["arb_per_mwh"],
                    "netback_usd_mmbtu": spread["fob_netback_usd_mmbtu"],
                    "assumptions": cargo["assumptions"],
                    "input_class": chosen["grade"],
                    "simulated": chosen["grade"] == "simulated",
                }
            )
    rows.append(row)
    rows.append(_clean_spark(session))
    return rows


def _clean_spark(session) -> dict[str, Any]:
    from eurogas_nexus.application.identity_resolution import identity_clause
    from eurogas_nexus.db.models import MarketObservationRecord
    from eurogas_nexus.db.models.power import PowerObservationRecord

    power = (
        session.query(PowerObservationRecord.observation_id)
        .filter(identity_clause(session, PowerObservationRecord))
        .first()
        is not None
    )
    carbon = (
        session.query(MarketObservationRecord.observation_id)
        .filter(MarketObservationRecord.product.ilike("%EUA%"))
        .filter(identity_clause(session, MarketObservationRecord))
        .first()
        is not None
    )
    reasons = []
    if not power:
        reasons.append("no power price held")
    if not carbon:
        reasons.append("no carbon (EUA) price held")
    return {
        "key": "clean_spark",
        "label": "Clean spark",
        "available": False,
        "reason": "; ".join(reasons) or "not computed yet",
    }
