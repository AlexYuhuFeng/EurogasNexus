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
            f"C0,Arctic Voyager,delivered,Hammerfest,70.68,23.6,Gate terminal,"
            f"{(now - timedelta(days=30)).isoformat()},51.95,4.0,"
            f"{(now - timedelta(days=30)).isoformat()},"
            f"23.6 70.68 {(now - timedelta(days=36)).isoformat()};"
            f"4.0 51.95 {(now - timedelta(days=30)).isoformat()},"
            "940,uk-nbp\n"
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
    # The count is of every outage, placed or not, so it agrees with the ticker.
    totals = data["totals"]
    assert totals["outages_active"] + totals["outages_scheduled"] == 2

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


def test_a_delivered_cargo_comes_back_with_its_timed_track_only_when_history_is_asked(seeded):
    client, headers = seeded
    live = client.get("/api/portfolio/map-situation", headers=headers["head"]).json()["data"]
    assert [c["cargo_id"] for c in live["cargoes"]] == ["C1"]
    assert len(live["cargoes"][0]["track_times"]) == 2

    looked_back = client.get(
        "/api/portfolio/map-situation?history_days=90", headers=headers["head"]
    ).json()["data"]
    delivered = next(c for c in looked_back["cargoes"] if c["cargo_id"] == "C0")
    assert delivered["status"] == "delivered"
    assert delivered["track"] == [[23.6, 70.68], [4.0, 51.95]]
    assert all(isinstance(when, str) for when in delivered["track_times"])


def test_our_book_view_lists_what_relates_to_the_deals_and_why(seeded):
    """Design basis 2, J.5: ours (deals, their hubs, paths, capacity, cargoes, slots) and
    reachable (neighbouring market areas along the proven adjacency), derived from the store."""

    import os

    client, headers = seeded
    engine = create_engine(os.environ["RUNTIME_STORE_DATABASE_URL"], future=True)
    now = datetime.now(UTC)
    with Session(engine) as session:
        # Bought at TTF to be sold at NBP: its priced path crosses BBL.
        session.add(_contract("nl-ttf", "TTF", "uk-nbp", now))
        session.commit()

    book = client.get("/api/portfolio/map-situation", headers=headers["uk"]).json()["data"][
        "book_relevance"
    ]
    ours = {(item["kind"], item["name"]): item for item in book["ours"]}
    # Each item says why it is on the book view.
    point = ours[("point", "Easington")]
    assert point["reasons"][0] == {
        "key": "delivery_point",
        "contract": "uk-norway supply",
        "counterparty": None,
        "mwh_d": 12_000.0,
    }
    assert ours[("capacity", "Easington")]["reasons"][0]["key"] == "held_capacity"
    assert ours[("hub", "TTF")]["reasons"] == [{"key": "contract_hub", "contract": "nl-ttf supply"}]
    assert ours[("cargo", "Arctic Voyager")]["reasons"][0]["key"] == "expected_cargo"
    assert {reason["key"] for reason in ours[("terminal", "Gate terminal")]["reasons"]} == {
        "expected_cargo",
        "regas_slot",
    }
    # The contract's priced path to its allowed exit, along the proven adjacency.
    (path,) = book["contract_paths"]
    assert (path["from_hub"], path["to_hub"]) == ("TTF", "NBP")
    assert ("point", "Bacton (BBL)") in ours
    # Reachable from TTF: NBP through BBL, with the gaps named (no price or tariff held here).
    reach = {(item["from_hub"], item["to_hub"]): item for item in book["reachable"]}
    to_nbp = reach[("TTF", "NBP")]
    assert to_nbp["crossings_count"] == 1 and "Bacton (BBL)" in to_nbp["via"]
    assert to_nbp["indicative"] is True
    assert to_nbp["net_gbp_mwh"] is None and to_nbp["tariff_status"] == "missing"
    assert to_nbp["missing_legs"]
    assert all(item["crossings_count"] <= 2 for item in book["reachable"])
    # The outage at our delivery point touches the book; the opportunity class waits for
    # the opportunity core.
    assert book["outages_touching"] == ["UMM-1"]
    assert book["opportunities"] == []
    # Another office's contract is not on this caller's book view.
    assert not any(
        reason.get("contract") == "ca-import supply"
        for item in book["ours"]
        for reason in item["reasons"]
    )


