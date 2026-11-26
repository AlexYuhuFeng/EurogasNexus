"""Question joins: engine-computed facts that relate two things a question names.

An asked report answers from facts, and a question often relates two of them: a country's
storage against NW Europe's, one country's LNG send-out against the total, the spread between
two hubs, what moved since a date. Each join here computes those facts from the sections' own
reads, declares the relation it computed (``fact["relation"]``), and says what the data cannot
tell. No join states a cause; a relation is arithmetic on held figures (a share, a difference, a
change), never "because".

``answer.build`` picks the join (:func:`kind_of`) and adds its facts to their sections; the
rule answer cites them. The Norwegian outages join stays in ``answer.py``.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from eurogas_nexus.application.reports import facts as F
from eurogas_nexus.application.reports.commentary import _sim, number
from eurogas_nexus.application.reports.commentary import day as fday
from eurogas_nexus.application.reports.lang import T, country

NOT_SHOWN = "The data held does not show"
NOT_SHOWN_ZH = "所持数据无法显示"

STORAGE_WORDS = re.compile(r"storage|stock|inventor|fill|储气|库存|充注", re.I)
LNG_WORDS = re.compile(r"\blng\b|send-?out|regas|terminal|液化天然气|气化外输|接收站", re.I)
SPREAD_WORDS = re.compile(r"spread|differential|premium|discount|versus|vs\.?|against|价差|"
                          r"溢价|贴水|对比", re.I)
SINCE = re.compile(
    r"(?:since|from)\s+(\d{4}-\d{2}-\d{2}|\d{1,2}\s+[A-Za-z]{3,9}(?:\s+\d{4})?)"
    r"|(?:自|从)?\s*(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日\s*(?:以来|起|至今)", re.I)
BORDER_WORDS = re.compile(r"border|interconnect|cross-border|跨境|边境|互联", re.I)

def _pts(value: float) -> str:
    """``0.45 points`` / ``0.45个百分点``."""

    return T(f"{number(value, digits=1)} points", f"{number(value, digits=1)}个百分点")


#: The relations a join may declare: the arithmetic the engine did.
RELATIONS = ("share_of", "difference", "change_since", "spread")


def since_date(question: str, today: date) -> date | None:
    """The date a "what changed since <date>" question names (no later than today)."""

    match = SINCE.search(question)
    if not match:
        return None
    try:
        if match.group(1):
            text = match.group(1)
            if re.match(r"\d{4}-", text):
                found = date.fromisoformat(text)
            else:
                from datetime import datetime

                parts = text.split()
                year = int(parts[2]) if len(parts) > 2 else today.year
                found = datetime.strptime(f"{parts[0]} {parts[1][:3]} {year}", "%d %b %Y").date()
        else:
            year = int(match.group(2)) if match.group(2) else today.year
            found = date(year, int(match.group(3)), int(match.group(4)))
    except ValueError:
        return None
    if found > today:
        found = found.replace(year=found.year - 1)
    return found


def kind_of(question: str, sections: list[str], hubs: list[str], countries: list[str],
            today: date) -> str | None:
    """The join a question asks for, or ``None``."""

    if since_date(question, today) is not None:
        return "since_date"
    if BORDER_WORDS.search(question):
        return "border_flows"
    if len(hubs) >= 2 and "prices" in sections and SPREAD_WORDS.search(question):
        return "hub_spread"
    if countries and "lng" in sections and LNG_WORDS.search(question):
        return "lng_country"
    if countries and "storage" in sections and STORAGE_WORDS.search(question):
        return "storage_country"
    return None


def _q(key: str, section: str, label: str, value: float | None, unit: str, *, day: str,
       state: str, sim: bool, sentence: str, relation: str, score: float = 4.0,
       sources: list[str] | None = None) -> dict[str, Any]:
    fact = F.fact(key, section, label, value, unit, day=day, state=state, simulated=sim,
                  indicator=False, score=score, sentence=sentence, sources=sources or [],
                  reason=f"the question's subject ({relation})")
    fact["question"] = True
    fact["relation"] = relation
    return fact


# ------------------------------------------------------------------------- storage x country


def storage_country(results: dict, raws: dict, countries: list[str], ctx=None
                    ) -> tuple[list, list]:
    """A country's storage against NW Europe and against its own history, from the storage
    fundamentals read (``fundamentals_storage.storage_read``: the N-year average and band,
    N = complete prior gas years held, stated); the reports' own read is the fallback."""

    read = None
    if ctx is not None:
        from eurogas_nexus.application.fundamentals_storage import storage_read

        try:
            read = storage_read(ctx.session, ctx.caller.principal, region="nwe", now=ctx.now)
        except Exception:  # noqa: BLE001 - the reports' own storage read stands in
            ctx.session.rollback()
            read = None
    if not read or not read.get("countries"):
        return _storage_country_basic(results, raws, countries)
    by_code = {c["code"]: c for c in read["countries"]}
    region = read.get("region") or {}
    nwe = region.get("fill_pct")
    out, cannot = [], []
    for code in countries:
        view = by_code.get(code)
        if not view or view.get("fill_pct") is None:
            cannot.append(T(f"{NOT_SHOWN} {country(code)} storage: no facility there publishes "
                            "a working capacity in the data held.",
                            f"{NOT_SHOWN_ZH}{country(code)}储气：所持数据中该国没有公布工作容量的"
                            "设施。"))
            continue
        sim = bool(view.get("simulated"))
        fill, day = view["fill_pct"], view["as_of"]
        gap = fill - nwe if nwe is not None else None
        avg = view.get("vs_average") or {}
        years = avg.get("years") or 0
        parts_en, parts_zh = [], []
        if gap is not None:
            side_en, side_zh = ("above", "高于") if gap > 0 else ("below", "低于")
            parts_en.append(f"{_pts(abs(gap))} {side_en} the NW Europe fill of {number(nwe, '%')}")
            parts_zh.append(f"{side_zh}西北欧储气率{number(nwe, '%')}，相差{_pts(abs(gap))}")
        if years and avg.get("diff_pts") is not None:
            d = avg["diff_pts"]
            side_en, side_zh = ("above", "高于") if d > 0 else ("below", "低于")
            parts_en.append(f"{_pts(abs(d))} {side_en} its {years}-year average for the day")
            parts_zh.append(f"{side_zh}其{years}年同日均值{_pts(abs(d))}")
            if avg.get("outside") in {"above", "below"} and years >= 5:
                parts_en.append(f"{avg['outside']} its five-year range")
                parts_zh.append("高于其五年区间" if avg["outside"] == "above" else "低于其五年区间")
        sentence = T(
            f"{country(code)} storage was {number(fill, '%')}{_sim(sim)} full on {fday(day)} "
            f"({number(view.get('stock_twh'), 'TWh')} of "
            f"{number(view.get('working_capacity_twh'), 'TWh')} working capacity)"
            + (", " + ", ".join(parts_en) if parts_en else "") + ".",
            f"{fday(day)}{country(code)}储气率为{number(fill, '%')}{_sim(sim)}（工作容量"
            f"{number(view.get('working_capacity_twh'), 'TWh')}中的"
            f"{number(view.get('stock_twh'), 'TWh')}）"
            + ("，" + "，".join(parts_zh) if parts_zh else "") + "。")
        out.append(_q(f"q.storage.{code}", "storage",
                      T(f"{country(code)} storage fill", f"{country(code)}储气率"), fill, "%",
                      day=day, state="current", sim=sim, sentence=sentence,
                      relation="difference", sources=["GIE storage (AGSI)"]))
        if years and years < 5:
            cannot.append(T(f"The {country(code)} average rests on {years} complete gas "
                            f"year{'s' if years != 1 else ''} held, not five.",
                            f"{country(code)}的均值仅基于所持{years}个完整气年，而非五年。"))
    cannot.append(T("A country's fill counts only its facilities that publish a working "
                    "capacity, as the NW Europe fill does.",
                    "国别储气率与西北欧储气率一样，只计入公布工作容量的设施。"))
    return out, cannot


