"""The model's only part in a market report: rewording a section's rule commentary for flow.

Each section's rule text (headline and up to three facts, every figure with its unit) is
sent as the section's lines, with its sources as ``S1``-style aliases and the simulated and
forecast flags (``ai_payloads.REPORT_SECTION_FIELDS``); nothing else leaves the platform: no
table, no identifier, no book id. The model returns ``{"text", "cites"}``, and the text is
used only if it passes the desk-note checks (``ai_style.note_verdict``): no number, hub,
unit, direction, superlative, source or name the lines do not hold, no advice, no simulated
price read as a market price. A refused rewrite leaves the rule text; the verdict is
recorded per section in the report's ``model_use``.
"""

from __future__ import annotations

import json
from typing import Any

#: Sections whose wording the model may touch. Book sections stay rule text: their figures
#: are the firm's own and their wording is the risk function's.
REWRITABLE = frozenset({"prices", "pipeline_supply", "lng", "storage", "power_burn", "outages",
                        "balance", "situation_event", "alerts"})


def section_payload(section: dict[str, Any]) -> dict[str, Any]:
    """Exactly what one section sends to the model (the allowlist's fields)."""

    from eurogas_nexus.application.ai_style import source_aliases

    rule = section["rule_commentary"]
    names = sorted({str(item.get("name")) for item in section["evidence"]["sources"]})
    return {
        "section": section["title"],
        "lines": [rule["headline"], *rule["bullets"]],
        "sources": list(source_aliases(names)),
        "simulated_inputs": bool(section.get("simulated")),
        "forecast": bool(section.get("forecast")),
    }


def section_task(section: dict[str, Any]) -> str:
    return (
        "Rewrite the lines of one section of a market report as sober report prose for a "
        "gas trader: the most important fact first, then the others. Keep every figure, date "
        "and unit exactly as given; do not add, round or combine figures."
        + (" Say that the figures are simulated demo data." if section.get("simulated") else "")
        + (" Say that the forward figures are a forecast." if section.get("forecast") else "")
    )


def section_messages(section: dict[str, Any], language: str) -> list[dict[str, str]]:
    from eurogas_nexus.application.ai_style import note_messages

    return note_messages(section_task(section), section_payload(section), language=language)


def section_verdict(section: dict[str, Any], output: str | None):
    from eurogas_nexus.application.ai_style import note_verdict

    payload = section_payload(section)
    return note_verdict(
        output,
        evidence_text=json.dumps(payload, ensure_ascii=False),
        sources=payload["sources"],
        simulated=payload["simulated_inputs"],
    )


def rewrite_sections(results: list[dict[str, Any]], model, *, language: str = "en") -> dict:
    """Reword each eligible section in place; return the model-use record."""

    use: dict[str, Any] = {"attempted": 0, "passed": 0, "sections": {}, "language": language}
    for section in results:
        if section["status"] != "ok" or section["key"] not in REWRITABLE:
            continue
        use["attempted"] += 1
        try:
            output = model(section_messages(section, language))
        except Exception as exc:  # noqa: BLE001 - a provider failure leaves the rule text
            use["sections"][section["key"]] = {"ok": False, "check": "provider",
                                               "detail": exc.__class__.__name__}
            continue
        verdict = section_verdict(section, output)
        use["sections"][section["key"]] = {"ok": verdict.ok, "check": verdict.check,
                                           "detail": verdict.detail[:200]}
        if verdict.ok and verdict.note is not None:
            use["passed"] += 1
            section["commentary"] = {"headline": verdict.note.text, "bullets": [],
                                     "basis": "model"}
    return use
