"""Rule-written commentary for each report section: a headline and up to three facts.

Pure functions over the figures a section computed: nothing here reads the store or calls a
model. Every sentence states a figure the section's table holds, with its unit; a
simulated figure says so next to the value; a forecast says it is a forecast; late and stale
inputs are named. There is no advice and no word about execution, nomination or settlement.
The model may later rewrite this text for flow (``rewrite.py``); if its text fails the
checks, this text stands.
"""

from __future__ import annotations

from datetime import date
from typing import Any

MAX_BULLETS = 3
SIM = " (simulated)"


def number(value: float | None, unit: str = "", digits: int | None = None) -> str:
    """``31.40 EUR/MWh``, ``1,234 GWh/d``, ``84.5%``: the figure as the desk writes it."""

    if value is None:
        return "n/a"
    if digits is None:
        if unit == "%":
            digits = 1
        elif unit.startswith("GWh") or unit.startswith("MWh") or unit == "TWh":
            digits = 0 if abs(value) >= 100 else 1
        else:
            digits = 2
    text = f"{abs(value):,.{digits}f}" if value < 0 else f"{value:,.{digits}f}"
    if value < 0:
        text = "-" + text
    if not unit:
        return text
    return f"{text}{unit}" if unit == "%" else f"{text} {unit}"


def move(change: float | None, unit: str, digits: int | None = None) -> str:
    """``up 0.35 EUR/MWh``, ``down 2.1 points``, ``unchanged``."""

    if change is None:
        return "n/a"
    shown = number(abs(change), unit, digits)
    if shown.split(" ")[0].rstrip("%") in {"0", "0.0", "0.00"}:
        return "unchanged"
    return f"{'up' if change > 0 else 'down'} {shown}"


def day(value: str | date | None) -> str:
    if value is None:
        return "n/a"
    moment = value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
    return f"{moment.day} {moment:%b}"


def _sim(flag: bool) -> str:
    return SIM if flag else ""


def _state_note(items: list[tuple[str, str]]) -> str | None:
    """``Late: TTF close (12 Nov). Stale: storage (9 Nov).``"""

    late = [label for label, state in items if state == "late"]
    stale = [label for label, state in items if state == "stale"]
    parts = []
    if late:
        parts.append("Late: " + ", ".join(late) + ".")
    if stale:
        parts.append("Stale: " + ", ".join(stale) + ".")
    return " ".join(parts) or None


def _out(headline: str, bullets: list[str | None]) -> dict[str, Any]:
    return {"headline": headline, "bullets": [b for b in bullets if b][:MAX_BULLETS]}


# ------------------------------------------------------------------------------- prices


def prices(rows: list[dict[str, Any]], *, period_label: str | None) -> dict[str, Any]:
    """Hub closes. ``period_label`` (``the week``, ``November``) when the report is a period."""

    if not rows:
        return _out("No hub close is available to this report.", [])
    parts = []
    for row in rows[:3]:
        text = f"{row['hub']} {row['product']} {number(row['close'], row['unit'])}" \
               f"{_sim(row['simulated'])}"
        change = row.get("period_change") if period_label else row.get("day_change")
        if change is not None:
            text += f", {move(change, row['unit'])}"
            text += f" over {period_label}" if period_label else " on the day"
        parts.append(text)
    headline = "; ".join(parts) + "."
    bullets: list[str | None] = []
    moved = [r for r in rows if (r.get("period_change") if period_label else r.get("day_change"))
             is not None]
    if len(moved) > 1:
        key = "period_change" if period_label else "day_change"
        biggest = max(moved, key=lambda r: abs(r[key]))
        bullets.append(
            f"The largest move was {biggest['hub']}, {move(biggest[key], biggest['unit'])}"
            f"{' over ' + period_label if period_label else ' on the day'}."
        )
    ranged = [r for r in rows if r.get("high") is not None and r.get("low") is not None]
    if period_label and ranged:
        r = ranged[0]
        bullets.append(
            f"{r['hub']} traded between {number(r['low'], r['unit'])} and "
            f"{number(r['high'], r['unit'])} at the close over {period_label}"
            f"{_sim(r['simulated'])}."
        )
    yearly = [r for r in rows if r.get("year_ago") is not None]
    if yearly:
        r = yearly[0]
        bullets.append(
            f"A year earlier the {r['hub']} front month closed at "
            f"{number(r['year_ago'], r['unit'])}{_sim(r['simulated'])}."
        )
    bullets.append(_state_note([(f"{r['hub']} close ({day(r['close_day'])})", r["state"])
                                for r in rows]))
    return _out(headline, bullets)


