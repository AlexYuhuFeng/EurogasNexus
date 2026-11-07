"""The central-platform subscription reads a published view and loads it like a file import."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import ScreenOrderObservationRecord, TradingBookRecord

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "sync_central_platform.py"


def _load():
    spec = importlib.util.spec_from_file_location("sync_central_platform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def stores(tmp_path, monkeypatch):
    runtime_url = f"sqlite+pysqlite:///{tmp_path / 'runtime.sqlite'}"
    runtime = create_engine(runtime_url)
    Base.metadata.create_all(runtime)
    with Session(runtime) as session:
        session.add(TradingBookRecord(
            book_id="uk-nbp", name="UK NBP", legal_entity="NWG-UK", region="europe",
            business="gas", base_currency="GBP", active=True, updated_by="test",
            updated_at_utc=datetime(2026, 11, 1, tzinfo=UTC),
        ))
        session.commit()

    central_url = f"sqlite+pysqlite:///{tmp_path / 'central.sqlite'}"
    central = create_engine(central_url)
    with central.begin() as connection:
        connection.execute(text(
            "CREATE TABLE etrm_raw (trade_id TEXT, trade_time TEXT, book_id TEXT, hub TEXT,"
            " side TEXT, delivery_start TEXT, delivery_end TEXT, quantity REAL,"
            " quantity_unit TEXT, price REAL, price_unit TEXT, status TEXT,"
            " counterparty TEXT, internal_note TEXT)"
        ))
        connection.execute(text(
            "INSERT INTO etrm_raw VALUES"
            " ('T-1', '2026-11-02T09:15:00Z', 'uk-nbp', 'NBP', 'SELL', '2026-12-01',"
            "  '2026-12-31', 10000, 'MWh/d', 33.10, 'GBP/MWh', 'LIVE', 'Aldermoor', 'x'),"
            " ('T-2', '2026-11-02T10:00:00Z', 'uk-nbp', 'NBP', 'BUY', '2026-12-01',"
            "  '2026-12-31', 5000, 'MWh/d', 33.40, 'GBP/MWh', 'LIVE', 'Nordvik', NULL)"
        ))
        # The platform publishes a view; Eurogas Nexus never sees the raw table's extras.
        connection.execute(text(
            "CREATE VIEW egn_etrm_trades AS SELECT trade_id, trade_time, book_id, hub, side,"
            " delivery_start, delivery_end, quantity, quantity_unit, price, price_unit,"
            " status, counterparty FROM etrm_raw"
        ))
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", runtime_url)
    monkeypatch.setenv("EUROGAS_NEXUS_CENTRAL_PLATFORM_URL", central_url)
    return runtime, central


def test_a_platform_view_loads_through_the_etrm_importer(stores):
    runtime, central = stores
    sync = _load()
    assert sync.main(["--feed", "etrm-trades", "--view", "main.egn_etrm_trades",
                      "--system", "Endur"]) == 0
    with Session(runtime) as session:
        trades = session.query(ScreenOrderObservationRecord).all()
        assert sorted(trade.side for trade in trades) == ["BUY", "SELL"]
        assert {trade.book_id for trade in trades} == {"uk-nbp"}

    # A cancellation published on the platform removes the trade on the next sync.
    with central.begin() as connection:
        connection.execute(text("UPDATE etrm_raw SET status = 'CANCELLED' WHERE trade_id='T-2'"))
    assert sync.main(["--feed", "etrm-trades", "--view", "main.egn_etrm_trades",
                      "--system", "Endur"]) == 0
    with Session(runtime) as session:
        assert session.query(ScreenOrderObservationRecord).count() == 1


def test_only_a_plain_view_name_is_accepted(stores):
    sync = _load()
    status = sync.main(["--feed", "etrm-trades", "--view", "egn_etrm_trades; DROP TABLE x",
                        "--system", "Endur"])
    assert status == 2


def test_the_platform_url_is_required(stores, monkeypatch):
    monkeypatch.delenv("EUROGAS_NEXUS_CENTRAL_PLATFORM_URL")
    assert _load().main(["--feed", "fx", "--view", "egn_wmr", "--source", "WMR"]) == 2


def test_rows_become_the_importers_csv():
    sync = _load()
    text_out = sync.rows_as_csv(["a", "b"], [(1, None), ("x", 2.5)])
    assert text_out == "a,b\n1,\nx,2.5\n"
