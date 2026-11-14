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
