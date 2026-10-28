"""Real SQLAlchemy/SQLite tests for append-only demand persistence."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models.demand import NationalGasActualDemandRecord
from eurogas_nexus.db.repositories.demand import (
    DemandPublicationConflict,
    insert_demand_rows,
    list_demand_rows,
)
from eurogas_nexus.ingestion.national_gas_demand import parse_national_gas_csv

RECEIVED = datetime(2026, 10, 27, 13, 0, tzinfo=UTC)
HEADER = "Applicable At,Applicable For,Data Item,Value,Generated Time,Quality Indicator\n"
LABELS = {
    "PUBOB637": "Demand Actual, NTS, D+1",
    "PUBOB652": "Demand Actual, NTS, D+6",
}


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[NationalGasActualDemandRecord.__table__])
    with Session(engine) as active:
        yield active


def rows(
    item: str = "PUBOB637",
    *,
    value: str = "176.708",
    generated: str = "22/10/2026 12:20:01",
    gas_day: str = "21/10/2026",
    quality: str = "",
):
    document = (
        HEADER
        + f'22/10/2026 12:20:01,{gas_day},"{LABELS[item]}",'
        + f"{value},{generated},{quality}\n"
    )
    return parse_national_gas_csv(
        document,
        provider_item_id=item,
        date_from=date(2026, 10, 1),
        date_to=date(2026, 10, 31),
        received_at_utc=RECEIVED,
    )


def count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(NationalGasActualDemandRecord)) or 0


def test_append_replay_is_idempotent(session: Session):
    first = insert_demand_rows(session, rows())
    session.commit()
    replay = insert_demand_rows(session, rows())
    session.commit()

    assert first.inserted == 1
    assert replay.inserted == 0
    assert replay.duplicates == 1
    assert count(session) == 1
    stored = session.scalar(select(NationalGasActualDemandRecord))
    assert stored is not None
    assert stored.value_text == "176.708"


def test_duplicate_rows_inside_one_batch_are_counted_once(session: Session):
    batch = rows() + rows()
    summary = insert_demand_rows(session, batch)
    session.commit()

    assert summary.rows_seen == 2
    assert summary.inserted == 1
    assert summary.duplicates == 1
    assert count(session) == 1


def test_revisions_with_different_generated_time_append(session: Session):
    insert_demand_rows(session, rows(value="176.695", generated="22/10/2026 16:20:00"))
    insert_demand_rows(session, rows(value="176.708", generated="22/10/2026 12:20:01"))
    session.commit()

    stored = list(session.scalars(select(NationalGasActualDemandRecord)))
    assert len(stored) == 2
    assert {row.value_text for row in stored} == {"176.695", "176.708"}


def test_conflicting_publication_identity_is_refused_atomically(session: Session):
    insert_demand_rows(session, rows(value="176.708"))
    session.commit()

    new_day = rows(value="173.540", gas_day="20/10/2026", generated="21/10/2026 12:20:01")
    conflicting = rows(value="176.700")  # same generated/applicable identity, changed value
    with pytest.raises(DemandPublicationConflict):
        insert_demand_rows(session, [*new_day, *conflicting])

    assert count(session) == 1
    only = session.scalar(select(NationalGasActualDemandRecord))
    assert only is not None
    assert only.value_text == "176.708"


def test_outer_transaction_rollback_leaves_no_partial_batch(session: Session):
    with pytest.raises(RuntimeError):
        with session.begin():
            insert_demand_rows(session, rows(value="176.708"))
            insert_demand_rows(session, rows(value="173.540", gas_day="20/10/2026"))
            raise RuntimeError("operator transaction aborted")

    assert count(session) == 0


def test_batch_query_filters_and_preserves_text_decimal(session: Session):
    insert_demand_rows(session, rows(value="176.590"))
    insert_demand_rows(
        session,
        rows(
            "PUBOB652",
            value="176.596",
            generated="27/10/2026 12:00:00",
            quality="A",
        ),
    )
    session.commit()

    d6 = list_demand_rows(session, provider_item_id="PUBOB652")
    assert len(d6) == 1
    assert d6[0].value_text == "176.596"
    assert d6[0].quality_indicator == "A"
    assert d6[0].published_at_utc is None

    filtered = list_demand_rows(
        session,
        term="D+1",
        gas_day_from=date(2026, 10, 21),
        gas_day_to=date(2026, 10, 21),
    )
    assert [row.value_text for row in filtered] == ["176.590"]