# ------------------------------------------------------------------------------- supply


def pipeline(stats: dict[str, Any]) -> dict[str, Any]:
    """Norwegian pipeline landings: ``latest``, ``latest_day``, ``avg_7``, ``period_avg``..."""

    sim = _sim(stats.get("simulated", False))
    unit = "GWh/d"
    if stats.get("period_label"):
        headline = (
            f"Norwegian pipeline landings averaged {number(stats['period_avg'], unit)}{sim} "
            f"over {stats['period_label']}"
        )
        if stats.get("previous_avg") is not None:
            headline += (
                f", {move(stats['period_avg'] - stats['previous_avg'], unit)} on the period "
                "before"
            )
    else:
        headline = (
            f"Norwegian pipeline landings were {number(stats['latest'], unit)}{sim} on "
            f"{day(stats['latest_day'])}"
        )
        if stats.get("previous") is not None:
            headline += f", {move(stats['latest'] - stats['previous'], unit)} on the day before"
    bullets = []
    if stats.get("uk_terminal") is not None and stats.get("continent") is not None:
        bullets.append(
            f"Continental landings {number(stats['continent'], unit)} and UK terminals "
            f"{number(stats['uk_terminal'], unit)} on {day(stats['latest_day'])}{sim}; UK "
            "terminals carry UK shelf gas with Norwegian gas."
        )
    if stats.get("avg_7") is not None and not stats.get("period_label"):
        bullets.append(f"The seven-day average is {number(stats['avg_7'], unit)}{sim}.")
    if stats.get("year_ago") is not None:
        bullets.append(
            f"A year earlier the same days averaged {number(stats['year_ago'], unit)}{sim}."
        )
    if stats.get("state") in {"late", "stale"}:
        bullets.insert(0, f"The newest complete gas day is {day(stats['latest_day'])} "
                          f"({stats['state']}).")
    return _out(headline + ".", bullets)


def lng(stats: dict[str, Any]) -> dict[str, Any]:
    sim = _sim(stats.get("simulated", False))
    unit = "GWh/d"
    if stats.get("period_label"):
        headline = (
            f"LNG send-out in NW Europe averaged {number(stats['period_avg'], unit)}{sim} over "
            f"{stats['period_label']}"
        )
        if stats.get("previous_avg") is not None:
            headline += f", {move(stats['period_avg'] - stats['previous_avg'], unit)} on the " \
                        "period before"
    else:
        headline = (
            f"LNG send-out in NW Europe was {number(stats['latest'], unit)}{sim} on "
            f"{day(stats['latest_day'])}"
        )
        if stats.get("avg_7") is not None:
            headline += f", against a seven-day average of {number(stats['avg_7'], unit)}"
    bullets = []
    top = stats.get("by_country") or []
    if top:
        name, value = top[0]
        bullets.append(f"{name} sent out the most: {number(value, unit)}{sim}.")
    if stats.get("year_ago") is not None:
        bullets.append(f"A year earlier: {number(stats['year_ago'], unit)}{sim}.")
    if stats.get("left_out"):
        bullets.append("Days not yet reported by every country are left out: "
                       + ", ".join(day(d) for d in stats["left_out"][:3]) + ".")
    if stats.get("state") in {"late", "stale"}:
        bullets.insert(0, f"The newest complete gas day is {day(stats['latest_day'])} "
                          f"({stats['state']}).")
    return _out(headline + ".", bullets)


