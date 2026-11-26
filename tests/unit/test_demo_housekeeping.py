"""Demo housekeeping: the rules, the profile refusal, the disk guard and dry run.

The product's retention job archives before it removes and keeps seven-year floors, so on the
demo (no object store) it removes nothing. ``scripts/demo/demo_housekeeping.py`` is the demo's
own bounded clean-up. These tests run the shared rules on SQLite; the PostgreSQL-only batch
path and VACUUM are covered by ``tests/integration/test_demo_housekeeping_postgres.py``.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.db.audit_chain import verify_chain
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    AuditEventRecord,
    FlowObservationRecord,
    GasDayNominationEventRecord,
    IngestionRunRecord,
    JobRecord,
    LicensedDataUseRecord,
    MarketEventDeliveryRecord,
    MarketEventRecord,
    MarketQuoteRecord,
    MarketTradeRecord,
    MonitoringAlertReaderStateRecord,
    MonitoringAlertRecord,
    NotificationOutboxRecord,
    ObservationTemporalMetadataRecord,
    OidcAuthorizationStateRecord,
    RawPayloadArchiveRecord,
    RawPayloadContentRecord,
    ScreenOrderObservationRecord,
    TradingBookRecord,
    UserSessionRecord,
)
from eurogas_nexus.db.repositories.audit import record_audit_event

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "demo" / "demo_housekeeping.py"
FEED_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "demo" / "exchange_feed.py"
NOW = datetime(2026, 11, 26, 12, tzinfo=UTC)


def _load():
    spec = importlib.util.spec_from_file_location("demo_housekeeping", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine)
    engine.dispose()


def _high_disk(_path: str):
    return SimpleNamespace(total=100 * 1024**3, used=10 * 1024**3, free=90 * 1024**3)


def test_the_simulated_horizon_matches_the_feeds_own_retention() -> None:
    hk = _load()
    spec = importlib.util.spec_from_file_location("demo_housekeeping_feed_test", FEED_SCRIPT)
    feed = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = feed
    spec.loader.exec_module(feed)
    assert hk.FEED_RETENTION_HOURS == int(feed.RETENTION.total_seconds() // 3600) == 48


def _low_disk(_path: str):
    return SimpleNamespace(total=100 * 1024**3, used=90 * 1024**3, free=10 * 1024**3)


def _quote(quote_id: str, at: datetime, source: str) -> MarketQuoteRecord:
    return MarketQuoteRecord(
        quote_id=quote_id,
        source_system=source,
        venue="Demo",
        instrument_id="TTF:DA",
        hub="TTF",
        product="DA",
        delivery_start_utc=at,
        delivery_end_utc=at + timedelta(days=1),
        bid_price=30.0,
        ask_price=30.1,
        currency="EUR",
        unit="EUR/MWh",
        observed_at_utc=at,
        received_at_utc=at,
        source_reference="feed:simulated-exchange",
        freshness="live",
        quality_score=1.0,
        simulated=True,
    )


def _trade(trade_id: str, at: datetime) -> MarketTradeRecord:
    return MarketTradeRecord(
        trade_id=trade_id,
        source_system="DEMO_Sim",
        venue="Demo",
        instrument_id="TTF:DA",
        hub="TTF",
        product="DA",
        delivery_start_utc=at,
        delivery_end_utc=at + timedelta(days=1),
        price=30.0,
        quantity_mwh=10.0,
        currency="EUR",
        trade_type="screen",
        traded_at_utc=at,
        received_at_utc=at,
        simulated=True,
    )


def _flow(observation_id: str, at: datetime, source: str) -> FlowObservationRecord:
    return FlowObservationRecord(
        observation_id=observation_id,
        point_id="p1",
        point_name="Point 1",
        direction="in",
        kind="actual",
        flow_mcm_d=1.0,
        period_start_utc=at,
        period_end_utc=at + timedelta(hours=1),
        observed_at_utc=at,
        source_system=source,
        source_reference="test",
        freshness="daily",
        research_only=False,
    )


def _alert(alert_id: str, *, status: str, at: datetime) -> MonitoringAlertRecord:
    return MonitoringAlertRecord(
        alert_id=alert_id,
        fingerprint=f"fp-{alert_id}",
        category="operations",
        alert_type="test",
        severity="warning",
        status=status,
        title_en="title",
        title_zh_cn="标题",
        message_en="message",
        message_zh_cn="消息",
        entity_type="desk",
        entity_id="demo",
        event_time_utc=at,
        detected_at_utc=at,
        updated_at_utc=at,
        occurrence_count=1,
        evidence_snapshot={},
        source_refs=[],
        warnings=[],
        llm_provider_id="DEEPSEEK",
        llm_status="pending",
        simulated=False,
        human_review_required=False,
    )


def _job(job_id: str, *, status: str, at: datetime) -> JobRecord:
    return JobRecord(
        job_id=job_id,
        kind="ingestion",
        status=status,
        principal="tester",
        created_at_utc=at,
        started_at_utc=at,
        finished_at_utc=at + timedelta(minutes=1) if status == "SUCCEEDED" else None,
    )


def test_settings_defaults_and_the_low_disk_floors() -> None:
    hk = _load()
    settings = hk.Settings.from_env({})
    assert settings.simulated_hours == 48
    assert settings.public_days == 120
    assert settings.alert_days == 30
    assert settings.meter_days == 90
    assert settings.disk_min_free_pct == 20.0

    tight = settings.tightened()
    assert tight.simulated_hours == 24
    assert tight.public_days == 60
    assert tight.alert_days == 15
    assert tight.meter_days == 45
    assert tight.job_days == 7

    # A window already at its floor never goes below it.
    low = hk.Settings.from_env(
        {
            "EUROGAS_NEXUS_DEMO_KEEP_SIMULATED_HOURS": "24",
            "EUROGAS_NEXUS_DEMO_KEEP_PUBLIC_DAYS": "10",
        }
    )
    assert low.tightened().simulated_hours == 24
    assert low.tightened().public_days == 30


def test_the_disk_guard_reports_not_visible_and_low() -> None:
    hk = _load()
    settings = hk.Settings.from_env(
        {"EUROGAS_NEXUS_DEMO_DISK_DATABASE_PATH": "/does/not/exist"}
    )

    def missing(path: str):
        raise FileNotFoundError(path)

    state = hk.read_disk_state(settings, missing)
    assert all(not path.visible for path in state.paths)
    assert all(path.free_pct is None for path in state.paths)
    assert state.low is False

    state = hk.read_disk_state(settings, _low_disk)
    assert state.low is True
    assert all(path.visible and path.free_pct == pytest.approx(10.0) for path in state.paths)

    state = hk.read_disk_state(settings, _high_disk)
    assert state.low is False


def test_dry_run_counts_without_deleting(factory) -> None:
    hk = _load()
    with factory() as session:
        session.add(_quote("old", NOW - timedelta(days=10), "DEMO_Sim"))
        session.add(_quote("new", NOW - timedelta(hours=1), "DEMO_Sim"))
        session.add(_flow("old-flow", NOW - timedelta(days=300), "ENTSOG"))
        session.commit()

    report = hk.run_housekeeping(
        factory, dry_run=True, now_utc=NOW, environ={}, disk_reader=_high_disk
    )
    assert report["status"] == "ok"
    assert report["dry_run"] is True
    assert report["tables"]["market_quotes"]["would_remove"] == 1
    assert report["tables"]["flow_observations"]["would_remove"] == 1
    assert report["sizes"]["before"]["database_bytes"] > 0
    assert "after" not in report["sizes"]

    with factory() as session:
        assert session.query(MarketQuoteRecord).count() == 2
        assert session.query(FlowObservationRecord).count() == 1
        # The plan is audited even though it deleted nothing.
        events = session.query(AuditEventRecord).filter(
            AuditEventRecord.action == "demo.housekeeping"
        )
        assert events.count() == 1
        assert events.one().outcome == "dry_run"


def test_simulated_backstop_and_public_window_scope_by_age_and_source(factory) -> None:
    hk = _load()
    with factory() as session:
        session.add(_quote("old-sim", NOW - timedelta(days=10), "DEMO_Sim"))
        session.add(_quote("new-sim", NOW - timedelta(hours=1), "DEMO_Sim"))
        session.add(_trade("old-print", NOW - timedelta(days=10)))
        session.add(_trade("new-print", NOW - timedelta(hours=1)))
        session.add(_flow("old-real", NOW - timedelta(days=300), "ENTSOG"))
        session.add(_flow("new-real", NOW - timedelta(days=1), "ENTSOG"))
        # Simulated daily history is what the demo's screens and risk read: it stays.
        session.add(_flow("old-sim-history", NOW - timedelta(days=300), "DEMO_Sim"))
        session.add(
            ScreenOrderObservationRecord(
                order_observation_id="old-booked",
                provider_id="ETRM_Sim",
                venue="Demo",
                account_label="demo",
                external_order_id="old-booked",
                side="buy",
                order_type="limit",
                hub="TTF",
                product="DA",
                contract_code="TTF:DA",
                delivery_start_utc=NOW - timedelta(days=10),
                delivery_end_utc=NOW - timedelta(days=9),
                price=30.0,
                currency="EUR",
                unit="EUR/MWh",
                quantity_mwh=1.0,
                filled_quantity_mwh=0.0,
                remaining_quantity_mwh=1.0,
                status="open",
                observed_at_utc=NOW - timedelta(days=10),
                source_system="ETRM_Sim",
                source_reference="test",
                research_only=False,
                human_review_required=False,
            )
        )
        session.add(
            GasDayNominationEventRecord(
                event_id="old-nomination",
                gas_day=date(2026, 11, 1),
                line_ref="contract:demo-haldor-24",
                hub="NBP",
                step="nomination",
                status="confirmed",
                quantity_mwh=1.0,
                origin="import",
                recorded_by="demo.operations",
                recorded_at_utc=NOW - timedelta(days=10),
                source_system="ETRM_Sim",
            )
        )
        session.commit()

    report = hk.run_housekeeping(
        factory, now_utc=NOW, environ={}, disk_reader=_high_disk
    )
    assert report["status"] == "ok"
    with factory() as session:
        quotes = {row.quote_id for row in session.query(MarketQuoteRecord)}
        assert quotes == {"new-sim"}
        trades = {row.trade_id for row in session.query(MarketTradeRecord)}
        assert trades == {"new-print"}
        flows = {row.observation_id for row in session.query(FlowObservationRecord)}
        assert flows == {"new-real", "old-sim-history"}
        assert session.query(ScreenOrderObservationRecord).count() == 0
        assert session.query(GasDayNominationEventRecord).count() == 0


def test_operational_rules_remove_only_the_finished_and_delivered(factory) -> None:
    hk = _load()
    old = NOW - timedelta(days=100)
    recent = NOW - timedelta(days=1)
    with factory() as session:
        session.add_all(
            [
                IngestionRunRecord(
                    run_id="old-finished", source_name="ENTSOG", source_id="src-entsog",
                    status="succeeded", started_at_utc=old,
                ),
                IngestionRunRecord(
                    run_id="old-running", source_name="ENTSOG", source_id="src-entsog",
                    status="RUNNING", started_at_utc=old,
                ),
                IngestionRunRecord(
                    run_id="new-finished", source_name="ENTSOG", source_id="src-entsog",
                    status="succeeded", started_at_utc=recent,
                ),
                _alert("resolved-old", status="resolved", at=old),
                _alert("ack-old", status="acknowledged", at=old),
                _alert("open-old", status="open", at=old),
                MonitoringAlertReaderStateRecord(
                    principal_id="tester", alert_id="resolved-old",
                    read_at_utc=old, read_severity="warning",
                ),
                _job("old-done", status="SUCCEEDED", at=old),
                _job("old-running-job", status="RUNNING", at=old),
                _job("new-done", status="SUCCEEDED", at=recent),
                UserSessionRecord(
                    session_id="expired", principal_id="tester",
                    session_token_hash="h1", created_at_utc=old,
                    last_seen_at_utc=old, expires_at_utc=old + timedelta(hours=1),
                ),
                UserSessionRecord(
                    session_id="active", principal_id="tester",
                    session_token_hash="h2", created_at_utc=recent,
                    last_seen_at_utc=recent, expires_at_utc=NOW + timedelta(days=1),
                ),
                OidcAuthorizationStateRecord(
                    state="consumed", code_challenge="c", code_challenge_method="S256",
                    code_verifier_hash="v", nonce="n", redirect_uri="https://x",
                    created_at_utc=old, expires_at_utc=old + timedelta(minutes=5),
                ),
                NotificationOutboxRecord(
                    notification_id="sent-old", category="limits", severity="warning",
                    title="t", body="b", dedupe_key="old",
                    created_at_utc=old, dispatched_at_utc=old,
                ),
                NotificationOutboxRecord(
                    notification_id="pending-new", category="limits", severity="warning",
                    title="t", body="b", dedupe_key="new",
                    created_at_utc=recent,
                ),
                RawPayloadContentRecord(
                    payload_sha256="old-sha", byte_size=10, compression="gzip",
                    payload_compressed=b"x", stored_in="inline",
                    first_received_at_utc=old, last_received_at_utc=old,
                ),
                RawPayloadContentRecord(
                    payload_sha256="new-sha", byte_size=10, compression="gzip",
                    payload_compressed=b"x", stored_in="inline",
                    first_received_at_utc=recent, last_received_at_utc=recent,
                ),
                RawPayloadArchiveRecord(
                    archive_id="old-receipt", source_system="ENTSOG", dataset="flows",
                    source_reference="rid", payload_text="<page/>",
                    payload_sha256="old-sha", record_count=1, received_at_utc=old,
                    research_only=False, human_review_required=False,
                ),
                LicensedDataUseRecord(
                    usage_day=date(2026, 1, 1), principal_id="tester",
                    source_family="EEX", surface="/api/prices", reads=1,
                    first_at_utc=old, last_at_utc=old,
                ),
                LicensedDataUseRecord(
                    usage_day=date(2026, 11, 25), principal_id="tester",
                    source_family="EEX", surface="/api/prices", reads=1,
                    first_at_utc=recent, last_at_utc=recent,
                ),
                ObservationTemporalMetadataRecord(
                    observation_id="old-meta", observation_table="flow_observations",
                    observed_at_utc=NOW - timedelta(days=300),
                    available_at_utc=NOW - timedelta(days=300),
                    ingested_at_utc=NOW - timedelta(days=300),
                    temporal_integrity="ok", provenance={},
                ),
            ]
        )
        old_event = MarketEventRecord(
            event_id="evt-old", event_key="k-old", revision=1, content_hash="h",
            source_id="src", event_type="price", subject_key="s", priority=1,
            ingested_at_utc=old,
        )
        new_event = MarketEventRecord(
            event_id="evt-new", event_key="k-new", revision=1, content_hash="h",
            source_id="src", event_type="price", subject_key="s", priority=1,
            ingested_at_utc=recent,
        )
        session.add_all([old_event, new_event])
        session.flush()
        session.add_all(
            [
                MarketEventDeliveryRecord(
                    consumer="opportunities", event_seq=old_event.seq,
                    status="processed", attempts=1, available_at_utc=old,
                    processed_at_utc=old,
                ),
                MarketEventDeliveryRecord(
                    consumer="opportunities", event_seq=new_event.seq,
                    status="pending", attempts=0, available_at_utc=recent,
                ),
            ]
        )
        session.commit()

    report = hk.run_housekeeping(
        factory, now_utc=NOW, environ={}, disk_reader=_high_disk
    )
    assert report["status"] == "ok", report["errors"]
    with factory() as session:
        runs = {row.run_id for row in session.query(IngestionRunRecord)}
        assert runs == {"old-running", "new-finished"}
        alerts = {row.alert_id for row in session.query(MonitoringAlertRecord)}
        assert alerts == {"open-old"}
        assert session.query(MonitoringAlertReaderStateRecord).count() == 0
        jobs = {row.job_id for row in session.query(JobRecord)}
        assert jobs == {"old-running-job", "new-done"}
        assert {row.session_id for row in session.query(UserSessionRecord)} == {"active"}
        assert session.query(OidcAuthorizationStateRecord).count() == 0
        assert {
            row.notification_id for row in session.query(NotificationOutboxRecord)
        } == {"pending-new"}
        assert {
            row.payload_sha256 for row in session.query(RawPayloadContentRecord)
        } == {"new-sha"}
        receipt = session.get(RawPayloadArchiveRecord, "old-receipt")
        assert receipt is not None and receipt.payload_text is None
        assert session.query(LicensedDataUseRecord).count() == 1
        assert session.query(ObservationTemporalMetadataRecord).count() == 0
        events = {row.event_id for row in session.query(MarketEventRecord)}
        assert events == {"evt-new"}
        deliveries = list(session.query(MarketEventDeliveryRecord))
        assert [(d.consumer, d.status) for d in deliveries] == [("opportunities", "pending")]


def test_the_audit_trail_is_left_alone_and_still_verifies(factory) -> None:
    hk = _load()
    with factory() as session:
        old = record_audit_event(
            session, event_type="governance.test", principal="tester",
            action="test.old", resource="demo", detail="old",
            now_utc=NOW - timedelta(days=400),
        )
        session.commit()
        old_id = old.event_id

    hk.run_housekeeping(factory, now_utc=NOW, environ={}, disk_reader=_high_disk)

    with factory() as session:
        assert session.get(AuditEventRecord, old_id) is not None
        result = verify_chain(session)
        assert result["ok"] is True, result
        assert result["unsealed_rows"] == 0
        assert (
            session.query(AuditEventRecord)
            .filter(AuditEventRecord.action == "demo.housekeeping")
            .count()
            == 1
        )


def test_a_low_disk_run_tightens_and_keeps_one_alert(factory) -> None:
    hk = _load()
    first = hk.run_housekeeping(
        factory, now_utc=NOW, environ={}, disk_reader=_low_disk
    )
    assert first["disk"]["low"] is True
    assert first["windows"]["public_days"] == 60
    assert first["windows"]["simulated_hours"] == 24
    assert first["alert"] == "updated"

    second = hk.run_housekeeping(
        factory, now_utc=NOW + timedelta(hours=1), environ={}, disk_reader=_low_disk
    )
    assert second["alert"] == "updated"

    with factory() as session:
        rows = session.query(MonitoringAlertRecord).filter(
            MonitoringAlertRecord.fingerprint == hk.DISK_ALERT_FINGERPRINT
        ).all()
        assert len(rows) == 1  # one alert updated, never one per run
        assert rows[0].occurrence_count == 2
        assert rows[0].status == "open"

    resolved = hk.run_housekeeping(
        factory, now_utc=NOW + timedelta(hours=2), environ={}, disk_reader=_high_disk
    )
    assert resolved["alert"] == "resolved"
    with factory() as session:
        row = session.query(MonitoringAlertRecord).filter(
            MonitoringAlertRecord.fingerprint == hk.DISK_ALERT_FINGERPRINT
        ).one()
        assert row.status == "resolved"


def test_the_script_refuses_a_release_profile(monkeypatch, capsys) -> None:
    hk = _load()
    monkeypatch.setenv("EUROGAS_NEXUS_API_PROFILE", "release")
    monkeypatch.setenv("EUROGAS_NEXUS_ENV", "release")
    assert hk.main([]) == 2
    captured = capsys.readouterr()
    assert "refused" in captured.err
    assert "demo" in captured.err
    assert "customer runtime" in captured.err


def test_the_report_is_one_structured_json_line(factory, capsys) -> None:
    hk = _load()
    hk.run_housekeeping(factory, now_utc=NOW, environ={}, disk_reader=_high_disk)
    captured = capsys.readouterr()
    lines = [line for line in captured.err.splitlines() if line.startswith("{")]
    assert lines
    payload = json.loads(lines[-1])
    assert payload["event"] == "demo.housekeeping"
    assert payload["status"] == "ok"
    assert payload["run_id"]


def test_the_seeded_business_rows_are_never_touched(factory) -> None:
    """The demo desk a tester may edit is not housekeeping's business."""

    hk = _load()
    with factory() as session:
        session.add(
            TradingBookRecord(
                book_id="demo-uk-nbp",
                name="UK NBP",
                legal_entity="NWG-UK",
                region="UK",
                business="Gas trading",
                base_currency="GBP",
                active=True,
                updated_by="demo-seed",
                updated_at_utc=NOW - timedelta(days=400),
            )
        )
        session.commit()
    hk.run_housekeeping(factory, now_utc=NOW, environ={}, disk_reader=_high_disk)
    with factory() as session:
        assert session.query(TradingBookRecord).count() == 1
        assert (
            session.query(func.count())
            .select_from(TradingBookRecord)
            .scalar()
            == 1
        )
