"""The cargo-in-transit plan over the API: hedges recorded, schedule changes, what-ifs."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    AuditEventRecord,
    LngCargoHedgeRecord,
    LngCargoRecord,
    LngTerminalTermsRecord,
    MarketEventRecord,
    RegasSlotRecord,
    TradingBookRecord,
)
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)

PUBLIC_TOKEN = "test-public-api-token"


def _cargo(cargo_id: str, now: datetime, *, book: str | None, eta_days: float) -> LngCargoRecord:
    return LngCargoRecord(
        cargo_id=cargo_id,
        vessel_name=f"Vessel {cargo_id}",
        status="laden",
        load_port="Sabine Pass",
        departed_at_utc=now - timedelta(days=5),
        destination_terminal="Gate Terminal",
        eta_utc=now + timedelta(days=eta_days),
        position_lat=46.9,
        position_lon=-14.2,
        position_at_utc=now - timedelta(hours=2),
        energy_gwh=1_000.0,
        book_id=book,
        source_system="ETRM_CSV",
        source_reference=f"etrm:{cargo_id}",
        updated_at_utc=now,
    )


def _setup(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'cargo.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    now = datetime.now(UTC).replace(microsecond=0)
    who = {}
    with Session(engine) as session:
        for name, role in (("analyst", "ANALYST"), ("viewer", "VIEWER")):
            row = create_identity_principal(
                session, name=name, display_name=name, role=role, data_scopes=["*"]
            )
            _key, bearer = create_identity_api_key(
                session, row.principal_id, display_name="t", scopes=["*"]
            )
            who[name] = {"X-Eurogas-Api-Key": PUBLIC_TOKEN, "X-Eurogas-Identity": bearer}
        session.add(
            TradingBookRecord(
                book_id="lng-nwe",
                name="LNG NWE",
                legal_entity="Demo Energy BV",
                region="NWE",
                business="LNG",
                base_currency="EUR",
                active=True,
                updated_by="test",
                updated_at_utc=now,
            )
        )
        session.add(
            LngTerminalTermsRecord(
                terminal_id="gate",
                name="Gate Terminal",
                hub="TTF",
                regas_tariff_per_mwh=1.0,
                fuel_retention_pct=1.0,
                source_note="test terms",
                updated_by="test",
                updated_at_utc=now,
            )
        )
        session.add(_cargo("own-1", now, book="lng-nwe", eta_days=6))
        session.add(_cargo("feed-1", now, book=None, eta_days=6))
        session.add(
            RegasSlotRecord(
                slot_id="gate-slot-1",
                terminal_name="Gate Terminal",
                window_start_utc=now + timedelta(days=5),
                window_end_utc=now + timedelta(days=15),
                send_out_gwh_d=100.0,
                cargo_id="own-1",
                book_id="lng-nwe",
                source_system="ETRM_CSV",
                source_reference="etrm:slot-1",
                updated_at_utc=now,
            )
        )
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return engine, who, now


def test_plan_follows_energy_from_eta_to_hub_months(tmp_path, monkeypatch):
    _engine, who, _now = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())

    response = client.get("/api/lng/cargoes/own-1/plan", headers=who["viewer"])
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    plan = data["plan"]
    assert plan["slot_status"] == "on_time"
    assert 0 < plan["boil_off_mwh"] < 20_000  # 11 days at the desk standard 0.10 %/day
    assert plan["gas_in_kind_mwh"] > 0  # Gate's 1 % from the firm's terms
    assert sum(item["physical_mwh"] for item in plan["months"]) == pytest.approx(
        plan["delivered_mwh"], abs=1
    )
    assert all(item["hub"] == "TTF" for item in plan["months"])
    assert {row["input"] for row in data["inputs"]} >= {"ETA", "boil-off", "hedges"}
    assert any("desk standard" in row["source"] for row in data["inputs"])
    assert data["last_change"] is None
    # Unhedged, so every month's gas is to sell: forward where the month still trades, at
    # short notice where it has stopped (which months depends on today's date).
    kinds = {item["kind"] for item in plan["suggestions"]} - {"deadline"}
    assert kinds and kinds <= {"sell", "short_notice"}
    assert all(item["mwh"] > 0 for item in plan["suggestions"] if item["kind"] != "deadline")


def test_recorded_hedges_and_a_slipped_eta_show_what_changed(tmp_path, monkeypatch):
    engine, who, now = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())
    plan = client.get("/api/lng/cargoes/own-1/plan", headers=who["viewer"]).json()["data"]["plan"]
    legs = [
        {"hub": "TTF", "month": item["month"], "mwh": -round(item["physical_mwh"])}
        for item in plan["months"]
    ]

    refused = client.put(
        "/api/lng/cargoes/own-1/hedges", headers=who["viewer"], json={"legs": legs}
    )
    assert refused.status_code == 403
    recorded = client.put(
        "/api/lng/cargoes/own-1/hedges", headers=who["analyst"], json={"legs": legs}
    )
    assert recorded.status_code == 200, recorded.text
    assert recorded.json()["data"]["events"]["published"] == {"cargo.changed": 1}

    hedged = client.get("/api/lng/cargoes/own-1/plan", headers=who["viewer"]).json()["data"]
    assert all(abs(item["net_mwh"]) < 1 for item in hedged["plan"]["months"])
    assert not [s for s in hedged["plan"]["suggestions"] if s["kind"] in {"sell", "roll"}]
    # Recording the hedges is the cargo's first event: nothing earlier to compare with.
    assert hedged["last_change"] is None

    # The vessel feed reports a new ETA past the slot window (an import publishes it).
    from eurogas_nexus.application.market_event_capture import capture_desk

    with Session(engine) as session:
        row = session.get(LngCargoRecord, "own-1")
        row.eta_utc = now + timedelta(days=20)
        capture_desk(session, cargo_ids=["own-1"], now_utc=now + timedelta(minutes=5))
        session.commit()

    slipped = client.get("/api/lng/cargoes/own-1/plan", headers=who["viewer"]).json()["data"]
    assert slipped["plan"]["slot_status"] == "missed"
    assert slipped["last_change"]["headline"] == "The new ETA misses the slot window."
    assert slipped["plan"]["suggestions"][0]["kind"] == "find_slot"
    assert "of hedges no longer has gas behind it" in slipped["plan"]["suggestions"][0]["text"]

    board = client.get("/api/lng/cargoes/plans", headers=who["viewer"]).json()["data"]
    assert [line["cargo_id"] for line in board] == ["own-1"]  # the feed cargo is not the firm's
    assert board[0]["slot_status"] == "missed"
    assert board[0]["headline"] == "The new ETA misses the slot window."

    with Session(engine) as session:
        held = session.query(LngCargoHedgeRecord).filter_by(cargo_id="own-1").all()
        assert len(held) == len(legs) and all(leg.retired_at_utc is None for leg in held)
        events = (
            session.query(MarketEventRecord)
            .filter_by(subject_key="cargo:own-1")
            .order_by(MarketEventRecord.revision)
            .all()
        )
        assert [event.revision for event in events] == [1, 2]
        assert events[1].payload_json["hedges"]  # the plan before can be rebuilt
        assert session.query(AuditEventRecord).filter_by(action="lng.cargo_hedges").count() == 1


def test_the_board_and_plan_carry_what_the_cargo_screen_shows(tmp_path, monkeypatch):
    """Additive fields for the cargo board and plan screen (QA-L-05): the slot window, the hub,
    the next action and expiry, the hub months, what last changed and who, the hedge legs with
    their author, and the slots a what-if may move the cargo to."""

    engine, who, now = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())
    with Session(engine) as session:
        session.add(
            RegasSlotRecord(
                slot_id="gate-slot-2",
                terminal_name="Gate Terminal",
                window_start_utc=now + timedelta(days=20),
                window_end_utc=now + timedelta(days=22),
                send_out_gwh_d=100.0,
                cargo_id="other-cargo",
                book_id="lng-nwe",
                source_system="ETRM_CSV",
                source_reference="etrm:slot-2",
                updated_at_utc=now,
            )
        )
        session.commit()
    legs = [{"hub": "TTF", "month": "2030-01", "mwh": -50_000, "reference": "ICE 42"}]
    assert client.put(
        "/api/lng/cargoes/own-1/hedges", headers=who["analyst"], json={"legs": legs}
    ).status_code == 200

    from eurogas_nexus.application.market_event_capture import capture_desk

    with Session(engine) as session:
        row = session.get(LngCargoRecord, "own-1")
        row.eta_utc = now + timedelta(days=7)
        capture_desk(session, cargo_ids=["own-1"], now_utc=now + timedelta(minutes=5))
        session.commit()

    data = client.get("/api/lng/cargoes/own-1/plan", headers=who["viewer"]).json()["data"]
    cargo = data["cargo"]
    assert cargo["hub"] == "TTF"
    assert cargo["slot"]["slot_id"] == "gate-slot-1"
    assert cargo["slot"]["send_out_mwh_per_day"] == 100_000.0
    assert cargo["imported_at_utc"] and cargo["departed_at_utc"]
    assert cargo["loaded_mwh"] == 1_000_000.0
    plan = data["plan"]
    assert cargo["loaded_mwh"] == pytest.approx(
        plan["boil_off_mwh"] + plan["gas_in_kind_mwh"] + plan["delivered_mwh"], abs=0.5
    )
    assert cargo["changed"]["kinds"] == ["eta"]
    assert cargo["changed"]["by"] == "import ETRM_CSV"
    assert cargo["changed"]["eta_before_utc"] == (now + timedelta(days=6)).isoformat()
    assert data["hedges"][0]["reference"] == "ICE 42"
    assert data["hedges"][0]["created_by"]
    options = {item["slot_id"]: item for item in data["slot_options"]}
    assert options["gate-slot-1"]["free"] is True  # its own slot
    assert options["gate-slot-2"]["free"] is False
    assert options["gate-slot-2"]["held_by"] == "other-cargo"
    assert data["plan"]["send_out_end_utc"]

    board = client.get("/api/lng/cargoes/plans", headers=who["viewer"]).json()["data"]
    line = board[0]
    assert line["hub"] == "TTF" and line["slot"]["slot_id"] == "gate-slot-1"
    assert line["months"] == data["plan"]["months"]
    assert line["next_action"]["kind"] != "deadline"
    actions = [item for item in data["plan"]["suggestions"] if item["kind"] != "deadline"]
    dues = sorted(item["due_utc"] for item in actions if item["due_utc"])
    if dues:
        assert line["next_action"]["due_utc"] == dues[0]
    assert line["next_expiry"] is None or line["next_expiry"]["kind"] == "deadline"


def test_replacing_hedges_retires_the_old_set(tmp_path, monkeypatch):
    engine, who, _now = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())
    first = [{"hub": "TTF", "month": "2027-01", "mwh": -100_000}]
    second = [{"hub": "TTF", "month": "2027-02", "mwh": -100_000, "reference": "EEX 123"}]
    for legs in (first, second):
        assert (
            client.put(
                "/api/lng/cargoes/own-1/hedges", headers=who["analyst"], json={"legs": legs}
            ).status_code
            == 200
        )
    with Session(engine) as session:
        rows = session.query(LngCargoHedgeRecord).order_by(LngCargoHedgeRecord.created_at_utc)
        states = sorted((row.delivery_month, row.retired_at_utc is None) for row in rows)
    assert states == [("2027-01", False), ("2027-02", True)]

    bad = client.put(
        "/api/lng/cargoes/own-1/hedges",
        headers=who["analyst"],
        json={"legs": [{"hub": "NOPE", "month": "2027-01", "mwh": -1}]},
    )
    assert bad.status_code == 422
    assert bad.json()["detail"]["code"] == "hub_unknown"


def test_what_if_compares_without_storing(tmp_path, monkeypatch):
    engine, who, now = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())

    later = client.post(
        "/api/lng/cargoes/own-1/plan/what-if",
        headers=who["viewer"],
        json={
            "eta_utc": (now + timedelta(days=9)).isoformat(),
            "berth_delay_hours": 48,
            "demurrage_per_day": 90_000,
        },
    )
    assert later.status_code == 200, later.text
    change = later.json()["data"]["change"]
    assert change["boil_off_change_mwh"] > 0
    assert change["delivered_change_mwh"] < 0
    assert change["before"]["slot_status"] == "on_time"
    after = change["after"]
    assert after["demurrage_hours"] == 12.0
    assert after["demurrage_cost"] == 45_000.0

    missed = client.post(
        "/api/lng/cargoes/own-1/plan/what-if",
        headers=who["viewer"],
        json={"eta_utc": (now + timedelta(days=16)).isoformat()},
    ).json()["data"]["change"]
    assert missed["headline"] == "The new ETA misses the slot window."
    with Session(engine) as session:
        assert session.query(MarketEventRecord).count() == 0
        assert session.get(LngCargoRecord, "own-1").eta_utc.replace(tzinfo=UTC) == now + (
            timedelta(days=6)
        )


def test_a_market_cargo_has_no_plan(tmp_path, monkeypatch):
    _engine, who, _now = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())

    for cargo_id in ("feed-1", "nobody"):
        response = client.get(f"/api/lng/cargoes/{cargo_id}/plan", headers=who["viewer"])
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "cargo_not_found"
