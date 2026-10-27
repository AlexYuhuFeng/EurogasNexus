"""Byte-preserving, read-only inspection of an operator-supplied EEX TTF NGP capture.

This module is the local capture-inspection seam for the EEX TTF NGP CSV. It answers one
question only: *what does this exact local file contain, and what may not be concluded from
it?* It never downloads, enables a source, writes a database row, grants an entitlement or
certifies provider rights.

The inspection is deliberately narrower than the canonical ingestion path:

- the exact bytes are hashed before any decoding, so a BOM, line-ending change, trailing space
  or re-encoding is visible as a different ``raw_sha256``/``raw_byte_length``;
- the existing pure parser (``eex_ngp.parse_eex_ttf_ngp_csv``) performs the header, row and
  duplicate-key validation, so inspection cannot drift from the adapter's contracts;
- the parser is always called with an explicit, unproven
  :class:`~eurogas_nexus.domain.ingestion.source_timezone.SourceTimezoneContract` for EEX /
  ``ttf-ngp-15min`` with ``declared_zone=None``. Even if the repository later records a
  provider-zone declaration, this seam cannot start canonicalizing inadvertently;
- the canonical observation mapper is never called. Canonical publication instants, delivery
  periods and executable quotes are therefore absent (``None``) rather than guessed.

The report is JSON-safe (strings, numbers, booleans, nulls, lists and objects only). It records
the source URLs from :mod:`eurogas_nexus.ingestion.eex_ngp`, the operator-supplied retrieval
instant normalized to UTC, row-level raw fields, row-level parser rejections and the separate
source-level blockers. A row-level parse rejection and an unproven source contract are
different facts and are reported separately.

Stable refusal codes raised by :class:`EexNgpCaptureError`:

``invalid_input_type``
    ``raw_bytes`` is not a :class:`bytes` instance.
``empty_payload``
    The byte string is empty (or contains only a BOM/whitespace).
``payload_too_large``
    The byte string exceeds :data:`MAX_CAPTURE_BYTES`.
``invalid_utf8``
    The bytes are not strict UTF-8 (a leading UTF-8 BOM is allowed).
``html_payload``
    The decoded text begins with ``<`` and is therefore an HTML/XML document, not this CSV.
``malformed_csv``
    The existing parser refused the CSV shape/header (``parser_code`` preserves its code).
``duplicate_observation_key``
    The existing parser found the same natural key twice; it is never silently deduplicated.
``naive_retrieval_timestamp``
    ``retrieved_at_utc`` is timezone-naive; the host clock is never substituted.
``invalid_retrieval_timestamp``
    ``retrieved_at_utc`` is not a usable aware :class:`datetime`.
``canonicalization_detected``
    Defensive guard: the parser returned a canonical/published instant despite the explicit
    unproven contract.
``report_too_large`` / ``report_not_json_safe``
    The report cannot be serialized within the byte bound as JSON-safe data.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from eurogas_nexus.domain.ingestion.source_timezone import SourceTimezoneContract
from eurogas_nexus.ingestion.eex_ngp import (
    SOURCE_DATASET,
    SOURCE_FILE_URL,
    SOURCE_PAGE_URL,
    SOURCE_REFERENCE,
    SOURCE_SYSTEM,
    EexNgpNormalization,
    EexNgpParseError,
    EexNgpRecord,
    EexNgpRowRejection,
    parse_eex_ttf_ngp_csv,
)

#: Version of the JSON report shape. Bump only with a reviewed schema change.
REPORT_VERSION = "eex-ngp-capture-report/v1"

#: Both the accepted raw capture and its serialized report are bounded by this many bytes.
MAX_CAPTURE_BYTES = 5 * 1024 * 1024

#: The capture is decoded as strict UTF-8; a leading BOM is accepted as an encoding marker.
ENCODING = "utf-8"

#: Human-readable description of where the bytes came from. It is not provider authentication.
PROVENANCE_BASIS = "operator_supplied_local_file"

#: Explicitly unproven declaration. The parser must keep these rows pending normalization.
CAPTURE_TIMEZONE_CONTRACT = SourceTimezoneContract(
    source_system=SOURCE_SYSTEM,
    datasets=(SOURCE_DATASET,),
    declared_zone=None,
    evidence=(
        "capture inspection: the EEX Timestamp Let publication zone is not assessed here; "
        "canonicalization is prohibited and no publication instant is invented."
    ),
)

_HTML_PREFIX = "<"
_DETAIL_LIMIT = 1000
_MESSAGE_LIMIT = 600


class EexNgpCaptureError(ValueError):
    """A local capture that cannot be inspected under the fail-closed contract.

    ``code`` is stable and machine-readable. ``parser_code`` preserves the underlying EEX CSV
    parser refusal when this wrapper maps it to a broader capture code (currently only
    ``malformed_csv``), so an operator can still see the exact parser rule.
    """

    def __init__(
        self, code: str, message: str, *, parser_code: str | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.parser_code = parser_code


#: Descriptive alias for callers that prefer the longer class name.
EexNgpCaptureInspectionError = EexNgpCaptureError


def inspect_eex_ngp_capture(
    raw_bytes: bytes, *, retrieved_at_utc: datetime
) -> dict[str, Any]:
    """Inspect exact local EEX TTF NGP bytes without canonicalizing or persisting anything.

    Args:
        raw_bytes: The exact file bytes, BOM and line endings included. It must be a nonempty
            :class:`bytes` value of at most :data:`MAX_CAPTURE_BYTES`. It is hashed before any
            decoding, so the digest identifies the supplied bytes rather than a normalized copy.
        retrieved_at_utc: The operator-supplied retrieval instant. It must be an aware
            :class:`datetime` and is normalized to UTC. There is deliberately no default:
            this seam never reads the host clock as if it were the source capture time.

    Returns:
        A JSON-safe report with the raw hash/length/encoding, fixed source URLs, explicit
        provenance, raw row fields, row-level parser rejections and source-level blockers. The
        report always states ``canonicalization_allowed=False`` and ``executable_quote=False``.

    Raises:
        EexNgpCaptureError: For an invalid input/retrieval instant, an undecodable or HTML
            payload, a payload-level CSV refusal (header/duplicate key), a defensive
            canonicalization detection, or an unbounded report. Row-level CSV rejections are
            returned in ``rejections`` rather than raised.
    """

    if not isinstance(raw_bytes, bytes):
        raise EexNgpCaptureError(
            "invalid_input_type",
            (
                "raw_bytes must be an exact bytes object; text, bytearray and memoryview "
                "values would make the hash depend on an implicit re-encoding."
            ),
        )

    raw_length = len(raw_bytes)
    if raw_length == 0:
        raise EexNgpCaptureError("empty_payload", "the EEX NGP capture is empty.")
    if raw_length > MAX_CAPTURE_BYTES:
        raise EexNgpCaptureError(
            "payload_too_large",
            (
                f"the capture is {raw_length} bytes; the inspection limit is "
                f"{MAX_CAPTURE_BYTES} bytes."
            ),
        )

    # Hash the exact supplied bytes before decoding, trimming or normalizing anything.
    raw_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    supplied_retrieved_at = _require_aware_retrieval_instant(retrieved_at_utc)
    retrieved_at = supplied_retrieved_at.astimezone(UTC)

    text, bom_present = _decode_strict_utf8(raw_bytes)
    if not text.strip():
        raise EexNgpCaptureError("empty_payload", "the EEX NGP capture contains no text.")
    if text.lstrip().startswith(_HTML_PREFIX):
        raise EexNgpCaptureError(
            "html_payload",
            (
                "the capture begins with '<' and is an HTML/XML document, not the verified "
                "five-column semicolon-delimited EEX TTF NGP CSV."
            ),
        )

    try:
        parsed = parse_eex_ttf_ngp_csv(
            text,
            retrieved_at_utc=retrieved_at,
            timezone_contract=CAPTURE_TIMEZONE_CONTRACT,
        )
    except EexNgpParseError as error:
        code = (
            "malformed_csv"
            if error.code == "unexpected_header"
            else error.code
        )
        raise EexNgpCaptureError(
            code,
            _bounded_message(error.message),
            parser_code=error.code,
        ) from error
    except csv.Error as error:
        raise EexNgpCaptureError(
            "malformed_csv",
            _bounded_message(f"the CSV reader refused the payload: {error}"),
        ) from error

    _refuse_accidental_canonicalization(parsed.records)
    rows = tuple(_row_report(record) for record in parsed.records)
    rejections = tuple(_rejection_report(rejection) for rejection in parsed.rejections)

    report: dict[str, Any] = {
        "report_version": REPORT_VERSION,
        "inspection_status": (
            "complete_with_rejections" if rejections else "complete"
        ),
        "ok": not rejections,
        "source_system": SOURCE_SYSTEM,
        "source_dataset": SOURCE_DATASET,
        "source_reference": SOURCE_REFERENCE,
        "source_file_url": SOURCE_FILE_URL,
        "source_page_url": SOURCE_PAGE_URL,
        "encoding": ENCODING,
        "bom_present": bom_present,
        "raw_sha256": raw_sha256,
        "raw_byte_length": raw_length,
        "retrieved_at_utc": retrieved_at.isoformat(),
        "retrieved_at_utc_supplied": supplied_retrieved_at.isoformat(),
        "retrieved_at_source": "operator_supplied",
        "provenance": {
            "basis": PROVENANCE_BASIS,
            "bytes_and_hash": "identify_this_exact_operator_supplied_file_only",
            "provider_authenticity": "not_proven_by_bytes_or_hash",
            "note": (
                "Bytes and SHA-256 preserve the inspected file's integrity; they do not prove "
                "that EEX produced, authorised or certified it."
            ),
        },
        # These are constants, not conclusions drawn from the payload. Nothing in this module
        # can enable canonical publication or turn a reference index into an executable quote.
        "canonicalization_allowed": False,
        "canonicalization_reason": "unproven_publication_timezone",
        "executable_quote": False,
        "publication_timezone_proven": False,
        "gas_day_calendar_proven": False,
        "delivery_granularity_proven": False,
        "rights_or_certification_assessed": False,
        "timezone_contract": {
            "source_system": CAPTURE_TIMEZONE_CONTRACT.source_system,
            "dataset": SOURCE_DATASET,
            "declared_zone": None,
            "normalization_status": EexNgpNormalization.PENDING_SOURCE_TIMEZONE.value,
            "evidence": CAPTURE_TIMEZONE_CONTRACT.evidence,
        },
        "blockers": _blockers(),
        "canonical_publication": {
            "allowed": False,
            "reason": "unproven_publication_timezone",
            "publication_time_utc": None,
            "period_start_utc": None,
            "period_end_utc": None,
            "delivery_granularity": "unproven",
            "note": (
                "No canonical publication timestamp or gas-day delivery period is derived; "
                "the 15-minute cadence in the official filename is not granularity proof."
            ),
        },
        "rows": list(rows),
        "row_count": len(rows),
        "rejections": list(rejections),
        "rejected_row_count": len(rejections),
        "blank_lines_skipped": parsed.blank_lines_skipped,
    }

    # Refuse rather than emit a report larger than the capture byte bound.
    serialize_capture_report(report)
    return report


def serialize_capture_report(report: Mapping[str, Any]) -> str:
    """Serialize a report compactly, refusing non-JSON-safe or over-limit output.

    The same :data:`MAX_CAPTURE_BYTES` bound applies to the report so a 5 MiB input cannot turn
    into an unbounded operator-facing output. ASCII escaping keeps the result printable on a
    Windows console regardless of the source file's characters.
    """

    try:
        serialized = json.dumps(
            report,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as error:
        raise EexNgpCaptureError(
            "report_not_json_safe",
            "the capture report could not be serialized as strict JSON-safe data.",
        ) from error

    encoded_length = len(serialized.encode("utf-8"))
    if encoded_length > MAX_CAPTURE_BYTES:
        raise EexNgpCaptureError(
            "report_too_large",
            (
                f"the capture report is {encoded_length} bytes; the inspection limit is "
                f"{MAX_CAPTURE_BYTES} bytes."
            ),
        )
    return serialized


def _require_aware_retrieval_instant(value: datetime) -> datetime:
    """Validate the explicit operator instant; never substitute a host clock."""

    if not isinstance(value, datetime):
        raise EexNgpCaptureError(
            "invalid_retrieval_timestamp",
            "retrieved_at_utc must be an explicit datetime supplied by the operator.",
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise EexNgpCaptureError(
            "naive_retrieval_timestamp",
            (
                "retrieved_at_utc must carry an explicit UTC offset; a naive value would be "
                "read as UTC and the seam never guesses the capture clock."
            ),
        )
    try:
        value.astimezone(UTC)
    except (OverflowError, OSError, ValueError) as error:
        raise EexNgpCaptureError(
            "invalid_retrieval_timestamp",
            "retrieved_at_utc cannot be normalized to UTC.",
        ) from error
    return value


def _decode_strict_utf8(raw_bytes: bytes) -> tuple[str, bool]:
    """Decode strict UTF-8, accepting exactly one leading BOM as an encoding marker."""

    bom_present = raw_bytes.startswith(b"\xef\xbb\xbf")
    try:
        text = raw_bytes.decode(ENCODING)
    except UnicodeDecodeError as error:
        raise EexNgpCaptureError(
            "invalid_utf8",
            (
                "the capture is not strict UTF-8; refusing to decode with replacement "
                "characters, because that would silently change the source bytes' meaning."
            ),
        ) from error
    if text.startswith("\ufeff"):
        text = text[1:]
    return text, bom_present


def _refuse_accidental_canonicalization(records: tuple[EexNgpRecord, ...]) -> None:
    """Guard the explicit unproven contract: no row may carry a canonical instant."""

    for record in records:
        if (
            record.publication_time_utc is not None
            or record.normalization_status is not EexNgpNormalization.PENDING_SOURCE_TIMEZONE
        ):
            raise EexNgpCaptureError(
                "canonicalization_detected",
                (
                    f"row {record.row_number} was returned as canonical even though capture "
                    "inspection supplied an unproven timezone contract; refusing to report an "
                    "invented publication instant."
                ),
            )


def _row_report(record: EexNgpRecord) -> dict[str, Any]:
    """One raw-preserving row view; decimals stay exact strings, never source floats."""

    return {
        "row_number": record.row_number,
        "gas_day_raw": record.gas_day_raw,
        "timestamp_raw": record.timestamp_raw,
        "status": record.status,
        "status_raw": record.status_raw,
        "is_provisional": record.is_provisional,
        "index_value_raw": record.index_value_raw,
        "index_value_exact": (
            str(record.index_value) if record.index_value is not None else None
        ),
        "index_volume_raw": record.index_volume_raw,
        "index_volume_exact": (
            str(record.index_volume) if record.index_volume is not None else None
        ),
        "price_available": record.price_available,
        "unavailable_reason": record.unavailable_reason,
        "normalization_status": record.normalization_status.value,
        # Explicit nulls are the honest representation: no instant or period is derived.
        "publication_time_utc": None,
        "period_start_utc": None,
        "period_end_utc": None,
    }


def _rejection_report(rejection: EexNgpRowRejection) -> dict[str, Any]:
    return {
        "row_number": rejection.row_number,
        "reason": rejection.reason,
        "detail": _bounded_message(rejection.detail, limit=_DETAIL_LIMIT),
    }


def _blockers() -> list[dict[str, Any]]:
    """Source-contract blockers, deliberately separate from row-level parse validity."""

    return [
        {
            "code": "unproven_publication_timezone",
            "category": "publication_timezone",
            "status": "unproven",
            "detail": (
                "No official EEX evidence for the Timestamp Let column's zone is assessed "
                "here; no publication_time_utc is produced."
            ),
            "distinct_from_row_parse_validity": True,
            "blocks_canonical_publication": True,
        },
        {
            "code": "unproven_gas_day_calendar",
            "category": "gas_day_calendar",
            "status": "unproven",
            "detail": (
                "The delivery calendar of the Gasday label is not proven; no period start or "
                "end is derived."
            ),
            "distinct_from_row_parse_validity": True,
            "blocks_canonical_publication": True,
        },
        {
            "code": "unproven_delivery_granularity",
            "category": "delivery_granularity",
            "status": "unproven",
            "detail": (
                "The official filename's 15-minute cadence is not proof that a Gasday row is a "
                "15-minute delivery period; no granularity is asserted."
            ),
            "distinct_from_row_parse_validity": True,
            "blocks_canonical_publication": True,
        },
        {
            "code": "rights_and_certification_not_assessed",
            "category": "rights_certification",
            "status": "not_assessed",
            "detail": (
                "Local inspection makes no entitlement, redistribution-right, certification or "
                "legal assertion and enables no source."
            ),
            "distinct_from_row_parse_validity": True,
            "blocks_canonical_publication": True,
        },
    ]


def _bounded_message(value: object, *, limit: int = _MESSAGE_LIMIT) -> str:
    """A single-line, length-bounded diagnostic; never a traceback or raw payload dump."""

    compact = " ".join(str(value).split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


__all__ = [
    "CAPTURE_TIMEZONE_CONTRACT",
    "ENCODING",
    "EexNgpCaptureError",
    "EexNgpCaptureInspectionError",
    "MAX_CAPTURE_BYTES",
    "PROVENANCE_BASIS",
    "REPORT_VERSION",
    "inspect_eex_ngp_capture",
    "serialize_capture_report",
]
