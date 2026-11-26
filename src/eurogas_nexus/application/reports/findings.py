"""Page one, by rule: the fact sheet's ids, the ranked key findings, the standfirst and the
"At a glance" rows. This is the candidate generator the editor (``editor.py``) chooses from,
and the plan that stands when no model is configured or the editor's plan fails the checks.

Ranking is by each fact's materiality score (``facts.py``: change against the indicator's own
recent variation, distance from a year earlier, capacity offline against supply, size of a
forecast change), with three rules on top:

- one finding per indicator family (never two about the same indicator);
- a late, stale or simulated fact is weighed down in ``facts.py``, so it does not lead over a
  current measured one of similar weight;
- if nothing scores 1 or more, the first finding says so plainly instead of inflating a small
  move.

Each chosen finding records which facts it rests on and why it was chosen.
"""

from __future__ import annotations

from typing import Any

from eurogas_nexus.application.reports.commentary import _sim, number
from eurogas_nexus.application.reports.commentary import day as fday
from eurogas_nexus.application.reports.lang import T

MIN_FINDINGS = 3
MAX_FINDINGS = 5
MATERIAL = 1.0
#: "At a glance" rows, in print order (a fixed menu the editor picks from).
GLANCE_MENU = ("price.", "spread.", "landings", "lng", "storage.fill", "storage.withdrawal",
               "power.gen", "power.burn", "balance.call", "outages.offline")
NO_NEWS = ("Flows, storage and prices moved within their recent range: no indicator changed by "
           "more than its usual daily variation.")
NO_NEWS_ZH = "流量、储气与价格均在近期波动范围内：没有指标的变动超过其通常的日波动。"
#: The quiet line when prices are the only market indicators in the report.
PRICES_QUIET = ("Prices moved within their recent range: no hub changed by more than its usual "
                "daily variation.")
PRICES_QUIET_ZH = "价格均在近期波动范围内：没有枢纽的变动超过其通常的日波动。"
#: Indicator families the quiet line speaks for (a book or portfolio fact is not one).
MARKET_FAMILIES = {"prices", "landings", "lng", "storage", "power", "balance", "outages"}


def no_news() -> str:
    return T(NO_NEWS, NO_NEWS_ZH)


def _quiet_line(candidates: list[dict[str, Any]]) -> str | None:
    """What a quiet report says first: only about the market indicators it holds."""

    held = {family(f) for f in candidates} & MARKET_FAMILIES
    if not held:
        return None
    if held == {"prices"}:
        return T(PRICES_QUIET, PRICES_QUIET_ZH)
    return no_news()


