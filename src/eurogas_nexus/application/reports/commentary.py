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

from eurogas_nexus.application.reports.lang import T, zh

MAX_BULLETS = 3
SIM = " (simulated)"
SIM_ZH = "（模拟）"


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
        return T("unchanged", "持平")
    if zh():
        return f"{'上升' if change > 0 else '下降'}{shown}"
    return f"{'up' if change > 0 else 'down'} {shown}"


def day(value: str | date | None) -> str:
    if value is None:
        return "n/a"
    moment = value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
    return f"{moment.month}月{moment.day}日" if zh() else f"{moment.day} {moment:%b}"


def _versus(value: float, average: float, unit: str) -> str:
    """``above the seven-day average of 2,764 GWh/d`` (the direction stated, not left to infer)."""

    word = "above" if value > average else "below" if value < average else "level with"
    return f"{word} the seven-day average of {number(average, unit)}"


def _sim(flag: bool) -> str:
    return (SIM_ZH if zh() else SIM) if flag else ""


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
        return _out(T("No hub close is held under your licences.", "您的许可下没有枢纽收盘价"
                                                                   "。"), [])
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
    rolled = [r for r in rows if r.get("rolled_from")]
    if period_label and rolled:
        r = rolled[0]
        bullets.append(
            f"The {r['hub']} front month rolled from {r['rolled_from']} to {r['product']} during "
            f"{period_label}, so no change over {period_label} is given; the range is "
            f"{r['product']} only."
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
            headline += f", {_versus(stats['latest'], stats['avg_7'], unit)}"
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
            headline += f", {_versus(stats['latest'], stats['avg_7'], unit)}"
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
    elif "norway_active" in stats:
        bullets.append("No active outage in Norway is among the messages held.")
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
        return _out(T("No position is held in the books you may see.", "您可查看的账簿中没有头寸"
                                                                       "。"),
                    [])
    parts = []
    for hub in hubs[:3]:
        today = hub["today"]
        size = number(abs(today), "MWh/d")
        if zh():
            parts.append(f"{hub['hub']}{'多头' if today > 0 else '空头'}{size}" if today
                         else f"{hub['hub']}持平")
        else:
            parts.append(f"{'long' if today > 0 else 'short'} {size} at {hub['hub']}" if today
                         else f"flat at {hub['hub']}")
    headline = T("The book is " + _and(parts) + " today.", "今日账簿：" + "，".join(parts) + "。")
    bullets = []
    for hub in hubs[:2]:
        fm = hub["front_month"]
        size = number(abs(fm), "MWh/d")
        side = T("long" if fm > 0 else "short", "多头" if fm > 0 else "空头")
        bullets.append(T(
            f"For {stats['front_month']} the {hub['hub']} position averages {size} {side}."
            if fm else f"For {stats['front_month']} the {hub['hub']} position is flat.",
            f"{stats['front_month']}的{hub['hub']}头寸平均为{side}{size}。" if fm
            else f"{stats['front_month']}的{hub['hub']}头寸持平。"))
    return _out(headline, bullets)


def _and(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def pnl(stats: dict[str, Any]) -> dict[str, Any]:
    from eurogas_nexus.application.desk_text import money

    rows = stats.get("hubs") or []
    sim = _sim(stats.get("simulated", False))
    valued = [r for r in rows if r.get("change") is not None]
    if valued:
        def one(r):
            amount = money(abs(r["change"]), r["currency"])
            if zh():
                return f"{r['hub']}{'盈利' if r['change'] >= 0 else '亏损'}{amount}"
            return f"{'gained' if r['change'] >= 0 else 'lost'} {amount} at {r['hub']}"
        parts = [one(r) for r in valued[:3]]
        headline = T(f"The open position {_and(parts)} on the day{sim}.",
                     f"未平仓头寸当日{'，'.join(parts)}{sim}。")
    elif stats.get("snapshots"):
        headline = T("No day P&L change could be computed; the latest imported valuation stands.",
                     "无法计算当日损益变化；沿用最新导入的估值。")
    else:
        return _out(T("No P&L figure is held for the books you may see.",
                      "您可查看的账簿没有损益数据。"), [])
    bullets = []
    for snap in (stats.get("snapshots") or [])[:2]:
        text = T(f"The {snap['portfolio']} valuation is an indicative {money(snap['pnl'], 'GBP')}",
                 f"{snap['portfolio']}的指示性估值为{money(snap['pnl'], 'GBP')}")
        if snap.get("change") is not None:
            text += T(f", {money(snap['change'], 'GBP')} since the previous valuation",
                      f"，较上次估值变化{money(snap['change'], 'GBP')}")
        bullets.append(text + _sim(snap.get("simulated", False)) + T(".", "。"))
    unvalued = [r for r in rows if r.get("change") is None and r.get("reason")]
    if unvalued:
        bullets.append(f"{unvalued[0]['hub']}{T(': ', '：')}{unvalued[0]['reason']}{T('.', '。')}")
    return _out(headline, bullets)


_WORDS = {0: "No", 1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven",
          8: "Eight", 9: "Nine"}


def limits(stats: dict[str, Any]) -> dict[str, Any]:
    rows = stats.get("rows") or []
    if not rows:
        return _out(T("No credit line or mandate is held that you may see.",
                      "没有您可查看的信用额度或授权。"), [])
    breach = [r for r in rows if r["status"] == "breach"]
    watch = [r for r in rows if r["status"] == "watch"]
    headline = T(
        f"{_WORDS.get(len(breach), str(len(breach)))} of {len(rows)} limits "
        f"{'is' if len(breach) == 1 else 'are'} in breach and "
        f"{_WORDS.get(len(watch), str(len(watch))).lower()} on watch.",
        f"{len(rows)}项限额中{len(breach)}项超限，{len(watch)}项处于观察。")
    kinds = {"credit line": T("credit line", "信用额度"), "mandate": T("mandate", "授权")}
    states = {"breach": T("in breach", "超限"), "watch": T("on watch", "观察"),
              "ok": T("within", "正常")}
    bullets = []
    for row in (breach + watch)[:3]:
        used = row.get("utilisation_pct")
        kind = kinds.get(row["kind"], row["kind"])
        state = states.get(row["status"], row["status"])
        if zh():
            bullets.append(f"{row['name']}（{kind}）{state}"
                           + (f"，已使用{number(used, '%', 0)}" if used is not None else "")
                           + _sim(row.get("simulated", False)) + "。")
        else:
            bullets.append(f"The {row['name']} {kind} is {state}"
                           + (f" at {number(used, '%', 0)} used" if used is not None else "")
                           + _sim(row.get("simulated", False)) + ".")
    return _out(headline, bullets)


def contracts(stats: dict[str, Any]) -> dict[str, Any]:
    rows = stats.get("rows") or []
    if not rows:
        return _out(T("No supply contract is in effect in the books you may see.",
                      "您可查看的账簿中没有生效的供应合同。"), [])
    total = sum(r["mwh_per_day"] for r in rows)
    headline = T(
        f"{_WORDS.get(len(rows), str(len(rows)))} supply contract"
        f"{'s are' if len(rows) != 1 else ' is'} in effect today, "
        f"{number(total, 'MWh/d')} in total.",
        f"今日有{len(rows)}份供应合同生效，合计{number(total, 'MWh/d')}。")
    bullets = [
        T(f"{r['name']} delivers {number(r['mwh_per_day'], 'MWh/d')} at {r['point']} "
          f"(gas year {r['gas_year']}).",
          f"{r['name']}在{r['point']}交付{number(r['mwh_per_day'], 'MWh/d')}"
          f"（气年{r['gas_year']}）。")
        for r in rows[:3]
    ]
    return _out(headline, bullets)


def alerts(stats: dict[str, Any]) -> dict[str, Any]:
    counts = stats["counts"]
    if not counts["open"]:
        return _out(T("No critical or watch alert is open.", "没有未关闭的严重或观察级预警。"), [])
    headline = T(
        f"{counts['open']} alert{'s' if counts['open'] != 1 else ''} open: "
        f"{counts['critical']} critical, {counts['warning']} watch.",
        f"{counts['open']}项预警未关闭：{counts['critical']}项严重，{counts['warning']}项观察。")
    bullets = [
        T(f"{'Critical' if row['severity'] == 'critical' else 'Watch'}: "
          f"{row['title'].rstrip('.')}{_sim(row.get('simulated', False))}.",
          f"{'严重' if row['severity'] == 'critical' else '观察'}：{row['title'].rstrip('.')}"
          f"{_sim(row.get('simulated', False))}。")
        for row in stats["items"][:3]
    ]
    return _out(headline, bullets)


# ------------------------------------------------------------------------------- situation


def situation_outage(stats: dict[str, Any]) -> dict[str, Any]:
    sim = _sim(stats.get("simulated", False))
    size = (
        number(stats["gwh"], "GWh/d") if stats.get("gwh") is not None
        else f"{stats.get('capacity')} {stats.get('unit') or ''}".strip()
    )
    zone = f" ({stats['zone']})" if stats.get("zone") else ""
    if zh():
        until = f"至{day(stats['end'])}" if stats.get("end") else "未给出结束日期"
        start = f"自{day(stats['start'])}起" if stats["status"] == "active" else \
            f"将自{day(stats['start'])}起"
        headline = f"{stats['facility']}{zone}{start}不可用{size}{sim}，{until}。"
    else:
        until = f"until {day(stats['end'])}" if stats.get("end") else "with no end date"
        verb = "has" if stats["status"] == "active" else "is to have"
        since = "since" if stats["status"] == "active" else "from"
        headline = (f"{stats['facility']}{zone} {verb} {size} unavailable{sim} {since} "
                    f"{day(stats['start'])}, {until}.")
    bullets = []
    if stats.get("before") is not None and stats.get("after") is not None:
        bullets.append(T(
            f"Norwegian landings averaged {number(stats['before'], 'GWh/d')} in the seven days "
            f"before and {number(stats['after'], 'GWh/d')} since{sim}: "
            f"{move(stats['after'] - stats['before'], 'GWh/d')}.",
            f"挪威到岸量此前七天平均为{number(stats['before'], 'GWh/d')}，此后为"
            f"{number(stats['after'], 'GWh/d')}{sim}："
            f"{move(stats['after'] - stats['before'], 'GWh/d')}。"))
    elif stats.get("before") is not None:
        bullets.append(T(
            f"Norwegian landings averaged {number(stats['before'], 'GWh/d')} in the seven days "
            f"to {day(stats['before_until'])}{sim}; no complete day since the start yet.",
            f"截至{day(stats['before_until'])}的七天挪威到岸量平均为"
            f"{number(stats['before'], 'GWh/d')}{sim}；开始以来尚无完整气日。"))
    if stats.get("share_pct") is not None:
        bullets.append(T(
            f"The unavailable capacity is {number(stats['share_pct'], '%', 0)} of that seven-day "
            "average.", f"不可用容量相当于该七天均值的{number(stats['share_pct'], '%', 0)}。"))
    kind = {"planned": T("planned", "计划"), "unplanned": T("unplanned", "非计划")}.get(
        str(stats.get("event_type") or ""), stats.get("event_type"))
    bullets.append(T(
        f"The operator published the {kind or 'outage'} notice on {day(stats['published'])} "
        f"(version {stats['version']}).",
        f"运营方于{day(stats['published'])}发布{kind or ''}停运通知（第{stats['version']}版）。"))
    return _out(headline, bullets)


def situation_alert(stats: dict[str, Any]) -> dict[str, Any]:
    sim = _sim(stats.get("simulated", False))
    severity = {"critical": T("Critical", "严重"), "warning": T("Watch", "观察")}.get(
        stats["severity"], stats["severity"].capitalize())
    headline = f"{severity}{T(': ', '：')}{stats['title'].rstrip('.')}{sim}{T('.', '。')}"
    bullets = [stats["message"].rstrip(".") + "." if stats.get("message") else None,
               T(f"Detected {day(stats['detected'])}, {stats['occurrences']} occurrence"
                 f"{'s' if stats['occurrences'] != 1 else ''}; status {stats['status']}.",
                 f"{day(stats['detected'])}检测到，共{stats['occurrences']}次；状态：{stats['status']}。")]
    return _out(headline, bullets)
