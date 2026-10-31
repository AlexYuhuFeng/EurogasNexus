"""GET /api/portfolio/map-situation: located outages, own contracts, cargoes and slots."""

import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    LngCargoRecord,
    ReferenceNode,
    RegasSlotRecord,
    RemitUmmRecord,
    TradingBookRecord,
    UpstreamResourceContractRecord,
)
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)
from eurogas_nexus.domain.observations.remit_umm import parse_umm_export
from eurogas_nexus.ingestion.infrastructure_geojson import (
    InfrastructureImportError,
    parse_infrastructure,
)
from eurogas_nexus.ingestion.lng_positions import (
    LngImportError,
    parse_lng_cargoes,
    parse_regas_slots,
)

PUBLIC = "test-public-api-token"


def _node(node_id, name, lon, lat, eic=None, node_type="entry_point"):
    return ReferenceNode(
        id=node_id,
        name=name,
        node_type=node_type,
        country="GB",
        lat=lat,
        lon=lon,
        source_system="ENTSOG",
        source_record_id=node_id.removeprefix("entsog-").upper(),
        data_quality="display_approximation",
        metadata_json={"point_eic_code": eic} if eic else {},
    )


def _contract(contract_id, point, book_id, now):
    return UpstreamResourceContractRecord(
        contract_id=contract_id,
        contract_name=f"{contract_id} supply",
        resource_type="PIPELINE_IMPORT",
        delivery_point_name=point,
        gas_year="2026",
        delivery_quantity_mwh_per_day=12_000.0,
        contract_price_gbp_mwh=30.0,
        settlement_frequency="monthly",
        upstream_payment_lag_days=20,
        screen_sale_cash_lag_days=1,
        delivery_tolerance_pct=2.0,
        nomination_tolerance_pct=1.0,
        tolerance_risk_allowance_gbp_mwh=None,
        annual_financing_rate_pct=5.0,
        owned_entry_capacity_mwh_per_day=15_000.0,
        owned_exit_capacity_mwh_per_day=None,
        allowed_exit_points=["NBP"],
        eligible_sale_modes=["LOCAL_MARKET_SALE"],
        notes=None,
        book_id=book_id,
        created_at_utc=now,
        updated_at_utc=now,
    )


def _book(book_id, entity, region, now):
    return TradingBookRecord(
        book_id=book_id,
        name=book_id,
        legal_entity=entity,
        region=region,
        business="gas",
        base_currency="EUR",
        active=True,
        updated_by="t",
        updated_at_utc=now,
    )


