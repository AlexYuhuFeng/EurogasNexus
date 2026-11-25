"""NEWS-1: ``GET /api/news``, ``GET /api/news/{item_id}`` and ``POST /api/news/{item_id}/note``.

Items come from the constructed GOV.UK feed fixture and a held REMIT message; matches to the
book are computed only in the books the caller may see. The AI note is exercised with a stub
model in place of the governed provider call; no provider is called.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.application.news_ingest import poll_source, sync_remit_items
from eurogas_nexus.db.models import AuditEventRecord, NewsItemRecord
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.domain.news.sources import news_source
from tests.fixtures.news_seed import (
    FakeFetcher,
    book,
    cargoes,
    contract,
    govuk_feed,
    remit,
    store,
)

PUBLIC = "test-public-api-token"
LANGELED = "Update on Langeled flows to Easington"


@pytest.fixture()
def seeded(tmp_path, monkeypatch):
    url, engine = store(tmp_path)
    now = datetime.now(UTC)
    headers = {}
    with Session(engine) as session:
        session.add_all([book("uk-nbp", "EGN-UK", now), book("nl-ttf", "EGN-NL", now)])
        session.add(contract("uk-supply", "NBP", "uk-nbp", now))
        session.add(contract("nl-supply", "TTF", "nl-ttf", now))
        session.add_all(cargoes(now, [("C1", "Arctic Voyager", "Gate terminal", "nl-ttf")]))
        session.add_all(remit(now, "UMM-NYH", "Nyhamna"))
        session.commit()
        sync_remit_items(session, now=now)
        poll_source(session, news_source("govuk-desnz"), fetch=FakeFetcher(govuk_feed()),
                    now=now)
        for name, scopes in (("head", ["BOOKS:*", "*"]), ("uk", ["BOOKS:ENTITY:EGN-UK"])):
            principal = create_identity_principal(
                session, name=name, display_name=name, role="ANALYST", data_scopes=scopes
            )
            _key, bearer = create_identity_api_key(
                session, principal.principal_id, display_name="t", scopes=["*"]
            )
            headers[name] = {"X-Eurogas-Api-Key": PUBLIC, "X-Eurogas-Identity": bearer}
        ids = {row.title: row.item_id for row in session.query(NewsItemRecord)}
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    monkeypatch.setenv("EUROGAS_NEXUS_PORTFOLIO_ISOLATION", "true")
    return TestClient(create_app()), headers, ids, engine


def test_the_list_puts_my_books_items_first_and_filters(seeded):
    client, headers, ids, _engine = seeded
    response = client.get("/api/news", headers=headers["head"])
    assert response.status_code == 200, response.text
    body = response.json()
    rows = body["data"]
    assert len(rows) == 4
    assert rows[0]["title"] == LANGELED and rows[0]["relevance"]["score"] > 0
    assert rows[0]["relevance"]["roles"] == ["trader"]
    assert all(r["relevance"]["score"] == 0 for r in rows[2:])
    assert {s["source_id"] for s in body["meta"]["sources"]} >= {"remit-umm", "govuk-desnz",
                                                                 "eex-website"}
    assert body["meta"]["advisory"].startswith("Decision support")

    def titles(query):
        got = client.get(f"/api/news?{query}", headers=headers["head"])
        assert got.status_code == 200, got.text
        return [r["title"] for r in got.json()["data"]]

    assert titles("type=policy") == ["Consultation on gas storage regulation"]
    assert titles("type=sanction&country=RU") == ["New sanctions designations on LNG shipping"]
    assert LANGELED in titles("hub=nbp")
    assert titles("mine=true") == [LANGELED, "Consultation on gas storage regulation"]
    assert len(titles("source=remit-umm")) == 1
    timed = titles("order=time")
    assert len(timed) == 4 and timed[-1] == "Consultation on gas storage regulation"


@pytest.mark.parametrize(
    ("query", "code"),
    [("type=rumour", "type_unknown"), ("source=twitter", "source_unknown"),
     ("since=yesterday", "since_invalid"), ("order=random", "order_unknown")],
)
def test_a_filter_that_cannot_apply_is_a_422(seeded, query, code):
    client, headers, _ids, _engine = seeded
    response = client.get(f"/api/news?{query}", headers=headers["head"])
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == code


def test_matches_stay_inside_the_callers_books(seeded):
    client, headers, ids, _engine = seeded
    rows = client.get("/api/news?mine=true", headers=headers["uk"]).json()["data"]
    assert [r["title"] for r in rows] == [LANGELED, "Consultation on gas storage regulation"]
    detail = client.get(f"/api/news/{ids[LANGELED]}", headers=headers["uk"]).json()["data"]
    assert {m["book_id"] for m in detail["linked_exposures"]} == {"uk-nbp"}


def test_an_item_carries_its_source_terms_exposures_and_cited_rule_note(seeded):
    client, headers, ids, _engine = seeded
    response = client.get(f"/api/news/{ids[LANGELED]}", headers=headers["head"])
    assert response.status_code == 200, response.text
    item = response.json()["data"]
    assert item["url"].startswith("https://www.gov.uk/government/news/")
    assert item["source"]["licence"].startswith("Open Government Licence")
    assert item["source"]["terms_url"].startswith("https://")
    assert item["linked_event_key"] == "outage:UMM-NYH"
    assert [m["kind"] for m in item["linked_exposures"]] == ["contract"]
    assert [r["title"] for r in item["related"]][0].startswith("Nyhamna")
    note = item["note"]
    assert note["basis"] == "rule" and note["label"] is None
    cited = {c for s in note["sentences"] for c in s["cites"]}
    assert cited <= {c["id"] for c in note["citations"]}
    assert note["citations"][0]["item_id"] == ids[LANGELED]
    assert client.get("/api/news/nw-none", headers=headers["head"]).status_code == 404


def test_the_note_with_ai_off_is_the_rule_note(seeded):
    client, headers, ids, _engine = seeded
    response = client.post(f"/api/news/{ids[LANGELED]}/note", json={"language": "en"},
                           headers=headers["head"])
    assert response.status_code == 200, response.text
    note = response.json()["data"]
    assert note["basis"] == "rule" and note["ai"]["status"] == "off"
    assert client.post(f"/api/news/{ids[LANGELED]}/note", json={"language": "fr"},
                       headers=headers["head"]).status_code == 422


class _Stub:
    def __init__(self, reply):
        self.reply = reply

    def __call__(self, messages):
        return self.reply

    def audit_summary(self):
        return {"use": "news_note", "prompt_version": "news-note-2026.11.25",
                "model_id": "stub"}


@pytest.mark.parametrize("grounded", [True, False])
def test_the_ai_note_is_shown_labelled_only_when_grounded_and_is_audited(
    seeded, monkeypatch, grounded
):
    from eurogas_nexus.api.routes.public import explain

    client, headers, ids, engine = seeded
    text = ("Gassco AS states 25 mcm/d unavailable of 145 mcm/d technical." if grounded
            else "Gassco AS states 40 mcm/d unavailable.")
    reply = json.dumps({"sentences": [
        {"text": "The department reports an unplanned outage at Nyhamna.", "cites": ["N1"]},
        {"text": text, "cites": ["F1"]},
    ]})
    seen = {}

    def fake_model_for(principal, *, answer=False, use="explain"):
        seen["use"] = use
        return _Stub(reply)

    monkeypatch.setattr(explain, "_model_for", fake_model_for)
    response = client.post(f"/api/news/{ids[LANGELED]}/note", json={"language": "en"},
                           headers=headers["head"])
    assert response.status_code == 200, response.text
    body = response.json()
    note = body["data"]
    assert seen["use"] == "news_note"
    if grounded:
        assert note["basis"] == "model" and note["label"] == "AI-generated"
        assert note["ai"]["prompt_version"] == "news-note-2026.11.25"
        assert body["meta"]["warnings"] == []
    else:
        assert note["basis"] == "rule" and note["label"] is None
        assert note["ai"]["status"] == "refused" and note["ai"]["check"] == "number"
        assert "grounding check" in body["meta"]["warnings"][0]
    with Session(engine) as session:
        audit = (session.query(AuditEventRecord)
                 .filter(AuditEventRecord.action == "ai.news_note").one())
        assert audit.resource == f"news:{ids[LANGELED]}"
        assert audit.outcome.startswith("model" if grounded else "rule")


def test_without_a_runtime_store_the_list_is_empty_and_says_why(monkeypatch):
    monkeypatch.delenv("RUNTIME_STORE_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    client = TestClient(create_app(), headers={"X-Eurogas-Api-Key": PUBLIC})
    response = client.get("/api/news")
    assert response.status_code == 200
    assert response.json()["data"] == []
    assert client.get("/api/news/nw-x").status_code == 503
