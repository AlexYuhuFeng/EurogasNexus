"""RFC0006 stage B bounded persistence for an EEX TTF NGP public capture.

This module is the one ingestion seam that turns a bounded official capture into
raw lineage plus receipt-bound canonical observations. It deliberately does not
download, schedule, activate a source, certify rights, create an ingestion run,
or commit:

- the caller supplies the already-bounded :class:`EexPublicCapture` and owns the
  transaction and authorization;
- the exact capture bytes (BOM and line endings included) are decoded strictly
  as UTF-8 and archived through the existing ``archive_raw_payload`` helper with
  their own SHA-256 and the explicit aware response receipt;
- the independent archival savepoint completes **before** the canonical mapping,
  so a parse/mapping refusal or a revision refusal still retains valid raw bytes;
- the pure parser is called exactly once with that same receipt, then the
  RFC0006 receipt-bound mapper supplies canonical rows; the unverified provider
  ``Timestamp Let`` clock is never promoted to publication/availability;
- canonical rows are append-or-verified by
  :func:`eurogas_nexus.db.repositories.eex_ngp_persistence.upsert_eex_ngp_observation_rows`,
  which keeps the original ``eex-ttf-ngp-15-mins`` source-reference authority
  (never a URL substitution) and preserves the first receipt on recapture.

No default calendar, receipt clock, source URL or raw hash is accepted. A
malformed capture, an altered/non-official URL, a non-200 response, a naive
receipt, non-UTF-8 bytes or caller-supplied hash trust is refused before any
canonical write.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from eurogas_nexus.db.repositories.eex_ngp_persistence import (
    EexNgpInvalidObservationError,
    EexNgpPersistenceError,
    EexNgpRevisionRaceError,
    EexNgpRevisionRequiresHistoryError,
    upsert_eex_ngp_observation_rows,
)
from eurogas_nexus.db.repositories.raw_archive import archive_raw_payload
from eurogas_nexus.ingestion.eex_ngp import (
    SOURCE_DATASET,
    SOURCE_REFERENCE,
    SOURCE_SYSTEM,
    EexNgpGasDayCalendarContract,
    EexNgpParseError,
    eex_ttf_ngp_receipt_observations,
    parse_eex_ttf_ngp_csv,
)
from eurogas_nexus.ingestion.eex_ngp_capture import MAX_CAPTURE_BYTES
from eurogas_nexus.ingestion.eex_public_download import (
    ALLOWED_CONTENT_TYPES,
    OFFICIAL_SOURCE_URL,
    EexPublicCapture,
)

_RAW_ARCHIVE_ADAPTER_VERSION = "eex-ngp-bounded-ingestor/1"


class EexNgpIngestionError(RuntimeError):
    """Base class for a typed EEX NGP ingestion refusal."""

    code = "eex_ngp_ingestion_error"


class EexNgpCaptureValidationError(EexNgpIngestionError):
    """The supplied capture is not one bounded official EEX response."""

    code = "eex_ngp_invalid_capture"


class EexNgpInvalidUtf8Error(EexNgpIngestionError):
    """The exact capture bytes are not strict UTF-8 and cannot be archived losslessly."""

    code = "eex_ngp_invalid_utf8"


class EexNgpArchiveLineageError(EexNgpIngestionError):
    """The raw archive identity could not be confirmed, so canonical writes are refused."""

    code = "eex_ngp_archive_lineage_required"


class EexNgpInputError(EexNgpIngestionError):
    """The caller supplied an invalid run identity."""

    code = "eex_ngp_invalid_input"


def persist_eex_ngp_capture(
    session: Any,
    *,
    capture: EexPublicCapture,
    gas_day_calendar_contract: EexNgpGasDayCalendarContract,
    run_id: str,
) -> dict[str, Any]:
    """Archive one exact official capture, then append-or-verify its canonical rows.

    Args:
        session: Caller-owned SQLAlchemy session. This helper opens independent
            savepoints and never commits; the caller owns the outer transaction.
        capture: The exact bounded official EEX response. Its bytes, aware receipt
            and 200 status are re-validated here; its hash is computed from those
            bytes, never taken from a caller claim.
        gas_day_calendar_contract: The separately evidenced delivery calendar for
            the ``Gasday`` column. There is no default.
        run_id: Nonempty caller-owned ingestion run identity stamped into row
            metadata. This helper does not create an ingestion run row.

    Returns:
        Counts for the batch: ``records`` (canonical rows), ``received_records``
        (parsed records), ``skipped_records`` (unavailable/unpriced records),
        ``archived_pages`` (1), ``archive_id`` and the existing helper's
        ``inserted``/``unchanged`` counts.

    Raises:
        EexNgpCaptureValidationError: The capture is not an exact bounded
            official-URL/200/aware-receipt capture.
        EexNgpInvalidUtf8Error: The exact bytes cannot be losslessly stored as
            UTF-8 text.
        EexNgpArchiveLineageError: Raw archival failed or its identity/hash did
            not match, so no canonical row is written.
        EexNgpParseError: The pure CSV parser or the receipt-bound mapper refused
            the payload. The raw archive completed first and survives.
        EexNgpRevisionRequiresHistoryError: A same-identity canonical row carries
            different semantic content; canonical writes roll back and raw
            archives remain.
    """

    receipt = _validate_capture(capture)
    run = _validate_run_id(run_id)

    raw_bytes = capture.raw_bytes
    payload_text = _decode_exact_utf8(raw_bytes)
    payload_sha256 = hashlib.sha256(raw_bytes).hexdigest()

    # Parse independently of the write path. A fatal parse still leaves the valid
    # decoded bytes archivable with a truthful zero record count.
    parse_error: Exception | None = None
    parsed: Any = None
    try:
        parsed = parse_eex_ttf_ngp_csv(
            payload_text,
            retrieved_at_utc=receipt,
        )
    except Exception as error:  # preserve the parser's typed refusal after archiving
        parse_error = error

    record_count = 0 if parsed is None else len(parsed.records)
    archive_id = _archive_exact_bytes(
        session,
        raw_bytes=raw_bytes,
        payload_text=payload_text,
        payload_sha256=payload_sha256,
        receipt=receipt,
        record_count=record_count,
    )

    if parse_error is not None:
        raise parse_error
    if parsed is None:  # defensive; parse_error is the only non-result path
        raise EexNgpIngestionError("EEX NGP parser returned no result.")

    rows = eex_ttf_ngp_receipt_observations(
        parsed,
        received_at_utc=receipt,
        gas_day_calendar_contract=gas_day_calendar_contract,
    )
    stamped = _stamp_rows(
        rows,
        archive_id=archive_id,
        payload_sha256=payload_sha256,
        receipt=receipt,
        run_id=run,
    )
    outcome = upsert_eex_ngp_observation_rows(session, stamped)
    return {
        "records": len(stamped),
        "received_records": len(parsed.records),
        "skipped_records": len(parsed.records) - len(stamped),
        "archived_pages": 1,
        "archived": 1,
        "archive_id": archive_id,
        **outcome,
        "duplicates": outcome["unchanged"],
    }


def _validate_capture(capture: EexPublicCapture) -> datetime:
    """Validate the exact bounded official capture and return its UTC receipt."""

    if not isinstance(capture, EexPublicCapture):
        raise EexNgpCaptureValidationError(
            "persist_eex_ngp_capture requires an EexPublicCapture from the bounded transport."
        )
    raw_bytes = capture.raw_bytes
    if type(raw_bytes) is not bytes:
        raise EexNgpCaptureValidationError(
            "EEX NGP capture raw_bytes must be exact bytes, not text or a mutable buffer."
        )
    if not raw_bytes:
        raise EexNgpCaptureValidationError("EEX NGP capture raw_bytes must not be empty.")
    if len(raw_bytes) > MAX_CAPTURE_BYTES:
        raise EexNgpCaptureValidationError(
            f"EEX NGP capture exceeds the {MAX_CAPTURE_BYTES}-byte inspection ceiling."
        )
    if capture.source_url != OFFICIAL_SOURCE_URL:
        raise EexNgpCaptureValidationError(
            "EEX NGP capture source_url is not the fixed official file URL."
        )
    if capture.final_url != OFFICIAL_SOURCE_URL:
        raise EexNgpCaptureValidationError(
            "EEX NGP capture final_url is not the fixed official file URL."
        )
    status = capture.status_code
    if isinstance(status, bool) or not isinstance(status, int) or status != 200:
        raise EexNgpCaptureValidationError(
            "EEX NGP capture status_code must be the actual HTTP 200 response."
        )
    if not isinstance(capture.content_encoding, str) or (
        capture.content_encoding.strip().lower() != "identity"
    ):
        raise EexNgpCaptureValidationError(
            "EEX NGP capture must be the identity-encoded exact response bytes."
        )
    if not isinstance(capture.content_type, str):
        raise EexNgpCaptureValidationError(
            "EEX NGP capture content_type must be a string."
        )
    media_type = capture.content_type.split(";", 1)[0].strip().lower()
    if media_type not in ALLOWED_CONTENT_TYPES:
        raise EexNgpCaptureValidationError(
            "EEX NGP capture content_type is not an accepted exact CSV media type."
        )
    return _require_aware_receipt(capture.retrieved_at_utc)


def _validate_run_id(run_id: object) -> str:
    if not isinstance(run_id, str) or not run_id.strip():
        raise EexNgpInputError("EEX NGP run_id must be a nonempty caller-owned string.")
    return run_id


def _require_aware_receipt(value: object) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise EexNgpCaptureValidationError(
            "EEX NGP capture receipt must be the actual aware response instant."
        )
    try:
        return value.astimezone(UTC)
    except (OverflowError, OSError, ValueError):
        raise EexNgpCaptureValidationError(
            "EEX NGP capture receipt cannot be normalized to UTC."
        ) from None


def _decode_exact_utf8(raw_bytes: bytes) -> str:
    """Decode strict UTF-8 while preserving a BOM as the source's own character."""

    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise EexNgpInvalidUtf8Error(
            "EEX NGP capture bytes are not strict UTF-8; the raw file cannot be archived "
            "losslessly as text and no canonical row is written."
        ) from None
    if text.encode("utf-8") != raw_bytes:
        raise EexNgpInvalidUtf8Error(
            "EEX NGP capture bytes do not round-trip through UTF-8 without alteration."
        )
    return text


