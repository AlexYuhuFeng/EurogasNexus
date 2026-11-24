"""LNG-2 on PostgreSQL: a late cargo reaches each role through the outbox listen worker.

The import commits the new ETA with its ``cargo.changed`` event; PostgreSQL notifies the
listening worker (``scripts/ops/market_events.py listen``, run as its own process); the worker
drains the ``cargo_roles`` consumer, which queues one notification per role. The test measures
the time from the import's commit to every role's notification queued, and to each channel
having received it (criterion LNG2-5, evidence in 09_EVIDENCE_AND_TEST_PLAN.md).

Run via ``scripts/ci/run_postgres_ci.sh`` (``RUNTIME_STORE_DATABASE_URL`` set, migrated to head).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application import market_events
from eurogas_nexus.application.lng_cargo_alerts import CONSUMER_NAME
from eurogas_nexus.application.lng_in_transit import send_out_plan
from eurogas_nexus.application.lng_positions_import import store_lng_rows
from eurogas_nexus.application.market_event_capture import capture_desk
from eurogas_nexus.application.notifications import dispatch
from eurogas_nexus.db.models import (
    LngCargoHedgeRecord,
    LngCargoRecord,
    LngTerminalTermsRecord,
    MarketEventRecord,
    MonitoringAlertRecord,
    NotificationChannelRecord,
    NotificationDeliveryRecord,
    NotificationOutboxRecord,
    RegasSlotRecord,
    TraderMandateRecord,
    TradingBookRecord,
)
from eurogas_nexus.ingestion.lng_positions import parse_lng_cargoes

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUNTIME_STORE_DATABASE_URL", "").startswith("postgresql"),
    reason="RUNTIME_STORE_DATABASE_URL not PostgreSQL; run via scripts/ci/run_postgres_ci.sh",
)

ROOT = Path(__file__).resolve().parents[2]
ROLES = ("trader", "scheduler", "risk", "desk_head")
CATEGORIES = {"trader": "cargo", "scheduler": "nomination", "risk": "limits",
              "desk_head": "desk_head"}


def _eta(now: datetime) -> datetime:
    """Three days before a month end, so a four-day delay moves gas across it."""

    first = datetime(now.year + now.month // 12, now.month % 12 + 1, 1, 9, tzinfo=UTC)
    eta = first - timedelta(days=3)
    if eta < now + timedelta(days=1):
        first = datetime(first.year + first.month // 12, first.month % 12 + 1, 1, 9, tzinfo=UTC)
        eta = first - timedelta(days=3)
    return eta


@pytest.fixture()
def desk():
    engine = create_engine(os.environ["RUNTIME_STORE_DATABASE_URL"], future=True)
    tag = uuid4().hex[:8]
    cargo, book, terminal = f"PG-{tag}", f"lng-pg-{tag}", f"Gate {tag}"
    now = datetime.now(UTC).replace(microsecond=0)
    eta = _eta(now)
    with Session(engine) as session:
        session.add(TradingBookRecord(
            book_id=book, name="LNG PG", legal_entity="Demo Energy BV", region="NWE",
            business="LNG", base_currency="EUR", active=True, updated_by="t", updated_at_utc=now,
        ))
        session.add(LngTerminalTermsRecord(
            terminal_id=f"gate-{tag}", name=terminal, hub="TTF", regas_tariff_per_mwh=1.0,
            fuel_retention_pct=1.0, source_note="test terms", updated_by="t", updated_at_utc=now,
        ))
        session.add(LngCargoRecord(
            cargo_id=cargo, vessel_name="Aurora", status="laden", load_port="Sabine Pass",
            departed_at_utc=now - timedelta(days=12), destination_terminal=terminal,
            eta_utc=eta, energy_gwh=1_000.0, book_id=book, source_system="ETRM",
            source_reference="etrm:cargo", updated_at_utc=now - timedelta(days=1),
            eta_source="ETRM", eta_recorded_at_utc=now - timedelta(days=1),
            eta_basis="schedule", eta_confidence="medium",
        ))
        session.add(RegasSlotRecord(
            slot_id=f"slot-{tag}", terminal_name=terminal,
            window_start_utc=eta - timedelta(days=1), window_end_utc=eta + timedelta(days=9),
            send_out_gwh_d=100.0, cargo_id=cargo, book_id=book, source_system="ETRM",
            source_reference="etrm:slot", updated_at_utc=now - timedelta(days=1),
        ))
        session.add(TraderMandateRecord(
            mandate_id=f"m-{tag}", trader="lng.trader", display_name="LNG desk",
            book_ids=[book], hubs=["TTF"], max_net_mwh_per_month=300_000,
            physical_allowed=True, financial_allowed=True, updated_by="t", updated_at_utc=now,
        ))
        for role in ROLES:
            session.add(NotificationChannelRecord(
                channel_id=f"ch-{role}-{tag}", name=f"{role}-{tag}", kind="email",
                recipients=f"{role}@desk.example", categories=[CATEGORIES[role]],
                min_severity="info", enabled=True, updated_by="t", updated_at_utc=now,
            ))
        session.flush()
        plan, _slot = send_out_plan(session, cargo, now=now)
        for cover in plan.months:
            session.add(LngCargoHedgeRecord(
                link_id=uuid4().hex, cargo_id=cargo, hub=cover.hub, delivery_month=cover.month,
                mwh=-round(cover.physical_mwh), reference=None,
                created_at_utc=now - timedelta(hours=20), created_by="lng.trader",
            ))
        capture_desk(session, cargo_ids=[cargo], now_utc=now - timedelta(minutes=5))
        session.commit()
        # Drain this cargo's first recording so the worker sees only the change.
        summary = market_events.process(session, CONSUMER_NAME, now_utc=now)
        session.commit()
        assert summary["failed"] == 0, summary
    yield engine, tag, cargo, eta
    with Session(engine) as session:
        session.query(NotificationDeliveryRecord).filter(
            NotificationDeliveryRecord.channel_id.like(f"%-{tag}")
        ).delete(synchronize_session=False)
        session.query(NotificationOutboxRecord).filter(
            NotificationOutboxRecord.dedupe_key.like(f"cargo:{cargo}:%")
        ).delete(synchronize_session=False)
        session.query(MonitoringAlertRecord).filter(
            MonitoringAlertRecord.entity_id == cargo
        ).delete(synchronize_session=False)
        session.query(MarketEventRecord).filter(
            MarketEventRecord.subject_key.like(f"%{cargo}%")
        ).delete(synchronize_session=False)
        for model, column, value in (
            (LngCargoHedgeRecord, LngCargoHedgeRecord.cargo_id, cargo),
            (RegasSlotRecord, RegasSlotRecord.cargo_id, cargo),
            (LngCargoRecord, LngCargoRecord.cargo_id, cargo),
            (TraderMandateRecord, TraderMandateRecord.mandate_id, f"m-{tag}"),
            (LngTerminalTermsRecord, LngTerminalTermsRecord.terminal_id, f"gate-{tag}"),
            (TradingBookRecord, TradingBookRecord.book_id, f"lng-pg-{tag}"),
        ):
            session.query(model).filter(column == value).delete(synchronize_session=False)
        session.query(NotificationChannelRecord).filter(
            NotificationChannelRecord.channel_id.like(f"%-{tag}")
        ).delete(synchronize_session=False)
        session.commit()
    engine.dispose()


def _worker() -> subprocess.Popen:
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    return subprocess.Popen(
        [sys.executable, str(ROOT / "scripts/ops/market_events.py"), "listen",
         "--interval", "600", "--iterations", "3", "--poll-seconds", "0.05", "--no-evaluate"],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )


def _import_eta(engine, cargo: str, eta: datetime, basis: str, confidence: str) -> float:
    """Commit an import of one ETA; the moment of the commit."""

    now = datetime.now(UTC)
    text = (
        "cargo_id,vessel_name,status,load_port,eta,eta_basis,eta_confidence\n"
        f"{cargo},Aurora,laden,Sabine Pass,{eta.isoformat()},{basis},{confidence}\n"
    )
    rows = parse_lng_cargoes(text, source_system="KPLER", source_reference="KPLER:f", now_utc=now)
    with Session(engine) as session:
        result = store_lng_rows(session, "cargo", rows, now_utc=now)
        session.commit()
        committed = time.perf_counter()
    assert result["events"]["published"] == {"cargo.changed": 1}
    return committed


def _queued(engine, cargo: str, *, withdrawn: bool) -> float:
    """The moment every role's notification (or withdrawal) is in the outbox."""

    deadline = time.perf_counter() + 30
    with Session(engine) as session:
        while time.perf_counter() < deadline:
            session.expire_all()
            categories = {
                row.category for row in session.query(NotificationOutboxRecord).filter(
                    NotificationOutboxRecord.dedupe_key.like(f"cargo:{cargo}:%")
                )
                if (":withdrawn:" in row.dedupe_key) == withdrawn
            }
            if categories >= set(CATEGORIES.values()):
                return time.perf_counter()
            time.sleep(0.02)
    raise AssertionError("no notification for every role within 30 s")


