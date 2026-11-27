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
    family,
)

PARAGRAPH_WORDS = (40, 140)
CITE = re.compile(r"\s*\[(F\d+)(?:\s*,\s*F\d+)*\]")
CITE_IDS = re.compile(r"F\d+")
FACT_FIELDS = ("id", "label", "value", "unit", "day", "phrases", "comparisons", "score",
               "reason", "state", "simulated", "forecast", "scheduled", "sentence",
               "implications", "related", "question")
CAUSAL = re.compile(r"\b(because|due to|driven by|as a result|caused|causing|led to|owing to|"
                    r"on the back of|thanks to)\b|由于|因为|导致|受.{0,6}影响", re.I)
#: Connectives that link two facts in time or sequence and so read as a cause ("X fell as
#: Y rose", "amid", "following", "after", "precedes"). Refused when the text cites facts of
#: two indicators the engine does not relate (directive rule LINKING). Not a link: "as of",
#: "as well as", "such as", "the same as", "as a/an ...", and "after"/"following" before a
#: date or the roll.
LINK = re.compile(
    r"\b(?:amid|amidst|in the wake of|on the heels of|preced(?:es|ed|ing)|ahead of)\b"
    r"|(?<!such )(?<!same )\bas\b(?!\s+(?:of|well|a|an|much|many|high|low|far|long|soon|"
    r"the same|measured|forecast)\b)"
    r"|\b(?:after|following)\b(?!\s+(?:\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|"
    r"Nov|Dec)|the (?:roll|month end)|(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)))"
    r"|随着|之际|继.{0,12}之后|在.{0,24}之后|伴随", re.I)
#: Verbs by which one fact acts on another ("while LNG pushed ..."); "sent out" is LNG
#: send-out, not a link.
LINK_VERB = re.compile(
    r"\b(?:push(?:ed|es|ing)?|dr(?:ove|ives|iving)|sen(?:t|ds|ding)(?!\s*-?\s*out)|"
    r"weigh(?:ed|s|ing)? on|"
    r"support(?:ed|s|ing)|pressur(?:ed|es|ing)|boost(?:ed|s|ing)|dragg(?:ed|ing)|drags|"
    r"prompt(?:ed|s|ing)|trigger(?:ed|s|ing)|spurr(?:ed|ing)|spurs|fuel(?:l?ed|s|l?ing)|"
    r"offset(?:s|ting)?|cushion(?:ed|s|ing))\b"
    r"|推动|带动|拉动|促使|推高|压低|拖累|支撑|抵消", re.I)
#: The editor runs at the provider's lowest temperature so the same fact sheet gives the
#: same plan as nearly as the provider allows; the record states it. A reasoning model spends
#: most of its budget thinking before it writes the plan; at 8,000 tokens the daily plan came
#: back empty (live run, 2026-11-16).
#: An answer is two to four sentences.
ANSWER_SENTENCES = 4
#: Words by which an answer says what the held data does not show.
NOT_SHOWN = re.compile(r"does not show|do not show|not held|cannot (?:tell|show|attribute)|"
                       r"no .{0,40}is held|无法|未显示|不显示|没有显示|并未显示", re.I)
#: Its time limit is the ``draft`` timing (``ai_controls.call_budget``; 240 s by default).
EDITOR_CALL = {"temperature": 0.0, "max_tokens": 24000}


# --------------------------------------------------------------------------- payload


def fact_sheet_payload(sheet: list[dict], sections: list[dict], plan, language: str,
                       cannot_tell: list[str] | None = None) -> dict:
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
                   "paragraph_words": list(PARAGRAPH_WORDS),
                   "answer_sentences": [2, ANSWER_SENTENCES]},
        # An asked report: what the engine found the held data cannot tell (sentences built
        # from the facts above; no identifier).
        "cannot_tell": list(cannot_tell or []),
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


