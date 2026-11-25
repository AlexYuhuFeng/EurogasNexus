"""NEWS-1: what an item touches in the book, who is told (dedupe and cooldown), and the
"what this means for my book" note (rule note always; a model note only when every sentence is
cited and grounded). No provider is called: the model is a stub returning fixed text.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from eurogas_nexus.application import market_events
from eurogas_nexus.application.alert_routing import (
    NEWS_ROLE_CATEGORIES,
    SELF_NOTIFYING,
    route_for,
)
from eurogas_nexus.application.alert_scope import BOOK_SCOPED_CATEGORIES
from eurogas_nexus.application.news_ingest import outage_link, poll_source, upsert_item
from eurogas_nexus.application.news_note import (
    AI_LABEL,
    assemble,
    build_evidence,
    model_note,
    note_messages,
    rule_note,
)
from eurogas_nexus.application.news_reads import item_dict
from eurogas_nexus.application.news_relevance import (
    Exposure,
    firm_exposures,
    matches,
    relevance_score,
)
from eurogas_nexus.application.news_routing import (
    CONSUMER_NAME,
    COOLDOWN,
    expire_aged,
    fingerprint,
    react,
)
from eurogas_nexus.db.models import (
    GasDayNominationEventRecord,
    MonitoringAlertRecord,
    NewsItemRecord,
    NotificationOutboxRecord,
)
from eurogas_nexus.domain.news.sources import news_source
from eurogas_nexus.domain.news.tagging import tag_text
from tests.fixtures.news_seed import (
    FakeFetcher,
    book,
    cargoes,
    contract,
    govuk_feed,
    remit,
    store,
)

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)


def _nomination(hub: str, book_id: str) -> GasDayNominationEventRecord:
    return GasDayNominationEventRecord(
        event_id=f"nom-{hub}-{book_id}", gas_day=date(2026, 11, 19), line_ref="L1", hub=hub,
        book_id=book_id, step="nominated", status="confirmed", quantity_mwh=1000.0,
        agent=None, origin="manual", recorded_by="t", recorded_at_utc=NOW,
        note=None, source_system="ETRM",
    )


@pytest.fixture()
def seeded(tmp_path):
    _url, engine = store(tmp_path)
    with Session(engine) as session:
        session.add_all([book("uk-nbp", "EGN-UK", NOW), book("nl-ttf", "EGN-NL", NOW)])
        session.add(contract("uk-supply", "NBP", "uk-nbp", NOW))
        session.add(contract("nl-supply", "TTF", "nl-ttf", NOW))
        session.add_all(cargoes(NOW, [("C1", "Arctic Voyager", "Gate terminal", "nl-ttf")]))
        session.add(_nomination("NBP", "uk-nbp"))
        session.add_all(remit(NOW, "UMM-NYH", "Nyhamna"))
        session.commit()
        poll_source(session, news_source("govuk-desnz"), fetch=FakeFetcher(govuk_feed()),
                    now=NOW)
        session.commit()
        yield session


def _item(session, title: str) -> NewsItemRecord:
    return session.query(NewsItemRecord).filter(NewsItemRecord.title == title).one()


def _add(session, source_id: str, ref: str, title: str, summary: str = "",
         published: datetime = NOW) -> NewsItemRecord:
    tags = tag_text(f"{title} {summary}", vessels=["Arctic Voyager"])
    link, _ = outage_link(session, tags, at=NOW)
    item_id, _state = upsert_item(
        session, source=news_source(source_id), source_ref=ref, url=None,
        publisher="European Commission", title=title, summary=summary, language="en",
        published=published, retrieved=NOW, tags=tags, linked_event_key=link, now=NOW,
    )
    session.flush()
    return session.get(NewsItemRecord, item_id)


LANGELED = "Update on Langeled flows to Easington"


# ---------------------------------------------------------------------------------- relevance


def test_an_item_matches_contracts_nominations_and_cargoes_with_reasons(seeded):
    exposures = firm_exposures(seeded, now=NOW)
    assert sorted(e.kind for e in exposures) == ["cargo", "contract", "contract", "nomination"]
    langeled = item_dict(_item(seeded, LANGELED))
    found = matches(langeled, exposures)
    assert [(m["kind"], m["book_id"], m["role"]) for m in found] == [
        ("contract", "uk-nbp", "trader"), ("nomination", "uk-nbp", "scheduler")]
    assert found[0]["reason"] == "names NBP (through Langeled)"
    assert "delivers 12,000 MWh/d at NBP" in found[0]["figure"]
    cargo_item = item_dict(_add(seeded, "ec-energy-news", "fog", "Arctic Voyager held by fog"))
    vessel = matches(cargo_item, exposures)
    assert [(m["kind"], m["basis"], m["role"]) for m in vessel] == [("cargo", "vessel", "lng")]
    assert relevance_score(vessel) == 3


def test_matches_stay_inside_the_books_a_caller_may_see():
    exposures = [Exposure("contract", "a", "uk-nbp", "contract a", hubs=("NBP",)),
                 Exposure("contract", "b", None, "contract b", hubs=("NBP",))]
    item = {"entities": [], "hubs": ["NBP"]}
    assert [m["ref"] for m in matches(item, exposures)] == ["a", "b"]
    assert [m["ref"] for m in matches(item, exposures, {"uk-nbp"})] == ["a"]
    assert matches(item, exposures, set()) == []


# ---------------------------------------------------------------------------------- routing


def test_news_categories_are_routed_book_scoped_and_notify_themselves():
    for role, category in NEWS_ROLE_CATEGORIES.items():
        assert category in SELF_NOTIFYING and category in BOOK_SCOPED_CATEGORIES, role
    assert route_for(NEWS_ROLE_CATEGORIES["lng"]).notification_category == "cargo"
    assert route_for(NEWS_ROLE_CATEGORIES["scheduler"]).owner == "OPERATIONS"


def test_a_recent_outage_item_tells_each_role_once_then_holds_back(seeded):
    item = _item(seeded, LANGELED)
    first = react(seeded, item.item_id, now=NOW)
    assert first["roles"] == {"scheduler": "notified", "trader": "notified"}
    queued = seeded.query(NotificationOutboxRecord).all()
    assert sorted(r.category for r in queued) == ["alert", "nomination"]
    assert all(r.severity == "warning" and LANGELED in r.title for r in queued)
    alert = (seeded.query(MonitoringAlertRecord)
             .filter(MonitoringAlertRecord.fingerprint == fingerprint(item.item_id, "trader"))
             .one())
    assert alert.category == "news_trader" and alert.evidence_snapshot["book_ids"] == ["uk-nbp"]
    assert alert.evidence_snapshot["linked_event_key"] == "outage:UMM-NYH"
    assert alert.human_review_required is True
    # The same content again: nothing new is sent.
    assert react(seeded, item.item_id, now=NOW + timedelta(minutes=5))["roles"] == {
        "scheduler": "duplicate", "trader": "duplicate"}
    # An edit within the cooldown that touches nothing new is held back too.
    item.content_sha256 = "0" * 64
    assert react(seeded, item.item_id, now=NOW + timedelta(minutes=10))["roles"][
        "trader"] == "cooldown"
    assert seeded.query(NotificationOutboxRecord).count() == 2
    # After the cooldown, changed content is news again.
    assert react(seeded, item.item_id, now=NOW + COOLDOWN + timedelta(minutes=1))["roles"][
        "trader"] == "notified"


def test_a_second_report_of_the_same_outage_within_the_cooldown_is_one_message(seeded):
    react(seeded, _item(seeded, LANGELED).item_id, now=NOW)
    second = _add(seeded, "ec-energy-news", "nyh", "Nyhamna outage cuts Langeled flows",
                  "Unplanned outage at Nyhamna.")
    assert second.linked_event_key == "outage:UMM-NYH"
    assert react(seeded, second.item_id, now=NOW + timedelta(minutes=3))["roles"] == {
        "scheduler": "same_event", "trader": "same_event"}
    assert seeded.query(NotificationOutboxRecord).count() == 2


def test_policy_or_old_items_raise_an_in_app_alert_only(seeded):
    policy = _item(seeded, "Consultation on gas storage regulation")
    assert react(seeded, policy.item_id, now=NOW)["roles"] == {
        "scheduler": "in_app_only", "trader": "in_app_only"}
    old = _add(seeded, "ec-energy-news", "old", "Unplanned outage on Langeled",
               published=NOW - timedelta(days=5))
    assert set(react(seeded, old.item_id, now=NOW)["roles"].values()) == {"in_app_only"}
    assert seeded.query(NotificationOutboxRecord).count() == 0
    assert seeded.query(MonitoringAlertRecord).count() == 4
    assert expire_aged(seeded, now=NOW + timedelta(days=4)) == 4


def test_the_outbox_delivers_news_events_to_the_routing_consumer(seeded):
    seeded.commit()
    result = market_events.process(seeded, CONSUMER_NAME, now_utc=NOW + timedelta(seconds=5),
                                   clock=lambda: NOW + timedelta(seconds=5))
    assert result["processed"] == 3 and result["failed"] == 0
    assert seeded.query(NotificationOutboxRecord).count() == 2
    assert seeded.query(MonitoringAlertRecord).count() == 4


# ---------------------------------------------------------------------------------- the note


class StubModel:
    def __init__(self, reply):
        self.reply = reply
        self.messages = None

    def __call__(self, messages):
        self.messages = messages
        return self.reply


def _evidence(session):
    row = _item(session, LANGELED)
    item = item_dict(row)
    found = matches(item, firm_exposures(session, now=NOW))
    return item, found, build_evidence(session, item, found, row)


def test_the_rule_note_cites_the_item_the_outage_and_each_exposure(seeded):
    item, found, evidence = _evidence(seeded)
    assert list(evidence.lines) == ["N1", "F1", "F2", "F3"]
    assert "REMIT message UMM-NYH by Gassco AS" in evidence.lines["F1"]
    assert "25 mcm/d of technical 145 mcm/d" in evidence.lines["F1"]
    sentences = rule_note(item, found, evidence)
    assert [s["cites"] for s in sentences] == [["N1"], ["F1"], ["N1", "F2"], ["N1", "F3"]]
    note = assemble(item, found, evidence, ai=None, prompt_version="", language="en")
    assert note["basis"] == "rule" and note["label"] is None and note["ai"]["status"] == "off"
    assert note["citations"][0]["url"].startswith("https://www.gov.uk/")
    assert {c["id"] for c in note["citations"]} == {"N1", "F1", "F2", "F3"}


def test_a_grounded_model_note_is_used_and_labelled(seeded):
    item, found, evidence = _evidence(seeded)
    model = StubModel(json.dumps({"sentences": [
        {"text": "The department reports that flows through Langeled to Easington are reduced "
                 "after an unplanned outage at Nyhamna.", "cites": ["N1"]},
        {"text": "Gassco AS states 25 mcm/d unavailable of 145 mcm/d technical.",
         "cites": ["F1"]},
    ]}))
    ai = model_note(model, evidence, language="en")
    assert ai["status"] == "used", ai
    system, user = model.messages
    assert "Never recommend" in system["content"] and "Write in English." in system["content"]
    assert json.loads(user["content"])["lines"]["N1"] == evidence.lines["N1"]
    note = assemble(item, found, evidence, ai=ai, prompt_version="news-note-x", language="en")
    assert note["basis"] == "model" and note["label"] == AI_LABEL
    assert note["ai"]["prompt_version"] == "news-note-x"
    assert len(note["rule_sentences"]) == 4


@pytest.mark.parametrize(
    ("reply", "check"),
    [
        ({"sentences": [{"text": "Gassco AS states 25 mcm/d unavailable.", "cites": ["N1"]}]},
         "number"),
        ({"sentences": [{"text": "The desk should hedge the NBP contract.",
                         "cites": ["N1", "F2"]}]}, "advice"),
        ({"sentences": [{"text": "Langeled flows to Easington are lower.", "cites": []}]},
         "cites"),
    ],
)
def test_an_unsupported_model_note_is_refused_and_the_rule_note_stands(seeded, reply, check):
    item, found, evidence = _evidence(seeded)
    ai = model_note(StubModel(json.dumps(reply)), evidence, language="en")
    assert ai["status"] == "refused" and ai["check"] == check and ai["flags"]
    note = assemble(item, found, evidence, ai=ai, prompt_version="v", language="en")
    assert note["basis"] == "rule" and note["label"] is None
    assert note["sentences"] == note["rule_sentences"]


def test_no_reply_leaves_the_rule_note_and_chinese_is_asked_for_in_chinese(seeded):
    _item_, _found, evidence = _evidence(seeded)
    model = StubModel(None)
    assert model_note(model, evidence, language="zh-CN")["status"] == "unavailable"
    assert "Simplified Chinese" in note_messages(evidence, language="zh-CN")[0]["content"]