def _opportunity(opp_id, state, buy, sell, book, now, opp_type="locational", headline="1.250"):
    from decimal import Decimal

    from eurogas_nexus.db.models import OpportunityRecord

    return OpportunityRecord(
        opportunity_id=opp_id,
        opp_key=f"key-{opp_id}",
        type=opp_type,
        lane="could_act",
        state=state,
        assessed_state=state,
        version=1,
        claim_key="locational.spread",
        claim_fields={"buy_hub": buy, "sell_hub": sell} if buy else {"subject": "x"},
        claim_text=f"Buy {buy}, sell {sell}",
        headline_value=Decimal(headline),
        headline_unit="EUR/MWh",
        period_label="2026-12",
        period_start=now.date(),
        period_end=(now + timedelta(days=30)).date(),
        quality_class="sourced",
        simulated=False,
        book_ids=[book],
        source_families=[],
        reasons=[],
        first_seen_utc=now,
        last_evaluated_utc=now,
        last_changed_utc=now,
        consecutive_seen=1,
        consecutive_missed=0,
        surfaced=True,
        expires_at_utc=now + timedelta(days=1),
        snapshot_id="s1",
        evaluation_id="e1",
        evaluator="locational",
        evaluator_version="1",
    )


def test_our_book_view_draws_the_callers_opportunity_paths(seeded):
    """CP-21: the opportunity class comes from the opportunity core, in the caller's scope:
    a path between two hubs, the core's headline, actionable popped out and watch outlined."""

    import os

    client, headers = seeded
    engine = create_engine(os.environ["RUNTIME_STORE_DATABASE_URL"], future=True)
    now = datetime.now(UTC)
    with Session(engine) as session:
        # TTF is one of this office's market areas (a contract delivered there).
        session.add(_contract("nl-ttf", "TTF", "uk-nbp", now))
        session.add_all(
            [
                _opportunity("o-act", "actionable", "TTF", "THE", "uk-nbp", now),
                _opportunity("o-watch", "watch", "NBP", "ZTP", "uk-nbp", now, headline="0.300"),
                _opportunity("o-blocked", "blocked", "TTF", "NBP", "uk-nbp", now),
                _opportunity("o-hedge", "actionable", None, None, "uk-nbp", now, "hedge_gap"),
                _opportunity("o-other", "actionable", "TTF", "ZTP", "ca-gas", now),
            ]
        )
        session.commit()

    book = client.get("/api/portfolio/map-situation", headers=headers["uk"]).json()["data"][
        "book_relevance"
    ]
    paths = {item["opportunity_id"]: item for item in book["opportunities"]}
    # Another office's opportunity, a blocked one and one without two hubs are not drawn.
    assert sorted(paths) == ["o-act", "o-watch"]
    act = paths["o-act"]
    assert (act["from_hub"], act["to_hub"], act["emphasis"]) == ("TTF", "THE", "pop")
    assert act["headline"] == {"value": "1.25", "unit": "EUR/MWh"}
    assert act["path_node_ids"][0] != act["path_node_ids"][-1] and len(act["path_node_ids"]) >= 3
    assert act["type_code"] == "L"
    assert paths["o-watch"]["emphasis"] == "outline"
    # No route stated on these records: drawn along the default proven crossing, said so.
    assert act["route_stated"] is False
    # Whether the opportunity starts or ends at one of our hubs.
    assert paths["o-act"]["relation"] == "on_book"
    # NBP to ZTP touches none of this office's hubs; NBP is a crossing away from TTF.
    assert paths["o-watch"]["relation"] == "adjacent"
    assert book["arrivals"] == []
    # The head office sees both offices' opportunities.
    head = client.get("/api/portfolio/map-situation", headers=headers["head"]).json()["data"]
    assert "o-other" in {item["opportunity_id"] for item in head["book_relevance"]["opportunities"]}


