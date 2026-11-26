"""Demo housekeeping on real PostgreSQL: seed, old rows, run, verify, keep business data.

Skipped unless ``EUROGAS_NEXUS_TEST_POSTGRES_URL`` is set; ``scripts/ci/run_postgres_ci.sh``
runs it. It proves the PostgreSQL-only parts (the ctid batched deletes, VACUUM (ANALYZE), the
table/database sizes) and that the seeded demo desk survives while old rows go and the audit
chain still verifies.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import event, func, text
from sqlalchemy.engine import make_url

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.db.audit_chain import verify_chain
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    AuditEventRecord,
    FlowObservationRecord,
    IdentityPrincipalRecord,
    IngestionRunRecord,
    JobRecord,
    LicensedDataUseRecord,
    MarketEventDeliveryRecord,
    MarketEventRecord,
    MarketQuoteRecord,
    MarketTradeRecord,
    MonitoringAlertRecord,
    NotificationOutboxRecord,
    ObservationTemporalMetadataRecord,
    RawPayloadArchiveRecord,
    RawPayloadContentRecord,
    TradingBookRecord,
    UpstreamResourceContractRecord,
    UserSessionRecord,
)
from eurogas_nexus.db.repositories.audit import record_audit_event
from eurogas_nexus.db.session import get_engine, get_session_factory

_POSTGRES_URL = os.environ.get("EUROGAS_NEXUS_TEST_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(
    not _POSTGRES_URL.startswith("postgresql"),
    reason="Set EUROGAS_NEXUS_TEST_POSTGRES_URL: the test uses a disposable PostgreSQL schema.",
)

ROOT = Path(__file__).resolve().parents[2]
HOUSEKEEPING = ROOT / "scripts" / "demo" / "demo_housekeeping.py"
SEED = ROOT / "scripts" / "demo" / "seed_demo_desk.py"
NOW = datetime(2026, 11, 26, 12, tzinfo=UTC)
OLD = NOW - timedelta(days=400)


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _high_disk(_path: str):
    return SimpleNamespace(total=100 * 1024**3, used=10 * 1024**3, free=90 * 1024**3)


@contextmanager
def _database():
    url = make_url(_POSTGRES_URL)
    engine = get_engine(url.render_as_string(hide_password=False), statement_timeout=None)
    schema = f"demohousekeeping_{uuid4().hex}"

    @event.listens_for(engine, "connect")
    def _search_path(dbapi_connection, _record):  # noqa: ANN001 - DBAPI callback
        cursor = dbapi_connection.cursor()
        cursor.execute(f'SET search_path TO "{schema}"')
        cursor.close()

    try:
        with engine.connect() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            connection.commit()
        Base.metadata.create_all(engine)
        yield get_session_factory(engine=engine)
    finally:
        with engine.connect() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
            connection.commit()
        engine.dispose()


def _quote(quote_id: str, at: datetime, source: str = "DEMO_Sim") -> MarketQuoteRecord:
    return MarketQuoteRecord(
        quote_id=quote_id, source_system=source, venue="Demo", instrument_id="TTF:DA",
        hub="TTF", product="DA", delivery_start_utc=at,
        delivery_end_utc=at + timedelta(days=1), bid_price=30.0, ask_price=30.1,
        currency="EUR", unit="EUR/MWh", observed_at_utc=at, received_at_utc=at,
        source_reference="feed:simulated-exchange", freshness="live", quality_score=1.0,
        simulated=True,
    )


def _flow(observation_id: str, at: datetime, source: str) -> FlowObservationRecord:
    return FlowObservationRecord(
        observation_id=observation_id, point_id="p1", point_name="Point 1", direction="in",
        kind="actual", flow_mcm_d=1.0, period_start_utc=at,
        period_end_utc=at + timedelta(hours=1), observed_at_utc=at,
        source_system=source, source_reference="test", freshness="daily", research_only=False,
    )


def _alert(alert_id: str, *, status: str, at: datetime) -> MonitoringAlertRecord:
    return MonitoringAlertRecord(
        alert_id=alert_id, fingerprint=f"fp-{alert_id}", category="operations",
        alert_type="test", severity="warning", status=status, title_en="t",
        title_zh_cn="标题", message_en="m", message_zh_cn="消息", entity_type="desk",
        entity_id="demo", event_time_utc=at, detected_at_utc=at, updated_at_utc=at,
        occurrence_count=1, evidence_snapshot={}, source_refs=[], warnings=[],
        llm_provider_id="DEEPSEEK", llm_status="pending", simulated=False,
        human_review_required=False,
    )


def _job(job_id: str, *, status: str, at: datetime) -> JobRecord:
    return JobRecord(
        job_id=job_id, kind="ingestion", status=status, principal="tester",
        created_at_utc=at, started_at_utc=at,
        finished_at_utc=at + timedelta(minutes=1) if status == "SUCCEEDED" else None,
    )


def test_housekeeping_keeps_the_seed_and_removes_old_rows_on_postgresql() -> None:
    housekeeping = _module(HOUSEKEEPING, "demo_housekeeping_pg")
    seed = _module(SEED, "demo_seed_housekeeping_pg")

    with _database() as factory:
        with factory() as session:
            seed.seed(session, NOW, history_days=20)
            session.commit()
            contracts = session.query(UpstreamResourceContractRecord).count()
            books = session.query(TradingBookRecord).count()
            assert contracts > 0 and books > 0

            # A real old audit row: housekeeping must never touch the audit trail.
            old_audit = record_audit_event(
                session, event_type="governance.test", principal="tester",
                action="test.old", resource="demo", detail="old", now_utc=OLD,
            )
            session.commit()
            old_audit_id = old_audit.event_id

            old_event = MarketEventRecord(
                event_id="pg-evt-old", event_key="k-old", revision=1, content_hash="h",
                source_id="src", event_type="price", subject_key="s", priority=1,
                ingested_at_utc=OLD,
            )
            new_event = MarketEventRecord(
                event_id="pg-evt-new", event_key="k-new", revision=1, content_hash="h",
                source_id="src", event_type="price", subject_key="s", priority=1,
                ingested_at_utc=NOW - timedelta(days=1),
            )
            session.add_all(
                [
                    _quote("pg-old-sim", NOW - timedelta(days=10)),
                    _quote("pg-new-sim", NOW - timedelta(hours=1)),
                    MarketTradeRecord(
                        trade_id="pg-old-print", source_system="DEMO_Sim", venue="Demo",
                        instrument_id="TTF:DA", hub="TTF", product="DA",
                        delivery_start_utc=NOW - timedelta(days=10),
                        delivery_end_utc=NOW - timedelta(days=9), price=30.0,
                        quantity_mwh=1.0, currency="EUR", trade_type="screen",
                        traded_at_utc=NOW - timedelta(days=10),
                        received_at_utc=NOW - timedelta(days=10), simulated=True,
                    ),
                    _flow("pg-old-real", NOW - timedelta(days=300), "ENTSOG"),
                    _flow("pg-old-sim-history", NOW - timedelta(days=300), "DEMO_Sim"),
                    IngestionRunRecord(
                        run_id="pg-old-finished", source_name="ENTSOG",
                        source_id="src-entsog", status="succeeded", started_at_utc=OLD,
                    ),
                    IngestionRunRecord(
                        run_id="pg-old-running", source_name="ENTSOG",
                        source_id="src-entsog", status="RUNNING", started_at_utc=OLD,
                    ),
                    _alert("pg-resolved-old", status="resolved", at=OLD),
                    _alert("pg-open-old", status="open", at=OLD),
                    _job("pg-old-job", status="SUCCEEDED", at=OLD),
                    _job("pg-active-job", status="RUNNING", at=OLD),
                    IdentityPrincipalRecord(
                        principal_id="housekeeping-test", principal_type="USER",
                        name="housekeeping-test", display_name="Housekeeping test",
                        role="ADMIN", status="active", data_scopes=["*"],
                        created_at_utc=OLD, updated_at_utc=OLD,
                    ),
                    UserSessionRecord(
                        session_id="pg-expired", principal_id="housekeeping-test",
                        session_token_hash="h1", created_at_utc=OLD,
                        last_seen_at_utc=OLD, expires_at_utc=OLD + timedelta(hours=1),
                    ),
                    NotificationOutboxRecord(
                        notification_id="pg-sent", category="limits", severity="warning",
                        title="t", body="b", dedupe_key="pg-sent",
                        created_at_utc=OLD, dispatched_at_utc=OLD,
                    ),
                    RawPayloadContentRecord(
                        payload_sha256="pg-old-sha", byte_size=10, compression="gzip",
                        payload_compressed=b"x", stored_in="inline",
                        first_received_at_utc=OLD, last_received_at_utc=OLD,
                    ),
                    RawPayloadContentRecord(
                        payload_sha256="pg-new-sha", byte_size=10, compression="gzip",
                        payload_compressed=b"x", stored_in="inline",
                        first_received_at_utc=NOW - timedelta(days=1),
                        last_received_at_utc=NOW - timedelta(days=1),
                    ),
                    RawPayloadArchiveRecord(
                        archive_id="pg-old-receipt", source_system="ENTSOG",
                        dataset="flows", source_reference="rid", payload_text="<page/>",
                        payload_sha256="pg-old-sha", record_count=1, received_at_utc=OLD,
                        research_only=False, human_review_required=False,
                    ),
                    LicensedDataUseRecord(
                        usage_day=date(2026, 1, 1), principal_id="tester",
                        source_family="EEX", surface="/api/prices", reads=1,
                        first_at_utc=OLD, last_at_utc=OLD,
                    ),
                    ObservationTemporalMetadataRecord(
                        observation_id="pg-old-meta",
                        observation_table="flow_observations", observed_at_utc=OLD,
                        available_at_utc=OLD, ingested_at_utc=OLD,
                        temporal_integrity="ok", provenance={},
                    ),
                    old_event,
                    new_event,
                ]
            )
            session.flush()
            session.add_all(
                [
                    MarketEventDeliveryRecord(
                        consumer="opportunities", event_seq=old_event.seq,
                        status="processed", attempts=1, available_at_utc=OLD,
                        processed_at_utc=OLD,
                    ),
                    MarketEventDeliveryRecord(
                        consumer="opportunities", event_seq=new_event.seq,
                        status="pending", attempts=0,
                        available_at_utc=NOW - timedelta(days=1),
                    ),
                ]
            )
            session.commit()

        report = housekeeping.run_housekeeping(
            factory, now_utc=NOW, environ={}, disk_reader=_high_disk
        )
        assert report["status"] == "ok", report["errors"]
        assert report["audit_event_id"]
        assert report["sizes"]["before"]["database_bytes"] > 0
        assert report["sizes"]["after"]["database_bytes"] > 0
        assert report["vacuumed"]
        print("demo housekeeping sizes before/after:", json.dumps(report["sizes"], default=str))

        with factory() as session:
            # The seeded business desk is untouched.
            assert session.query(UpstreamResourceContractRecord).count() == contracts
            assert session.query(TradingBookRecord).count() == books

            # Old simulated high-frequency rows go; recent ones stay.
            assert session.get(MarketQuoteRecord, "pg-old-sim") is None
            assert session.get(MarketQuoteRecord, "pg-new-sim") is not None
            assert session.get(MarketTradeRecord, "pg-old-print") is None

            # Old public data goes; old simulated history is what the screens read and stays.
            assert session.get(FlowObservationRecord, "pg-old-real") is None
            assert session.get(FlowObservationRecord, "pg-old-sim-history") is not None

            assert session.get(IngestionRunRecord, "pg-old-finished") is None
            assert session.get(IngestionRunRecord, "pg-old-running") is not None
            assert session.get(MonitoringAlertRecord, "pg-resolved-old") is None
            assert session.get(MonitoringAlertRecord, "pg-open-old") is not None
            assert session.get(JobRecord, "pg-old-job") is None
            assert session.get(JobRecord, "pg-active-job") is not None
            assert session.get(UserSessionRecord, "pg-expired") is None
            assert session.get(NotificationOutboxRecord, "pg-sent") is None
            assert session.get(RawPayloadContentRecord, "pg-old-sha") is None
            assert session.get(RawPayloadContentRecord, "pg-new-sha") is not None
            receipt = session.get(RawPayloadArchiveRecord, "pg-old-receipt")
            assert receipt is not None and receipt.payload_text is None
            assert (
                session.query(LicensedDataUseRecord)
                .filter(LicensedDataUseRecord.usage_day == date(2026, 1, 1))
                .count()
                == 0
            )
            assert session.get(ObservationTemporalMetadataRecord, "pg-old-meta") is None
            assert session.query(MarketEventRecord).filter(
                MarketEventRecord.event_id == "pg-evt-old"
            ).count() == 0
            assert session.query(MarketEventRecord).filter(
                MarketEventRecord.event_id == "pg-evt-new"
            ).count() == 1

            # The audit trail is left alone and the chain still verifies.
            assert session.get(AuditEventRecord, old_audit_id) is not None
            result = verify_chain(session)
            assert result["ok"] is True, result
            assert result["unsealed_rows"] == 0
            assert (
                session.query(AuditEventRecord)
                .filter(AuditEventRecord.action == "demo.housekeeping")
                .count()
                == 1
            )
            assert session.query(func.count()).select_from(MarketQuoteRecord).scalar() >= 0
