"""The AI editor: decides what a report presents, under the directive and the checks.

Owner decision 2026-11-16: findings selection, their order, emphasis, the choice of exhibits
and windows, section order and the narrative are the editor's decisions when a model is
configured. The rule plan (``findings.rule_plan``) is the candidate generator the editor
chooses from and the fallback.

What the model may and may not do:

- it sees only the **fact sheet** (:func:`fact_sheet_payload`, fields in
  ``ai_payloads.REPORT_EDITOR_FIELDS``): fact ids, labels, values, units, days, comparisons,
  scores and reasons, states, rule sentences and the implications the engine can derive, and
  each section's permitted exhibits, types and windows. No identifier, no row, no book fact
  for an audience that may not see the book (they are never gathered);
- it returns an **editorial plan** (``directive.PLAN_SCHEMA``) as JSON;
- every text element is checked before anything is rendered (:func:`check_text`): every
  number, unit, hub, date and direction must come from the facts it cites, every cited id
  must exist, no advice, no superlative, no simulated price as a market price, a forecast
  called a forecast and never measured; findings count 3 to 5; paragraph 60 to 120 words;
  exhibits, types and windows only from the permitted set;
- a refused element falls back to the rule-written element (not the whole report); if the
  plan as a whole is invalid (not JSON, wrong shape), the rule plan stands. The record says
  which elements are the model's and which are rule-written, with each verdict.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from eurogas_nexus.application.reports import directive
from eurogas_nexus.application.reports.findings import (
    GLANCE_MENU,
    MAX_FINDINGS,
    MIN_FINDINGS,
)

PARAGRAPH_WORDS = (40, 140)
CITE = re.compile(r"\s*\[(F\d+)(?:\s*,\s*F\d+)*\]")
CITE_IDS = re.compile(r"F\d+")
FACT_FIELDS = ("id", "label", "value", "unit", "day", "phrases", "comparisons", "score",
               "reason", "state", "simulated", "forecast", "scheduled", "sentence",
               "implications", "related")
CAUSAL = re.compile(r"\b(because|due to|driven by|as a result|caused|causing|led to|owing to|"
                    r"on the back of|thanks to)\b|由于|因为|导致|受.{0,6}影响", re.I)
#: A reasoning model spends most of its budget thinking before it writes the plan; at 8,000
#: tokens the daily plan came back empty (live run, 2026-11-16).
EDITOR_CALL = {"temperature": 0.2, "max_tokens": 24000, "timeout_seconds": 240.0}


# --------------------------------------------------------------------------- payload


def fact_sheet_payload(sheet: list[dict], sections: list[dict], plan, language: str) -> dict:
    """Exactly what the editor is sent (``ai_payloads.REPORT_EDITOR_FIELDS``)."""

    by_section: dict[str, list[str]] = {}
    for fact in sheet:
        by_section.setdefault(fact["section"], []).append(fact["id"])
    return {
        "report": {"kind": plan.kind, "variant": plan.variant, "audience": plan.audience,
                   "period_start": plan.period_start.isoformat() if plan.period_start else None,
                   "period_end": plan.period_end.isoformat() if plan.period_end else None,
                   "question": plan.question, "language": language},
        # The fact's own id travels as "fact" (an F-number; no platform identifier).
        "facts": [{("fact" if k == "id" else k): f.get(k) for k in FACT_FIELDS} for f in sheet],
        "sections": [
            {"key": s["key"], "title": s["title"], "facts": by_section.get(s["key"], []),
             "exhibits": [{"exhibit": c.get("id"), "types": c.get("types") or [c.get("type")],
                           "windows": c.get("windows") or [], "default": c.get("window")}
                          for c in s.get("charts") or []]}
            for s in sections if s["status"] == "ok"],
        "glance_menu": [f["id"] for f in sheet if f.get("indicator") and f.get("value") is not None
                        and any(f["key"] == p or (p.endswith(".") and f["key"].startswith(p))
                                for p in GLANCE_MENU)],
        "limits": {"findings": [MIN_FINDINGS, MAX_FINDINGS],
                   "paragraph_words": list(PARAGRAPH_WORDS)},
    }


def editor_messages(payload: dict) -> list[dict[str, str]]:
    return [{"role": "system", "content": directive.system_prompt()},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False, default=str)}]


# --------------------------------------------------------------------------- checks


def strip_citations(text: str) -> str:
    return " ".join(CITE.sub("", text or "").split())


def cited(text: str, listed: list[str] | None = None) -> list[str]:
    ids = set(CITE_IDS.findall(" ".join(m.group(0) for m in CITE.finditer(text or ""))))
    return sorted(ids | set(listed or []), key=lambda x: int(x[1:]))


def check_text(text: str, fact_ids: list[str], facts: dict[str, dict], *,
               max_sentences: int = 3, max_chars: int = 420,
               max_words: int | None = None, context: str = "") -> tuple[bool, str]:
    """The checks on one model text element (see the module text)."""

    from eurogas_nexus.application.ai_style import text_verdict

    if not text or not text.strip():
        return False, "empty"
    unknown = [i for i in fact_ids if i not in facts]
    if unknown:
        return False, f"unknown fact {', '.join(unknown)}"
    if not fact_ids:
        return False, "cites no fact"
    used = [facts[i] for i in fact_ids]
    evidence = json.dumps([{k: f.get(k) for k in ("label", "value", "unit", "day", "phrases",
                                                  "comparisons", "sentence", "implications",
                                                  "forecast", "state")} for f in used],
                          ensure_ascii=False, default=str) + context
    plain = strip_citations(text)
    verdict = text_verdict(plain, evidence_text=evidence,
                           simulated=any(f.get("simulated") for f in used),
                           max_sentences=max_sentences, max_chars=max_chars,
                           max_words=max_words)
    if not verdict.ok:
        return False, f"{verdict.check}: {verdict.detail}"[:160]
    if CAUSAL.search(plain) and not any(
            other in (f.get("related") or []) for f in used for other in
            (g["key"] for g in used if g is not f)):
        return False, "cause: a cause is stated between facts the engine does not relate"
    if any(f.get("forecast") for f in used) and not re.search(r"forecast|预测", plain, re.I):
        return False, "forecast: a forecast fact is cited but not called a forecast"
    if re.search(r"\b(measured|actual)\b", plain, re.I) and all(f.get("forecast") for f in used):
        return False, "forecast: a forecast described as measured"
    return True, ""


# --------------------------------------------------------------------------- apply


#: How a window may be named in an exhibit title.
WINDOW_WORDS = {"30d": "30 days", "91d": "91 days 13 weeks three months",
                "365d": "365 days 12 months a year", "395d": "395 days 13 months",
                "gas_year": "gas year since 1 Oct"}


def _check_title(title: str, section: str, window: str | None, sheet: list[dict],
                 facts: dict[str, dict]) -> tuple[bool, str]:
    """An exhibit title stands on the section's measured facts; a figure that only a
    forecast holds must be called a forecast."""

    context = " " + WINDOW_WORDS.get(window or "", "")
    measured = [f["id"] for f in sheet if f["section"] == section and not f.get("forecast")]
    ok, why = check_text(title, measured, facts, max_sentences=1, max_chars=160,
                         context=context) if measured else (False, "no measured fact")
    if ok:
        return ok, why
    every = [f["id"] for f in sheet if f["section"] == section]
    return check_text(title, every, facts, max_sentences=1, max_chars=160, context=context)


def _record(record: dict, element: str, ok: bool, detail: str = "") -> bool:
    record["elements"][element] = {"ok": ok, "detail": detail[:160]}
    return ok


def apply_plan(raw: Any, sheet: list[dict], sections: list[dict], rule: dict,
               model_id: str) -> dict:
    """The editorial plan to render: the model's elements that pass, rule elements otherwise."""

    facts = {f["id"]: f for f in sheet}
    record = {"basis": "model", "model": model_id, "directive": directive.VERSION,
              "elements": {}, "plan": None}
    out = {**rule, "record": record}
    if not isinstance(raw, dict):
        record.update(basis="rule", invalid="plan is not a JSON object")
        return {**rule, "record": record}
    record["plan"] = raw
    # Headline and standfirst.
    for key, sentences, chars in (("headline", 1, 200), ("standfirst", 3, 520)):
        element = raw.get(key) or {}
        text = element.get("text") if isinstance(element, dict) else None
        ids = cited(text or "", element.get("facts") if isinstance(element, dict) else None)
        ok, why = check_text(text or "", ids, facts, max_sentences=sentences, max_chars=chars)
        if _record(record, key, ok, why):
            out[key] = strip_citations(text).rstrip(".") if key == "headline" else \
                strip_citations(text)
    # Findings: 3 to 5, each checked; a refused finding is replaced by the next rule finding.
    findings = raw.get("findings") if isinstance(raw.get("findings"), list) else []
    if not MIN_FINDINGS <= len(findings) <= MAX_FINDINGS:
        _record(record, "findings", False, f"{len(findings)} findings")
    else:
        chosen, families = [], set()
        for index, item in enumerate(findings):
            if not isinstance(item, dict):
                continue
            ids = cited(f"{item.get('finding', '')} {item.get('implication') or ''}",
                        item.get("facts"))
            ok, why = check_text(item.get("finding", ""), ids, facts, max_sentences=2)
            implication = item.get("implication")
            if ok and implication:
                ok_i, why_i = check_text(implication, ids, facts, max_sentences=1)
                if not ok_i:
                    implication = None
                    _record(record, f"finding.{index}.implication", False, why_i)
            fam = {facts[i]["key"] for i in ids if i in facts}
            if ok and fam & families:
                ok, why = False, "second finding about the same indicator"
            if _record(record, f"finding.{index}", ok, why):
                families |= fam
                chosen.append({"fact_ids": ids, "text": strip_citations(item["finding"]),
                               "implication": strip_citations(implication) if implication
                               else None, "why": str(item.get("why") or "")[:160],
                               "score": max((facts[i]["score"] for i in ids if i in facts),
                                            default=0.0), "basis": "model"})
        for fallback in rule["findings"]:
            if len(chosen) >= MIN_FINDINGS:
                break
            if not set(fallback["fact_ids"]) & {i for c in chosen for i in c["fact_ids"]}:
                chosen.append({**fallback, "basis": "rule"})
        out["findings"] = chosen[:MAX_FINDINGS]
    # Sections: order, drops, paragraphs and exhibit choices.
    by_key = {s["key"]: s for s in sections if s["status"] == "ok"}
    order, dropped, edits = [], [], {}
    for item in raw.get("sections") or []:
        if not isinstance(item, dict) or item.get("key") not in by_key:
            continue
        key = item["key"]
        if item.get("keep") is False:
            dropped.append({"key": key, "title": by_key[key]["title"],
                            "reason": str(item.get("reason") or "not material in this issue")[:160],
                            "action": None})
            _record(record, f"section.{key}", True, "dropped")
            continue
        order.append({"key": key})
        paragraph = str(item.get("paragraph") or "")
        ids = cited(paragraph, item.get("facts"))
        words = len(strip_citations(paragraph).split())
        ok, why = check_text(paragraph, ids, facts, max_sentences=7, max_chars=1100)
        if ok and not PARAGRAPH_WORDS[0] <= words <= PARAGRAPH_WORDS[1]:
            ok, why = False, f"length: {words} words"
        if _record(record, f"section.{key}.paragraph", ok, why):
            edits.setdefault(key, {})["paragraph"] = strip_citations(paragraph)
        permitted = {c.get("id"): c for c in by_key[key].get("charts") or []}
        picks = []
        for ex in item.get("exhibits") or []:
            if isinstance(ex, dict) and "exhibit" in ex:
                ex = {**ex, "id": ex["exhibit"]}
            if not isinstance(ex, dict) or ex.get("id") not in permitted:
                continue
            spec = permitted[ex["id"]]
            ok = (ex.get("type") in (spec.get("types") or [spec.get("type")])
                  and ex.get("window") in (spec.get("windows") or [spec.get("window")]))
            why = "" if ok else "type or window not permitted"
            title_ok, title_why = _check_title(ex.get("title", ""), key, ex.get("window"),
                                               sheet, facts)
            if _record(record, f"exhibit.{ex['id']}", ok, why):
                picks.append({"id": ex["id"], "type": ex["type"], "window": ex["window"],
                              "title": strip_citations(ex["title"]) if title_ok else None})
            if not title_ok:
                _record(record, f"exhibit.{ex['id']}.title", False, title_why)
        if picks:
            edits.setdefault(key, {})["exhibits"] = picks
    if order:
        missing = [k for k in by_key if k not in {o["key"] for o in order}
                   and k not in {d["key"] for d in dropped}]
        out["sections"] = order + [{"key": k} for k in missing]
        out["dropped"] = dropped
    out["section_edits"] = edits
    glance = [g for g in raw.get("glance") or [] if g in facts]
    if glance:
        out["glance"] = [facts[g]["key"] for g in glance if facts[g].get("indicator")]
        _record(record, "glance", True)
    watch = []
    for index, item in enumerate(raw.get("watch") or []):
        if not isinstance(item, dict):
            continue
        ids = cited(item.get("text", ""), item.get("facts"))
        scheduled = all(facts.get(i, {}).get("scheduled") for i in ids) and ids
        ok, why = check_text(item.get("text", ""), ids, facts, max_sentences=2)
        if ok and not scheduled:
            ok, why = False, "watch item cites a fact that is not scheduled"
        if _record(record, f"watch.{index}", ok, why):
            watch.append({"fact_ids": ids, "text": strip_citations(item["text"])})
    if watch:
        out["watch"] = watch
    return out


