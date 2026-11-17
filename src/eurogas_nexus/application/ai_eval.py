"""The AI evaluation set (AI-04): recorded evidence, candidate texts and what the checks say.

``tests/evals/ai_note_cases.json`` holds evidence recorded in the shape each AI use builds
(a "Why?" ``Facts``, the brief's sections, an alert for an answer or for the background
enrichment) from demo and public-shaped data, and candidate model texts with the verdict
they must get: ``pass`` with the reason it is faithful, or ``refuse`` with the check that
must refuse it.

The evidence goes through the same payload builders and message builders the product uses
(``explain.model_payload``, ``desk_brief.lead_payload``, ``ai_payloads``), so what is
checked here, and what the on-demand provider run (``scripts/ai/run_note_eval.py``) sends,
is exactly what production would send for that evidence. Nothing here calls a model.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from eurogas_nexus.application.ai_style import (
    Verdict,
    answer_verdict,
    note_messages,
    note_verdict,
)

CASES_PATH = Path(__file__).resolve().parents[3] / "tests" / "evals" / "ai_note_cases.json"
USES = ("explain", "brief", "answer", "enrichment", "report")


@dataclass(frozen=True)
class Evidence:
    """One recorded evidence payload, ready for a model and for the checks."""

    key: str
    use: str
    messages: list[dict[str, str]]
    evidence_text: str
    sources: list[str]
    simulated: bool
    #: True only for demo or public data; the provider run refuses anything else.
    demo_or_public: bool
    #: The alert an enrichment case is about (the product's refusal function reads it).
    subject: Any = None
    #: The interface language the reply must be in (``None``: not checked, the older cases).
    language: str | None = None


@dataclass(frozen=True)
class Case:
    case_id: str
    evidence: str
    category: str
    expect: str  # "pass" or "refuse"
    check: str  # the check that must refuse it; "" for a pass
    reason: str
    output: str  # the model output exactly as a provider would return it


def load(path: Path = CASES_PATH) -> tuple[dict[str, Evidence], list[Case]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    evidence = {key: build_evidence(key, entry) for key, entry in raw["evidence"].items()}
    cases = []
    for item in raw["cases"]:
        ev = evidence[item["evidence"]]
        output = item.get("output")
        if output is None:
            if ev.use in {"explain", "brief", "report"}:
                cites = item.get("cites", ev.sources[:1])
                output = json.dumps({"text": item["text"], "cites": cites}, ensure_ascii=False)
            elif ev.use == "enrichment":
                output = json.dumps(
                    {"summary_en": item["text"], "summary_zh_cn": item.get("text_zh", "")
                     or item["text"]},
                    ensure_ascii=False,
                )
            else:
                output = item["text"]
        cases.append(
            Case(
                case_id=item["id"],
                evidence=item["evidence"],
                category=item["category"],
                expect=item["expect"],
                check=item.get("check", ""),
                reason=item["reason"],
                output=output,
            )
        )
    return evidence, cases


def build_evidence(key: str, entry: dict[str, Any]) -> Evidence:
    use = entry["use"]
    language = entry.get("language", "en")
    #: Cases that name their language are held to it (the reply must be written in it).
    checked = entry.get("language") if entry.get("check_language") else None
    demo_or_public = entry.get("data_class") in {"demo", "public"}
    if use == "explain":
        from eurogas_nexus.application.explain import Facts, model_payload, model_task

        facts = Facts(
            title=entry["title"],
            lines=list(entry["lines"]),
            evidence=dict(entry.get("evidence") or {}),
            sources=list(entry["sources"]),
            simulated=bool(entry.get("simulated")),
        )
        payload = model_payload(facts)
        return Evidence(
            key, use, note_messages(model_task(facts), payload, language=language),
            json.dumps(payload, ensure_ascii=False, default=str), payload["sources"],
            facts.simulated, demo_or_public, language=checked,
        )
    if use == "brief":
        from eurogas_nexus.application.desk_brief import Section, lead_payload, lead_task

        sections = [
            Section(s["key"], s["heading"], list(s["lines"]), list(s.get("sources") or []))
            for s in entry["sections"]
        ]
        simulated = bool(entry.get("simulated"))
        payload = lead_payload(entry.get("kind", "morning"), sections, simulated)
        return Evidence(
            key, use,
            note_messages(lead_task(entry.get("kind", "morning"), simulated), payload,
                          language=language),
            json.dumps(payload, ensure_ascii=False), payload["sources"], simulated,
            demo_or_public, language=checked,
        )
    if use == "report":
        from eurogas_nexus.application.reports.rewrite import section_messages, section_payload

        section = {
            "key": entry.get("section_key", "storage"),
            "title": entry["title"],
            "simulated": bool(entry.get("simulated")),
            "forecast": bool(entry.get("forecast")),
            "rule_commentary": {"headline": entry["lines"][0], "bullets": entry["lines"][1:]},
            "evidence": {"sources": [{"name": name} for name in entry["sources"]]},
        }
        payload = section_payload(section)
        return Evidence(
            key, use, section_messages(section, language),
            json.dumps(payload, ensure_ascii=False), payload["sources"],
            bool(entry.get("simulated")), demo_or_public,
        )
    if use == "answer":
        from eurogas_nexus.application.ai_payloads import alert_answer_messages

        if entry.get("ask_lines"):
            # The answer bar's Ask: the question over the Today fact lines.
            from eurogas_nexus.application.ai_payloads import ask_messages
            from eurogas_nexus.application.desk_ask import FactLine

            lines = [FactLine(x["topic"], x["text"], x["source"], x.get("as_of"),
                              bool(x.get("simulated"))) for x in entry["ask_lines"]]
            messages = ask_messages(entry["question"], lines,
                                    simulated=bool(entry.get("simulated")), language=language)
            return Evidence(key, use, messages, messages[1]["content"], [],
                            bool(entry.get("simulated")), demo_or_public, language=checked)
        messages = alert_answer_messages(entry["alert"], entry["question"], language)
        return Evidence(
            key, use, messages, messages[1]["content"], [],
            bool(entry["alert"].get("simulated")), demo_or_public, language=checked,
        )
    if use == "enrichment":
        from types import SimpleNamespace

        from eurogas_nexus.application.monitoring_service import _alert_enrichment_messages

        alert = SimpleNamespace(**entry["alert"])
        messages = _alert_enrichment_messages(alert)
        return Evidence(
            key, use, messages, messages[1]["content"], [], bool(alert.simulated),
            demo_or_public, alert,
        )
    raise ValueError(f"unknown AI use {use!r}")


def verdict(evidence: Evidence, output: str | None) -> Verdict:
    """What the product's checks say about ``output`` for ``evidence``."""

    if evidence.use in {"explain", "brief", "report"}:
        return note_verdict(
            output, evidence_text=evidence.evidence_text, sources=evidence.sources,
            simulated=evidence.simulated, language=evidence.language,
        )
    if evidence.use == "answer":
        return answer_verdict(
            output, evidence_text=evidence.evidence_text, simulated=evidence.simulated,
            language=evidence.language,
        )
    # Enrichment: both summaries must pass; the product's own refusal function decides.
    from eurogas_nexus.application.monitoring_service import _enrichment_refusal

    if not output:
        return Verdict(False, "empty")
    refusal = _enrichment_refusal(evidence.subject, output)
    return Verdict(refusal is None, refusal or "")


__all__ = ["CASES_PATH", "USES", "Case", "Evidence", "load", "verdict"]