def _storage_country_basic(results: dict, raws: dict, countries: list[str]) -> tuple[list, list]:
    raw = raws.get("storage") or {}
    by_country, week = raw.get("by_country") or {}, raw.get("by_country_week") or {}
    sim = bool((results.get("storage") or {}).get("simulated"))
    latest = raw.get("latest")
    out, cannot = [], []
    if not by_country or latest is None:
        return out, [T(f"{NOT_SHOWN} storage by country for this period.",
                       f"{NOT_SHOWN_ZH}本期分国别的储气数据。")]
    inv_all = sum(v[0] for v in by_country.values())
    cap_all = sum(v[1] for v in by_country.values())
    nwe = 100 * inv_all / cap_all if cap_all else None
    for code in countries:
        held = by_country.get(code)
        if not held or not held[1]:
            cannot.append(T(f"{NOT_SHOWN} {country(code)} storage: no facility there publishes "
                            "a working capacity in the data held.",
                            f"{NOT_SHOWN_ZH}{country(code)}储气：所持数据中该国没有公布工作容量的"
                            "设施。"))
            continue
        fill = 100 * held[0] / held[1]
        gap = fill - nwe if nwe is not None else None
        prior = week.get(code)
        moved = (fill - 100 * prior[0] / prior[1]) if prior and prior[1] else None
        side = (T("above", "高于") if gap and gap > 0 else T("below", "低于")) if gap else ""
        sentence = T(
            f"{country(code)} storage was {number(fill, '%')}{_sim(sim)} full on {fday(latest)} "
            f"({number(held[0], 'TWh')} of {number(held[1], 'TWh')} working capacity)"
            + (f", {_pts(abs(gap))} {side} the NW Europe fill of {number(nwe, '%')}"
               if gap is not None else "")
            + (f", having {'risen' if moved > 0 else 'fallen'} {_pts(abs(moved))} in "
               "seven days" if moved else "") + ".",
            f"{fday(latest)}{country(code)}储气率为{number(fill, '%')}{_sim(sim)}（工作容量"
            f"{number(held[1], 'TWh')}中的{number(held[0], 'TWh')}）"
            + (f"，{side}西北欧储气率{number(nwe, '%')}，相差{_pts(abs(gap))}"
               if gap is not None else "")
            + (f"，七天内{'上升' if moved > 0 else '下降'}{_pts(abs(moved))}"
               if moved else "") + "。")
        out.append(_q(f"q.storage.{code}", "storage",
                      T(f"{country(code)} storage fill", f"{country(code)}储气率"), round(fill, 2),
                      "%", day=F.iso(latest), state=raw.get("state", "current"), sim=sim,
                      sentence=sentence, relation="difference",
                      sources=["GIE storage (AGSI)"]))
    cannot.append(T("A country's fill counts only its facilities that publish a working "
                    "capacity, as the NW Europe fill does.",
                    "国别储气率与西北欧储气率一样，只计入公布工作容量的设施。"))
    return out, cannot