#: Meta-commentary: a sentence about the report, the question, a section or what the text is
#: about to say, instead of about the market (directive rule NO META-COMMENTARY). "The data
#: held does not show" is the one sanctioned sentence about the evidence.
META = re.compile(
    r"\b(?:this|the|that|each|every) (?:report|section|paragraph|question|answer|analysis|"
    r"part|exhibit|chart|figure|table|series|note|summary|piece|issue)\b(?! (?:on|of) (?:\d|"
    r"[A-Z]))"
    r"|\b(?:bears?|bearing|bore) (?:directly |most |closely )?on\b|\bsets? out\b"
    r"|\bturns? on\b|\b(?:as )?(?:shown|set out|discussed|described|detailed) (?:below|above)\b"
    r"|\bthe following\b|\bwe (?:look|turn|show|see|note)\b|\bto answer\b|\bin answer\b"
    r"|\b(?:is|are) (?:relevant|central|key) to\b|\bspeaks? to\b|\baddress(?:es|ed)? the\b"
    r"|\b(?:measures|captures|tells us|shows us) what\b|\bwhat (?:the|an?) \w+ did to\b"
    r"|本报告|本节|本段|该问题|这个问题|此问题|问题所|下文|上文|如下所示|如下|就本|回答该|"
    r"与问题|本题", re.I)
#: Words by which one fact acts on another without a cause word ("what the outages did to
#: supply", "the effect of", "hit supply"): refused like a cause unless the engine relates
#: them as a cause.
EFFECT = re.compile(r"\b(?:effect|impact|toll) (?:of|on)\b|\bdid to\b|\b(?:hit|dented|"
                    r"curbed|cut into|weighed on|knocked)\b|\bresult(?:ed|ing)? in\b|"
                    r"造成|导致|使得|拖累|冲击", re.I)

#: Words that speak of the book; a report for distribution never carries them, even when the
#: question asks (the book's facts are never gathered for it, so this catches an allusion).
BOOK_WORDS = re.compile(r"\b(?:our|the desk's|net|open) (?:book|position)s?\b|\bP&L\b|\bPnL\b|"
                        r"\bcredit (?:line|limit|exposure)s?\b|counterpart|\bmandates?\b|"
                        r"头寸|损益|限额|交易对手|授权额度", re.I)


def check_text(text: str, fact_ids: list[str], facts: dict[str, dict], *,
               max_sentences: int = 3, max_chars: int = 420,
               max_words: int | None = None, context: str = "",
               audience: str = "internal", language: str | None = None) -> tuple[bool, str]:
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
    if audience == "shareable" and BOOK_WORDS.search(plain):
        return False, "book: a report for distribution mentions the book"
    meta = META.search(re.sub(r"\(Figure \d+(?:; (?:Figure|Table) \d+)*\.?\)|"
                              r"\(Table \d+\.?\)|\(图 ?\d+\)|\(表 ?\d+\)", "", plain))
    if meta and not NOT_SHOWN.search(plain[max(0, meta.start() - 40):meta.end() + 40]):
        return False, f"meta: speaks about the report, not the market ({meta.group(0)!r})"
    verdict = text_verdict(plain, evidence_text=evidence, language=language,
                           simulated=any(f.get("simulated") for f in used),
                           max_sentences=max_sentences, max_chars=max_chars,
                           max_words=max_words)
    if not verdict.ok:
        return False, f"{verdict.check}: {verdict.detail}"[:160]
    # A stated cause needs a cause the engine computed (``causes``); a relation in time
    # (``related``) permits a time word, never "because".
    # A sentence that says what the data does not show ("does not show how much the outage
    # caused") states no cause.
    claimed = " ".join(x for x in re.split(r"(?<=[.!?。])\s*", plain) if not NOT_SHOWN.search(x))
    if (CAUSAL.search(claimed) or EFFECT.search(claimed)) and not any(
            other in (f.get("causes") or []) for f in used for other in
            (g["key"] for g in used if g is not f)):
        return False, "cause: a cause is stated between facts the engine does not relate"
    if _unrelated(used) and (LINK.search(plain) or LINK_VERB.search(plain)):
        word = (LINK.search(plain) or LINK_VERB.search(plain)).group(0)
        return False, (f"link: {word!r} links facts of two indicators the engine does not "
                       "relate; state them separately or contrast them with 'while'")
    if any(f.get("forecast") for f in used) and not re.search(r"forecast|预测", plain, re.I):
        return False, "forecast: a forecast fact is cited but not called a forecast"
    claim = re.sub(r"measured days|not a measurement|not measured", "", plain, flags=re.I)
    if re.search(r"\b(measured|actual)\b", claim, re.I) and all(f.get("forecast") for f in used):
        return False, "forecast: a forecast described as measured"
    return True, ""


