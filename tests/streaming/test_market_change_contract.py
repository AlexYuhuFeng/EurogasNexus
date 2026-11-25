"""CODEX-1: the versioned wire form of a market change, for any later transport.

The envelope must carry exactly the DATA-1 change feed's digest (no value can ride along),
keep one partition key per fact across revisions, and refuse a version it does not know. The
change rows here come from the real outbox and feed on SQLite, not from a hand-written dict,
so the feed and the envelope cannot drift apart.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import eurogas_nexus.db.models  # noqa: F401  (registers every table)
from eurogas_nexus.application import market_events as outbox
from eurogas_nexus.application.change_feed import CHANGE_COLUMNS, read_changes
from eurogas_nexus.db.base import Base
from eurogas_nexus.domain.market_events import MarketEvent
from eurogas_nexus.streaming import MarketChangeV1, market_change_fields

NOW = datetime(2026, 11, 25, 9, 0, tzinfo=UTC)


def _price(price: str, *, at: datetime) -> MarketEvent:
    return MarketEvent(
        source_id="EEX",
        event_type="price.updated",
        subject_key="hub:TTF:2027-01",
        ingested_at_utc=at,
        market_time_utc=datetime(2026, 11, 24, 17, 30, tzinfo=UTC),
        published_at_utc=datetime(2026, 11, 24, 17, 30, tzinfo=UTC),
        payload={"price": price, "unit": "MWh", "currency": "EUR"},
        identity="hub:TTF:2027-01|EEX|2026-11-24",
    )


@pytest.fixture
def changes(tmp_path, monkeypatch) -> list[dict]:
    url = f"sqlite+pysqlite:///{(tmp_path / 'changes.sqlite').as_posix()}"
    monkeypatch.setenv("RUNTIME_STORE_DATABASE_URL", url)
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        outbox.publish(session, _price("80.0", at=NOW))
        outbox.publish(session, _price("81.5", at=NOW + timedelta(minutes=3)))  # a correction
        session.commit()
    with Session(engine) as session:
        return read_changes(session, None).changes


def test_the_envelope_carries_the_feeds_digest_and_nothing_else(changes) -> None:
    assert set(market_change_fields()) == set(CHANGE_COLUMNS) - {"cursor"}
    first, correction = (MarketChangeV1.from_change(change) for change in changes)

    assert (first.operation, correction.operation) == ("insert", "update")
    assert correction.supersedes_event_id == first.event_id
    # One partition key per fact: both revisions of the TTF settlement share it.
    assert first.broker_key() == correction.broker_key() == changes[0]["event_key"]
    wire = json.loads(correction.to_wire())
    assert wire["kind"] == "market.change" and wire["schema_version"] == 1
    assert "price" not in wire and "payload" not in wire and "cursor" not in wire
    assert wire["ingested_at_utc"].endswith("Z")
    assert MarketChangeV1.decode(correction.to_wire()) == correction


@pytest.mark.parametrize(
    "change",
    [
        {"schema_version": 2},
        {"kind": "opportunity.input.invalidated"},
        {"event_type": "market.quote"},
        {"price": "81.5"},
        {"ingested_at_utc": "2026-11-25T09:00:00"},
        {"operation": "insert"},
        {"supersedes_event_id": None},
    ],
)
def test_a_consumer_refuses_what_it_does_not_know(changes, change) -> None:
    wire = json.loads(MarketChangeV1.from_change(changes[1]).to_wire())
    with pytest.raises(ValidationError):
        MarketChangeV1.decode(json.dumps({**wire, **change}))


@pytest.mark.parametrize("field", ["kind", "schema_version"])
def test_dispatch_metadata_is_required(changes, field) -> None:
    wire = json.loads(MarketChangeV1.from_change(changes[0]).to_wire())
    wire.pop(field)
    with pytest.raises(ValidationError, match=field):
        MarketChangeV1.decode(json.dumps(wire))


def test_the_superseded_ingestion_notice_is_an_outbox_event_already() -> None:
    # The research branch proposed a run-level IngestionInvalidationV1. The outbox records the
    # same fact as source.ingested with the run as its identity; the envelope accepts it.
    from eurogas_nexus.domain.market_events.model import EVENT_TYPES

    assert "source.ingested" in EVENT_TYPES
    import eurogas_nexus.streaming.contracts as contracts

    assert not hasattr(contracts, "IngestionInvalidationV1")
