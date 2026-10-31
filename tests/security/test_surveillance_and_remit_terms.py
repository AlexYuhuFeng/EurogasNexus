"""Surveillance alerts against REMIT disclosure timing; REMIT platform reuse terms; RoPA draft."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.surveillance import hubs_for_zone, surveillance_alerts
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import DecisionCaseRecord, RemitUmmRecord
from eurogas_nexus.domain.observations.remit_platforms import source_reference_for


def _umm(message_id, participant, zone, start, published, version=1):
    return RemitUmmRecord(
        record_id=f"{message_id}-{version}",
        message_id=message_id,
        version=version,
        published_at_utc=published,
        event_status="Active",
        unavailability_type="Unplanned",
        event_start_utc=start,
        event_stop_utc=start + timedelta(days=1),
        asset_name=f"asset {message_id}",
        asset_eic="",
        asset_type="production",
        balancing_zone=zone,
        direction="",
        unit="GWh/d",
        technical_capacity=100,
        available_capacity=0,
        unavailable_capacity=100,
        unavailable_mcm_d=None,
        unavailable_gwh_d=100,
        reason="",
        market_participant=participant,
        remarks="",
        source_system="REMIT",
        source_reference="GIE_IIP:terms-published:t",
        ingested_at_utc=published,
    )


def _case(case_id, hub, at, who="trader-1"):
    return DecisionCaseRecord(
        case_id=case_id,
        objective="o",
        status="OPEN",
        created_by=who,
        created_at_utc=at,
        updated_at_utc=at,
        hub_id=hub,
    )


def test_zones_map_to_the_hubs_they_move():
    assert hubs_for_zone("GB") == {"NBP"}
    assert hubs_for_zone("NETHERLANDS") == set()  # no substring false match on "THE"
    assert {"NBP", "TTF"} <= hubs_for_zone("NO")


def test_alerts_for_own_late_disclosure_and_activity_before_publication(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{(tmp_path / 's.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    start = now - timedelta(hours=10)
    with Session(engine) as session:
        # Own outage published 3 hours after it started; a TTF trade case opened in between.
        session.add(_umm("OWN-1", "Example Energy", "NL", start, start + timedelta(hours=3)))
        session.add(_case("c-before", "TTF", start + timedelta(hours=1)))
        session.add(_case("c-after", "TTF", start + timedelta(hours=4)))
        session.add(_case("c-other-hub", "NBP", start + timedelta(hours=1)))
        # Another participant's outage; activity 30 minutes before its publication.
        other_pub = now - timedelta(hours=2)
        session.add(_umm("MKT-1", "Someone Else", "GB", other_pub - timedelta(hours=1), other_pub))
        session.add(_case("c-leak", "NBP", other_pub - timedelta(minutes=30)))
        session.commit()
        alerts = surveillance_alerts(
            session, since=now - timedelta(days=1), until=now, own={"example energy"}
        )
    found = {(a.rule, a.message_id, a.activity_id) for a in alerts}
    assert ("late_own_disclosure", "OWN-1", "") in found
    assert ("activity_before_own_disclosure", "OWN-1", "c-before") in found
    assert ("activity_before_market_disclosure", "MKT-1", "c-leak") in found
    assert not any(
        a.activity_id in {"c-after", "c-other-hub"} for a in alerts if a.message_id == "OWN-1"
    )
    leak = next(a for a in alerts if a.activity_id == "c-leak")
    assert leak.minutes_before_publication == 30 and leak.severity == "medium"


def test_remit_platform_terms_gate_the_import():
    assert source_reference_for("GIE_IIP", "f.json", terms_confirmed=False).startswith(
        "GIE_IIP:terms-published:"
    )
    with pytest.raises(ValueError, match="terms-confirmed"):
        source_reference_for("EEX_TP", "f.csv", terms_confirmed=False)
    assert "terms-confirmed-by-operator" in source_reference_for(
        "EEX_TP", "f.csv", terms_confirmed=True
    )


def test_processing_register_reflects_configuration(monkeypatch):
    import scripts.ops.processing_register as register

    monkeypatch.setenv("EUROGAS_NEXUS_DEPLOYMENT_REGION", "china")
    monkeypatch.delenv("EUROGAS_NEXUS_LLM_EXTERNAL_PROVIDER_ENABLED", raising=False)
    text = register.render("Example Ltd", "dpo@example.com")
    assert "| Controller | Example Ltd |" in text
    assert "stays in China" in text
    assert "no data leaves the installation for AI processing" in text
