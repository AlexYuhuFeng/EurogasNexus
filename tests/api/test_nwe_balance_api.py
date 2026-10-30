"""GET /api/market/nwe-balance measures the call from ENTSOG, ALSI and AGSI and forecasts it."""

import json
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import FlowObservationRecord, RemitUmmRecord
from eurogas_nexus.db.models.observation import LngObservationRecord, StorageObservationRecord
from eurogas_nexus.domain.observations.remit_umm import parse_umm_export


def _common(day, ref):
    return dict(
        period_start_utc=day,
        period_end_utc=day + timedelta(days=1),
        observed_at_utc=day + timedelta(hours=20),
        source_reference=ref,
        freshness="daily",
        research_only=True,
    )


def test_balance_history_and_forecast_with_a_norwegian_outage(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'nwe.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    today = datetime.combine(now.date(), datetime.min.time(), tzinfo=UTC) + timedelta(hours=5)
    with Session(engine) as session:
        for back in range(1, 31):
            day = today - timedelta(days=back)
            tag = day.date().isoformat()
            session.add(
                FlowObservationRecord(
                    observation_id=f"f-{tag}",
                    point_id="emden",
                    point_name="Emden (EPT1)",
                    direction="entry",
                    flow_mcm_d=100.0,  # 1,100 GWh at 11 kWh/m3
                    source_system="ENTSOG",
                    **_common(day, f"f:{tag}"),
                )
            )
            session.add(
                LngObservationRecord(
                    observation_id=f"l-{tag}",
                    source_dataset="alsi",
                    terminal_id="gate",
                    terminal_name="Gate",
                    country="NL",
                    send_out_twh_d=0.4,
                    source_system="GIE",
                    **_common(day, f"l:{tag}"),
                )
            )
            session.add(
                StorageObservationRecord(
                    observation_id=f"s-{tag}",
                    source_dataset="agsi",
                    facility_id="rehden",
                    facility_name="Rehden",
                    country="DE",
                    inventory_twh=40.0,
                    working_capacity_twh=50.0,
                    fill_pct=80.0,
                    injection_twh_d=0.0,
                    withdrawal_twh_d=0.5,
                    source_system="GIE",
                    **_common(day, f"s:{tag}"),
                )
            )
        umm = [
            {
                "messageId": "TROLL-1",
                "version": 1,
                "eventStart": (today + timedelta(days=1)).isoformat(),
                "eventStop": (today + timedelta(days=3)).isoformat(),
                "affectedAssetName": "Troll",
                "balancingZone": "NO",
                "unitMeasure": "mcm/d",
                "unavailableCapacity": 20,
            }
        ]
        for message in parse_umm_export(json.dumps(umm), source_reference="t"):
            session.add(
                RemitUmmRecord(**message.as_record(), source_system="REMIT", ingested_at_utc=now)
            )
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    response = TestClient(create_app(), headers={"X-Eurogas-Api-Key": "test-public-api-token"}).get(
        "/api/market/nwe-balance?days=5"
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    last = data["history"][-1]
    assert last["norway_gwh"] == 1100.0 and last["lng_gwh"] == 400.0
    assert last["call_gwh"] == 2000.0  # 1,100 + 400 + 500 withdrawal
    forecast = {row["day"]: row for row in data["forecast"]}
    plain = forecast[today.date().isoformat()]
    hit = forecast[(today + timedelta(days=1)).date().isoformat()]
    assert plain["norway_gwh"] == 1100.0 and hit["norway_gwh"] == 880.0  # 20 mcm/d off
    assert hit["storage_net_withdrawal_gwh"] == plain["storage_net_withdrawal_gwh"] + 220.0
    assert plain["methods"]["norway"] == "7_day_average_less_remit_outages"
    assert data["norway_outages"] == 1 and plain["fill_pct"] is not None
