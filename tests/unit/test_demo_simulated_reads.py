"""A demo desk reads the demo market (labelled simulated); a customer desk never does."""

from __future__ import annotations

import importlib.util
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401
from eurogas_nexus.application.caller import Caller
from eurogas_nexus.application.opportunities.listing import readiness
from eurogas_nexus.application.valuation_snapshot import open_valuation_snapshot
from eurogas_nexus.db.base import Base
from eurogas_nexus.domain.valuation.periods import DeliveryPeriod
from eurogas_nexus.domain.valuation.quality import InputClass
from eurogas_nexus.security.identity import AuthenticatedPrincipal

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "demo" / "seed_demo_desk.py"
NOW = datetime(2026, 12, 3, 9, tzinfo=UTC)


def _principal() -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        principal_id="p-trader", name="trader", principal_type="USER", role="ANALYST",
        status="ACTIVE", data_scopes=("*",), roles=("ANALYST",),
    )


@pytest.fixture(scope="module")
def session():
    spec = importlib.util.spec_from_file_location("seed_demo_desk_reads", SCRIPT)
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed.seed(db, NOW, history_days=2)
        db.commit()
        yield db


@pytest.mark.parametrize("side", ["bid", "ask"])
def test_a_demo_desk_reads_the_demo_board_as_simulated(session, side):
    reader = open_valuation_snapshot(session, caller=Caller(_principal()), as_of_utc=NOW,
                                     demo_desk=True)
    within_day = reader.price("TTF", DeliveryPeriod.gas_day(date(2026, 12, 3)), side)
    assert within_day.held
    assert within_day.input_class is InputClass.SIMULATED
    assert within_day.detail["basis"] == "quote"
    assert within_day.detail["depth_mwh"]


def test_a_customer_desk_never_reads_a_simulated_price(session):
    reader = open_valuation_snapshot(session, caller=Caller(_principal()), as_of_utc=NOW,
                                     demo_desk=False)
    assert not reader.price("TTF", DeliveryPeriod.gas_day(date(2026, 12, 3)), "bid").held
    assert not reader.price("TTF", DeliveryPeriod.month(2027, 1), "bid").held


def test_readiness_counts_the_demo_market_only_on_a_demo_desk(session, monkeypatch):
    monkeypatch.setenv("EUROGAS_NEXUS_DEMO_MARKS", "true")
    demo = readiness(session, _principal())
    assert demo["prices"]["ready"] is True
    assert demo["prices"]["simulated_sources"] == ["DEMO_Sim"]
    assert demo["book"]["ready"] and demo["prices"]["licensed_quote_sources"] == []
    monkeypatch.setenv("EUROGAS_NEXUS_DEMO_MARKS", "false")
    customer = readiness(session, _principal())
    assert customer["prices"]["simulated_sources"] == []
    assert customer["prices"]["ready"] is False
