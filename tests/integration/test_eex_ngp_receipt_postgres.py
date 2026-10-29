"""Real PostgreSQL tests for RFC0006 stage B EEX NGP receipt persistence.

Every payload below is a synthetic development fixture. No test contacts EEX,
uses a provider key, activates a source or claims a live market price. Each test
creates its own uniquely named disposable schema, exercises the actual
``market_observations``/``raw_payload_archives`` tables and drops the schema
afterwards (the ENTSOG bounded-persistence pattern).

The explicit delivery-calendar contract cites the RFC0006 source chain only as
test evidence. It is not certification, rights clearance or source activation.
"""

from __future__ import annotations

import hashlib
import os
import re
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from eurogas_nexus.db.models import (
    MarketObservationRecord,
    RawPayloadArchiveRecord,
)
from eurogas_nexus.db.repositories.eex_ngp_persistence import (
    EexNgpInvalidObservationError,
    EexNgpRevisionRequiresHistoryError,
    upsert_eex_ngp_observation_rows,
)
from eurogas_nexus.domain.market.gas_day import EU_CAM_UTC_CALENDAR
from eurogas_nexus.domain.market_intelligence.source_price import (
    STATUS_EXACT,
    resolve_source_price,
)
from eurogas_nexus.domain.observations.market import ObservationFreshness
from eurogas_nexus.ingestion import eex_ngp_ingestion as ingestion
from eurogas_nexus.ingestion.eex_ngp import (
    SOURCE_DATASET,
    SOURCE_REFERENCE,
    SOURCE_SYSTEM,
    EexNgpGasDayCalendarContract,
    EexNgpParseError,
    eex_ttf_ngp_market_observations,
    eex_ttf_ngp_receipt_observations,
    parse_eex_ttf_ngp_csv,
)
from eurogas_nexus.ingestion.eex_public_download import (
    OFFICIAL_SOURCE_URL,
    EexPublicCapture,
)

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUNTIME_STORE_DATABASE_URL", "").startswith("postgresql"),
    reason=(
        "RUNTIME_STORE_DATABASE_URL must point at PostgreSQL; run via "
        "scripts/ci/run_postgres_ci.sh or the disposable local test database"
    ),
)

FIRST_RECEIPT = datetime(2026, 5, 29, 15, 5, tzinfo=UTC)
LATER_RECEIPT = FIRST_RECEIPT + timedelta(hours=2)
HEADER = "Gasday;IndexValue (€/MWh);IndexVolume (MWh);Status;Timestamp Let"
ROW_FINAL = "29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:30"
ROW_TEMPORARY = "29/05/2026;31.500;42.25;Temporary NGP;29/05/2026 14:45"
CALENDAR_EVIDENCE = (
    "RFC-0006 synthetic integration evidence: EEX Index Description v25 sections 1 and 2.5 "
    "and Contract Specifications 0105a section 1.2.3 place the NGP delivery day at 06:00 "
    "Europe/Berlin, represented by EU-CAM-UTC-2025. Test evidence only; no rights "
    "certification or source activation."
)
RECEIPT_ID_PATTERN = re.compile(r"eex-ngp-r1-[0-9a-f]{48}")


def _calendar() -> EexNgpGasDayCalendarContract:
    return EexNgpGasDayCalendarContract(
        calendar_id=EU_CAM_UTC_CALENDAR,
        evidence=CALENDAR_EVIDENCE,
    )


def _capture(
    *rows: str,
    receipt: datetime = FIRST_RECEIPT,
    bom: bool = True,
    newline: str = "\r\n",
    header: str = HEADER,
    source_url: str = OFFICIAL_SOURCE_URL,
    final_url: str = OFFICIAL_SOURCE_URL,
    status_code: int = 200,
) -> EexPublicCapture:
    text_payload = newline.join([header, *(rows or (ROW_FINAL,))]) + newline
    body = text_payload.encode("utf-8")
    if bom:
        body = b"\xef\xbb\xbf" + body
    return EexPublicCapture(
        raw_bytes=body,
        source_url=source_url,
        final_url=final_url,
        retrieved_at_utc=receipt,
        content_type="text/csv",
        content_encoding="identity",
        status_code=status_code,
        http_attempts=1,
        redirect_count=0,
    )


