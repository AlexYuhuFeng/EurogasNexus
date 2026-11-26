"""From what a section read to what a publication shows: facts, exhibits, edited tables, prose.

Each ``derive_<section>`` takes the :class:`~sections.SectionResult` an adapter filled (its
``raw`` holds the series it read) and sets:

- ``facts`` (``facts.fact``), the candidates the editor chooses from;
- ``charts``: numbered-exhibit specs with a declarative title, subtitle, source line, notes and
  their permitted chart types and windows; the series cover the longest window, the renderer
  shows the chosen one;
- ``tables``: body tables of at most ``BODY_ROWS`` rows with units in the column heads;
- ``annex``: the full series behind every exhibit, for the data annex and the CSV download;
- the lead sentence (``headline``) and the paragraph sentences (``bullets``).

Rule prose only states facts the section computed; implications are the engine's own rules
(``implications`` on each fact), so the editor and the checks know what may be said.
"""

from __future__ import annotations

import re
from datetime import date, timedelta

from eurogas_nexus.application.reports import facts as F
from eurogas_nexus.application.reports.commentary import _sim, lose_sentence, number
from eurogas_nexus.application.reports.commentary import day as fday
from eurogas_nexus.application.reports.lang import T, country, zh


def _move(change: float | None, unit: str, digits: int | None = None) -> str:
    from eurogas_nexus.application.reports.commentary import move

    return move(change, unit, digits)


def _compare_clause(f: dict, *, day_word: str | None = None) -> str:
    """``down 0.17 EUR/MWh on the day and up 1.20 EUR/MWh on the week``."""

    c = f["comparisons"]
    unit = c["unit"]
    parts = []
    if zh():
        if c["day"] is not None:
            parts.append(f"{day_word or '较前一日'}{_move(c['day'], unit)}")
        if c["week"] is not None:
            parts.append(f"较一周前{_move(c['week'], unit)}")
        return "，".join(parts)
    if c["day"] is not None:
        parts.append(f"{_move(c['day'], unit)} {day_word or 'on the day'}")
    if c["week"] is not None:
        parts.append(f"{_move(c['week'], unit)} on the week")
    return " and ".join(parts)


def _then(clause: str) -> str:
    """The comma that joins a comparison clause to its sentence, in the report's language."""

    return (f"，{clause}" if zh() else f", {clause}") if clause else ""


def _end() -> str:
    return "。" if zh() else "."


def _year_clause(f: dict, what: str = "a year earlier") -> str | None:
    c = f["comparisons"]
    if c["year"] is None:
        return None
    unit = c["unit"]
    if zh():
        word = "高" if c["year"] > 0 else "低"
        size = (f"{number(abs(c['year']), '', 1)}个百分点" if unit in {"points", "pts"}
                else number(abs(c["year"]), unit))
        return f"较{_ZH_WHAT.get(what, '一年前')}{word}{size}"
    if unit in {"points", "pts"}:
        word = "above" if c["year"] > 0 else "below"
        return f"{number(abs(c['year']), '', 1)} points {word} {what}"
    word = "above" if c["year"] > 0 else "below"
    return f"{number(abs(c['year']), unit)} {word} {what}"


_ZH_WHAT = {"a year earlier": "一年前", "the same day a year earlier": "一年前同日"}


def _period_days(ctx) -> int:
    return (ctx.end - ctx.start).days + 1


def _windows(ctx, family: str) -> tuple[str, tuple[str, ...]]:
    default = F.default_window(ctx.plan.kind, family)
    if family == "storage":
        return default, ("gas_year", "91d")
    if family == "price":
        return default, ("30d", "91d", "365d", "395d")
    return default, ("30d", "91d", "365d", "395d")


def _annex_from_series(caption: str, unit: str, series: dict[str, dict[date, float]],
                       first: date, last: date) -> dict:
    names = list(series)
    days = sorted({d for s in series.values() for d in s if first <= d <= last}, reverse=True)
    rows = [{"day": F.iso(d), **{n: (round(series[n][d], 2) if d in series[n] else None)
                                 for n in names}} for d in days]
    return F.table(f"{caption} ({unit})", [("day", T("Day", "日期"), "date")]
                   + [(n, n, "num") for n in names], rows)


# =========================================================================== prices


#: The hubs a NW Europe gas desk reads first.
BENCHMARKS = frozenset({"TTF", "NBP"})


def derive_prices(result, ctx) -> None:
    raw = result.raw
    facts, exhibits, annex = [], [], []
    by_unit: dict[str, list] = {}
    hubs = raw["hubs"]
    end = ctx.end
    window, permitted = _windows(ctx, "price")
    for hub in hubs:
        series: dict[date, float] = hub["series"]
        contract = hub["contract"]
        last = hub["close_day"]
        same = {d: v for d, v in series.items() if contract.get(d) == contract.get(last)}
        wow = F.change_at(same, last, 7, tolerance=3)
        variation = F.recent_variation(same, last)
        score, reason = F.materiality(hub["day_change"], variation)
        if hub["state"] in {"late", "stale"}:
            score, reason = score * 0.5, reason + "; halved: the close is " + hub["state"]
        if hub["hub"] not in BENCHMARKS:
            # The desk reads TTF and NBP first: another hub leads only on an unusual move
            # (at least one standard deviation of its daily changes).
            unusual = bool(variation) and abs(hub["day_change"] or 0.0) >= variation
            weight = 0.6 if unusual else 0.3
            hub["_quiet"] = not unusual and not ctx.plan.hubs
            score, reason = score * weight, reason + f"; weighted {weight}: not a benchmark hub"
        sim = hub["simulated"]
        f = F.fact(
            f"price.{hub['hub']}", "prices", f"{hub['hub']} {hub['product']}",
            hub["close"], hub["unit"], day=F.iso(last), state=hub["state"], simulated=sim,
            dod=hub["day_change"], wow=wow, yoy=(hub["close"] - hub["year_ago"])
            if hub["year_ago"] is not None else None, years=1 if hub["year_ago"] is not None else 0,
            score=score, reason=reason, spark=F.spark_of(series, last),
            sources=[f"{hub['hub']} closes"], exhibits=[f"fig.prices.{hub['unit']}"],
            sentence="", headline="",
            # A quiet non-benchmark hub stays in the closes table, not At a glance.
            indicator=not hub.get("_quiet"),
        )
        clause = _compare_clause(f)
        f["sentence"] = T(
            f"{hub['hub']} {hub['product']} closed at "
            f"{number(hub['close'], hub['unit'])}{_sim(sim)} on {fday(last)}",
            f"{hub['hub']} {hub['product']} {fday(last)}收于"
            f"{number(hub['close'], hub['unit'])}{_sim(sim)}") + _then(clause) + _end()
        f["headline"] = T(
            f"{hub['hub']} {hub['product']} {_move(hub['day_change'], hub['unit'])} "
            f"at {number(hub['close'], hub['unit'])}{_sim(sim)}",
            f"{hub['hub']} {hub['product']}收于{number(hub['close'], hub['unit'])}{_sim(sim)}，"
            f"日内{_move(hub['day_change'], hub['unit'])}")
        if variation:
            f["implications"].append(
                T(f"The {hub['hub']} move was within the range of its recent daily changes.",
                  f"{hub['hub']}的这一变动处于其近期日变动范围之内。") if score < 1 else
                T(f"The {hub['hub']} move was larger than its typical daily change over the "
                  "last 30 days.", f"{hub['hub']}的这一变动大于其近30天的典型日变动。")
            )
        if hub.get("rolled_from"):
            f["implications"].insert(0, T(
                f"The front month rolled from {hub['rolled_from']} to {hub['product']} during "
                "the period, so no change across the two contracts is given.",
                f"近月合约在此期间由{hub['rolled_from']}换月至{hub['product']}，"
                "因此不给出跨合约的变化。"))
        facts.append(f)
        by_unit.setdefault(hub["unit"], []).append(hub)
    # A spread only between hubs quoted in the same unit (no silent conversion).
    eur = {h["hub"]: h for h in hubs if h["unit"] == "EUR/MWh"}
    if "TTF" in eur:
        for other in ("THE", "PEG", "ZTP", "PSV", "ETF"):
            if other in eur and eur[other]["close_day"] == eur["TTF"]["close_day"]:
                spread = eur[other]["close"] - eur["TTF"]["close"]
                sim = eur[other]["simulated"] or eur["TTF"]["simulated"]
                facts.append(F.fact(
                    f"spread.{other}-TTF", "prices", f"{other}–TTF spread", spread, "EUR/MWh",
                    day=F.iso(eur["TTF"]["close_day"]), state=eur["TTF"]["state"],
                    simulated=sim, score=0.2, reason="level only; no history weighed",
                    sentence=T(f"The {other}–TTF front-month spread was "
                               f"{number(spread, 'EUR/MWh')}{_sim(sim)} on "
                               f"{fday(eur['TTF']['close_day'])}.",
                               f"{fday(eur['TTF']['close_day'])}{other}–TTF近月价差为"
                               f"{number(spread, 'EUR/MWh')}{_sim(sim)}。"),
                    sources=[f"{other} closes", "TTF closes"],
                ))
                break
    for unit, items in by_unit.items():
        longest = end - timedelta(days=F.WINDOWS["395d"] - 1)
        lead = items[0]
        exhibits.append(F.exhibit(
            f"fig.prices.{unit}", "prices", "line",
            title=T(f"{lead['hub']} front month closed at {number(lead['close'], unit)}"
                    f"{_sim(lead['simulated'])} on {fday(lead['close_day'])}",
                    f"{lead['hub']}近月合约{fday(lead['close_day'])}收于"
                    f"{number(lead['close'], unit)}{_sim(lead['simulated'])}"),
            subtitle=T(f"Front-month daily closes, {unit}", f"近月合约每日收盘价，{unit}"),
            unit=unit,
            # Benchmarks and hubs that moved unusually are drawn (four lines at most); every
            # hub stays in the closes table and the annex.
            series=[{"name": h["hub"], "points": F.series_points(h["series"], longest, end)}
                    for h in ([h for h in items if not h.get("_quiet")] or items)[:4]],
            types=("line", "step"), windows=permitted, window=window,
            simulated=any(h["simulated"] for h in items),
            notes=T("The front month rolls at each month end; the line joins the contracts.",
                    "近月合约在每月月底换月；曲线连接相邻合约。"),
        ))
        annex.append(_annex_from_series(T("Front-month closes", "近月收盘价"), unit,
                                        {h["hub"]: h["series"] for h in items},
                                        F.window_start(window, end), end))
    rows = [{"hub": h["hub"], "product": h["product"], "unit": h["unit"], "close": h["close"],
             "close_day": F.iso(h["close_day"]), "day": h["day_change"],
             "week": next((f["comparisons"]["week"] for f in facts
                           if f["key"] == f"price.{h['hub']}"), None),
             "year": h["year_ago"], "simulated": h["simulated"], "state": h["state"],
             "period_change": h.get("period_change"), "high": h.get("high"),
             "low": h.get("low"), "average": h.get("average")}
            for h in hubs[: F.BODY_ROWS]]
    columns = [("hub", T("Hub", "枢纽"), "text"), ("product", T("Contract", "合约"), "text"),
               ("unit", T("Unit", "单位"), "text"), ("close", T("Close", "收盘"), "num"),
               ("day", T("Day", "日变化"), "signed")]
    if ctx.period_label:
        columns += [("period_change", T("Period", "期间变化"), "signed"),
                    ("average", T("Average", "均值"), "num"), ("high", T("High", "最高"), "num"),
                    ("low", T("Low", "最低"), "num")]
    else:
        columns += [("week", T("Week", "周变化"), "signed")]
    columns.append(("year", T("Year earlier", "一年前"), "num"))
    conversion_notes = _convert_closes(result, ctx, rows, columns)
    result.tables = [F.table(
        T("Front-month closes", "近月收盘价"), columns, rows,
        source=F.source_line("prices", result.simulated),
        notes=T("Day and week: change in the hub's own unit; year earlier: the front month's "
                "close on the same day a year earlier (a different contract).",
                "日变化与周变化以该枢纽的报价单位计；一年前为一年前同日近月合约的收盘价"
                "（不同合约）。") + conversion_notes)]
    result.facts, result.charts, result.annex = facts, exhibits, annex
    _prose(result, facts)


