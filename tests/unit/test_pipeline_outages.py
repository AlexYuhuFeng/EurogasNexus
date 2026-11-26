"""LNG-4 change 3: REMIT outages update the pipeline supply they flow through.

Matching is exact (EIC, normalised name, or the reviewed GIE alias table); the volume is the
message's unavailable share of technical capacity, times the supply's share through the
asset, weighed by the part of each gas day the event covers; a newer version revises the
link, an older or repeated one changes nothing, a dismissed message withdraws it and an
inactive one ends it; days entered by hand win, and the manual mode keeps only those.
Every message here is test data.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application import pipeline_outages as po
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    AuditEventRecord,
    PipelineOutageLinkRecord,
    PipelineSupplyRecord,
    RemitUmmRecord,
)
from eurogas_nexus.domain.market.gas_day import gas_day_start_for_date

NOW = datetime(2027, 1, 20, 9, tzinfo=UTC)
EIC = "21Z000000000TEST"


def gas_day(day: date, hours: float = 0) -> datetime:
    return gas_day_start_for_date(day) + timedelta(hours=hours)


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{(tmp_path / 'o.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as made:
        yield made
    engine.dispose()


def supply(**values) -> PipelineSupplyRecord:
    base = {
        "supply_id": "pipe-1",
        "book_id": "book-1",
        "label": "Interconnector gas",
        "contract_id": None,
        "hub": "ZTP",
        "point": "ZTP",
        "first_gas_day": date(2027, 1, 20),
        "last_gas_day": date(2027, 2, 28),
        "mwh_per_day": 30_000.0,
        "cost_eur_mwh": 28.0,
        "curtailed": [],
        "depends_on": [{"asset_eic": EIC, "kind": "interconnector", "share_pct": 50}],
        "outage_mode": None,
        "source_system": "TEST",
        "source_reference": "test",
        "updated_at_utc": NOW,
    }
    return PipelineSupplyRecord(**{**base, **values})


def message(version: int = 1, **values) -> RemitUmmRecord:
    base = {
        "record_id": f"umm-1-v{version}",
        "message_id": "umm-1",
        "version": version,
        "published_at_utc": NOW,
        "event_status": "active",
        "unavailability_type": "planned",
        "event_start_utc": gas_day(date(2027, 2, 1)),
        "event_stop_utc": gas_day(date(2027, 2, 3), 12),
        "asset_name": "Test Interconnector",
        "asset_eic": EIC,
        "asset_type": "interconnector",
        "balancing_zone": "ZTP",
        "direction": "entry",
        "unit": "GWh/d",
        "technical_capacity": 200.0,
        "available_capacity": 100.0,
        "unavailable_capacity": 100.0,
        "unavailable_mcm_d": None,
        "unavailable_gwh_d": 100.0,
        "reason": "maintenance",
        "market_participant": "Test TSO",
        "remarks": "",
        "source_system": "REMIT",
        "source_reference": "test",
        "ingested_at_utc": NOW,
    }
    return RemitUmmRecord(**{**base, **values})


def test_an_outage_curtails_the_supply_by_its_share_and_the_part_of_each_gas_day(session):
    session.add_all([supply(), message()])
    session.flush()
    report = po.link_outages(session, now=NOW)
    assert report.created == ["pipe-1:umm-1"] and report.books == {"book-1"}
    (link,) = session.query(PipelineOutageLinkRecord).all()
    assert (link.matched_on, link.status, link.fraction, link.version) == (
        "asset_eic",
        po.APPLIED,
        0.5,
        1,
    )
    # 30,000 MWh/d x 50 % through the asset x 50 % unavailable = 7,500 MWh/d; the event
    # ends at 12:00 into the 3 Feb gas day, so half of that day.
    assert link.curtailed == [
        ["2027-02-01", 7500.0],
        ["2027-02-02", 7500.0],
        ["2027-02-03", 3750.0],
    ]
    assert "matches the supply's interconnector on asset eic" in link.why
    assert "100 of 200 GWh/d technical capacity unavailable (50%)" in link.why


def test_a_repeated_or_older_version_changes_nothing_and_a_newer_one_revises(session):
    session.add_all([supply(), message()])
    session.flush()
    po.link_outages(session, now=NOW)
    again = po.link_outages(session, now=NOW)
    assert again.created == [] and again.revised == [] and again.unchanged == ["pipe-1:umm-1"]
    session.add(message(2, unavailable_capacity=200.0, available_capacity=0.0))
    session.flush()
    revised = po.link_outages(session, message_ids={"umm-1"}, now=NOW + timedelta(hours=1))
    assert revised.revised == ["pipe-1:umm-1"]
    (link,) = session.query(PipelineOutageLinkRecord).all()
    assert (link.version, link.fraction, link.curtailed[0]) == (2, 1.0, ["2027-02-01", 15000.0])
    assert session.query(PipelineOutageLinkRecord).count() == 1


def test_a_withdrawn_message_removes_the_curtailment_and_keeps_the_record(session):
    session.add_all([supply(), message()])
    session.flush()
    po.link_outages(session, now=NOW)
    session.add(message(2, event_status="dismissed"))
    session.flush()
    po.link_outages(session, now=NOW)
    (link,) = session.query(PipelineOutageLinkRecord).all()
    assert (link.status, link.curtailed, link.version) == (po.WITHDRAWN, [], 2)
    assert "withdrawn, so it curtails nothing" in link.why
    used = po.effective(session.get(PipelineSupplyRecord, "pipe-1"), [link])
    assert used.curtailed == ()


def test_an_inactive_message_ends_the_link(session):
    session.add_all([supply(), message(event_status="inactive")])
    session.flush()
    po.link_outages(session, now=NOW)
    (link,) = session.query(PipelineOutageLinkRecord).all()
    assert (link.status, link.curtailed) == (po.ENDED, [])


def test_matching_by_name_by_reviewed_alias_and_direction(session, monkeypatch):
    by_name = supply(supply_id="pipe-n", depends_on=[{"asset_name": "TEST  interconnector!"}])
    other_way = supply(supply_id="pipe-x", depends_on=[{"asset_eic": EIC, "direction": "exit"}])

    class Aliases:
        def facility_for(self, *, eic, name):
            return {"gie_facility_eic": "21W-GIE-FAC"} if eic == EIC else None

    monkeypatch.setattr(po, "shipped_aliases", lambda: Aliases())
    by_alias = supply(supply_id="pipe-g", depends_on=[{"gie_facility_eic": "21w-gie-fac"}])
    unrelated = supply(supply_id="pipe-u", depends_on=[{"asset_eic": "21Z-OTHER"}])
    session.add_all([by_name, other_way, by_alias, unrelated, message()])
    session.flush()
    po.link_outages(session, now=NOW)
    matched = {
        row.supply_id: row.matched_on for row in session.query(PipelineOutageLinkRecord).all()
    }
    assert matched == {"pipe-n": "asset_name", "pipe-g": "gie_facility_eic"}


def test_no_derivable_volume_is_shown_unsized_and_curtails_nothing(session):
    session.add_all([supply(), message(technical_capacity=None, unavailable_capacity=None)])
    session.flush()
    po.link_outages(session, now=NOW)
    (link,) = session.query(PipelineOutageLinkRecord).all()
    assert (link.status, link.fraction, link.curtailed) == (po.UNSIZED, None, [])
    # The supply's own capacity through the asset sizes it from the message's GWh/d.
    session.query(PipelineOutageLinkRecord).delete()
    session.query(PipelineSupplyRecord).delete()
    session.add(supply(depends_on=[{"asset_eic": EIC, "capacity_mwh_d": 400_000}]))
    session.flush()
    po.link_outages(session, now=NOW)
    (link,) = session.query(PipelineOutageLinkRecord).all()
    assert link.fraction == 0.25 and link.curtailed[0] == ["2027-02-01", 7500.0]


def test_days_entered_by_hand_win_and_the_largest_link_counts(session):
    held = supply(curtailed=[["2027-02-02", 1000.0]])
    session.add_all(
        [
            held,
            message(),
            message(1, record_id="umm-2", message_id="umm-2", unavailable_capacity=50.0),
        ]
    )
    session.flush()
    po.link_outages(session, now=NOW)
    all_links = po.links(session, ["pipe-1"])["pipe-1"]
    assert len(all_links) == 2
    used = po.effective(held, all_links)
    assert dict(used.curtailed) == {
        date(2027, 2, 1): 7500.0,  # the larger of 7,500 and 3,750
        date(2027, 2, 2): 1000.0,  # entered by hand
        date(2027, 2, 3): 3750.0,
    }
    assert used.by_day["2027-02-02"] == "entered by hand"
    assert used.by_day["2027-02-01"] == "REMIT umm-1 v1"
    held.outage_mode = po.MANUAL
    assert po.effective(held, all_links).curtailed == ((date(2027, 2, 2), 1000.0),)


def test_the_manual_override_is_checked_audited_and_kept(session):
    session.add_all([supply(), message()])
    session.flush()
    po.link_outages(session, now=NOW)
    result = po.set_override(
        session,
        "pipe-1",
        mode=po.MANUAL,
        curtailed=[["2027-02-05", 2000], ["2027-02-04", 1000]],
        actor="trader",
        reason="the TSO confirmed a shorter outage",
        now=NOW,
    )
    assert result["outage_mode"] == po.MANUAL
    assert result["entered_by_hand"] == [["2027-02-04", 1000.0], ["2027-02-05", 2000.0]]
    assert result["effective"] == [["2027-02-04", 1000.0], ["2027-02-05", 2000.0]]
    assert [link["status"] for link in result["links"]] == [po.APPLIED]
    (audit,) = (
        session.query(AuditEventRecord).filter_by(action="lng.pipeline_outage_override").all()
    )
    assert audit.detail.startswith("outage mode auto -> manual; 2 day(s) entered by hand")
    for bad in ([["2026-12-31", 1]], [["2027-02-01", 40_000]], [["nope"]]):
        with pytest.raises(po.OverrideError) as refused:
            po.set_override(session, "pipe-1", mode=po.AUTO, curtailed=bad, actor="trader")
        assert refused.value.code == "curtailment_invalid"
    with pytest.raises(po.OverrideError) as unknown:
        po.supply_links(session, "nope")
    assert unknown.value.status_code == 404
    with pytest.raises(po.OverrideError):
        po.set_override(session, "pipe-1", mode="sometimes", curtailed=None, actor="trader")
