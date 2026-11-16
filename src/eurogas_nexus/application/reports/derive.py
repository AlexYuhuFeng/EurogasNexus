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

from datetime import date, timedelta

from eurogas_nexus.application.reports import facts as F
from eurogas_nexus.application.reports.commentary import day as fday
from eurogas_nexus.application.reports.commentary import number

SIM = " (simulated)"


def _sim(flag: bool) -> str:
    return SIM if flag else ""


def _move(change: float | None, unit: str, digits: int | None = None) -> str:
    from eurogas_nexus.application.reports.commentary import move

    return move(change, unit, digits)


def _compare_clause(f: dict, *, day_word: str = "on the day") -> str:
    """``down 0.17 EUR/MWh on the day and up 1.20 EUR/MWh on the week``."""

    c = f["comparisons"]
    unit = c["unit"]
    parts = []
    if c["day"] is not None:
        parts.append(f"{_move(c['day'], unit)} {day_word}")
    if c["week"] is not None:
        parts.append(f"{_move(c['week'], unit)} on the week")
    return " and ".join(parts)


def _year_clause(f: dict, what: str = "a year earlier") -> str | None:
    c = f["comparisons"]
    if c["year"] is None:
        return None
    unit = c["unit"]
    if unit in {"points", "pts"}:
        word = "above" if c["year"] > 0 else "below"
        return f"{number(abs(c['year']), '', 1)} points {word} {what}"
    word = "above" if c["year"] > 0 else "below"
    return f"{number(abs(c['year']), unit)} {word} {what}"


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
    return F.table(f"{caption} ({unit})", [("day", "Day", "date")]
                   + [(n, n, "num") for n in names], rows)