# =========================================================================== landings


def derive_pipeline(result, ctx) -> None:
    raw = result.raw
    total: dict[date, float] = raw["total"]
    norway, uk = raw["norway"], raw["uk"]
    latest: date = raw["latest"]
    sim = result.simulated
    end = ctx.end
    variation = F.recent_variation(total, latest)
    dod = F.change_at(total, latest, 1)
    wow = F.change_at(total, latest, 7)
    prior = F.same_day_last_year(latest)
    yoy = total[latest] - total[prior] if prior in total else None
    score, reason = F.materiality(dod, variation)
    if yoy is not None and total[prior]:
        share = abs(yoy) / total[prior] * 10
        if share > score:
            score, reason = round(share, 2), f"{abs(yoy) / total[prior]:.0%} from a year earlier"
    if raw["state"] in {"late", "stale"}:
        score, reason = score * 0.7, reason + f"; reduced: data {raw['state']}"
    years = F.years_held(total, latest)
    f = F.fact("landings", "pipeline_supply", T("Norwegian pipeline landings", "挪威管道到岸量"),
               total[latest],
               "GWh/d", day=F.iso(latest), state=raw["state"], simulated=sim, dod=dod, wow=wow,
               yoy=yoy, years=years, score=score, reason=reason,
               spark=F.spark_of(total, latest), sources=["Physical flows at the landing points"],
               exhibits=["fig.landings.total", "fig.landings.split"], sentence="")
    clause = _compare_clause(f)
    f["sentence"] = T(f"Norwegian pipeline landings were {number(total[latest], 'GWh/d')}"
                      f"{_sim(sim)} on {fday(latest)}",
                      f"{fday(latest)}挪威管道到岸量为{number(total[latest], 'GWh/d')}"
                      f"{_sim(sim)}") + _then(clause) + _end()
    f["headline"] = T(f"Norwegian landings {_move(dod, 'GWh/d')} at "
                      f"{number(total[latest], 'GWh/d')}",
                      f"挪威到岸量{number(total[latest], 'GWh/d')}，日内{_move(dod, 'GWh/d')}")
    year = _year_clause(f, "the same day a year earlier")
    if year:
        f["implications"].append(T(f"Flows were {year}.", f"流量{year}。"))
    facts = [f]
    if latest in norway and latest in uk:
        facts.append(F.fact(
            "landings.split", "pipeline_supply", T("Landings by scope", "按到岸范围"),
            norway[latest], "GWh/d",
            day=F.iso(latest), state=raw["state"], simulated=sim, indicator=False,
            score=0.1, reason="composition",
            sentence=T(f"Continental terminals took {number(norway[latest], 'GWh/d')} and UK "
                       f"terminals, which also land UK shelf gas, "
                       f"{number(uk[latest], 'GWh/d')}{_sim(sim)}.",
                       f"欧洲大陆终端接收{number(norway[latest], 'GWh/d')}，英国终端（同时接收英国"
                       f"大陆架天然气）接收{number(uk[latest], 'GWh/d')}{_sim(sim)}。"),
            sources=["Physical flows at the landing points"]))
    if ctx.period_label and raw.get("period_avg") is not None:
        facts.append(F.fact(
            "landings.period", "pipeline_supply", T("Landings, period average", "到岸量，期间均值"),
            raw["period_avg"],
            "GWh/d", day=F.iso(latest), state=raw["state"], simulated=sim, indicator=False,
            score=score + 0.1, reason="period aggregate",
            sentence=T(f"Over {raw['period_label']} landings averaged "
                       f"{number(raw['period_avg'], 'GWh/d')}{_sim(sim)}"
                       + (f", {_move(raw['period_avg'] - raw['previous_avg'], 'GWh/d')} on the "
                          "period before" if raw.get("previous_avg") is not None else "") + ".",
                       f"期间内到岸量平均为{number(raw['period_avg'], 'GWh/d')}{_sim(sim)}"
                       + (f"，较上一期间{_move(raw['period_avg'] - raw['previous_avg'], 'GWh/d')}"
                          if raw.get("previous_avg") is not None else "") + "。")))
    window, permitted = _windows(ctx, "flow")
    longest = end - timedelta(days=394)
    context = F.shifted_year(total, longest, end)
    exhibits = [
        F.exhibit("fig.landings.total", "pipeline_supply", "line",
                  title=T(f"Landings {_move(dod, 'GWh/d')} to {number(total[latest], 'GWh/d')}"
                          f"{_sim(sim)} on {fday(latest)}",
                          f"{fday(latest)}到岸量为{number(total[latest], 'GWh/d')}{_sim(sim)}，"
                          f"日内{_move(dod, 'GWh/d')}"),
                  subtitle=T("Norwegian pipeline landings, GWh/d, against the same days a year "
                             "earlier" + (f" ({years} prior year held)" if years else ""),
                             "挪威管道到岸量，GWh/d，对比一年前同期"
                             + (f"（持有{years}年历史）" if years else "")),
                  unit="GWh/d",
                  series=[{"name": T("This year", "今年"),
                           "points": F.series_points(total, longest, end)}]
                  + ([{"name": T("Year earlier", "去年"), "points": context, "context": True}]
                     if context else []),
                  types=("line",), windows=permitted, window=window, simulated=sim, half=True),
        F.exhibit("fig.landings.split", "pipeline_supply", "stacked_area",
                  title=T("Continental terminals take most of the gas",
                          "欧洲大陆终端接收大部分天然气"),
                  subtitle=T("Landings by terminal scope, GWh/d", "按终端范围的到岸量，GWh/d"),
                  unit="GWh/d",
                  series=[{"name": T("Continental", "大陆"),
                           "points": F.series_points(norway, longest, end)},
                          {"name": T("UK terminals", "英国"),
                           "points": F.series_points(uk, longest, end)}],
                  types=("stacked_area", "stacked_bar"), windows=permitted, window=window,
                  simulated=sim, half=True,
                  notes=T("UK terminals carry UK shelf gas with Norwegian gas.",
                          "英国终端同时接收英国大陆架天然气与挪威天然气。")),
    ]
    if latest in norway and latest in uk and norway[latest] < uk[latest]:
        exhibits[1]["title"] = T("UK terminals take more gas than the continental terminals",
                                 "英国终端接收的天然气多于欧洲大陆终端")
    days = [d for d in sorted(total, reverse=True) if d <= end][:7]
    result.tables = [F.table(
        T("Landings, last seven complete gas days (GWh/d)", "到岸量，最近七个完整燃气日（GWh/d）"),
        [("day", T("Gas day", "燃气日"), "date"),
         ("continent", T("Continental", "欧洲大陆"), "num"),
         ("uk", T("UK terminals", "英国终端"), "num"), ("total", T("Total", "合计"), "num")],
        [{"day": F.iso(d), "continent": round(norway.get(d, 0.0), 1),
          "uk": round(uk.get(d, 0.0), 1), "total": round(total[d], 1), "simulated": sim}
         for d in days],
        source=F.source_line("pipeline_supply", sim))]
    result.annex = [_annex_from_series(T("Norwegian landings", "挪威到岸量"), "GWh/d",
                                       {T("Continental", "欧洲大陆"): norway,
                                        T("UK terminals", "英国终端"): uk,
                                        T("Total", "合计"): total},
                                       F.window_start(window, end), end)]
    result.facts, result.charts = facts, exhibits
    _prose(result, facts)


