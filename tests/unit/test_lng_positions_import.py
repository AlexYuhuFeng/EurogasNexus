"""QA-L-04: a vessel-feed import keeps what it does not supply and publishes the cargo event."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.lng_positions_import import store_lng_rows
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import LngCargoRecord, MarketEventRecord, RegasSlotRecord
from eurogas_nexus.ingestion.lng_positions import parse_lng_cargoes, parse_regas_slots

NOW = datetime(2026, 11, 24, 14, tzinfo=UTC)

ETRM = (
    "cargo_id,vessel_name,status,load_port,departed_at,destination_terminal,eta,volume_m3,"
    "energy_gwh,book_id\n"
    "SAB-0420,Aurora,laden,Sabine Pass,2026-11-20T08:00:00Z,Gate Terminal,"
    "2026-12-06T06:00:00Z,170000,1130,lng-nwe\n"
)
# The Kpler fix: no book, no volume, no terminal; a new ETA and position, a blank energy.
KPLER = """cargo_id,vessel_name,status,load_port,eta,position_lat,position_lon,position_at,\
energy_gwh
SAB-0420,Aurora,laden,Sabine Pass,2026-12-08T18:00:00Z,38.1,-41.5,2026-11-24T13:00:00Z,
MKT-9,Other Ship,laden,Ras Laffan,2026-12-01T00:00:00Z,20.0,60.0,2026-11-24T13:00:00Z,
"""


def _session(tmp_path) -> Session:
    engine = create_engine(f"sqlite+pysqlite:///{(tmp_path / 'lng.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    return Session(engine)


def _load(session, text: str, source: str, at: datetime) -> dict:
    rows = parse_lng_cargoes(
        text, source_system=source, source_reference=f"{source.lower()}:file", now_utc=at
    )
    result = store_lng_rows(session, "cargo", rows, now_utc=at)
    session.commit()
    return result


def _events(session, cargo_id: str) -> list[MarketEventRecord]:
    return (
        session.query(MarketEventRecord)
        .filter_by(subject_key=f"cargo:{cargo_id}", event_type="cargo.changed")
        .order_by(MarketEventRecord.revision)
        .all()
    )


def test_a_vessel_feed_update_keeps_the_book_and_publishes_the_new_eta(tmp_path):
    with _session(tmp_path) as session:
        first = _load(session, ETRM, "ETRM", NOW - timedelta(days=1))
        assert first["created"] == 1
        assert first["events"]["published"] == {"cargo.changed": 1}

        result = _load(session, KPLER, "KPLER", NOW)

        cargo = session.get(LngCargoRecord, "SAB-0420")
        assert cargo.book_id == "lng-nwe"
        assert cargo.volume_m3 == 170_000
        assert cargo.destination_terminal == "Gate Terminal"
        assert cargo.energy_gwh == 1_130  # a blank cell is not a value
        assert cargo.eta_utc.replace(tzinfo=UTC) == datetime(2026, 12, 8, 18, tzinfo=UTC)
        assert (cargo.position_lat, cargo.position_lon) == (38.1, -41.5)
        assert cargo.source_system == "KPLER"
        assert (result["created"], result["updated"]) == (1, 1)
        # The feed moves an ETA the ETRM set: listed for the desk.
        assert result["eta_disagreements"] == [
            {
                "cargo_id": "SAB-0420",
                "eta_before_utc": "2026-12-06T06:00:00+00:00",
                "eta_before_source": "ETRM",
                "eta_utc": "2026-12-08T18:00:00+00:00",
                "source": "KPLER",
                "hours": 60.0,
            }
        ]
        # The new ETA is a cargo.changed revision, still in the firm's book; the market
        # cargo publishes nothing.
        events = _events(session, "SAB-0420")
        assert [event.revision for event in events] == [1, 2]
        assert events[1].payload_json["book_id"] == "lng-nwe"
        assert events[1].payload_json["eta_utc"].startswith("2026-12-08T18:00")
        assert result["events"]["published"] == {"cargo.changed": 1}
        assert _events(session, "MKT-9") == []
        assert session.get(LngCargoRecord, "MKT-9").book_id is None


def test_a_book_change_and_a_slot_update_are_cargo_events(tmp_path):
    with _session(tmp_path) as session:
        _load(session, ETRM, "ETRM", NOW - timedelta(days=1))
        moved = ETRM.replace(",lng-nwe", ",lng-med")
        _load(session, moved, "ETRM", NOW)
        events = _events(session, "SAB-0420")
        assert [event.payload_json["book_id"] for event in events] == ["lng-nwe", "lng-med"]

        slot = """slot_id,terminal_name,window_start,window_end,send_out_gwh_d,cargo_id,book_id