def test_an_opportunity_draws_the_crossing_its_evaluator_priced(seeded):
    """claim_fields route_points (ENTSOG point keys in flow order) fixes the crossing."""

    import os

    client, headers = seeded
    engine = create_engine(os.environ["RUNTIME_STORE_DATABASE_URL"], future=True)
    now = datetime.now(UTC)
    with Session(engine) as session:
        session.add(_contract("nl-ttf", "TTF", "uk-nbp", now))
        priced = _opportunity("o-bbl", "actionable", "TTF", "NBP", "uk-nbp", now)
        priced.claim_fields = {
            "buy_hub": "TTF",
            "sell_hub": "NBP",
            "route_points": "ITP-00063,ITP-00207",
        }
        session.add(priced)
        session.commit()
    book = client.get("/api/portfolio/map-situation", headers=headers["uk"]).json()["data"][
        "book_relevance"
    ]
    (item,) = book["opportunities"]
    assert item["route_stated"] is True
    assert item["relation"] == "on_book"
    assert "Bacton (BBL)" in item["via"]


def test_book_view_says_how_much_of_ours_each_disruption_touches(seeded):
    """An active outage at a contract's delivery point pulses, with the contracts and their
    delivery it touches; the contract's gas-year window says how much has been delivered."""

    client, headers = seeded
    book = client.get("/api/portfolio/map-situation", headers=headers["uk"]).json()["data"][
        "book_relevance"
    ]
    (easington,) = [item for item in book["disruptions"] if item["event_id"] == "UMM-1"]
    assert easington["placement"] == "point"
    assert easington["touches"] == "ours"
    assert easington["contracts"] == ["uk-norway supply"]
    assert easington["affected_mwh_d"] == 12000.0
    assert easington["pulse"] is True
    assert easington["end_utc"]
    period = book["contract_periods"]["uk-norway"]
    assert period["start"] == "2026-10-01" and period["end"] == "2027-10-01"
    assert 0 <= period["elapsed_days"] <= period["total_days"] == 365


def test_an_outage_no_source_positions_is_placed_at_its_zone_hub_when_we_hold_it():
    from eurogas_nexus.application.map_book import _disruptions

    out = _disruptions(
        [],
        [
            {
                "event_id": "Z1",
                "facility_name": "A field",
                "balancing_zone": "TTF",
                "status": "scheduled",
                "source_system": "DEMO",
            },
            {"event_id": "Z2", "facility_name": "Elsewhere", "balancing_zone": "PEG"},
        ],
        ours_items=[],
        contract_paths=[],
        reachable_refs=set(),
        opportunity_refs=set(),
        ours_hubs={"TTF": ["A supply", "B supply"]},
        hub_location=lambda hub: {"lon": 4.9, "lat": 52.1},
        mwh_by_contract={"A supply": 18000.0, "B supply": 6000.0},
    )
    (item,) = out
    assert item["placement"] == "zone" and item["hub"] == "TTF"
    assert item["affected_mwh_d"] == 24000.0
    assert item["simulated"] is True
    # Scheduled, not yet out: a quiet mark, no pulse.
    assert item["pulse"] is False