# =========================================================================== LNG


def derive_lng(result, ctx) -> None:
    raw = result.raw
    total: dict[date, float] = raw["total"]
    by_day = raw["by_day"]
    latest: date = raw["latest"]
    sim = result.simulated
    end = ctx.end
    dod = F.change_at(total, latest, 1)
    wow = F.change_at(total, latest, 7)
    prior = F.same_day_last_year(latest)
    yoy = total[latest] - total[prior] if prior in total else None
    score, reason = F.materiality(dod, F.recent_variation(total, latest))
    if raw["state"] in {"late", "stale"}:
        score, reason = score * 0.7, reason + f"; reduced: data {raw['state']}"
    years = F.years_held(total, latest)
    f = F.fact("lng", "lng", T("LNG send-out", "LNG 气化外输"), total[latest], "GWh/d",
               day=F.iso(latest),
               state=raw["state"], simulated=sim, dod=dod, wow=wow, yoy=yoy, years=years,
               score=score, reason=reason, spark=F.spark_of(total, latest),
               sources=["LNG send-out"], exhibits=["fig.lng.country"], sentence="")
    clause = _compare_clause(f)
    f["sentence"] = T(f"LNG send-out across NW Europe was {number(total[latest], 'GWh/d')}"
                      f"{_sim(sim)} on {fday(latest)}",
                      f"{fday(latest)}西北欧 LNG 气化外输量为{number(total[latest], 'GWh/d')}"
                      f"{_sim(sim)}") + _then(clause) + _end()
    f["headline"] = T(f"LNG send-out {_move(dod, 'GWh/d')} at {number(total[latest], 'GWh/d')}",
                      f"LNG 外输{number(total[latest], 'GWh/d')}，日内{_move(dod, 'GWh/d')}")
    year = _year_clause(f, "the same day a year earlier")
    if year:
        f["implications"].append(T(f"Send-out was {year}.", f"外输量{year}。"))
    facts = [f]
    top = sorted(by_day[latest].items(), key=lambda kv: -kv[1])
    if top:
        facts.append(F.fact("lng.top", "lng", T(f"LNG send-out, {country(top[0][0])}",
                                                f"LNG 外输，{country(top[0][0])}"),
                            top[0][1], "GWh/d",
                            day=F.iso(latest), state=raw["state"], simulated=sim,
                            indicator=False, score=0.1, reason="composition",
                            sentence=T(f"{country(top[0][0])} terminals sent out "
                                       f"{number(top[0][1], 'GWh/d')}{_sim(sim)}, the most of "
                                       "any country.",
                                       f"{country(top[0][0])}终端外输{number(top[0][1], 'GWh/d')}"
                                       f"{_sim(sim)}，为各国之首。"),
                            sources=["LNG send-out"]))
    if raw.get("left_out"):
        left = ", ".join(fday(d) for d in raw["left_out"][:3])
        facts.append(F.fact("lng.partial", "lng", T("LNG days left out", "未计入的 LNG 日"), None,
                            "", day=F.iso(latest),
                            state="late", indicator=False, score=0.05, reason="data note",
                            sentence=T(f"Days not yet reported by every country ({left}) are "
                                       "left out.", f"尚未由所有国家报告的日期（{left}）未计入。")))
    window, permitted = _windows(ctx, "flow")
    longest = end - timedelta(days=394)
    countries = [c for c, _ in top] or sorted({c for d in by_day for c in by_day[d]})
    days_all = sorted(d for d in by_day if longest <= d <= end and d in total)
    exhibits = [F.exhibit(
        "fig.lng.country", "lng", "stacked_bar",
        title=(T(f"{country(top[0][0])} terminals led NW Europe send-out on {fday(latest)}",
                 f"{fday(latest)}{country(top[0][0])}终端领先西北欧外输") if top
               else T("LNG send-out", "LNG 气化外输")),
        subtitle=T("LNG send-out by country, GWh/d", "按国家的 LNG 气化外输，GWh/d"),
        unit="GWh/d",
        series=[{"name": c, "points": [[F.iso(d), round(by_day[d].get(c, 0.0), 1)]
                                       for d in days_all]} for c in countries],
        types=("stacked_bar", "stacked_area"), windows=permitted, window=window,
        simulated=sim, half=True)]
    context = F.shifted_year(total, longest, end)
    exhibits.append(F.exhibit(
        "fig.lng.total", "lng", "line",
        title=(T(f"Send-out {('above' if (yoy or 0) > 0 else 'below')} the same days a year "
                 "earlier", f"外输量{'高于' if (yoy or 0) > 0 else '低于'}一年前同期")
               if yoy is not None else T("LNG send-out over the window", "期间内 LNG 外输")),
        subtitle=T("LNG send-out, NW Europe total, GWh/d"
                   + (f"; context: {years} prior year held" if years else ""),
                   "西北欧 LNG 外输合计，GWh/d" + (f"；对照：持有{years}年历史" if years else "")),
        unit="GWh/d",
        series=[{"name": T("This year", "今年"), "points": F.series_points(total, longest, end)}]
        + ([{"name": T("Year earlier", "去年"), "points": context, "context": True}]
           if context else []),
        types=("line",), windows=permitted, window=window, simulated=sim, half=True))
    result.tables = [F.table(
        T(f"Send-out by country on {fday(latest)} (GWh/d)", f"{fday(latest)}按国家外输（GWh/d）"),
        [("country", T("Country", "国家"), "text"), ("value", T("Send-out", "外输"), "num")],
        [{"country": c, "value": round(v, 1), "simulated": sim} for c, v in top[: F.BODY_ROWS]],
        source=F.source_line("lng", sim))]
    result.annex = [_annex_from_series(
        T("LNG send-out by country", "按国家的 LNG 外输"), "GWh/d",
        {c: {d: by_day[d].get(c, 0.0) for d in days_all} for c in countries},
        F.window_start(window, end), end)]
    result.facts, result.charts = facts, exhibits
    _prose(result, facts)


# =========================================================================== storage