# ----------------------------------------------------------------------------- LNG x country


def lng_country(results: dict, raws: dict, countries: list[str]) -> tuple[list, list]:
    raw = raws.get("lng") or {}
    by_day = raw.get("by_day") or {}
    sim = bool((results.get("lng") or {}).get("simulated"))
    out, cannot = [], []
    days = sorted(by_day)
    if not days:
        return out, [T(f"{NOT_SHOWN} LNG send-out by country for this period.",
                       f"{NOT_SHOWN_ZH}本期分国别的 LNG 外输数据。")]
    last = days[-1]
    total = sum(by_day[last].values())
    week = [d for d in days if d > last - timedelta(days=7)]
    for code in countries:
        value = by_day[last].get(code)
        if value is None:
            cannot.append(T(f"{NOT_SHOWN} LNG send-out in {country(code)} on {fday(last)}.",
                            f"{NOT_SHOWN_ZH}{fday(last)}{country(code)}的 LNG 外输。"))
            continue
        share = 100 * value / total if total else None
        avg = sum(by_day[d].get(code, 0.0) for d in week) / len(week)
        sentence = T(
            f"{country(code)} terminals sent out {number(value, 'GWh/d')}{_sim(sim)} on "
            f"{fday(last)}"
            + (f", {number(share, '%')} of the NW Europe total of {number(total, 'GWh/d')}"
               if share is not None else "")
            + f"; they averaged {number(avg, 'GWh/d')} over the last {len(week)} days.",
            f"{fday(last)}{country(code)}接收站外输{number(value, 'GWh/d')}{_sim(sim)}"
            + (f"，占西北欧合计{number(total, 'GWh/d')}的{number(share, '%')}"
               if share is not None else "")
            + f"；最近{len(week)}天平均{number(avg, 'GWh/d')}。")
        out.append(_q(f"q.lng.{code}", "lng", T(f"{country(code)} LNG send-out",
                                                 f"{country(code)} LNG 外输"),
                      round(value, 1), "GWh/d", day=F.iso(last), state=raw.get("state", "current"),
                      sim=sim, sentence=sentence, relation="share_of",
                      sources=["GIE LNG (ALSI)"]))
    cannot.append(T("Send-out is by country; the data held does not split it by terminal or by "
                    "where the cargo came from.",
                    "外输按国家统计；所持数据未按接收站或货源拆分。"))
    return out, cannot


