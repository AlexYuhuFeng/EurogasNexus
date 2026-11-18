"""Ask from the answer bar: Today facts with sources; a model answer only when it checks out."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.application.caller import firm_caller
from eurogas_nexus.application.desk_ask import ask, topics_for
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
    return engine


@pytest.mark.parametrize(
    ("question", "book", "expected"),
    [
        ("what's going on with Norwegian supply this week", False, ["outages", "supply"]),
        ("why did storage withdrawal jump", False, ["supply"]),
        ("any outages at NBP?", False, ["outages", "prices"]),
        ("how is our credit with Rhinmark", True, ["book"]),
        ("how is our credit with Rhinmark", False, ["prices", "outages", "supply", "alerts"]),
        ("挪威供应怎么样", False, ["outages", "supply"]),
        ("summarise the day", False, ["prices", "outages", "supply", "alerts"]),
    ],
)
def test_topics_follow_the_question_and_the_book_needs_permission(question, book, expected):
    assert topics_for(question, book_allowed=book) == expected


def test_an_outage_question_gets_outage_lines_with_sources_and_as_of(desk):
    with Session(desk) as session:
        answer = ask(session, firm_caller(), "what outages are there", now=NOW)
    assert answer.topics == ["outages"]
    assert answer.lines and all(line.topic == "outages" for line in answer.lines)
    assert all(line.source and line.as_of for line in answer.lines)
    assert answer.answer is None and answer.basis == "facts" and answer.ai == "off"


def test_book_lines_only_for_a_caller_allowed_the_book(desk):
    with Session(desk) as session:
        hidden = ask(session, firm_caller(), "what is our position", now=NOW)
        shown = ask(session, firm_caller(), "what is our position", now=NOW, book_allowed=True)
    assert not any(line.topic == "book" for line in hidden.lines)
    assert any(line.topic == "book" for line in shown.lines)


def test_a_model_answer_is_shown_only_when_it_passes_the_checks(desk):
    with Session(desk) as session:
        facts = ask(session, firm_caller(), "what outages are there", now=NOW)
        first = facts.lines[1].text.split(":")[0]  # a facility name the facts give
        good = ask(session, firm_caller(), "what outages are there", now=NOW,
                   model=lambda _m: f"{first} is out. Simulated demo data.")
        invented = ask(session, firm_caller(), "what outages are there", now=NOW,
                       model=lambda _m: "Twelve fields are out and TTF rose 7.5 EUR/MWh.")
        advice = ask(session, firm_caller(), "what outages are there", now=NOW,
                     model=lambda _m: f"{first} is out, so buy TTF now.")
    assert good.basis == "model" and good.ai == "used" and good.answer
    assert invented.answer is None and invented.ai == "refused"
    assert advice.answer is None and advice.ai == "refused"
    assert invented.lines  # the facts still stand


def test_the_route_answers_without_a_provider(desk):
    from eurogas_nexus.api.app import create_app

    client = TestClient(create_app())
    response = client.post("/api/analysis/ask", json={"question": "what outages are there"})
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["ai"] == "off" and data["lines"] and data["topics"] == ["outages"]
    assert client.post("/api/analysis/ask", json={"question": "x"}).status_code == 422


def test_ask_fact_dates_follow_the_answer_language():
    from eurogas_nexus.application.desk_ask import _day
    from eurogas_nexus.application.reports.lang import writing

    assert _day("2026-11-16") == "16 Nov"
    with writing("zh-CN"):
        assert _day("2026-11-16") == "11月16日"
        assert _day("2026-11-09T06:00:00Z") == "11月9日"
