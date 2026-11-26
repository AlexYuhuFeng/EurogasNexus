"""A bounded read refuses past its bound instead of computing on part (backend audit A4)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.api.error_handlers import register_error_handlers
from eurogas_nexus.application import remit_outages
from eurogas_nexus.application.bounded_reads import ReadBoundExceeded, read_bounded
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import RemitUmmRecord


class _Query:
    def __init__(self, rows):
        self.rows = rows
        self.asked = None

    def limit(self, n):
        self.asked = n
        return self

    def all(self):
        return self.rows[: self.asked]


def test_within_the_bound_every_row_is_returned() -> None:
    query = _Query(list(range(5)))
    assert read_bounded(query, 5, what="test") == [0, 1, 2, 3, 4]
    assert query.asked == 6  # one past the bound, to see whether there is more


def test_past_the_bound_the_read_refuses() -> None:
    with pytest.raises(ReadBoundExceeded) as caught:
        read_bounded(_Query(list(range(6))), 5, what="market observation")
    assert caught.value.code == "read_bound_exceeded"
    assert caught.value.bound == 5


def test_the_api_answers_a_bound_as_a_coded_422() -> None:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/calc")
    def calc() -> None:
        raise ReadBoundExceeded("market observation", 20_000)

    body = TestClient(app).get("/calc").json()
    assert body["error"] == "read_bound_exceeded"
    assert body["family"] == "VALIDATION"
    assert body["params"] == {"what": "market observation", "bound": 20_000}
    assert "20,000" in body["fallback_message"]


def _umm(index: int, now: datetime) -> RemitUmmRecord:
    return RemitUmmRecord(
        record_id=f"r{index}", message_id=f"m{index}", version=1,
        published_at_utc=now - timedelta(days=2), event_status="active",
        unavailability_type="planned", event_start_utc=now - timedelta(days=1),
        event_stop_utc=now + timedelta(days=3), asset_name=f"Asset {index}",
        asset_eic=f"21W{index:013d}", asset_type="storage", balancing_zone="NL",
        direction="withdrawal", unit="GWh/d", unavailable_capacity=10.0, reason="test",
        market_participant="Operator", remarks="", source_reference="test",
        ingested_at_utc=now,
    )


def test_outages_past_the_open_message_bound_refuse(tmp_path, monkeypatch) -> None:
    engine = create_engine(f"sqlite+pysqlite:///{(tmp_path / 'r.sqlite').as_posix()}")
    Base.metadata.create_all(engine)
    now = datetime(2026, 11, 26, 12, tzinfo=UTC)
    with Session(engine) as session:
        for index in range(4):
            session.add(_umm(index, now))
        session.commit()
        monkeypatch.setattr(remit_outages, "MAX_OPEN_MESSAGES", 4)
        remit_outages.load_outage_rows(session, now=now, horizon_days=30)
        monkeypatch.setattr(remit_outages, "MAX_OPEN_MESSAGES", 3)
        with pytest.raises(ReadBoundExceeded):
            remit_outages.load_outage_rows(session, now=now, horizon_days=30)
