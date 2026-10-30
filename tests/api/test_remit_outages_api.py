"""GET /api/physical/outages reads imported REMIT UMMs: latest version, live or upcoming."""

import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import RemitUmmRecord
from eurogas_nexus.domain.observations.remit_umm import parse_umm_export


def _row(message_id, version, start, stop, status="Active"):
    return {
        "messageId": message_id,
        "version": version,
        "publicationDateTime": (start - timedelta(hours=1)).isoformat(),
        "eventStatus": status,
        "unavailabilityType": "Unplanned",
        "eventStart": start.isoformat(),
        "eventStop": stop.isoformat(),
        "affectedAssetName": "Nyhamna",
        "affectedAssetType": "Production",
        "balancingZone": "NO",
        "unitMeasure": "mcm/d",
        "unavailableCapacity": 25,
    }


def test_outages_show_latest_version_of_live_and_upcoming_events(tmp_path, monkeypatch):
    database_url = f"sqlite+pysqlite:///{(tmp_path / 'remit.sqlite').as_posix()}"
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    export = [
        _row("UMM-LIVE", 1, now - timedelta(hours=3), now + timedelta(days=2)),
        # Revised: the outage ended early, so the event is no longer live.
        _row("UMM-ENDED", 1, now - timedelta(hours=3), now + timedelta(days=2)),
        _row("UMM-ENDED", 2, now - timedelta(hours=3), now - timedelta(hours=1)),
        _row("UMM-NEXT", 1, now + timedelta(days=3), now + timedelta(days=4)),
        _row("UMM-GONE", 1, now + timedelta(days=3), now + timedelta(days=4)),
        _row("UMM-GONE", 2, now + timedelta(days=3), now + timedelta(days=4), "Dismissed"),
    ]
    with Session(engine) as session:
        for message in parse_umm_export(json.dumps(export), source_reference="fixture"):
            session.add(
                RemitUmmRecord(**message.as_record(), source_system="REMIT", ingested_at_utc=now)
            )
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", database_url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    response = TestClient(create_app(), headers={"X-Eurogas-Api-Key": "test-public-api-token"}).get(
        "/api/physical/outages"
    )
    assert response.status_code == 200, response.text
    rows = response.json()["data"]
    assert [(row["event_id"], row["status"]) for row in rows] == [
        ("UMM-LIVE", "active"),
        ("UMM-NEXT", "scheduled"),
    ]
    assert rows[0]["capacity_impact_mcm_d"] == 25 and rows[0]["facility_name"] == "Nyhamna"
