"""Measure the live pipeline (M7): a price committed -> the opportunity change on the stream.

PostgreSQL with the demo desk only (``scripts/demo/seed_demo_desk.py``, evaluated twice so its
opportunities are listed). Each sample stores the firm's mark for TTF for the next gas day, with
the same calls as ``PUT /api/market/firm-marks`` in one transaction: the mark, the pending
``marks`` class and its ``mark.changed`` event. A firm mark outranks the demo's simulated board
and needs no market-data licence, so the demo's event-exposure opportunities (cover at TTF for
the next day) read it on any local store. Settlements and fixings take the same path from the
event on. The clock starts when that commit returns. The marks are withdrawn at the end (marked
superseded); the opportunities keep the last value until the next evaluation.

``after`` (the M7 path): the API and the listen worker must be running
(``python -m uvicorn apps.api.main:app`` and ``scripts/ops/market_events.py listen``). The script
reads ``/api/stream/opportunities`` and stops each sample at the first ``opportunity`` event for
an opportunity that reads the price; it also reports the first ``evaluated`` event.

``before`` (the path before M7): no listen worker. The script plays the scheduler: it drains the
outbox at the next whole minute, as the 60 s ingestion tick did, with the old cap of ten batches.
The stream did not carry the opportunity engine then, so the change was visible only when the
page was reloaded; the figure reported is commit -> the evaluation committed.

``throughput``: publishes ``--events`` events (source ``m7-throughput``, no dependency key, so
no evaluator runs) to a counting consumer, then drains them; it reports publish and delivery
rates, the transport's capacity without evaluation cost. Its events and deliveries are deleted
afterwards.

``notice`` (small-desk plan section 5, "a price change on screen within 200 ms of arriving"):
the API must be running. Each sample commits the TTF mark as above and stops at the first
``change`` notice for the ``book`` topic on ``/api/stream/live`` (the tab's one stream: the
browser re-reads the board on that notice). The figure is the server's share of the target:
commit -> notice on the wire, bounded by ``EUROGAS_NEXUS_STREAM_POLL_SECONDS``. The browser's
share (notice -> re-read -> painted cell) is measured in the browser on the desk's PC, as
``docs/operations/SMALL_DESK_RESILIENCE.md`` describes; add the two.

``deal`` (small-desk plan section 5, "a new deal changes position and P&L within one second"):
the API must be running and ``--book`` must name a book the token may write. Each sample enters
a 1 MW TTF month-ahead deal by hand through ``POST /api/desk/deals/manual`` (the clock starts when
that answer returns, so the store has committed it), stops at the first ``change`` notice for the
``deals`` topic on ``/api/stream/live``, then reads the position ladder as the open page would
(``position_read_ms``: the page's re-read, computed afresh because a deal makes the position
views unservable). Every deal it entered is cancelled by hand at the end (still on the blotter,
marked cancelled, out of the position). The browser's share (notice to painted figures) is
measured in the browser.

The latency modes also read the stages from the store: delivery processed, evaluation
started and finished.
Run it only against a local or demo store; nothing is traded, sent or published elsewhere.

Usage::

    RUNTIME_STORE_DATABASE_URL=postgresql+pg8000://... \\
    EUROGAS_NEXUS_PUBLIC_API_TOKEN=<the local API's token> \\
        python scripts/ops/measure_live_latency.py after --samples 10
    python scripts/ops/measure_live_latency.py before --samples 5
    python scripts/ops/measure_live_latency.py throughput --events 5000
    python scripts/ops/measure_live_latency.py notice --samples 20 --gap 1
    python scripts/ops/measure_live_latency.py deal --book desk-a --samples 10 --gap 1
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import statistics
import threading
import time
from datetime import UTC, datetime, timedelta

ACTOR = "m7-latency"


def _settle(session_factory, price: float) -> tuple[float, str]:
    """Store the mark, its pending class and its event in one transaction; the commit instant
    and the event's key."""

    from eurogas_nexus.application.market_events import publish_firm_marks
    from eurogas_nexus.application.opportunities.schedule import note_input_changed
    from eurogas_nexus.db.repositories.commercial_assumptions import put_firm_marks
    from eurogas_nexus.domain.valuation.firm_marks import validate_firm_mark

    now = datetime.now(UTC)
    day = (now + timedelta(days=1)).date().isoformat()
    entry = validate_firm_mark("TTF", day, price, "EUR/MWh", "M7 latency measurement")
    with session_factory() as session:
        put_firm_marks(session, [entry], actor=ACTOR, now_utc=now)
        note_input_changed(session, "marks", reason="firm marks")
        publish_firm_marks(session, [entry], actor=ACTOR, now_utc=now)
        session.commit()
        committed = time.time()
    return committed, f"hub:TTF:{entry.period.label}"


