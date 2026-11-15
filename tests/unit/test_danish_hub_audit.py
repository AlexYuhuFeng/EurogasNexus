"""The Danish-hub audit lists ETF/GTF rows before and after, and corrects only with --commit."""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import Boolean, DateTime, Float, Integer, create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import ScreenOrderObservationRecord, UpstreamResourceContractRecord

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 11, 15, 9, tzinfo=UTC)


def _record(model, **values):
    for column in model.__table__.columns:
        if column.name in values or column.nullable or column.default is not None:
            continue
        kind = column.type
        values[column.name] = (
            NOW if isinstance(kind, DateTime)
            else 1.0 if isinstance(kind, Float)
            else 1 if isinstance(kind, Integer)
            else False if isinstance(kind, Boolean)
            else {} if kind.__class__.__name__ == "JSON"
            else "x"
        )
    return model(**values)


def _audit_module():
    spec = importlib.util.spec_from_file_location(
        "audit", ROOT / "scripts" / "ops" / "audit_danish_hub_references.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_audit_reports_before_and_after_and_writes_only_on_commit(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'a.sqlite'}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        session.add_all(
            [
                _record(UpstreamResourceContractRecord, contract_id="c-etf",
                        delivery_point_name="ETF", contract_name="Danish supply"),
                _record(UpstreamResourceContractRecord, contract_id="c-gtf",
                        delivery_point_name="GTF", contract_name="Bilateral"),
                _record(UpstreamResourceContractRecord, contract_id="c-ttf",
                        delivery_point_name="TTF", contract_name="Dutch supply"),
                _record(ScreenOrderObservationRecord, order_observation_id="o-1",
                        hub="TTF", product="ETF Dec-26", contract_code="ETF-DEC26"),
            ]
        )
        session.commit()
        audit = _audit_module()
        report = audit.audit(session)
        contracts = {item["id"]: item for item in report["tables"]["contracts"]["items"]}
        assert set(contracts) == {"c-etf", "c-gtf"}  # the Dutch contract is not listed
        assert (contracts["c-etf"]["before"], contracts["c-etf"]["after"]) == ("TTF", "ETF")
        assert (contracts["c-gtf"]["before"], contracts["c-gtf"]["after"]) == (None, "GTF")
        assert report["corrections"] == [
            {"table": "screen_order_observations", "id": "o-1", "column": "hub",
             "from": "TTF", "to": "ETF"}
        ]
        assert session.get(ScreenOrderObservationRecord, "o-1").hub == "TTF"  # dry run
        audit.audit(session, commit=True)
        assert session.get(ScreenOrderObservationRecord, "o-1").hub == "ETF"