def _unrelated(used: list[dict]) -> bool:
    """True when the cited facts span two indicators and none lists another as related."""

    if len({family(f) for f in used}) < 2:
        return False
    keys = {f["key"] for f in used}
    return not any(set(f.get("related") or []) & (keys - {f["key"]}) for f in used)


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


def _mark_simulated(text: str, ids: list[str], facts: dict[str, dict]) -> str:
    """A text resting on simulated facts says so, even when the editor did not."""

    if any(facts.get(i, {}).get("simulated") for i in ids) and not re.search(
            r"simulated|模拟", text, re.I):
        from eurogas_nexus.application.reports.commentary import _sim

        end = text[-1] if text and text[-1] in ".。" else ""
        return text.rstrip(".。") + _sim(True) + end
    return text


def word_count(text: str) -> int:
    """Words in English; Chinese characters count two to a word (as the desk-note check)."""

    return len(re.findall(r"[A-Za-z0-9][\w./%-]*", text)) + len(
        re.findall(r"[\u4e00-\u9fff]", text)) // 2


def _report_context(sheet: list[dict], report_days: tuple = ()) -> str:
    """Dates any text may use: every fact's day and the issue's own dates (12 Nov)."""

    from eurogas_nexus.application.reports.commentary import day

    days = sorted({f["day"][:10] for f in sheet if f.get("day")}
                  | {str(d)[:10] for d in report_days if d})
    return " report days: " + ", ".join(day(d) for d in days)


def _record(record: dict, element: str, ok: bool, detail: str = "") -> bool:
    record["elements"][element] = {"ok": ok, "detail": detail[:160]}
    return ok


