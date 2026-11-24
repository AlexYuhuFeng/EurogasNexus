"""The market event outbox (M4): the whole event lifecycle on a runtime store.

Publish (idempotent, revisions supersede), deliver in priority order, re-evaluate only the
evaluators whose opportunities read a changed key, retry with backoff, dead-letter, replay
reproducibly, staleness, the five-time timeline, and the two producers wired today (ingestion
runs in the scheduler, firm marks through the API).
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from eurogas_nexus.api.app import create_app
from eurogas_nexus.application import market_events as outbox
from eurogas_nexus.application.opportunities.service import run_evaluation
from eurogas_nexus.core.config import Settings
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    IngestionRunRecord,
    MarketEventDeliveryRecord,
    MarketEventRecord,
    OpportunityEvaluationRecord,
    OpportunityRecord,
)
from eurogas_nexus.db.repositories import identity as identity_repository
from eurogas_nexus.domain.market_events import MarketEvent, PublishKind
from eurogas_nexus.security import rate_limit as rate_limit_module

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 17, 9, 42, tzinfo=UTC)
PUBLIC_TOKEN = "test-public-api-token"


@pytest.fixture()
def engine(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'outbox.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_PUBLIC_API_TOKEN", PUBLIC_TOKEN)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    rate_limit_module._WINDOWS.clear()
    return engine


class Recorder:
    """A test consumer: records what it was given, optionally fails."""

    def __init__(self, name="recorder", fail_times=0, accepts_all=True):
        self.name = name
        self.fail_times = fail_times
        self.accepts_all = accepts_all
        self.batches: list[list[str]] = []

    def accepts(self, record) -> bool:
        return self.accepts_all or bool(record.dependency_keys)

    def handle(self, session, records, *, now_utc):
        if self.fail_times:
            self.fail_times -= 1
            raise RuntimeError("consumer down")
        self.batches.append([record.event_id for record in records])
        return {"seen": len(records), "notified": True}


@pytest.fixture()
def recorder():
    item = Recorder()
    outbox.register_consumer(item)
    yield item
    outbox.unregister_consumer(item.name)


def _event(subject="hub:TTF:2027-01", value="31.25", event_type="price.updated", **kw):
    base = {
        "source_id": "src-eex",
        "event_type": event_type,
        "subject_key": subject,
        "ingested_at_utc": NOW,
        "market_time_utc": datetime(2026, 11, 16, tzinfo=UTC),
        "published_at_utc": NOW - timedelta(minutes=20),
        "payload": {"settlement": value},
    }
    base.update(kw)
    return MarketEvent(**base)


def _seed_and_evaluate(session) -> None:
    spec = importlib.util.spec_from_file_location(
        "seed_demo_desk_outbox", ROOT / "scripts" / "demo" / "seed_demo_desk.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.seed(session, NOW, history_days=5)
    session.commit()
    run_evaluation(session, trigger="on_demand", triggered_by="t", now_utc=NOW, demo_desk=True)
    session.commit()


def test_publish_is_idempotent_and_a_correction_supersedes(engine, recorder) -> None:
    with Session(engine) as session:
        first = outbox.publish(session, _event())
        assert first.kind is PublishKind.NEW and first.revision == 1
        assert set(first.deliveries) == {"opportunities", "recorder"}
        # The same fact again (re-published later) writes nothing.
        again = outbox.publish(session, _event(ingested_at_utc=NOW + timedelta(minutes=5)))
        assert again.kind is PublishKind.DUPLICATE and again.event_id == first.event_id
        corrected = outbox.publish(session, _event(value="31.40"))
        assert corrected.kind is PublishKind.REVISION and corrected.revision == 2
        assert corrected.supersedes_event_id == first.event_id
        # The first figure replayed after its correction does not resurrect it.
        assert outbox.publish(session, _event()).kind is PublishKind.OUT_OF_ORDER
        session.commit()
        rows = session.query(MarketEventRecord).order_by(MarketEventRecord.seq).all()
        assert [(r.event_id, r.revision) for r in rows] == [
            (first.event_id, 1),
            (corrected.event_id, 2),
        ]
        states = {
            (d.consumer, d.event_seq): d.status
            for d in session.query(MarketEventDeliveryRecord).all()
        }
        assert states == {
            ("opportunities", rows[0].seq): "superseded",
            ("recorder", rows[0].seq): "superseded",
            ("opportunities", rows[1].seq): "pending",
            ("recorder", rows[1].seq): "pending",
        }
        summary = outbox.process(session, "recorder", now_utc=NOW)
        assert summary["processed"] == 1 and recorder.batches == [[corrected.event_id]]


def test_delivery_is_by_priority_then_log_order(engine, recorder) -> None:
    with Session(engine) as session:
        price = outbox.publish(session, _event())
        fx = outbox.publish(
            session, _event(subject="fx:EURGBP", event_type="fx.updated", source_id="src-ecb")
        )
        outage = outbox.publish(
            session,
            _event(
                subject="outage:UMM-77",
                event_type="outage.published",
                source_id="src-remit-umm",
                identity="UMM-77",
            ),
        )
        outbox.process(session, "recorder", now_utc=NOW)
        assert recorder.batches == [[outage.event_id, price.event_id, fx.event_id]]
        # Nothing is delivered twice.
        assert outbox.process(session, "recorder", now_utc=NOW)["claimed"] == 0


def test_a_failing_consumer_is_retried_with_backoff_then_dead_lettered(engine) -> None:
    flaky = Recorder(name="flaky", fail_times=outbox.MAX_ATTEMPTS)
    outbox.register_consumer(flaky)
    try:
        with Session(engine) as session:
            published = outbox.publish(session, _event())
            first = outbox.process(session, "flaky", now_utc=NOW)
            assert (first["failed"], first["dead"]) == (1, 0)
            # Not due again before the backoff.
            assert outbox.process(session, "flaky", now_utc=NOW)["claimed"] == 0
            at = NOW
            for attempt in range(2, outbox.MAX_ATTEMPTS + 1):
                at = at + outbox.backoff(attempt - 1)
                result = outbox.process(session, "flaky", now_utc=at)
                assert result["claimed"] == 1
            assert result["dead"] == 1
            report = outbox.status(session, now_utc=at)["consumers"]["flaky"]
            assert report["counts"]["dead"] == 1
            assert report["dead_letters"][0]["event_id"] == published.event_id
            assert "consumer down" in report["dead_letters"][0]["last_error"]
            # A replay re-arms the dead letter; the consumer is back and processes it.
            assert outbox.replay(session, "flaky", now_utc=at, event_ids=[published.event_id])[
                "rearmed"
            ] == 1
            assert outbox.process(session, "flaky", now_utc=at)["processed"] == 1
            assert flaky.batches == [[published.event_id]]
    finally:
        outbox.unregister_consumer("flaky")


def test_backoff_doubles_and_is_capped() -> None:
    assert [outbox.backoff(n).total_seconds() for n in (1, 2, 3, 4)] == [60, 120, 240, 480]
    assert outbox.backoff(30) == outbox.BACKOFF_CAP


def test_a_consumer_failure_leaves_none_of_its_writes(engine) -> None:
    class Partial(Recorder):
        def handle(self, session, records, *, now_utc):
            session.add(
                IngestionRunRecord(
                    run_id="half-written", source_name="x", source_id="x",
                    status="RUNNING", started_at_utc=now_utc,
                )
            )
            session.flush()
            raise RuntimeError("after writing")

    outbox.register_consumer(Partial(name="partial"))
    try:
        with Session(engine) as session:
            outbox.publish(session, _event())
            assert outbox.process(session, "partial", now_utc=NOW)["failed"] == 1
            session.commit()
            assert session.get(IngestionRunRecord, "half-written") is None
    finally:
        outbox.unregister_consumer("partial")


def test_replay_reproduces_the_current_state_and_reaches_a_new_consumer(engine) -> None:
    with Session(engine) as session:
        first = outbox.publish(session, _event())
        corrected = outbox.publish(session, _event(value="31.40"))
        other = outbox.publish(session, _event(subject="hub:NBP:2027-01", source_id="src-ice"))
        session.commit()
        late = Recorder(name="late")
        outbox.register_consumer(late)
        try:
            created = outbox.replay(session, "late", now_utc=NOW)
            assert created == {"consumer": "late", "rearmed": 0, "created": 2}
            outbox.process(session, "late", now_utc=NOW)
            assert late.batches == [[corrected.event_id, other.event_id]]
            assert first.event_id not in late.batches[0]
            # Replaying again by log position gives the same ids in the same order.
            rearmed = outbox.replay(
                session, "late", now_utc=NOW, from_seq=1, since_utc=NOW - timedelta(days=1)
            )
            assert rearmed["rearmed"] == 2
            outbox.process(session, "late", now_utc=NOW)
            assert late.batches[1] == late.batches[0]
        finally:
            outbox.unregister_consumer("late")


def test_staleness_and_the_timeline(engine, recorder) -> None:
    with Session(engine) as session:
        published = outbox.publish(session, _event())
        outbox.publish(
            session,
            _event(
                subject="outage:UMM-9",
                event_type="outage.published",
                source_id="src-remit-umm",
                ingested_at_utc=NOW - timedelta(hours=8),
                published_at_utc=NOW - timedelta(hours=8),
            ),
        )
        findings = outbox.staleness(session, now_utc=NOW)
        assert [(f["subject_key"], f["status"]) for f in findings] == [
            ("outage:UMM-9", "stale"),
            ("hub:TTF:2027-01", "live"),
        ]
        done = NOW + timedelta(seconds=3)
        outbox.process(session, "recorder", now_utc=NOW, clock=lambda: done)
        line = outbox.timeline(session, published.event_id, "recorder")
        assert line["status"] == "processed"
        assert line["processed_at_utc"] == done.isoformat()
        assert line["notified_at_utc"] == done.isoformat()
        assert line["latencies_seconds"] == {
            "publication_to_ingestion": 1200.0,
            "ingestion_to_processing": 3.0,
            "processing_to_notification": 0.0,
        }
        assert line["issues"] == []
        assert outbox.timeline(session, "mev-missing-r1", "recorder") is None


def test_an_event_re_evaluates_only_the_evaluators_that_read_its_key(engine) -> None:
    later = NOW + timedelta(minutes=1)
    with Session(engine) as session:
        _seed_and_evaluate(session)
        by_evaluator = {
            row.evaluator for row in session.query(OpportunityRecord.evaluator).all()
        }
        assert {"hedge_gap", "sell_down"} <= by_evaluator
        # A move of the TTF day-ahead mark: only the sell-down opportunities read it.
        outbox.publish(
            session,
            _event(
                subject="hub:TTF:2026-11-18",
                event_type="mark.changed",
                source_id="firm-marks",
                ingested_at_utc=later,
                published_at_utc=None,
            ),
        )
        # A key nothing depends on is delivered and changes nothing.
        outbox.publish(
            session,
            _event(subject="hub:PEG:2031-01", ingested_at_utc=later, published_at_utc=None),
        )
        session.commit()
        summary = outbox.process(session, "opportunities", now_utc=later)
        session.commit()
        result = summary["result"]
        assert summary["processed"] == 2
        assert result["dependency_keys"] == ["hub:PEG:2031-01", "hub:TTF:2026-11-18"]
        assert result["evaluators"] == ["sell_down"]
        assert result["affected_opportunities"] >= 1
        run = session.get(OpportunityEvaluationRecord, result["evaluation_id"])
        assert run.trigger == "outbox" and run.triggered_by == "market-event-outbox"
        assert set(run.evaluators_json) == {"sell_down"}
        # Hedge-gap records were not touched by the targeted run.
        untouched = (
            session.query(OpportunityRecord)
            .filter(OpportunityRecord.evaluator == "hedge_gap")
            .all()
        )
        assert untouched and all(row.evaluation_id != run.evaluation_id for row in untouched)

        # A contract change re-evaluates hedge gap only.
        contract_key = "contract:demo-haldor-24"
        outbox.publish(
            session,
            MarketEvent(
                source_id="desk",
                event_type="contract.changed",
                subject_key=contract_key,
                ingested_at_utc=later + timedelta(minutes=1),
                payload={"revision": 2},
            ),
        )
        second = outbox.process(session, "opportunities", now_utc=later + timedelta(minutes=1))
        assert second["result"]["evaluators"] == ["hedge_gap"]


def test_events_without_keys_are_kept_but_not_sent_to_the_opportunity_consumer(engine) -> None:
    with Session(engine) as session:
        session.add(
            IngestionRunRecord(
                run_id="run-eex-1", source_name="src-eex", source_id="src-eex",
                status="SUCCEEDED", started_at_utc=NOW, finished_at_utc=NOW,
                rows_inserted=12,
            )
        )
        session.add(
            IngestionRunRecord(
                run_id="run-eex-0", source_name="src-eex", source_id="src-eex",
                status="SUCCEEDED", started_at_utc=NOW, rows_inserted=0,
            )
        )
        session.flush()
        events = outbox.ingestion_events(
            session,
            [
                {"run_id": "run-eex-1", "status": "SUCCEEDED"},
                {"run_id": "run-eex-0", "status": "SUCCEEDED"},
                {"run_id": "run-x", "status": "FAILED"},
            ],
            now_utc=NOW,
        )
        assert [(e.subject_key, e.input_class, e.correlation_id) for e in events] == [
            ("ingestion:src-eex", "prices", "run-eex-1")
        ]
        published = outbox.publish(session, events[0])
        assert published.deliveries == ()
        assert outbox.publish(session, events[0]).kind is PublishKind.DUPLICATE


def test_the_scheduler_hook_records_and_drains_and_never_fails_the_loop(
    engine, monkeypatch
) -> None:
    spec = importlib.util.spec_from_file_location(
        "run_dataops_scheduler_m4", ROOT / "scripts" / "ops" / "run_dataops_scheduler.py"
    )
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    factory = sessionmaker(engine)
    with factory() as session:
        session.add(
            IngestionRunRecord(
                run_id="tick-1", source_name="src-eex", source_id="src-eex",
                status="SUCCEEDED", started_at_utc=NOW, rows_inserted=3,
            )
        )
        outbox.publish(session, _event())
        session.commit()
    tick = script.deliver_market_events(
        factory, [{"run_id": "tick-1", "status": "SUCCEEDED"}], now_utc=NOW
    )
    assert tick == {"status": "ok", "published": ["new"], "processed": 1, "failed": 0, "dead": 0}

    def boom(*_a, **_k):
        raise RuntimeError("store away")

    monkeypatch.setattr(outbox, "ingestion_events", boom)
    assert script.deliver_market_events(factory, [], now_utc=NOW) == {
        "status": "failed",
        "error_type": "RuntimeError",
    }


def test_a_firm_mark_write_publishes_one_event_per_cell(engine) -> None:
    with Session(engine) as session:
        row = identity_repository.create_identity_principal(
            session, name="m4-trader", display_name="m", role="ANALYST", data_scopes=["*"]
        )
        _key, bearer = identity_repository.create_identity_api_key(session, row.principal_id)
        session.commit()
    client = TestClient(create_app(Settings(api_profile="release")))
    headers = {"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer}
    body = {
        "marks": [
            {"hub": "TTF", "period": "2027-01", "value": 30.0, "unit": "EUR/MWh"},
            {"hub": "NBP", "period": "2027-01", "value": 80.0, "unit": "GBp/th"},
        ]
    }
    assert client.put("/api/market/firm-marks", json=body, headers=headers).status_code == 200
    with Session(engine) as session:
        events = session.query(MarketEventRecord).order_by(MarketEventRecord.subject_key).all()
        assert [(e.event_type, e.subject_key, e.dependency_keys) for e in events] == [
            ("mark.changed", "hub:NBP:2027-01", ["hub:NBP:2027-01"]),
            ("mark.changed", "hub:TTF:2027-01", ["hub:TTF:2027-01"]),
        ]
        # The outbox carries a digest of the mark, never its value.
        assert all("value" not in e.payload_json for e in events)
        assert all(str(30.0) not in str(e.payload_json) for e in events)
    # The same marks again are the same facts: nothing new is published.
    assert client.put("/api/market/firm-marks", json=body, headers=headers).status_code == 200
    with Session(engine) as session:
        assert session.query(MarketEventRecord).count() == 2