def derive_storage(result, ctx) -> None:
    raw = result.raw
    fill: dict[date, float] = raw["fill"]
    prev: dict[date, float] = raw["previous"]
    latest: date = raw["latest"]
    sim = result.simulated
    end = ctx.end
    dod = F.change_at(fill, latest, 1)
    wow = F.change_at(fill, latest, 7)
    yoy = fill[latest] - prev[latest] if latest in prev else None
    z, why = F.materiality(dod, F.recent_variation(fill, latest))
    score, reason = z, why
    if yoy is not None and abs(yoy) / 5 > score:
        score, reason = round(abs(yoy) / 5, 2), f"{abs(yoy):.1f} points from a year earlier " \
                                                "(5 points weighs 1)"
    f = F.fact("storage.fill", "storage", T("NW Europe storage fill", "西北欧储气率"), fill[latest],
               "%",
               day=F.iso(latest), state=raw["state"], simulated=sim, dod=dod, wow=wow, yoy=yoy,
               change_unit="points", years=1 if yoy is not None else 0, score=score,
               reason=reason, spark=F.spark_of(fill, latest), sources=["Storage inventory"],
               exhibits=["fig.storage.season"], sentence="")
    year = _year_clause(f, "a year earlier")
    moved = wow is not None and abs(wow) >= 0.05
    if zh():
        week = (f"，七天内{'上升' if wow > 0 else '下降'}{number(abs(wow), '', 1)}个百分点"
                if moved else "")
        f["sentence"] = (f"{fday(latest)}西北欧储气率为{number(fill[latest], '%')}{_sim(sim)}"
                         + (f"，{year}" if year else "") + week + "。")
        f["headline"] = (f"储气率{number(fill[latest], '%')}，"
                         + (year if year else "无一年前可比数据"))
    else:
        week = (f", having {'risen' if wow > 0 else 'fallen'} {number(abs(wow), '', 1)} points "
                "in seven days") if moved else ""
        f["sentence"] = (f"NW Europe storage was {number(fill[latest], '%')} full{_sim(sim)} on "
                         f"{fday(latest)}" + (f", {year}" if year else "") + week + ".")
        f["headline"] = (f"Storage {number(fill[latest], '%')} full, "
                         + (year if year else "no year-earlier comparison held"))
    if yoy is not None:
        f["implications"].append(
            T("Stocks are lower than a year earlier at this point of the season.",
              "库存低于一年前同期水平。") if yoy < 0 else
            T("Stocks are higher than a year earlier at this point of the season.",
              "库存高于一年前同期水平。"))
    facts = [f]
    if raw.get("inventory") is not None:
        inv = number(raw["inventory"], "TWh", 1)
        facts.append(F.fact("storage.inventory", "storage", T("Storage inventory", "储气库存"),
                            raw["inventory"], "TWh", day=F.iso(latest), state=raw["state"],
                            simulated=sim, indicator=False, score=0.1, reason="level",
                            sentence=T(f"Facilities that publish a working capacity held "
                                       f"{inv}{_sim(sim)}.",
                                       f"公布工作容量的储气设施共持有{inv}{_sim(sim)}。"),
                            sources=["Storage inventory"]))
    if raw.get("target"):
        tgt = number(raw["target"], "%", 0)
        facts.append(F.fact("storage.target", "storage", T("EU filling target", "欧盟充注目标"),
                            raw["target"], "%",
                            day=F.iso(latest), state="current", indicator=False, score=0.05,
                            reason="reference",
                            sentence=T(f"The EU filling target is {tgt}.", f"欧盟充注目标为{tgt}"
                                                                           f"。")))
    window, permitted = _windows(ctx, "storage")
    first = F.window_start("gas_year", end) - timedelta(days=90)
    gas_year = F.window_start("gas_year", end)
    label_now = f"{gas_year.year}/{str(gas_year.year + 1)[2:]}"
    label_prev = f"{gas_year.year - 1}/{str(gas_year.year)[2:]}"
    exhibits = [F.exhibit(
        "fig.storage.season", "storage", "line",
        title=T(f"Storage {number(fill[latest], '%')} full{_sim(sim)}, "
                + (year if year else "no year-earlier comparison held"),
                f"储气率{number(fill[latest], '%')}{_sim(sim)}，"
                + (year if year else "无一年前可比数据")),
        subtitle=T(f"NW Europe storage fill, % of working capacity; gas year {label_now} against "
                   f"{label_prev} (one prior year held)",
                   f"西北欧储气率，占工作容量百分比；{label_now}气年对比{label_prev}（持有一年历史）"),
        unit="%",
        series=[{"name": label_now, "points": F.series_points(fill, first, end)},
                {"name": label_prev, "points": F.series_points(prev, first, end),
                 "context": True}],
        types=("line",), windows=permitted, window=window, simulated=sim,
        reference_lines=[{"label": T(f"EU target {raw['target']:.0f}%",
                                     f"欧盟目标 {raw['target']:.0f}%"), "value": raw["target"]}]
        if raw.get("target") else [],
        notes=T("The prior gas year is placed on this year's dates.", "上一气年按今年日期对齐。"))]
    days = [d for d in sorted(fill, reverse=True) if d <= end][:7]
    result.tables = [F.table(
        T("Storage fill, last seven gas days (%)", "储气率，最近七个燃气日（%）"),
        [("day", T("Gas day", "燃气日"), "date"), ("fill", T("Fill", "储气率"), "num"),
         ("prev", T("Year earlier", "一年前"), "num"),
         ("diff", T("Difference (points)", "差值（百分点）"), "signed")],
        [{"day": F.iso(d), "fill": fill[d], "prev": prev.get(d),
          "diff": None if d not in prev else round(fill[d] - prev[d], 2), "simulated": sim}
         for d in days],
        source=F.source_line("storage", sim))]
    result.annex = [_annex_from_series(T("Storage fill", "储气率"), "%", {label_now: fill,
                                                           label_prev: prev},
                                       F.window_start("gas_year", end), end)]
    result.facts, result.charts = facts, exhibits
    _prose(result, facts)


# =========================================================================== power


#: The gas-for-power read's default plant efficiency (``/api/market/gas-for-power``).
GAS_EFFICIENCY = 0.50


def derive_power(result, ctx) -> None:
    from eurogas_nexus.domain.power.gas_for_power import SystemHour, implied_gas_burn_mwh_th

    raw = result.raw
    total: dict[date, float] = raw["total"]
    by_zone = raw["by_day"]
    latest: date = raw["latest"]
    sim = result.simulated
    end = ctx.end
    dod = F.change_at(total, latest, 1)
    wow = F.change_at(total, latest, 7)
    score, reason = F.materiality(dod, F.recent_variation(total, latest))
    if raw["state"] in {"late", "stale"}:
        score, reason = score * 0.7, reason + f"; reduced: data {raw['state']}"
    f = F.fact("power.gen", "power_burn", T("Gas-fired generation", "燃气发电量"), total[latest],
               "GWh/d",
               day=F.iso(latest), state=raw["state"], simulated=sim, dod=dod, wow=wow,
               score=score, reason=reason, spark=F.spark_of(total, latest),
               sources=["Generation by fuel (gas)"], exhibits=["fig.power.zone"], sentence="")
    clause = _compare_clause(f)
    f["sentence"] = T(f"Gas-fired plants generated {number(total[latest], 'GWh/d')} of "
                      f"electricity{_sim(sim)} on {fday(latest)}",
                      f"{fday(latest)}燃气电厂发电{number(total[latest], 'GWh/d')}{_sim(sim)}"
                      ) + _then(clause) + _end()
    f["headline"] = T(f"Gas-fired generation {_move(dod, 'GWh/d')} at "
                      f"{number(total[latest], 'GWh/d')}",
                      f"燃气发电{number(total[latest], 'GWh/d')}，日内{_move(dod, 'GWh/d')}")
    burn = {d: implied_gas_burn_mwh_th(SystemHour(load_mw=0.0, gas_generation_mw=v * 1000 / 24),
                                       hours=24.0, efficiency=GAS_EFFICIENCY)[0] / 1000
            for d, v in total.items()}
    facts = [f, F.fact(
        "power.burn", "power_burn", T("Implied gas burn for power", "发电隐含燃气消耗"),
        burn[latest], "GWh/d",
        day=F.iso(latest), state=raw["state"], simulated=sim,
        dod=F.change_at(burn, latest, 1), wow=F.change_at(burn, latest, 7), score=score * 0.5,
        reason="derived from generation at a stated efficiency",
        sentence=T(f"At an assumed {GAS_EFFICIENCY:.0%} plant efficiency, that output implies "
                   f"about {number(burn[latest], 'GWh/d')} of gas burn{_sim(sim)}, an estimate "
                   "rather than a measurement.",
                   f"按{GAS_EFFICIENCY:.0%}的假定电厂效率，该发电量对应约"
                   f"{number(burn[latest], 'GWh/d')}的燃气消耗{_sim(sim)}，为估算值而非实测。"),
        spark=F.spark_of(burn, latest), sources=["Generation by fuel (gas)"])]
    window, permitted = _windows(ctx, "flow")
    longest = end - timedelta(days=394)
    zones = sorted({z for d in by_zone for z in by_zone[d]})
    days_all = sorted(d for d in by_zone if longest <= d <= end and d in total)
    exhibits = [F.exhibit(
        "fig.power.zone", "power_burn", "stacked_bar",
        title=T(f"Gas-fired output {_move(dod, 'GWh/d')} to {number(total[latest], 'GWh/d')}"
                f"{_sim(sim)}",
                f"燃气发电{number(total[latest], 'GWh/d')}{_sim(sim)}，日内{_move(dod, 'GWh/d')}"),
        subtitle=T("Electricity generated from gas by bidding zone, GWh/d (UTC days)",
                   "按竞价区的燃气发电量，GWh/d（UTC 日）"),
        unit="GWh/d",
        series=[{"name": z, "points": [[F.iso(d), round(by_zone[d].get(z, 0.0), 1)]
                                       for d in days_all]} for z in zones],
        types=("stacked_bar", "stacked_area"), windows=permitted, window=window, simulated=sim,
        notes=T(f"Implied gas burn = generation / {GAS_EFFICIENCY:.0%} efficiency; not measured.",
                f"隐含燃气消耗 = 发电量 / {GAS_EFFICIENCY:.0%} 效率；非实测。"))]
    top = sorted(by_zone[latest].items(), key=lambda kv: -kv[1])
    result.tables = [F.table(
        T(f"Gas-fired generation and implied burn on {fday(latest)} (GWh/d)",
          f"{fday(latest)}燃气发电量与隐含消耗（GWh/d）"),
        [("zone", T("Zone", "区域"), "text"), ("gen", T("Generation", "发电量"), "num"),
         ("burn", T("Implied gas burn", "隐含燃气消耗"), "num")],
        [{"zone": z, "gen": round(v, 1), "burn": round(v / GAS_EFFICIENCY, 1), "simulated": sim}
         for z, v in top[: F.BODY_ROWS]],
        source=F.source_line("power_burn", sim),
        notes=T(f"Implied burn assumes {GAS_EFFICIENCY:.0%} efficiency.",
                f"隐含消耗按{GAS_EFFICIENCY:.0%}效率计算。"))]
    result.annex = [_annex_from_series(T("Gas-fired generation", "燃气发电量"), "GWh/d",
                                       {T("Generation", "发电量"): total,
                                        T("Implied burn", "隐含消耗"): burn},
                                       F.window_start(window, end), end)]
    result.facts, result.charts = facts, exhibits
    _prose(result, facts)


