""""Why?": rule lines from the object's own evidence; a model note only if it checks out."""

from __future__ import annotations

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.application import explain as explain_module
from eurogas_nexus.application.ai_style import checked_note
from eurogas_nexus.application.caller import firm_caller
from eurogas_nexus.application.explain import NotFound, explain
from eurogas_nexus.application.monitoring_service import scan_monitoring_conditions
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import MonitoringAlertRecord
from eurogas_nexus.security import portfolio_scope

SEED = Path(__file__).resolve().parents[2] / "scripts" / "demo" / "seed_demo_desk.py"
NOW = datetime(2026, 11, 7, 9, tzinfo=UTC)


@pytest.fixture
def desk(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'desk.sqlite'}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_DEMO_MARKS", "true")
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    spec = importlib.util.spec_from_file_location("seed_demo_desk", SEED)
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    with Session(engine) as session:
        seed.seed(session, NOW)
        session.commit()
    explain_module._CACHE.clear()
    return engine


def _breach(session) -> str:
    from eurogas_nexus.application.limits_service import credit_exposure_rows

    rows = credit_exposure_rows(firm_caller(), NOW.date()).rows
    return next(row["counterparty_id"] for row in rows if row["status"] == "breach")


def test_a_credit_breach_is_explained_in_figures_without_the_model(desk):
    with Session(desk) as session:
        result = explain(session, firm_caller(), "credit", _breach(session), now=NOW)
    assert result.basis == "rule"
    assert result.text.startswith("Net exposure ")
    assert "Needs " in result.text and "headroom" in result.text
    assert 2 <= len(result.lines) <= 4
    assert result.sources and result.simulated  # demo marks say so


def test_a_model_note_is_used_only_when_it_cites_and_invents_nothing(desk):
    with Session(desk) as session:
        counterparty = _breach(session)
        source = f"credit-line:{counterparty}"
        facts = explain(session, firm_caller(), "credit", counterparty, now=NOW)
        good = json.dumps({"text": facts.lines[0] + " Collateral is the fastest fix.",
                           "cites": [source]})
        explain_module._CACHE.clear()
        result = explain(session, firm_caller(), "credit", counterparty, now=NOW,
                         model=lambda _messages: good)
        assert result.basis == "model"

        for bad in (
            json.dumps({"text": "Exposure is 999 above plan.", "cites": [source]}),  # new number
            json.dumps({"text": "Exposure is high.", "cites": ["bloomberg"]}),  # foreign source
            json.dumps({"text": "Exposure is high.", "cites": []}),  # no citation
            "Exposure is high.",  # not JSON
        ):
            explain_module._CACHE.clear()
            result = explain(session, firm_caller(), "credit", counterparty, now=NOW,
                             model=lambda _messages, bad=bad: bad)
            assert result.basis == "rule", bad
            assert result.text.startswith("Net exposure ")


def test_the_prompt_asks_for_a_short_desk_note(desk):
    seen = []
    with Session(desk) as session:
        explain(session, firm_caller(), "credit", _breach(session), now=NOW,
                model=lambda messages: seen.append(messages) or None)
    system = seen[0][0]["content"]
    assert "at most three short sentences" in system
    assert "never add a number" in system
    assert "simulated demo prices" in system  # demo marks are named, not hidden


def test_an_outage_names_the_desk_position_at_its_hub(desk):
    with Session(desk) as session:
        result = explain(session, firm_caller(), "outage", "demo-umm-1", now=NOW)
    assert "Demo Haldor field" in result.lines[0] and "unavailable" in result.lines[0]
    assert any("at NBP today" in line for line in result.lines)
    assert result.sources == ["remit:demo-umm-1:v1"]
    assert result.simulated


def test_a_limits_alert_is_hidden_from_a_regional_caller(desk, monkeypatch):
    with Session(desk) as session:
        scan_monitoring_conditions(session, now_utc=NOW, enrich_with_llm=False)
        alert = session.query(MonitoringAlertRecord).filter_by(category="limits").first()
        assert explain(session, firm_caller(), "alert", alert.alert_id, now=NOW).lines
        monkeypatch.setenv(portfolio_scope.ISOLATION_ENV, "true")
        portfolio_scope.set_request_scope(("BOOKS:BOOK:elsewhere",))
        try:
            with pytest.raises(NotFound):
                explain(session, firm_caller(), "alert", alert.alert_id, now=NOW)
        finally:
            portfolio_scope._current.set(None)


def test_the_route_explains_without_a_provider(desk):
    from eurogas_nexus.api.app import create_app

    with Session(desk) as session:
        counterparty = _breach(session)
    client = TestClient(create_app())
    response = client.post(
        "/api/analysis/explain", json={"subject": "credit", "id": counterparty}
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["basis"] == "rule" and data["sources"] == [f"credit-line:{counterparty}"]
    missing = client.post("/api/analysis/explain", json={"subject": "credit", "id": "nope"})
    assert missing.status_code == 404


def test_note_checks():
    sources = ["s1"]
    evidence = '{"net": 2300000, "line": "Net exposure at 115% of limit."}'
    assert checked_note('{"text": "At 115% of limit.", "cites": ["s1"]}',
                        evidence_text=evidence, sources=sources)
    long = "One. Two. Three. Four."
    assert not checked_note(json.dumps({"text": long, "cites": ["s1"]}),
                            evidence_text=evidence, sources=sources)
