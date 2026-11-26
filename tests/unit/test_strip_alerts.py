"""Alerts the situational strip consumes: price moves (G3), delivery shortfalls (G5) and
fundamentals surprises, each from the stored data and with its source named."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, func
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.application.alert_scope import alert_visibility
from eurogas_nexus.application.monitoring_service import scan_monitoring_conditions
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    ContractDeliveryRecord,
    MarketObservationRecord,
    MonitoringAlertRecord,
)
from eurogas_nexus.db.models.observation import LngObservationRecord
from eurogas_nexus.security.identity import AuthenticatedPrincipal

SEED = Path(__file__).resolve().parents[2] / "scripts" / "demo" / "seed_demo_desk.py"
NOW = datetime(2026, 11, 7, 9, tzinfo=UTC)


@pytest.fixture
def desk(tmp_path, monkeypatch):
    url = f"sqlite+pysqlite:///{tmp_path / 'desk.sqlite'}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    monkeypatch.setenv("EUROGAS_NEXUS_DEMO_MARKS", "true")
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    spec = importlib.util.spec_from_file_location("seed_demo_desk", SEED)
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    with Session(engine) as session:
        seed.seed(session, NOW)
        session.commit()
    return engine


def _alerts(engine, category: str) -> list[MonitoringAlertRecord]:
    with Session(engine) as session:
        scan_monitoring_conditions(session, now_utc=NOW, enrich_with_llm=False)
        rows = session.query(MonitoringAlertRecord).filter_by(category=category).all()
        session.expunge_all()
        return rows


def _principal(*scopes: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id="p", name="p", principal_type="USER", role="ANALYST", status="ACTIVE",
        data_scopes=scopes, roles=("ANALYST",),
    )


def _latest_close(session, hub: str) -> MarketObservationRecord:
    rows = [
        row
        for row in session.query(MarketObservationRecord)
        .order_by(MarketObservationRecord.observed_at_utc.desc())
        .limit(2000)
        if (row.metadata_json or {}).get("hub") == hub
        and (row.metadata_json or {}).get("tenor") == "month-ahead"
    ]
    return rows[0], rows[1]


def test_a_front_month_move_beyond_two_percent_raises_a_sourced_simulated_alert(desk):
    with Session(desk) as session:
        latest, prior = _latest_close(session, "TTF")
        latest.price = round(prior.price * 1.064, 4)
        session.commit()
    alerts = [row for row in _alerts(desk, "market") if row.alert_type == "price_move"]
    ttf = next(row for row in alerts if row.evidence_snapshot["hub"] == "TTF")
    assert ttf.evidence_snapshot["product"] == "FM"
    assert ttf.evidence_snapshot["move_pct"] == pytest.approx(6.4, abs=0.05)
    assert ttf.evidence_snapshot["source_system"] and ttf.source_refs
    assert ttf.simulated is True and ttf.evidence_snapshot["simulated"] is True
    assert ttf.severity == "warning"
    assert ttf.title_en.startswith("TTF FM +6.4% vs prior close")


def test_a_small_move_raises_nothing(desk):
    with Session(desk) as session:
        latest, prior = _latest_close(session, "TTF")
        latest.price = round(prior.price * 1.01, 4)
        session.commit()
    alerts = _alerts(desk, "market")
    assert not [row for row in alerts if row.evidence_snapshot.get("hub") == "TTF"]


def test_a_price_alert_is_shown_only_to_readers_entitled_to_its_source(desk):
    with Session(desk) as session:
        latest, prior = _latest_close(session, "TTF")
        latest.price = round(prior.price * 0.93, 4)
        session.commit()
    row = next(r for r in _alerts(desk, "market") if r.evidence_snapshot["hub"] == "TTF")
    with Session(desk) as session:
        assert alert_visibility(session, principal=_principal("*"))(row)
        assert alert_visibility(session, principal=_principal("DEMO"))(row)
        # Not entitled to the family, and outside a request with no principal: hidden.
        assert not alert_visibility(session, principal=_principal("EEX"))(row)
        assert not alert_visibility(session, principal=None)(row)


def test_a_delivery_short_beyond_tolerance_raises_a_book_scoped_alert(desk):
    with Session(desk) as session:
        day = session.query(func.max(ContractDeliveryRecord.gas_day)).filter(
            ContractDeliveryRecord.allocated_mwh.isnot(None)
        ).scalar()
        rows = session.query(ContractDeliveryRecord).filter_by(gas_day=day).all()
        short = rows[0]
        short.allocated_mwh = round(short.nominated_mwh * 0.8, 1)
        contract_id = short.contract_id
        for other in rows[1:]:
            other.allocated_mwh = other.nominated_mwh  # on nomination: no alert
        session.commit()
    alerts = _alerts(desk, "delivery")
    alert = next(
        row for row in alerts if row.entity_id == f"{contract_id}:{day.isoformat()}"
    )
    # A contract delivering on its nomination that day raises nothing.
    on_day = {row.evidence_snapshot["contract_id"] for row in alerts
              if row.evidence_snapshot["gas_day"] == day.isoformat()}
    assert on_day == {contract_id}
    assert alert.alert_type == "shortfall"
    assert alert.evidence_snapshot["shortfall_pct"] == pytest.approx(20.0)
    assert alert.evidence_snapshot["shortfall_pct"] > alert.evidence_snapshot["tolerance_pct"]
    assert alert.evidence_snapshot["book_ids"]  # isolation applies (alert_scope)
    assert alert.severity == "critical"


def test_lng_send_out_far_from_its_7_day_average_is_a_fundamentals_surprise(desk):
    with Session(desk) as session:
        newest = session.query(func.max(LngObservationRecord.period_start_utc)).scalar()
        for row in session.query(LngObservationRecord).filter_by(period_start_utc=newest):
            row.send_out_twh_d = (row.send_out_twh_d or 0.0) * 2.5 + 0.2
        session.commit()
    alerts = _alerts(desk, "fundamentals")
    lng = next(row for row in alerts if row.alert_type == "lng_sendout")
    assert lng.evidence_snapshot["deviation_pct"] >= 30
    assert lng.evidence_snapshot["source_system"].endswith("_Sim")
    assert lng.simulated is True
    # More than 60 % off the week is a warning, dated by the day it is for, not by the scan.
    assert lng.severity == "warning"
    assert lng.event_time_utc.date().isoformat() == lng.evidence_snapshot["day"]


def test_an_ordinary_demo_day_raises_no_fundamentals_surprise(desk):
    alerts = _alerts(desk, "fundamentals")
    assert not [row for row in alerts if row.alert_type == "lng_sendout"]