def storage(stats: dict[str, Any]) -> dict[str, Any]:
    sim = _sim(stats.get("simulated", False))
    headline = (
        f"NW Europe storage was {number(stats['fill'], '%')} full{sim} on "
        f"{day(stats['day'])}"
    )
    if stats.get("year_ago") is not None:
        diff = stats["fill"] - stats["year_ago"]
        headline += (
            f", {number(abs(diff), '', 1)} points {'above' if diff >= 0 else 'below'} the same "
            f"day a year earlier ({number(stats['year_ago'], '%')})"
        )
    bullets = []
    if stats.get("period_change") is not None:
        bullets.append(
            f"Fill {'rose' if stats['period_change'] > 0 else 'fell'} "
            f"{number(abs(stats['period_change']), '', 1)} points over "
            f"{stats.get('period_label') or 'the last seven days'}{sim}."
        )
    if stats.get("inventory_twh") is not None:
        bullets.append(f"Inventory {number(stats['inventory_twh'], 'TWh', 1)} in the "
                       f"facilities that publish a working capacity{sim}.")
    if stats.get("target") is not None:
        bullets.append(
            f"The EU filling target is {number(stats['target'], '%', 0)} between "
            f"{stats['target_window']}."
        )
    if stats.get("state") in {"late", "stale"}:
        bullets.insert(0, f"Newest complete day {day(stats['day'])} ({stats['state']}).")
    return _out(headline + ".", bullets)


def power(stats: dict[str, Any]) -> dict[str, Any]:
    sim = _sim(stats.get("simulated", False))
    unit = "GWh/d"
    if stats.get("period_label"):
        headline = (
            f"Gas-fired generation in the zones held averaged {number(stats['period_avg'], unit)}"
            f" of electricity{sim} over {stats['period_label']}"
        )
    else:
        headline = (
            f"Gas-fired generation in the zones held was {number(stats['latest'], unit)} of "
            f"electricity{sim} on {day(stats['latest_day'])}"
        )
        if stats.get("avg_7") is not None:
            headline += f", against a seven-day average of {number(stats['avg_7'], unit)}"
    bullets = []
    if stats.get("by_zone"):
        name, value = stats["by_zone"][0]
        bullets.append(f"{name} generated the most from gas: {number(value, unit)}{sim}.")
    bullets.append("Electricity output, not gas burned: the gas used depends on plant "
                   "efficiency, which this section does not estimate.")
    if stats.get("state") in {"late", "stale"}:
        bullets.insert(0, f"Newest complete day {day(stats['latest_day'])} ({stats['state']}).")
    return _out(headline + ".", bullets)


def outages(stats: dict[str, Any]) -> dict[str, Any]:
    sim = _sim(stats.get("simulated", False))
    active, total = stats["active"], stats["total"]
    if not total:
        return _out("No active or upcoming outage is reported for the scope.", [])
    headline = f"{active} outage{'s' if active != 1 else ''} active"
    if stats.get("active_gwh"):
        headline += f", removing {number(stats['active_gwh'], 'GWh/d')} in total{sim}"
    upcoming = total - active
    if upcoming:
        headline += f"; {upcoming} more scheduled within {stats['horizon_days']} days"
    bullets = []
    largest = stats.get("largest")
    if largest:
        until = f"until {day(largest['end'])}" if largest.get("end") else "with no end date"
        bullets.append(
            f"The largest is {largest['facility']} ({largest['zone'] or 'zone n/a'}): "
            f"{number(largest['gwh'], 'GWh/d')}{sim}, {until}."
        )
    if stats.get("norway_active"):
        bullets.append(
            f"{stats['norway_active']} of the active outages are in Norway, "
            f"{number(stats.get('norway_gwh'), 'GWh/d')} in total{sim}."
        )
    if stats.get("unconverted"):
        bullets.append(f"{stats['unconverted']} messages give a capacity unit that does not "
                       "convert to GWh/d; they are listed in their own unit.")
    return _out(headline + ".", bullets)


