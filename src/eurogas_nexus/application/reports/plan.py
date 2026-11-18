"""An asked report: a question becomes a report *plan* the user sees and edits, never SQL.

The plan is a selection of catalogue sections with parameters (hubs, countries, period).
When the deployment enables a model and the caller may use it, the model proposes the plan
as structured JSON; the proposal is used only if it validates against the catalogue
(``validate_plan``) and every hub it names is named in the question itself, so a question
about ETF can never become a TTF report. Otherwise, and when no model is configured, a
deterministic keyword and ontology mapping proposes the plan. A question the held data
cannot answer returns ``answerable: false`` with what is missing.

The model is sent the question, the section keys with their one-line descriptions, the hub
codes, the country codes and the audience (``ai_payloads.REPORT_PLAN_FIELDS``); no
identifier, figure or book.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from typing import Any

from eurogas_nexus.application.reports.catalogue import (
    SECTIONS,
    PlanError,
    known_hubs,
    resolve_hub,
    validate_plan,
)

#: Country words a question may use, to NW Europe codes.
COUNTRY_WORDS = {
    "netherlands": "NL", "dutch": "NL", "holland": "NL", "germany": "DE", "german": "DE",
    "belgium": "BE", "belgian": "BE", "france": "FR", "french": "FR", "britain": "GB",
    "british": "GB", "uk": "GB", "gb": "GB", "denmark": "DK", "danish": "DK",
    "luxembourg": "LU", "荷兰": "NL", "德国": "DE", "比利时": "BE", "法国": "FR", "英国": "GB",
    "丹麦": "DK",
}
#: Topics people ask about that the platform does not hold, with what is missing.
NOT_HELD = (
    (("oil", "brent", "crude", "原油"), "oil prices (no oil source is connected)"),
    (("coal price", "api2", "煤价"), "coal prices (licensed exchange data, not connected here)"),
    (("carbon", "eua", "uka", "碳价"), "carbon prices (licensed exchange data, not connected "
                                       "here)"),
    (("weather", "temperature", "hdd", "天气", "气温"),
     "a weather section (weather enters only the balance forecast)"),
    (("china", "asia", "japan", "korea", "jkm", "中国", "亚洲"),
     "Asian demand and prices (the platform covers NW Europe)"),
    (("vessel", "ship", "cargo", "tanker", "船"), "LNG cargo tracking (no vessel source is "
                                                  "connected)"),
    (("electricity price", "power price", "电价"), "power prices in a report section"),
    (("border", "interconnector", "跨境", "边境"),
     "flows at a border point (reports hold Norwegian landings by terminal; the Network view "
     "shows cross-border flows)"),
)
PERIOD_WORDS = (
    (("today", "this morning", "今天", "今日"), 1),
    (("this week", "week", "weekly", "本周", "这周", "一周"), 7),
    (("this month", "month", "monthly", "本月", "一个月"), 31),
    (("winter", "season", "冬季"), 31),
)


def _sections_for(text: str) -> list[str]:
    lower = text.lower()
    found = []
    for section in SECTIONS:
        if section.key == "situation_event":
            continue
        for word in section.keywords:
            hit = (re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", lower)
                   if word.isascii() else word in lower)
            if hit:
                found.append(section.key)
                break
    # Winter balance questions need storage and the balance together.
    if "winter" in lower or "冬" in lower:
        for key in ("storage", "balance"):
            if key not in found:
                found.append(key)
    if "norw" in lower or "挪威" in lower:
        for key in ("pipeline_supply",):
            if key not in found:
                found.append(key)
    return found


def hubs_in_question(text: str) -> list[str]:
    """Hubs the question names, by exact ontology code or alias (ETF stays ETF)."""

    out: list[str] = []
    for word in re.findall(r"[A-Za-z][A-Za-z0-9-]*", text):
        if word.lower() in {"the"} and not word.isupper():
            continue  # "the" is a word, THE is the German hub
        hub = resolve_hub(word)
        if hub and hub not in out:
            out.append(hub)
    return out


def _countries(text: str) -> list[str]:
    lower = text.lower()
    out = []
    for word, code in COUNTRY_WORDS.items():
        hit = (re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", lower) if word.isascii()
               else word in lower)
        if hit and code not in out:
            out.append(code)
    return out


def _period_days(text: str) -> int | None:
    lower = text.lower()
    for words, days in PERIOD_WORDS:
        if any(w in lower for w in words):
            return days
    return None


def _not_held(text: str) -> list[str]:
    lower = text.lower()
    return [what for words, what in NOT_HELD if any(w in lower for w in words)]


def rule_plan(question: str, audience: str) -> dict[str, Any]:
    """The deterministic proposal: keywords and the ontology."""

    from eurogas_nexus.application.reports import joins

    sections = _sections_for(question)
    hubs = hubs_in_question(question)
    countries = _countries(question)
    if not sections and joins.SINCE.search(question):
        # "What changed since <date>" with no topic: the market indicators that have a series.
        sections = ["prices", "pipeline_supply", "lng", "storage"]
    if len(hubs) >= 2 and joins.SPREAD_WORDS.search(question) and "prices" not in sections:
        sections.insert(0, "prices")
    return {
        "sections": sections,
        "hubs": hubs,
        "countries": countries,
        "period_days": _period_days(question),
        "missing": _not_held(question),
    }


PLAN_RULES = (
    "You map a gas trader's question to a report plan. Choose only from the section keys, "
    "hub codes and country codes given. Name a hub only if the question names it; never "
    "substitute one hub for another. If the held sections cannot answer the question, set "
    "answerable to false and list in missing what would be needed. Never write SQL, never "
    "add a figure. Return JSON only: {\"sections\": [keys], \"hubs\": [codes], "
    "\"countries\": [codes], \"period_days\": integer or null, \"answerable\": true or "
    "false, \"missing\": [short phrases]}."
)


def plan_payload(question: str, audience: str) -> dict[str, Any]:
    """Exactly what the plan call sends (``ai_payloads.REPORT_PLAN_FIELDS``)."""

    from eurogas_nexus.domain.fundamentals.balance import NWE_COUNTRIES

    return {
        "question": question,
        "sections": [{"key": s.key, "description": f"{s.title}: {s.description}"}
                     for s in SECTIONS if s.key != "situation_event"
                     and (audience == "internal" or not s.internal_only)],
        "hubs": sorted(known_hubs()),
        "countries": list(NWE_COUNTRIES),
        "audience": audience,
    }


def plan_messages(question: str, audience: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": PLAN_RULES},
        {"role": "user", "content": json.dumps(plan_payload(question, audience),
                                               ensure_ascii=False)},
    ]


def _parse_model(content: str | None, question: str) -> tuple[dict | None, str]:
    """The model's proposal if well-formed and grounded in the question, else the reason."""

    if not content:
        return None, "empty"
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        data = json.loads(text)
    except ValueError:
        return None, "format"
    if not isinstance(data, dict):
        return None, "format"
    named = set(hubs_in_question(question))
    hubs = [str(h) for h in data.get("hubs") or []]
    if any(resolve_hub(h) not in named for h in hubs):
        return None, "hub_not_in_question"
    sections = [str(s) for s in data.get("sections") or []]
    period = data.get("period_days")
    if period is not None and not (isinstance(period, int) and 1 <= period <= 400):
        return None, "period"
    return {
        "sections": sections,
        "hubs": hubs,
        "countries": [str(c) for c in data.get("countries") or []],
        "period_days": period,
        "answerable": bool(data.get("answerable", True)),
        "missing": [str(m)[:120] for m in data.get("missing") or []][:5],
    }, ""