# =========================================================================== outages


def _zone(row: dict) -> str:
    """" (NBP (GB))" after an asset's name, or nothing when the message names no zone."""

    return f" ({row['zone']})" if row.get("zone") else ""


_OPERATOR_CODE = re.compile(r"\s*\([A-Z]{2}-[A-Z]{3}-\d{4}\)")
_COUNT_WORDS = {1: "One", 2: "Two", 3: "Three", 4: "Four", 5: "Five", 6: "Six", 7: "Seven",
                8: "Eight", 9: "Nine"}


def derive_outages(result, ctx) -> None:
    raw = result.raw
    rows = raw["rows"]
    sim = result.simulated
    landings = (ctx.cache.get("landings_latest") or 4000.0)
    facts = []
    active = [r for r in rows if r["status"] == "active" and r["gwh"]]
    offline = sum(r["gwh"] for r in active)
    largest = max(active, key=lambda r: r["gwh"]) if active else None
    count = len(active)
    counted = (_COUNT_WORDS.get(count, str(count)) + (" outages were" if count != 1
                                                      else " outage was"))
    detail = ""
    if largest is not None and count > 1:
        if zh():
            until = f"，至{fday(largest['end'])}" if largest.get("end") else ""
            detail = (f"；其中最大一处为{largest['facility']}{_zone(largest)}，"
                      f"不可用{number(largest['gwh'], 'GWh/d')}{until}")
        else:
            until = f" until {fday(largest['end'])}" if largest.get("end") else ""
            detail = (f"; the largest, {largest['facility']}{_zone(largest)}, "
                      f"has {number(largest['gwh'], 'GWh/d')} unavailable{until}")
    facts.append(F.fact(
        "outages.offline", "outages", T("Capacity offline (REMIT)", "停运容量（REMIT）"), offline,
        "GWh/d",
        # Capacity offline is weighed on the same scale as one outage (10 x its share of the
        # latest Norwegian landings): 5% of landings offline weighs as much as a move of half
        # a standard deviation, 15% outweighs a routine one-day change in storage withdrawal.
        day=F.iso(ctx.today), state=raw["state"], simulated=sim,
        score=round(min(offline / landings * 10, 6.0), 2),
        reason=f"{offline / landings:.0%} of the latest Norwegian landings offline",
        sentence=T(f"{counted} active on {fday(ctx.today)}, removing "
                   f"{number(offline, 'GWh/d')} in total{_sim(sim)}{detail}.",
                   f"{fday(ctx.today)}有{count}处停运处于活跃状态，合计减少"
                   f"{number(offline, 'GWh/d')}{_sim(sim)}{detail}。"),
        headline=T(f"Outages remove {number(offline, 'GWh/d')}"
                   + (f", {number(largest['gwh'], 'GWh/d')} of it at {largest['facility']}"
                      if largest is not None and count > 1 else ""),
                   f"停运减少{number(offline, 'GWh/d')}"
                   + (f"，其中{largest['facility']}占{number(largest['gwh'], 'GWh/d')}"
                      if largest is not None and count > 1 else "")),
        sources=["REMIT urgent market messages"], exhibits=["tab.outages"]))
    for index, r in enumerate(sorted(active, key=lambda r: -r["gwh"])[:3], start=1):
        if zh():
            until = f"至{fday(r['end'])}" if r.get("end") else "未给出结束日期"
        else:
            until = f"until {fday(r['end'])}" if r.get("end") else "with no end date"
        facts.append(F.fact(
            f"outage.{index}", "outages", T(f"Outage: {r['facility']}", f"停运：{r['facility']}"),
            r["gwh"], "GWh/d",
            day=F.iso(r["start"][:10]), state=raw["state"], simulated=sim, indicator=False,
            score=min(r["gwh"] / landings * 10, 6.0),
            reason=f"{r['gwh'] / landings:.0%} of the latest Norwegian landings offline",
            sentence=T(f"{r['facility']}{_zone(r)} has "
                       f"{number(r['gwh'], 'GWh/d')} unavailable{_sim(sim)} since "
                       f"{fday(r['start'])}, {until}.",
                       f"{r['facility']}{_zone(r)}自{fday(r['start'])}起不可用"
                       f"{number(r['gwh'], 'GWh/d')}{_sim(sim)}，{until}。"),
            headline=T(f"{r['facility']} outage removes {number(r['gwh'], 'GWh/d')}",
                       f"{r['facility']}停运减少{number(r['gwh'], 'GWh/d')}"),
            sources=["REMIT urgent market messages"]))
    starting = sorted([r for r in rows if r["status"] == "scheduled" and r["gwh"]],
                      key=lambda r: r["start"])[:3]
    for index, r in enumerate(starting, start=1):
        facts.append(F.fact(
            f"outage.next.{index}", "outages",
            T(f"Scheduled: {r['facility']}", f"计划停运：{r['facility']}"), r["gwh"], "GWh/d",
            day=F.iso(r["start"][:10]), state=raw["state"], simulated=sim, indicator=False,
            scheduled=True, score=min(r["gwh"] / landings * 3, 2.0), reason="scheduled event",
            sentence=lose_sentence(r["facility"], number(r["gwh"], "GWh/d") + _sim(sim),
                                  r["start"], r.get("end")),
            sources=["REMIT urgent market messages"]))
    ended = [r for r in rows if r["status"] == "ended" and r["gwh"]]
    if ended:
        facts.append(F.fact(
            "outages.ended", "outages", T("Outages ended in the period", "期间内结束的停运"),
            sum(r["gwh"] for r in ended), "GWh/d", day=F.iso(ctx.end), state=raw["state"],
            simulated=sim, indicator=False, score=0.3, reason="ended in period",
            sentence=T(f"{len(ended)} outage{'s' if len(ended) != 1 else ''} that removed "
                       f"{number(sum(r['gwh'] for r in ended), 'GWh/d')} ended during "
                       f"{ctx.period_label or 'the period'}.",
                       f"期间内有{len(ended)}处停运结束，共曾减少"
                       f"{number(sum(r['gwh'] for r in ended), 'GWh/d')}。"),
            sources=["REMIT urgent market messages"]))
    if raw.get("norway_active") == 0:
        facts.append(F.fact("outages.norway", "outages", T("Norwegian outages", "挪威停运"), 0.0,
                            "outages", day=F.iso(ctx.today), state=raw["state"], indicator=False,
                            score=0.05, reason="absence noted",
                            sentence=T("No outage is reported at a Norwegian field, plant, "
                                       "pipeline or landing terminal.",
                                       "挪威油气田、处理厂、管道或登陆终端均无停运报告。")))
    order = {"active": 0, "scheduled": 1, "ended": 2}
    ranked = sorted(rows, key=lambda r: (order.get(r["status"], 3), -(r["gwh"] or 0.0)))
    status = {"active": T("active", "活跃"), "scheduled": T("scheduled", "计划"),
              "ended": T("ended", "已结束")}
    result.tables = [F.table(
        T("Outage schedule, largest active first", "停运时间表，按活跃停运规模排序"),
        [("facility", T("Asset", "资产"), "text"), ("operator", T("Operator", "运营方"), "text"),
         ("zone", T("Zone", "区域"), "text"), ("start", T("Start", "开始"), "datetime"),
         ("end", T("End", "结束"), "datetime"),
         ("gwh", T("Offline (GWh/d)", "停运（GWh/d）"), "num"),
         ("status_label", T("Status", "状态"), "text")],
        # The operator's EIC-style code is in the annex and the CSV; the body prints the name.
        [{**r, "operator": _OPERATOR_CODE.sub("", r.get("operator") or ""), "simulated": sim,
          "status_label": status.get(r["status"], r["status"])}
         for r in ranked[: F.BODY_ROWS]],
        source=F.source_line("outages", sim),
        notes=T((f"{len(ranked) - F.BODY_ROWS} more in the data annex. "
                 if len(ranked) > F.BODY_ROWS else "")
                + "Times UTC; capacity converted to GWh/d where the message's unit allows.",
                (f"另有{len(ranked) - F.BODY_ROWS}条见数据附录。" if len(ranked) > F.BODY_ROWS
                 else "") + "时间为 UTC；在消息单位允许时换算为 GWh/d。"))]
    result.tables[0]["id"] = "tab.outages"
    result.annex = [F.table(T("Outage schedule, all messages held", "停运时间表，全部消息"),
                            [("facility", T("Asset", "资产"), "text"),
                             ("zone", T("Zone", "区域"), "text"),
                             ("start", T("Start", "开始"), "datetime"),
                             ("end", T("End", "结束"), "datetime"),
                             ("gwh", T("Offline (GWh/d)", "停运（GWh/d）"), "num"),
                             ("status", T("Status", "状态"), "text")],
                            ranked)]
    result.charts = []
    result.facts = facts
    _prose(result, facts)


