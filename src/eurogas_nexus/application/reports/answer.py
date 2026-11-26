"""An asked report answers its question: question-specific facts, relations, the answer.

The section builders collect the generic facts of each section. For an asked report this
module adds what the question needs on top, all deterministic and computed from the same
reads:

- **Joins the question asks for.** For a question about outages affecting Norwegian supply:
  the outage events that can be attributed to Norwegian supply (``sections.norwegian_basis``:
  a Norwegian balancing zone, a Norwegian field, plant or export pipeline, or a landing
  terminal for Norwegian gas) with their capacity as a share of the latest landings; the
  landings before and since the first of those outages began; the scheduled ones.
- **Relations the engine computed.** A fact lists the facts it was computed with under
  ``related`` (here: the landings over the days the Norwegian outages were active, and those
  outages). The editor may then put them in one sentence with a time word ("over the days
  ...", "as"); the LINKING rule still refuses a link between facts the engine did not relate,
  and no relation here is a cause (``causes`` stays empty: the data held cannot show one).
- **What the data cannot tell**: outages that cannot be attributed, flows not yet reported,
  missing sources, the forecast's missing range, and that a coincidence is not a measured
  effect.
- **The rule answer**: two to four sentences assembled from those facts, the fallback for the
  editor's answer and the answer when no model is configured.

The answer never states more than the facts it cites; where the question cannot be answered
from held data it says so plainly ("The data held does not show ...").
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from eurogas_nexus.application.reports import facts as F
from eurogas_nexus.application.reports.commentary import _sim, lose_sentence, move, number
from eurogas_nexus.application.reports.commentary import day as fday
from eurogas_nexus.application.reports.derive import _OPERATOR_CODE
from eurogas_nexus.application.reports.lang import T, zh

OUTAGE_WORDS = re.compile(r"outage|maintenance|unavailab|shut|trip|derate|停运|检修|中断", re.I)
NORWAY_WORDS = re.compile(r"norw|挪威|gassco", re.I)
SUPPLY_WORDS = re.compile(r"supply|landing|flow|import|供应|到岸|流量", re.I)
#: The sentence an answer uses when the data cannot attribute an effect.
NOT_SHOWN = "The data held does not show"
NOT_SHOWN_ZH = "所持数据无法显示"


def not_shown() -> str:
    return T(NOT_SHOWN, NOT_SHOWN_ZH)


def _avg(values: list[float]) -> float:
    return sum(values) / len(values)


def _names(rows: list[dict], most: int = 3) -> str:
    names = [r["facility"] for r in rows[:most]]
    extra = len(rows) - len(names)
    if zh():
        return "、".join(names) + (f"等{len(rows)}处" if extra > 0 else "")
    return ", ".join(names) + (f" and {extra} more" if extra > 0 else "")


def _count(n: int, one: str, many: str) -> str:
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
             8: "eight", 9: "nine"}
    return f"{words.get(n, str(n))} {one if n == 1 else many}"


def _pct(ratio: float) -> str:
    return f"{ratio:.1%}" if ratio < 0.1 else f"{ratio:.0%}"


def kind_of(question: str, sections: list[str]) -> str:
    """``outages_supply`` or ``general``; the other joins are in ``joins.py``."""

    if OUTAGE_WORDS.search(question) and (NORWAY_WORDS.search(question)
                                          or SUPPLY_WORDS.search(question)) \
            and "outages" in sections:
        return "outages_supply"
    return "general"


def _outage_supply(results: dict[str, dict], raws: dict[str, Any], today: date
                   ) -> tuple[list[dict], list[str]]:
    """Facts for "how are Norwegian outages affecting supply", and what cannot be told."""

    out: list[dict] = []
    cannot: list[str] = []
    outages = raws.get("outages") or {}
    landings = raws.get("pipeline_supply") or {}
    sim = bool((results.get("outages") or {}).get("simulated"))
    rows = [r for r in outages.get("rows") or [] if r.get("gwh")]
    active = sorted([r for r in rows if r["status"] == "active"], key=lambda r: -r["gwh"])
    scheduled = sorted([r for r in rows if r["status"] == "scheduled"],
                       key=lambda r: r["start"])
    norway = [r for r in active if r.get("norway")]
    other = [r for r in active if not r.get("norway")]
    total = sum(r["gwh"] for r in active)
    nor_gwh = sum(r["gwh"] for r in norway)
    other_gwh = total - nor_gwh
    total_l = landings.get("total") or {}
    latest = landings.get("latest")
    latest_val = total_l.get(latest) if latest else None
    state = outages.get("state", "current")
    if norway:
        ratio = nor_gwh / latest_val if latest_val else None
        basis = sorted({r["norway"] for r in norway})
        sentence = T(
            f"Of the {number(total, 'GWh/d')} offline on {fday(today)}, "
            f"{number(nor_gwh, 'GWh/d')}{_sim(sim)} is on "
            f"{_count(len(norway), 'asset', 'assets')} tied to Norwegian supply "
            f"({_names(norway)})"
            + (f", {_pct(ratio)} of the latest Norwegian landings" if ratio else "") + ".",
            f"{fday(today)}停运的{number(total, 'GWh/d')}中，{number(nor_gwh, 'GWh/d')}"
            f"{_sim(sim)}位于{len(norway)}处与挪威供应相关的资产（{_names(norway)}）"
            + (f"，相当于最新挪威到岸量的{_pct(ratio)}" if ratio else "") + "。")
        headline = T(f"Norwegian outages remove {number(nor_gwh, 'GWh/d')}",
                     f"挪威相关停运减少{number(nor_gwh, 'GWh/d')}")
    else:
        basis = []
        if not active:
            sentence = T(f"No outage is active on {fday(today)}.", f"{fday(today)}没有活跃停运。")
        elif len(active) == 1:
            sentence = T(f"The one active outage ({number(total, 'GWh/d')}{_sim(sim)} on "
                         f"{fday(today)}) is not at a Norwegian field, plant, export pipeline or "
                         "landing terminal.",
                         f"{fday(today)}唯一一处活跃停运（{number(total, 'GWh/d')}{_sim(sim)}）"
                         "不在挪威的油气田、处理厂、出口管道或登陆终端。")
        else:
            lead = "Neither of the two" if len(active) == 2 else \
                f"None of the {_count(len(active), '', '').strip()}"
            sentence = T(f"{lead} active outages ({number(total, 'GWh/d')}{_sim(sim)} on "
                         f"{fday(today)}) is at a Norwegian field, plant, export pipeline or "
                         "landing terminal.",
                         f"{fday(today)}的{len(active)}处活跃停运（合计{number(total, 'GWh/d')}"
                         f"{_sim(sim)}）均不在挪威的油气田、处理厂、出口管道或登陆终端。")
        headline = T(f"No Norwegian outage among {number(total, 'GWh/d')} offline",
                     f"停运的{number(total, 'GWh/d')}中无挪威停运")
    nor = F.fact("q.outages.norway", "outages", T("Norwegian capacity offline", "挪威停运容量"),
                 nor_gwh, "GWh/d",
                 day=F.iso(today), state=state, simulated=sim, indicator=False, score=4.0,
                 reason="the question's subject: outages attributable to Norwegian supply",
                 sentence=sentence, headline=headline,
                 sources=["REMIT urgent market messages"], exhibits=["tab.outages"])
    nor["question"] = True
    nor["basis"] = basis
    out.append(nor)
    if other:
        cannot.append(T(
            f"{number(other_gwh, 'GWh/d')} of the capacity offline is on assets the messages "
            f"do not tie to Norwegian supply (largest: {_names(other, 2)}); the data held "
            "does not show whether any of it carries Norwegian gas.",
            f"停运容量中有{number(other_gwh, 'GWh/d')}位于消息未与挪威供应关联的资产"
            f"（最大者：{_names(other, 2)}）；所持数据无法显示其中是否有挪威天然气。"))
    cannot.append(T("Outages are tied to Norwegian supply by the balancing zone and asset name "
                    "the messages give, not by where the gas comes from.",
                    "停运与挪威供应的关联依据消息给出的平衡区与资产名称，而非天然气来源。"))
    if any(r.get("norway") == "landing terminal" for r in norway):
        cannot.append(T("A landing terminal can also take gas from other sources (UK terminals "
                        "land UK shelf gas), so its outage is not necessarily all Norwegian "
                        "capacity.",
                        "登陆终端也可能接收其他来源的天然气（英国终端接收英国大陆架天然气），"
                        "因此其停运不一定全部是挪威容量。"))
    # Landings around the first Norwegian outage: the days before against the days since.
    window = None
    if norway and latest:
        first = min(date.fromisoformat(str(r["start"])[:10]) for r in norway)
        before = [d for d in total_l if first - timedelta(days=7) <= d < first]
        since = [d for d in total_l if first <= d <= latest]
        if len(before) >= 4 and since:
            b, a = _avg([total_l[d] for d in before]), _avg([total_l[d] for d in since])
            change = a - b
            lsim = _sim(bool((results.get("pipeline_supply") or {}).get("simulated")))
            window = F.fact(
                "q.landings.outage_window", "pipeline_supply",
                T("Norwegian landings since the Norwegian outages began", "挪威停运开始以来的到岸"
                                                                          "量"),
                round(a, 1), "GWh/d",
                day=F.iso(latest), state=landings.get("state", "current"),
                simulated=bool((results.get("pipeline_supply") or {}).get("simulated")),
                indicator=False, score=3.5,
                reason="the question's join: the supply series over the outages' days",
                sentence=T(f"Norwegian landings averaged {number(a, 'GWh/d')}{lsim} over the "
                           f"{_count(len(since), 'gas day', 'gas days')} from {fday(first)} to "
                           f"{fday(latest)}, while Norwegian outages were active, against "
                           f"{number(b, 'GWh/d')} in the seven days before: "
                           f"{move(change, 'GWh/d')}.",
                           f"{fday(first)}至{fday(latest)}挪威停运期间的{len(since)}个燃气日内，"
                           f"挪威到岸量平均为{number(a, 'GWh/d')}{lsim}，此前七天为"
                           f"{number(b, 'GWh/d')}：{move(change, 'GWh/d')}。"),
                related=["q.outages.norway"])
            window["question"] = True
            nor["related"] = ["q.landings.outage_window"]
            out.append(window)
        elif since == [] or first > latest:
            cannot.append(T(f"Landings are held to {fday(latest)}; the first Norwegian outage "
                            f"began {fday(first)}, so no landings are held for its days yet.",
                            f"到岸量数据截至{fday(latest)}；首个挪威停运始于{fday(first)}，"
                            "因此尚无其停运期间的到岸量。"))
        else:
            cannot.append(T("Fewer than four gas days of landings are held before the first "
                            "Norwegian outage, so no before-and-since comparison is made.",
                            "首个挪威停运之前持有的到岸量不足四个燃气日，因此不做前后比较。"))
    for index, r in enumerate([r for r in scheduled if r.get("norway")][:2], start=1):
        f = F.fact(f"q.outages.norway.next.{index}", "outages",
                   T(f"Scheduled Norwegian outage: {r['facility']}",
                     f"计划中的挪威停运：{r['facility']}"), r["gwh"], "GWh/d",
                   day=F.iso(str(r["start"])[:10]), state=state, simulated=sim,
                   indicator=False, scheduled=True, score=1.0, reason="scheduled, Norwegian",
                   sentence=lose_sentence(r["facility"], number(r["gwh"], "GWh/d") + _sim(sim),
                                           r["start"], r.get("end")))
        f["question"] = True
        out.append(f)
    if landings.get("state") in {"late", "stale"} and latest:
        cannot.append(T(f"Norwegian landings are {landings['state']}: the newest complete gas "
                        f"day held is {fday(latest)}.",
                        f"挪威到岸量数据{'延迟' if landings['state'] == 'late' else '过期'}："
                        f"最新完整燃气日为{fday(latest)}。"))
    cannot.append(T("Flows and outages moving over the same days is a coincidence in time; the "
                    "data held does not show how much of any change an outage caused.",
                    "流量与停运在同一时段变动只是时间上的重合；所持数据无法显示停运造成了多少变化。"))
    return out, cannot


def build(plan, results: list[dict], raws: dict[str, Any], *, today: date,
          missing: list[str] | None = None, ctx=None) -> dict[str, Any]:
    """Question facts (added to their sections in place), what cannot be told, and the order
    of the sections by relevance to the question."""

    question = plan.question or ""
    by_key = {r["key"]: r for r in results if r["status"] == "ok"}
    kind = kind_of(question, list(by_key))
    added: list[dict] = []
    cannot: list[str] = []
    if kind == "outages_supply":
        added, cannot = _outage_supply(by_key, raws, today)
    else:
        from eurogas_nexus.application.reports import joins
        from eurogas_nexus.application.reports.plan import _countries

        countries = list(plan.countries) or _countries(question)
        join = joins.kind_of(question, list(by_key), list(plan.hubs), countries, today)
        if join == "storage_country":
            added, cannot = joins.storage_country(by_key, raws, countries, ctx)
        elif join == "lng_country":
            added, cannot = joins.lng_country(by_key, raws, countries)
        elif join == "hub_spread" and ctx is not None:
            added, cannot = joins.hub_spread(by_key, raws, list(plan.hubs), ctx)
        elif join == "since_date":
            added, cannot = joins.since(by_key, raws, joins.since_date(question, today))
        elif join == "border_flows":
            added, cannot = joins.border_flows()
        if join:
            kind = join
    if kind == "outages_supply" and "outages" in by_key:
        # The schedule lists the outages tied to Norwegian supply first.
        nor_names = {r["facility"] for r in (raws.get("outages") or {}).get("rows") or []
                     if r.get("norway")}
        every = [r for a in by_key["outages"].get("annex") or [] for r in a.get("rows") or []]
        for spec in by_key["outages"].get("tables") or []:
            if spec.get("id") == "tab.outages" and nor_names:
                size = len(spec["rows"])
                sim = bool(by_key["outages"].get("simulated"))
                words = {"active": T("active", "活跃"), "scheduled": T("scheduled", "计划")}
                ours = [{**r, "operator": _OPERATOR_CODE.sub("", r.get("operator") or ""),
                         "simulated": sim,
                         "status_label": words.get(r.get("status"), r.get("status"))}
                        for r in every if r.get("facility") in nor_names
                        and r.get("status") != "ended"]
                rest = [r for r in spec["rows"] if r.get("facility") not in nor_names]
                spec["rows"] = (ours + rest)[:max(size, len(ours))]
                spec["notes"] = (T("Outages tied to Norwegian supply first. ",
                                   "与挪威供应相关的停运列在前面。")
                                 + (spec.get("notes") or ""))
    for fact in added:
        section = by_key.get(fact["section"])
        if section is None:
            continue
        # The question's fact leads its section's facts and, unless it is only scheduled,
        # its paragraph: each section of the evidence is tied back to the question.
        # In the join's order: after the question facts already placed in this section.
        current = section.get("facts") or []
        placed = sum(1 for f in current if f.get("question"))
        section["facts"] = [*current[:placed], fact, *current[placed:]]
        if fact["scheduled"]:
            continue
        for key in ("commentary", "rule_commentary"):
            text = section.get(key) or {}
            if text.get("headline") and text.get("question_led"):
                text["bullets"] = [fact["sentence"], *text.get("bullets", [])][:4]
                continue
            text["bullets"] = [b for b in [text.get("headline"), *text.get("bullets", [])]
                               if b][:4]
            text["headline"] = fact["sentence"]
            text["question_led"] = True
    for item in missing or []:
        cannot.insert(0, T(f"{NOT_SHOWN} {item}.", f"{NOT_SHOWN_ZH}{MISSING_ZH.get(item, item)}。"))
    for result in results:
        if result["status"] != "ok" and result.get("empty"):
            from eurogas_nexus.application.reports.render import omitted_reason, section_title

            cannot.append(f"{section_title(result['key'], result['title'])}"
                          f"{T(': ', '：')}{omitted_reason(result['empty']['reason'])}"
                          f"{T('.', '。')}")
    if "pf_pnl" in by_key or "pf_outlook" in by_key:
        budget = "variance against a budget (no budget or plan figures are held)"
        cannot.append(T(f"{NOT_SHOWN} {budget}.", f"{NOT_SHOWN_ZH}{MISSING_ZH[budget]}。"))
    if "balance" in by_key:
        cannot.append(T("The balance forecast is a model estimate with no range.",
                        "平衡预测为模型估算，没有区间。"))
    if plan.audience == "shareable" and plan.notes:
        cannot.append(T("Positions, P&L, limits, counterparties and contract terms are not "
                        "shown in a report for distribution.",
                        "对外分发的报告不显示头寸、损益、限额、交易对手或合同条款。"))
    return {"kind": kind, "cannot_tell": list(dict.fromkeys(cannot)),
            "question_keys": [f["key"] for f in added]}


def rule_answer(sheet: list[dict], info: dict[str, Any], plan) -> dict[str, Any]:
    """Two to four sentences from the question's facts (else the asked sections' weightiest
    facts), each figure from a cited fact; says plainly what the data does not show."""

    by_key = {f["key"]: f for f in sheet}
    cited: list[dict] = []
    if info["kind"] == "outages_supply":
        for key in ("q.outages.norway", "q.landings.outage_window"):
            if key in by_key:
                cited.append(by_key[key])
        if "q.landings.outage_window" not in by_key and "landings" in by_key:
            cited.append(by_key["landings"])
        nor = by_key.get("q.outages.norway")
        closing = (T(f"{NOT_SHOWN} how much of any change in landings the outages caused.",
                     f"{NOT_SHOWN_ZH}停运造成了多少到岸量变化。")
                   if nor and nor["value"] else
                   T(f"{NOT_SHOWN} a Norwegian outage affecting supply in this period.",
                     f"{NOT_SHOWN_ZH}本期有挪威停运影响供应。"))
    elif info["kind"] != "general":
        from eurogas_nexus.application.reports import joins

        # A join's own facts, in the order it computed them, then what it does not establish.
        keys = set(info.get("question_keys") or [])
        cited = [f for f in sheet if f["key"] in keys and not f.get("scheduled")][:3]
        closing = joins.closing(info["kind"]) if cited else next(
            (c for c in info["cannot_tell"] if c.startswith((NOT_SHOWN, NOT_SHOWN_ZH))), None)
    elif any(f["section"].startswith("pf_") for f in sheet):
        # A portfolio question: where the book stands forward, what it is worth, what was
        # traded (each section's headline fact), then what the data cannot tell.
        heads = {f["section"]: f for f in sheet if f["key"].endswith(".0") and f.get("sentence")
                 and f["score"] > 0}
        cited = [heads[key] for key in ("pf_outlook", "pf_pnl", "pf_trades") if key in heads]
        closing = next((c for c in info["cannot_tell"]
                        if c.startswith((NOT_SHOWN, NOT_SHOWN_ZH))), None)
    else:
        ranked = sorted((f for f in sheet if f.get("sentence") and not f.get("scheduled")
                         and not f.get("forecast")), key=lambda f: -f["score"])
        cited = ranked[:2]
        closing = next((c for c in info["cannot_tell"]
                        if c.startswith((NOT_SHOWN, NOT_SHOWN_ZH))), None)
    sentences = [f["sentence"] for f in cited if f.get("sentence")][:3]
    if closing:
        sentences.append(closing)
    if not sentences:
        empty = [c for c in info["cannot_tell"] if not c.startswith((NOT_SHOWN, NOT_SHOWN_ZH))][:2]
        detail = "; ".join(e.rstrip(".。") for e in empty)
        sentences = [T(f"{NOT_SHOWN} any figure for this: none of the sections chosen holds "
                       "data" + (f" ({detail})." if empty else "."),
                       f"{NOT_SHOWN_ZH}相关数据：所选章节均无数据"
                       + (f"（{detail}）。" if empty else "。"))]
    return {"text": (" " if not zh() else "").join(sentences),
            "fact_ids": [f["id"] for f in cited], "basis": "rule"}


#: What the platform does not hold, in Chinese (``plan.NOT_HELD``).
MISSING_ZH = {
    "oil prices (no oil source is connected)": "原油价格（未接入原油数据源）",
    "coal prices (licensed exchange data, not connected here)": "煤炭价格（需交易所授权数据，此处"
                                                                "未接入）",
    "carbon prices (licensed exchange data, not connected here)": "碳价（需交易所授权数据，此处未"
                                                                  "接入）",
    "a weather section (weather enters only the balance forecast)": "天气章节（天气仅用于平衡预测"
                                                                    "）",
    "Asian demand and prices (the platform covers NW Europe)": "亚洲需求与价格（平台覆盖西北欧）",
    "LNG cargo tracking (no vessel source is connected)": "LNG 船货跟踪（未接入船舶数据源）",
    "power prices in a report section": "电价章节",
    "variance against a budget (no budget or plan figures are held)":
        "与预算的差异（平台未持有预算或计划数据）",
}


def relevance_order(sheet: list[dict], answer: dict, sections: list[str]) -> list[str]:
    """Sections that hold the answer's facts first (in the answer's order), then the rest
    by the weight of their question facts, then in plan order."""

    by_id = {f["id"]: f for f in sheet}
    order: list[str] = []
    for fact_id in answer.get("fact_ids") or []:
        section = (by_id.get(fact_id) or {}).get("section")
        if section in sections and section not in order:
            order.append(section)
    weight = {s: max([f["score"] for f in sheet if f["section"] == s and f.get("question")]
                     or [0.0]) for s in sections}
    rest = sorted((s for s in sections if s not in order), key=lambda s: -weight[s])
    return order + rest


__all__ = ["NOT_SHOWN", "build", "kind_of", "relevance_order", "rule_answer"]
