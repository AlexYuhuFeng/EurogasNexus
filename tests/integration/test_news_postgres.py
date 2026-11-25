"""NEWS-1 on PostgreSQL migrated to head: a feed poll stores items with their JSON tags and
times, a second poll changes nothing, a held outage links, and the routing consumer tells
each role once through the outbox.

Run with ``EUROGAS_NEXUS_TEST_POSTGRES_URL`` (or ``RUNTIME_STORE_DATABASE_URL``) set to a
PostgreSQL store migrated to head.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from eurogas_nexus.application import market_events
from eurogas_nexus.application.news_ingest import EVENT_SOURCE, poll_source
from eurogas_nexus.application.news_reads import NewsFilters, item_detail, list_items
from eurogas_nexus.application.news_routing import CONSUMER_NAME
from eurogas_nexus.db.models import (
    MarketEventDeliveryRecord,
    MarketEventRecord,
    MonitoringAlertRecord,
    NewsItemRecord,
    NewsSourcePollRecord,
    NotificationOutboxRecord,
    RemitUmmRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.domain.news.sources import news_source
from tests.fixtures.news_seed import FakeFetcher, contract, govuk_feed, remit

_URL = os.environ.get("EUROGAS_NEXUS_TEST_POSTGRES_URL") or os.environ.get(
    "RUNTIME_STORE_DATABASE_URL", ""
)
pytestmark = pytest.mark.skipif(not _URL.startswith("postgresql"),
                                reason="no PostgreSQL test store")


@pytest.fixture()
def engine():
    engine = create_engine(_URL, future=True)
    tag = uuid4().hex[:8]
    yield engine, tag
    with Session(engine) as session:
        ids = [r.item_id for r in session.query(NewsItemRecord.item_id)]
        seqs = [r.seq for r in session.query(MarketEventRecord.seq)
                .filter(MarketEventRecord.source_id == EVENT_SOURCE)]
        session.query(MarketEventDeliveryRecord).filter(
            MarketEventDeliveryRecord.event_seq.in_(seqs)).delete(synchronize_session=False)
        session.query(MarketEventRecord).filter(
            MarketEventRecord.source_id == EVENT_SOURCE).delete(synchronize_session=False)
        session.query(MonitoringAlertRecord).filter(
            MonitoringAlertRecord.entity_id.in_(ids)).delete(synchronize_session=False)
        session.query(NotificationOutboxRecord).filter(
            NotificationOutboxRecord.dedupe_key.like("news:%")).delete(synchronize_session=False)
        session.query(NewsItemRecord).delete()
        session.query(NewsSourcePollRecord).delete()
        session.query(RemitUmmRecord).filter(
            RemitUmmRecord.message_id == f"UMM-NYH-{tag}").delete()
        session.query(UpstreamResourceContractRecord).filter(
            UpstreamResourceContractRecord.contract_id == f"news-{tag}").delete()
        session.commit()
    engine.dispose()


def test_news_tables_poll_link_route_and_read_on_postgresql(engine):
    engine, tag = engine
    tables = set(inspect(engine).get_table_names())
    assert {"news_items", "news_source_polls"} <= tables
    now = datetime.now(UTC).replace(microsecond=0)
    with Session(engine) as session:
        session.add(contract(f"news-{tag}", "NBP", None, now))
        session.add_all(remit(now, f"UMM-NYH-{tag}", "Nyhamna"))
        session.commit()
        fetch = FakeFetcher(govuk_feed())
        first = poll_source(session, news_source("govuk-desnz"), fetch=fetch, now=now)
        session.commit()
        assert (first.status, first.new) == ("ok", 3)
        again = poll_source(session, news_source("govuk-desnz"), fetch=FakeFetcher(
            govuk_feed(), etag=None), now=now + timedelta(hours=2), force=True)
        session.commit()
        assert (again.new, again.changed) == (0, 0)
        item = (session.query(NewsItemRecord)
                .filter(NewsItemRecord.title.like("Update on Langeled%")).one())
        assert item.linked_event_key == f"outage:UMM-NYH-{tag}"
        assert item.published_at_utc.tzinfo is not None and "NBP" in item.hubs
        assert {e["entity_id"] for e in item.entities} >= {"pipeline:langeled"}
        result = market_events.process(session, CONSUMER_NAME, now_utc=now + timedelta(seconds=5))
        session.commit()
        assert result["processed"] == 3 and result["failed"] == 0
        alert = (session.query(MonitoringAlertRecord)
                 .filter(MonitoringAlertRecord.fingerprint == f"news:{item.item_id}:trader")
                 .one())
        assert alert.category == "news_trader"
        rows = list_items(session, NewsFilters(hub="NBP", mine=True), book_allowed=True,
                          visible_books=None, now=now)
        assert rows[0]["item_id"] == item.item_id
        detail = item_detail(session, item.item_id, book_allowed=True, visible_books=None,
                             now=now)
        assert detail["note"]["citations"][0]["item_id"] == item.item_id
        session.rollback()