# =========================================================================== balance


def derive_balance(result, ctx) -> None:
    raw = result.raw
    history = raw["history"]
    forecast = raw["forecast"]
    sim = result.simulated
    end = ctx.end
    call = {date.fromisoformat(h["day"]): h["call_gwh"] for h in history}
    draw = {date.fromisoformat(h["day"]): h["storage_net_withdrawal_gwh"] for h in history}
    latest = max(call)
    years = F.years_held(call, latest)
    dod = F.change_at(call, latest, 1)
    wow = F.change_at(call, latest, 7)
    prior = F.same_day_last_year(latest)
    score, reason = F.materiality(dod, F.recent_variation(call, latest))
    f_call = F.fact("balance.call", "balance", T("NW Europe supply call", "西北欧供应需求"),
                    call[latest], "GWh/d",
                    day=F.iso(latest), state=raw["state"], simulated=sim, dod=dod, wow=wow,
                    yoy=call[latest] - call[prior] if prior in call else None, years=years,
                    score=score, reason=reason, spark=F.spark_of(call, latest),
                    sources=["NW Europe balance inputs"], exhibits=["fig.balance.call"],
                    sentence="")
    h = history[-1]
    f_call["sentence"] = T(
        f"The NW Europe supply call was {number(call[latest], 'GWh/d')}{_sim(sim)} on "
        f"{fday(latest)}, met by Norway ({number(h['norway_gwh'], 'GWh/d')}), LNG "
        f"({number(h['lng_gwh'], 'GWh/d')}) and a net storage withdrawal of "
        f"{number(h['storage_net_withdrawal_gwh'], 'GWh/d')}.",
        f"{fday(latest)}西北欧供应需求为{number(call[latest], 'GWh/d')}{_sim(sim)}，由挪威"
        f"（{number(h['norway_gwh'], 'GWh/d')}）、LNG（{number(h['lng_gwh'], 'GWh/d')}）及储气净提"
        f"取"
        f"（{number(h['storage_net_withdrawal_gwh'], 'GWh/d')}）满足。")
    f_call["headline"] = T(f"Supply call {_move(dod, 'GWh/d')} at {number(call[latest], 'GWh/d')}",
                           f"供应需求{number(call[latest], 'GWh/d')}，日内{_move(dod, 'GWh/d')}")
    draw_dod = _move(F.change_at(draw, latest, 1), "GWh/d")
    f_draw = F.fact("storage.withdrawal", "balance", T("Net storage withdrawal", "储气净提取"),
                    draw[latest],
                    "GWh/d", day=F.iso(latest), state=raw["state"], simulated=sim,
                    dod=F.change_at(draw, latest, 1), wow=F.change_at(draw, latest, 7),
                    yoy=draw[latest] - draw[prior] if prior in draw else None, years=years,
                    score=F.materiality(F.change_at(draw, latest, 1),
                                        F.recent_variation(draw, latest))[0] * 0.6,
                    reason="change against recent variation (weighted 0.6: part of the call)",
                    spark=F.spark_of(draw, latest), sources=["NW Europe balance inputs"],
                    sentence=T(f"Net withdrawal from storage was "
                               f"{number(draw[latest], 'GWh/d')}{_sim(sim)} on {fday(latest)}, "
                               f"{draw_dod} on the day.",
                               f"{fday(latest)}储气净提取量为{number(draw[latest], 'GWh/d')}"
                               f"{_sim(sim)}，较前一日{draw_dod}。"),
                    headline=T(f"Storage withdrawal {draw_dod} at "
                               f"{number(draw[latest], 'GWh/d')}",
                               f"储气提取{number(draw[latest], 'GWh/d')}，日内{draw_dod}"),
                    indicator=True)
    facts = [f_call, f_draw]
    exhibits = []
    window, permitted = _windows(ctx, "flow")
    longest = end - timedelta(days=394)
    series = [{"name": T("Measured", "实测"), "points": F.series_points(call, longest, end)}]
    context = F.shifted_year(call, longest, end)
    if context:
        series.append({"name": T("Year earlier", "去年"), "points": context, "context": True})
    if forecast:
        last = forecast[-1]
        method = str((last.get("methods") or {}).get("call") or "stated in Methodology")
        method = method.replace("_", " ")
        method = T(method, _METHOD_ZH.get(method, method))
        change = last["call_gwh"] - call[latest]
        years_word = _COUNT_WORDS.get(years, str(years)).lower()
        limitation = T((f"its seasonal normal rests on {years_word} year"
                        f"{'s' if years != 1 else ''} of measured days" if years else
                        "it has no year of measured days to set a seasonal normal"),
                       (f"其季节常态仅基于{years}年的实测日数据" if years else
                        "尚无一年的实测数据可设定季节常态"))
        facts.append(F.fact(
            "balance.forecast", "balance", T("Supply call forecast", "供应需求预测"),
            last["call_gwh"], "GWh/d",
            day=last["day"], state="current", simulated=sim, forecast=method, scheduled=True,
            # A forecast is weighed by the change it projects but capped below a material
            # measured change: rules do not lead an issue with a model estimate.
            indicator=False, score=min(round(abs(change) / call[latest] * 10, 2), 1.5),
            reason=f"forecast change of {abs(change) / call[latest]:.0%} of the latest call "
                   "(capped at 1.5: a forecast)",
            sentence=T(f"The balance forecast puts the call at "
                       f"{number(last['call_gwh'], 'GWh/d')}{_sim(sim)} on {fday(last['day'])}; "
                       f"it is a model estimate ({method}), not a measurement, and {limitation}.",
                       f"平衡预测显示{fday(last['day'])}供应需求为"
                       f"{number(last['call_gwh'], 'GWh/d')}{_sim(sim)}；该预测为模型估算"
                       f"（{method}），并非实测，且{limitation}。"),
            headline=T(f"Forecast call {number(last['call_gwh'], 'GWh/d')} by "
                       f"{fday(last['day'])}",
                       f"预测{fday(last['day'])}供应需求{number(last['call_gwh'], 'GWh/d')}"),
            implications=[T(f"On that forecast the call would be "
                            f"{'higher' if change > 0 else 'lower'} by {fday(last['day'])} "
                            f"than on {fday(latest)}.",
                            f"按该预测，{fday(last['day'])}的供应需求将"
                            f"{'高于' if change > 0 else '低于'}{fday(latest)}。")],
            sources=["NW Europe balance forecast"]))
        if last.get("fill_pct") is not None:
            facts.append(F.fact(
                "balance.forecast_fill", "balance", T("Projected storage fill", "预测储气率"),
                last["fill_pct"],
                "%", day=last["day"], state="current", simulated=sim, forecast=method,
                scheduled=True, indicator=False, score=0.3, reason="forecast level",
                sentence=T(f"On the same forecast, storage would be "
                           f"{number(last['fill_pct'], '%')} full by {fday(last['day'])}.",
                           f"按同一预测，{fday(last['day'])}储气率将为"
                           f"{number(last['fill_pct'], '%')}。"),
                sources=["NW Europe balance forecast"]))
        series.append({"name": T("Forecast", "预测"), "points": [[F.iso(latest), call[latest]]]
                       + [[f["day"], f["call_gwh"]] for f in forecast], "forecast": True})
    exhibits.append(F.exhibit(
        "fig.balance.call", "balance", "line",
        title=(T(f"Forecast points to a call of {number(forecast[-1]['call_gwh'], 'GWh/d')} by "
                 f"{fday(forecast[-1]['day'])}",
                 f"预测{fday(forecast[-1]['day'])}供应需求为"
                 f"{number(forecast[-1]['call_gwh'], 'GWh/d')}") if forecast else
               T(f"Supply call at {number(call[latest], 'GWh/d')}{_sim(sim)} on {fday(latest)}",
                 f"{fday(latest)}供应需求为{number(call[latest], 'GWh/d')}{_sim(sim)}")),
        subtitle=T("NW Europe supply call (Norway + LNG + net storage withdrawal), GWh/d; "
                   "measured, year earlier and forecast",
                   "西北欧供应需求（挪威 + LNG + 储气净提取），GWh/d；实测、一年前与预测"),
        unit="GWh/d", series=series, types=("line",), windows=permitted, window=window,
        simulated=sim,
        notes=T(f"Forecast: a model estimate ({method}), not a measurement; {limitation}. No "
                "forecast range is produced.",
                f"预测：模型估算（{method}），并非实测；{limitation}。未给出预测区间。")
        if forecast else ""))
    # Supply stack: the period's (or the latest day's) average sources and uses.
    days = [x for x in history if ctx.start.isoformat() <= x["day"] <= end.isoformat()] \
        if ctx.period_label else [history[-1]]
    days = days or [history[-1]]
    n = len(days)
    landings = ctx.cache.get("landed")
    cont = uk = None
    if landings is not None:
        picked = [date.fromisoformat(x["day"]) for x in days]
        cont = sum(landings.by_scope.get("norway", {}).get(d, 0.0) for d in picked) / n
        uk = sum(landings.by_scope.get("uk_terminal", {}).get(d, 0.0) for d in picked) / n
    avg = {k: sum(x[k] for x in days) / n for k in ("norway_gwh", "lng_gwh",
                                                    "storage_net_withdrawal_gwh", "call_gwh")}
    rows = []
    scopes_add_up = cont is not None and abs(cont + uk - avg["norway_gwh"]) <= max(
        1.0, 0.02 * avg["norway_gwh"])
    if scopes_add_up:
        rows += [{"item": T("Norway: continental terminals", "挪威：欧洲大陆终端"), "value": cont},
                 {"item": T("Norway and UK shelf: UK terminals", "挪威与英国大陆架：英国终端"),
                  "value": uk}]
    else:
        rows.append({"item": T("Norwegian pipeline landings", "挪威管道到岸量"),
                     "value": avg["norway_gwh"]})
    rows += [{"item": T("LNG send-out", "LNG 气化外输"), "value": avg["lng_gwh"]},
             {"item": T("Storage net withdrawal (injection negative)", "储气净提取（注入为负）"),
              "value": avg["storage_net_withdrawal_gwh"]},
             {"item": T("Supply call", "供应需求"), "value": avg["call_gwh"], "total": True}]
    for row in rows:
        row["value"] = round(row["value"], 1)
        row["share"] = round(100 * row["value"] / avg["call_gwh"], 1) if avg["call_gwh"] and \
            not row.get("total") else None
        row["simulated"] = sim
    label = (T(f"{ctx.period_label} average", "期间均值") if ctx.period_label
             else fday(history[-1]["day"]))
    result.tables = [F.table(
        T(f"Supply stack, {label} (GWh/d)", f"供应构成，{label}（GWh/d）"),
        [("item", "", "text"), ("value", "GWh/d", "num"),
         ("share", T("Share of call (%)", "占需求比例（%）"), "num")],
        rows, source=F.source_line("balance", sim))]
    if forecast:
        result.tables.append(F.table(
            T("Forecast, not a measurement (GWh/d)", "预测，并非实测（GWh/d）"),
            [("day", T("Gas day", "燃气日"), "date"), ("call_gwh", T("Call", "需求"), "num"),
             ("norway_gwh", T("Norway", "挪威"), "num"), ("lng_gwh", "LNG", "num"),
             ("storage_net_withdrawal_gwh", T("Storage", "储气"), "signed")],
            [{**x, "simulated": sim} for x in forecast[: F.BODY_ROWS]],
            source=F.source_line("balance", False),
            notes=T(f"Method: {method}; {limitation}.", f"方法：{method}；{limitation}。")))
    result.annex = [_annex_from_series(
        T("NW Europe balance, measured", "西北欧平衡，实测"), "GWh/d",
        {T("Norway", "挪威"): {date.fromisoformat(x["day"]): x["norway_gwh"] for x in history},
         "LNG": {date.fromisoformat(x["day"]): x["lng_gwh"] for x in history},
         T("Storage", "储气"): draw, T("Call", "需求"): call}, F.window_start(window, end), end)]
    result.facts, result.charts = facts, exhibits
    _prose(result, facts)


