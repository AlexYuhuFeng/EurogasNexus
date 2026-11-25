"""NEWS-1: the source registry and its terms, the feed reader, and deterministic tagging.

The feeds are constructed fixtures (``tests/fixtures/news``; each says so in its header, with
the feed address and the date), because the build environment had no outbound network.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from eurogas_nexus.domain.news.feeds import (
    MAX_FEED_BYTES,
    MAX_SUMMARY_CHARS,
    FeedError,
    parse_feed,
    plain_text,
)
from eurogas_nexus.domain.news.sources import (
    EXCLUDED_SOURCES,
    NEWS_SOURCES,
    feed_url_refusal,
    news_source,
    poll_refusal,
    registry_rows,
)
from eurogas_nexus.domain.news.tagging import EVENT_TYPES, gazetteer_size, tag_text, zone_hub
from tests.fixtures.news_seed import FIXTURES, GOVUK_FEED

# ---------------------------------------------------------------------------------- registry


def test_every_polled_source_records_its_terms_and_an_excluded_one_is_never_polled():
    for source in NEWS_SOURCES:
        assert source.reuse == "permitted", source.source_id
        assert source.terms_quote and source.terms_url and source.terms_read_on, source.source_id
        assert source.licence and source.attribution, source.source_id
        datetime.fromisoformat(source.terms_read_on)
    for source in EXCLUDED_SOURCES:
        assert source.reuse in {"forbidden", "licensed", "unknown"}, source.source_id
        assert poll_refusal(source).startswith("reuse is"), source.source_id
        assert source.notes, source.source_id
    ids = [s.source_id for s in (*NEWS_SOURCES, *EXCLUDED_SOURCES)]
    assert len(ids) == len(set(ids))
    rows = {row["source_id"]: row for row in registry_rows()}
    assert set(rows) == set(ids)
    assert rows["wire-and-price-reporters"]["polled"] is False


def test_remit_is_made_from_held_messages_and_only_a_recorded_feed_is_polled():
    assert "nothing is fetched" in poll_refusal(news_source("remit-umm"))
    # Terms read, but no feed address recorded on the publisher's host: not polled.
    for source_id in ("ec-energy-news", "eurlex-oj-energy", "acer-news"):
        assert poll_refusal(news_source(source_id)) == "no feed address recorded"
    assert poll_refusal(news_source("govuk-desnz")) == ""
    # ACER's terms allow reproduction of its news, not of material licensed to it: titles only.
    assert news_source("acer-news").store == "title_only"
    with pytest.raises(KeyError):
        news_source("no-such-source")


@pytest.mark.parametrize(
    ("url", "refused"),
    [
        (GOVUK_FEED, ""),
        ("https://assets.publishing.service.gov.uk/feed.atom", "not the publisher's host"),
        ("https://gov.uk/feed.atom", ""),
        ("https://www.gov.uk.example.com/feed.atom", "not the publisher's host"),
        ("https://evilgov.uk/feed.atom", "not the publisher's host"),
        ("http://www.gov.uk/feed.atom", "must be https"),
        ("https://user:secret@www.gov.uk/feed.atom", "no credentials"),
        ("file:///etc/passwd", "must be https"),
    ],
)
def test_a_feed_address_must_be_https_on_the_publishers_own_host(url, refused):
    reason = feed_url_refusal(news_source("govuk-desnz"), url)
    assert (refused in reason) if refused else reason == "", reason


# ---------------------------------------------------------------------------------- feeds


def test_atom_feed_entries_are_read_with_their_times_links_and_plain_text():
    language, entries = parse_feed((FIXTURES / "govuk_desnz.atom").read_bytes())
    assert language == "en-GB"
    assert [e.title for e in entries] == [
        "Update on Langeled flows to Easington",
        "New sanctions designations on LNG shipping",
        "Consultation on gas storage regulation",
    ]
    first = entries[0]
    assert first.url.startswith("https://www.gov.uk/government/news/")
    assert first.published_at_utc == datetime(2026, 11, 20, 10, 15, tzinfo=UTC)
    assert "<" not in first.summary and first.summary.startswith("Flows through Langeled")


def test_rss_feed_drops_scripts_converts_times_and_refuses_unsafe_links():
    language, entries = parse_feed((FIXTURES / "energy_news.rss").read_bytes())
    assert language == "en"
    strike, cold, unsafe = entries
    assert strike.title == "Strike at Zeebrugge LNG terminal & port"
    assert "alert" not in strike.summary and "<" not in strike.summary
    assert strike.guid == "fixture-zeebrugge-strike"
    assert cold.published_at_utc == datetime(2026, 11, 18, 8, 0, tzinfo=UTC)
    assert unsafe.url == "" and unsafe.published_at_utc is None


@pytest.mark.parametrize(
    "document",
    [
        b'<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">]><rss><channel>'
        b"<item><title>&lol;</title></item></channel></rss>",
        b'<?xml version="1.0"?><!DOCTYPE rss SYSTEM "http://example.org/x.dtd"><rss/>',
    ],
)
def test_a_document_with_a_doctype_or_entity_is_refused_before_parsing(document):
    with pytest.raises(FeedError):
        parse_feed(document)


def test_oversized_or_non_feed_documents_are_refused():
    with pytest.raises(FeedError):
        parse_feed(b"<rss>" + b" " * MAX_FEED_BYTES + b"</rss>")
    with pytest.raises(FeedError):
        parse_feed(b"<html><body>not a feed</body></html>")
    with pytest.raises(FeedError):
        parse_feed(b"<rss><channel><item>")


def test_plain_text_is_bounded():
    text = plain_text("<p>" + "word " * 1000 + "</p>", MAX_SUMMARY_CHARS)
    assert len(text) <= MAX_SUMMARY_CHARS and text.endswith("…")
    assert plain_text("<style>p{}</style>A &amp; B", 50) == "A & B"


# ---------------------------------------------------------------------------------- tagging


def test_assets_operators_hubs_and_event_types_are_tagged_without_a_model():
    tags = tag_text("Unplanned outage at Kollsnes cuts flows through Langeled to Easington")
    ids = {e.entity_id for e in tags.entities}
    assert {"pipeline:langeled"} <= ids
    assert "outage" in tags.event_types and tags.capacity_change
    assert "NBP" in tags.hubs and "NO" in tags.countries
    policy = tag_text("Commission adopts amendment to the gas storage regulation")
    assert policy.event_types == ("policy",)
    sanction = tag_text("New sanctions designations on vessels carrying Russian LNG")
    assert "sanction" in sanction.event_types and "RU" in sanction.countries


def test_hub_codes_match_only_as_written_and_vessels_only_when_held():
    assert "TTF" in tag_text("TTF front month moves").hubs
    assert tag_text("the ttf word in lower case").hubs == ()
    tags = tag_text("Arctic Voyager delayed by fog at Zeebrugge LNG", vessels=["Arctic Voyager"])
    kinds = {(e.kind, e.name) for e in tags.entities}
    assert {("vessel", "Arctic Voyager"), ("terminal", "Zeebrugge LNG")} <= kinds
    assert "ZTP" in tags.hubs
    assert "weather" in tags.event_types
    assert not any(e.kind == "vessel" for e in tag_text("Arctic Voyager delayed").entities)


def test_unrelated_text_carries_no_tags_and_zones_map_to_hubs():
    tags = tag_text("Quarterly report on staff training")
    assert tags.entities == () and tags.event_types == () and tags.hubs == ()
    assert zone_hub("GB") == "NBP" and zone_hub("NL") == "TTF" and zone_hub(None) is None
    assert set(tags.event_types) <= set(EVENT_TYPES)
    assert gazetteer_size() >= 100