def assign_ids(sections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Number every fact ``F1``.. in section order; return the flat fact sheet."""

    sheet = []
    for section in sections:
        if section["status"] != "ok":
            continue
        for fact in section.get("facts") or []:
            fact["id"] = f"F{len(sheet) + 1}"
            sheet.append(fact)
    return sheet


def family(fact: dict[str, Any]) -> str:
    key = fact["key"]
    if key.startswith("price.") or key.startswith("spread."):
        return "prices"
    if key.startswith("outage"):
        return "outages"
    if key.startswith("storage") or key == "balance.forecast_fill":
        return "storage"
    if key.startswith("balance"):
        return "balance"
    return key.split(".")[0]


def rank_findings(sheet: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """3 to 5 findings by materiality, one per family, each with its reason."""

    candidates = sorted((f for f in sheet if f.get("sentence") and f["score"] > 0),
                        key=lambda f: -f["score"])
    chosen: list[dict[str, Any]] = []
    families: set[str] = set()
    for fact in candidates:
        fam = family(fact)
        if fam in families:
            continue
        families.add(fam)
        implication = fact["implications"][0] if fact["implications"] else None
        chosen.append({
            "fact_ids": [fact["id"]],
            "text": fact["sentence"],
            "implication": implication,
            "why": f"score {fact['score']}: {fact['reason']}",
            "score": fact["score"],
        })
        if len(chosen) == MAX_FINDINGS:
            break
    quiet = _quiet_line(candidates) if chosen and chosen[0]["score"] < MATERIAL else None
    if quiet:
        chosen.insert(0, {"fact_ids": [f["id"] for f in candidates[:3]], "text": quiet,
                          "implication": None, "quiet": True,
                          "why": f"no fact scored {MATERIAL} or more (largest "
                                 f"{chosen[0]['score']})", "score": 0.0})
        chosen = chosen[:MAX_FINDINGS]
    return chosen


def standfirst(sheet: list[dict[str, Any]]) -> str:
    """Two or three sentences on the state of the system, from the balance, storage and the
    forecast where held, else from the leading facts."""

    by_key = {f["key"]: f for f in sheet}
    parts = []
    call = by_key.get("balance.call")
    if call:
        sim = _sim(call["simulated"])
        parts.append(T(f"NW Europe drew {number(call['value'], 'GWh/d')}{sim} from Norway, LNG "
                       f"and storage on {fday(call['day'])}.",
                       f"{fday(call['day'])}西北欧从挪威、LNG 与储气共取用"
                       f"{number(call['value'], 'GWh/d')}{sim}。"))
    fill = by_key.get("storage.fill")
    if fill:
        year = fill["comparisons"]["year"]
        parts.append(T(
            f"Storage stood at {number(fill['value'], '%')} full"
            + (f", {number(abs(year), '', 1)} points {'above' if year > 0 else 'below'} a year "
               "earlier" if year is not None else "") + ".",
            f"储气率为{number(fill['value'], '%')}"
            + (f"，较一年前{'高' if year > 0 else '低'}{number(abs(year), '', 1)}个百分点"
               if year is not None else "") + "。"))
    forecast = by_key.get("balance.forecast")
    if forecast:
        parts.append(T(f"The balance forecast, a model estimate, puts the call at "
                       f"{number(forecast['value'], 'GWh/d')} by {fday(forecast['day'])}.",
                       f"平衡预测（模型估算）显示{fday(forecast['day'])}供应需求为"
                       f"{number(forecast['value'], 'GWh/d')}。"))
    if not parts:
        ranked = sorted((f for f in sheet if f.get("sentence")), key=lambda f: -f["score"])
        parts = [f["sentence"] for f in ranked[:2]]
    return " ".join(parts[:3])


def glance_rows(sheet: list[dict[str, Any]], keys: list[str] | None = None) -> list[dict]:
    """The indicator rows, in the menu's order; ``keys`` narrows them (the editor's choice)."""

    rows = []
    for prefix in GLANCE_MENU:
        for fact in sheet:
            if not fact.get("indicator") or fact["value"] is None:
                continue
            if not (fact["key"] == prefix or (prefix.endswith(".") and
                                              fact["key"].startswith(prefix))):
                continue
            if keys is not None and fact["key"] not in keys:
                continue
            rows.append({"key": fact["key"], "fact_id": fact.get("id"), "label": fact["label"],
                         "unit": fact["unit"], "latest": fact["value"],
                         "change_unit": fact["comparisons"]["unit"],
                         "day": fact["comparisons"]["day"], "week": fact["comparisons"]["week"],
                         "year": fact["comparisons"]["year"], "norm": fact["comparisons"]["norm"],
                         "as_of": fact["day"], "state": fact["state"],
                         "simulated": fact["simulated"], "spark": fact["spark"]})
    return rows


def what_to_watch(sheet: list[dict[str, Any]]) -> list[dict]:
    return [{"fact_ids": [f["id"]], "text": f["sentence"]} for f in sheet if f["scheduled"]][:4]


def headline_of(findings: list[dict], sheet: list[dict]) -> str:
    if not findings:
        return T("No market data is held for the sections chosen.", "所选章节均无市场数据。")
    lead = findings[0]
    if lead["text"] in {NO_NEWS, NO_NEWS_ZH}:
        return T("Flows, storage and prices within their recent range",
                 "流量、储气与价格均在近期波动范围内")
    if lead["text"] in {PRICES_QUIET, PRICES_QUIET_ZH}:
        return T("Prices within their recent range", "价格均在近期波动范围内")
    fact = next((f for f in sheet if f["id"] == lead["fact_ids"][0]), None)
    text = (fact or {}).get("headline") or lead["text"]
    if fact and fact.get("simulated") and "(simulated)" not in text and "模拟" not in text:
        text += _sim(True)
    return text


def rule_plan(sheet: list[dict], sections: list[dict]) -> dict[str, Any]:
    """The editorial plan the rules make (same shape as the editor's, see ``editor.py``)."""

    findings = rank_findings(sheet)
    return {
        "basis": "rule",
        "headline": headline_of(findings, sheet),
        "standfirst": standfirst(sheet),
        "findings": findings,
        "glance": [row["key"] for row in glance_rows(sheet)],
        "watch": what_to_watch(sheet),
        "sections": [{"key": s["key"]} for s in sections if s["status"] == "ok"],
        "dropped": [],
    }