@contextmanager
def _session():
    url = make_url(os.environ["RUNTIME_STORE_DATABASE_URL"])
    connect_args = {"timeout": 5} if url.get_driver_name() == "pg8000" else {"connect_timeout": 5}
    engine = create_engine(url, future=True, connect_args=connect_args)
    schema = f"eexngptest_{uuid4().hex}"
    schema_created = False
    try:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL statement_timeout = '10s'"))
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            schema_created = True
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            for model in (
                MarketObservationRecord,
                RawPayloadArchiveRecord,
            ):
                model.__table__.create(bind=connection)
            with Session(bind=connection) as session:
                yield session
    finally:
        try:
            if schema_created:
                with engine.begin() as connection:
                    connection.execute(text("SET LOCAL statement_timeout = '10s'"))
                    connection.execute(text("SET LOCAL lock_timeout = '5s'"))
                    connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        finally:
            engine.dispose()


def _rows(session, model):
    return [dict(row) for row in session.execute(select(model.__table__)).mappings()]


def _archives(session):
    return _rows(session, RawPayloadArchiveRecord)


def _map_rows(capture: EexPublicCapture) -> list[dict]:
    parsed = parse_eex_ttf_ngp_csv(
        capture.raw_bytes.decode("utf-8"),
        retrieved_at_utc=capture.retrieved_at_utc,
    )
    return eex_ttf_ngp_receipt_observations(
        parsed,
        received_at_utc=capture.retrieved_at_utc,
        gas_day_calendar_contract=_calendar(),
    )


def test_first_insert_then_replay_preserves_first_receipt_exact_bom_and_line_endings():
    first = _capture(ROW_FINAL, ROW_TEMPORARY, receipt=FIRST_RECEIPT)
    repeated = _capture(ROW_FINAL, ROW_TEMPORARY, receipt=LATER_RECEIPT)

    with _session() as session:
        outcome = ingestion.persist_eex_ngp_capture(
            session,
            capture=first,
            gas_day_calendar_contract=_calendar(),
            run_id="run-first",
        )
        assert outcome["records"] == 2
        assert outcome["received_records"] == 2
        assert outcome["skipped_records"] == 0
        assert outcome["archived_pages"] == 1
        assert outcome["inserted"] == 2 and outcome["unchanged"] == 0

        snapshot = _rows(session, MarketObservationRecord)
        assert len(snapshot) == 2
        archives = _archives(session)
        assert len(archives) == 1
        stored_archive = archives[0]
        assert stored_archive["payload_text"].encode("utf-8") == first.raw_bytes
        assert stored_archive["payload_sha256"] == hashlib.sha256(first.raw_bytes).hexdigest()
        assert stored_archive["received_at_utc"] == FIRST_RECEIPT
        assert stored_archive["source_system"] == SOURCE_SYSTEM
        assert stored_archive["dataset"] == SOURCE_DATASET
        assert stored_archive["source_reference"] == SOURCE_REFERENCE
        assert first.bom_present is True

        for row in snapshot:
            metadata = row["metadata_json"]
            assert row["observed_at_utc"] == FIRST_RECEIPT
            assert row["source_reference"] == SOURCE_REFERENCE
            assert row["source_system"] == SOURCE_SYSTEM
            assert row["freshness"] == ObservationFreshness.UNKNOWN.value
            assert RECEIPT_ID_PATTERN.fullmatch(row["observation_id"])
            assert metadata["archive_id"] == stored_archive["archive_id"]
            assert metadata["raw_archive_id"] == stored_archive["archive_id"]
            assert metadata["payload_sha256"] == stored_archive["payload_sha256"]
            assert metadata["ingestion_run_id"] == "run-first"
            assert metadata["source_receipt_at_utc"] == FIRST_RECEIPT.isoformat()
            assert metadata["available_at_utc"] == FIRST_RECEIPT.isoformat()
            assert metadata["availability_basis"] == "response_receipt"
            assert metadata["publication_time_utc"] is None
            assert metadata["normalizer_version"] == "eex-ngp-receipt-v1"

        replay = ingestion.persist_eex_ngp_capture(
            session,
            capture=repeated,
            gas_day_calendar_contract=_calendar(),
            run_id="run-second",
        )
        assert replay["inserted"] == 0 and replay["unchanged"] == 2
        assert _rows(session, MarketObservationRecord) == snapshot
        archives = sorted(_archives(session), key=lambda row: row["received_at_utc"])
        assert len(archives) == 2
        assert archives[1]["received_at_utc"] == LATER_RECEIPT
        assert archives[1]["payload_text"].encode("utf-8") == repeated.raw_bytes
        assert archives[1]["payload_sha256"] == hashlib.sha256(repeated.raw_bytes).hexdigest()
        assert archives[1]["payload_sha256"] == stored_archive["payload_sha256"]


