"""Small-desk plan section 5: a new deal changes position and P&L within one second.

The server's share: from the commit of a captured deal (a new one, a correction, a
cancellation) to the ``deals`` change notice in an open live stream's queue. The deal routes
wake the poller at once (``StreamHub.poll_soon``), so the notice does not wait for the poll
interval (1.5 s by default, longer than the target), and the position views stop answering
from before the deal (``warm_views.note_deals``), so the page's re-read computes. The browser
answers a ``deals`` notice without its price throttle (``clients/web`` ``useLiveTopics`` with
``DEAL_LIVE_MS``).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from eurogas_nexus.api.routes.public import streaming
from eurogas_nexus.api.routes.public.streaming import _LiveStream
from eurogas_nexus.api.stream_hub import StreamHub
from eurogas_nexus.db.models import CapturedDealRecord

from .test_stream_hub import _principal, engine  # noqa: F401  (fixture)

#: The plan's target for a new deal to change position and P&L on an open screen.
TARGET_SECONDS = 1.0


def _deal(key: str, book: str, at: datetime) -> CapturedDealRecord:
    return CapturedDealRecord(
        version_id=uuid.uuid4().hex, deal_key=key, version=1, status="live", venue="ICE",
        venue_trade_id=key.split(":")[-1], leg_id="", trade_date=at.date(),
        trade_time_utc=at, trader="trader.a", counterparty="", cleared=True, hub="TTF",
        product="Dec-26", delivery_start=date(2026, 12, 1), delivery_end=date(2026, 12, 31),
        side="buy", volume=Decimal(5), volume_unit="MW", total_mwh=Decimal(3720),
        price=Decimal("31.25"), price_currency="EUR", price_unit="EUR/MWh", physical=False,
        instrument="future", fees=None, fee_currency=None, book_id=book, origin="file",
        file_id=None, file_name="f.csv", line=2, entered_by_hand=None, entered_by="t",
        recorded_at_utc=at, superseded_at_utc=None, change_reason=None, content_digest="d",
    )


def _deal_notices(chunks: list[str]) -> list[str]:
    return [c for c in chunks if "event: change" in c and '"deals"' in c]


def test_a_captured_deal_is_on_the_stream_within_one_second(engine, monkeypatch):  # noqa: F811
    monkeypatch.delenv("EUROGAS_NEXUS_STREAM_POLL_SECONDS", raising=False)
    interval = streaming.poll_seconds()
    assert interval > TARGET_SECONDS  # the default poll alone would miss the target

    async def drive() -> tuple[float, float]:
        hub = StreamHub(
            interval=streaming.poll_seconds,
            session_factory=lambda: (lambda: Session(engine)),
            warning=streaming.warning_event,
        )
        sub = hub.subscribe(_LiveStream(("prices", "deals"), datetime.now(UTC), False, None,
                                        None))
        await asyncio.wait_for(sub.queue.get(), timeout=5)  # ready
        samples = []
        for index in range(3):
            await asyncio.sleep(0.2)  # just after a poll: the worst case without the wake
            with Session(engine) as session:
                session.add(_deal(f"ICE:91{index}", "desk-a", datetime.now(UTC)))
                session.commit()
            committed = time.monotonic()
            hub.poll_soon()  # what the deal routes do after their commit
            while True:
                chunks, _done = await asyncio.wait_for(sub.queue.get(), timeout=5)
                if _deal_notices(chunks):
                    samples.append(time.monotonic() - committed)
                    break
        hub.unsubscribe(sub)
        return max(samples), sum(samples) / len(samples)

    worst, mean = asyncio.run(drive())
    assert worst < TARGET_SECONDS, f"{worst:.3f} s from commit to the deals notice"
    assert mean < interval


def test_a_deal_in_a_book_the_reader_cannot_see_announces_nothing(engine):  # noqa: F811
    from eurogas_nexus.application.live_topics import topic_changes
    from eurogas_nexus.db.models import TradingBookRecord

    start = datetime.now(UTC)
    with Session(engine) as session:
        for book in ("desk-a", "desk-b"):
            session.add(TradingBookRecord(
                book_id=book, name=book, legal_entity="E", region="europe", business="gas",
                base_currency="EUR", commodities=["gas"], active=True, updated_by="t",
                updated_at_utc=start))
        session.add(_deal("ICE:92", "desk-b", datetime.now(UTC)))
        session.commit()
        cursors = {"deals": start}
        mine = topic_changes(session, ("deals",), cursors, _principal("a", "BOOKS:BOOK:desk-a"))
        theirs = topic_changes(session, ("deals",), cursors, _principal("b", "BOOKS:BOOK:desk-b"))
    assert [n["visible"] for n in mine] == [False]  # the cursor moves, nothing is announced
    assert [n["visible"] for n in theirs] == [True]


def test_a_deal_makes_position_views_unservable_for_every_reader():
    from eurogas_nexus.application.warm_views import FRESH, ViewSpec, WarmViews

    calls = {"ladder": 0, "storage": 0}

    def compute(name):
        def run():
            calls[name] += 1
            return {"data": {"n": calls[name]}, "meta": {}}

        return run

    store = WarmViews(watermark=lambda: 1)
    ladder = ViewSpec("portfolio.position_ladder", follows_deals=True)
    storage = ViewSpec("fundamentals.storage")
    store.serve(ladder, "reader-1", ("k",), compute("ladder"))
    store.serve(storage, "reader-1", ("k",), compute("storage"))
    store.note_deals()  # another trader captured a deal
    after = store.serve(ladder, "reader-1", ("k",), compute("ladder"))
    assert after["data"]["n"] == 2 and after["meta"]["view"]["state"] == FRESH  # recomputed
    kept = store.serve(storage, "reader-1", ("k",), compute("storage"))
    assert kept["data"]["n"] == 1  # a view that reads no position is not touched