def _price(index: int) -> float:
    """Alternate about 44 and 40 EUR/MWh: the demo's cover exposure moves by more than the 20 %
    material-change threshold each time, so every sample changes an opportunity's version. A
    cent more each time keeps every value new to the outbox, whatever ran before."""

    base = 44.0 if index % 2 == 0 else 40.0
    return round(base + 0.01 * (int(time.time()) % 1000) + 0.01 * index, 2)


def _stages(session_factory, key: str, since: datetime) -> dict:
    from sqlalchemy import text

    with session_factory() as session:
        row = session.execute(
            text(
                "select e.ingested_at_utc, d.processed_at_utc, "
                "(d.result_json->>'evaluation_id') as evaluation_id "
                "from market_events e join market_event_deliveries d on d.event_seq = e.seq "
                "where e.subject_key = :key and d.consumer = 'opportunities' "
                "and e.ingested_at_utc >= :since order by e.seq desc limit 1"
            ),
            {"key": key, "since": since},
        ).first()
        if row is None:
            return {}
        evaluation = None
        if row.evaluation_id:
            evaluation = session.execute(
                text(
                    "select started_at_utc, finished_at_utc from opportunity_evaluations "
                    "where evaluation_id = :id"
                ),
                {"id": row.evaluation_id},
            ).first()
    out = {"processed_at_utc": row.processed_at_utc, "evaluation_id": row.evaluation_id}
    if evaluation is not None:
        out["evaluation_ms"] = round(
            (evaluation.finished_at_utc - evaluation.started_at_utc).total_seconds() * 1000
        )
        out["finished_at_utc"] = evaluation.finished_at_utc
    return out


def _reader(
    base_url: str,
    token: str,
    frames: queue.Queue,
    stop: threading.Event,
    path: str = "/api/stream/opportunities",
) -> None:
    import httpx

    headers = {"X-Eurogas-Api-Key": token, "Accept": "text/event-stream"}
    with httpx.stream(
        "GET", f"{base_url}{path}", headers=headers, timeout=None
    ) as response:
        response.raise_for_status()
        event = None
        for line in response.iter_lines():
            if stop.is_set():
                return
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: ") and event:
                frames.put((time.time(), event, json.loads(line[6:])))
                event = None


def _after(session_factory, args) -> list[dict]:
    from sqlalchemy import text

    with session_factory() as session:
        readers = {
            row.opportunity_id
            for row in session.execute(
                text("select opportunity_id from opportunity_dependencies where input_key = :k"),
                {"k": f"hub:TTF:{(datetime.now(UTC) + timedelta(days=1)).date().isoformat()}"},
            )
        }
    frames: queue.Queue = queue.Queue()
    stop = threading.Event()
    threading.Thread(
        target=_reader, args=(args.base_url, args.token, frames, stop), daemon=True
    ).start()
    time.sleep(3)  # the stream's first poll
    while not frames.empty():
        frames.get_nowait()
    samples = []
    for index in range(args.samples):
        since = datetime.now(UTC)
        committed, key = _settle(session_factory, _price(index))
        evaluated = changed = None
        deadline = committed + args.timeout
        while time.time() < deadline and changed is None:
            try:
                at, event, data = frames.get(timeout=0.2)
            except queue.Empty:
                continue
            if at < committed:
                continue
            if event == "evaluated" and data.get("trigger") == "outbox" and evaluated is None:
                evaluated = at
            if event == "opportunity" and data.get("opportunity_id") in readers:
                changed = at
        stages = {}
        for _ in range(60):  # the change may come from a sweep before this event's own run
            stages = _stages(session_factory, key, since - timedelta(seconds=1))
            if stages.get("finished_at_utc"):
                break
            time.sleep(0.5)
        sample = {
            "evaluated_on_stream_ms": round((evaluated - committed) * 1000) if evaluated else None,
            "opportunity_on_stream_ms": round((changed - committed) * 1000) if changed else None,
            "processed_ms": _ms(stages.get("processed_at_utc"), committed),
            "evaluation_ms": stages.get("evaluation_ms"),
            "evaluation_committed_ms": _ms(stages.get("finished_at_utc"), committed),
        }
        samples.append(sample)
        print(json.dumps(sample), flush=True)
        time.sleep(args.gap)
    stop.set()
    return samples