def test_changed_provider_clock_creates_a_new_identity_without_overwriting_the_first():
    first = _capture(ROW_FINAL, receipt=FIRST_RECEIPT)
    changed_provider_clock = _capture(
        "29/05/2026;31.400;1200.5;Final NGP;29/05/2026 14:45",
        receipt=LATER_RECEIPT,
    )

    with _session() as session:
        ingestion.persist_eex_ngp_capture(
            session,
            capture=first,
            gas_day_calendar_contract=_calendar(),
            run_id="first-clock",
        )
        snapshot = _rows(session, MarketObservationRecord)
        outcome = ingestion.persist_eex_ngp_capture(
            session,
            capture=changed_provider_clock,
            gas_day_calendar_contract=_calendar(),
            run_id="new-clock",
        )
        assert outcome["inserted"] == 1 and outcome["unchanged"] == 0
        rows = _rows(session, MarketObservationRecord)
        assert len(rows) == 2
        first_row = next(
            row for row in rows if row["observation_id"] == snapshot[0]["observation_id"]
        )
        assert first_row == snapshot[0]
        assert first_row["observed_at_utc"] == FIRST_RECEIPT
        new_row = next(
            row for row in rows if row["observation_id"] != snapshot[0]["observation_id"]
        )
        assert new_row["source_record_id"] == "2026-05-29-20260529T1445-final"
        assert new_row["observed_at_utc"] == LATER_RECEIPT
        assert len(_archives(session)) == 2


def test_same_provider_key_changed_exact_price_refuses_and_retains_new_raw_capture():
    first = _capture(ROW_FINAL, receipt=FIRST_RECEIPT)
    revised = _capture(
        "29/05/2026;31.900;1300.0;Final NGP;29/05/2026 14:30",
        receipt=LATER_RECEIPT,
    )

    with _session() as session:
        ingestion.persist_eex_ngp_capture(
            session,
            capture=first,
            gas_day_calendar_contract=_calendar(),
            run_id="price-first",
        )
        snapshot = _rows(session, MarketObservationRecord)
        with pytest.raises(EexNgpRevisionRequiresHistoryError) as caught:
            ingestion.persist_eex_ngp_capture(
                session,
                capture=revised,
                gas_day_calendar_contract=_calendar(),
                run_id="price-revised",
            )
        assert caught.value.code == "eex_ngp_revision_requires_history"
        assert "price" in caught.value.changed_fields
        assert "metadata_json.index_value_exact" in caught.value.changed_fields
        assert "31.900" not in str(caught.value)
        assert _rows(session, MarketObservationRecord) == snapshot
        archives = sorted(_archives(session), key=lambda row: row["received_at_utc"])
        assert len(archives) == 2
        assert archives[1]["payload_text"].encode("utf-8") == revised.raw_bytes
        assert archives[1]["received_at_utc"] == LATER_RECEIPT


