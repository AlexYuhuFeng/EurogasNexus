"""GET /api/market/nwe-balance measures the call from ENTSOG, ALSI and AGSI and forecasts it."""

import json
from datetime import UTC, datetime, timedelta

import pytest
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
        # Received as the gas day closes: a row received while its day was open is a
        # snapshot, not the day's figure (pipeline_supply.published_after_close).
        observed_at_utc=day + timedelta(days=1),
        source_reference=ref,
        freshness="daily",
        research_only=True,
    )


@pytest.mark.parametrize("future_publication", [False, True])
def test_balance_history_and_forecast_with_a_norwegian_outage(
    tmp_path, monkeypatch, future_publication
):
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
                "publishedAt": (now + timedelta(days=2) if future_publication else now).isoformat(),
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
    if future_publication:
        assert hit["norway_gwh"] == 1100.0
        assert data["norway_outages"] == 0
        return
    assert plain["norway_gwh"] == 1100.0 and hit["norway_gwh"] == 880.0  # 20 mcm/d off
    assert hit["storage_net_withdrawal_gwh"] == plain["storage_net_withdrawal_gwh"] + 220.0
    assert plain["methods"]["norway"] == "7_day_average_less_remit_outages"
    assert data["norway_outages"] == 1 and plain["fill_pct"] is not None
    from eurogas_nexus.domain.market.gas_day import gas_day_label

    runtime = TestClient(create_app(), headers={"X-Eurogas-Api-Key": "test-public-api-token"}).post(
        "/api/market/nwe-balance",
        json={
            "use_runtime_history": True,
            "history": [],
            "prediction_origin": now.isoformat(),
            "start": gas_day_label(now),
            "days": 2,
        },
    )
    assert runtime.status_code == 200, runtime.text
    resolved = runtime.json()["data"]
    assert resolved["inputs"]["history"][-1]["norway_gwh"] == 1100.0
    assert resolved["weather_evidence"][0]["evidence_kind"] == "RUNTIME_BALANCE_CURRENT_AGGREGATE"


