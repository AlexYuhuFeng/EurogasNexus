"""Pure canonical schema for RFC-0007 S1 ECMWF archive availability evidence.

This module owns the reviewed archive policy identity and the deterministic
policy, method and whole-evidence hashes plus the mandatory limitation set.  It
has no application, database or network dependency so that both the S1
reconstruction (``application/research/weather_archive_evidence.py``) and the
S3 repository revalidation (``db/repositories/ecmwf_forecasts.py``) recompute
exactly the same identities from typed facts instead of trusting carried text.

``archive_evidence_hash`` accepts either the S1 evidence payload or the S3
persistence block (``ecmwf-archive-persistence-evidence/v1``); the persistence
block is projected back onto the S1 layout before hashing, so a persisted block
is self-verifying against the hash S1 produced.

本模块是 ECMWF 归档证据哈希与限制说明的唯一纯函数实现（无应用层/数据库/网络
依赖），S1 重建与 S3 仓储复核共用，避免两处各自推导导致口径漂移。
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Final

from eurogas_nexus.ingestion.ecmwf_grib import DECODER_LIBRARY
from eurogas_nexus.ingestion.ecmwf_open_data import (
    GRID_NAME,
    MAX_FIELD_BYTES,
    MAX_INDEX_BYTES,
    MODEL_NAME,
    PARAM_ID,
    PARAM_UNITS,
    PRODUCT_STREAM,
)

ARCHIVE_AVAILABILITY_BASIS: Final = "ARCHIVE_OBJECT_LAST_MODIFIED_RECONSTRUCTION"
ARCHIVE_BUCKET: Final = "ecmwf-forecasts"
ARCHIVE_HOST: Final = "ecmwf-forecasts.s3.eu-central-1.amazonaws.com"
ARCHIVE_ORIGIN_LABEL: Final = "ECMWF-managed AWS Open Data replica"
ARCHIVE_CYCLE_HOUR: Final = 0
ARCHIVE_GRID_TYPE: Final = "regular_ll"
ARCHIVE_GRID_NI: Final = 1440
ARCHIVE_GRID_NJ: Final = 721
ARCHIVE_TIME_PRECISION: Final = "utc_seconds"
MAX_ARCHIVE_OBJECT_BYTES: Final = 256 * 1024 * 1024

S1_EVIDENCE_SCHEMA: Final = "ecmwf-archive-evidence-v1"

_POLICY_PAYLOAD: Final[dict[str, object]] = {
    "schema": "ecmwf-archive-availability-policy-v1",
    "availability_basis": ARCHIVE_AVAILABILITY_BASIS,
    "bucket": ARCHIVE_BUCKET,
    "host": ARCHIVE_HOST,
    "model": MODEL_NAME,
    "grid": GRID_NAME,
    "stream": PRODUCT_STREAM,
    "key_layout": "YYYYMMDD/00z/ifs/0p25/oper/YYYYMMDD000000-{step}h-oper-fc",
    "index_suffix": ".index",
    "grib_suffix": ".grib2",
    "cycle_hours": [ARCHIVE_CYCLE_HOUR],
    "step": {"min_hours": 0, "max_hours": 360, "increment_hours": 3},
    "param_id": PARAM_ID,
    "param_units": PARAM_UNITS,
    "step_type": "instant",
    "grid_type": ARCHIVE_GRID_TYPE,
    "grid_ni": ARCHIVE_GRID_NI,
    "grid_nj": ARCHIVE_GRID_NJ,
    "last_modified_precision": ARCHIVE_TIME_PRECISION,
    "effective_rule": "max(index_last_modified,grib_last_modified)",
    "public_read_continuity_assumption": True,
    "max_index_bytes": MAX_INDEX_BYTES,
    "max_message_bytes": MAX_FIELD_BYTES,
    "max_object_bytes": MAX_ARCHIVE_OBJECT_BYTES,
}
WORK_BOUNDS: Final[dict[str, object]] = {
    "max_index_bytes": MAX_INDEX_BYTES,
    "max_message_bytes": MAX_FIELD_BYTES,
    "max_object_bytes": MAX_ARCHIVE_OBJECT_BYTES,
    "time_precision": ARCHIVE_TIME_PRECISION,
}

_BASE_LIMITATIONS: Final[tuple[str, ...]] = (
    (
        "Availability is reconstructed from current S3 object LastModified; it is not a "
        "local capture receipt."
    ),
    (
        "Public-read continuity is an accepted research assumption, not proof of historical "
        "public readability, rights, or entitlement."
    ),
    (
        "Object LastModified does not prove first publication, continuous availability, or "
        "prospective OOS availability."
    ),
    "ETag is retained as an opaque validator and is not a content hash or MD5.",
    "This evidence is not a genuine forecast vintage and is not forecast-accuracy evidence.",
)

_OBJECT_KEYS: Final[tuple[str, ...]] = (
    "bucket",
    "key",
    "url",
    "etag",
    "version_id",
    "http_etag",
    "http_version_id",
    "size_bytes",
    "last_modified_utc",
    "s3_last_modified_utc",
    "http_last_modified_utc",
    "s3_captured_at_utc",
    "http_captured_at_utc",
    "sha256",
)


def canonical_hash(payload: Mapping[str, object]) -> str:
    """Return the SHA-256 of the canonical (sorted, compact, ASCII) JSON payload.

    Raises:
        TypeError/ValueError: When the payload is not strict JSON (e.g. NaN).
    """

    encoded = json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


_ARCHIVE_POLICY_HASH: Final = canonical_hash(_POLICY_PAYLOAD)


def archive_policy_hash() -> str:
    """Return the exact reviewed S1 archive policy identity."""

    return _ARCHIVE_POLICY_HASH


def archive_method_hash(decoder_version: str) -> str:
    """Return the S1 method identity for one validated decoder version.

    Raises:
        TypeError: When ``decoder_version`` is not text.
    """

    if not isinstance(decoder_version, str):
        raise TypeError("decoder_version must be text")
    return canonical_hash(
        {
            "schema": "ecmwf-archive-evidence-method-v1",
            "policy_hash": _ARCHIVE_POLICY_HASH,
            "index_parser": "eurogas_nexus.ingestion.ecmwf_open_data.parse_grib_index",
            "selection": "single reviewed 2t surface row",
            "range_reader": "exact single Content-Range with no full-body fallback",
            "decoder_library": DECODER_LIBRARY,
            "decoder_version": decoder_version,
            "work_bounds": WORK_BOUNDS,
        }
    )


def archive_limitations(
    index_version_id: str | None,
    grib_version_id: str | None,
) -> tuple[str, ...]:
    """Return the complete mandatory limitation set for one object pair.

    ``None`` and the literal S3 ``"null"`` versionId are both unpinned.
    """

    limitations = list(_BASE_LIMITATIONS)
    if index_version_id in (None, "null"):
        limitations.append(
            "Index versionId is null/unversioned; the index object is not version-pinned."
        )
    if grib_version_id in (None, "null"):
        limitations.append(
            "GRIB versionId is null/unversioned; the GRIB object is not version-pinned."
        )
    return tuple(limitations)


def _object_projection(obj: Mapping[str, object]) -> dict[str, object]:
    return {key: obj[key] for key in _OBJECT_KEYS}


def s1_evidence_payload(evidence: Mapping[str, object]) -> dict[str, object]:
    """Project an S1 payload or an S3 persistence block onto the S1 hash layout.

    Raises:
        KeyError: When a required fact is missing.
    """

    if evidence.get("schema") == S1_EVIDENCE_SCHEMA:
        payload = dict(evidence)
        payload.pop("evidence_hash", None)
        return payload
    decoded = evidence["decoded"]
    if not isinstance(decoded, Mapping):
        raise TypeError("decoded evidence must be an object")
    index = evidence["index"]
    grib = evidence["grib"]
    if not isinstance(index, Mapping) or not isinstance(grib, Mapping):
        raise TypeError("object evidence must be an object")
    return {
        "schema": S1_EVIDENCE_SCHEMA,
        "availability_basis": evidence["availability_basis"],
        "index": _object_projection(index),
        "grib": _object_projection(grib),
        "run_date": evidence["run_date"],
        "cycle_hour": evidence["cycle_hour"],
        "step_hours": evidence["step_hours"],
        "index_row_offset": evidence["index_row_offset"],
        "message_offset": evidence["message_offset"],
        "message_length": evidence["message_length"],
        "content_range": evidence["content_range"],
        "object_total_bytes": evidence["object_total_bytes"],
        "effective_archive_available_at_utc": evidence["effective_archive_available_at_utc"],
        "captured_at_utc": evidence["captured_at_utc"],
        "decoder_library": decoded["decoder_library"],
        "decoder_version": decoded["decoder_version"],
        "param_id": decoded["param_id"],
        "units": decoded["units"],
        "step_type": decoded["step_type"],
        "grid_type": decoded["grid_type"],
        "grid_ni": decoded["grid_ni"],
        "grid_nj": decoded["grid_nj"],
        "decoded_data_date": decoded["data_date"],
        "decoded_data_time_utc": decoded["data_time_utc"],
        "decoded_validity_at_utc": decoded["validity_at_utc"],
        "decoded_forecast_step_hours": decoded["forecast_step_hours"],
        "decoded_request_sha256": decoded["request_sha256"],
        "policy_hash": evidence["policy_hash"],
        "method_hash": evidence["method_hash"],
        "work_bounds": WORK_BOUNDS,
        "public_read_continuity_assumption": True,
        "availability_is_local_receipt": False,
        "availability_is_prospective": False,
        "limitations": list(evidence["limitations"]),
    }


def archive_evidence_hash(evidence: Mapping[str, object]) -> str:
    """Return the whole-evidence identity of an S1 payload or S3 persistence block.

    Raises:
        KeyError/TypeError/ValueError: When the evidence cannot be projected.
    """

    return canonical_hash(s1_evidence_payload(evidence))