gate-1,Gate Terminal,2026-12-05T00:00:00Z,2026-12-15T00:00:00Z,110,SAB-0420,lng-med
"""
        rows = parse_regas_slots(
            slot, source_system="ETRM", source_reference="etrm:slots", now_utc=NOW
        )
        store_lng_rows(session, "slot", rows, now_utc=NOW)
        session.commit()
        # The terminal's capacity confirmation updates the window only: cargo and rate stay.
        window = """slot_id,terminal_name,window_start,window_end
gate-1,Gate Terminal,2026-12-06T00:00:00Z,2026-12-16T00:00:00Z
"""
        rows = parse_regas_slots(
            window, source_system="TERMINAL", source_reference="gate:conf", now_utc=NOW
        )
        result = store_lng_rows(session, "slot", rows, now_utc=NOW + timedelta(minutes=1))
        session.commit()
        held = session.get(RegasSlotRecord, "gate-1")
        assert (held.cargo_id, held.book_id, held.send_out_gwh_d) == ("SAB-0420", "lng-med", 110)
        assert result["events"]["published"] == {"cargo.changed": 1}
        events = _events(session, "SAB-0420")
        assert events[-1].payload_json["slot"]["window_start_utc"].startswith("2026-12-06")


def test_an_eta_carries_its_basis_confidence_and_source_lesson_p3(tmp_path):
    with _session(tmp_path) as session:
        _load(session, ETRM, "ETRM", NOW - timedelta(days=1))
        cargo = session.get(LngCargoRecord, "SAB-0420")
        # The ETRM file states no basis: not stated, never inferred from the source.
        assert (cargo.eta_basis, cargo.eta_confidence) == (None, None)
        assert cargo.eta_source == "ETRM"

        feed = (
            "cargo_id,vessel_name,status,load_port,eta,eta_basis,eta_confidence\n"
            "SAB-0420,Aurora,laden,Sabine Pass,2026-12-09T06:00:00Z,AIS,low\n"
        )
        _load(session, feed, "KPLER", NOW)
        session.refresh(cargo)
        assert (cargo.eta_basis, cargo.eta_confidence) == ("ais_declared", "low")
        assert cargo.eta_source == "KPLER"
        assert cargo.eta_recorded_at_utc.replace(tzinfo=UTC) == NOW

        # A position fix without an ETA keeps the ETA's basis and source.
        fix = (
            "cargo_id,vessel_name,status,load_port,position_lat,position_lon\n"
            "SAB-0420,Aurora,laden,Sabine Pass,40.0,-30.0\n"
        )
        _load(session, fix, "SPIRE", NOW + timedelta(hours=1))
        session.refresh(cargo)
        assert (cargo.eta_basis, cargo.eta_source) == ("ais_declared", "KPLER")

        # A new ETA without a basis clears the old one's: it described another ETA.
        manual = (
            "cargo_id,vessel_name,status,load_port,eta\n"
            "SAB-0420,Aurora,laden,Sabine Pass,2026-12-10T06:00:00Z\n"
        )
        _load(session, manual, "MANUAL", NOW + timedelta(hours=2))
        session.refresh(cargo)
        assert (cargo.eta_basis, cargo.eta_confidence, cargo.eta_source) == (
            None, None, "MANUAL"
        )


def test_an_unknown_eta_basis_refuses_the_file():
    import pytest

    from eurogas_nexus.ingestion.lng_positions import LngImportError

    with pytest.raises(LngImportError, match="eta_basis"):
        parse_lng_cargoes(
            "cargo_id,vessel_name,status,load_port,eta,eta_basis\n"
            "X,Y,laden,Z,2026-12-01T00:00:00Z,guess\n",
            source_system="KPLER", source_reference="k", now_utc=NOW,
        )
