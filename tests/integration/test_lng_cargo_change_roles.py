"""LNG-2 acceptance: a cargo change reaches the trader, scheduler, risk and desk head.

The owner's scenario (2026-11-24): a firm cargo due at Gate in three days is hedged forward
month by month; the vessel feed then reports it four days late. The chain is driven as it
runs in production: an import commits the ETA with its ``cargo.changed`` event, the outbox
delivers it to the ``cargo_roles`` consumer, the consumer rebuilds the plan and raises one
alert per role, and the notification dispatcher sends each role's message to the channel
subscribed to its category. Criteria LNG2-1 to LNG2-5 in
docs/engineering/Commercial-Intelligence-V3/06_ACCEPTANCE_CRITERIA.md.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application import market_events
from eurogas_nexus.application.lng_cargo_alerts import CONSUMER_NAME, open_messages
from eurogas_nexus.application.lng_in_transit import record_hedges, send_out_plan
from eurogas_nexus.application.lng_positions_import import store_lng_rows
from eurogas_nexus.application.market_event_capture import capture_desk
from eurogas_nexus.application.monitoring_service import scan_monitoring_conditions
from eurogas_nexus.application.notifications import dispatch, mirror_monitoring_alerts
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    LngCargoHedgeRecord,
    LngCargoRecord,
    LngTerminalTermsRecord,
    MonitoringAlertRecord,
    NotificationChannelRecord,
    NotificationOutboxRecord,
    RegasSlotRecord,
    TraderMandateRecord,
    TradingBookRecord,
)
from eurogas_nexus.ingestion.lng_positions import parse_lng_cargoes, parse_regas_slots

#: Tuesday 24 November 2026: the Nov contract stopped trading on 29 Oct, Dec trades until the
#: close of Friday 27 Nov, Jan until 30 Dec.
NOW = datetime(2026, 11, 24, 9, 0, tzinfo=UTC)
ETA = datetime(2026, 11, 27, 9, 0, tzinfo=UTC)  # due in three days
LATE = ETA + timedelta(days=4)
CARGO = "SAB-0420"
CHANNELS = {
    "trader": "cargo",
    "scheduler": "nomination",
    "risk": "limits",
    "desk_head": "desk_head",
}


@pytest.fixture()
def desk(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'lng2.sqlite').as_posix()}"
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    with Session(engine) as session:
        session.add(TradingBookRecord(
            book_id="lng-nwe", name="LNG NWE", legal_entity="Demo Energy BV", region="NWE",
            business="LNG", base_currency="EUR", active=True, updated_by="t",
            updated_at_utc=NOW,
        ))
        session.add(LngTerminalTermsRecord(
            terminal_id="gate", name="Gate Terminal", hub="TTF", regas_tariff_per_mwh=1.0,
            fuel_retention_pct=1.0, source_note="test terms", updated_by="t",
            updated_at_utc=NOW,
        ))
        session.add(LngCargoRecord(
            cargo_id=CARGO, vessel_name="Aurora", status="laden", load_port="Sabine Pass",
            departed_at_utc=datetime(2026, 11, 10, 6, tzinfo=UTC),
            destination_terminal="Gate Terminal", eta_utc=ETA, energy_gwh=1_000.0,
            book_id="lng-nwe", source_system="ETRM", source_reference="etrm:cargo",
            updated_at_utc=NOW - timedelta(days=1),
            eta_source="ETRM", eta_recorded_at_utc=NOW - timedelta(days=1),
            eta_basis="schedule", eta_confidence="medium",
        ))
        session.add(RegasSlotRecord(
            slot_id="gate-1", terminal_name="Gate Terminal",
            window_start_utc=datetime(2026, 11, 26, tzinfo=UTC),
            window_end_utc=datetime(2026, 12, 6, tzinfo=UTC),
            send_out_gwh_d=100.0, cargo_id=CARGO, book_id="lng-nwe", source_system="ETRM",
            source_reference="etrm:slot", updated_at_utc=NOW - timedelta(days=1),
        ))
        session.add(TraderMandateRecord(
            mandate_id="m-lng", trader="lng.trader", display_name="LNG desk",
            book_ids=["lng-nwe"], hubs=["TTF"], max_net_mwh_per_month=300_000,
            physical_allowed=True, financial_allowed=True, updated_by="t",
            updated_at_utc=NOW,
        ))
        for role, category in CHANNELS.items():
            session.add(NotificationChannelRecord(
                channel_id=f"ch-{role}", name=role, kind="email",
                recipients=f"{role}@desk.example", categories=[category], min_severity="info",
                enabled=True, updated_by="t", updated_at_utc=NOW,
            ))
        session.flush()
        # Hedged forward to the plan: each month's send-out sold, recorded on the cargo.
        plan, _slot = send_out_plan(session, CARGO, now=NOW)
        for cover in plan.months:
            session.add(LngCargoHedgeRecord(
                link_id=uuid4().hex, cargo_id=CARGO, hub=cover.hub,
                delivery_month=cover.month, mwh=-round(cover.physical_mwh), reference=None,
                created_at_utc=NOW - timedelta(hours=20), created_by="lng.trader",
            ))
        capture_desk(session, cargo_ids=[CARGO], now_utc=NOW - timedelta(hours=1))
        session.commit()
        assert _drain(session, NOW)["cargoes"][0]["roles"] == {
            role: "first_recorded" for role in CHANNELS
        }
    yield engine
    engine.dispose()


def _drain(session, at: datetime) -> dict:
    summary = market_events.process(session, CONSUMER_NAME, now_utc=at)
    session.commit()
    assert summary["failed"] == 0, summary
    return summary["result"] or {}


def _import_eta(session, eta: datetime, at: datetime, *, source="KPLER", basis="AIS",
                confidence="low") -> dict:
    text = (
        "cargo_id,vessel_name,status,load_port,eta,eta_basis,eta_confidence\n"
        f"{CARGO},Aurora,laden,Sabine Pass,{eta.isoformat()},{basis},{confidence}\n"
    )
    rows = parse_lng_cargoes(text, source_system=source, source_reference=f"{source}:f",
                             now_utc=at)
    result = store_lng_rows(session, "cargo", rows, now_utc=at)
    session.commit()
    return result


def _alerts(session) -> dict[str, MonitoringAlertRecord]:
    from eurogas_nexus.application.lng_cargo_alerts import role_of

    return {
        role_of(row.category): row
        for row in session.query(MonitoringAlertRecord)
        .filter(MonitoringAlertRecord.entity_id == CARGO)
        .all()
    }


def _sent(session, at: datetime) -> dict[str, list]:
    sent: dict[str, list] = {}
    dispatch(session, now=at, senders={
        "email": lambda channel, message: sent.setdefault(channel.name, []).append(message)
    })
    session.commit()
    return sent


def test_a_late_cargo_reaches_each_role_with_its_own_message(desk) -> None:
    """LNG2-1 to LNG2-4 on the owner's scenario."""

    with Session(desk) as session:
        started = time.perf_counter()
        imported = _import_eta(session, LATE, NOW)
        # LNG2-1: the vessel feed's ETA is one cargo.changed event.
        assert imported["events"]["published"] == {"cargo.changed": 1}
        result = _drain(session, NOW + timedelta(seconds=1))
        queued_after = time.perf_counter() - started
        roles = result["cargoes"][0]["roles"]
        assert roles == {role: "notified" for role in CHANNELS}
        alerts = _alerts(session)
        assert set(alerts) == set(CHANNELS)
        assert {role: row.category for role, row in alerts.items()} == {
            "trader": "lng_hedge", "scheduler": "lng_schedule", "risk": "lng_exposure",
            "desk_head": "lng_material",
        }

        # LNG2-2 / LNG2-3 trader: the gas left November (no longer trading) and moved into
        # December (trading until Friday's close): buy back Nov at short notice, sell Dec.
        trader = alerts["trader"].evidence_snapshot["message"]
        kinds = {item["kind"]: item for item in trader["items"]}
        assert set(kinds) == {"short_notice", "sell"}
        nov, dec = kinds["short_notice"], kinds["sell"]
        assert (nov["from_month"], dec["from_month"]) == ("2026-11", "2026-12")
        assert nov["mwh"] < 0 and dec["mwh"] > 0
        # What left Nov arrives in Dec, less four more days of boil-off at 0.10 %/day.
        assert -nov["mwh"] - dec["mwh"] == pytest.approx(4_000, abs=100)
        assert "physical 0 + hedge" in nov["arithmetic"]
        assert "= net" in dec["arithmetic"] and "sell" in dec["arithmetic"]
        assert dec["due_utc"] == "2026-11-28T00:00:00+00:00"
        assert alerts["trader"].severity == "critical"  # a month already stopped trading
        assert alerts["trader"].human_review_required is True
        body = " ".join(trader["lines_en"])
        assert "nothing is traded" in body
        assert "confirm it before you act" in body  # an AIS ETA, low confidence

        # Scheduler: berth, send-out by gas day and the nomination cut-offs it hits.
        scheduler = alerts["scheduler"].evidence_snapshot["message"]
        berth = next(item for item in scheduler["items"] if item["key"] == "berth")
        assert berth["berth_before_utc"].startswith("2026-11-27T09:00")
        assert berth["berth_after_utc"].startswith("2026-12-01T09:00")
        days = [item for item in scheduler["items"] if item["key"].startswith("gas_day:")]
        assert days[0]["gas_day"] == "2026-11-27" and days[0]["send_out_after_mwh"] == 0
        assert all(item["cutoff"]["action"] == "nominate" for item in days)
        assert all(not item["cutoff"]["passed"] for item in days)
        assert scheduler["due_utc"] == days[0]["cutoff"]["at_utc"]

        # Risk: the net exposure by month and the mandate it moves into breach.
        risk = alerts["risk"].evidence_snapshot["message"]
        months = {item["month"]: item for item in risk["items"] if "month" in item}
        assert months["2026-11"]["net_before_mwh"] == pytest.approx(0, abs=1)
        assert months["2026-11"]["net_after_mwh"] < -300_000
        assert months["2026-12"]["net_after_mwh"] > 300_000
        mandate = next(item for item in risk["items"] if item["key"] == "mandate:m-lng")
        # Before, the hedged cargo left the mandate short of a breach (the remaining days of
        # a month count, so Nov reads partly open); after, Dec's open 380 GWh is over 300 GWh.
        assert mandate["status_before"] != "breach" and mandate["status_after"] == "breach"
        assert alerts["risk"].severity == "critical"

        # Desk head: material by the desk standard (no approved threshold), with why.
        head = alerts["desk_head"].evidence_snapshot
        assert "mandate breach (LNG desk)" in head["message"]["material_reasons"]
        assert head["threshold"] == {
            "mwh": 100_000.0, "source": "desk standard, no approved lng.material_change_mwh"
        }

        # LNG2-4: each message says how current its inputs are.
        for row in alerts.values():
            inputs = row.evidence_snapshot["inputs_as_of"]
            assert inputs["revision"] == 2
            assert inputs["eta"]["basis"] == "ais_declared"
            assert "ETA from KPLER (the ETA declared in AIS, low confidence)" in row.message_en
            assert "plan rebuilt" in row.message_en

        # Each role's channel receives its own message and no other.
        sent = _sent(session, NOW + timedelta(seconds=2))
        assert {name: len(items) for name, items in sent.items()} == {
            role: 1 for role in CHANNELS
        }
        assert sent["trader"][0].title == (
            "Hedges no longer match Aurora (SAB-0420): buy 383,333 MWh TTF 2026-11 at short "
            "notice; sell 379,373 MWh TTF 2026-12"
        )
        assert sent["scheduler"][0].title.startswith("Renominate")
        assert sent["risk"][0].title.startswith("Mandate breach")
        assert sent["desk_head"][0].title.startswith("Material cargo change")
        assert "For: Trader. If not acted on: Management." in sent["trader"][0].body
        assert "Inputs: ETA from KPLER" in sent["scheduler"][0].body
        assert queued_after < 5.0  # import commit to every role's notification queued

        # The alert mirror and the monitoring scan leave the consumer's alerts alone.
        assert mirror_monitoring_alerts(session, now=NOW + timedelta(seconds=3)) == 0
        scan_monitoring_conditions(session, now_utc=NOW + timedelta(seconds=4),
                                   enrich_with_llm=False)
        assert all(row.resolved_at_utc is None for row in _alerts(session).values())

        # Dedupe: the same event delivered again changes nothing and notifies no one.
        before = session.query(NotificationOutboxRecord).count()
        from eurogas_nexus.application.lng_cargo_alerts import react
        from eurogas_nexus.db.models import MarketEventRecord

        latest = (
            session.query(MarketEventRecord)
            .filter(MarketEventRecord.subject_key == f"cargo:{CARGO}")
            .order_by(MarketEventRecord.revision.desc())
            .first()
        )
        again = react(session, latest, now=NOW + timedelta(minutes=1))
        session.commit()
        assert set(again["roles"].values()) == {"duplicate"}
        assert session.query(NotificationOutboxRecord).count() == before

        # Cooldown: another hour of delay ten minutes later updates every alert, but the
        # roles told ten minutes ago are not told again for the same items.
        _import_eta(session, LATE + timedelta(hours=1), NOW + timedelta(minutes=10))
        result = _drain(session, NOW + timedelta(minutes=10, seconds=1))
        roles = result["cargoes"][0]["roles"]
        assert roles["trader"] == "cooldown"
        assert roles["risk"] == "cooldown"
        assert session.query(NotificationOutboxRecord).count() == before + (
            list(roles.values()).count("notified")
        )
        assert _alerts(session)["trader"].evidence_snapshot["inputs_as_of"]["revision"] == 3

        # Withdrawal: the feed corrects the ETA back to the plan; every message is moot.
        _import_eta(session, ETA, NOW + timedelta(minutes=40), basis="master_notice",
                    confidence="high")
        result = _drain(session, NOW + timedelta(minutes=40, seconds=1))
        assert set(result["cargoes"][0]["roles"].values()) == {"withdrawn"}
        alerts = _alerts(session)
        assert all(row.status == "resolved" for row in alerts.values())
        assert all(row.message_en.startswith("Withdrawn:") for row in alerts.values())
        withdrawn = alerts["scheduler"].evidence_snapshot["withdrawn"]
        assert withdrawn["reason_zh"] == "靠泊与外输已恢复原计划"
        assert alerts["scheduler"].message_zh_cn.startswith("已撤回：靠泊与外输已恢复原计划")
        sent = _sent(session, NOW + timedelta(minutes=41))
        assert {name: [m.title.split(":")[0] for m in items] for name, items in sent.items()} \
            == {role: ["Withdrawn"] for role in CHANNELS}
        assert open_messages(session, cargo_id=CARGO) == []
        assert len(open_messages(session, cargo_id=CARGO,
                                 include_withdrawn_since=NOW)) == 4


