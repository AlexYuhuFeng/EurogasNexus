"""The fictional demo desk: invented names, flagged prices, limits that tell a known story."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.core.config import demo_marks_allowed
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    CreditLineRecord,
    MarketObservationRecord,
    UpstreamResourceContractRecord,
)

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "demo" / "seed_demo_desk.py"
REAL_FIRMS = ("centrica", "equinor", "rwe", "shell", "bp ", "uniper", "engie", "eni ", "orsted")


def _load():
    spec = importlib.util.spec_from_file_location("seed_demo_desk", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db


def test_limits_are_sized_from_the_book_into_ok_watch_and_breach(session):
    seed = _load()
    sizing = seed.seed(session, datetime(2026, 11, 7, 9, tzinfo=UTC))
    session.commit()

    utilisation = {cpty: row["net"] / row["limit"] for cpty, row in sizing.items()}
    assert utilisation["ALD"] < 0.75  # ok
    assert 0.75 <= utilisation["NVK"] <= 1.0  # watch
    assert utilisation["RHM"] > 1.0  # breach, with a stated cause
    assert "letter of credit" in sizing["RHM"]["why"]
    assert session.query(CreditLineRecord).count() == 3


def test_every_name_is_fictional_and_every_price_is_flagged(session):
    seed = _load()
    seed.seed(session, datetime(2026, 11, 7, 9, tzinfo=UTC))
    session.commit()

    names = [line.name.lower() for line in session.query(CreditLineRecord)]
    names += [c.contract_name.lower() for c in session.query(UpstreamResourceContractRecord)]
    for name in names:
        assert not any(firm in f"{name} " for firm in REAL_FIRMS), name
    prices = session.query(MarketObservationRecord).all()
    assert prices
    assert all(row.source_system.endswith("_Sim") for row in prices)
    assert all((row.metadata_json or {}).get("simulated") is True for row in prices)


def test_reseeding_replaces_the_demo_rows(session):
    seed = _load()
    now = datetime(2026, 11, 7, 9, tzinfo=UTC)
    seed.seed(session, now)
    session.commit()
    seed.seed(session, now)
    session.commit()
    assert session.query(CreditLineRecord).count() == 3
    assert session.query(UpstreamResourceContractRecord).count() == 3


def test_the_seed_refuses_release_and_demo_marks_stay_off_by_default(monkeypatch, capsys):
    monkeypatch.setenv("EUROGAS_NEXUS_ENV", "release")
    assert _load().main() == 2
    assert "refused" in capsys.readouterr().err

    monkeypatch.setenv("EUROGAS_NEXUS_DEMO_MARKS", "true")
    assert demo_marks_allowed() is False  # never in trial or release

    monkeypatch.setenv("EUROGAS_NEXUS_ENV", "development")
    monkeypatch.delenv("EUROGAS_NEXUS_DEMO_MARKS")
    assert demo_marks_allowed() is False  # off unless asked for
    monkeypatch.setenv("EUROGAS_NEXUS_DEMO_MARKS", "true")
    assert demo_marks_allowed() is True


def test_market_around_the_book_is_simulated_and_fills_the_balance_and_map(session):
    from datetime import date

    from eurogas_nexus.application.map_situation import build_map_situation
    from eurogas_nexus.application.pipeline_supply import landed_supply
    from eurogas_nexus.db.models import FlowObservationRecord, ReferenceNode
    from eurogas_nexus.db.models.observation import (
        LngObservationRecord,
        StorageObservationRecord,
    )
    from eurogas_nexus.db.models.power import PowerObservationRecord

    now = datetime(2026, 11, 7, 9, tzinfo=UTC)
    seed = _load()
    seed.seed(session, now)
    session.commit()

    assert session.query(ReferenceNode).count() > 200  # the shipped reference network
    for model in (FlowObservationRecord, StorageObservationRecord, LngObservationRecord):
        rows = session.query(model).all()
        assert rows
        assert all(row.source_system == "DEMO_Sim" for row in rows)
        assert all((row.metadata_json or {}).get("simulated") is True for row in rows)
    power = session.query(PowerObservationRecord).all()
    assert power and all(row.source_system == "DEMO_Sim" for row in power)
    # No simulated power price: it could be read as a market price.
    assert not {row.metric for row in power} & {"day_ahead_price", "market_index_price"}

    supply = landed_supply(session, date(2025, 9, 1), as_of=now)
    assert len(supply.by_day) >= 395  # 400 gas days, every landing point every day
    assert supply.incomplete_days == []
    assert 3_000 < max(supply.by_day.values()) < 7_000  # GWh/d, a believable NWE landing

    payload = build_map_situation(session, now=now, entitled=lambda rows: list(rows))
    assert len(payload["flows"]) >= 20


def test_reseeding_keeps_one_copy_of_the_simulated_history(session):
    from eurogas_nexus.db.models import FlowObservationRecord

    seed = _load()
    now = datetime(2026, 11, 7, 9, tzinfo=UTC)
    seed.seed(session, now)
    session.commit()
    first = session.query(FlowObservationRecord).count()
    seed.seed(session, now)
    session.commit()
    assert session.query(FlowObservationRecord).count() == first


# --- roll-forward after a paused server ----------------------------------------------


def _snapshot(session):
    """Every stored demo row's key and value, to prove earlier rows are never rewritten."""

    from eurogas_nexus.db.models import FlowObservationRecord, PowerObservationRecord
    from eurogas_nexus.db.models.observation import LngObservationRecord, StorageObservationRecord

    rows = {}
    for model, value in (
        (FlowObservationRecord, "original_value"),
        (StorageObservationRecord, "inventory_twh"),
        (LngObservationRecord, "send_out_twh_d"),
        (PowerObservationRecord, "value"),
        (MarketObservationRecord, "price"),
    ):
        for row in session.query(model):
            rows[(model.__name__, row.observation_id)] = getattr(row, value)
    return rows