# ------------------------------------------------------------------------------- balance


def balance(stats: dict[str, Any]) -> dict[str, Any]:
    sim = _sim(stats.get("simulated", False))
    unit = "GWh/d"
    if stats.get("period_label"):
        headline = (
            f"The NW Europe supply call averaged {number(stats['period_avg'], unit)}{sim} over "
            f"{stats['period_label']}"
        )
    else:
        headline = (
            f"The NW Europe supply call was {number(stats['call'], unit)}{sim} on "
            f"{day(stats['day'])}: Norway {number(stats['norway'], unit)}, LNG "
            f"{number(stats['lng'], unit)}, storage {number(stats['storage'], unit)} net "
            "withdrawal"
        )
    bullets = []
    if stats.get("forecast_call") is not None:
        bullets.append(
            f"Forecast, not a measurement: {number(stats['forecast_call'], unit)} on "
            f"{day(stats['forecast_day'])} ({stats['forecast_method']})."
        )
    if stats.get("forecast_fill") is not None:
        bullets.append(
            f"Projected storage fill {number(stats['forecast_fill'], '%')} by "
            f"{day(stats['forecast_day'])} on that forecast."
        )
    if stats.get("warning"):
        bullets.append(f"Warning: {stats['warning']}")
    return _out(headline + ".", bullets)


# ------------------------------------------------------------------------------- book


def position(stats: dict[str, Any]) -> dict[str, Any]:
    hubs = stats.get("hubs") or []
    if not hubs:
        return _out("No position in the books this report may see.", [])
    parts = []
    for hub in hubs[:3]:
        today = hub["today"]
        side = "long" if today > 0 else "short" if today < 0 else "flat"
        parts.append(f"{hub['hub']} {side} {number(abs(today), 'MWh/d')}" if side != "flat"
                     else f"{hub['hub']} flat")
    headline = "Net position today: " + "; ".join(parts) + "."
    bullets = []
    for hub in hubs[:2]:
        fm = hub["front_month"]
        side = "long" if fm > 0 else "short" if fm < 0 else "flat"
        bullets.append(
            f"{hub['hub']} {stats['front_month']}: {side} {number(abs(fm), 'MWh/d')} on "
            "average." if side != "flat" else f"{hub['hub']} {stats['front_month']}: flat."
        )
    return _out(headline, bullets)


def pnl(stats: dict[str, Any]) -> dict[str, Any]:
    from eurogas_nexus.application.desk_text import money

    rows = stats.get("hubs") or []
    sim = _sim(stats.get("simulated", False))
    valued = [r for r in rows if r.get("change") is not None]
    if valued:
        parts = [f"{r['hub']} {money(r['change'], r['currency'])}" for r in valued[:3]]
        headline = "Day P&L change on the open position" + sim + ": " + "; ".join(parts) + "."
    elif stats.get("snapshots"):
        headline = "No day P&L change could be computed; the latest imported valuation stands."
    else:
        return _out("No P&L figure is available for the books this report may see.", [])
    bullets = []
    for snap in (stats.get("snapshots") or [])[:2]:
        text = f"{snap['portfolio']}: indicative {money(snap['pnl'], 'GBP')}"
        if snap.get("change") is not None:
            text += f", {money(snap['change'], 'GBP')} since the previous valuation"
        bullets.append(text + _sim(snap.get("simulated", False)) + ".")
    unvalued = [r for r in rows if r.get("change") is None and r.get("reason")]
    if unvalued:
        bullets.append(f"{unvalued[0]['hub']}: {unvalued[0]['reason']}.")
    return _out(headline, bullets)