def test_a_reroute_is_drawn_against_the_way_the_volume_goes_now(seeded):
    """claim_fields current_sell_hub (and the per-side texts) give a now-against-proposed
    reading; every figure is the record's own, the rest reads as not stated."""

    import os
    from decimal import Decimal

    from eurogas_nexus.db.models.opportunities import (
        OpportunityCheckRecord,
        OpportunityLegRecord,
    )

    client, headers = seeded
    engine = create_engine(os.environ["RUNTIME_STORE_DATABASE_URL"], future=True)
    now = datetime.now(UTC)
    with Session(engine) as session:
        session.add(_contract("nl-ttf", "TTF", "uk-nbp", now))
        reroute = _opportunity("o-r", "actionable", "TTF", "NBP", "uk-nbp", now, opp_type="reroute")
        reroute.claim_fields = {
            "buy_hub": "TTF",
            "sell_hub": "NBP",
            "current_sell_hub": "TTF",
            "route_points": "ITP-00063,ITP-00207",
            "tariff": "0.92 EUR/MWh",
            "margin": "+0.35 EUR/MWh",
            "current_margin": "+0.00 EUR/MWh",
        }
        session.add(reroute)
        session.flush()
        session.add(
            OpportunityLegRecord(
                opportunity_id="o-r",
                seq=1,
                kind="term",
                label_key="reroute.with_routes",
                label="NBP day-ahead",
                rate_value=Decimal("31.2"),
                rate_unit="GBP/MWh",
                input_class="sourced",
                source_family="ICE Endex",
                source_ref="NBP DA settlement",
                as_of_utc=now,
            )
        )
        session.add(
            OpportunityCheckRecord(
                opportunity_id="o-r",
                seq=1,
                kind="capacity",
                result="pass",
                figure="route capacity 6,000 MWh/d",
            )
        )
        session.commit()
    book = client.get("/api/portfolio/map-situation", headers=headers["uk"]).json()["data"][
        "book_relevance"
    ]
    (item,) = book["opportunities"]
    proposal = item["proposal"]
    assert proposal["now"]["via"] == [] and proposal["now"]["to_hub"] == "TTF"
    assert len(proposal["current_path_node_ids"]) == 1
    assert "Bacton (BBL)" in proposal["proposed"]["via"]
    assert proposal["proposed"]["tariff"] == "0.92 EUR/MWh"
    assert proposal["proposed"]["capacity"] == "route capacity 6,000 MWh/d"
    assert proposal["now"]["tariff"] is None
    assert proposal["benefit"]["headline"]["value"] is not None
    (evidence,) = proposal["evidence"]
    assert evidence["source_family"] == "ICE Endex" and evidence["as_of_utc"]


def test_an_unchanged_situation_revalidates_as_not_modified(seeded):
    """The map re-reads on return and on a timer: an unchanged picture is a 304 with no body,
    though it was computed again (its as_of_utc is not part of the tag)."""

    client, headers = seeded
    first = client.get("/api/portfolio/map-situation", headers=headers["uk"])
    assert first.status_code == 200
    etag = first.headers["etag"]
    assert first.headers["cache-control"] == "private, no-cache"
    again = client.get(
        "/api/portfolio/map-situation", headers={**headers["uk"], "If-None-Match": etag}
    )
    assert again.status_code == 304
    assert again.content == b""
    # Another caller's picture has its own tag.
    other = client.get(
        "/api/portfolio/map-situation", headers={**headers["head"], "If-None-Match": etag}
    )
    assert other.status_code == 200


def test_a_reroute_that_names_no_hubs_is_drawn_along_its_stated_route(seeded):
    """The R evaluator states the re-routed path (route_points) and no buy/sell hubs."""

    import os

    client, headers = seeded
    engine = create_engine(os.environ["RUNTIME_STORE_DATABASE_URL"], future=True)
    now = datetime.now(UTC)
    with Session(engine) as session:
        session.add(_contract("nl-ttf", "TTF", "uk-nbp", now))
        reroute = _opportunity("o-r2", "actionable", None, None, "uk-nbp", now, opp_type="reroute")
        reroute.claim_fields = {"resource": "r1", "route_points": "ITP-00063,ITP-00207"}
        session.add(reroute)
        session.commit()
    book = client.get("/api/portfolio/map-situation", headers=headers["uk"]).json()["data"][
        "book_relevance"
    ]
    (item,) = book["opportunities"]
    assert (item["from_hub"], item["to_hub"]) == ("TTF", "NBP")
    assert item["route_stated"] is True