def test_same_identity_status_metadata_revision_refuses_without_overwrite():
    first = _capture(ROW_FINAL, receipt=FIRST_RECEIPT)
    with _session() as session:
        ingestion.persist_eex_ngp_capture(
            session,
            capture=first,
            gas_day_calendar_contract=_calendar(),
            run_id="status-first",
        )
        snapshot = _rows(session, MarketObservationRecord)
        row = _map_rows(first)[0]
        metadata = dict(row["metadata_json"])
        metadata.update(
            {
                "revision_status": "temporary",
                "revision_status_raw": "Temporary NGP",
                "provisional": True,
            }
        )
        changed = {**row, "metadata_json": metadata}
        with pytest.raises(EexNgpRevisionRequiresHistoryError) as caught:
            upsert_eex_ngp_observation_rows(session, [changed])
        assert "metadata_json.revision_status" in caught.value.changed_fields
        assert _rows(session, MarketObservationRecord) == snapshot


def test_mixed_new_and_revised_batch_rolls_back_canonical_writes_but_retains_raw():
    first = _capture(ROW_FINAL, receipt=FIRST_RECEIPT)
    mixed = _capture(
        "29/05/2026;31.900;1300.0;Final NGP;29/05/2026 14:30",
        ROW_TEMPORARY,
        receipt=LATER_RECEIPT,
    )

    with _session() as session:
        ingestion.persist_eex_ngp_capture(
            session,
            capture=first,
            gas_day_calendar_contract=_calendar(),
            run_id="mixed-first",
        )
        snapshot = _rows(session, MarketObservationRecord)
        with pytest.raises(EexNgpRevisionRequiresHistoryError):
            ingestion.persist_eex_ngp_capture(
                session,
                capture=mixed,
                gas_day_calendar_contract=_calendar(),
                run_id="mixed-refused",
            )
        assert _rows(session, MarketObservationRecord) == snapshot
        assert len(snapshot) == 1
        archives = sorted(_archives(session), key=lambda row: row["received_at_utc"])
        assert len(archives) == 2
        assert archives[1]["payload_text"].encode("utf-8") == mixed.raw_bytes


def test_malformed_payload_archives_valid_raw_with_zero_records_and_no_canonical():
    malformed = _capture(ROW_FINAL, header="not;the;official;header")

    with _session() as session:
        with pytest.raises(EexNgpParseError) as caught:
            ingestion.persist_eex_ngp_capture(
                session,
                capture=malformed,
                gas_day_calendar_contract=_calendar(),
                run_id="malformed",
            )
        assert caught.value.code == "unexpected_header"
        assert _rows(session, MarketObservationRecord) == []
        archives = _archives(session)
        assert len(archives) == 1
        assert archives[0]["payload_text"].encode("utf-8") == malformed.raw_bytes
        assert archives[0]["payload_sha256"] == hashlib.sha256(malformed.raw_bytes).hexdigest()
        assert archives[0]["record_count"] == 0
        assert archives[0]["received_at_utc"] == FIRST_RECEIPT


def test_mapping_refusal_retains_raw_but_never_invents_publication_or_canonical():
    rejected_row = _capture(
        "29/05/2026;not-a-number;1200.5;Final NGP;29/05/2026 14:30",
        receipt=FIRST_RECEIPT,
    )

    with _session() as session:
        with pytest.raises(EexNgpParseError) as caught:
            ingestion.persist_eex_ngp_capture(
                session,
                capture=rejected_row,
                gas_day_calendar_contract=_calendar(),
                run_id="rejected-row",
            )
        assert caught.value.code == "rejected_rows_present"
        assert _rows(session, MarketObservationRecord) == []
        archives = _archives(session)
        assert len(archives) == 1
        assert archives[0]["record_count"] == 0
        assert archives[0]["payload_text"].encode("utf-8") == rejected_row.raw_bytes