# =========================================================================== prose


#: Forecast method names in Chinese.
_METHOD_ZH = {"seasonal normal plus recent anomaly": "季节常态加近期偏差",
              "stated in Methodology": "见方法说明"}

#: Openers that link a paragraph's sentences without claiming a relation between them.
_LINKS = ("", "", "Separately, ", "", "")


def _prose(result, facts: list[dict]) -> None:
    """Lead sentence and paragraph: the weightiest fact first, then the rest, then one
    implication the engine can derive; scheduled facts close the paragraph."""

    measured = [f for f in facts if not f["scheduled"] and f["sentence"]]
    ahead = [f for f in facts if f["scheduled"] and f["sentence"]]
    if not measured and not ahead:
        return
    ordered = sorted(measured, key=lambda f: -f["score"]) or ahead
    lead = ordered[0]
    rest = [f for f in ordered[1:]]
    sentences: list[str] = []
    # An outage the lead already names (the largest, inside the total) is not named again.
    rest = [f for f in rest if not (f["key"].startswith("outage.")
                                    and re.split(r": |：", f["label"], maxsplit=1)[-1]
                                    in lead["sentence"])]
    for index, f in enumerate(rest[:3]):
        text = f["sentence"]
        link = "" if zh() else _LINKS[index % len(_LINKS)]
        # Lower-case the first letter after a link word, but never a code ("NBP Dec-26").
        first = text.split(" ", 1)[0]
        lowered = text if first.isupper() or any(ch.isdigit() for ch in first) else (
            text[0].lower() + text[1:]
        )
        sentences.append(link + lowered if link else text)
    implication = next((i for f in ordered for i in f["implications"]), None)
    if implication:
        sentences.insert(0, implication)
    for f in ahead[:2]:
        if f is not lead:
            sentences.append(f["sentence"])
    result.headline = lead["sentence"]
    # At most three facts under the headline (commentary.MAX_BULLETS).
    result.bullets = sentences[:3]


# ======================================================================= conversions


def _fx_holdings(ctx):
    """The FX reference rates and fixings this caller may read, from the report's session."""

    from eurogas_nexus.application.market_normalisation import _interest_rate_rows
    from eurogas_nexus.application.projections.market_reads import (
        filter_entitled_rows,
        fx_observations,
    )
    from eurogas_nexus.domain.market.fx_forward import FxHoldings

    principal = ctx.caller.principal
    return FxHoldings.from_rows(
        filter_entitled_rows(principal, fx_observations(ctx.session), source_key="source_system"),
        filter_entitled_rows(principal, _interest_rate_rows(ctx.session),
                             source_key="source_system"))


def _target_unit(native: str, currency: str | None, energy: str | None) -> str:
    from eurogas_nexus.application.market_normalisation import parse_price_unit

    source = parse_price_unit(native)
    cur = currency or source.currency
    unit = energy or source.unit.code
    # The desk quotes sterling per therm in pence.
    return f"GBp/{unit}" if cur == "GBP" and unit == "th" else f"{cur}/{unit}"


#: FX methods as the Chinese edition names them (``domain.market.fx_forward``).
_FX_METHOD_ZH = {"spot: ECB reference rate": "即期：欧洲央行参考汇率",
                 "derived: covered interest parity": "推导：抛补利率平价", "licensed": "授权远期"}


