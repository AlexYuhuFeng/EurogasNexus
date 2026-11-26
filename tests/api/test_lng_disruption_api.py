"""LNG-3 and LNG-4 over the API: the book re-optimised around a late cargo, every option with
its consequences and full cost, the recommended set, the option detail with the sources of each
line, demurrage in USD at the FX choice, the frontier with a pipeline what-if, the recorded
choice, and the outbox consumer's timeline.

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
    FxObservationRecord,
    LngCapacityOfferRecord,
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


#: An illustrative ECB reference rate (test data, not a published fix).
EURUSD = 1.0857


def _fx(session, now: datetime) -> None:
    session.add(
        FxObservationRecord(
            observation_id="fx-test-eurusd",
            pair="EURUSD",
            base_currency="EUR",
            quote_currency="USD",
            rate=EURUSD,
            rate_type="reference",
            value_date=(now.date() - timedelta(days=1)).isoformat(),
            observed_at_utc=now - timedelta(days=1),
            source_system="ECB",
            source_reference="test:ecb-eurusd",
            freshness="fresh",
            research_only=False,
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
        _fx(session, now)
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
    # LNG-4: the Huelva swap is listed, possible, and flagged as breaking the firm delivery.
    iberia = options["swap:demo-lng-c+absorb"]
    assert iberia["possible"] and iberia["rank"]
    assert iberia["flags"] == {
        "physically_possible": True,
        "contract_breach": True,
        "disrupts_normal_cargo": True,
    }
    (breach,) = iberia["breaches"]
    assert breach["counterparty"] == "Iberia offtaker" and not breach["penalty_held"]
    assert "breaks the firm delivery to Iberia offtaker" in breach["text"]
    # Hub gas at PVB covers the shortfall as a further option with no breach.
    covered = options["swap:demo-lng-c+absorb + cover:hub:PVB:demo-d1-iberia"]
    assert covered["kind"] == "substitute" and not covered["flags"]["contract_breach"]
    assert covered["rank"] < iberia["rank"]  # same score, fewer contracts broken
    # The contracted Dunkerque slot carries what it costs another user's carrier and the
    # slot's release value; the Montoir spot slot is valued beside it.
    dunk = options["divert:demo-d1-dunk+absorb"]
    kinds = {item["kind"] for item in dunk["opportunity"]}
    assert kinds == {"berth_delay", "capacity_forgone"}
    assert dunk["opportunity_cost_expected"] > 0
    assert dunk["objectives"]["pnl_expected"] == round(
        dunk["direct_pnl_expected"] - dunk["opportunity_cost_expected"], 2
    )
    assert "spot:demo-d1-spot+absorb" in options
    # The Rotterdam swap moves a cargo that runs normally: counted and penalised.
    swap = options["swap:demo-lng-b+absorb"]
    assert swap["affects_other_supplies"] == ["demo-lng-b"]
    assert swap["objectives"]["disrupted_mwh"] > 0
    # Borrowing in tank keeps the planned send-out: nothing to re-hedge, the default here.
    borrow = options["stay+borrow"]
    assert borrow["hedge_legs"] == []
    assert data["recommended"] == borrow["option_id"]
    assert [(r["basis"], r["option_id"]) for r in data["recommended_set"]] == [
        ("clean", borrow["option_id"]),
        ("best_expected", swap["option_id"]),
    ]
    assert all(r["reason"] for r in data["recommended_set"])
    assert borrow["recommended_as"] == ["clean"]
    # Meridian's demurrage is 76,000 USD/day, converted at the ECB reference rate.
    demurrage = data["demurrage"]
    assert (demurrage["rate_per_day"], demurrage["currency"]) == (76_000.0, "USD")
    assert demurrage["eur_per_day"] == round(76_000 / EURUSD, 2)
    assert demurrage["fx"]["source"] == "ECB" and demurrage["fx"]["rate_date"]
    assert data["fx"]["choice"]["default"] is True
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
    assert all(line["sources"] and line["basis"] for line in body["arithmetic"])

    # A rate entered by hand, and figures in USD: the read says so.
    manual = client.get(
        "/api/lng/cargoes/demo-lng-a/disruption-options",
        params={
            "fx_source": "manual",
            "fx_rate": 1.10,
            "fx_currency": "USD",
            "reporting_currency": "USD",
        },
        headers=who["viewer"],
    ).json()["data"]
    assert manual["demurrage"]["eur_per_day"] == round(76_000 / 1.10, 2)
    assert manual["demurrage"]["fx"]["entered_by_hand"] is True
    usd = _by_kind(manual["options"])["stay+borrow"]["reporting"]
    assert usd["currency"] == "USD" and usd["fx"]["entered_by_hand"] is True
    licensed = client.get(
        "/api/lng/cargoes/demo-lng-a/disruption-options",
        params={"fx_source": "WMR"},
        headers=who["viewer"],
    )
    assert licensed.status_code == 403
    assert licensed.json()["error"] == "fx_source_entitlement_denied"
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
    # Solace is only moved by the Huelva swaps, each flagged as moving it.
    assert data["status"] == "affected"
    assert data["options"] and all(o["flags"]["disrupts_normal_cargo"] for o in data["options"])
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
    breach = options["swap:demo-lng-c+absorb"]["option_id"]
    path = f"/api/lng/cargoes/demo-lng-a/disruption-options/{swap}/choose"

    assert client.post(path, json={}, headers=who["viewer"]).status_code == 403
    # Without Huelva's interruptible capacity the Huelva swap cannot physically happen.
    with Session(engine) as session:
        held = session.get(LngCapacityOfferRecord, "demo-d1-hint")
        kept_offer = {c.name: getattr(held, c.name) for c in held.__table__.columns}
        session.delete(held)
        session.commit()
    refused = client.post(
        f"/api/lng/cargoes/demo-lng-a/disruption-options/{breach}/choose",
        json={},
        headers=who["analyst"],
    )
    assert refused.status_code == 409
    assert refused.json()["error"] == "option_infeasible"
    assert "cannot physically happen" in refused.json()["detail"]["message"]
    with Session(engine) as session:
        session.add(LngCapacityOfferRecord(**kept_offer))
        session.commit()
    # A breach option can be chosen; the record keeps what it breaks and moves.
    took = client.post(
        f"/api/lng/cargoes/demo-lng-a/disruption-options/{breach}/choose",
        json={"note": "Iberia agreed a one-day shortfall"},
        headers=who["analyst"],
    )
    assert took.status_code == 200, took.text
    kept = took.json()["data"]
    assert kept["consequences"]["flags"]["contract_breach"] is True
    assert kept["consequences"]["breaches"][0]["counterparty"] == "Iberia offtaker"
    assert kept["fx"]["choice"]["source"] == "ECB"
    assert kept["recommended_set"]
    with Session(engine) as session:
        session.query(LngDisruptionDecisionRecord).delete()
        session.query(AuditEventRecord).filter_by(action="lng.disruption_choice").delete()
        session.commit()

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
    assert decision["was_recommended"] is True  # the best expected P&L of the set
    assert decision["decided_by"]
    with Session(engine) as session:
        audit = session.query(AuditEventRecord).filter_by(action="lng.disruption_choice").one()
        assert "(recommended: best_expected)" in audit.detail
        assert "moves Halcyon" in audit.detail
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

        assert all(row.title.startswith("Recommended options changed") for row in told)
        assert [r["basis"] for r in runs[0].recommended_set] == ["clean", "best_expected"]

        # A later ETA (two more days) ten minutes on: the swap with Halcyon no longer
        # fits, so the best expected option of the recommended set changes. A change to the
        # recommended set is told at once, cooldown or not.
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
        assert runs[1].change == "recommendation" and runs[1].notified
        assert runs[1].recommended_set != runs[0].recommended_set
        assert session.query(NotificationOutboxRecord).count() == 6

        # The same input once more: nothing new, nobody told twice.
        again = lng_disruption.reoptimise(
            session, "demo-lng-nwe", trigger="test", now=later + timedelta(minutes=1)
        )
        assert again["status"] == "unchanged"
        assert session.query(NotificationOutboxRecord).count() == 6


def test_remit_links_on_a_pipeline_supply_are_read_and_overridden(tmp_path, monkeypatch):
    """LNG-4: the REMIT messages linked to the demo pipeline, and the manual override."""

    from eurogas_nexus.application import pipeline_outages
    from eurogas_nexus.db.models import RemitUmmRecord
    from eurogas_nexus.domain.market.gas_day import gas_day_start_for_date

    engine, who, now = _setup(tmp_path, monkeypatch)
    start = now.date() + timedelta(days=5)
    with Session(engine) as session:
        session.add(
            RemitUmmRecord(
                record_id="umm-demo-v1",
                message_id="umm-demo",
                version=1,
                published_at_utc=now,
                event_status="active",
                unavailability_type="planned",
                event_start_utc=gas_day_start_for_date(start),
                event_stop_utc=gas_day_start_for_date(start + timedelta(days=2)),
                asset_name="North-Sea entry point",
                asset_eic="21Z-DEMO-TEST",
                asset_type="entry",
                balancing_zone="ZTP",
                direction="entry",
                unit="GWh/d",
                technical_capacity=100.0,
                available_capacity=75.0,
                unavailable_capacity=25.0,
                unavailable_mcm_d=None,
                unavailable_gwh_d=25.0,
                reason="test",
                market_participant="Test TSO",
                remarks="",
                source_system="REMIT",
                source_reference="test",
                ingested_at_utc=now,
            )
        )
        pipeline_outages.link_outages(session, now=now)
        session.commit()
    client = TestClient(create_app())
    path = "/api/lng/pipeline-supplies/demo-d1-pipe"
    read = client.get(f"{path}/outage-links", headers=who["viewer"])
    assert read.status_code == 200, read.text
    data = read.json()["data"]
    (link,) = data["links"]
    assert (link["matched_on"], link["status"], link["curtailed_mwh"]) == (
        "asset_name",
        "applied",
        15_000.0,  # 30,000 MWh/d x 25 % on two gas days
    )
    assert data["outage_mode"] == "auto" and len(data["effective"]) == 2
    assert data["advisory"].startswith("Advisory")
    assert (
        client.get(
            "/api/lng/pipeline-supplies/nope/outage-links", headers=who["viewer"]
        ).status_code
        == 404
    )

    body = {"outage_mode": "manual", "curtailed": [[start.isoformat(), 1000]], "reason": "t"}
    assert (
        client.put(f"{path}/outage-override", json=body, headers=who["viewer"]).status_code == 403
    )
    done = client.put(f"{path}/outage-override", json=body, headers=who["analyst"])
    assert done.status_code == 200, done.text
    assert done.json()["data"]["effective"] == [[start.isoformat(), 1000.0]]
    bad = client.put(
        f"{path}/outage-override", json={"outage_mode": "sometimes"}, headers=who["analyst"]
    )
    assert bad.status_code == 422
    with Session(engine) as session:
        (audit,) = (
            session.query(AuditEventRecord).filter_by(action="lng.pipeline_outage_override").all()
        )
        assert audit.resource == "pipeline_supply:demo-d1-pipe"
    # The book's read carries the override.
    frontier = client.get(
        "/api/lng/disruption/frontier", params={"book_id": "demo-lng-nwe"}, headers=who["viewer"]
    ).json()["data"]
    (outage,) = frontier["pipeline_outages"]
    assert outage["outage_mode"] == "manual" and outage["links"][0]["message_id"] == "umm-demo"