@pytest.fixture()
def seeded(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'map.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    now = datetime.now(UTC)
    umms = [
        {
            "messageId": "UMM-1",
            "version": 1,
            "publicationDateTime": (now - timedelta(hours=4)).isoformat(),
            "eventStatus": "Active",
            "unavailabilityType": "Unplanned",
            "eventStart": (now - timedelta(hours=3)).isoformat(),
            "eventStop": (now + timedelta(days=2)).isoformat(),
            "affectedAssetName": "Easington entry",
            "affectedAssetEic": "21Z000000000001X",
            "affectedAssetType": "Transmission",
            "balancingZone": "GB",
            "unitMeasure": "GWh/d",
            "technicalCapacity": 400,
            "unavailableCapacity": 100,
        },
        {
            "messageId": "UMM-NOWHERE",
            "version": 1,
            "publicationDateTime": (now - timedelta(hours=4)).isoformat(),
            "eventStatus": "Active",
            "unavailabilityType": "Planned",
            "eventStart": (now + timedelta(days=1)).isoformat(),
            "eventStop": (now + timedelta(days=3)).isoformat(),
            "affectedAssetName": "Unknown field",
            "affectedAssetType": "Production",
            "balancingZone": "NO",
            "unitMeasure": "mcm/d",
            "unavailableCapacity": 5,
        },
    ]
    headers = {}
    with Session(engine) as session:
        for message in parse_umm_export(json.dumps(umms), source_reference="fixture"):
            session.add(
                RemitUmmRecord(**message.as_record(), source_system="REMIT", ingested_at_utc=now)
            )
        session.add(_node("entsog-easington", "Easington", -0.1, 53.65, eic="21Z000000000001X"))
        session.add(_node("entsog-bacton", "Bacton", 1.45, 52.85))
        session.add(_node("lng-gate", "Gate terminal", 4.0, 51.95, node_type="lng"))
        session.add(_book("uk-nbp", "EGN-UK", "europe", now))
        session.add(_book("ca-gas", "EGN-CA", "north_america", now))
        session.add(_contract("uk-norway", "Easington", "uk-nbp", now))
        session.add(_contract("ca-import", "Bacton", "ca-gas", now))
        session.add(_contract("lost", "Nowhere point", "uk-nbp", now))
        cargo_csv = (
            "cargo_id,vessel_name,status,load_port,load_lat,load_lon,destination_terminal,"
            "eta,position_lat,position_lon,position_at,track,energy_gwh,book_id\n"
            f"C1,Arctic Voyager,laden,Hammerfest,70.68,23.6,Gate terminal,"
            f"{(now + timedelta(days=3)).isoformat()},62.0,4.5,{now.isoformat()},"
            f"23.6 70.68 {(now - timedelta(days=2)).isoformat()};4.5 62.0 {now.isoformat()},"
            "950,uk-nbp\n"
        )
        for row in parse_lng_cargoes(
            cargo_csv, source_system="ETRM", source_reference="t", now_utc=now
        ):
            session.add(LngCargoRecord(**row))
        slot_csv = (
            "slot_id,terminal_name,window_start,window_end,send_out_gwh_d,cargo_id,book_id\n"
            f"S1,Gate terminal,{(now + timedelta(days=3)).isoformat()},"
            f"{(now + timedelta(days=8)).isoformat()},190,C1,uk-nbp\n"
        )
        for row in parse_regas_slots(
            slot_csv, source_system="ETRM", source_reference="t", now_utc=now
        ):
            session.add(RegasSlotRecord(**row))
        for name, scopes in (("head", ["BOOKS:*", "*"]), ("uk", ["BOOKS:ENTITY:EGN-UK"])):
            principal = create_identity_principal(
                session, name=name, display_name=name, role="ANALYST", data_scopes=scopes
            )
            _key, bearer = create_identity_api_key(
                session, principal.principal_id, display_name="t", scopes=["*"]
            )
            headers[name] = {"X-Eurogas-Api-Key": PUBLIC, "X-Eurogas-Identity": bearer}
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    monkeypatch.setenv("EUROGAS_NEXUS_PORTFOLIO_ISOLATION", "true")
    return TestClient(create_app()), headers


def test_situation_locates_what_sources_locate_and_counts_the_rest(seeded):
    client, headers = seeded
    response = client.get("/api/portfolio/map-situation", headers=headers["head"])
    assert response.status_code == 200, response.text
    data = response.json()["data"]

    (outage,) = data["outages"]
    assert outage["event_id"] == "UMM-1"
    assert outage["location"]["ref_id"] == "entsog-easington"
    assert outage["location"]["match"] == "eic"
    assert outage["unavailable_share"] == 0.25
    assert data["unlocated"]["outages"] == 1

    assert sorted(c["contract_id"] for c in data["contracts"]) == ["ca-import", "uk-norway"]
    assert data["unlocated"]["contracts"] == 1

    (cargo,) = data["cargoes"]
    assert cargo["own"] is True and cargo["status"] == "laden"
    assert cargo["destination"]["ref_id"] == "lng-gate"
    assert cargo["track"] == [[23.6, 70.68], [4.5, 62.0]]

    (slot,) = data["regas_slots"]
    assert slot["terminal_name"] == "Gate terminal" and slot["active"] is False
    assert slot["location"]["ref_id"] == "lng-gate"
    assert any("could not be located" in w for w in response.json()["meta"]["warnings"])


def test_regional_head_sees_only_own_book_positions(seeded):
    client, headers = seeded
    data = client.get("/api/portfolio/map-situation", headers=headers["uk"]).json()["data"]
    assert [c["contract_id"] for c in data["contracts"]] == ["uk-norway"]
    assert [c["cargo_id"] for c in data["cargoes"]] == ["C1"]
    # REMIT outages are public market information: every office sees them.
    assert [o["event_id"] for o in data["outages"]] == ["UMM-1"]


def test_cargo_and_slot_imports_refuse_malformed_rows():
    now = datetime.now(UTC)
    with pytest.raises(LngImportError, match="status"):
        parse_lng_cargoes(
            "cargo_id,vessel_name,status,load_port\nC,V,sailing,X\n",
            source_system="KPLER",
            source_reference="t",
            now_utc=now,
        )
    with pytest.raises(LngImportError, match="UTC offset"):
        parse_lng_cargoes(
            "cargo_id,vessel_name,status,load_port,eta\nC,V,laden,X,2026-11-02T10:00\n",
            source_system="KPLER",
            source_reference="t",
            now_utc=now,
        )
    with pytest.raises(LngImportError, match="window_end"):
        parse_regas_slots(
            "slot_id,terminal_name,window_start,window_end\n"
            "S,T,2026-11-02T00:00Z,2026-11-01T00:00Z\n",
            source_system="ETRM",
            source_reference="t",
            now_utc=now,
        )


def test_infrastructure_import_accepts_only_commercial_licences():
    geojson = json.dumps(
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "troll-a",
                    "geometry": {"type": "Point", "coordinates": [3.72, 60.64]},
                    "properties": {"name": "Troll A"},
                },
                {"type": "Feature", "geometry": {"type": "LineString", "coordinates": []}},
            ],
        }
    )
    rows = parse_infrastructure(
        geojson,
        dataset="SODIR-FACILITIES",
        licence="nlod-2.0",
        attribution="Norwegian Offshore Directorate",
        facility_type="production_platform",
        default_country="no",
    )
    assert [(r["name"], r["country"], r["metadata_json"]["licence"]) for r in rows] == [
        ("Troll A", "NO", "NLOD-2.0")
    ]
    with pytest.raises(InfrastructureImportError, match="commercial"):
        parse_infrastructure(
            geojson, dataset="X", licence="CC-BY-NC-4.0", attribution="x", facility_type="field"
        )