def test_invalid_utf8_is_refused_before_any_archive_or_canonical_write():
    capture = _capture(ROW_FINAL)
    broken = replace(capture, raw_bytes=capture.raw_bytes + b"\xff")

    with _session() as session:
        with pytest.raises(ingestion.EexNgpInvalidUtf8Error):
            ingestion.persist_eex_ngp_capture(
                session,
                capture=broken,
                gas_day_calendar_contract=_calendar(),
                run_id="invalid-utf8",
            )
        assert _rows(session, MarketObservationRecord) == []
        assert _archives(session) == []


@pytest.mark.parametrize(
    "mutator",
    [
        lambda capture: replace(capture, source_url="https://evil.example/file.csv"),
        lambda capture: replace(capture, final_url="https://evil.example/file.csv"),
        lambda capture: replace(capture, status_code=503),
        lambda capture: replace(capture, retrieved_at_utc=FIRST_RECEIPT.replace(tzinfo=None)),
        lambda capture: replace(capture, content_encoding="gzip"),
    ],
)
def test_capture_validation_refuses_non_official_or_unusable_transport_evidence(mutator):
    with _session() as session:
        with pytest.raises(ingestion.EexNgpCaptureValidationError):
            ingestion.persist_eex_ngp_capture(
                session,
                capture=mutator(_capture(ROW_FINAL)),
                gas_day_calendar_contract=_calendar(),
                run_id="bad-capture",
            )
        assert _rows(session, MarketObservationRecord) == []
        assert _archives(session) == []


def test_archive_lineage_failure_rolls_back_raw_and_never_writes_canonical(monkeypatch):
    real_archive = ingestion.archive_raw_payload

    def unconfirmed_archive(session, **kwargs):
        real_archive(session, **kwargs)
        return None

    monkeypatch.setattr(ingestion, "archive_raw_payload", unconfirmed_archive)
    with _session() as session:
        with pytest.raises(ingestion.EexNgpArchiveLineageError):
            ingestion.persist_eex_ngp_capture(
                session,
                capture=_capture(ROW_FINAL),
                gas_day_calendar_contract=_calendar(),
                run_id="archive-fail",
            )
        assert _rows(session, MarketObservationRecord) == []
        assert _archives(session) == []


def test_archive_sql_failure_is_typed_and_never_writes_canonical(monkeypatch):
    def failing_archive(session, **kwargs):
        raise SQLAlchemyError("synthetic archive failure")

    monkeypatch.setattr(ingestion, "archive_raw_payload", failing_archive)
    with _session() as session:
        with pytest.raises(ingestion.EexNgpArchiveLineageError) as caught:
            ingestion.persist_eex_ngp_capture(
                session,
                capture=_capture(ROW_FINAL),
                gas_day_calendar_contract=_calendar(),
                run_id="archive-sql-fail",
            )
        assert caught.value.code == "eex_ngp_archive_lineage_required"
        assert _rows(session, MarketObservationRecord) == []
        assert _archives(session) == []


def test_pending_provider_timezone_is_accepted_only_by_the_receipt_bound_mapper():
    capture = _capture(ROW_FINAL)
    parsed = parse_eex_ttf_ngp_csv(
        capture.raw_bytes.decode("utf-8"),
        retrieved_at_utc=capture.retrieved_at_utc,
    )
    assert parsed.records[0].normalization_status == "pending_source_timezone"

    with pytest.raises(EexNgpParseError) as strict:
        eex_ttf_ngp_market_observations(
            parsed,
            gas_day_calendar_contract=_calendar(),
        )
    assert strict.value.code == "unproven_publication_timezone"

    with _session() as session:
        outcome = ingestion.persist_eex_ngp_capture(
            session,
            capture=capture,
            gas_day_calendar_contract=_calendar(),
            run_id="pending-receipt",
        )
        assert outcome["inserted"] == 1
        row = _rows(session, MarketObservationRecord)[0]
        assert row["metadata_json"]["publication_time_utc"] is None
        assert row["metadata_json"]["publication_time_basis"] == "unknown"
        assert row["observed_at_utc"] == FIRST_RECEIPT
        assert row["metadata_json"]["available_at_utc"] == FIRST_RECEIPT.isoformat()


