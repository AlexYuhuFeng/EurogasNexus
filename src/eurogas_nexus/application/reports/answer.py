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
from eurogas_nexus.application.reports.commentary import day as fday
from eurogas_nexus.application.reports.commentary import move, number
from eurogas_nexus.application.reports.derive import _OPERATOR_CODE

OUTAGE_WORDS = re.compile(r"outage|maintenance|unavailab|shut|trip|derate|停运|检修|中断", re.I)
NORWAY_WORDS = re.compile(r"norw|挪威|gassco", re.I)
SUPPLY_WORDS = re.compile(r"supply|landing|flow|import|供应|到岸|流量", re.I)
#: The sentence an answer uses when the data cannot attribute an effect.
NOT_SHOWN = "The data held does not show"


def _sim(flag: bool) -> str:
    return " (simulated)" if flag else ""


def _avg(values: list[float]) -> float:
    return sum(values) / len(values)


def _names(rows: list[dict], most: int = 3) -> str:
    names = [r["facility"] for r in rows[:most]]
    extra = len(rows) - len(names)
    return ", ".join(names) + (f" and {extra} more" if extra > 0 else "")


def _count(n: int, one: str, many: str) -> str:
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven",
             8: "eight", 9: "nine"}
    return f"{words.get(n, str(n))} {one if n == 1 else many}"


def kind_of(question: str, sections: list[str]) -> str:
    """Which join the question asks for: ``outages_supply`` or ``general``."""

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
        share = "" if ratio is None else (
            f", {ratio:.1%} of the latest Norwegian landings" if ratio < 0.1 else
            f", {ratio:.0%} of the latest Norwegian landings")
        basis = sorted({r["norway"] for r in norway})
        sentence = (f"Of the {number(total, 'GWh/d')} offline on {fday(today)}, "
                    f"{number(nor_gwh, 'GWh/d')}{_sim(sim)} is on "
                    f"{_count(len(norway), 'asset', 'assets')} tied to Norwegian supply "
                    f"({_names(norway)}){share}.")
        headline = f"Norwegian outages remove {number(nor_gwh, 'GWh/d')}"
    else:
        basis = []
        where = ("on a Norwegian field, plant, export pipeline or landing terminal, by the zone "
                 "and asset the messages name")
        if not active:
            sentence = f"No outage is active on {fday(today)} among the messages held."
        elif len(active) == 1:
            sentence = (f"The one active outage ({number(total, 'GWh/d')}{_sim(sim)} on "
                        f"{fday(today)}) is not {where}.")
        else:
            lead = "Neither of the two" if len(active) == 2 else \
                f"None of the {_count(len(active), '', '').strip()}"
            sentence = (f"{lead} active outages ({number(total, 'GWh/d')}{_sim(sim)} on "
                        f"{fday(today)}) is {where}.")
        headline = "No active outage on a Norwegian asset is held"
    nor = F.fact("q.outages.norway", "outages", "Norwegian capacity offline", nor_gwh, "GWh/d",
                 day=F.iso(today), state=state, simulated=sim, indicator=False, score=4.0,
                 reason="the question's subject: outages attributable to Norwegian supply",
                 sentence=sentence, headline=headline,
                 sources=["REMIT urgent market messages"], exhibits=["tab.outages"])
    nor["question"] = True
    nor["basis"] = basis
    out.append(nor)
    if other:
        cannot.append(
            f"{number(other_gwh, 'GWh/d')} of the capacity offline is on assets the messages "
            f"do not tie to Norwegian supply (largest: {_names(other, 2)}); the data held "
            "does not show whether any of it carries Norwegian gas.")
    if any(r.get("norway") == "landing terminal" for r in norway):
        cannot.append("A landing terminal can also take gas from other sources (UK terminals "
                      "land UK shelf gas), so its outage is not necessarily all Norwegian "
                      "capacity.")
    # Landings around the first Norwegian outage: the days before against the days since.
    window = None
    if norway and latest:
        first = min(date.fromisoformat(str(r["start"])[:10]) for r in norway)
        before = [d for d in total_l if first - timedelta(days=7) <= d < first]
        since = [d for d in total_l if first <= d <= latest]
        if len(before) >= 4 and since:
            b, a = _avg([total_l[d] for d in before]), _avg([total_l[d] for d in since])
            change = a - b
            window = F.fact(
                "q.landings.outage_window", "pipeline_supply",
                "Norwegian landings since the Norwegian outages began", round(a, 1), "GWh/d",
                day=F.iso(latest), state=landings.get("state", "current"),
                simulated=bool((results.get("pipeline_supply") or {}).get("simulated")),
                indicator=False, score=3.5,
                reason="the question's join: the supply series over the outages' days",
                sentence=(f"Norwegian landings averaged {number(a, 'GWh/d')} over the "
                          f"{_count(len(since), 'gas day', 'gas days')} from {fday(first)} to "
                          f"{fday(latest)}, while Norwegian outages were active, against "
                          f"{number(b, 'GWh/d')} in the seven days before: "
                          f"{move(change, 'GWh/d')}."),
                related=["q.outages.norway"])
            window["question"] = True
            nor["related"] = ["q.landings.outage_window"]
            out.append(window)
        elif since == [] or first > latest:
            cannot.append(f"Landings are held to {fday(latest)}; the first Norwegian outage "
                          f"began {fday(first)}, so its effect is not yet in the flows held.")
        else:
            cannot.append("Fewer than four gas days of landings are held before the first "
                          "Norwegian outage, so no before-and-since comparison is made.")
    for index, r in enumerate([r for r in scheduled if r.get("norway")][:2], start=1):
        f = F.fact(f"q.outages.norway.next.{index}", "outages",
                   f"Scheduled Norwegian outage: {r['facility']}", r["gwh"], "GWh/d",
                   day=F.iso(str(r["start"])[:10]), state=state, simulated=sim,
                   indicator=False, scheduled=True, score=1.0, reason="scheduled, Norwegian",
                   sentence=(f"{r['facility']} is scheduled to lose {number(r['gwh'], 'GWh/d')}"
                             f"{_sim(sim)} from {fday(str(r['start'])[:10])}"
                             + (f" to {fday(str(r['end'])[:10])}" if r.get("end") else "")
                             + "."))
        f["question"] = True
        out.append(f)
    if landings.get("state") in {"late", "stale"} and latest:
        cannot.append(f"Norwegian landings are {landings['state']}: the newest complete gas day "
                      f"held is {fday(latest)}.")
    cannot.append("A change in flows over the days an outage is active is a coincidence the "
                  "report states; the data held does not show how much of it the outage "
                  "caused.")
    return out, cannot