def test_roll_forward_after_a_30_day_pause_ends_at_today_and_keeps_every_stored_row(session):
    from sqlalchemy import func

    from eurogas_nexus.db.models import (
        ContractDeliveryRecord,
        FlowObservationRecord,
        PowerObservationRecord,
    )

    seed = _load()
    seeded_at = datetime(2026, 10, 8, 9, tzinfo=UTC)
    seed.seed(session, seeded_at, history_days=40)
    session.commit()
    # A tester's own edit to a demo row and a tester's own contract must survive.
    line = session.get(CreditLineRecord, "RHM")
    line.limit_amount = 5_000_000
    session.add(
        UpstreamResourceContractRecord(
            contract_id="tester-own-1", contract_name="Tester contract",
            resource_type="PIPELINE_IMPORT", delivery_point_name="TTF", gas_year="2026/27",
            delivery_quantity_mwh_per_day=1000.0, contract_price_gbp_mwh=30.0,
            settlement_frequency="monthly", upstream_payment_lag_days=20,
            screen_sale_cash_lag_days=1, delivery_tolerance_pct=5.0,
            nomination_tolerance_pct=2.0, annual_financing_rate_pct=5.0,
            allowed_exit_points=["TTF"], eligible_sale_modes=["LOCAL_MARKET_SALE"],
            created_at_utc=seeded_at, updated_at_utc=seeded_at,
        )
    )
    session.commit()
    before = _snapshot(session)

    later = datetime(2026, 11, 7, 9, tzinfo=UTC)  # the server was paused for 30 days
    counts = seed.roll_forward(session, later)
    session.commit()

    after = _snapshot(session)
    assert all(after[key] == value for key, value in before.items())  # nothing rewritten
    assert counts["physical_rows"] > 0
    assert counts["month_ahead_rows"] == 2 * 30  # Oct 8 to Nov 6, both hubs
    newest_flow = session.query(func.max(FlowObservationRecord.period_start_utc)).scalar()
    assert seed._gas_day_of(newest_flow) == seed._closed_gas_days(later, 1)[0][0]
    newest_power = session.query(func.max(PowerObservationRecord.period_start_utc)).scalar()
    assert newest_power.date() == datetime(2026, 11, 6).date()
    curve = (
        session.query(MarketObservationRecord)
        .filter(MarketObservationRecord.source_reference == "demo:curve")
        .order_by(MarketObservationRecord.observed_at_utc.desc())
        .first()
    )
    assert curve.observed_at_utc.date() == later.date()
    assert all(
        (row.metadata_json or {}).get("simulated") is True
        for row in session.query(MarketObservationRecord)
    )
    deliveries = session.query(func.max(ContractDeliveryRecord.gas_day)).scalar()
    assert deliveries == datetime(2026, 11, 6).date()
    assert counts["outage_rows"] == 2  # the demo outages had ended during the pause
    assert session.get(CreditLineRecord, "RHM").limit_amount == 5_000_000
    assert session.get(UpstreamResourceContractRecord, "tester-own-1") is not None

    # Idempotent: a second start the same day adds nothing.
    total = len(after)
    again = seed.roll_forward(session, later)
    session.commit()
    assert again.get("physical_rows", 0) == 0
    assert again["curve_rows"] == again["month_ahead_rows"] == again["delivery_rows"] == 0
    assert again["outage_rows"] == 0
    assert len(_snapshot(session)) == total


def test_roll_forward_leaves_an_unseeded_store_alone(session):
    seed = _load()
    assert seed.roll_forward(session, datetime(2026, 11, 7, 9, tzinfo=UTC)) == {"seeded": 0}
