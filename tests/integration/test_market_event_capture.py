"""Change capture (M5): settlements, FX fixings and REMIT messages become market events.

A capture over the store publishes one event per figure, nothing for a figure already held,
a revision for a correction, nothing for an older figure after a correction; REMIT versions
are revisions of one event; FX fixings reach the cross pairs; the scheduler and the
importers capture in their own transaction.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from eurogas_nexus.application import market_event_capture as capture
from eurogas_nexus.application import market_events as outbox
from eurogas_nexus.application.opportunities.service import run_evaluation
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    FxObservationRecord,
    MarketEventRecord,
    MarketObservationRecord,
    OpportunityDependencyRecord,
    OpportunityEvaluationRecord,
    OpportunityRecord,
    RemitUmmRecord,
)

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 17, 9, 42, tzinfo=UTC)
SINCE = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture()
def engine(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'capture.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return engine


def _seed_and_evaluate(session) -> None:
    spec = importlib.util.spec_from_file_location(
        "seed_demo_desk_capture", ROOT / "scripts" / "demo" / "seed_demo_desk.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.seed(session, NOW, history_days=5)
    session.commit()
    run_evaluation(session, trigger="on_demand", triggered_by="t", now_utc=NOW, demo_desk=True)
    session.commit()


def _store_ttf_day_ahead(session, price: float, observed: datetime) -> MarketObservationRecord:
    """An exchange settlement for the TTF day-ahead (2026-11-18), the gas day the demo's
    sell-down opportunities read; stored in place under one observation id, as an
    upsert by observation id does."""

    template = session.query(MarketObservationRecord).first()
    fields = {
        column.key: getattr(template, column.key)
        for column in MarketObservationRecord.__table__.columns
    }
    fields.update(
        observation_id="eex-ttf-da-2026-11-18",
        market_venue="EEX",
        product="TTF DA",
        price=price,
        period_start_utc=datetime(2026, 11, 18, tzinfo=UTC),
        period_end_utc=datetime(2026, 11, 19, tzinfo=UTC),
        observed_at_utc=observed,
        source_system="EEX_NGP",
        metadata_json={"hub": "TTF"},
    )
    stored = session.merge(MarketObservationRecord(**fields))
    session.flush()
    return stored


def _price_events(session, key):
    return (
        session.query(MarketEventRecord)
        .filter(MarketEventRecord.subject_key == key)
        .filter(MarketEventRecord.event_type == "price.updated")
        .order_by(MarketEventRecord.seq)
        .all()
    )


# ------------------------------------------------------------------------------ periods


@pytest.mark.parametrize(
    ("start", "end", "label"),
    [
        (date(2026, 11, 18), date(2026, 11, 19), "2026-11-18"),
        (date(2026, 11, 18), date(2026, 11, 18), "2026-11-18"),  # inclusive one-day row
        (date(2026, 12, 1), date(2027, 1, 1), "2026-12"),
        (date(2026, 12, 1), date(2026, 12, 31), "2026-12"),  # inclusive end
        (date(2027, 1, 1), date(2027, 4, 1), "2027-Q1"),
        (date(2027, 4, 1), date(2027, 10, 1), "SUM-27"),
        (date(2026, 10, 1), date(2027, 4, 1), "WIN-26"),
        (date(2026, 11, 14), date(2026, 11, 16), None),  # a weekend: no canonical label
        (date(2027, 1, 1), date(2028, 1, 1), None),  # a calendar year
    ],
)
def test_a_settlement_row_maps_to_the_period_an_opportunity_stores(start, end, label) -> None:
    period = capture.period_of(start, end)
    assert (period.label if period else None) == label


# ------------------------------------------------------------------------------ builders


def _remit(version, *, published, start, gwh="12.5", status="active"):
    return SimpleNamespace(
        record_id=f"UMM-77-v{version}",
        message_id="UMM-77",
        version=version,
        published_at_utc=published,
        ingested_at_utc=published + timedelta(minutes=3),
        event_status=status,
        unavailability_type="planned",
        event_start_utc=start,
        event_stop_utc=start + timedelta(days=2),
        asset_eic="21Z000000000001X",
        balancing_zone="THE",
        direction="entry",
        unavailable_gwh_d=float(gwh),
        unavailable_mcm_d=None,
        source_system="REMIT",
    )


def test_builders_give_the_keys_opportunities_store() -> None:
    settlement = SimpleNamespace(
        observation_id="obs-1",
        product="TTF DA",
        metadata_json={"hub": "TTF"},
        period_start_utc=datetime(2026, 11, 18, tzinfo=UTC),
        period_end_utc=datetime(2026, 11, 19, tzinfo=UTC),
        observed_at_utc=NOW,
        price=31.25,
        unit="EUR/MWh",
        currency="EUR",
        market_venue="EEX",
        source_system="EEX_NGP",
    )
    price = capture.settlement_event(settlement, ingested_at_utc=NOW)
    assert price.subject_key == "hub:TTF:2026-11-18"
    assert price.dependency_keys == ("hub:TTF:2026-11-18",)
    assert price.payload["price"] == "31.25" and price.payload["trade_day"] == "2026-11-17"
    # A correction stored later the same trade day is the same event; the next day is not.
    corrected = SimpleNamespace(**{**vars(settlement), "price": 31.4, "observed_at_utc": NOW
                                   + timedelta(hours=2)})
    next_day = SimpleNamespace(**{**vars(settlement), "observed_at_utc": NOW + timedelta(days=1)})
    later = NOW + timedelta(days=1)
    assert capture.settlement_event(corrected, ingested_at_utc=later).event_key == price.event_key
    assert capture.settlement_event(next_day, ingested_at_utc=later).event_key != price.event_key

    fixing = SimpleNamespace(
        observation_id="fx-1", base_currency="EUR", quote_currency="gbp", rate=0.8712,
        rate_type="reference", value_date="2026-11-17", source_system="ECB",
    )
    fx = capture.fx_event(fixing, ingested_at_utc=NOW)
    assert fx.subject_key == fx.dependency_keys[0] == "fx:EURGBP"
    assert fx.input_class == "fx" and fx.payload["rate"] == "0.8712"

    first = capture.outage_event(
        _remit(1, published=NOW, start=datetime(2026, 11, 20, tzinfo=UTC))
    )
    moved = capture.outage_event(
        _remit(2, published=NOW + timedelta(hours=1), start=datetime(2026, 11, 21, tzinfo=UTC))
    )
    assert first.subject_key == "outage:UMM-77" and first.priority == 0
    assert first.event_key == moved.event_key and first.content_hash != moved.content_hash


# ------------------------------------------------------------------------------ capture


def test_capture_publishes_once_then_a_correction_reaches_only_its_readers(engine) -> None:
    later = NOW + timedelta(minutes=5)
    with Session(engine) as session:
        _seed_and_evaluate(session)
        first = capture.capture(session, now_utc=later, since_utc=SINCE)
        session.commit()
        assert first["published"]["price.updated"] > 0
        assert first["published"]["fx.updated"] > 0
        assert first["published"]["outage.published"] > 0
        # Weekends, balance-of-month and calendar years are no stored input: not events.
        assert first["skipped"] > 0
        # The same store captured again: every figure is already held, nothing is written.
        count = session.query(MarketEventRecord).count()
        again = capture.capture(session, now_utc=later, since_utc=SINCE)
        assert again["published"] == {} and again["unchanged"] == again["examined"]
        assert session.query(MarketEventRecord).count() == count

        # Deliver the initial capture: the demo's settlement history is for gas days no
        # opportunity reads, so nothing is re-evaluated.
        done = outbox.process(session, "opportunities", now_utc=later, limit=5000)
        session.commit()
        assert done["processed"] > 0 and done["result"]["evaluators"] == []

        # An exchange settlement for the TTF day-ahead arrives, then is corrected in place.
        row = _store_ttf_day_ahead(session, 31.25, NOW)
        arrived = capture.capture(session, now_utc=later, since_utc=SINCE)
        session.commit()
        assert arrived["published"] == {"price.updated": 1}
        first = outbox.process(session, "opportunities", now_utc=later)
        session.commit()
        assert first["result"]["evaluators"] == ["sell_down"]

        original = row.price
        row.price = 32.0
        session.flush()
        corrected = capture.capture(session, now_utc=later + timedelta(minutes=1), since_utc=SINCE)
        session.commit()
        assert corrected["published"] == {"price.updated": 1}
        revisions = _price_events(session, "hub:TTF:2026-11-18")
        latest = max(revisions, key=lambda record: record.revision)
        assert [record.revision for record in revisions] == [1, 2]
        assert latest.supersedes_event_id == revisions[0].event_id
        assert latest.payload_json["price"] == "32"  # Decimals are normalised

        result = outbox.process(session, "opportunities", now_utc=later + timedelta(minutes=1))
        session.commit()
        assert result["processed"] == 1
        assert result["result"]["dependency_keys"] == ["hub:TTF:2026-11-18"]
        assert result["result"]["evaluators"] == ["sell_down"]
        run = session.get(OpportunityEvaluationRecord, result["result"]["evaluation_id"])
        assert run.trigger == "outbox" and set(run.evaluators_json) == {"sell_down"}

        # The source sends the old figure again: the correction stands, nothing is written.
        row.price = original
        session.flush()
        replayed = capture.capture(session, now_utc=later + timedelta(minutes=2), since_utc=SINCE)
        assert replayed["published"] == {}
        assert len(_price_events(session, "hub:TTF:2026-11-18")) == len(revisions)


def test_remit_versions_are_revisions_of_one_event_and_late_versions_change_nothing(
    engine,
) -> None:
    start = datetime(2026, 11, 20, tzinfo=UTC)
    with Session(engine) as session:
        for version, hours, moved in ((1, 0, start), (2, 2, start + timedelta(days=1))):
            fields = vars(_remit(version, published=NOW + timedelta(hours=hours), start=moved))
            session.add(RemitUmmRecord(**fields, asset_name="Storage X", asset_type="storage",
                                       unit="GWh/d", reason="maintenance",
                                       market_participant="SSO", remarks="",
                                       source_reference="test"))
        session.flush()
        result = capture.capture(session, now_utc=NOW + timedelta(hours=3), since_utc=SINCE)
        session.commit()
        assert result["published"] == {"outage.published": 2}
        events = (
            session.query(MarketEventRecord)
            .filter(MarketEventRecord.subject_key == "outage:UMM-77")
            .order_by(MarketEventRecord.revision)
            .all()
        )
        assert [event.revision for event in events] == [1, 2]
        assert len({event.event_key for event in events}) == 1
        assert events[1].payload_json["version"] == 2
        assert events[1].priority == 0

        # A stale copy of version 1 under a new record id changes nothing.
        stale = vars(_remit(1, published=NOW, start=start, gwh="99"))
        stale["record_id"] = "UMM-77-v1-copy"
        stale["ingested_at_utc"] = NOW + timedelta(hours=4)
        session.add(RemitUmmRecord(**stale, asset_name="Storage X", asset_type="storage",
                                   unit="GWh/d", reason="maintenance",
                                   market_participant="SSO", remarks="",
                                   source_reference="test"))
        session.flush()
        late = capture.capture(session, now_utc=NOW + timedelta(hours=5), since_utc=SINCE)
        assert late["published"] == {}


def test_a_fixing_reaches_the_cross_pairs_that_contain_its_currency(engine) -> None:
    with Session(engine) as session:
        _seed_and_evaluate(session)
        opportunity = session.query(OpportunityRecord.opportunity_id).first()[0]
        for key in ("fx:GBPUSD", "fx:EURGBP", "fx:EURNOK"):
            session.add(OpportunityDependencyRecord(opportunity_id=opportunity, input_key=key))
        session.flush()
        assert outbox._fx_crosses(session, ["fx:EURUSD"]) == {"fx:GBPUSD"}  # noqa: SLF001
        assert outbox._fx_crosses(session, ["fx:EURGBP"]) == {  # noqa: SLF001
            "fx:GBPUSD", "fx:EURGBP"
        }
        assert outbox._fx_crosses(session, ["hub:TTF:2026-12"]) == set()  # noqa: SLF001
        session.rollback()


def test_an_importer_captures_in_the_same_transaction(engine) -> None:
    with Session(engine) as session:
        row = FxObservationRecord(
            observation_id="ecb-eurgbp-2026-11-17", pair="EUR/GBP", base_currency="EUR",
            quote_currency="GBP", rate=0.8712, rate_type="reference", value_date="2026-11-17",
            observed_at_utc=NOW, source_system="ECB", source_reference="test",
            source_record_id=None, freshness="fresh", research_only=False, metadata_json={},
        )
        stored = session.merge(row)
        assert capture.capture_rows(session, fixings=[stored], now_utc=NOW)["published"] == {
            "fx.updated": 1
        }
        session.rollback()  # the import failed: neither the fixing nor its event is kept
        assert session.query(FxObservationRecord).count() == 0
        assert session.query(MarketEventRecord).count() == 0


def test_the_scheduler_captures_after_ingestion(engine) -> None:
    spec = importlib.util.spec_from_file_location(
        "run_dataops_scheduler_m5", ROOT / "scripts" / "ops" / "run_dataops_scheduler.py"
    )
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    factory = sessionmaker(engine)
    with factory() as session:
        fields = vars(_remit(1, published=NOW - timedelta(hours=1), start=NOW + timedelta(days=1)))
        session.add(RemitUmmRecord(**fields, asset_name="Storage X", asset_type="storage",
                                   unit="GWh/d", reason="maintenance",
                                   market_participant="SSO", remarks="",
                                   source_reference="test"))
        session.commit()
    tick = script.deliver_market_events(factory, [], now_utc=NOW)
    assert tick["status"] == "ok" and tick["captured"] == {"outage.published": 1}
    assert script.deliver_market_events(factory, [], now_utc=NOW)["captured"] == {}