# ------------------------------------------------------------------------------- hub spread


def hub_spread(results: dict, raws: dict, hubs: list[str], ctx) -> tuple[list, list]:
    """The spread between two hubs over the period, in the first hub's unit. A second hub
    quoted in another unit is converted, contract by contract, at the FX for its delivery
    month (``market_normalisation``: forward by covered interest parity, or spot when the
    month is prompt or no forward can be derived), each rate stated."""

    from eurogas_nexus.application.market_normalisation import NormalisationError, conversion

    prices = {h["hub"]: h for h in (raws.get("prices") or {}).get("hubs") or []}
    a, b = hubs[0], hubs[1]
    out, cannot = [], []
    if a not in prices or b not in prices:
        missing = [h for h in (a, b) if h not in prices]
        return out, [T(f"{NOT_SHOWN} a close for {', '.join(missing)} under your licences.",
                       f"{NOT_SHOWN_ZH}您许可范围内{'、'.join(missing)}的收盘价。")]
    ha, hb = prices[a], prices[b]
    unit = ha["unit"]
    start = ctx.start if ctx.period_label else ctx.end - timedelta(days=29)
    days = sorted(d for d in ha["series"] if d in hb["series"] and start <= d <= ctx.end)
    if not days:
        return out, [T(f"{NOT_SHOWN} a day on which both {a} and {b} closed in the period.",
                       f"{NOT_SHOWN_ZH}期间{a}与{b}同时收盘的日子。")]
    factors: dict[date, float] = {d: 1.0 for d in days}
    rate_note = ""
    if hb["unit"] != unit:
        from eurogas_nexus.application.reports.derive import _fx_holdings

        holdings = _fx_holdings(ctx)
        # Each front-month contract converts at the FX for its delivery month (forward, D.5;
        # spot when the month is prompt or no forward can be derived; the method is stated).
        by_contract: dict[str, list[date]] = {}
        for d in days:
            by_contract.setdefault(str((hb.get("contract") or {}).get(d) or ""), []).append(d)
        notes: list[str] = []
        conv = None
        for label, held in by_contract.items():
            try:
                conv = conversion(hb["unit"], unit, holdings=holdings, as_of=held[-1],
                                  delivery=_month_delivery(label))
            except NormalisationError:
                try:
                    conv = conversion(hb["unit"], unit, holdings=holdings, as_of=held[-1])
                except NormalisationError as exc:
                    return out, [T(f"{NOT_SHOWN} the {a}–{b} spread: {b} cannot be put into "
                                   f"{unit} ({exc}).",
                                   f"{NOT_SHOWN_ZH}{a}–{b}价差：{b}无法折算为{unit}"
                                   f"（{_unconvertible_zh(exc)}）。")]
            for d in held:
                factors[d] = conv.factor
            fx = conv.fx
            if fx:
                name = (_month_delivery(label).label if _month_delivery(label) else label) or b
                notes.append(T(f"{name}: {fx.base}{fx.quote} {fx.rate:.4f} ({fx.method}"
                               + (f", value date {fx.value_date}" if fx.value_date else "") + ")",
                               f"{name}：{fx.base}{fx.quote} {fx.rate:.4f}"
                               + (f"（起息日 {fx.value_date}）" if fx.value_date else "")))
        if conv is not None:
            rate_note = T(f"{b} is converted from {hb['unit']} to {unit} with a unit factor of "
                          f"{conv.unit_factor:.6g} and, per contract, the FX for its delivery "
                          "month: " + "; ".join(notes) + ".",
                          f"{b}由{hb['unit']}折算为{unit}，单位系数{conv.unit_factor:.6g}，各合约"
                          "按其交割月汇率：" + "；".join(notes) + "。")
    spread = {d: ha["series"][d] - hb["series"][d] * factors[d] for d in days}
    last = days[-1]
    avg = sum(spread.values()) / len(days)
    wide, narrow = max(days, key=lambda d: spread[d]), min(days, key=lambda d: spread[d])
    sim = bool(ha.get("simulated") or hb.get("simulated"))
    sentence = T(
        f"{a} closed {number(abs(spread[last]), unit)}{_sim(sim)} "
        f"{'above' if spread[last] >= 0 else 'below'} {b} on {fday(last)}; over the "
        f"{len(days)} common close days from {fday(days[0])} the {a}–{b} spread averaged "
        f"{number(avg, unit)}, from {number(spread[narrow], unit)} on {fday(narrow)} to "
        f"{number(spread[wide], unit)} on {fday(wide)}.",
        f"{fday(last)}{a}收盘{'高于' if spread[last] >= 0 else '低于'}{b}"
        f"{number(abs(spread[last]), unit)}{_sim(sim)}；自{fday(days[0])}起的{len(days)}个共同"
        f"收盘日内，{a}–{b}价差平均为{number(avg, unit)}，介于{fday(narrow)}的"
        f"{number(spread[narrow], unit)}与{fday(wide)}的{number(spread[wide], unit)}之间。")
    out.append(_q(f"q.spread.{a}.{b}", "prices", f"{a}–{b} spread", round(spread[last], 3),
                  unit, day=F.iso(last), state=ha.get("state", "current"), sim=sim,
                  sentence=sentence, relation="spread",
                  sources=[f"{a} closes", f"{b} closes"]))
    cannot.append(T("The spread compares front-month closes; it is not a delivered or "
                    "transport-adjusted spread.",
                    "价差比较的是近月收盘价，并非交付价差，也未计入运输成本。"))
    if rate_note:
        cannot.append(rate_note)
    return out, cannot