def limits(stats: dict[str, Any]) -> dict[str, Any]:
    rows = stats.get("rows") or []
    if not rows:
        return _out("No credit line or mandate this report may see.", [])
    breach = [r for r in rows if r["status"] == "breach"]
    watch = [r for r in rows if r["status"] == "watch"]
    headline = (
        f"{len(breach)} limit{'s' if len(breach) != 1 else ''} in breach and {len(watch)} on "
        f"watch, of {len(rows)}."
    )
    bullets = []
    for row in (breach + watch)[:3]:
        used = row.get("utilisation_pct")
        bullets.append(
            f"{row['name']} ({row['kind']}): {row['status']}"
            + (f", {number(used, '%', 0)} used" if used is not None else "")
            + _sim(row.get("simulated", False)) + "."
        )
    return _out(headline, bullets)


def contracts(stats: dict[str, Any]) -> dict[str, Any]:
    rows = stats.get("rows") or []
    if not rows:
        return _out("No supply contract in effect in the books this report may see.", [])
    total = sum(r["mwh_per_day"] for r in rows)
    headline = (
        f"{len(rows)} contract{'s' if len(rows) != 1 else ''} in effect today, "
        f"{number(total, 'MWh/d')} in total."
    )
    bullets = [
        f"{r['name']} at {r['point']}: {number(r['mwh_per_day'], 'MWh/d')}, gas year "
        f"{r['gas_year']}."
        for r in rows[:3]
    ]
    return _out(headline, bullets)


def alerts(stats: dict[str, Any]) -> dict[str, Any]:
    counts = stats["counts"]
    if not counts["open"]:
        return _out("No critical or watch alert is open.", [])
    headline = (
        f"{counts['open']} alert{'s' if counts['open'] != 1 else ''} open: "
        f"{counts['critical']} critical, {counts['warning']} watch."
    )
    bullets = [
        f"{'Critical' if row['severity'] == 'critical' else 'Watch'}: {row['title'].rstrip('.')}"
        f"{_sim(row.get('simulated', False))}."
        for row in stats["items"][:3]
    ]
    return _out(headline, bullets)


# ------------------------------------------------------------------------------- situation


def situation_outage(stats: dict[str, Any]) -> dict[str, Any]:
    sim = _sim(stats.get("simulated", False))
    until = f"until {day(stats['end'])}" if stats.get("end") else "with no end date"
    size = (
        number(stats["gwh"], "GWh/d") if stats.get("gwh") is not None
        else f"{stats.get('capacity')} {stats.get('unit') or ''}".strip()
    )
    headline = (
        f"{stats['facility']} ({stats.get('zone') or 'zone n/a'}): {size} unavailable{sim}, "
        f"{'out since' if stats['status'] == 'active' else 'from'} {day(stats['start'])}, "
        f"{until}."
    )
    bullets = []
    if stats.get("before") is not None and stats.get("after") is not None:
        bullets.append(
            f"Norwegian landings averaged {number(stats['before'], 'GWh/d')} in the seven days "
            f"before and {number(stats['after'], 'GWh/d')} since{sim}: "
            f"{move(stats['after'] - stats['before'], 'GWh/d')}."
        )
    elif stats.get("before") is not None:
        bullets.append(
            f"Norwegian landings averaged {number(stats['before'], 'GWh/d')} in the seven days "
            f"to {day(stats['before_until'])}{sim}; no complete day since the start yet."
        )
    if stats.get("share_pct") is not None:
        bullets.append(
            f"The unavailable capacity is {number(stats['share_pct'], '%', 0)} of that seven-day "
            "average."
        )
    bullets.append(f"Published {day(stats['published'])}, version {stats['version']}; "
                   f"{stats.get('event_type') or 'type not stated'}.")
    return _out(headline, bullets)


def situation_alert(stats: dict[str, Any]) -> dict[str, Any]:
    sim = _sim(stats.get("simulated", False))
    headline = f"{stats['severity'].capitalize()}: {stats['title'].rstrip('.')}{sim}."
    bullets = [stats["message"].rstrip(".") + "." if stats.get("message") else None,
               f"Detected {day(stats['detected'])}, {stats['occurrences']} occurrence"
               f"{'s' if stats['occurrences'] != 1 else ''}; status {stats['status']}."]
    return _out(headline, bullets)