def build(plan, results: list[dict], raws: dict[str, Any], *, today: date,
          missing: list[str] | None = None) -> dict[str, Any]:
    """Question facts (added to their sections in place), what cannot be told, and the order
    of the sections by relevance to the question."""

    question = plan.question or ""
    by_key = {r["key"]: r for r in results if r["status"] == "ok"}
    kind = kind_of(question, list(by_key))
    added: list[dict] = []
    cannot: list[str] = []
    if kind == "outages_supply":
        added, cannot = _outage_supply(by_key, raws, today)
    if kind == "outages_supply" and "outages" in by_key:
        # The schedule lists the outages tied to Norwegian supply first.
        nor_names = {r["facility"] for r in (raws.get("outages") or {}).get("rows") or []
                     if r.get("norway")}
        every = [r for a in by_key["outages"].get("annex") or [] for r in a.get("rows") or []]
        for spec in by_key["outages"].get("tables") or []:
            if spec.get("id") == "tab.outages" and nor_names:
                size = len(spec["rows"])
                sim = bool(by_key["outages"].get("simulated"))
                ours = [{**r, "operator": _OPERATOR_CODE.sub("", r.get("operator") or ""),
                         "simulated": sim}
                        for r in every if r.get("facility") in nor_names
                        and r.get("status") != "ended"]
                rest = [r for r in spec["rows"] if r.get("facility") not in nor_names]
                spec["rows"] = (ours + rest)[:max(size, len(ours))]
                spec["notes"] = ("Outages tied to Norwegian supply first. "
                                 + (spec.get("notes") or ""))
    for fact in added:
        section = by_key.get(fact["section"])
        if section is None:
            continue
        # The question's fact leads its section's facts and, unless it is only scheduled,
        # its paragraph: each section of the evidence is tied back to the question.
        section["facts"] = [fact, *(section.get("facts") or [])]
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
        cannot.insert(0, f"{NOT_SHOWN} {item}.")
    for result in results:
        if result["status"] != "ok" and result.get("empty"):
            cannot.append(f"{result['title']}: {result['empty']['reason']}.")
    if "balance" in by_key:
        cannot.append("The balance forecast is a model estimate with no range.")
    if plan.audience == "shareable" and plan.notes:
        cannot.append("This report is for distribution: it holds no position, P&L, limit, "
                      "counterparty or contract term.")
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
        closing = (f"{NOT_SHOWN} how much of any change in landings the outages caused."
                   if nor and nor["value"] else
                   f"{NOT_SHOWN} a Norwegian outage affecting supply in this period.")
    else:
        ranked = sorted((f for f in sheet if f.get("sentence") and not f.get("scheduled")
                         and not f.get("forecast")), key=lambda f: -f["score"])
        cited = ranked[:2]
        closing = (f"{NOT_SHOWN} " + info["cannot_tell"][0][len(NOT_SHOWN) + 1:]
                   if info["cannot_tell"] and info["cannot_tell"][0].startswith(NOT_SHOWN)
                   else None)
    sentences = [f["sentence"] for f in cited if f.get("sentence")][:3]
    if closing:
        sentences.append(closing)
    if not sentences:
        empty = [c for c in info["cannot_tell"] if not c.startswith(NOT_SHOWN)][:2]
        sentences = [f"{NOT_SHOWN} anything on this question: no section asked for holds data"
                     + (f" ({'; '.join(e.rstrip('.') for e in empty)})." if empty else ".")]
    return {"text": " ".join(sentences), "fact_ids": [f["id"] for f in cited], "basis": "rule"}


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