def _archive_exact_bytes(
    session: Any,
    *,
    raw_bytes: bytes,
    payload_text: str,
    payload_sha256: str,
    receipt: datetime,
    record_count: int,
) -> str:
    """Archive exact bytes in an independent savepoint, before canonical mapping."""

    archive_id = f"raw-{uuid4().hex[:20]}"
    try:
        with session.begin_nested():
            record = archive_raw_payload(
                session,
                archive_id=archive_id,
                source_system=SOURCE_SYSTEM,
                dataset=SOURCE_DATASET,
                source_reference=SOURCE_REFERENCE,
                payload_text=payload_text,
                payload_sha256=payload_sha256,
                record_count=record_count,
                received_at_utc=receipt,
            )
            stored_receipt = getattr(record, "received_at_utc", None)
            stored_text = getattr(record, "payload_text", None)
            if (
                record is None
                or getattr(record, "archive_id", None) != archive_id
                or getattr(record, "payload_sha256", None) != payload_sha256
                or not isinstance(stored_text, str)
                or stored_text != payload_text
                or stored_text.encode("utf-8") != raw_bytes
                or getattr(record, "record_count", None) != record_count
                or not isinstance(stored_receipt, datetime)
                or stored_receipt.tzinfo is None
                or stored_receipt.astimezone(UTC) != receipt
            ):
                raise EexNgpArchiveLineageError(
                    "EEX NGP exact raw archive identity/bytes/receipt were not confirmed; "
                    "canonical rows were not written."
                )
    except SQLAlchemyError:
        raise EexNgpArchiveLineageError(
            "EEX NGP raw archival failed; canonical rows were not written."
        ) from None
    return archive_id


