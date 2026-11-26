"""Retention by data class: floors, archive before remove, dry run, audit, restore.

Replaces the tests of the hard-coded 30/90/7-day pruning. Their intent stays: a dry run counts
and changes nothing; an enforced run acts on every class that has an action. What changed is
what it may do: settlements and observations are kept, ticks are archived then thinned, raw
pages are offloaded, snapshots are archived then removed, all verified first.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from eurogas_nexus.application import retention
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    AuditEventRecord,
    IntradayOpportunityRecord,
    MarketObservationRecord,
    MarketQuoteRecord,
    RawPayloadArchiveRecord,
    RawPayloadContentRecord,
    RetentionArchiveRecord,
    RetentionPolicyRecord,
    RetentionRunRecord,
)
from eurogas_nexus.db.registry import get_metadata
from eurogas_nexus.db.repositories.raw_archive import (
    archive_raw_payload,
    load_raw_payload_text,
)
from eurogas_nexus.db.session import get_engine
from eurogas_nexus.runtime_store.object_store import FilesystemObjectStore
from tests.support.scratch_postgres import SCRATCH_PG_ENV, scratch_postgres_database

NOW = datetime(2026, 11, 26, 3, 0, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[2]


_BACKENDS = ["sqlite"] + (["postgresql"] if os.environ.get(SCRATCH_PG_ENV) else [])


@pytest.fixture(params=_BACKENDS)
def factory(request, tmp_path):
    """SQLite always; also a fresh database on a scratch PostgreSQL when one is named."""

    if request.param == "sqlite":
        engine = create_engine(f"sqlite+pysqlite:///{tmp_path.as_posix()}/retention.sqlite")
        Base.metadata.create_all(engine)
        yield sessionmaker(bind=engine, expire_on_commit=False)
        engine.dispose()
        return
    with scratch_postgres_database(os.environ[SCRATCH_PG_ENV]) as url:
        engine = get_engine(url)
        Base.metadata.create_all(engine)
        yield sessionmaker(bind=engine, expire_on_commit=False)
        engine.dispose()


@pytest.fixture()
def store(tmp_path):
    return FilesystemObjectStore(tmp_path / "object-store")


def _quote(quote_id, observed, *, hub="TTF", product="DA", bid=30.0):
    return MarketQuoteRecord(
        quote_id=quote_id,
        source_system="EEX_Sim",
        venue="EEX",
        instrument_id=f"{hub}-{product}",
        hub=hub,
        product=product,
        delivery_start_utc=datetime(2026, 8, 1, tzinfo=UTC),
        delivery_end_utc=datetime(2026, 8, 2, tzinfo=UTC),
        bid_price=bid,
        ask_price=bid + 0.2,
        currency="EUR",
        unit="EUR/MWh",
        observed_at_utc=observed,
        received_at_utc=observed,
        source_reference="sim",
        freshness="live",
        quality_score=1.0,
        simulated=True,
        metadata_json={"seq": quote_id},
    )


def _observation(observation_id, observed):
    return MarketObservationRecord(
        observation_id=observation_id,
        market_venue="EEX",
        product="TTF-DA",
        price=31.5,
        unit="EUR/MWh",
        currency="EUR",
        period_start_utc=observed,
        period_end_utc=observed + timedelta(days=1),
        observed_at_utc=observed,
        source_system="EEX",
        source_reference="eex-settlement",
        freshness="settled",
        quality_score=1.0,
        research_only=False,
    )


def _opportunity(opportunity_id, detected):
    return IntradayOpportunityRecord(
        opportunity_id=opportunity_id,
        scan_id="scan",
        opportunity_type="location",
        status="detected",
        buy_quote_id="q1",
        sell_quote_id="q2",
        route_id="r",
        route_name="TTF to THE",
        buy_venue="EEX",
        sell_venue="EEX",
        buy_hub="TTF",
        sell_hub="THE",
        product="DA",
        delivery_start_utc=detected,
        delivery_end_utc=detected + timedelta(days=1),
        comparison_currency="EUR",
        comparison_unit="EUR/MWh",
        buy_ask=30.0,
        sell_bid=31.0,
        gross_spread=1.0,
        trading_cost=0.1,
        risk_buffer=0.1,
        quote_age_seconds=1.0,
        confidence_score=0.5,
        cost_components=[],
        source_refs=[],
        assumptions=[],
        missing_inputs=[],
        warnings=[],
        detected_at_utc=detected,
        valid_until_utc=detected + timedelta(minutes=5),
        simulated=True,
        human_review_required=True,
    )


def _seed_ticks(factory):
    old_day = datetime(2026, 8, 1, 10, 0, tzinfo=UTC)  # 117 days before NOW
    with factory() as session:
        # Three ticks in one minute of one stream, one in the next minute, one other stream.
        session.add(_quote("a1", old_day + timedelta(seconds=1), bid=30.0))
        session.add(_quote("a2", old_day + timedelta(seconds=20), bid=30.1))
        session.add(_quote("a3", old_day + timedelta(seconds=59), bid=30.2))
        session.add(_quote("a4", old_day + timedelta(minutes=1, seconds=5), bid=30.3))
        session.add(_quote("b1", old_day + timedelta(seconds=30), hub="THE", bid=32.0))
        session.add(_quote("b2", old_day + timedelta(seconds=40), hub="THE", bid=32.1))
        # Inside the hot period: never touched.
        session.add(_quote("r1", NOW - timedelta(days=10)))
        session.add(_quote("r2", NOW - timedelta(days=10, seconds=-1)))
        session.commit()


def test_every_class_table_exists_and_no_table_is_in_two_classes() -> None:
    tables = set(get_metadata().tables)
    seen: dict[str, str] = {}
    for data_class in retention.DATA_CLASSES:
        for table in data_class.tables:
            assert table in tables, f"{data_class.name} names unknown table {table}"
            assert table not in seen, f"{table} is in {seen.get(table)} and {data_class.name}"
            seen[table] = data_class.name


def test_regulated_classes_are_kept_and_have_a_seven_year_floor() -> None:
    for name in ("trading_records", "audit_and_decisions"):
        data_class = retention.CLASSES_BY_NAME[name]
        assert data_class.action == retention.KEEP
        assert data_class.floor_days >= 7 * 365
    for name in ("settlements_curves_and_marks", "fundamentals"):
        assert retention.CLASSES_BY_NAME[name].action == retention.KEEP
    assert "market_observations" in retention.CLASSES_BY_NAME["settlements_curves_and_marks"].tables
    assert "audit_events" in retention.CLASSES_BY_NAME["audit_and_decisions"].tables


def test_the_schedule_document_names_every_class_and_floor() -> None:
    document = (ROOT / "docs/compliance/RETENTION_SCHEDULE.md").read_text(encoding="utf-8")
    for data_class in retention.DATA_CLASSES:
        assert f"`{data_class.name}`" in document, data_class.name
        for table in data_class.tables:
            assert f"`{table}`" in document, table


def test_settings_can_raise_but_never_lower_a_floor(factory) -> None:
    with factory() as session:
        with pytest.raises(retention.RetentionPolicyError, match="below the floor"):
            retention.set_policy(
                session, data_class="live_ticks", hot_days=30, principal="ops", reason="smaller"
            )
        with pytest.raises(retention.RetentionPolicyError, match="kept by rule"):
            retention.set_policy(
                session, data_class="audit_and_decisions", hot_days=3000, principal="ops",
                reason="try",
            )
        raised = retention.set_policy(
            session, data_class="live_ticks", hot_days=365, principal="ops",
            reason="surveillance asked for a year of ticks",
        )
        session.commit()
        assert raised.hot_days == 365
        audit = session.query(AuditEventRecord).filter_by(action="retention.policy.set").one()
        assert audit.principal == "ops"
        # A row written below the floor by hand is still read at the floor.
        session.get(RetentionPolicyRecord, "live_ticks").hot_days = 1
        session.commit()
        assert retention.effective_policies(session)["live_ticks"].hot_days == 90


def test_dry_run_reports_and_changes_nothing(factory, store) -> None:
    _seed_ticks(factory)
    report = retention.run_retention(
        factory, mode="dry_run", principal="ops", now_utc=NOW, object_store=store
    )
    ticks = report["classes"]["live_ticks"]
    assert ticks["result"] == "dry_run"
    assert ticks["rows_to_archive"] == 6
    assert ticks["rows_to_remove"] == 3  # a1, a2 (a3 is the minute's last) and b1
    assert report["classes"]["trading_records"]["result"] == "kept"
    with factory() as session:
        assert session.query(MarketQuoteRecord).count() == 8
        assert session.query(RetentionArchiveRecord).count() == 0
        run = session.query(RetentionRunRecord).one()
        assert (run.mode, run.status) == ("dry_run", "ok")
        assert session.query(AuditEventRecord).filter_by(action="retention.dry_run").count() == 1
    assert not (store.root).exists() or not any(store.root.rglob("*.gz"))


def test_settlements_and_observations_older_than_90_days_survive(factory, store) -> None:
    with factory() as session:
        session.add(_observation("settle-old", NOW - timedelta(days=400)))
        session.add(_observation("settle-recent", NOW - timedelta(days=5)))
        session.commit()
    retention.run_retention(factory, mode="enforce", now_utc=NOW, object_store=store)
    with factory() as session:
        assert session.query(MarketObservationRecord).count() == 2


def test_ticks_are_archived_in_full_then_thinned_to_one_minute_bars(factory, store) -> None:
    _seed_ticks(factory)
    report = retention.run_retention(
        factory, mode="enforce", principal="ops", now_utc=NOW, object_store=store
    )
    ticks = report["classes"]["live_ticks"]
    assert ticks["result"] == "done", ticks
    assert (ticks["rows_archived"], ticks["rows_removed"]) == (6, 3)
    with factory() as session:
        kept = {row.quote_id for row in session.query(MarketQuoteRecord).all()}
        assert kept == {"a3", "a4", "b2", "r1", "r2"}
        archive = session.query(RetentionArchiveRecord).one()
        assert archive.data_class == "live_ticks"
        assert archive.object_key == "live_ticks/market_quotes/2026/08/01.jsonl.gz"
        data = store.get_bytes(archive.object_key)
        assert hashlib.sha256(data).hexdigest() == archive.sha256
        rows = [json.loads(line) for line in gzip.decompress(data).splitlines()]
        assert [row["quote_id"] for row in rows] == ["a1", "a2", "b1", "b2", "a3", "a4"]
        manifest = json.loads(store.get_bytes(archive.manifest_key))
        assert manifest["row_count"] == 6 and manifest["data_sha256"] == archive.sha256
        assert session.query(AuditEventRecord).filter_by(action="retention.enforce").count() == 1

    # A second pass finds the day archived and does not touch it again.
    again = retention.run_retention(factory, mode="enforce", now_utc=NOW, object_store=store)
    assert again["classes"]["live_ticks"]["result"] in {"done", "nothing_due"}
    assert again["classes"]["live_ticks"].get("rows_removed", 0) == 0

    # The read path: the archived day, without and then with loading it back.
    with factory() as session:
        archive_id = session.query(RetentionArchiveRecord).one().archive_id
        read = list(retention.read_archive_rows(session, archive_id, object_store=store))
        assert len(read) == 6 and read[0]["observed_at_utc"].tzinfo is not None
        restored = retention.restore_archive(
            session, archive_id, principal="ops", object_store=store
        )
        session.commit()
        assert restored["restored"] == 3
        assert session.query(MarketQuoteRecord).count() == 8
        assert session.get(MarketQuoteRecord, "a1").metadata_json == {"seq": "a1"}
        assert session.get(RetentionArchiveRecord, archive_id).status == "restored"


def test_without_an_object_store_nothing_is_removed(factory, monkeypatch) -> None:
    monkeypatch.delenv("EUROGAS_NEXUS_OBJECT_STORE_URL", raising=False)
    _seed_ticks(factory)
    with factory() as session:
        session.add(_opportunity("old-opp", NOW - timedelta(days=200)))
        session.commit()
    report = retention.run_retention(factory, mode="enforce", now_utc=NOW)
    assert report["classes"]["live_ticks"]["result"] == "blocked_no_object_store"
    assert report["classes"]["intraday_opportunity_snapshots"]["result"] == (
        "blocked_no_object_store"
    )
    with factory() as session:
        assert session.query(MarketQuoteRecord).count() == 8
        assert session.query(IntradayOpportunityRecord).count() == 1


def test_a_failed_verification_removes_nothing(factory, store, monkeypatch) -> None:
    _seed_ticks(factory)
    monkeypatch.setattr(type(store), "verify", lambda self, key, *, sha256, size: False)
    report = retention.run_retention(factory, mode="enforce", now_utc=NOW, object_store=store)
    assert report["classes"]["live_ticks"]["result"] == "failed"
    assert report["status"] == "failed"
    with factory() as session:
        assert session.query(MarketQuoteRecord).count() == 8
        assert session.query(RetentionArchiveRecord).count() == 0


def test_intraday_snapshots_are_archived_then_removed(factory, store) -> None:
    with factory() as session:
        session.add(_opportunity("old-1", NOW - timedelta(days=120)))
        session.add(_opportunity("old-2", NOW - timedelta(days=120, minutes=5)))
        session.add(_opportunity("recent", NOW - timedelta(days=3)))
        session.commit()
    report = retention.run_retention(factory, mode="enforce", now_utc=NOW, object_store=store)
    entry = report["classes"]["intraday_opportunity_snapshots"]
    assert (entry["rows_archived"], entry["rows_removed"]) == (2, 2)
    with factory() as session:
        assert [row.opportunity_id for row in session.query(IntradayOpportunityRecord)] == [
            "recent"
        ]
        archive_id = session.query(RetentionArchiveRecord).one().archive_id
        retention.restore_archive(session, archive_id, principal="ops", object_store=store)
        session.commit()
        restored = session.get(IntradayOpportunityRecord, "old-1")
        assert restored.cost_components == [] and restored.detected_at_utc is not None


def test_raw_pages_are_deduplicated_offloaded_and_still_readable(factory, store) -> None:
    page = '{"data": [1, 2, 3]}'
    digest = hashlib.sha256(page.encode()).hexdigest()
    with factory() as session:
        # Two legacy receipts written before 0095, each holding the same page.
        for number in range(2):
            session.add(
                RawPayloadArchiveRecord(
                    archive_id=f"legacy-{number}",
                    source_system="ENTSOG",
                    dataset="flows",
                    source_reference="legacy",
                    payload_text=page,
                    payload_json=json.loads(page),
                    payload_sha256=digest,
                    record_count=3,
                    received_at_utc=NOW - timedelta(days=60 + number),
                    research_only=True,
                    human_review_required=True,
                )
            )
        recent = '{"data": [4]}'
        archive_raw_payload(
            session,
            archive_id="recent",
            source_system="ENTSOG",
            dataset="flows",
            source_reference="new",
            payload_text=recent,
            payload_sha256=hashlib.sha256(recent.encode()).hexdigest(),
            record_count=1,
            received_at_utc=NOW - timedelta(days=2),
        )
        session.commit()

    preview = retention.run_retention(factory, mode="dry_run", now_utc=NOW, object_store=store)
    pages = preview["classes"]["raw_source_pages"]
    assert pages["receipts_with_inline_page"] == 2
    report = retention.run_retention(factory, mode="enforce", now_utc=NOW, object_store=store)
    pages = report["classes"]["raw_source_pages"]
    assert pages["receipts_deduplicated"] == 2 and pages["distinct_pages_added"] == 1
    assert pages["pages_offloaded"] == 1, pages
    with factory() as session:
        content = session.get(RawPayloadContentRecord, digest)
        assert content.stored_in == "object_store" and content.payload_compressed is None
        assert content.object_key == f"raw-pages/{digest[:2]}/{digest}.gz"
        hot = session.query(RawPayloadContentRecord).filter_by(stored_in="database").count()
        assert hot == 1  # the recent page stays hot
        # The read path fetches the offloaded page from object storage, verified.
        assert load_raw_payload_text(session, "legacy-1", object_store=store) == page
        archive = session.query(RetentionArchiveRecord).one()
        assert archive.action == "offload" and archive.row_count == 1
        retention.restore_archive(session, archive.archive_id, principal="ops", object_store=store)
        session.commit()
        assert session.get(RawPayloadContentRecord, digest).payload_compressed is not None


def test_retention_is_due_once_a_day_after_its_hour(factory) -> None:
    with factory() as session:
        assert not retention.retention_due(
            session, now_utc=datetime(2026, 11, 26, 1, 59, tzinfo=UTC), hour_utc=2
        )
        assert retention.retention_due(session, now_utc=NOW, hour_utc=2)
    retention.run_retention(factory, mode="dry_run", now_utc=NOW)
    with factory() as session:
        assert not retention.retention_due(session, now_utc=NOW + timedelta(hours=5), hour_utc=2)
        assert retention.retention_due(session, now_utc=NOW + timedelta(days=1), hour_utc=2)
    summary = retention.run_retention_if_due(
        factory,
        now_utc=NOW + timedelta(days=1),
        environ={"EUROGAS_NEXUS_RETENTION_MODE": "dry_run"},
    )
    assert summary["status"] == "ok" and summary["mode"] == "dry_run"
    assert retention.run_retention_if_due(
        factory, now_utc=NOW + timedelta(days=2), environ={"EUROGAS_NEXUS_RETENTION_MODE": "off"}
    ) == {"status": "off"}


def test_mode_setting_defaults_to_enforce_and_rejects_nonsense() -> None:
    assert retention.configured_mode({}) == "enforce"
    assert retention.configured_mode({"EUROGAS_NEXUS_RETENTION_MODE": "DRY_RUN"}) == "dry_run"
    assert retention.configured_mode({"EUROGAS_NEXUS_RETENTION_MODE": "delete-all"}) == "dry_run"