def test_gb_rows_join_the_sums_but_not_the_fill_or_the_newest_partial_day(tmp_path, monkeypatch):
    """GB (National Gas) has no working capacity and publishes a day before GIE."""

    url = f"sqlite+pysqlite:///{(tmp_path / 'nwe-gb.sqlite').as_posix()}"
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
                    observation_id=f"f-{tag}", point_id="emden", point_name="Emden (EPT1)",
                    direction="entry", flow_mcm_d=100.0, source_system="ENTSOG",
                    **_common(day, f"f:{tag}"),
                )
            )
            # National Gas reports yesterday; GIE does not have it yet.
            session.add(
                StorageObservationRecord(
                    observation_id=f"gb-s-{tag}", source_dataset="NG-SUPPLY",
                    facility_id="GB-NTS-STORAGE", facility_name="GB storage", country="GB",
                    inventory_twh=10.0, working_capacity_twh=None, fill_pct=None,
                    injection_twh_d=0.0, withdrawal_twh_d=0.3, source_system="NATIONAL_GAS",
                    **_common(day, f"gb-s:{tag}"),
                )
            )
            session.add(
                LngObservationRecord(
                    observation_id=f"gb-l-{tag}", source_dataset="NG-SUPPLY",
                    terminal_id="GB-NTS-LNG", terminal_name="GB LNG", country="GB",
                    send_out_twh_d=0.5, source_system="NATIONAL_GAS",
                    **_common(day, f"gb-l:{tag}"),
                )
            )
            if back == 1:
                continue
            session.add(
                LngObservationRecord(
                    observation_id=f"l-{tag}", source_dataset="alsi", terminal_id="gate",
                    terminal_name="Gate", country="NL", send_out_twh_d=0.4, source_system="GIE",
                    **_common(day, f"l:{tag}"),
                )
            )
            session.add(
                StorageObservationRecord(
                    observation_id=f"s-{tag}", source_dataset="agsi", facility_id="rehden",
                    facility_name="Rehden", country="DE", inventory_twh=40.0,
                    working_capacity_twh=50.0, fill_pct=80.0, injection_twh_d=0.0,
                    withdrawal_twh_d=0.5, source_system="GIE", **_common(day, f"s:{tag}"),
                )
            )
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    response = TestClient(create_app(), headers={"X-Eurogas-Api-Key": "test-public-api-token"}).get(
        "/api/market/nwe-balance?days=3"
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    last = data["history"][-1]
    # Yesterday holds only GB, so the history stops at the last day GIE also reported.
    assert last["day"] == (today - timedelta(days=2)).date().isoformat()
    assert last["lng_gwh"] == 900.0 and last["storage_net_withdrawal_gwh"] == 800.0
    assert data["assumptions"]["storage_inventory_day"] == last["day"]
    # Fill is 40 TWh over 50 TWh of capacity; GB's 10 TWh has no capacity behind it.
    first = data["forecast"][0]
    assert first["inventory_twh"] < 40.0
    assert first["fill_pct"] == pytest.approx(100 * first["inventory_twh"] / 50.0, abs=0.1)
    # The 800 GWh draw includes GB's 300 GWh; only Rehden's 500 GWh comes out of the
    # 40 TWh it holds (subtracting all 800 gave 39.2 TWh and a fill falling too fast).
    assert first["storage_net_withdrawal_gwh"] == 800.0
    assert first["inventory_draw_gwh"] == 500.0
    assert first["inventory_twh"] == 39.5
    assert first["methods"]["inventory_draw"] == "residual_less_14_day_average_outside_inventory"
    assert "GB" in data["assumptions"]["storage_inventory_draw_basis"]


def test_partly_reported_newest_pipeline_days_are_left_out(tmp_path, monkeypatch):
    """ENTSOG fills the newest days point by point: coverage, not size, decides."""

    url = f"sqlite+pysqlite:///{(tmp_path / 'nwe-partial.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    today = datetime.combine(now.date(), datetime.min.time(), tzinfo=UTC) + timedelta(hours=5)
    landings = (("ITP-00106", "BE-TSO-0001"), ("ITP-00045", "FR-TSO-0003"),
                ("ITP-00097", "DK-TSO-0001"))
    with Session(engine) as session:
        for back in range(1, 31):
            day = today - timedelta(days=back)
            tag = day.date().isoformat()
            # Yesterday and the day before: one landing of three has reported so far.
            reported = landings[:1] if back <= 2 else landings
            for point_id, operator in reported:
                session.add(
                    FlowObservationRecord(
                        observation_id=f"f-{point_id}-{tag}", point_id=point_id,
                        point_name=point_id, direction="entry", original_value=500e6,
                        original_unit="kWh/d", source_system="ENTSOG",
                        metadata_json={"operatorKey": operator},
                        normalizer_version="entsog-native-units-v1",
                        native_rate_json={"value": "500000000", "unit": "kWh/d"},
                        **_common(day, f"f:{point_id}:{tag}"),
                    )
                )
            session.add(
                LngObservationRecord(
                    observation_id=f"l-{tag}", source_dataset="alsi", terminal_id="gate",
                    terminal_name="Gate", country="NL", send_out_twh_d=0.4, source_system="GIE",
                    **_common(day, f"l:{tag}"),
                )
            )
            session.add(
                StorageObservationRecord(
                    observation_id=f"s-{tag}", source_dataset="agsi", facility_id="rehden",
                    facility_name="Rehden", country="DE", inventory_twh=40.0,
                    working_capacity_twh=50.0, fill_pct=80.0, injection_twh_d=0.0,
                    withdrawal_twh_d=0.5, source_system="GIE", **_common(day, f"s:{tag}"),
                )
            )
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)

    response = TestClient(create_app(), headers={"X-Eurogas-Api-Key": "test-public-api-token"}).get(
        "/api/market/nwe-balance?days=3"
    )
    assert response.status_code == 200, response.text
    body = response.json()
    data = body["data"]
    complete = (today - timedelta(days=3)).date().isoformat()
    assert data["history"][-1]["day"] == complete
    assert all(day["norway_gwh"] == 1500.0 for day in data["history"])  # never 500
    assumptions = data["assumptions"]
    assert assumptions["pipeline_complete_through"] == complete
    assert assumptions["pipeline_incomplete_days"] == [
        (today - timedelta(days=2)).date().isoformat(),
        (today - timedelta(days=1)).date().isoformat(),
    ]
    assert "median" in assumptions["pipeline_completeness_rule"]
    assert any("partly reported" in warning for warning in body["meta"]["warnings"])
    # The forecast starts the day after the last complete day, from that day's stock.
    assert data["forecast"][0]["day"] == (today - timedelta(days=2)).date().isoformat()
    assert assumptions["storage_inventory_day"] == complete