def _stamp_rows(
    rows: list[dict[str, Any]],
    *,
    archive_id: str,
    payload_sha256: str,
    receipt: datetime,
    run_id: str,
) -> list[dict[str, Any]]:
    """Stamp lineage/receipt metadata without changing the source authority fields."""

    stamped: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise EexNgpIngestionError(
                "EEX NGP receipt mapper returned a non-mapping observation row."
            )
        copy = dict(row)
        metadata = dict(copy.get("metadata_json") or {})
        metadata.update(
            {
                "archive_id": archive_id,
                "raw_archive_id": archive_id,
                "payload_sha256": payload_sha256,
                "ingestion_run_id": run_id,
                "source_receipt_at_utc": receipt.isoformat(),
                "adapter_version": _RAW_ARCHIVE_ADAPTER_VERSION,
            }
        )
        copy["metadata_json"] = metadata
        # The column keeps the original provider/source authority reference. The
        # official URL is evidence in metadata, never a replacement reference.
        copy["source_reference"] = SOURCE_REFERENCE
        stamped.append(copy)
    return stamped


__all__ = [
    "EexNgpArchiveLineageError",
    "EexNgpCaptureValidationError",
    "EexNgpIngestionError",
    "EexNgpInputError",
    "EexNgpInvalidObservationError",
    "EexNgpInvalidUtf8Error",
    "EexNgpParseError",
    "EexNgpPersistenceError",
    "EexNgpRevisionRaceError",
    "EexNgpRevisionRequiresHistoryError",
    "persist_eex_ngp_capture",
]