def test_a_slot_change_and_a_hedge_change_take_the_same_chain(desk) -> None:
    """LNG2-5: not only an ETA. A slot moved so the ETA misses it, then the trader's hedges."""

    with Session(desk) as session:
        # The terminal moves the slot window: the ship now arrives after it closes.
        slot = (
            "slot_id,terminal_name,window_start,window_end\n"
            "gate-1,Gate Terminal,2026-11-20T00:00:00Z,2026-11-26T00:00:00Z\n"
        )
        rows = parse_regas_slots(slot, source_system="TERMINAL", source_reference="gate:conf",
                                 now_utc=NOW)
        assert store_lng_rows(session, "slot", rows, now_utc=NOW)["events"]["published"] == {
            "cargo.changed": 1
        }
        session.commit()
        result = _drain(session, NOW + timedelta(seconds=1))
        roles = result["cargoes"][0]["roles"]
        assert roles == {role: "notified" for role in CHANNELS}
        alerts = _alerts(session)
        assert alerts["scheduler"].title_en.startswith("Slot missed: Aurora (SAB-0420)")
        assert alerts["scheduler"].severity == "critical"
        trader_items = alerts["trader"].evidence_snapshot["message"]["items"]
        # No berth, no gas: every hedge leg is left without gas behind it.
        assert {item["kind"] for item in trader_items} == {"short_notice", "buy_back"}
        assert "the slot is missed" in alerts["desk_head"].evidence_snapshot["message"][
            "material_reasons"]
        assert "slot gate-1 from TERMINAL" in alerts["trader"].message_en

        # The slot is restored and the trader records smaller hedges: a hedge change.
        rows = parse_regas_slots(
            "slot_id,terminal_name,window_start,window_end\n"
            "gate-1,Gate Terminal,2026-11-26T00:00:00Z,2026-12-06T00:00:00Z\n",
            source_system="TERMINAL", source_reference="gate:conf2",
            now_utc=NOW + timedelta(hours=1),
        )
        store_lng_rows(session, "slot", rows, now_utc=NOW + timedelta(hours=1))
        session.commit()
        _drain(session, NOW + timedelta(hours=1, seconds=1))
        assert {row.status for row in _alerts(session).values()} == {"resolved"}

        held = session.query(LngCargoHedgeRecord).filter_by(retired_at_utc=None).all()
        legs = [{"hub": leg.hub, "month": leg.delivery_month, "mwh": float(leg.mwh) / 2}
                for leg in held]
        captured = record_hedges(session, CARGO, legs, actor="lng.trader",
                                 now=NOW + timedelta(hours=2))
        session.commit()
        assert captured["events"]["published"] == {"cargo.changed": 1}
        result = _drain(session, NOW + timedelta(hours=2, seconds=1))
        roles = result["cargoes"][0]["roles"]
        assert roles["trader"] == "notified" and roles["risk"] == "notified"
        assert roles["scheduler"] == "nothing"  # no berth or send-out moved
        trader = _alerts(session)["trader"]
        assert {item["kind"] for item in trader.evidence_snapshot["message"]["items"]} <= {
            "sell", "short_notice"}
        assert "hedges recorded by lng.trader" in trader.message_en