def _notice(session_factory, args) -> list[dict]:
    """Commit a mark -> its ``change`` notice (topic ``book``) on the tab's live stream."""

    frames: queue.Queue = queue.Queue()
    stop = threading.Event()
    threading.Thread(
        target=_reader,
        args=(args.base_url, args.token, frames, stop, "/api/stream/live?topics=book,prices"),
        daemon=True,
    ).start()
    time.sleep(3)  # the stream's first poll
    while not frames.empty():
        frames.get_nowait()
    samples = []
    for index in range(args.samples):
        committed, _key = _settle(session_factory, _price(index))
        noticed = None
        deadline = committed + args.timeout
        while time.time() < deadline and noticed is None:
            try:
                at, event, data = frames.get(timeout=0.05)
            except queue.Empty:
                continue
            if at >= committed and event == "change" and data.get("topic") == "book":
                noticed = at
        sample = {"notice_on_stream_ms": round((noticed - committed) * 1000) if noticed else None}
        samples.append(sample)
        print(json.dumps(sample), flush=True)
        time.sleep(args.gap)
    stop.set()
    return samples


def _before(session_factory, args) -> list[dict]:
    import random

    from eurogas_nexus.application import market_events

    samples = []
    for index in range(args.samples):
        time.sleep(random.uniform(1, 59))  # an import lands anywhere in the minute
        since = datetime.now(UTC)
        committed, key = _settle(session_factory, _price(index))
        tick = (int(committed) // 60 + 1) * 60
        time.sleep(max(0.0, tick - time.time()))
        market_events.drain(session_factory, max_batches=10, max_seconds=None)
        stages = _stages(session_factory, key, since - timedelta(seconds=1))
        sample = {
            "tick_wait_ms": round((tick - committed) * 1000),
            "processed_ms": _ms(stages.get("processed_at_utc"), committed),
            "evaluation_ms": stages.get("evaluation_ms"),
            "evaluation_committed_ms": _ms(stages.get("finished_at_utc"), committed),
            "opportunity_on_stream_ms": None,  # the stream did not carry the engine
        }
        samples.append(sample)
        print(json.dumps(sample), flush=True)
    return samples


def _throughput(session_factory, args) -> list[dict]:
    from eurogas_nexus.application import market_events
    from eurogas_nexus.db.models import MarketEventDeliveryRecord, MarketEventRecord
    from eurogas_nexus.domain.market_events import MarketEvent

    class Counter:
        name = "m7-throughput"
        seen = 0

        def accepts(self, record) -> bool:
            return record.source_id == "m7-throughput"

        def handle(self, session, records, *, now_utc):
            Counter.seen += len(records)
            return {"seen": len(records)}

    market_events.register_consumer(Counter())
    run = datetime.now(UTC).strftime("%H%M%S%f")
    try:
        started = time.perf_counter()
        with session_factory() as session:
            for index in range(args.events):
                now = datetime.now(UTC)
                market_events.publish(
                    session,
                    MarketEvent(
                        source_id="m7-throughput",
                        event_type="price.updated",
                        subject_key=f"m7:{run}:{index}",
                        ingested_at_utc=now,
                        market_time_utc=now,
                        published_at_utc=now,
                        payload={"n": index},
                    ),
                )
                if index % 500 == 499:
                    session.commit()
            session.commit()
        published = time.perf_counter() - started
        started = time.perf_counter()
        market_events.drain(session_factory, max_seconds=None)
        drained = time.perf_counter() - started
    finally:
        market_events.unregister_consumer("m7-throughput")
        with session_factory() as session:
            seqs = [
                seq
                for (seq,) in session.query(MarketEventRecord.seq).filter(
                    MarketEventRecord.source_id == "m7-throughput"
                )
            ]
            for chunk in range(0, len(seqs), 1000):
                part = seqs[chunk : chunk + 1000]
                session.query(MarketEventDeliveryRecord).filter(
                    MarketEventDeliveryRecord.event_seq.in_(part)
                ).delete(synchronize_session=False)
                session.query(MarketEventRecord).filter(MarketEventRecord.seq.in_(part)).delete(
                    synchronize_session=False
                )
            session.commit()
    sample = {
        "events": args.events,
        "delivered": Counter.seen,
        "publish_per_s": round(args.events / published),
        "deliver_per_s": round(Counter.seen / drained) if drained else None,
    }
    print(json.dumps(sample), flush=True)
    return [sample]


def _deal(session_factory, args) -> list[dict]:
    """A deal entered by hand -> its ``deals`` notice on the live stream -> the ladder re-read."""

    import httpx

    if not args.book:
        raise SystemExit("deal mode needs --book (a book the token may write)")
    headers = {"X-Eurogas-Api-Key": args.token}
    frames: queue.Queue = queue.Queue()
    stop = threading.Event()
    threading.Thread(
        target=_reader,
        args=(args.base_url, args.token, frames, stop, "/api/stream/live?topics=deals,prices"),
        daemon=True,
    ).start()
    time.sleep(3)  # the stream's first poll
    while not frames.empty():
        frames.get_nowait()
    samples, keys = [], []
    with httpx.Client(base_url=args.base_url, headers=headers, timeout=60) as client:
        try:
            for index in range(args.samples):
                answer = client.post("/api/desk/deals/manual", json={
                    "book": args.book, "venue": "OTC", "counterparty": ACTOR, "hub": "TTF",
                    "product": "M+1", "side": "buy" if index % 2 == 0 else "sell",
                    "volume": "1", "volume_unit": "MW", "price": "30", "price_unit": "EUR/MWh",
                })
                answer.raise_for_status()
                committed = time.time()
                keys.append(answer.json()["data"]["deal_key"])
                noticed = None
                deadline = committed + args.timeout
                while time.time() < deadline and noticed is None:
                    try:
                        at, event, data = frames.get(timeout=0.02)
                    except queue.Empty:
                        continue
                    if at >= committed and event == "change" and data.get("topic") == "deals":
                        noticed = at
                read_started = time.time()
                client.get("/api/portfolio/position-ladder").raise_for_status()
                read_ms = round((time.time() - read_started) * 1000)
                sample = {
                    "deal_notice_on_stream_ms": round((noticed - committed) * 1000)
                    if noticed else None,
                    "position_read_ms": read_ms,
                    "deal_to_new_position_ms": round((time.time() - committed) * 1000),
                }
                samples.append(sample)
                print(json.dumps(sample), flush=True)
                time.sleep(args.gap)
        finally:
            for key in keys:
                client.post("/api/desk/deals/manual",
                            json={"book": args.book, "deal_key": key, "status": "cancelled"})
            stop.set()
    return samples


def _ms(instant: datetime | None, committed: float) -> int | None:
    return round((instant.timestamp() - committed) * 1000) if instant else None


def _summary(samples: list[dict]) -> dict:
    out = {}
    for name in samples[0]:
        values = sorted(s[name] for s in samples if s.get(name) is not None)
        if values:
            out[name] = {
                "n": len(values),
                "median": round(statistics.median(values)),
                "max": values[-1],
                "min": values[0],
            }
    return out


def main(argv: list[str] | None = None) -> int:
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("mode", choices=("after", "before", "throughput", "notice", "deal"))
    parser.add_argument("--book", default="", help="deal mode: the book the deals go in")
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", default=os.environ.get("EUROGAS_NEXUS_PUBLIC_API_TOKEN", ""))
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--events", type=int, default=5000)
    parser.add_argument("--gap", type=float, default=3.0, help="seconds between samples")
    args = parser.parse_args(argv)
    if not resolve_database_url().startswith("postgresql"):
        parser.error("needs PostgreSQL (RUNTIME_STORE_DATABASE_URL)")
    factory = get_session_factory()
    run = {"after": _after, "before": _before, "throughput": _throughput,
           "notice": _notice, "deal": _deal}[args.mode]
    try:
        samples = run(factory, args)
    finally:
        from eurogas_nexus.db.models import FirmMarkRecord

        with factory() as session:
            session.query(FirmMarkRecord).filter(FirmMarkRecord.entered_by == ACTOR).filter(
                FirmMarkRecord.superseded_at_utc.is_(None)
            ).update({"superseded_at_utc": datetime.now(UTC)}, synchronize_session=False)
            session.commit()
    print(json.dumps({"mode": args.mode, "summary": _summary(samples)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
