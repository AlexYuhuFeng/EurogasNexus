"""TAR-1 tariff book on SQLite: versions from the registers, supersession, as-of reads,
``tariff.changed`` events with the snapshot keys, capacity notices and freshness alerts.

Every tariff figure here is made up; the shapes are the registers' own.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.application import tariff_book as book
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    CapacityNoticeRecord,
    LngTerminalOperatorTermsRecord,
    LngTerminalTariffRecord,
    MarketEventRecord,
    OpportunityDependencyRecord,
    OpportunityPendingInputRecord,
    TariffVersionRecord,
    TsoTariffRecord,
)

T0 = datetime(2026, 11, 20, 9, tzinfo=UTC)


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def entsog_row(value=4.0, status="INDICATIVE", *, at=T0, point="ITP-1", tso="Operator A", refs=()):
    return TsoTariffRecord(
        tariff_id=f"entsog-{point}-exit-annual-2026",
        document_id="entsog-tariffsfulls-2026-11-20",
        country="XX",
        tso=tso,
        market_area="AREA",
        gas_year="2026/27",
        point_id=point,
        source_point_name=f"Point {point}",
        direction="EXIT",
        capacity_product="ANNUAL",
        firmness="FIRM",
        tariff_value=value,
        currency="EUR",
        unit="EUR/(kWh/h)/y",
        effective_from=datetime(2026, 10, 1, tzinfo=UTC),
        effective_to=datetime(2027, 9, 30, tzinfo=UTC),
        tariff_status=status,
        source_table="ENTSOG TP tariffsfulls",
        source_page=None,
        source_refs=list(refs),
        manual_review_required=status != "FINAL",
        created_at_utc=at,
    )


def put(session, row):
    held = session.merge(row)
    session.flush()
    return held


def versions(session, key=None):
    query = session.query(TariffVersionRecord).order_by(
        TariffVersionRecord.tariff_key, TariffVersionRecord.version
    )
    if key:
        query = query.filter(TariffVersionRecord.tariff_key == key)
    return query.all()


KEY = "entsog-tp:entsog-ITP-1-exit-annual-2026"


# ------------------------------------------------------------------------------ versions


def test_a_register_row_becomes_version_one_with_its_status_and_source(session):
    put(session, entsog_row())
    result = book.capture_tariffs(session, now_utc=T0)
    assert result["tariffs"]["written"] == {"first": 1}
    (first,) = versions(session)
    assert first.tariff_key == KEY and first.version == 1
    assert (first.status, first.status_basis) == ("INDICATIVE", "period_not_started")
    assert first.source_url.endswith("tariffsfulls?pointKey=ITP-1")
    assert first.retrieved_at_utc.replace(tzinfo=UTC) == T0
    assert first.duration == "yearly" and first.superseded_at_utc is None
    # The same content again writes nothing, however often the capture runs.
    again = book.capture_tariffs(session, now_utc=T0 + timedelta(minutes=5))
    assert again["tariffs"]["written"] == {} and again["tariffs"]["unchanged"] == 1


def test_indicative_to_final_is_a_named_status_change_and_history_stays_readable(session):
    put(session, entsog_row())
    book.capture_tariffs(session, now_utc=T0)
    later = T0 + timedelta(days=3)
    put(session, entsog_row(status="FINAL", at=later))
    result = book.capture_tariffs(session, now_utc=later)
    assert result["tariffs"]["written"] == {"status_change": 1}
    old, new = versions(session)
    assert old.superseded_at_utc is not None and new.superseded_at_utc is None
    assert (new.version, new.change_kind, new.status_change) == (
        2,
        "status_change",
        "INDICATIVE->FINAL",
    )
    now_view = book.list_tariffs(session)["rows"]
    assert [(row["version"], row["status"], row["data_class"]) for row in now_view] == [
        (2, "FINAL", "sourced")
    ]
    before = book.list_tariffs(session, as_of=T0 + timedelta(days=1))["rows"]
    assert [(row["version"], row["status"], row["data_class"]) for row in before] == [
        (1, "INDICATIVE", "indicative")
    ]
    history = book.list_tariffs(session, filters=book.TariffFilter(tariff_key=KEY), history=True)[
        "rows"
    ]
    assert [row["version"] for row in history] == [1, 2]
    assert book.list_tariffs(session, as_of=T0 - timedelta(days=1))["rows"] == []


def test_a_revision_publishes_one_tariff_event_with_the_snapshot_keys(session):
    # An opportunity that read this tariff stored its key (with the operator slug).
    session.add(
        OpportunityDependencyRecord(
            opportunity_id="opp-1", input_key="tariff:ITP-1:EXIT:ANNUAL:2026/27:operator-a"
        )
    )
    put(session, entsog_row())
    book.capture_tariffs(session, now_utc=T0)
    put(session, entsog_row(value=4.5, at=T0 + timedelta(hours=2)))
    book.capture_tariffs(session, now_utc=T0 + timedelta(hours=2))
    events = session.query(MarketEventRecord).order_by(MarketEventRecord.revision).all()
    assert [event.event_type for event in events] == ["tariff.changed", "tariff.changed"]
    assert [event.revision for event in events] == [1, 2]
    latest = events[-1]
    assert latest.source_id == "ENTSOG"
    assert latest.payload_json["version"] == 2 and latest.payload_json["change_kind"] == "revised"
    assert latest.payload_json["value"] == 4.5 and latest.payload_json["status"] == "INDICATIVE"
    assert set(latest.dependency_keys) >= {
        "tariff:ITP-1:EXIT:ANNUAL:2026/27",
        "tariff:ITP-1:EXIT:ANNUAL:2026/27:operator-a",
    }
    assert versions(session)[-1].event_id == latest.event_id
    pending = session.get(OpportunityPendingInputRecord, "tariffs")
    assert pending is not None and pending.changes == 2


def test_an_older_read_never_supersedes_a_newer_one(session):
    put(session, entsog_row(value=4.5, at=T0))
    book.capture_tariffs(session, now_utc=T0)
    put(session, entsog_row(value=4.0, at=T0 - timedelta(days=2)))
    result = book.capture_tariffs(session, now_utc=T0 + timedelta(minutes=1))
    assert result["tariffs"]["out_of_order"] == 1
    assert [row.value for row in versions(session)] == [4.5]


def test_a_row_that_leaves_the_register_is_withdrawn_and_can_return(session):
    row = put(session, entsog_row())
    book.capture_tariffs(session, now_utc=T0)
    session.delete(row)
    session.flush()
    result = book.capture_tariffs(session, now_utc=T0 + timedelta(hours=1))
    assert result["tariffs"]["written"] == {"withdrawn": 1}
    assert book.list_tariffs(session)["rows"] == []
    assert versions(session)[-1].change_kind == "withdrawn"
    put(session, entsog_row(at=T0 + timedelta(hours=2)))
    back = book.capture_tariffs(session, now_utc=T0 + timedelta(hours=2))
    assert back["tariffs"]["written"] == {"revised": 1}
    assert [row["version"] for row in book.list_tariffs(session)["rows"]] == [3]


def test_status_bases_from_the_register(session):
    disagree = entsog_row(refs=["check: ENTSOG's common-unit figure disagrees"])
    assert book.spec_from_register_row(disagree).status_basis == "figures_disagree"
    stated = entsog_row(refs=["remarks: tariffs are provisional"])
    assert book.spec_from_register_row(stated).status_basis == "operator_stated"
    final = entsog_row(status="FINAL")
    assert book.spec_from_register_row(final).status_basis == "period_started"
    demo = entsog_row(status="SIMULATOR_ONLY")
    assert book.spec_from_register_row(demo) == "simulated"
    entry = entsog_row(
        status="FINAL",
        refs=["source: https://tso.example/tariffs.pdf", "published on 2026-05-30, final"],
    )
    entry.tariff_id = "entry-abc"
    spec = book.spec_from_register_row(entry)
    assert (
        spec.publisher_id == "tso-entries" and spec.source_url == "https://tso.example/tariffs.pdf"
    )
    assert spec.published_at_utc == datetime(2026, 5, 30, tzinfo=UTC)
    undocumented = entsog_row(refs=["typed by hand"])
    undocumented.tariff_id = "doc-xyz"
    assert book.spec_from_register_row(undocumented) == "no_source_url"


def test_the_entsog_read_records_versions_in_its_own_transaction(session):
    from eurogas_nexus.ingestion import entsog_tariffs

    rows = [
        {
            column: getattr(entsog_row(), column)
            for column in TsoTariffRecord.__table__.columns.keys()
        }
    ]

    def fake_rows(records, **_):
        return rows, {}

    from unittest.mock import patch

    with (
        patch.object(entsog_tariffs, "entsog_tariff_rows", fake_rows),
        patch("eurogas_nexus.ingestion.entsog_ingestion.archive_entsog_pages", lambda *_: None),
    ):
        counts = entsog_tariffs.persist_entsog_tariffs(
            session, results=[], run_id="run-1", bundle={}, points=["ITP-1"]
        )
    assert counts["tariff_versions"] == {"first": 1} and counts["tariff_events"] == 1
    assert versions(session)[0].tariff_key == KEY


# ---------------------------------------------------------------------- LNG terminals


def lng_row(review="CANDIDATE", amount=500000.0, sha="a" * 64, at=T0):
    return LngTerminalTariffRecord(
        tariff_id=f"lng-{sha[:8]}",
        terminal_id="zeebrugge:term",
        operator="fluxys_lng",
        terminal_name="Zeebrugge",
        country="BE",
        hub="ZTP",
        entry_point_key=None,
        regime="regulated",
        service="bundled_slot",
        product="term",
        charge_basis="per_cargo",
        amount=amount,
        currency="EUR",
        unit="EUR/cargo",
        by_cargo_class=None,
        indexation="none",
        valid_from=date(2027, 1, 1),
        valid_to=None,
        period_label=None,
        slot_days=None,
        sendout_days=None,
        included_storage=None,
        uioli_notice_days=None,
        source_url="https://www.fluxys.com/tariffs-2027.pdf",
        source_sha256=sha,
        retrieved_at_utc=at,
        document_title="Tariffs 2027",
        review_status=review,
        recorded_by="analyst",
        reviewed_by=None,
        reviewed_at_utc=None,
        created_at_utc=at,
    )


def test_a_terminal_document_is_indicative_until_reviewed_then_final(session):
    session.add(lng_row())
    session.flush()
    book.capture_tariffs(session, now_utc=T0)
    (first,) = versions(session)
    assert (first.publisher_id, first.facility_kind, first.status, first.status_basis) == (
        "fluxys-lng",
        "terminal",
        "INDICATIVE",
        "awaiting_review",
    )
    row = session.query(LngTerminalTariffRecord).one()
    row.review_status = "REVIEWED"
    session.flush()
    book.capture_tariffs(session, now_utc=T0 + timedelta(hours=1))
    assert versions(session)[-1].status_change == "INDICATIVE->FINAL"
    # A newer document for the same tariff supersedes; the older document stays in history.
    session.add(
        lng_row(review="REVIEWED", amount=520000.0, sha="b" * 64, at=T0 + timedelta(days=1))
    )
    session.flush()
    book.capture_tariffs(session, now_utc=T0 + timedelta(days=1))
    assert [row.value for row in versions(session)] == [500000.0, 500000.0, 520000.0]


def test_a_terminal_whose_terms_need_permission_is_excluded_until_recorded(session):
    status = {row["publisher_id"]: row for row in book.publisher_status(session, now_utc=T0)}
    assert status["fluxys-lng"]["state"] == "excluded"
    assert status["fluxys-lng"]["firm_permission"] is False
    session.add(
        LngTerminalOperatorTermsRecord(
            operator="fluxys_lng", permission_state="permitted", reference="letter 2026-11-01"
        )
    )
    session.flush()
    status = {row["publisher_id"]: row for row in book.publisher_status(session, now_utc=T0)}
    assert status["fluxys-lng"]["state"] == "manual"


# ---------------------------------------------------------------------------- notices


def test_standard_auctions_are_kept_rule_derived_and_idempotent(session):
    first = book.refresh_standard_auctions(session, now_utc=T0)
    assert first["created"] > 12 and first["updated"] == 0
    again = book.refresh_standard_auctions(session, now_utc=T0 + timedelta(hours=1))
    assert again["created"] == 0 and again["unchanged"] == first["created"]
    rows = book.list_notices(session, now_utc=T0, days=40)
    assert rows[0]["notice_key"] == "cam:monthly:2026-12" or rows[0]["opens_in_days"] >= 0
    assert {row["basis"] for row in rows} == {"rule_derived"}
    assert all(row["source_url"].startswith("https://eur-lex.europa.eu/") for row in rows)


def test_an_imported_notice_file_is_all_or_nothing(session):
    good = {
        "notice_id": "slot-2027-03",
        "kind": "lng_slot",
        "product": "SPOT_SLOT",
        "title": "Spot slot offer, March 2027",
        "opens_at_utc": "2026-12-01T09:00:00Z",
        "closes_at_utc": "2026-12-03T15:00:00Z",
        "facility_kind": "terminal",
        "facility_id": "gate",
        "quantity": "1",
        "quantity_unit": "slot",
        "source_url": "https://www.gate.nl/notice",
    }
    bad = dict(good, notice_id="slot-x", opens_at_utc="2026-12-01T09:00:00")
    refused = book.import_capacity_notices(
        session, [good, bad], publisher_id="gate-terminal", now_utc=T0
    )
    assert refused["stored"] is False and refused["refused"][0]["line"] == 2
    assert session.query(CapacityNoticeRecord).count() == 0
    stored = book.import_capacity_notices(session, [good], publisher_id="gate-terminal", now_utc=T0)
    assert stored["created"] == 1
    moved = dict(good, opens_at_utc="2026-12-02T09:00:00Z")
    changed = book.import_capacity_notices(
        session, [moved], publisher_id="gate-terminal", now_utc=T0
    )
    assert changed["updated"] == 1
    assert session.get(CapacityNoticeRecord, "gate-terminal:slot-2027-03").revision == 2
    with pytest.raises(book.NoticeImportError) as excluded:
        book.import_capacity_notices(session, [good], publisher_id="fluxys-lng", now_utc=T0)
    assert excluded.value.code == "publisher_terms_exclude"
    wrong_kind = book.import_capacity_notices(
        session, [dict(good, kind="auction")], publisher_id="gate-terminal", now_utc=T0
    )
    assert "does not publish auction" in wrong_kind["refused"][0]["reason"]


# ---------------------------------------------------------------------------- freshness


def test_a_publisher_read_late_raises_a_staleness_alert(session):
    put(session, entsog_row(at=T0))
    book.capture_tariffs(session, now_utc=T0)
    fresh = book.monitoring_candidates(session, T0 + timedelta(hours=10))
    assert not [c for c in fresh if c.alert_type == "tariff_publisher_stale"]
    late = book.monitoring_candidates(session, T0 + timedelta(days=4))
    (stale,) = [
        c for c in late if c.alert_type == "tariff_publisher_stale" and c.entity_id == "entsog-tp"
    ]
    assert (
        stale.category == "data_source" and stale.fingerprint == "tariff_publisher_stale:entsog-tp"
    )


def test_an_operator_without_next_period_prices_after_the_nc_tar_deadline(session):
    put(session, entsog_row(status="FINAL"))
    book.capture_tariffs(session, now_utc=T0)
    # Gas year 2027/28 starts 2027-10-01; yearly auction 2027-07-05; prices due 2027-06-05.
    assert book.final_deadline_for(date(2027, 10, 1)) == date(2027, 6, 5)
    assert book.missed_publications(session, today=date(2027, 6, 4)) == []
    (missed,) = book.missed_publications(session, today=date(2027, 6, 6))
    assert missed == {
        "operator": "Operator A",
        "next_period_from": "2027-10-01",
        "deadline": "2027-06-05",
    }
    alerts = book.monitoring_candidates(session, datetime(2027, 6, 6, 9, tzinfo=UTC))
    assert [c.fingerprint for c in alerts if c.alert_type == "tariff_publication_missed"] == [
        "tariff_publication_missed:entsog-tp"
    ]


def test_windows_opening_within_three_days_alert_scheduling_but_monthly_auctions_do_not(session):
    book.refresh_standard_auctions(session, now_utc=datetime(2026, 10, 30, tzinfo=UTC))
    alerts = book.monitoring_candidates(session, datetime(2026, 10, 30, 12, tzinfo=UTC))
    windows = [c for c in alerts if c.category == "capacity"]
    assert [c.entity_id for c in windows] == ["cam:quarterly:2026-11-02"]
    assert windows[0].severity == "info"
    from eurogas_nexus.application.alert_routing import route_for

    assert route_for("capacity").owner == "OPERATIONS"
    monthly = book.monitoring_candidates(session, datetime(2026, 11, 14, 12, tzinfo=UTC))
    assert not [c for c in monthly if c.category == "capacity"]


def test_the_valuation_snapshot_names_the_version_it_priced(session):
    put(session, entsog_row(status="FINAL"))
    book.capture_tariffs(session, now_utc=T0)
    held = book.version_at(session, KEY)
    assert held.version == 1 and held.status_basis == "period_started"
    assert book.version_at(session, KEY, T0 - timedelta(days=1)) is None