# =========================================================================== prices


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
        sim = hub["simulated"]
        f = F.fact(
            f"price.{hub['hub']}", "prices", f"{hub['hub']} {hub['product']}",
            hub["close"], hub["unit"], day=F.iso(last), state=hub["state"], simulated=sim,
            dod=hub["day_change"], wow=wow, yoy=(hub["close"] - hub["year_ago"])
            if hub["year_ago"] is not None else None, years=1 if hub["year_ago"] is not None else 0,
            score=score, reason=reason, spark=F.spark_of(series, last),
            sources=[f"{hub['hub']} closes"], exhibits=[f"fig.prices.{hub['unit']}"],
            sentence="", headline="",
        )
        clause = _compare_clause(f)
        f["sentence"] = (
            f"{hub['hub']} {hub['product']} closed at "
            f"{number(hub['close'], hub['unit'])}{_sim(sim)}"
            f" on {fday(last)}" + (f", {clause}" if clause else "") + "."
        )
        f["headline"] = (f"{hub['hub']} {hub['product']} {_move(hub['day_change'], hub['unit'])} "
                         f"at {number(hub['close'], hub['unit'])}{_sim(sim)}")
        if variation:
            f["implications"].append(
                "The move was within the range of its recent daily changes." if score < 1 else
                "The move was larger than its typical daily change over the last 30 days."
            )
        if hub.get("rolled_from"):
            f["implications"].insert(0, 
                f"The front month rolled from {hub['rolled_from']} to {hub['product']} during "
                "the period, so no change across the two contracts is given.")
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
                    sentence=f"The {other}–TTF front-month spread was "
                             f"{number(spread, 'EUR/MWh')}{_sim(sim)} on "
                             f"{fday(eur['TTF']['close_day'])}.",
                    sources=[f"{other} closes", "TTF closes"],
                ))
                break
    for unit, items in by_unit.items():
        longest = end - timedelta(days=F.WINDOWS["395d"] - 1)
        lead = items[0]
        exhibits.append(F.exhibit(
            f"fig.prices.{unit}", "prices", "line",
            title=(f"{lead['hub']} front month closed at {number(lead['close'], unit)}"
                   f"{_sim(lead['simulated'])} on {fday(lead['close_day'])}"),
            subtitle=f"Front-month daily closes, {unit}",
            unit=unit,
            series=[{"name": h["hub"], "points": F.series_points(h["series"], longest, end)}
                    for h in items],
            types=("line", "step"), windows=permitted, window=window,
            simulated=any(h["simulated"] for h in items),
            notes="The front month rolls at each month end; the line joins the contracts.",
        ))
        annex.append(_annex_from_series("Front-month closes", unit,
                                        {h["hub"]: h["series"] for h in items},
                                        F.window_start(window, end), end))
    rows = [{"hub": h["hub"], "product": h["product"], "unit": h["unit"], "close": h["close"],
             "day": h["day_change"],
             "week": next((f["comparisons"]["week"] for f in facts
                           if f["key"] == f"price.{h['hub']}"), None),
             "year": h["year_ago"], "simulated": h["simulated"], "state": h["state"],
             "period_change": h.get("period_change"), "high": h.get("high"),
             "low": h.get("low"), "average": h.get("average")}
            for h in hubs[: F.BODY_ROWS]]
    columns = [("hub", "Hub", "text"), ("product", "Contract", "text"), ("unit", "Unit", "text"),
               ("close", "Close", "num"), ("day", "Day", "signed")]
    if ctx.period_label:
        columns += [("period_change", "Period", "signed"), ("average", "Average", "num"),
                    ("high", "High", "num"), ("low", "Low", "num")]
    else:
        columns += [("week", "Week", "signed")]
    columns.append(("year", "Year earlier", "num"))
    result.tables = [F.table(
        "Front-month closes", columns, rows,
        source=F.DEMO_SOURCE if result.simulated else F.SOURCE_LINES["prices"],
        notes="Day and week: change in the hub's own unit; year earlier: the front month's "
              "close on the same day a year earlier (a different contract).")]
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
    f = F.fact("landings", "pipeline_supply", "Norwegian pipeline landings", total[latest],
               "GWh/d", day=F.iso(latest), state=raw["state"], simulated=sim, dod=dod, wow=wow,
               yoy=yoy, years=years, score=score, reason=reason,
               spark=F.spark_of(total, latest), sources=["Physical flows at the landing points"],
               exhibits=["fig.landings.total", "fig.landings.split"], sentence="")
    clause = _compare_clause(f)
    f["sentence"] = (f"Norwegian pipeline landings were {number(total[latest], 'GWh/d')}"
                     f"{_sim(sim)} "
                     f"on {fday(latest)}" + (f", {clause}" if clause else "") + ".")
    f["headline"] = f"Norwegian landings {_move(dod, 'GWh/d')} at {number(total[latest], 'GWh/d')}"
    year = _year_clause(f, "the same day a year earlier")
    if year:
        f["implications"].append(f"Flows were {year}.")
    facts = [f]
    if latest in norway and latest in uk:
        facts.append(F.fact(
            "landings.split", "pipeline_supply", "Landings by scope", norway[latest], "GWh/d",
            day=F.iso(latest), state=raw["state"], simulated=sim, indicator=False,
            score=0.1, reason="composition",
            sentence=(f"Continental terminals took {number(norway[latest], 'GWh/d')} and UK "
                      f"terminals, which also land UK shelf gas, "
                      f"{number(uk[latest], 'GWh/d')}{_sim(sim)}."),
            sources=["Physical flows at the landing points"]))
    if ctx.period_label and raw.get("period_avg") is not None:
        facts.append(F.fact(
            "landings.period", "pipeline_supply", "Landings, period average", raw["period_avg"],
            "GWh/d", day=F.iso(latest), state=raw["state"], simulated=sim, indicator=False,
            score=score + 0.1, reason="period aggregate",
            sentence=(f"Over {raw['period_label']} landings averaged "
                      f"{number(raw['period_avg'], 'GWh/d')}{_sim(sim)}"
                      + (f", {_move(raw['period_avg'] - raw['previous_avg'], 'GWh/d')} on the "
                         "period before" if raw.get("previous_avg") is not None else "") + ".")))
    window, permitted = _windows(ctx, "flow")
    longest = end - timedelta(days=394)
    context = F.shifted_year(total, longest, end)
    exhibits = [
        F.exhibit("fig.landings.total", "pipeline_supply", "line",
                  title=f"Landings {_move(dod, 'GWh/d')} to {number(total[latest], 'GWh/d')}"
                        f"{_sim(sim)} on {fday(latest)}",
                  subtitle="Norwegian pipeline landings, GWh/d, against the same days a year "
                           "earlier" + (f" ({years} prior year held)" if years else ""),
                  unit="GWh/d",
                  series=[{"name": "This year", "points": F.series_points(total, longest, end)}]
                  + ([{"name": "Year earlier", "points": context, "context": True}]
                     if context else []),
                  types=("line",), windows=permitted, window=window, simulated=sim, half=True),
        F.exhibit("fig.landings.split", "pipeline_supply", "stacked_area",
                  title="Continental terminals take most of the gas",
                  subtitle="Landings by terminal scope, GWh/d",
                  unit="GWh/d",
                  series=[{"name": "Continental", "points": F.series_points(norway, longest, end)},
                          {"name": "UK terminals", "points": F.series_points(uk, longest, end)}],
                  types=("stacked_area", "stacked_bar"), windows=permitted, window=window,
                  simulated=sim, half=True,
                  notes="UK terminals carry UK shelf gas with Norwegian gas."),
    ]
    if latest in norway and latest in uk and norway[latest] < uk[latest]:
        exhibits[1]["title"] = "UK terminals take more gas than the continental terminals"
    days = [d for d in sorted(total, reverse=True) if d <= end][:7]
    result.tables = [F.table(
        "Landings, last seven complete gas days (GWh/d)",
        [("day", "Gas day", "date"), ("continent", "Continental", "num"),
         ("uk", "UK terminals", "num"), ("total", "Total", "num")],
        [{"day": F.iso(d), "continent": round(norway.get(d, 0.0), 1),
          "uk": round(uk.get(d, 0.0), 1), "total": round(total[d], 1), "simulated": sim}
         for d in days],
        source=F.DEMO_SOURCE if sim else F.SOURCE_LINES["pipeline_supply"])]
    result.annex = [_annex_from_series("Norwegian landings", "GWh/d",
                                       {"Continental": norway, "UK terminals": uk,
                                        "Total": total}, F.window_start(window, end), end)]
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
    f = F.fact("lng", "lng", "LNG send-out", total[latest], "GWh/d", day=F.iso(latest),
               state=raw["state"], simulated=sim, dod=dod, wow=wow, yoy=yoy, years=years,
               score=score, reason=reason, spark=F.spark_of(total, latest),
               sources=["LNG send-out"], exhibits=["fig.lng.country"], sentence="")
    clause = _compare_clause(f)
    f["sentence"] = (f"LNG send-out across NW Europe was {number(total[latest], 'GWh/d')}"
                     f"{_sim(sim)} on {fday(latest)}" + (f", {clause}" if clause else "") + ".")
    f["headline"] = f"LNG send-out {_move(dod, 'GWh/d')} at {number(total[latest], 'GWh/d')}"
    year = _year_clause(f, "the same day a year earlier")
    if year:
        f["implications"].append(f"Send-out was {year}.")
    facts = [f]
    top = sorted(by_day[latest].items(), key=lambda kv: -kv[1])
    if top:
        facts.append(F.fact("lng.top", "lng", f"LNG send-out, {top[0][0]}", top[0][1], "GWh/d",
                            day=F.iso(latest), state=raw["state"], simulated=sim,
                            indicator=False, score=0.1, reason="composition",
                            sentence=f"{top[0][0]} terminals sent out the most, "
                                     f"{number(top[0][1], 'GWh/d')}{_sim(sim)}.",
                            sources=["LNG send-out"]))
    if raw.get("left_out"):
        facts.append(F.fact("lng.partial", "lng", "LNG days left out", None, "", day=F.iso(latest),
                            state="late", indicator=False, score=0.05, reason="data note",
                            sentence="Days not yet reported by every country ("
                                     + ", ".join(fday(d) for d in raw["left_out"][:3])
                                     + ") are left out."))
    window, permitted = _windows(ctx, "flow")
    longest = end - timedelta(days=394)
    countries = [c for c, _ in top] or sorted({c for d in by_day for c in by_day[d]})
    days_all = sorted(d for d in by_day if longest <= d <= end and d in total)
    exhibits = [F.exhibit(
        "fig.lng.country", "lng", "stacked_bar",
        title=f"{top[0][0]} led NW Europe send-out on {fday(latest)}" if top else "LNG send-out",
        subtitle="LNG send-out by country, GWh/d", unit="GWh/d",
        series=[{"name": c, "points": [[F.iso(d), round(by_day[d].get(c, 0.0), 1)]
                                       for d in days_all]} for c in countries],
        types=("stacked_bar", "stacked_area"), windows=permitted, window=window,
        simulated=sim, half=True)]
    context = F.shifted_year(total, longest, end)
    exhibits.append(F.exhibit(
        "fig.lng.total", "lng", "line",
        title=(f"Send-out {('above' if (yoy or 0) > 0 else 'below')} the same days a year "
               "earlier") if yoy is not None else "LNG send-out over the window",
        subtitle="LNG send-out, NW Europe total, GWh/d"
                 + (f"; context: {years} prior year held" if years else ""),
        unit="GWh/d",
        series=[{"name": "This year", "points": F.series_points(total, longest, end)}]
        + ([{"name": "Year earlier", "points": context, "context": True}] if context else []),
        types=("line",), windows=permitted, window=window, simulated=sim, half=True))
    result.tables = [F.table(
        f"Send-out by country on {fday(latest)} (GWh/d)",
        [("country", "Country", "text"), ("value", "Send-out", "num")],
        [{"country": c, "value": round(v, 1), "simulated": sim} for c, v in top[: F.BODY_ROWS]],
        source=F.DEMO_SOURCE if sim else F.SOURCE_LINES["lng"])]
    result.annex = [_annex_from_series(
        "LNG send-out by country", "GWh/d",
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
    f = F.fact("storage.fill", "storage", "NW Europe storage fill", fill[latest], "%",
               day=F.iso(latest), state=raw["state"], simulated=sim, dod=dod, wow=wow, yoy=yoy,
               change_unit="points", years=1 if yoy is not None else 0, score=score,
               reason=reason, spark=F.spark_of(fill, latest), sources=["Storage inventory"],
               exhibits=["fig.storage.season"], sentence="")
    year = _year_clause(f, "a year earlier")
    week = (f", having {'risen' if wow > 0 else 'fallen'} {number(abs(wow), '', 1)} points in "
            "seven days") if wow is not None and abs(wow) >= 0.05 else ""
    f["sentence"] = (f"NW Europe storage was {number(fill[latest], '%')} full{_sim(sim)} on "
                     f"{fday(latest)}" + (f", {year}" if year else "") + week + ".")
    f["headline"] = (f"Storage {number(fill[latest], '%')} full, "
                     + (year if year else "no year-earlier comparison held"))
    if yoy is not None:
        f["implications"].append(
            "Stocks are lower than a year earlier at this point of the season." if yoy < 0 else
            "Stocks are higher than a year earlier at this point of the season.")
    facts = [f]
    if raw.get("inventory") is not None:
        facts.append(F.fact("storage.inventory", "storage", "Storage inventory",
                            raw["inventory"], "TWh", day=F.iso(latest), state=raw["state"],
                            simulated=sim, indicator=False, score=0.1, reason="level",
                            sentence=f"That is {number(raw['inventory'], 'TWh', 1)}{_sim(sim)} in "
                                     "the facilities that publish a working capacity.",
                            sources=["Storage inventory"]))
    if raw.get("target"):
        facts.append(F.fact("storage.target", "storage", "EU filling target", raw["target"], "%",
                            day=F.iso(latest), state="current", indicator=False, score=0.05,
                            reason="reference",
                            sentence=f"The EU filling target is {number(raw['target'], '%', 0)}."))
    window, permitted = _windows(ctx, "storage")
    first = F.window_start("gas_year", end) - timedelta(days=90)
    gas_year = F.window_start("gas_year", end)
    label_now = f"{gas_year.year}/{str(gas_year.year + 1)[2:]}"
    label_prev = f"{gas_year.year - 1}/{str(gas_year.year)[2:]}"
    exhibits = [F.exhibit(
        "fig.storage.season", "storage", "line",
        title=(f"Storage {number(fill[latest], '%')} full{_sim(sim)}, "
               + (year if year else "no year-earlier comparison held")),
        subtitle=f"NW Europe storage fill, % of working capacity; gas year {label_now} against "
                 f"{label_prev} (one prior year held)",
        unit="%",
        series=[{"name": label_now, "points": F.series_points(fill, first, end)},
                {"name": label_prev, "points": F.series_points(prev, first, end),
                 "context": True}],
        types=("line",), windows=permitted, window=window, simulated=sim,
        reference_lines=[{"label": f"EU target {raw['target']:.0f}%", "value": raw["target"]}]
        if raw.get("target") else [],
        notes="The prior gas year is placed on this year's dates.")]
    days = [d for d in sorted(fill, reverse=True) if d <= end][:7]
    result.tables = [F.table(
        "Storage fill, last seven gas days (%)",
        [("day", "Gas day", "date"), ("fill", "Fill", "num"), ("prev", "Year earlier", "num"),
         ("diff", "Difference (points)", "signed")],
        [{"day": F.iso(d), "fill": fill[d], "prev": prev.get(d),
          "diff": None if d not in prev else round(fill[d] - prev[d], 2), "simulated": sim}
         for d in days],
        source=F.DEMO_SOURCE if sim else F.SOURCE_LINES["storage"])]
    result.annex = [_annex_from_series("Storage fill", "%", {label_now: fill,
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
    f = F.fact("power.gen", "power_burn", "Gas-fired generation", total[latest], "GWh/d",
               day=F.iso(latest), state=raw["state"], simulated=sim, dod=dod, wow=wow,
               score=score, reason=reason, spark=F.spark_of(total, latest),
               sources=["Generation by fuel (gas)"], exhibits=["fig.power.zone"], sentence="")
    clause = _compare_clause(f)
    f["sentence"] = (f"Gas-fired plants generated {number(total[latest], 'GWh/d')} of "
                     f"electricity{_sim(sim)} on {fday(latest)}"
                     + (f", {clause}" if clause else "") + ".")
    f["headline"] = (f"Gas-fired generation {_move(dod, 'GWh/d')} at "
                     f"{number(total[latest], 'GWh/d')}")
    burn = {d: implied_gas_burn_mwh_th(SystemHour(load_mw=0.0, gas_generation_mw=v * 1000 / 24),
                                       hours=24.0, efficiency=GAS_EFFICIENCY)[0] / 1000
            for d, v in total.items()}
    facts = [f, F.fact(
        "power.burn", "power_burn", "Implied gas burn for power", burn[latest], "GWh/d",
        day=F.iso(latest), state=raw["state"], simulated=sim,
        dod=F.change_at(burn, latest, 1), wow=F.change_at(burn, latest, 7), score=score * 0.5,
        reason="derived from generation at a stated efficiency",
        sentence=(f"At the {GAS_EFFICIENCY:.0%} plant efficiency the gas-for-power read assumes, "
                  f"that implies about {number(burn[latest], 'GWh/d')} of gas burned"
                  f"{_sim(sim)} (implied, not measured)."),
        spark=F.spark_of(burn, latest), sources=["Generation by fuel (gas)"])]
    window, permitted = _windows(ctx, "flow")
    longest = end - timedelta(days=394)
    zones = sorted({z for d in by_zone for z in by_zone[d]})
    days_all = sorted(d for d in by_zone if longest <= d <= end and d in total)
    exhibits = [F.exhibit(
        "fig.power.zone", "power_burn", "stacked_bar",
        title=f"Gas-fired output {_move(dod, 'GWh/d')} to {number(total[latest], 'GWh/d')}"
              f"{_sim(sim)}",
        subtitle="Electricity generated from gas by bidding zone, GWh/d (UTC days)",
        unit="GWh/d",
        series=[{"name": z, "points": [[F.iso(d), round(by_zone[d].get(z, 0.0), 1)]
                                       for d in days_all]} for z in zones],
        types=("stacked_bar", "stacked_area"), windows=permitted, window=window, simulated=sim,
        notes=f"Implied gas burn = generation / {GAS_EFFICIENCY:.0%} efficiency; not measured.")]
    top = sorted(by_zone[latest].items(), key=lambda kv: -kv[1])
    result.tables = [F.table(
        f"Gas-fired generation and implied burn on {fday(latest)} (GWh/d)",
        [("zone", "Zone", "text"), ("gen", "Generation", "num"),
         ("burn", "Implied gas burn", "num")],
        [{"zone": z, "gen": round(v, 1), "burn": round(v / GAS_EFFICIENCY, 1), "simulated": sim}
         for z, v in top[: F.BODY_ROWS]],
        source=F.DEMO_SOURCE if sim else F.SOURCE_LINES["power_burn"],
        notes=f"Implied burn assumes {GAS_EFFICIENCY:.0%} efficiency.")]
    result.annex = [_annex_from_series("Gas-fired generation", "GWh/d",
                                       {"Generation": total, "Implied burn": burn},
                                       F.window_start(window, end), end)]
    result.facts, result.charts = facts, exhibits
    _prose(result, facts)


# =========================================================================== outages


def derive_outages(result, ctx) -> None:
    raw = result.raw
    rows = raw["rows"]
    sim = result.simulated
    landings = (ctx.cache.get("landings_latest") or 4000.0)
    facts = []
    active = [r for r in rows if r["status"] == "active" and r["gwh"]]
    offline = sum(r["gwh"] for r in active)
    facts.append(F.fact(
        "outages.offline", "outages", "Capacity offline (REMIT)", offline, "GWh/d",
        day=F.iso(ctx.today), state=raw["state"], simulated=sim, score=min(offline / landings * 4,
                                                                           5.0),
        reason=f"{offline / landings:.0%} of the latest Norwegian landings",
        sentence=(f"{len(active)} outage{'s' if len(active) != 1 else ''} were active, removing "
                  f"{number(offline, 'GWh/d')} in total{_sim(sim)}."),
        headline=f"{len(active)} outages remove {number(offline, 'GWh/d')}",
        sources=["REMIT urgent market messages"], exhibits=["tab.outages"]))
    for index, r in enumerate(sorted(active, key=lambda r: -r["gwh"])[:3], start=1):
        until = f"until {fday(r['end'])}" if r.get("end") else "with no end date"
        facts.append(F.fact(
            f"outage.{index}", "outages", f"Outage: {r['facility']}", r["gwh"], "GWh/d",
            day=F.iso(r["start"][:10]), state=raw["state"], simulated=sim, indicator=False,
            score=min(r["gwh"] / landings * 10, 6.0),
            reason=f"{r['gwh'] / landings:.0%} of the latest Norwegian landings offline",
            sentence=(f"{r['facility']} ({r['zone'] or 'zone n/a'}) has "
                      f"{number(r['gwh'], 'GWh/d')} unavailable{_sim(sim)} since "
                      f"{fday(r['start'])}, {until}."),
            headline=f"{r['facility']} outage removes {number(r['gwh'], 'GWh/d')}",
            sources=["REMIT urgent market messages"]))
    starting = sorted([r for r in rows if r["status"] == "scheduled" and r["gwh"]],
                      key=lambda r: r["start"])[:3]
    for index, r in enumerate(starting, start=1):
        facts.append(F.fact(
            f"outage.next.{index}", "outages", f"Scheduled: {r['facility']}", r["gwh"], "GWh/d",
            day=F.iso(r["start"][:10]), state=raw["state"], simulated=sim, indicator=False,
            scheduled=True, score=min(r["gwh"] / landings * 3, 2.0), reason="scheduled event",
            sentence=(f"{r['facility']} is scheduled to lose {number(r['gwh'], 'GWh/d')}"
                      f"{_sim(sim)} from {fday(r['start'])}"
                      + (f" to {fday(r['end'])}" if r.get("end") else "") + "."),
            sources=["REMIT urgent market messages"]))
    ended = [r for r in rows if r["status"] == "ended" and r["gwh"]]
    if ended:
        facts.append(F.fact(
            "outages.ended", "outages", "Outages ended in the period",
            sum(r["gwh"] for r in ended), "GWh/d", day=F.iso(ctx.end), state=raw["state"],
            simulated=sim, indicator=False, score=0.3, reason="ended in period",
            sentence=(f"{len(ended)} outage{'s' if len(ended) != 1 else ''} that removed "
                      f"{number(sum(r['gwh'] for r in ended), 'GWh/d')} ended during "
                      f"{ctx.period_label or 'the period'}."),
            sources=["REMIT urgent market messages"]))
    if raw.get("norway_active") == 0:
        facts.append(F.fact("outages.norway", "outages", "Norwegian outages", 0.0, "outages",
                            day=F.iso(ctx.today), state=raw["state"], indicator=False,
                            score=0.05, reason="absence noted",
                            sentence="No active outage in Norway is among the messages held."))
    order = {"active": 0, "scheduled": 1, "ended": 2}
    ranked = sorted(rows, key=lambda r: (order.get(r["status"], 3), -(r["gwh"] or 0.0)))
    result.tables = [F.table(
        "Outage schedule, largest active first",
        [("facility", "Asset", "text"), ("operator", "Operator", "text"),
         ("zone", "Zone", "text"), ("start", "Start", "datetime"), ("end", "End", "datetime"),
         ("gwh", "Offline (GWh/d)", "num"), ("status", "Status", "text")],
        [{**r, "simulated": sim} for r in ranked[: F.BODY_ROWS]],
        source=F.DEMO_SOURCE if sim else F.SOURCE_LINES["outages"],
        notes=(f"{len(ranked) - F.BODY_ROWS} more in the data annex. " if len(ranked) > F.BODY_ROWS
               else "") + "Times UTC; capacity converted to GWh/d where the message's unit "
                         "allows.")]
    result.tables[0]["id"] = "tab.outages"
    result.annex = [F.table("Outage schedule, all messages held",
                            [("facility", "Asset", "text"), ("zone", "Zone", "text"),
                             ("start", "Start", "datetime"), ("end", "End", "datetime"),
                             ("gwh", "Offline (GWh/d)", "num"), ("status", "Status", "text")],
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
    f_call = F.fact("balance.call", "balance", "NW Europe supply call", call[latest], "GWh/d",
                    day=F.iso(latest), state=raw["state"], simulated=sim, dod=dod, wow=wow,
                    yoy=call[latest] - call[prior] if prior in call else None, years=years,
                    score=score, reason=reason, spark=F.spark_of(call, latest),
                    sources=["NW Europe balance inputs"], exhibits=["fig.balance.call"],
                    sentence="")
    h = history[-1]
    f_call["sentence"] = (
        f"The NW Europe supply call was {number(call[latest], 'GWh/d')}{_sim(sim)} on "
        f"{fday(latest)}, met by Norway ({number(h['norway_gwh'], 'GWh/d')}), LNG "
        f"({number(h['lng_gwh'], 'GWh/d')}) and a net storage withdrawal of "
        f"{number(h['storage_net_withdrawal_gwh'], 'GWh/d')}.")
    f_call["headline"] = f"Supply call {_move(dod, 'GWh/d')} at {number(call[latest], 'GWh/d')}"
    f_draw = F.fact("storage.withdrawal", "balance", "Net storage withdrawal", draw[latest],
                    "GWh/d", day=F.iso(latest), state=raw["state"], simulated=sim,
                    dod=F.change_at(draw, latest, 1), wow=F.change_at(draw, latest, 7),
                    yoy=draw[latest] - draw[prior] if prior in draw else None, years=years,
                    score=F.materiality(F.change_at(draw, latest, 1),
                                        F.recent_variation(draw, latest))[0] * 0.6,
                    reason="change against recent variation (weighted 0.6: part of the call)",
                    spark=F.spark_of(draw, latest), sources=["NW Europe balance inputs"],
                    sentence=f"Net withdrawal from storage was {number(draw[latest], 'GWh/d')}"
                             f"{_sim(sim)} on {fday(latest)}, "
                             f"{_move(F.change_at(draw, latest, 1), 'GWh/d')} on the day.",
                    headline=f"Storage withdrawal {_move(F.change_at(draw, latest, 1), 'GWh/d')}"
                             f" at {number(draw[latest], 'GWh/d')}", indicator=True)
    facts = [f_call, f_draw]
    exhibits = []
    window, permitted = _windows(ctx, "flow")
    longest = end - timedelta(days=394)
    series = [{"name": "Measured", "points": F.series_points(call, longest, end)}]
    context = F.shifted_year(call, longest, end)
    if context:
        series.append({"name": "Year earlier", "points": context, "context": True})
    if forecast:
        last = forecast[-1]
        method = str((last.get("methods") or {}).get("call") or "stated in Methodology")
        method = method.replace("_", " ")
        change = last["call_gwh"] - call[latest]
        limitation = (f"its seasonal normal rests on {years} prior year{'s' if years != 1 else ''}"
                      " of measured days" if years else
                      "it has no prior year of measured days to set a seasonal normal")
        facts.append(F.fact(
            "balance.forecast", "balance", "Supply call forecast", last["call_gwh"], "GWh/d",
            day=last["day"], state="current", simulated=sim, forecast=method, scheduled=True,
            # A forecast is weighed by the change it projects but capped below a material
            # measured change: rules do not lead an issue with a model estimate.
            indicator=False, score=min(round(abs(change) / call[latest] * 10, 2), 1.5),
            reason=f"forecast change of {abs(change) / call[latest]:.0%} of the latest call "
                   "(capped at 1.5: a forecast)",
            sentence=(f"The balance forecast ({method}) puts the call at "
                      f"{number(last['call_gwh'], 'GWh/d')}{_sim(sim)} on {fday(last['day'])}; it "
                      f"is a forecast, not a measurement, and {limitation}."),
            headline=f"Forecast call {number(last['call_gwh'], 'GWh/d')} by {fday(last['day'])}",
            implications=[f"On that forecast the call would be "
                          f"{'higher' if change > 0 else 'lower'} by {fday(last['day'])} "
                          f"than on {fday(latest)}."],
            sources=["NW Europe balance forecast"]))
        if last.get("fill_pct") is not None:
            facts.append(F.fact(
                "balance.forecast_fill", "balance", "Projected storage fill", last["fill_pct"],
                "%", day=last["day"], state="current", simulated=sim, forecast=method,
                scheduled=True, indicator=False, score=0.3, reason="forecast level",
                sentence=f"On the same forecast storage would be {number(last['fill_pct'], '%')}"
                         f" full by {fday(last['day'])}.",
                sources=["NW Europe balance forecast"]))
        series.append({"name": "Forecast", "points": [[F.iso(latest), call[latest]]]
                       + [[f["day"], f["call_gwh"]] for f in forecast], "forecast": True})
    exhibits.append(F.exhibit(
        "fig.balance.call", "balance", "line",
        title=(f"Forecast points to a call of {number(forecast[-1]['call_gwh'], 'GWh/d')} by "
               f"{fday(forecast[-1]['day'])}" if forecast else
               f"Supply call at {number(call[latest], 'GWh/d')}{_sim(sim)} on {fday(latest)}"),
        subtitle="NW Europe supply call (Norway + LNG + net storage withdrawal), GWh/d; "
                 "measured, year earlier and forecast",
        unit="GWh/d", series=series, types=("line",), windows=permitted, window=window,
        simulated=sim,
        notes=("Forecast: " + facts[2]["sentence"].split("; ", 1)[-1]
               + " No forecast range is produced.") if forecast else ""))
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
        rows += [{"item": "Norway: continental terminals", "value": cont},
                 {"item": "Norway and UK shelf: UK terminals", "value": uk}]
    else:
        rows.append({"item": "Norwegian pipeline landings", "value": avg["norway_gwh"]})
    rows += [{"item": "LNG send-out", "value": avg["lng_gwh"]},
             {"item": "Storage net withdrawal (injection negative)",
              "value": avg["storage_net_withdrawal_gwh"]},
             {"item": "Supply call", "value": avg["call_gwh"], "total": True}]
    for row in rows:
        row["value"] = round(row["value"], 1)
        row["share"] = round(100 * row["value"] / avg["call_gwh"], 1) if avg["call_gwh"] and \
            not row.get("total") else None
        row["simulated"] = sim
    label = (f"{ctx.period_label} average" if ctx.period_label else fday(history[-1]["day"]))
    result.tables = [F.table(
        f"Supply stack, {label} (GWh/d)",
        [("item", "", "text"), ("value", "GWh/d", "num"), ("share", "Share of call (%)", "num")],
        rows, source=F.DEMO_SOURCE if sim else F.SOURCE_LINES["balance"])]
    if forecast:
        result.tables.append(F.table(
            "Forecast, not a measurement (GWh/d)",
            [("day", "Gas day", "date"), ("call_gwh", "Call", "num"),
             ("norway_gwh", "Norway", "num"), ("lng_gwh", "LNG", "num"),
             ("storage_net_withdrawal_gwh", "Storage", "signed")],
            [{**x, "simulated": sim} for x in forecast[: F.BODY_ROWS]],
            source=F.SOURCE_LINES["balance"],
            notes=f"Method: {facts[2]['forecast']}. "
                  + facts[2]["sentence"].split("; ", 1)[-1].capitalize()))
    result.annex = [_annex_from_series(
        "NW Europe balance, measured", "GWh/d",
        {"Norway": {date.fromisoformat(x["day"]): x["norway_gwh"] for x in history},
         "LNG": {date.fromisoformat(x["day"]): x["lng_gwh"] for x in history},
         "Storage": draw, "Call": call}, F.window_start(window, end), end)]
    result.facts, result.charts = facts, exhibits
    _prose(result, facts)


# =========================================================================== prose


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
    for index, f in enumerate(rest[:3]):
        text = f["sentence"]
        link = _LINKS[index % len(_LINKS)]
        sentences.append(link + (text[0].lower() + text[1:] if link else text))
    implication = next((i for f in ordered for i in f["implications"]), None)
    if implication:
        sentences.insert(0, implication)
    for f in ahead[:2]:
        if f is not lead:
            sentences.append(f["sentence"])
    result.headline = lead["sentence"]
    result.bullets = sentences[:4]


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


#: Body tables that earn their place: a hub board, a schedule, a supply stack. Daily series
#: tables go to the data annex only (the exhibit shows them).
BODY_TABLE_SECTIONS = {"prices", "outages", "balance"}


def _fit_to_budget(result, ctx) -> None:
    """Length budgets of the house standard: a daily shows one exhibit per section (two for
    prices, side by side), period reports keep their pairs; series tables live in the annex,
    which covers the report's own window (30 days daily, 13 weeks weekly, the month)."""

    kind = ctx.plan.kind
    if result.key == "prices" and len(result.charts) > 1:
        for chart in result.charts:
            chart["half"] = True
    elif kind in {"daily", "situation", "ask"}:
        result.charts = result.charts[:1]
        for chart in result.charts:
            chart["half"] = False
    if result.key not in BODY_TABLE_SECTIONS:
        result.tables = []
    elif result.key == "balance":
        result.tables = result.tables[:1]
    # The printed annex covers the report's own window; the full exhibit window stays in
    # the data block the viewer's CSV download reads (``print_from`` marks the cut).
    if kind == "monthly":
        first = ctx.start
    elif kind == "weekly":
        first = ctx.end - timedelta(days=27)
    else:
        first = ctx.end - timedelta(days=13)
    for spec in result.annex:
        if spec["columns"] and spec["columns"][0]["key"] == "day":
            spec["print_from"] = first.isoformat()


def _book_or_event_facts(result) -> None:
    """Sections without series (book, situation, alerts): their rule text as facts."""

    # Book facts rank below a material market change: the report is a market publication
    # first; a breach still reaches the findings when the market is quiet.
    weight = {"situation_event": 8.0, "book_limits": 0.9, "book_pnl": 0.5,
              "book_position": 0.4, "book_contracts": 0.1, "alerts": 0.6}.get(result.key, 0.5)
    sentences = [result.headline, *result.bullets]
    result.facts = [F.fact(f"{result.key}.{i}", result.key, result.title, None, "",
                           day="", state="current", simulated=result.simulated,
                           indicator=False, score=weight if i == 0 else weight * 0.3,
                           reason="section headline" if i == 0 else "section detail",
                           sentence=s, sources=[src["name"] for src in result.sources[:1]])
                    for i, s in enumerate(sentences) if s]
    for spec in result.tables:
        spec.setdefault("source", F.DEMO_SOURCE if result.simulated else "Eurogas Nexus.")
        if len(spec["rows"]) > F.BODY_ROWS:
            result.annex.append(dict(spec))
            spec["notes"] = (f"First {F.BODY_ROWS} of {len(spec['rows'])} rows; all rows in the "
                             "data annex.")
            spec["rows"] = spec["rows"][: F.BODY_ROWS]
    for chart in result.charts:
        chart.setdefault("id", f"fig.{result.key}")
        chart.setdefault("subtitle", f"{chart.get('title', '')}, {chart.get('unit', '')}")
        chart.setdefault("source", F.DEMO_SOURCE if result.simulated else "Eurogas Nexus.")
        chart.setdefault("types", [chart["type"]])
        chart.setdefault("windows", ["30d"])
        chart.setdefault("window", "30d")


__all__ = ["DERIVERS", "derive"]