def test_exact_source_price_identity_and_forged_value_or_zero_volume_refusals():
    capture = _capture(ROW_FINAL)
    with _session() as session:
        ingestion.persist_eex_ngp_capture(
            session,
            capture=capture,
            gas_day_calendar_contract=_calendar(),
            run_id="exact-price",
        )
        row = _rows(session, MarketObservationRecord)[0]
        assert row["source_reference"] == SOURCE_REFERENCE
        assert row["source_reference"] != OFFICIAL_SOURCE_URL
        assert row["metadata_json"]["source_file_url"] == OFFICIAL_SOURCE_URL
        assert RECEIPT_ID_PATTERN.fullmatch(row["observation_id"])

        expected_id = "eex-ngp-r1-" + hashlib.sha256(
            "\x1f".join((SOURCE_REFERENCE, "2026-05-29-20260529T1430-final")).encode("utf-8")
        ).hexdigest()[:48]
        assert row["observation_id"] == expected_id

        resolution = resolve_source_price(
            source_system=row["source_system"],
            source_reference=row["source_reference"],
            numeric_price=row["price"],
            metadata=row["metadata_json"],
            unit=row["unit"],
            currency=row["currency"],
        )
        assert resolution.status == STATUS_EXACT
        assert resolution.exact_decimal == Decimal("31.400")
        assert resolution.volume_decimal == Decimal("1200.5")
        assert resolution.executable_quote is False

        mapped = _map_rows(capture)[0]
        forged_float = {**mapped, "price": 99.0}
        with pytest.raises(EexNgpInvalidObservationError) as forged:
            upsert_eex_ngp_observation_rows(session, [forged_float])
        assert "issue='exact_numeric_price_mismatch'" in str(forged.value)
        assert _rows(session, MarketObservationRecord) == [row]

        zero_volume_metadata = dict(mapped["metadata_json"])
        zero_volume_metadata["index_volume_mwh_exact"] = "0"
        zero_volume_metadata["index_volume_raw"] = "0"
        zero_volume = {**mapped, "metadata_json": zero_volume_metadata}
        with pytest.raises(EexNgpInvalidObservationError) as zero:
            upsert_eex_ngp_observation_rows(session, [zero_volume])
        assert "exact_volume_not_positive" in str(zero.value)
        assert _rows(session, MarketObservationRecord) == [row]

        mixed = [{**mapped, "observation_id": "eex-ngp-r1-" + "b" * 48}, forged_float]
        with pytest.raises(EexNgpInvalidObservationError):
            upsert_eex_ngp_observation_rows(session, mixed)
        assert _rows(session, MarketObservationRecord) == [row]


def test_zero_volume_provider_row_is_not_mapped_but_other_rows_persist():
    with _session() as session:
        outcome = ingestion.persist_eex_ngp_capture(
            session,
            capture=_capture(
                ROW_FINAL,
                "29/05/2026;0;0;Temporary NGP;29/05/2026 14:45",
            ),
            gas_day_calendar_contract=_calendar(),
            run_id="zero-volume",
        )
        assert outcome["records"] == 1
        assert outcome["received_records"] == 2
        assert outcome["skipped_records"] == 1
        rows = _rows(session, MarketObservationRecord)
        assert len(rows) == 1
        assert rows[0]["source_record_id"] == "2026-05-29-20260529T1430-final"
        assert rows[0]["metadata_json"]["index_volume_mwh_exact"] == "1200.5"