def plan_for_question(
    question: str, *, audience: str = "internal", model=None, now: datetime | None = None
) -> dict[str, Any]:
    """A validated, editable plan for ``question`` (see the module text)."""

    from datetime import timedelta

    now = now or datetime.now(UTC)
    basis, refusal = "rules", ""
    proposal: dict[str, Any] | None = None
    if model is not None:
        try:
            proposal, refusal = _parse_model(model(plan_messages(question, audience)), question)
        except Exception as exc:  # noqa: BLE001 - provider failure: the rules propose
            proposal, refusal = None, f"provider ({exc.__class__.__name__})"
        if proposal is not None:
            basis = "model"
    rules = rule_plan(question, audience)
    if proposal is None:
        proposal = {**rules, "answerable": bool(rules["sections"])}
    missing = list(dict.fromkeys([*proposal.get("missing", []), *rules["missing"]]))
    sections = [s for s in proposal["sections"]]
    raw: dict[str, Any] = {
        "kind": "ask", "audience": audience, "sections": sections,
        "hubs": proposal["hubs"], "countries": proposal["countries"],
        "question": question, "drop_internal": True,
    }
    from eurogas_nexus.application.reports.joins import since_date

    since = since_date(question, now.date())
    if since is not None:
        # "What changed since <date>": the period runs from that date to today.
        raw["period_start"], raw["period_end"] = since.isoformat(), now.date().isoformat()
    elif proposal.get("period_days"):
        raw["period_start"] = (now.date() - timedelta(days=proposal["period_days"] - 1)).isoformat()
        raw["period_end"] = now.date().isoformat()
    notes: list[str] = []
    try:
        plan = validate_plan(raw, now=now) if sections else None
    except PlanError as exc:
        if basis == "model":
            # An invalid model plan never stands: the rules propose instead.
            refusal, basis = f"invalid ({exc.code})", "rules"
            raw.update(sections=rules["sections"], hubs=rules["hubs"],
                       countries=rules["countries"])
            try:
                plan = validate_plan(raw, now=now) if rules["sections"] else None
            except PlanError as again:
                plan, notes = None, [str(again)]
        else:
            plan, notes = None, [str(exc)]
    answerable = plan is not None and bool(plan.sections) and proposal.get("answerable", True)
    if plan is None or not plan.sections:
        answerable = False
    if not answerable and not missing:
        missing = ["No report section covers this question. Sections cover hub prices, "
                   "Norwegian pipeline landings, LNG send-out, storage, gas-fired power, "
                   "outages, the NW Europe balance and, for internal reports, the book."]
    return {
        "question": question,
        "answerable": answerable,
        "message": None if answerable else "Cannot answer from held data.",
        "missing": missing,
        "basis": basis,
        "model_refusal": refusal or None,
        "plan": plan.as_dict() if plan is not None else None,
        "notes": (plan.notes if plan is not None else []) + notes,
    }