def edit_report(model, sheet: list[dict], sections: list[dict], rule: dict, plan, *,
                language: str = "en", model_id: str = "deepseek-v4-flash") -> dict:
    """Ask the editor for a plan, check it, apply it to the sections (in place)."""

    payload = fact_sheet_payload(sheet, sections, plan, language)
    started = time.monotonic()
    try:
        content = model(editor_messages(payload))
    except Exception as exc:  # noqa: BLE001 - a provider failure leaves the rule plan
        return {**rule, "record": {"basis": "rule", "model": model_id,
                                   "directive": directive.VERSION, "elements": {},
                                   "invalid": f"provider: {exc.__class__.__name__}"}}
    latency = round(time.monotonic() - started, 1)
    raw = parse(content)
    edited = apply_plan(raw, sheet, sections, rule, model_id)
    edited["record"]["latency_s"] = latency
    if raw is None:
        edited["record"].update(basis="rule", invalid="not JSON" if content else "empty reply",
                                reply_chars=len(content or ""))
    apply_section_edits(sections, edited.get("section_edits") or {})
    return edited


def parse(content: str | None) -> dict | None:
    if not content:
        return None
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        value = json.loads(text)
    except ValueError:
        # A model may wrap the object in a sentence or a code fence: take the outermost
        # object, nothing else.
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            value = json.loads(text[start:end + 1])
        except ValueError:
            return None
    return value if isinstance(value, dict) else None


def apply_section_edits(sections: list[dict], edits: dict[str, dict]) -> None:
    """The editor's paragraph and exhibit choices into the section dicts (in place)."""

    for section in sections:
        edit = edits.get(section["key"])
        if not edit:
            continue
        if edit.get("paragraph"):
            sentences = re.split(r"(?<=[.!?。])\s+", edit["paragraph"].strip())
            section["commentary"] = {"headline": sentences[0], "bullets": sentences[1:],
                                     "basis": "model"}
        if edit.get("exhibits"):
            charts = {c.get("id"): c for c in section.get("charts") or []}
            kept = []
            for pick in edit["exhibits"]:
                chart = charts.get(pick["id"])
                if chart is None:
                    continue
                chart = {**chart, "type": pick["type"], "window": pick["window"]}
                if pick.get("title"):
                    chart["title"] = pick["title"]
                kept.append(chart)
            if kept:
                section["charts"] = kept


__all__ = ["apply_plan", "check_text", "edit_report", "editor_messages", "fact_sheet_payload"]
