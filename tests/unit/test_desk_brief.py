"""The desk brief: fixed sections from the desk's own data; a model lead only if checked."""

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
from eurogas_nexus.application.caller import firm_caller
from eurogas_nexus.application.desk_brief import build_brief
from eurogas_nexus.application.monitoring_service import scan_monitoring_conditions
from eurogas_nexus.db.base import Base

SEED = Path(__file__).resolve().parents[2] / "scripts" / "demo" / "seed_demo_desk.py"
NOW = datetime(2026, 11, 7, 7, tzinfo=UTC)


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
        scan_monitoring_conditions(session, now_utc=NOW, enrich_with_llm=False)
    return engine


def test_the_morning_brief_has_the_desk_sections_with_sources(desk):
    with Session(desk) as session:
        brief = build_brief(session, firm_caller(), "morning", now=NOW)
    keys = [section.key for section in brief.sections]
    assert {"outages", "prices", "positions", "limits"} <= set(keys)
    for section in brief.sections:
        assert section.sources and 0 < len(section.lines) <= 6
    assert brief.simulated and brief.text.startswith("Gas desk morning brief")
    assert "simulated prices" in brief.text  # a demo brief cannot be mistaken for a real one
    assert brief.lead is None and brief.lead_basis == "none"
    assert "Rhinmark" in brief.text and "credit breach" in brief.text


def test_a_model_lead_is_kept_only_when_it_checks_out(desk):
    with Session(desk) as session:
        first = build_brief(session, firm_caller(), "eod", now=NOW)
        source = first.sections[0].sources[0]
        good = json.dumps({"text": "Demo prices: the main outage is still out.",
                           "cites": [source]})
        brief = build_brief(session, firm_caller(), "eod", now=NOW, model=lambda _m: good)
        assert brief.lead and brief.lead_basis == "model"
        assert brief.text.splitlines()[4] == brief.lead
        invented = json.dumps({"text": "NBP rose 7.5 today.", "cites": [source]})
        brief = build_brief(session, firm_caller(), "eod", now=NOW, model=lambda _m: invented)
        assert brief.lead is None


def test_the_route_drafts_without_a_provider(desk):
    from eurogas_nexus.api.app import create_app

    response = TestClient(create_app()).post("/api/analysis/brief", json={"kind": "eod"})
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["title"].startswith("Gas desk end of day") and data["sections"]
