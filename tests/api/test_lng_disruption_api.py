"""LNG-3 over the API: the book re-optimised around a late cargo, the option detail, the
frontier with a pipeline what-if, the recorded choice, and the outbox consumer's timeline.

The book is the demo's planted case D1 (``scripts/demo/seed_demo_desk.py``), relative to
today: every figure is illustrative. The hand-worked numbers are asserted in
``tests/domain/test_lng_disruption.py``; here the wiring is.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from eurogas_nexus.api.app import create_app
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    AuditEventRecord,
    FirmMarkRecord,
    LngCargoRecord,
    LngDisruptionDecisionRecord,
    LngDisruptionRunRecord,
    NotificationOutboxRecord,
)
from eurogas_nexus.db.repositories.identity import (
    create_identity_api_key,
    create_identity_principal,
)

PUBLIC_TOKEN = "test-public-api-token"
DEMO = Path(__file__).resolve().parents[2] / "scripts" / "demo"
PRICES = {"ZTP": 30.0, "TTF": 30.4, "PEG": 29.9, "PVB": 31.0}


def _seed_module():
    spec = importlib.util.spec_from_file_location("seed_demo_desk_lng3", DEMO / "seed_demo_desk.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SEED = _seed_module()


def _marks(session, now: datetime) -> None:
    first = now.date().replace(day=1)
    for step in range(4):
        year, month = divmod(first.month - 1 + step, 12)
        start = date(first.year + year, month + 1, 1)
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        for hub, price in PRICES.items():
            session.add(
                FirmMarkRecord(
                    mark_id=f"m-{hub}-{start:%Y%m}",
                    hub=hub,
                    period_label=f"{start:%Y-%m}",
                    period_start=start,
                    period_end=end,
                    value=Decimal(str(price)),
                    unit="MWh",
                    currency="EUR",
                    note="test mark",
                    entered_by="test",
                    entered_at_utc=now - timedelta(hours=1),
                )
            )


def _setup(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{(tmp_path / 'lng3.sqlite').as_posix()}"
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
        SEED.seed_lng_disruption_case(session, now)
        _marks(session, now)
        session.commit()
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("EUROGAS_NEXUS_DB_DSN", raising=False)
    return engine, who, now


def _by_kind(options):
    return {o["key"].split(":", 1)[1]: o for o in options}


def test_a_late_cargo_gets_valued_options_a_frontier_and_a_default(tmp_path, monkeypatch):
    _engine, who, _now = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())

    response = client.get("/api/lng/cargoes/demo-lng-a/disruption-options", headers=who["viewer"])
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "disrupted"
    assert [s["supply_id"] for s in data["disrupted"]] == ["demo-lng-a"]
    assert data["cargo"]["slot"]["entitlement"][0]["storage_end_mwh"] == 900_000.0
    assert {s["scenario_id"] for s in data["scenarios"]} == {
        "base",
        "early",
        "late",
        "prices_up",
        "prices_down",
    }
    options = _by_kind(data["options"])
    assert {
        "stay+absorb",
        "stay+borrow",
        "stay+buy",
        "divert:demo-d1-dunk+absorb",
        "swap:demo-lng-b+absorb",
        "swap:demo-lng-c+absorb",
    } <= set(options)
    # The Huelva swap breaks the firm daily delivery there.
    iberia = options["swap:demo-lng-c+absorb"]
    assert not iberia["feasible"]
    assert any("Iberia offtaker" in reason for reason in iberia["reasons"])
    # The Rotterdam swap moves a cargo that runs normally: counted and penalised.
    swap = options["swap:demo-lng-b+absorb"]
    assert swap["affects_other_supplies"] == ["demo-lng-b"]
    assert swap["objectives"]["disrupted_mwh"] > 0
    # Borrowing in tank keeps the planned send-out: nothing to re-hedge, the default here.
    borrow = options["stay+borrow"]
    assert borrow["hedge_legs"] == []
    assert data["recommended"] == borrow["option_id"]
    assert borrow["option_id"] in data["frontier"]
    # A dominated option names its dominator and why.
    wait = options["stay+absorb"]
    assert wait["dominated_by"] and wait["dominated_why"]
    assert data["preference"]["sources"]["risk_weight"].startswith("desk standard")
    assert data["decision"] is None and data["timeline"] == []
    assert "Nothing is booked" in data["advisory"]

    detail = client.get(
        f"/api/lng/cargoes/demo-lng-a/disruption-options/{borrow['option_id']}",
        headers=who["viewer"],
    )
    assert detail.status_code == 200, detail.text
    body = detail.json()["data"]
    assert body["recommended"] is True
    assert body["components"]["capacity_fees"] < 0
    assert any("borrow" in line["text"] for line in body["arithmetic"])
    assert {s["scenario_id"] for s in body["scenario_detail"]} >= {"late"}
    assert body["mandates"] == {"checked": 0, "moves": []}

    missing = client.get(
        "/api/lng/cargoes/demo-lng-a/disruption-options/opt-000000000000", headers=who["viewer"]
    )
    assert missing.status_code == 404
    assert missing.json()["error"] == "option_not_found"


def test_a_cargo_running_normally_is_as_planned(tmp_path, monkeypatch):
    _engine, who, _now = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())
    data = client.get(
        "/api/lng/cargoes/demo-lng-c/disruption-options", headers=who["viewer"]
    ).json()["data"]
    # Solace is only moved by the (infeasible) swap.
    assert data["status"] == "affected"
    assert all(not o["feasible"] for o in data["options"])
    unknown = client.get("/api/lng/cargoes/nope/disruption-options", headers=who["viewer"])
    assert unknown.status_code == 404


def test_frontier_reads_the_book_and_a_pipeline_what_if(tmp_path, monkeypatch, _now=None):
    _engine, who, now = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())
    plain = client.get(
        "/api/lng/disruption/frontier", params={"book_id": "demo-lng-nwe"}, headers=who["viewer"]
    )
    assert plain.status_code == 200, plain.text
    data = plain.json()["data"]
    assert data["what_if"] is False
    assert {s["supply_id"] for s in data["supplies"]} >= {"demo-lng-a", "demo-d1-pipe"}
    assert data["obligations"][0]["firm"] is True

    first = (now + timedelta(days=12)).date()
    params = {
        "book_id": "demo-lng-nwe",
        "curtail_supply": "demo-d1-pipe",
        "curtail_from": first.isoformat(),
        "curtail_to": (first + timedelta(days=1)).isoformat(),
        "curtail_mwh_per_day": 30_000,
    }
    what_if = client.get("/api/lng/disruption/frontier", params=params, headers=who["viewer"])
    assert what_if.status_code == 200, what_if.text
    body = what_if.json()["data"]
    assert body["what_if"] is True
    assert {s["supply_id"] for s in body["disrupted"]} == {"demo-lng-a", "demo-d1-pipe"}
    assert any(o["kind"] == "combined" for o in body["options"])

    incomplete = client.get(
        "/api/lng/disruption/frontier",
        params={"book_id": "demo-lng-nwe", "curtail_supply": "demo-d1-pipe"},
        headers=who["viewer"],
    )
    assert incomplete.status_code == 422
    unknown = client.get(
        "/api/lng/disruption/frontier",
        params={**params, "curtail_supply": "nope"},
        headers=who["viewer"],
    )
    assert unknown.status_code == 404


def test_choosing_records_the_decision_audited_and_books_nothing(tmp_path, monkeypatch):
    engine, who, _now = _setup(tmp_path, monkeypatch)
    client = TestClient(create_app())
    data = client.get(
        "/api/lng/cargoes/demo-lng-a/disruption-options", headers=who["viewer"]
    ).json()["data"]
    options = _by_kind(data["options"])
    swap = options["swap:demo-lng-b+absorb"]["option_id"]
    infeasible = options["swap:demo-lng-c+absorb"]["option_id"]
    path = f"/api/lng/cargoes/demo-lng-a/disruption-options/{swap}/choose"

    assert client.post(path, json={}, headers=who["viewer"]).status_code == 403
    refused = client.post(
        f"/api/lng/cargoes/demo-lng-a/disruption-options/{infeasible}/choose",
        json={},
        headers=who["analyst"],
    )
    assert refused.status_code == 409
    assert refused.json()["error"] == "option_infeasible"

    def refuse(session, _context, _instances):
        if any(isinstance(item, AuditEventRecord) for item in session.new):
            raise OperationalError("INSERT INTO audit_events", {}, Exception("disk full"))

    event.listen(Session, "before_flush", refuse)
    try:
        failed = client.post(path, json={"note": "x"}, headers=who["analyst"])
    finally:
        event.remove(Session, "before_flush", refuse)
    assert failed.status_code == 503
    with Session(engine) as session:
        assert session.query(LngDisruptionDecisionRecord).count() == 0

    chosen = client.post(path, json={"note": "Halcyon's owner agreed"}, headers=who["analyst"])
    assert chosen.status_code == 200, chosen.text
    decision = chosen.json()["data"]
    assert decision["booked"] is False
    assert decision["was_recommended"] is False
    assert decision["decided_by"]
    with Session(engine) as session:
        audit = session.query(AuditEventRecord).filter_by(action="lng.disruption_choice").one()
        assert "(not the default)" in audit.detail
        # Nothing moved: the cargo still holds its slot and ETA.
        assert session.get(LngCargoRecord, "demo-lng-a").destination_terminal == (
            "Zeebrugge terminal"
        )
    again = client.get(
        "/api/lng/cargoes/demo-lng-a/disruption-options", headers=who["viewer"]
    ).json()["data"]
    assert again["decision"]["option_id"] == swap


def test_the_consumer_keeps_a_timeline_and_notifies_once_per_change(tmp_path, monkeypatch):
    from eurogas_nexus.application import lng_disruption, market_events
    from eurogas_nexus.application.market_event_capture import capture_desk

    engine, _who, now = _setup(tmp_path, monkeypatch)
    with Session(engine) as session:
        capture_desk(session, cargo_ids=["demo-lng-a"], now_utc=now)
        session.commit()
        first = market_events.process(session, lng_disruption.CONSUMER_NAME, now_utc=now)
        session.commit()
        assert first["claimed"] >= 1
        runs = session.query(LngDisruptionRunRecord).all()
        assert len(runs) == 1 and runs[0].change == "recommendation" and runs[0].notified
        told = session.query(NotificationOutboxRecord).all()
        assert {row.category for row in told} == {"cargo", "nomination", "desk_head"}

        # The same input again: no new run, no new notice.
        result = lng_disruption.reoptimise(
            session, "demo-lng-nwe", trigger="test", now=now + timedelta(minutes=5)
        )
        assert result["status"] == "unchanged"

        # A later ETA (two more days) ten minutes on: the swap with Halcyon no longer
        # fits, so the frontier moves (with these flat test prices the default stays): a
        # new run, held back by the cooldown because the recommendation is the same.
        cargo = session.get(LngCargoRecord, "demo-lng-a")
        cargo.eta_utc = cargo.eta_utc + timedelta(days=2)
        later = now + timedelta(minutes=10)
        capture_desk(session, cargo_ids=["demo-lng-a"], now_utc=later)
        session.commit()
        market_events.process(session, lng_disruption.CONSUMER_NAME, now_utc=later)
        session.commit()
        runs = (
            session.query(LngDisruptionRunRecord)
            .order_by(LngDisruptionRunRecord.computed_at_utc)
            .all()
        )
        assert len(runs) == 2
        assert runs[1].change == "frontier" and not runs[1].notified
        assert session.query(NotificationOutboxRecord).count() == 3

        # Back to the first ETA after the cooldown: the frontier moves back to what the roles
        # were told first, so the run is kept and nobody is told the same thing twice.
        cargo.eta_utc = cargo.eta_utc - timedelta(days=2)
        after = now + timedelta(minutes=45)
        capture_desk(session, cargo_ids=["demo-lng-a"], now_utc=after)
        session.commit()
        market_events.process(session, lng_disruption.CONSUMER_NAME, now_utc=after)
        session.commit()
        latest = (
            session.query(LngDisruptionRunRecord)
            .order_by(LngDisruptionRunRecord.computed_at_utc.desc())
            .first()
        )
        assert session.query(LngDisruptionRunRecord).count() == 3
        assert latest.digest == runs[0].digest and not latest.notified
        assert session.query(NotificationOutboxRecord).count() == 3
        again = lng_disruption.reoptimise(
            session, "demo-lng-nwe", trigger="test", now=after + timedelta(minutes=1)
        )
        assert again["status"] == "unchanged"