def apply_plan(raw: Any, sheet: list[dict], sections: list[dict], rule: dict,
               model_id: str, report_days: tuple = (), audience: str = "internal",
               language: str | None = None) -> dict:
    """The editorial plan to render: the model's elements that pass, rule elements otherwise.
    With ``language`` every element must be written in it."""

    def check(text, ids, facts_, **kw):
        return check_text(text, ids, facts_, audience=audience, language=language, **kw)

    facts = {f["id"]: f for f in sheet}
    context = _report_context(sheet, report_days)
    record = {"basis": "model", "model": model_id, "directive": directive.VERSION,
              "temperature": EDITOR_CALL["temperature"], "elements": {}, "plan": None}
    out = {**rule, "record": record}
    if not isinstance(raw, dict):
        record.update(basis="rule", invalid="plan is not a JSON object")
        return {**rule, "record": record}
    record["plan"] = raw
    # Headline and standfirst.
    for key, sentences, chars in (("headline", 1, 140), ("standfirst", 3, 520)):
        element = raw.get(key) or {}
        text = element.get("text") if isinstance(element, dict) else None
        ids = cited(text or "", element.get("facts") if isinstance(element, dict) else None)
        ok, why = check(text or "", ids, facts, max_sentences=sentences, max_chars=chars,
                              context=context)
        if _record(record, key, ok, why):
            value = strip_citations(text)
            out[key] = _mark_simulated(value.rstrip(".") if key == "headline" else value,
                                       ids, facts)
    # The answer of an asked report: checked like any element, and it must keep saying what
    # the data does not show when the rule answer does (never imply an attribution).
    if rule.get("answer"):
        element = raw.get("answer") or {}
        text = element.get("text") if isinstance(element, dict) else None
        ids = cited(text or "", element.get("facts") if isinstance(element, dict) else None)
        ok, why = check(text or "", ids, facts, max_sentences=ANSWER_SENTENCES,
                              max_chars=760, context=context)
        if ok and NOT_SHOWN.search(rule["answer"]["text"]) and not NOT_SHOWN.search(text):
            ok, why = False, "answer: drops what the data held does not show"
        if _record(record, "answer", ok, why):
            out["answer"] = {"text": _mark_simulated(strip_citations(text), ids, facts),
                             "fact_ids": ids, "basis": "model"}
    # Findings: 3 to 5, each checked; a refused finding is replaced in place by the rule's
    # finding on the same fact, and the list is topped up from the rule findings.
    findings = raw.get("findings") if isinstance(raw.get("findings"), list) else []
    # Three findings need three indicators; a narrow sheet (an asked report) may hold fewer.
    least = min(MIN_FINDINGS, len({f["key"] for f in sheet if f.get("sentence")}))
    if not max(least, 1) <= len(findings) <= MAX_FINDINGS:
        _record(record, "findings", False, f"{len(findings)} findings")
    else:
        chosen, families = [], set()
        for index, item in enumerate(findings):
            if not isinstance(item, dict):
                continue
            ids = cited(f"{item.get('finding', '')} {item.get('implication') or ''}",
                        item.get("facts"))
            ok, why = check(item.get("finding", ""), ids, facts, max_sentences=2,
                                  context=context)
            implication = item.get("implication")
            if ok and implication:
                ok_i, why_i = check(implication, ids, facts, max_sentences=1, context=context)
                if not ok_i:
                    implication = None
                    _record(record, f"finding.{index}.implication", False, why_i)
            # A finding is about its first cited fact (a "within range" finding may cite
            # several); two findings may not share that indicator.
            primary = [i for i in (item.get("facts") or ids) if i in facts][:1]
            # Two findings may not be about one indicator family (the outages total and its
            # largest outage are one).
            fam = {family(facts[i]) for i in primary}
            if ok and fam & families:
                ok, why = False, "second finding about the same indicator"
            if not _record(record, f"finding.{index}", ok, why):
                # The rule's finding on the same fact takes the refused one's place, so the
                # editor's order (and the headline's lead) survive a refused sentence.
                same = next((r for r in rule["findings"]
                             if set(r["fact_ids"]) & set(primary or ids)
                             and not set(r["fact_ids"]) & {i for c in chosen
                                                           for i in c["fact_ids"]}), None)
                same_fam = {family(facts[i]) for i in same["fact_ids"][:1] if i in facts} \
                    if same else set()
                if same and not same_fam & families:
                    families |= same_fam
                    chosen.append({**same, "basis": "rule"})
                continue
            families |= fam
            chosen.append({"fact_ids": ids,
                           "text": _mark_simulated(strip_citations(item["finding"]), ids, facts),
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
        words = word_count(strip_citations(paragraph))
        ok, why = check(paragraph, ids, facts, max_sentences=7, max_chars=1100,
                              context=context)
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
        ok, why = check(item.get("text", ""), ids, facts, max_sentences=2,
                              context=context)
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

    payload = fact_sheet_payload(sheet, sections, plan, language, rule.get("cannot_tell"))
    started = time.monotonic()
    try:
        content = model(editor_messages(payload))
    except Exception as exc:  # noqa: BLE001 - a provider failure leaves the rule plan
        return {**rule, "record": {"basis": "rule", "model": model_id,
                                   "directive": directive.VERSION,
                                   "temperature": EDITOR_CALL["temperature"], "elements": {},
                                   "invalid": f"provider: {exc.__class__.__name__}"}}
    latency = round(time.monotonic() - started, 1)
    raw = parse(content)
    edited = apply_plan(raw, sheet, sections, rule, model_id,
                        report_days=(plan.period_start, plan.period_end),
                        audience=plan.audience, language=language)
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
            # A Chinese full stop ends a sentence with no space after it.
            sentences = [x for x in re.split(r"(?<=[.!?])\s+|(?<=[。！？])",
                                             edit["paragraph"].strip()) if x]
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
