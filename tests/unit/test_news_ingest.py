"""NEWS-1 ingest: polling within the terms, dedupe and revisions, REMIT items, and the link
from a news item to a held outage that re-evaluates opportunities (market events).

Every fetch goes through a fake fetcher serving the constructed fixture feed; nothing here
touches the network.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from eurogas_nexus.application.news_ingest import (
    EVENT_SOURCE,
    FetchResult,
    http_fetch,
    item_id_for,
    poll_all,
    poll_source,
    robots_allows,
    sync_remit_items,
)
from eurogas_nexus.db.models import MarketEventRecord, NewsItemRecord, NewsSourcePollRecord
from eurogas_nexus.domain.news.sources import news_source
from tests.fixtures.news_seed import GOVUK_FEED, FakeFetcher, govuk_feed, remit, store

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
GOVUK = news_source("govuk-desnz")


def _session(tmp_path) -> Session:
    _url, engine = store(tmp_path)
    return Session(engine)


def test_a_feed_poll_stores_tagged_items_once_and_skips_within_the_interval(tmp_path):
    fetch = FakeFetcher(govuk_feed())
    with _session(tmp_path) as session:
        outcome = poll_source(session, GOVUK, fetch=fetch, now=NOW)
        assert (outcome.status, outcome.seen, outcome.new, outcome.changed) == ("ok", 3, 3, 0)
        rows = session.query(NewsItemRecord).order_by(NewsItemRecord.published_at_utc).all()
        assert [r.title for r in rows][-1] == "Update on Langeled flows to Easington"
        langeled = rows[-1]
        assert langeled.source_id == "govuk-desnz" and "Energy Security" in langeled.publisher
        assert langeled.url.startswith("https://www.gov.uk/") and langeled.language == "en"
        assert "outage" in langeled.event_types and "NBP" in langeled.hubs
        assert len(langeled.content_sha256) == 64 and langeled.revision == 1
        assert "Open Government Licence" in langeled.licence_note
        assert langeled.item_id == item_id_for("govuk-desnz",
                                               "https://www.gov.uk/government/news/"
                                               "fixture-langeled-maintenance")
        # robots.txt first, then the feed, with this product's own identity in the fetcher.
        assert [url for url, _ in fetch.calls] == ["https://www.gov.uk/robots.txt", GOVUK_FEED]
        again = poll_source(session, GOVUK, fetch=fetch, now=NOW + timedelta(minutes=5))
        assert again.status == "skipped" and len(fetch.calls) == 2
        poll = session.get(NewsSourcePollRecord, "govuk-desnz")
        assert poll.last_status == "ok" and poll.items_new == 3 and poll.etag == '"v1"'


def test_an_unchanged_feed_is_not_modified_and_an_edited_entry_is_a_revision(tmp_path):
    fetch = FakeFetcher(govuk_feed())
    later = NOW + timedelta(hours=2)
    with _session(tmp_path) as session:
        poll_source(session, GOVUK, fetch=fetch, now=NOW)
        outcome = poll_source(session, GOVUK, fetch=fetch, now=later)
        assert outcome.status == "not_modified"
        assert fetch.calls[-1][1] == {"If-None-Match": '"v1"'}
        # The same entries served again (no ETag): seen, nothing new.
        plain = FakeFetcher(govuk_feed(), etag=None)
        same = poll_source(session, GOVUK, fetch=plain, now=later, force=True)
        assert (same.seen, same.new, same.changed) == (3, 0, 0)
        assert session.query(NewsItemRecord).count() == 3
        edited = FakeFetcher(govuk_feed().replace(b"Capacity is expected to return this week.",
                                                  b"Capacity returned on Friday."), etag=None)
        changed = poll_source(session, GOVUK, fetch=edited, now=later, force=True)
        assert (changed.new, changed.changed) == (0, 1)
        row = session.get(NewsItemRecord, changed.item_ids[0])
        assert row.revision == 2 and row.summary.endswith("Capacity returned on Friday.")
        assert session.query(NewsItemRecord).count() == 3


def test_robots_and_terms_are_respected_before_any_feed_is_read(tmp_path):
    with _session(tmp_path) as session:
        disallow = FakeFetcher(govuk_feed(), robots=(200, b"User-agent: *\nDisallow: /\n"))
        outcome = poll_source(session, GOVUK, fetch=disallow, now=NOW)
        assert outcome.status == "robots_disallowed"
        assert [url for url, _ in disallow.calls] == ["https://www.gov.uk/robots.txt"]
        unreadable = FakeFetcher(govuk_feed(), robots=(503, b""))
        assert poll_source(session, GOVUK, fetch=unreadable, now=NOW,
                           force=True).status == "robots_disallowed"
        # A source whose terms forbid reuse, or whose feed is not recorded, is never fetched.
        never = FakeFetcher(govuk_feed())
        for source_id in ("eex-website", "wire-and-price-reporters", "acer-news"):
            assert poll_source(session, news_source(source_id), fetch=never,
                               now=NOW).status == "refused"
        # An override address on another host is refused too.
        moved = poll_source(session, GOVUK, fetch=never, now=NOW, force=True,
                            feed_url="https://feeds.example.com/desnz.atom")
        assert moved.status == "refused" and "not the publisher's host" in moved.detail
        assert never.calls == []
        assert session.get(NewsSourcePollRecord, "eex-website").last_status == "refused"


def test_robots_rules_for_this_product_and_the_real_fetcher_refuse_plain_http():
    own = FakeFetcher(b"", robots=(200, b"User-agent: EurogasNexus-NewsPoller\nDisallow: /\n"))
    assert robots_allows(own, GOVUK_FEED)[0] is False
    other = FakeFetcher(b"", robots=(200, b"User-agent: SomeBot\nDisallow: /\n"))
    assert robots_allows(other, GOVUK_FEED) == (True, "robots.txt allows")
    assert http_fetch("http://www.gov.uk/feed.atom", {}) == FetchResult(0, b"",
                                                                        {"error": "https only"})


def test_a_failed_or_unreadable_feed_is_recorded_and_stores_nothing(tmp_path):
    with _session(tmp_path) as session:
        broken = FakeFetcher(b"<html>maintenance</html>", etag=None)
        assert poll_source(session, GOVUK, fetch=broken, now=NOW).status == "failed"

        def down(url, headers):
            if url.endswith("robots.txt"):
                return FetchResult(404, b"", {})
            return FetchResult(0, b"", {"error": "URLError"})

        failed = poll_source(session, GOVUK, fetch=down, now=NOW, force=True)
        assert failed.status == "failed" and "URLError" in failed.detail
        assert session.query(NewsItemRecord).count() == 0


def test_held_remit_messages_become_items_linked_to_their_outage(tmp_path):
    with _session(tmp_path) as session:
        session.add_all(remit(NOW, "UMM-NYH", "Nyhamna"))
        session.add_all(remit(NOW, "UMM-NYH", "Nyhamna", version=2, unavailable=30))
        session.commit()
        outcome = sync_remit_items(session, now=NOW)
        assert (outcome.status, outcome.new) == ("ok", 1)
        row = session.get(NewsItemRecord, outcome.item_ids[0])
        assert row.source_id == "remit-umm" and row.publisher == "Gassco AS"
        assert row.linked_event_key == "outage:UMM-NYH" and "outage" in row.event_types
        assert "Unavailable 30 mcm/d of technical 145 mcm/d." in row.summary
        assert "version 2" in row.summary
        # REMIT items carry no dependency key: M5 change capture already published the outage.
        event = (session.query(MarketEventRecord)
                 .filter(MarketEventRecord.event_type == "news.published").one())
        assert event.dependency_keys == [] and event.source_id == EVENT_SOURCE
        assert sync_remit_items(session, now=NOW).new == 0


def test_a_feed_item_on_a_held_open_outage_links_to_it_and_wakes_opportunities(tmp_path):
    with _session(tmp_path) as session:
        session.add_all(remit(NOW, "UMM-NYH", "Nyhamna"))
        session.add_all(remit(NOW, "UMM-ENDED", "Nyhamna", start_hours=-72, days=-1))
        session.commit()
        poll_source(session, GOVUK, fetch=FakeFetcher(govuk_feed()), now=NOW)
        session.commit()
        item = (session.query(NewsItemRecord)
                .filter(NewsItemRecord.title.like("Update on Langeled%")).one())
        assert item.linked_event_key == "outage:UMM-NYH"
        event = (session.query(MarketEventRecord)
                 .filter(MarketEventRecord.subject_key == f"news:{item.item_id}").one())
        assert event.event_type == "news.published"
        assert event.dependency_keys == ["outage:UMM-NYH"] and event.input_class == "outages"
        # Items not about an outage on a held asset link to nothing.
        others = (session.query(NewsItemRecord)
                  .filter(NewsItemRecord.item_id != item.item_id).all())
        assert {o.linked_event_key for o in others} == {None}


def test_poll_all_reads_remit_then_each_pollable_feed(tmp_path):
    fetch = FakeFetcher(govuk_feed())
    with _session(tmp_path) as session:
        outcomes = {o.source_id: o.status for o in poll_all(session, fetch=fetch, now=NOW)}
        assert outcomes["remit-umm"] == "ok" and outcomes["govuk-desnz"] == "ok"
        assert outcomes["ec-energy-news"] == "refused"
        assert {url for url, _ in fetch.calls} == {"https://www.gov.uk/robots.txt", GOVUK_FEED}


def test_the_operator_script_stores_only_with_commit(tmp_path, monkeypatch, capsys):
    import importlib.util
    from pathlib import Path

    url, engine = store(tmp_path, "script.sqlite")
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    path = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "poll_news_sources.py"
    spec = importlib.util.spec_from_file_location("poll_news_sources", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fetch = FakeFetcher(govuk_feed())
    assert module.main(["--source", "govuk-desnz"], fetch=fetch) == 0
    assert "Dry run" in capsys.readouterr().out
    with Session(engine) as session:
        assert session.query(NewsItemRecord).count() == 0
    assert module.main(["--source", "govuk-desnz", "--commit"], fetch=fetch) == 0
    with Session(engine) as session:
        assert session.query(NewsItemRecord).count() == 3
    assert module.main(["--feed-url", GOVUK_FEED], fetch=fetch) == 2
    assert module.main(["--commit"], fetch=FakeFetcher(govuk_feed())) == 0
    out = capsys.readouterr().out
    assert "ec-energy-news" in out and "refused" in out