def _convert_closes(result, ctx, rows: list[dict], columns: list) -> str:
    """Add a converted close beside each native one when the plan asks for a reporting
    currency or energy unit; record the rate and factors in Methodology. Nothing is converted
    silently, and a close with no rate held stays native with the reason in the table note.
    Spot ECB reference rates for now; ``market_normalisation`` also serves forward FX for a
    delivery period when a report needs it."""

    plan = ctx.plan
    if not (plan.currency or plan.energy_unit) or not rows:
        return ""
    from eurogas_nexus.application.market_normalisation import (
        NormalisationError,
        display_unit,
        normalise_value,
        parse_price_unit,
    )

    try:
        holdings = _fx_holdings(ctx)
    except Exception:  # noqa: BLE001 - no FX read: every row stays native, with the reason
        ctx.session.rollback()
        from eurogas_nexus.domain.market.fx_forward import FxHoldings

        holdings = FxHoldings()
    used: dict[str, dict] = {}
    refused: list[str] = []
    for row in rows:
        try:
            target = _target_unit(row["unit"], plan.currency, plan.energy_unit)
            native = display_unit(parse_price_unit(row["unit"]))
            if display_unit(parse_price_unit(target)) == native:
                # Already in the reporting unit: the column shows the close as it is.
                row["converted"], row["converted_unit"] = row["close"], native
                continue
            day = date.fromisoformat(row["close_day"]) if row.get("close_day") else ctx.end
            out = normalise_value(row["close"], row["unit"], target, holdings=holdings,
                                  as_of=day, simulated=bool(row.get("simulated")))
        except NormalisationError as exc:
            refused.append(f"{row['hub']}: {exc}")
            continue
        row["converted"] = round(out["value"], 3)
        row["converted_unit"] = out["unit"]
        used[f"{row['unit']}>{out['unit']}"] = out["normalisation"]
    if not used and not refused:
        return ""
    columns.append(("converted", T("Converted", "折算"), "num"))
    columns.append(("converted_unit", T("Converted unit", "折算单位"), "text"))
    lines = []
    for record in used.values():
        fx = record.get("fx") or {}
        rate = (T(f"; FX {fx.get('base')}{fx.get('quote')} {fx.get('rate'):.4f} "
                  f"({fx.get('method')}, {fx.get('value_date') or 'latest'})",
                  f"；汇率 {fx.get('base')}{fx.get('quote')} {fx.get('rate'):.4f}"
                  f"（{_FX_METHOD_ZH.get(str(fx.get('method')), fx.get('method'))}，"
                  f"{fx.get('value_date') or '最新'}）")
                if fx else "")
        lines.append(T(f"{record['from_unit']} to {record['to_unit']}: unit factor "
                       f"{record['unit_factor']:.6g}{rate}.",
                       f"{record['from_unit']}折算为{record['to_unit']}：单位系数"
                       f"{record['unit_factor']:.6g}{rate}。"))
    if lines:
        result.methods.append({
            "key": "conversion",
            "title": T("Converted prices", "价格折算"),
            "text": T("Prices stay in their native unit; the converted column uses the units "
                      "authority's factors and the ECB reference rate shown. ",
                      "价格保留原报价单位；折算列使用单位权威表的系数及所示欧洲央行参考汇率。")
                    + " ".join(lines)})
    return (T(" Not converted: ", " 未折算：") + "; ".join(refused) + T(".", "。")) if refused \
        else ""


DERIVERS = {
    "prices": derive_prices,
    "pipeline_supply": derive_pipeline,
    "lng": derive_lng,
    "storage": derive_storage,
    "power_burn": derive_power,
    "outages": derive_outages,
    "balance": derive_balance,
}


def derive(result, ctx) -> None:
    """Facts, exhibits, edited tables and prose for one section (in place)."""

    if result.empty:
        result.facts = []
        return
    deriver = DERIVERS.get(result.key)
    if deriver is not None and result.raw is not None:
        deriver(result, ctx)
        _fit_to_budget(result, ctx)
    else:
        _book_or_event_facts(result)
        if ctx.plan.kind in {"daily", "situation", "ask"}:
            _short_book(result)


#: Body tables that earn their place: a hub board, a schedule, a supply stack. Daily series
#: tables go to the data annex only (the exhibit shows them).
BODY_TABLE_SECTIONS = {"prices", "outages", "balance"}


def _fit_to_budget(result, ctx) -> None:
    """Length budgets of the house standard: a daily shows one exhibit per section (two for
    prices), period reports keep their pairs; every exhibit is half width, so it sits beside
    the section's text or beside its pair. Series tables live in the annex, which covers the
    report's own window (two weeks daily, four weeks weekly, the month)."""

    kind = ctx.plan.kind
    if kind in {"daily", "situation", "ask"} and result.key != "prices":
        result.charts = result.charts[:1]
    for chart in result.charts:
        chart["half"] = True
    if result.key not in BODY_TABLE_SECTIONS:
        result.tables = []
    elif result.key == "balance":
        result.tables = result.tables[:1]
    # The printed annex covers the report's own window; the full exhibit window stays in
    # the data block the viewer's CSV download reads (``print_from`` marks the cut).
    if kind == "monthly":
        first = ctx.start
    elif kind == "weekly":
        first = ctx.end - timedelta(days=6)
    else:
        first = ctx.end - timedelta(days=13)
    for spec in result.annex:
        if spec["columns"] and spec["columns"][0]["key"] == "day":
            spec["print_from"] = first.isoformat()


#: Rows of a book table a daily prints (the full table is in the data annex and the CSV).
DAILY_BOOK_ROWS = 5


def _short_book(result) -> None:
    """A daily's book sections print one table of at most five rows each (none for P&L and
    contracts, whose sentences already give every row)."""

    if not result.key.startswith("book_"):
        return
    if result.key in {"book_pnl", "book_contracts"}:
        # The section's sentences carry these few rows; the table stays in the CSV download.
        for spec in result.tables:
            if not any(a.get("caption") == spec.get("caption") for a in result.annex):
                result.annex.append(dict(spec))
        result.tables = []
        return
    result.tables = result.tables[:1]
    for spec in result.tables:
        if len(spec["rows"]) > DAILY_BOOK_ROWS:
            if not any(a.get("caption") == spec.get("caption") for a in result.annex):
                result.annex.append(dict(spec))
            spec["notes"] = T(f"First {DAILY_BOOK_ROWS} of {len(spec['rows'])} rows; all rows in "
                              "the CSV download.",
                              f"显示前{DAILY_BOOK_ROWS}行，共{len(spec['rows'])}行；全部行见 CSV "
                              f"下载。")
            spec["rows"] = spec["rows"][:DAILY_BOOK_ROWS]
        # A column empty in every printed row says nothing.
        spec["columns"] = [c for c in spec["columns"]
                           if any(r.get(c["key"]) not in (None, "") for r in spec["rows"])]


def _book_or_event_facts(result) -> None:
    """Sections without series (book, situation, alerts): their rule text as facts."""

    # Book facts rank below a material market change: the report is a market publication
    # first; a breach still reaches the findings when the market is quiet.
    weight = {"situation_event": 8.0, "book_limits": 0.9, "book_pnl": 0.5,
              "book_position": 0.4, "book_contracts": 0.1, "alerts": 0.6}.get(result.key, 0.5)
    sentences = [result.headline, *result.bullets]
    result.facts = [F.fact(f"{result.key}.{i}", result.key, result.title, None, "",
                           day="", state="current", simulated=result.simulated,
                           indicator=False,
                           # A sentence that only says nothing is held is never a finding.
                           score=0.0 if s.startswith("No ") else
                           weight if i == 0 else weight * 0.3,
                           reason="nothing held" if s.startswith("No ") else
                           "section headline" if i == 0 else "section detail",
                           sentence=s, sources=[src["name"] for src in result.sources[:1]])
                    for i, s in enumerate(sentences) if s]
    for spec in result.tables:
        spec.setdefault("source", F.source_line(None, result.simulated))
        if len(spec["rows"]) > F.BODY_ROWS:
            result.annex.append(dict(spec))
            spec["notes"] = T(f"First {F.BODY_ROWS} of {len(spec['rows'])} rows; all rows in the "
                              "data annex.",
                              f"显示前{F.BODY_ROWS}行，共{len(spec['rows'])}行；全部行见数据附录。")
            spec["rows"] = spec["rows"][: F.BODY_ROWS]
    for chart in result.charts:
        chart.setdefault("id", f"fig.{result.key}")
        chart.setdefault("subtitle", f"{chart.get('title', '')}, {chart.get('unit', '')}")
        chart.setdefault("source", F.source_line(None, result.simulated))
        chart.setdefault("types", [chart["type"]])
        chart.setdefault("windows", ["30d"])
        chart.setdefault("window", "30d")


__all__ = ["DERIVERS", "derive"]
