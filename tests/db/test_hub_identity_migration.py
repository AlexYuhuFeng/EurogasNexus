"""Migration 0091: rows stored under a hub's other name move to its registry code."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import (
    MarketObservationRecord,
    MarketQuoteRecord,
    TraderMandateRecord,
)
from eurogas_nexus.db.models.reference_network import ReferenceMarketHub

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 26, 9, tzinfo=UTC)


def _migration():
    spec = importlib.util.spec_from_file_location(
        "m0091", ROOT / "alembic" / "versions" / "0091_hub_one_identity.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _filled(model, **values):
    for column in model.__table__.columns:
        if column.name in values or column.nullable or column.default is not None:
            continue
        name = type(column.type).__name__
        values[column.name] = (
            NOW if "DateTime" in name else 1.0 if name in {"Float", "Numeric"}
            else 1 if name == "Integer" else False if name == "Boolean"
            else [] if name == "JSON" else "x"
        )
    return model(**values)


def _quote(quote_id: str, hub: str, product: str, *, simulated: bool):
    return _filled(MarketQuoteRecord, quote_id=quote_id, hub=hub, product=product,
                   simulated=simulated, source_system="DEMO_Sim" if simulated else "EEX")


def test_gtf_and_vtp_rows_move_to_the_registry_code(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'm.sqlite'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all([
            _quote("licensed-gtf", "GTF", "day-ahead", simulated=False),
            _quote("licensed-vtp", "VTP", "day-ahead", simulated=False),
            _quote("demo-gtf", "GTF", "day-ahead", simulated=True),
            _quote("demo-board", "TTF", "Jan-27", simulated=True),
            _quote("old-bom", "TTF", "bom nov-26", simulated=False),
            _filled(MarketObservationRecord, observation_id="obs-gtf", product="GTF Jan-27",
                    source_system="EEX", metadata_json={"hub": "GTF"}),
            _filled(MarketObservationRecord, observation_id="demo-gtf-ma",
                    product="GTF month-ahead", source_system="DEMO_Sim"),
            _filled(TraderMandateRecord, mandate_id="m-1", hubs=["TTF", "GTF", "ETF"]),
            _filled(ReferenceMarketHub, id="hub-vtp-00001", hub_code="GTF", name="GTF"),
        ])
        session.commit()

    with engine.begin() as connection:
        with Operations.context(MigrationContext.configure(connection)):
            _migration().upgrade()

    with Session(engine) as session:
        quotes = {row.quote_id: row for row in session.query(MarketQuoteRecord)}
        assert "demo-gtf" not in quotes  # the demo's second invented series is gone
        assert (quotes["licensed-gtf"].hub, quotes["licensed-vtp"].hub) == ("ETF", "CEGH")
        assert quotes["demo-board"].product == "jan-27"
        assert quotes["old-bom"].product == "bom"
        assert session.get(MarketObservationRecord, "demo-gtf-ma") is None
        moved = session.get(MarketObservationRecord, "obs-gtf")
        assert moved.product == "ETF Jan-27" and moved.metadata_json["hub"] == "ETF"
        assert session.get(TraderMandateRecord, "m-1").hubs == ["TTF", "ETF"]
        assert session.get(ReferenceMarketHub, "hub-vtp-00001").hub_code == "ETF"
