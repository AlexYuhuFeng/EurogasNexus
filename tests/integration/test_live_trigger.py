"""M7 (a): the listen worker is the default trigger; the drain has no event cap; the debounce
is one minute.

See docs/engineering/Commercial-Intelligence-V3/15_LIVE_PIPELINE_AND_LATENCY_BUDGET.md.
"""

from __future__ import annotations

import importlib.util
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from eurogas_nexus.application import market_events as outbox
from eurogas_nexus.application.opportunities import schedule
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import MarketEventDeliveryRecord, OpportunityEvaluationRecord
from eurogas_nexus.domain.market_events import MarketEvent

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 17, 9, 42, tzinfo=UTC)


@pytest.fixture()
def engine(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'live.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return engine


class Counter:
    name = "live-counter"

    def __init__(self) -> None:
        self.seen = 0

    def accepts(self, record) -> bool:
        return record.source_id == "src-live-test"

    def handle(self, session, records, *, now_utc):
        self.seen += len(records)
        return {"seen": len(records)}


@pytest.fixture()
def counter():
    item = Counter()
    outbox.register_consumer(item)
    yield item
    outbox.unregister_consumer(item.name)


def _publish(session, count: int) -> None:
    for index in range(count):
        outbox.publish(
            session,
            MarketEvent(
                source_id="src-live-test",
                event_type="price.updated",
                subject_key=f"hub:TTF:2027-{index:04d}",
                ingested_at_utc=NOW,
                market_time_utc=NOW - timedelta(hours=1),
                published_at_utc=NOW - timedelta(minutes=1),
                payload={"settlement": str(index)},
            ),
        )
    session.commit()


def _waiting(session, name: str) -> int:
    return (
        session.query(MarketEventDeliveryRecord)
        .filter(MarketEventDeliveryRecord.consumer == name)
        .filter(MarketEventDeliveryRecord.status == "pending")
        .count()
    )


def test_a_drain_takes_the_whole_backlog_not_ten_batches(engine, counter) -> None:
    factory = sessionmaker(engine)
    with factory() as session:
        _publish(session, 120)
    # Ten batches of ten would have stopped at 100 before M7.
    outbox.drain(factory, now_utc=NOW, limit=10)
    assert counter.seen == 120
    with factory() as session:
        assert _waiting(session, counter.name) == 0


def test_a_drain_hands_back_when_its_time_is_spent_and_a_count_cap_is_still_possible(
    engine, counter
) -> None:
    factory = sessionmaker(engine)
    with factory() as session:
        _publish(session, 50)
    ticks = iter(range(0, 1000, 30))
    summaries = outbox.drain(
        factory, now_utc=NOW, limit=10, max_seconds=45.0, clock=lambda: next(ticks)
    )
    assert {"consumer": counter.name, "status": "budget_spent"} in summaries
    assert counter.seen == 20  # started at 0, one batch at 30 s, stopped at 60 s
    with factory() as session:
        assert _waiting(session, counter.name) == 30
    outbox.drain(factory, now_utc=NOW, limit=10, max_batches=1, max_seconds=None)
    assert counter.seen == 30


def test_a_mark_set_back_to_an_earlier_value_is_published_again(engine) -> None:
    """Found by the M7 latency measurement: without a publication time, 44 -> 40 -> 44 was
    refused as a replay, so the third save waited for the full sweep instead of the outbox."""

    from eurogas_nexus.domain.valuation.firm_marks import validate_firm_mark

    factory = sessionmaker(engine)
    published = []
    with factory() as session:
        for offset, value in enumerate((44, 40, 44)):
            entry = validate_firm_mark("TTF", "2026-11-18", value, "EUR/MWh")
            (result,) = outbox.publish_firm_marks(
                session, [entry], actor="t", now_utc=NOW + timedelta(seconds=offset)
            )
            published.append((result.kind.value, result.revision))
        session.commit()
    assert published == [("new", 1), ("revision", 2), ("revision", 3)]


def test_the_debounce_is_one_minute() -> None:
    assert schedule.DEBOUNCE == timedelta(seconds=60)
    assert schedule.due(NOW - timedelta(seconds=59), NOW) is False
    assert schedule.due(NOW - timedelta(seconds=60), NOW) is True


def test_the_evaluation_lock_is_granted_off_postgresql(engine) -> None:
    with Session(engine) as session:
        assert schedule.evaluation_lock(session, wait=False) is True
        assert schedule.evaluation_lock(session, wait=True) is True


def test_the_listen_worker_runs_the_due_evaluation(engine) -> None:
    spec = importlib.util.spec_from_file_location(
        "market_events_cli_m7", ROOT / "scripts" / "ops" / "market_events.py"
    )
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    factory = sessionmaker(engine)
    with factory() as session:
        schedule.note_input_changed(session, "prices", reason="test", at_utc=NOW)
        session.commit()
    first = script._evaluate_due(factory)
    assert first["status"] == "ran" and first["classes"] == ["prices"]
    assert script._evaluate_due(factory) == {
        "status": "idle",
        "classes": [],
        "evaluation_id": None,
    }
    with factory() as session:
        assert session.query(OpportunityEvaluationRecord).one().trigger == "schedule"


def test_the_listen_worker_is_deployed_with_the_scheduler() -> None:
    compose = yaml.safe_load((ROOT / "deploy" / "runtime" / "compose.yaml").read_text())
    worker = compose["services"]["market-events-worker"]
    scheduler = compose["services"]["public-ingestion-worker"]
    assert worker["command"][1:3] == ["scripts/ops/market_events.py", "listen"]
    assert worker["profiles"] == scheduler["profiles"]
    assert worker["restart"] == "unless-stopped"
    dockerfile = (ROOT / "deploy" / "runtime" / "Dockerfile.api").read_text()
    assert "scripts/ops/market_events.py" in dockerfile


@pytest.mark.skipif(
    not os.environ.get("RUNTIME_STORE_DATABASE_URL", "").startswith("postgresql"),
    reason="needs PostgreSQL (scripts/ci/run_postgres_ci.sh)",
)
def test_a_second_sweep_is_told_busy_while_one_holds_the_lock_on_postgres() -> None:
    pg = create_engine(os.environ["RUNTIME_STORE_DATABASE_URL"], future=True)
    holder, other = Session(pg), Session(pg)
    try:
        schedule.note_input_changed(other, "prices", reason="m7 lock test", at_utc=NOW)
        other.commit()
        assert schedule.evaluation_lock(holder, wait=False) is True
        assert schedule.run_due(other, now_utc=NOW, runner=lambda *a, **k: {}) == {
            "status": "busy"
        }
        other.rollback()
        holder.rollback()  # released at the end of the holder's transaction
        assert schedule.evaluation_lock(other, wait=False) is True
    finally:
        other.rollback()
        from eurogas_nexus.db.models import OpportunityPendingInputRecord

        other.query(OpportunityPendingInputRecord).delete()
        other.commit()
        holder.close()
        other.close()
        pg.dispose()
