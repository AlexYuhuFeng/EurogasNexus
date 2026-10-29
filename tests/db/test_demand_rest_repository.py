"""Real SQLAlchemy/SQLite tests for REST National Gas demand persistence."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models.demand import NationalGasActualDemandRecord
from eurogas_nexus.db.repositories.demand import DemandPublicationConflict
from eurogas_nexus.db.repositories.demand_rest import (
    DemandRestInsertSummary,
    DemandRestPublicationConflict,
    insert_demand_rest_rows,
)
from eurogas_nexus.ingestion.national_gas_rest import parse_national_gas_rest

RECEIVED = datetime(2026, 10, 27, 13, 0, tzinfo=UTC)
LATER = RECEIVED + timedelta(hours=2)
WINDOW_FROM = date(2026, 10, 1)
WINDOW_TO = date(2026, 10, 31)
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


def _record(
    *,
    applicable_at: str = "2026-10-22T12:20:01+01:00",
    applicable_for: str = "2026-10-21",
    value: str = "176.708",
    generated: str = "2026-10-22T12:20:01+01:00",
    quality: str = "",
    substituted: str = "N",
    created: str = "2026-10-22T12:20:01+01:00",
) -> dict[str, str]:
    return {
        "applicableAt": applicable_at,
        "applicableFor": applicable_for,
        "value": value,
        "generatedTimeStamp": generated,
        "qualityIndicator": quality,
        "substituted": substituted,
        "createdDate": created,
    }


def _group(item: str, *records: dict[str, str]) -> dict[str, object]:
    return {
        "publicationId": item,
        "publicationName": LABELS[item],
        "publications": list(records),
        "unit": "mscm",
    }


def _parse(
    *groups: dict[str, object],
    received: datetime = RECEIVED,
    available: datetime | None = None,
):
    payload = json.dumps(list(groups), ensure_ascii=True, separators=(",", ":")).encode()
    return parse_national_gas_rest(
        payload,
        date_from=WINDOW_FROM,
        date_to=WINDOW_TO,
        received_at_utc=received,
        available_at_utc=available,
    )


def _count(session: Session) -> int:
    return (
        session.scalar(
            select(func.count()).select_from(NationalGasActualDemandRecord)
        )
        or 0
    )


def _stored(session: Session) -> list[NationalGasActualDemandRecord]:
    return list(session.scalars(select(NationalGasActualDemandRecord)))


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def test_actual_adapter_parse_persist_and_replay_keeps_first_receipt(session: Session):
    groups = (
        _group("PUBOB637", _record()),
        _group(
            "PUBOB652",
            _record(
                applicable_at="2026-10-23T12:00:00+01:00",
                applicable_for="2026-10-22",
                value="0.000",
                generated="2026-10-23T12:00:00+01:00",
                created="2026-10-23T12:00:00+01:00",
            ),
        ),
    )
    first_rows = _parse(*groups, received=RECEIVED)
    first = insert_demand_rest_rows(session, first_rows)
    session.commit()

    assert first == DemandRestInsertSummary(
        rows_seen=2,
        inserted=2,
        duplicates=0,
        publications=2,
    )

    replay_rows = _parse(
        *groups,
        received=LATER,
        available=LATER + timedelta(minutes=5),
    )
    replay = insert_demand_rest_rows(session, replay_rows)
    session.commit()

    assert replay == DemandRestInsertSummary(
        rows_seen=2,
        inserted=0,
        duplicates=2,
        publications=2,
    )
    assert _count(session) == 2

    stored = _stored(session)
    for row in stored:
        assert row.source_format == "REST"
        assert row.published_at_utc is None
        assert _as_utc(row.received_at_utc) == RECEIVED
        assert _as_utc(row.available_at_utc) == RECEIVED
        assert _as_utc(row.ingested_at_utc) == RECEIVED
        assert row.rest_provenance is not None
        assert row.rest_provenance["received_at_utc"] == RECEIVED.isoformat()
        assert row.rest_provenance["published_at_utc"] is None

    by_item = {row.provider_item_id: row for row in stored}
    assert by_item["PUBOB637"].provisional_status == "PROVISIONAL_INITIAL"
    assert by_item["PUBOB637"].is_provisional is True
    assert by_item["PUBOB652"].value_text == "0.000"
    assert by_item["PUBOB652"].value_is_blank is False
    assert by_item["PUBOB652"].provisional_status == "UNRESOLVED_D_PLUS_6"
    assert by_item["PUBOB652"].is_provisional is None


def test_blanks_and_zero_remain_distinct(session: Session):
    rows = _parse(
        _group("PUBOB637", _record(value="")),
        _group("PUBOB652", _record(value="0.000")),
    )
    summary = insert_demand_rest_rows(session, rows)
    session.commit()

    assert summary.inserted == 2
    stored = {row.provider_item_id: row for row in _stored(session)}

    blank = stored["PUBOB637"]
    assert blank.value_text == ""
    assert blank.value_is_blank is True
    assert blank.quality_indicator is None
    assert blank.rest_provenance is not None
    assert blank.rest_provenance["value_decimal"] is None

    zero = stored["PUBOB652"]
    assert zero.value_text == "0.000"
    assert zero.value_is_blank is False
    assert zero.rest_provenance is not None
    assert zero.rest_provenance["value_decimal"] == "0.000"


def test_late_amendment_appends_and_preserves_each_receipt(session: Session):
    original = _parse(_group("PUBOB637", _record()), received=RECEIVED)
    insert_demand_rest_rows(session, original)
    session.commit()

    amended = _parse(
        _group(
            "PUBOB637",
            _record(
                value="180.000",
                generated="2026-10-23T08:00:00+01:00",
                created="2026-10-23T08:00:00+01:00",
                quality="A",
            ),
        ),
        received=LATER,
    )
    summary = insert_demand_rest_rows(session, amended)
    session.commit()

    assert summary.inserted == 1
    assert summary.duplicates == 0
    assert _count(session) == 2
    assert original[0].source_publication_id != amended[0].source_publication_id

    stored = sorted(_stored(session), key=lambda row: row.generated_at_raw)
    assert [row.value_text for row in stored] == ["176.708", "180.000"]
    assert _as_utc(stored[0].received_at_utc) == RECEIVED
    assert _as_utc(stored[1].received_at_utc) == LATER
    assert stored[1].quality_indicator == "A"
    assert stored[1].rest_provenance is not None
    assert stored[1].rest_provenance["quality_flag"] == "AMENDED"


def test_conflicting_same_identity_batch_is_refused_atomically(session: Session):
    original = _parse(_group("PUBOB637", _record()), received=RECEIVED)
    insert_demand_rest_rows(session, original)
    session.commit()

    new_revision = _parse(
        _group(
            "PUBOB637",
            _record(
                applicable_at="2026-10-23T12:20:01+01:00",
                applicable_for="2026-10-22",
                value="170.000",
                generated="2026-10-23T12:20:01+01:00",
                created="2026-10-23T12:20:01+01:00",
            ),
        ),
        received=LATER,
    )[0]
    tampered = replace(
        original[0],
        value_text="999.000",
        value_decimal=Decimal("999.000"),
        value_is_blank=False,
    )

    with pytest.raises(DemandRestPublicationConflict) as raised:
        insert_demand_rest_rows(session, [new_revision, tampered])

    assert isinstance(raised.value, DemandPublicationConflict)
    assert _count(session) == 1
    only = _stored(session)[0]
    assert only.record_id == original[0].record_id
    assert only.value_text == "176.708"


def test_provider_clocks_roundtrip_without_claiming_naive_utc(session: Session):
    raw_clock = "2026-10-22T12:20:01+05:30"
    rows = _parse(
        _group(
            "PUBOB637",
            _record(
                applicable_at=raw_clock,
                generated=raw_clock,
                created=raw_clock,
                quality="S",
                substituted="Y",
            ),
        ),
        received=datetime(2026, 10, 22, 7, 0, tzinfo=UTC),
    )
    insert_demand_rest_rows(session, rows)
    session.commit()

    stored = _stored(session)[0]
    assert stored.published_at_utc is None
    assert stored.applicable_at_raw == raw_clock
    assert stored.generated_at_raw == raw_clock
    assert stored.applicable_at_naive == datetime(2026, 10, 22, 12, 20, 1)
    assert stored.generated_at_naive == datetime(2026, 10, 22, 12, 20, 1)
    assert stored.applicable_at_naive != datetime(2026, 10, 22, 6, 50, 1)

    provenance = stored.rest_provenance
    assert provenance is not None
    assert provenance["applicable_at_raw"] == raw_clock
    assert provenance["applicable_at_utc"] == "2026-10-22T06:50:01+00:00"
    assert provenance["applicable_at_wall_clock_naive"] == "2026-10-22T12:20:01"
    assert provenance["generated_at_raw"] == raw_clock
    assert provenance["generated_at_utc"] == "2026-10-22T06:50:01+00:00"
    assert provenance["generated_at_wall_clock_naive"] == "2026-10-22T12:20:01"
    assert provenance["created_at_raw"] == raw_clock
    assert provenance["created_at_utc"] == "2026-10-22T06:50:01+00:00"
    assert provenance["created_at_wall_clock_naive"] == "2026-10-22T12:20:01"
    assert (
        provenance["provider_timestamp_upper_bound_utc"]
        == "2026-10-22T06:50:01+00:00"
    )
    assert provenance["evidence_basis"] == "PROVIDER_DECLARED_TIMESTAMP_UPPER_BOUND"
    assert provenance["quality_indicator_raw"] == "S"
    assert provenance["quality_flag"] == "SUBSTITUTED"
    assert provenance["substituted_raw"] == "Y"
    assert provenance["is_substituted"] is True
    assert _as_utc(stored.available_at_utc) == datetime(2026, 10, 22, 7, 0, tzinfo=UTC)
