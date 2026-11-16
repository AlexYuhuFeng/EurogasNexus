"""AI-04 payload minimisation: what each AI use sends to the provider, field by field.

The provider client is stubbed; each test captures the outgoing messages and holds the user
payload to the allowlist documented in ``docs/operations/LLM_MONITORING-EN.md``. A new field
in a provider payload is a reviewed change here, not a silent widening. Identifiers and
earlier model text never leave the platform.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from types import SimpleNamespace

from eurogas_nexus.api.routes.public.analysis import _filtered_llm_payload
from eurogas_nexus.api.routes.public.monitoring import AlertAnalysisRequest, _analysis_messages
from eurogas_nexus.application import desk_brief, explain
from eurogas_nexus.application.ai_payloads import (
    ALERT_ANSWER_FIELDS,
    ALERT_ENRICHMENT_FIELDS,
    is_identifier,
)
from eurogas_nexus.application.monitoring_service import _alert_enrichment_messages
from eurogas_nexus.domain.analysis import AnalysisSnapshot

SECRET_IDS = ("cp-secret-77", "snap-secret-9", "fp-secret", "opp-secret", "ref-secret")
ALIAS = re.compile(r"^S\d+$")


def _capture():
    seen: list[list[dict[str, str]]] = []

    def model(messages):
        seen.append(messages)
        return None

    return seen, model


def _user(messages) -> dict:
    assert [m["role"] for m in messages] == ["system", "user"]
    return json.loads(messages[1]["content"])


def _no_ids(messages) -> None:
    blob = json.dumps(messages, ensure_ascii=False)
    for value in SECRET_IDS:
        assert value not in blob, value


def test_why_sends_the_rule_lines_title_aliases_and_the_simulated_flag_only():
    seen, model = _capture()
    facts = explain.Facts(
        title="Rhinmark Handel GmbH credit: breach",
        lines=["Net exposure €4.88m against a €4.25m limit (115%)."],
        evidence={"counterparty_id": "cp-secret-77", "net_exposure": 4880000.0,
                  "source_reference": "ref-secret"},
        sources=["credit-line:cp-secret-77", "pnl:snap-secret-9"],
        simulated=True,
    )
    explain._model_note(model, facts, "en")
    payload = _user(seen[0])
    assert set(payload) == {"object", "facts", "sources", "simulated_inputs"}
    assert payload["sources"] == ["S1", "S2"]
    _no_ids(seen[0])


def test_the_brief_sends_section_lines_aliases_and_the_simulated_flag_only():
    seen, model = _capture()
    sections = [desk_brief.Section("limits", "Credit and mandates",
                                   ["Rhinmark Handel GmbH credit breach: €4.88m of €4.25m."],
                                   ["credit-line:cp-secret-77"])]
    desk_brief._lead(model, "morning", sections, True, "en")
    payload = _user(seen[0])
    assert set(payload) == {"brief", "sections", "sources", "simulated_inputs"}
    assert all(ALIAS.match(s) for s in payload["sources"])
    _no_ids(seen[0])


def _alert_snapshot() -> dict:
    return {
        "alert_id": "fp-secret-alert", "fingerprint": "fp-secret", "category": "supply",
        "alert_type": "flow_drop", "severity": "warning", "status": "open",
        "title_en": "Ellund flow fell", "title_zh_cn": "Ellund 流量下降",
        "message_en": "Ellund exit to ETF: 42 GWh/d.", "message_zh_cn": "Ellund 42 GWh/d。",
        "entity_type": "point", "entity_id": "opp-secret", "event_time_utc": "2026-11-14T06:00Z",
        "detected_at_utc": "x", "updated_at_utc": "x", "occurrence_count": 1,
        "evidence_snapshot": {"opportunity_id": "opp-secret", "flow_gwh_d": 42.0,
                              "source_reference": "ref-secret", "hub": "ETF"},
        "source_refs": ["ref-secret"], "warnings": ["internal"], "llm_provider_id": "DEEPSEEK",
        "llm_status": "success", "llm_summary_en": "earlier model text",
        "llm_summary_zh_cn": "earlier model text", "simulated": False,
        "human_review_required": True,
    }


def test_an_alert_answer_sends_the_allowlisted_alert_fields_only():
    messages = _analysis_messages(_alert_snapshot(), AlertAnalysisRequest(question="Why?"))
    payload = _user(messages)
    assert set(payload) == {"question", "alert"}
    assert tuple(payload["alert"]) == ALERT_ANSWER_FIELDS
    assert payload["alert"]["evidence"] == {"flow_gwh_d": 42.0, "hub": "ETF"}
    assert "earlier model text" not in messages[1]["content"]
    _no_ids(messages)


def test_the_alert_enrichment_sends_the_allowlisted_fields_only():
    snapshot = _alert_snapshot()
    alert = SimpleNamespace(
        category=snapshot["category"], alert_type=snapshot["alert_type"],
        severity=snapshot["severity"], title_en=snapshot["title_en"],
        message_en=snapshot["message_en"], evidence_snapshot=snapshot["evidence_snapshot"],
        source_refs=snapshot["source_refs"], warnings=snapshot["warnings"], simulated=False,
    )
    messages = _alert_enrichment_messages(alert)
    assert tuple(_user(messages)) == ALERT_ENRICHMENT_FIELDS
    _no_ids(messages)


def test_the_analysis_snapshot_carries_no_identifier_field():
    snapshot = AnalysisSnapshot(
        snapshot_id="snap-secret-9", source="runtime-postgresql",
        created_at_utc=datetime.now(UTC), ontology={},
        market_observations=[{"hub": "TTF", "price": 31.4, "unit": "EUR/MWh",
                              "source_system": "EEX", "source_reference": "ref-secret"}],
        portfolio_context=[{"contract_id": "cp-secret-77", "contract_name": "TTF supply"}],
    )
    payload = _filtered_llm_payload(snapshot, include_contract_prices=False)

    def keys(value):
        if isinstance(value, dict):
            for key, item in value.items():
                yield key
                yield from keys(item)
        elif isinstance(value, list):
            for item in value:
                yield from keys(item)

    assert not [key for key in keys(payload) if is_identifier(key)]
    assert payload["market_observations"][0]["source_system"] == "EEX"
    assert "snap-secret-9" not in json.dumps(payload)


def test_a_report_section_rewrite_sends_its_rule_lines_aliases_and_flags_only():
    from eurogas_nexus.application.ai_payloads import REPORT_SECTION_FIELDS
    from eurogas_nexus.application.reports.rewrite import rewrite_sections

    seen, model = _capture()
    section = {
        "key": "outages", "title": "Outages", "status": "ok", "simulated": True,
        "forecast": False,
        "rule_commentary": {"headline": "2 outages active, removing 572 GWh/d in total.",
                            "bullets": ["The largest is Demo Haldor field (NBP)."]},
        "commentary": {"headline": "x", "bullets": [], "basis": "rule"},
        "evidence": {"sources": [{"name": "REMIT urgent market messages",
                                  "source_system": "REMIT", "family": "REMIT",
                                  "source_reference": "ref-secret"}]},
        "books": ["cp-secret-77"],
        "tables": [{"rows": [{"facility": "opp-secret"}]}],
    }
    use = rewrite_sections([section], model)
    payload = _user(seen[0])
    assert tuple(payload) == REPORT_SECTION_FIELDS
    assert payload["sources"] == ["S1"]
    assert use["attempted"] == 1 and use["passed"] == 0
    assert section["commentary"]["basis"] == "rule"  # nothing returned: the rule text stands
    _no_ids(seen[0])


def test_a_report_plan_sends_the_question_and_the_catalogue_only():
    from eurogas_nexus.application.ai_payloads import REPORT_PLAN_FIELDS
    from eurogas_nexus.application.reports.plan import plan_for_question

    seen, model = _capture()
    plan_for_question("Norwegian supply this week", audience="shareable", model=model)
    payload = _user(seen[0])
    assert tuple(payload) == REPORT_PLAN_FIELDS
    keys = {item["key"] for item in payload["sections"]}
    assert "book_position" not in keys  # a shareable plan is not offered the book
    assert set(payload["sections"][0]) == {"key", "description"}