def _send(engine) -> dict[str, list]:
    sent: dict[str, list] = {}
    with Session(engine) as session:
        dispatch(session, now=datetime.now(UTC), senders={
            "email": lambda channel, message: sent.setdefault(channel.name, []).append(message)
        })
        session.commit()
    return sent


def test_a_late_cargo_reaches_each_role_through_the_listen_worker(desk) -> None:
    engine, tag, cargo, eta = desk
    worker = _worker()
    try:
        # The worker's first pass drains at start; after it, it waits on LISTEN.
        first = json.loads(worker.stdout.readline() or "{}")
        assert first.get("status") == "ok", worker.stderr.read()

        # The vessel feed reports the cargo four days late: every role is told.
        committed = _import_eta(engine, cargo, eta + timedelta(days=4), "AIS", "low")
        queued_at = _queued(engine, cargo, withdrawn=False)
        sent = _send(engine)
        delivered_at = time.perf_counter()
        report = json.loads(worker.stdout.readline() or "{}")
        assert report.get("woken") is True  # drained on the commit's notice, not the timer
        assert report["batches"][0]["consumer"] == CONSUMER_NAME
        assert {name: len(items) for name, items in sent.items()} == {
            f"{role}-{tag}": 1 for role in ROLES
        }
        assert sent[f"trader-{tag}"][0].title.startswith("Hedges no longer match Aurora")

        # The master corrects the ETA back to the plan: every message is withdrawn. The worker
        # has now loaded the cargo modules, so this is the warm figure.
        corrected = _import_eta(engine, cargo, eta, "master_notice", "high")
        withdrawn_at = _queued(engine, cargo, withdrawn=True)
        withdrawn = _send(engine)
        assert json.loads(worker.stdout.readline() or "{}").get("woken") is True
        assert {name: [m.title.split(":")[0] for m in items]
                for name, items in withdrawn.items()} == {
            f"{role}-{tag}": ["Withdrawn"] for role in ROLES
        }

        cold, delivered = queued_at - committed, delivered_at - committed
        warm = withdrawn_at - corrected
        print(f"\nLNG-2 latency on PostgreSQL: commit to every role queued {cold * 1000:.0f} ms "
              f"(first change after the worker starts), sent {delivered * 1000:.0f} ms; "
              f"next change to every withdrawal queued {warm * 1000:.0f} ms")
        assert cold < 5.0 and warm < 5.0
    finally:
        worker.kill()
        worker.wait(timeout=10)
