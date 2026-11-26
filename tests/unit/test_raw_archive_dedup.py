"""Each distinct raw page is stored once; every receipt still reads back its exact bytes."""

from __future__ import annotations

import gzip
import hashlib
import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models import RawPayloadArchiveRecord, RawPayloadContentRecord
from eurogas_nexus.db.repositories.raw_archive import (
    RawArchiveDigestMismatch,
    RawPayloadUnavailable,
    archive_raw_payload,
    load_raw_payload_bytes,
    load_raw_payload_json,
    load_raw_payload_text,
    move_inline_payloads_to_contents,
    restore_inline_payloads,
)

T0 = datetime(2026, 11, 1, 6, tzinfo=UTC)
PAGE = '{"operationaldatas": [{"pointKey": "ITP-00096", "value": 1.5}]}'


@pytest.fixture()
def session(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path.as_posix()}/archive.sqlite")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


def _archive(session, archive_id, text, received):
    return archive_raw_payload(
        session,
        archive_id=archive_id,
        source_system="ENTSOG",
        dataset="operationaldatas",
        source_reference="entsog-operationaldatas;offset=0",
        payload_text=text,
        payload_json=json.loads(text),
        payload_sha256=hashlib.sha256(text.encode()).hexdigest(),
        record_count=1,
        received_at_utc=received,
    )


def test_the_same_page_read_hourly_for_a_week_is_stored_once(session) -> None:
    for hour in range(168):
        _archive(session, f"raw-{hour}", PAGE, T0 + timedelta(hours=hour))
    session.commit()

    assert session.query(RawPayloadArchiveRecord).count() == 168
    contents = session.query(RawPayloadContentRecord).all()
    assert len(contents) == 1
    content = contents[0]
    assert content.byte_size == len(PAGE.encode())
    assert gzip.decompress(content.payload_compressed) == PAGE.encode()
    first = content.first_received_at_utc.replace(tzinfo=UTC)
    last = content.last_received_at_utc.replace(tzinfo=UTC)
    assert (first, last) == (T0, T0 + timedelta(hours=167))
    # The receipt keeps lineage only; the parsed JSON is not stored (it is reproducible).
    receipt = session.get(RawPayloadArchiveRecord, "raw-100")
    assert receipt.payload_text is None and receipt.payload_json is None
    assert load_raw_payload_text(session, "raw-100") == PAGE
    assert load_raw_payload_json(session, receipt) == json.loads(PAGE)


def test_a_changed_page_is_a_new_content_row(session) -> None:
    _archive(session, "raw-a", PAGE, T0)
    _archive(session, "raw-b", PAGE.replace("1.5", "1.6"), T0 + timedelta(hours=1))
    session.commit()
    assert session.query(RawPayloadContentRecord).count() == 2
    assert load_raw_payload_text(session, "raw-b").endswith('"value": 1.6}]}')


def test_a_digest_that_is_not_the_pages_is_refused(session) -> None:
    with pytest.raises(RawArchiveDigestMismatch):
        archive_raw_payload(
            session,
            archive_id="raw-x",
            source_system="ENTSOG",
            dataset="flows",
            source_reference="page:1",
            payload_text="{}",
            payload_sha256="0" * 64,
            record_count=0,
        )


def test_receipts_written_before_0096_are_moved_once_and_read_the_same(session) -> None:
    other = '{"other": true}'
    for number, text in enumerate([PAGE, PAGE, other, PAGE]):
        session.add(
            RawPayloadArchiveRecord(
                archive_id=f"legacy-{number}",
                source_system="ENTSOG",
                dataset="operationaldatas",
                source_reference="legacy",
                payload_text=text,
                payload_json=json.loads(text),
                payload_sha256=hashlib.sha256(text.encode()).hexdigest(),
                record_count=1,
                received_at_utc=T0 + timedelta(days=number),
                research_only=True,
                human_review_required=True,
            )
        )
    # A JSON-only legacy receipt, hashed over the canonical serialisation.
    canonical = json.dumps({"b": 1, "a": 2}, ensure_ascii=False, sort_keys=True)
    session.add(
        RawPayloadArchiveRecord(
            archive_id="legacy-json",
            source_system="GIE",
            dataset="agsi",
            source_reference="legacy",
            payload_text=None,
            payload_json={"b": 1, "a": 2},
            payload_sha256=hashlib.sha256(canonical.encode()).hexdigest(),
            record_count=1,
            received_at_utc=T0,
            research_only=True,
            human_review_required=True,
        )
    )
    # A legacy receipt whose stored page does not match its digest is never rewritten.
    session.add(
        RawPayloadArchiveRecord(
            archive_id="legacy-bad",
            source_system="ENTSOG",
            dataset="operationaldatas",
            source_reference="legacy",
            payload_text="tampered",
            payload_json=None,
            payload_sha256="f" * 64,
            record_count=1,
            received_at_utc=T0,
            research_only=True,
            human_review_required=True,
        )
    )
    session.commit()
    before = {f"legacy-{n}": load_raw_payload_bytes(session, f"legacy-{n}") for n in range(4)}

    preview = move_inline_payloads_to_contents(session, dry_run=True)
    assert preview["receipts_moved"] == 5
    assert session.query(RawPayloadContentRecord).count() == 0

    summary = move_inline_payloads_to_contents(session, limit=3)
    summary_rest = move_inline_payloads_to_contents(session, limit=100)
    session.commit()
    assert summary["receipts_moved"] + summary_rest["receipts_moved"] == 5
    assert summary_rest["receipts_left_digest_mismatch"] == 1
    assert session.query(RawPayloadContentRecord).count() == 3
    for archive_id, data in before.items():
        assert load_raw_payload_bytes(session, archive_id) == data
    assert load_raw_payload_json(session, "legacy-json") == {"a": 2, "b": 1}
    assert session.get(RawPayloadArchiveRecord, "legacy-bad").payload_text == "tampered"

    # The way back below 0096 puts each page on its receipt again.
    assert restore_inline_payloads(session) == 5
    session.commit()
    assert session.get(RawPayloadArchiveRecord, "legacy-2").payload_text == '{"other": true}'


def test_a_missing_page_is_reported_not_invented(session) -> None:
    receipt = _archive(session, "raw-a", PAGE, T0)
    session.query(RawPayloadContentRecord).delete()
    with pytest.raises(RawPayloadUnavailable):
        load_raw_payload_text(session, receipt)