def _month_delivery(label: str):
    """The delivery month of a front-month contract label (``Dec-26``), else ``None``."""

    import calendar
    from datetime import datetime

    from eurogas_nexus.domain.market.fx_forward import Delivery

    first = None
    for pattern in ("%b-%y", "%Y-%m-%d", "%Y-%m"):
        try:
            first = datetime.strptime(label, pattern).date().replace(day=1)
            break
        except ValueError:
            continue
    if first is None:
        return None
    last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
    return Delivery(first=first, last=last, kind="month", label=f"{first:%b-%y}")


# ------------------------------------------------------------------------- since a date


def since(results: dict, raws: dict, start: date) -> tuple[list, list]:
    """What moved from ``start`` to the newest day held, indicator by indicator."""

    out, cannot = [], []

    def at_or_before(series: dict, day: date):
        held = [d for d in series if d <= day]
        return (max(held), series[max(held)]) if held else (None, None)

    def add(key, section, label, series, unit, sim, state):
        if not series:
            return
        last = max(series)
        first_day, first = at_or_before(series, start)
        if first_day is None or first_day >= last:
            cannot.append(T(f"{NOT_SHOWN} {label} on or before {fday(start)}.",
                            f"{NOT_SHOWN_ZH}{fday(start)}或之前的{label}。"))
            return
        change = series[last] - first
        word = ((T("up", "上升") if change > 0 else T("down", "下降")) if change
                else T("flat", "持平"))
        moved = _pts(abs(change)) if unit == "%" else number(abs(change), unit)
        sentence = T(
            f"{label} stood at {number(series[last], unit)}{_sim(sim)} on {fday(last)}, {word} "
            f"{moved} from {number(first, unit)} on {fday(first_day)}.",
            f"{fday(last)}{label}为{number(series[last], unit)}{_sim(sim)}，较{fday(first_day)}的"
            f"{number(first, unit)}{word}{moved}。")
        out.append(_q(f"q.since.{key}", section, label, round(series[last], 3), unit,
                      day=F.iso(last), state=state, sim=sim, sentence=sentence,
                      relation="change_since", score=3.0 + min(abs(change) / (abs(first) or 1),
                                                              1.0)))

    for hub in (raws.get("prices") or {}).get("hubs") or []:
        if hub["hub"] in {"TTF", "NBP"}:
            add(f"price.{hub['hub']}", "prices", f"{hub['hub']} {hub['product']}",
                hub["series"], hub["unit"], hub.get("simulated"), hub.get("state", "current"))
    landings = raws.get("pipeline_supply") or {}
    add("landings", "pipeline_supply", T("Norwegian pipeline landings", "挪威管道到岸量"),
        landings.get("total") or {}, "GWh/d",
        (results.get("pipeline_supply") or {}).get("simulated"), landings.get("state", "current"))
    lng = raws.get("lng") or {}
    add("lng", "lng", T("NW Europe LNG send-out", "西北欧 LNG 外输"), lng.get("total") or {},
        "GWh/d", (results.get("lng") or {}).get("simulated"), lng.get("state", "current"))
    storage = raws.get("storage") or {}
    add("storage", "storage", T("NW Europe storage fill", "西北欧储气率"),
        storage.get("fill") or {}, "%", (results.get("storage") or {}).get("simulated"),
        storage.get("state", "current"))
    cannot.append(T("Each change compares the newest day held with the last day held on or "
                    "before the date asked; it says what moved, not why.",
                    "每项变化比较最新数据日与所问日期当日或之前的最后数据日；只说明变化，不说明原因。"))
    return out, cannot