def test_an_energy_or_departure_change_below_the_threshold_skips_the_desk_head(desk) -> None:
    """LNG2-3 materiality and LNG2-5 for energy and departure."""

    with Session(desk) as session:
        text = (
            "cargo_id,vessel_name,status,load_port,departed_at,energy_gwh\n"
            f"{CARGO},Aurora,laden,Sabine Pass,2026-11-08T06:00:00Z,990\n"
        )
        rows = parse_lng_cargoes(text, source_system="ETRM", source_reference="etrm:2",
                                 now_utc=NOW)
        store_lng_rows(session, "cargo", rows, now_utc=NOW)
        session.commit()
        result = _drain(session, NOW + timedelta(seconds=1))
        roles = result["cargoes"][0]["roles"]
        assert roles["desk_head"] == "nothing"  # ~12,000 MWh is below 100,000 MWh
        assert roles["trader"] == "notified" and roles["risk"] == "notified"
        trader = _alerts(session)["trader"]
        assert "departure, energy changed" in trader.message_en


def test_each_role_sees_its_own_item_on_today_and_the_cargo_board(desk) -> None:
    """LNG2-3 in the app: What needs me holds the caller's role; the board and plan hold all."""

    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from eurogas_nexus.api.app import create_app
    from eurogas_nexus.application import lng_cargo_alerts
    from eurogas_nexus.application.alert_scope import set_request_principal
    from eurogas_nexus.db.repositories.identity import (
        create_identity_api_key,
        create_identity_principal,
    )

    with Session(desk) as session:
        _import_eta(session, LATE, NOW)
        _drain(session, NOW + timedelta(seconds=1))
        seen = {}
        for functions in (("TRADER",), ("OPERATIONS",), ("RISK_MANAGER",), ("MANAGEMENT",)):
            set_request_principal(SimpleNamespace(job_functions=functions, data_scopes=("*",)))
            try:
                items = lng_cargo_alerts.needs_me_items(session, functions, now=NOW)
            finally:
                set_request_principal(None)
            assert len(items) == 1 and items[0]["kind"] == "cargo"
            assert items[0]["target"] == {
                "mode": "desk", "task": "cargoes", "params": {"cargo": CARGO}
            }
            assert items[0]["as_of"] and items[0]["since_utc"]
            seen[functions[0]] = items[0]["role"]
        assert seen == {"TRADER": "trader", "OPERATIONS": "scheduler",
                        "RISK_MANAGER": "risk", "MANAGEMENT": "desk_head"}

        viewer = create_identity_principal(session, name="viewer", display_name="viewer",
                                           role="VIEWER", data_scopes=["*"])
        _key, bearer = create_identity_api_key(session, viewer.principal_id,
                                               display_name="t", scopes=["*"])
        session.commit()
    headers = {"X-Eurogas-Api-Key": "test-public-api-token", "X-Eurogas-Identity": bearer}
    client = TestClient(create_app())
    board = client.get("/api/lng/cargoes/plans", headers=headers)
    assert board.status_code == 200, board.text
    (line,) = board.json()["data"]
    assert sorted(item["role"] for item in line["attention"]) == sorted(CHANNELS)
    assert line["eta"]["basis"] == "ais_declared"
    plan = client.get(f"/api/lng/cargoes/{CARGO}/plan", headers=headers).json()["data"]
    roles = {item["role"]: item for item in plan["roles"]}
    assert set(roles) == set(CHANNELS)
    assert roles["trader"]["lines"][0].startswith("Aurora (SAB-0420) ETA moves 4.0 days later")
    assert roles["trader"]["inputs_as_of"]["eta"]["confidence"] == "low"
    assert roles["trader"]["mine"] is True  # a caller with no declared function: the trader's
