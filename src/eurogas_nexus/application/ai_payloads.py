"""What each AI use sends to the provider, and nothing more (AI-04 payload minimisation).

Every provider call in Eurogas Nexus builds its user message from one of the functions
here or from the use's own ``*_payload`` function (``explain.model_payload``,
``desk_brief.lead_payload``). The field lists are the allowlist that
``tests/security/test_ai_payload_allowlist.py`` holds the outgoing messages to, and that
``docs/operations/LLM_MONITORING-EN.md`` ("Provider payloads and the evaluation set")
documents. A field is on the list only if the text the model writes can use it.

Identifiers (alert, entity, opportunity, route, counterparty, snapshot ids, fingerprints,
provider references) are never sent: the model cites ``S1``-style aliases or nothing, and
the platform keeps the mapping. Earlier model output (``llm_summary_*``) is never fed back.
"""

from __future__ import annotations

import json
from typing import Any

#: The alert fields an answer about one alert may use (``/api/monitoring/alerts/{id}/analysis``).
ALERT_ANSWER_FIELDS = (
    "category",
    "alert_type",
    "severity",
    "status",
    "title",
    "message",
    "event_time_utc",
    "occurrence_count",
    "evidence",
    "simulated",
)

#: The alert fields the background enrichment sends (``monitoring_service``).
ALERT_ENRICHMENT_FIELDS = (
    "category",
    "type",
    "severity",
    "title_en",
    "message_en",
    "evidence",
    "simulated",
)

#: One market-report section's commentary for rewording (``reports/rewrite.section_payload``):
#: the section title, its rule lines, its sources as ``S1`` aliases and two flags.
REPORT_SECTION_FIELDS = ("section", "lines", "sources", "simulated_inputs", "forecast")

#: A question to a report plan (``reports/plan.plan_payload``): the question, the catalogue's
#: section keys with one-line descriptions, hub and country codes, the audience. No figure.
REPORT_PLAN_FIELDS = ("question", "sections", "hubs", "countries", "audience")


def is_identifier(key: str) -> bool:
    """Whether a field name is an identifier or a provider reference, never sent."""

    lowered = key.lower()
    return (
        lowered == "id"
        or lowered.endswith("_id")
        or lowered.endswith("_ids")
        or lowered.endswith("_eic")
        or "fingerprint" in lowered
        or "reference" in lowered
        or lowered in {"source_refs", "principal", "actor", "raw"}
    )


def without_identifiers(value: Any) -> Any:
    """``value`` with every identifier field removed, recursively."""

    if isinstance(value, dict):
        return {
            key: without_identifiers(item)
            for key, item in value.items()
            if not is_identifier(str(key))
        }
    if isinstance(value, list | tuple):
        return [without_identifiers(item) for item in value]
    return value


def alert_for_answer(snapshot: dict[str, Any], language: str) -> dict[str, Any]:
    """One alert as an answer may see it: title and message in the reply language."""

    zh = language.lower().startswith("zh")
    return {
        "category": snapshot.get("category"),
        "alert_type": snapshot.get("alert_type"),
        "severity": snapshot.get("severity"),
        "status": snapshot.get("status"),
        "title": snapshot.get("title_zh_cn" if zh else "title_en"),
        "message": snapshot.get("message_zh_cn" if zh else "message_en"),
        "event_time_utc": snapshot.get("event_time_utc"),
        "occurrence_count": snapshot.get("occurrence_count"),
        "evidence": without_identifiers(dict(snapshot.get("evidence_snapshot") or {})),
        "simulated": bool(snapshot.get("simulated")),
    }


def alert_for_enrichment(alert: Any) -> dict[str, Any]:
    """One persisted alert as the background enrichment sends it."""

    return {
        "category": alert.category,
        "type": alert.alert_type,
        "severity": alert.severity,
        "title_en": alert.title_en,
        "message_en": alert.message_en,
        "evidence": without_identifiers(dict(alert.evidence_snapshot or {})),
        "simulated": bool(alert.simulated),
    }


def alert_answer_messages(
    snapshot: dict[str, Any], question: str, language: str
) -> list[dict[str, str]]:
    """The messages for an answer about one alert (``ANSWER_RULES``)."""

    from eurogas_nexus.application.ai_style import ANSWER_RULES

    language_instruction = (
        "Respond in Simplified Chinese." if language == "zh-CN" else "Respond in English."
    )
    return [
        {
            "role": "system",
            "content": (
                f"{ANSWER_RULES} Answer the analyst's question about the supplied alert "
                f"and its evidence only. {language_instruction}"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {"question": question, "alert": alert_for_answer(snapshot, language)},
                ensure_ascii=False,
                default=str,
            ),
        },
    ]