# ------------------------------------------------------------------------------ border flows


def border_flows() -> tuple[list, list]:
    """Flows at a border point are not a report section: say so, and where they are."""

    return [], [T(f"{NOT_SHOWN} flows at a border point: reports hold Norwegian landings by "
                  "terminal, not cross-border points; the Network view shows those flows.",
                  f"{NOT_SHOWN_ZH}边境点流量：报告只含按接收端统计的挪威到岸量，不含跨境点；"
                  "跨境流量见管网视图。")]


def closing(kind: str) -> str:
    """The answer's last sentence for a join: what the relation does not establish."""

    return {
        "storage_country": T(f"{NOT_SHOWN} why the two fills differ.",
                             f"{NOT_SHOWN_ZH}两者储气率差异的原因。"),
        "lng_country": T(f"{NOT_SHOWN} where the cargoes came from or why send-out moved.",
                         f"{NOT_SHOWN_ZH}货源或外输变化的原因。"),
        "hub_spread": T(f"{NOT_SHOWN} what drove the spread.",
                        f"{NOT_SHOWN_ZH}价差变化的驱动因素。"),
        "since_date": T(f"{NOT_SHOWN} what caused these moves.", f"{NOT_SHOWN_ZH}这些变化的原因。"),
        "border_flows": T(f"{NOT_SHOWN} flows at a border point.", f"{NOT_SHOWN_ZH}边境点流量。"),
    }.get(kind, "")


__all__ = ["RELATIONS", "border_flows", "closing", "hub_spread", "kind_of", "lng_country",
           "since", "since_date", "storage_country"]


def _unconvertible_zh(exc: Exception) -> str:
    """Why a conversion was refused, in Chinese: the engine's reason is English, and a Chinese
    report should not print it raw ("not convertible: no EURGBP rate held")."""
    import re

    held = re.search(r"no (EUR[A-Z]{3}) rate held", str(exc))
    if held:
        return f"未持有截至该日的 {held.group(1)} 汇率"
    if "forward" in str(exc):
        return "无可用的远期汇率"
    return "缺少所需的汇率或换算系数"
