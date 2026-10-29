"""Focused synthetic tests for RFC-0007 S1 archive evidence reconstruction.

These fixtures are deliberately synthetic mechanics.  They are not provider
history, a local receipt, an archive eligibility grant or forecast-accuracy
evidence.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

import pytest

from eurogas_nexus.application.research.weather_archive_evidence import (
    ARCHIVE_AVAILABILITY_BASIS,
    ARCHIVE_BUCKET,
    ARCHIVE_HOST,
    ARCHIVE_ORIGIN_LABEL,
    MAX_ARCHIVE_OBJECT_BYTES,
    ArchiveGribObject,
    ArchiveHttpObjectMetadata,
    ArchiveIndexObject,
    ArchiveObjectChangedError,
    ArchiveS3ObjectMetadata,
    ArchiveSelectedMessage,
    WeatherArchiveEvidenceError,
    assert_archive_replay,
    reconstruct_archive_evidence,
)
from eurogas_nexus.ingestion.ecmwf_grib import EcmwfDecoderMetadata
from eurogas_nexus.ingestion.ecmwf_open_data import (
    EcmwfFieldReference,
    EcmwfLocation,
    EcmwfOpenDataRequest,
    EcmwfSource,
)

RUN_DATE = date(2025, 1, 15)
VALID_AT = datetime(2025, 1, 16, 0, 0, tzinfo=UTC)
CAPTURED_AT = datetime(2025, 1, 15, 9, 0, 4, tzinfo=UTC)
INDEX_S3_LM = datetime(2025, 1, 15, 8, 34, 1, 900_000, tzinfo=UTC)
INDEX_HTTP_LM = datetime(2025, 1, 15, 8, 34, 1, tzinfo=UTC)
GRIB_LM = datetime(2025, 1, 15, 8, 34, 29, tzinfo=UTC)
REQUEST = EcmwfOpenDataRequest(
    run_date=RUN_DATE,
    cycle_hour=0,
    step_hours=24,
    locations=(EcmwfLocation("london", 51.5, -0.1),),
)
INDEX_KEY = REQUEST.s3_prefix + REQUEST.index_filename
GRIB_KEY = REQUEST.s3_prefix + REQUEST.asset_filename
INDEX_URL = f"https://{ARCHIVE_HOST}/{INDEX_KEY}"
GRIB_URL = f"https://{ARCHIVE_HOST}/{GRIB_KEY}"
GRIB_BYTES = b"GRIB" + b"\x00" * 12 + b"7777"


def _raw_index(*, duplicate: bool = False) -> bytes:
    row = json.dumps(
        {
            "date": "20250115",
            "time": "0000",
            "step": "24",
            "param": "2t",
            "levtype": "sfc",
            "levelist": "2",
            "_offset": "0",
            "_length": str(len(GRIB_BYTES)),
            "units": "K",
            "type": "fc",
            "stream": "oper",
        },
        separators=(",", ":"),
    )
    lines = [row, row] if duplicate else [row]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _decoded(**overrides: object) -> EcmwfDecoderMetadata:
    values: dict[str, object] = {
        "decoder_library": "ecCodes",
        "decoder_version": "2.50.0",
        "param_id": 167,
        "units": "K",
        "step_type": "instant",
        "grid_type": "regular_ll",
        "grid_ni": 1440,
        "grid_nj": 721,
        "data_date": RUN_DATE,
        "data_time_utc": datetime(2025, 1, 15, 0, 0, tzinfo=UTC),
        "validity_at_utc": VALID_AT,
        "forecast_step_hours": 24,
        "request_sha256": REQUEST.fingerprint(),
    }
    values.update(overrides)
    return EcmwfDecoderMetadata(**values)


def _fixture(raw_index: bytes | None = None):
    index_bytes = _raw_index() if raw_index is None else raw_index
    index = ArchiveIndexObject(
        metadata=ArchiveS3ObjectMetadata(
            bucket=ARCHIVE_BUCKET,
            key=INDEX_KEY,
            etag='"opaque-index-validator"',
            version_id="index-v1",
            last_modified_utc=INDEX_S3_LM,
            size_bytes=len(index_bytes),
            captured_at_utc=datetime(2025, 1, 15, 9, 0, 0, tzinfo=UTC),
        ),
        http=ArchiveHttpObjectMetadata(
            url=INDEX_URL,
            status_code=200,
            etag='"opaque-index-validator"',
            version_id="index-v1",
            last_modified_utc=INDEX_HTTP_LM,
            content_range=None,
            content_length=len(index_bytes),
            captured_at_utc=datetime(2025, 1, 15, 9, 0, 1, tzinfo=UTC),
        ),
        raw_bytes=index_bytes,
    )
    grib = ArchiveGribObject(
        metadata=ArchiveS3ObjectMetadata(
            bucket=ARCHIVE_BUCKET,
            key=GRIB_KEY,
            etag='"opaque-grib-validator"',
            version_id="grib-v1",
            last_modified_utc=GRIB_LM,
            size_bytes=len(GRIB_BYTES),
            captured_at_utc=datetime(2025, 1, 15, 9, 0, 2, tzinfo=UTC),
        ),
        http=ArchiveHttpObjectMetadata(
            url=GRIB_URL,
            status_code=206,
            etag='"opaque-grib-validator"',
            version_id="grib-v1",
            last_modified_utc=GRIB_LM,
            content_range=f"bytes 0-{len(GRIB_BYTES) - 1}/{len(GRIB_BYTES)}",
            content_length=len(GRIB_BYTES),
            captured_at_utc=datetime(2025, 1, 15, 9, 0, 3, tzinfo=UTC),
        ),
        raw_bytes=GRIB_BYTES,
    )
    reference = EcmwfFieldReference(
        source=EcmwfSource.AWS,
        origin=ARCHIVE_ORIGIN_LABEL,
        asset_url=GRIB_URL,
        request_sha256=REQUEST.fingerprint(),
        grib_sha256=hashlib.sha256(GRIB_BYTES).hexdigest(),
        index_sha256=hashlib.sha256(index_bytes).hexdigest(),
        index_row_offset=0,
        run_date=RUN_DATE,
        cycle_hour=0,
        step_hours=24,
        valid_at_utc=VALID_AT,
    )
    return REQUEST, index, grib, ArchiveSelectedMessage(reference, _decoded()), CAPTURED_AT


def _evidence(*, fixture=None, **overrides: object):
    request, index, grib, selected, captured = fixture or _fixture()
    values = {
        "request": request,
        "index_object": index,
        "grib_object": grib,
        "selected_message": selected,
        "captured_at_utc": captured,
        "public_read_continuity_assumption": True,
    }
    values.update(overrides)
    return reconstruct_archive_evidence(**values)


def _refusal(code: str, *, fixture=None, **overrides: object) -> WeatherArchiveEvidenceError:
    with pytest.raises(WeatherArchiveEvidenceError) as excinfo:
        _evidence(fixture=fixture, **overrides)
    assert excinfo.value.code == code
    return excinfo.value


def test_valid_reconstruction_is_archive_basis_not_receipt():
    evidence = _evidence()

    assert evidence.availability_basis == ARCHIVE_AVAILABILITY_BASIS
    assert evidence.availability_is_local_receipt is False
    assert evidence.availability_is_prospective is False
    assert evidence.etag_is_content_hash is False
    assert evidence.public_read_continuity_assumption is True
    assert evidence.effective_archive_available_at_utc == GRIB_LM
    assert evidence.index.last_modified_utc == datetime(2025, 1, 15, 8, 34, 1, tzinfo=UTC)
    assert evidence.index.s3_last_modified_utc.microsecond == 900_000
    assert evidence.index.http_last_modified_utc.microsecond == 0
    assert evidence.index.etag == '"opaque-index-validator"'
    assert evidence.index.version_id == "index-v1"
    assert evidence.index.s3_captured_at_utc == datetime(2025, 1, 15, 9, 0, 0, tzinfo=UTC)
    assert evidence.grib.http_captured_at_utc == datetime(2025, 1, 15, 9, 0, 3, tzinfo=UTC)
    assert evidence.index.sha256 == hashlib.sha256(_raw_index()).hexdigest()
    assert evidence.grib.sha256 == hashlib.sha256(GRIB_BYTES).hexdigest()
    assert len(evidence.policy_hash) == 64
    assert len(evidence.method_hash) == 64
    assert len(evidence.evidence_hash) == 64
    assert any("not a local capture receipt" in item for item in evidence.limitations)
    assert any("not proof" in item for item in evidence.limitations)
    assert any("opaque validator" in item for item in evidence.limitations)
    assert any("not a genuine forecast vintage" in item for item in evidence.limitations)


def test_hashes_are_deterministic_and_changed_validators_are_object_changes():
    first = _evidence()
    second = _evidence()
    assert first == second
    assert first.evidence_hash == second.evidence_hash

    request, index, grib, selected, captured = _fixture()
    changed_grib = replace(
        grib,
        metadata=replace(grib.metadata, etag='"opaque-grib-v2"'),
        http=replace(grib.http, etag='"opaque-grib-v2"'),
    )
    changed = _evidence(fixture=(request, index, changed_grib, selected, captured))
    assert changed.evidence_hash != first.evidence_hash
    with pytest.raises(ArchiveObjectChangedError) as excinfo:
        assert_archive_replay(first, changed)
    assert excinfo.value.code == "ARCHIVE_OBJECT_CHANGED"

    later = _evidence(fixture=(request, index, grib, selected, captured + timedelta(seconds=5)))
    assert assert_archive_replay(first, later) is later


def test_effective_is_the_conservative_max_of_both_objects():
    assert _evidence().effective_archive_available_at_utc == GRIB_LM

    request, index, grib, selected, captured = _fixture()
    later = datetime(2025, 1, 15, 8, 34, 40, tzinfo=UTC)
    later_index = replace(
        index,
        metadata=replace(index.metadata, last_modified_utc=later),
        http=replace(index.http, last_modified_utc=later),
    )
    evidence = _evidence(fixture=(request, later_index, grib, selected, captured))
    assert evidence.effective_archive_available_at_utc == later


def test_opaque_etag_and_explicit_null_version_are_retained():
    request, index, grib, selected, captured = _fixture()
    opaque = 'W/"not-an-md5-validator"'
    index = replace(
        index,
        metadata=replace(index.metadata, etag=opaque, version_id=None),
        http=replace(index.http, etag=opaque, version_id=None),
    )
    evidence = _evidence(fixture=(request, index, grib, selected, captured))
    assert evidence.index.etag == opaque
    assert evidence.index.version_id is None
    assert evidence.etag_is_content_hash is False
    assert any("Index versionId is null" in item for item in evidence.limitations)


def test_naive_future_and_disagreeing_times_are_refused():
    request, index, grib, selected, captured = _fixture()
    naive = replace(
        index,
        metadata=replace(
            index.metadata,
            last_modified_utc=datetime(2025, 1, 15, 8, 34, 1),
        ),
    )
    _refusal(
        "weather_archive_time_invalid",
        fixture=(request, naive, grib, selected, captured),
    )

    future = captured + timedelta(seconds=1)
    future_index = replace(
        index,
        metadata=replace(
            index.metadata,
            last_modified_utc=future,
            captured_at_utc=future,
        ),
        http=replace(index.http, last_modified_utc=future, captured_at_utc=future),
    )
    _refusal(
        "weather_archive_time_invalid",
        fixture=(request, future_index, grib, selected, captured),
    )

    disagreeing_index = replace(
        index,
        http=replace(
            index.http,
            last_modified_utc=datetime(2025, 1, 15, 8, 34, 2, tzinfo=UTC),
        ),
    )
    _refusal(
        "weather_archive_metadata_invalid",
        fixture=(request, disagreeing_index, grib, selected, captured),
    )


def test_wrong_bucket_key_and_host_are_refused():
    request, index, grib, selected, captured = _fixture()
    wrong_bucket = replace(index, metadata=replace(index.metadata, bucket="other-bucket"))
    _refusal(
        "weather_archive_identity_mismatch",
        fixture=(request, wrong_bucket, grib, selected, captured),
    )
    wrong_key = replace(index, metadata=replace(index.metadata, key=GRIB_KEY))
    _refusal(
        "weather_archive_identity_mismatch",
        fixture=(request, wrong_key, grib, selected, captured),
    )
    wrong_host = replace(
        index,
        http=replace(index.http, url=f"https://example.invalid/{INDEX_KEY}"),
    )
    _refusal(
        "weather_archive_identity_mismatch",
        fixture=(request, index, grib, selected, captured),
        index_object=wrong_host,
    )
    wrong_grib_url = replace(grib, http=replace(grib.http, url=INDEX_URL))
    _refusal(
        "weather_archive_identity_mismatch",
        fixture=(request, index, wrong_grib_url, selected, captured),
    )


def test_duplicate_selected_index_rows_are_refused():
    _refusal(
        "weather_archive_identity_mismatch",
        fixture=_fixture(raw_index=_raw_index(duplicate=True)),
    )


@pytest.mark.parametrize(
    "raw_index",
    [
        b'{"date":"20250115",}\n',
        b'{"date":"20250115","date":"20250115"}\n',
    ],
)
def test_malformed_or_duplicate_index_json_is_a_typed_refusal(raw_index):
    _refusal(
        "weather_archive_metadata_invalid",
        fixture=_fixture(raw_index=raw_index),
    )


def test_index_and_message_hashes_are_exact():
    request, index, grib, selected, captured = _fixture()
    _refusal(
        "weather_archive_hash_mismatch",
        fixture=(request, index, grib, selected, captured),
        selected_message=replace(
            selected,
            reference=replace(selected.reference, index_sha256="0" * 64),
        ),
    )
    _refusal(
        "weather_archive_hash_mismatch",
        fixture=(request, index, grib, selected, captured),
        selected_message=replace(
            selected,
            reference=replace(selected.reference, grib_sha256="0" * 64),
        ),
    )
    mutated_grib = replace(grib, raw_bytes=b"X" + grib.raw_bytes[1:])
    _refusal(
        "weather_archive_hash_mismatch",
        fixture=(request, index, mutated_grib, selected, captured),
    )


def test_range_status_and_partial_body_are_refused():
    request, index, grib, selected, captured = _fixture()
    bad_end = replace(
        grib,
        http=replace(
            grib.http,
            content_range=f"bytes 0-{len(GRIB_BYTES)}/{len(GRIB_BYTES)}",
        ),
    )
    _refusal(
        "weather_archive_range_invalid",
        fixture=(request, index, bad_end, selected, captured),
    )
    bad_length = replace(
        grib,
        http=replace(grib.http, content_length=len(GRIB_BYTES) + 1),
    )
    _refusal(
        "weather_archive_range_invalid",
        fixture=(request, index, bad_length, selected, captured),
    )
    short_body = replace(grib, raw_bytes=grib.raw_bytes[:-1])
    _refusal(
        "weather_archive_range_invalid",
        fixture=(request, index, short_body, selected, captured),
    )
    full_body_status = replace(grib, http=replace(grib.http, status_code=200))
    _refusal(
        "weather_archive_metadata_invalid",
        fixture=(request, index, full_body_status, selected, captured),
    )
    index_ranged = replace(
        index,
        http=replace(
            index.http,
            content_range=f"bytes 0-{len(_raw_index()) - 1}/{len(_raw_index())}",
        ),
    )
    _refusal(
        "weather_archive_range_invalid",
        fixture=(request, index_ranged, grib, selected, captured),
    )


def test_oversized_object_range_is_refused():
    request, index, grib, selected, captured = _fixture()
    huge = MAX_ARCHIVE_OBJECT_BYTES + 1
    huge_grib = replace(
        grib,
        metadata=replace(grib.metadata, size_bytes=huge),
        http=replace(
            grib.http,
            content_range=f"bytes 0-{len(GRIB_BYTES) - 1}/{huge}",
        ),
    )
    _refusal(
        "weather_archive_range_invalid",
        fixture=(request, index, huge_grib, selected, captured),
    )


def test_malformed_metadata_is_a_typed_refusal():
    request, index, grib, selected, captured = _fixture()
    empty_etag = replace(index, metadata=replace(index.metadata, etag=""))
    _refusal(
        "weather_archive_metadata_invalid",
        fixture=(request, empty_etag, grib, selected, captured),
    )
    bool_size = replace(index, metadata=replace(index.metadata, size_bytes=True))
    _refusal(
        "weather_archive_metadata_invalid",
        fixture=(request, bool_size, grib, selected, captured),
    )
    bad_metadata_type = replace(index, metadata=object())
    _refusal(
        "weather_archive_metadata_invalid",
        fixture=(request, bad_metadata_type, grib, selected, captured),
    )
    mismatched_etag = replace(index, http=replace(index.http, etag='"other"'))
    _refusal(
        "weather_archive_metadata_invalid",
        fixture=(request, mismatched_etag, grib, selected, captured),
    )
    mismatched_version = replace(index, http=replace(index.http, version_id="other"))
    _refusal(
        "weather_archive_metadata_invalid",
        fixture=(request, mismatched_version, grib, selected, captured),
    )


def test_policy_assumption_and_capture_refusals():
    request, index, grib, selected, captured = _fixture()
    _refusal(
        "weather_archive_policy_rejected",
        request=replace(request, cycle_hour=6),
    )
    _refusal(
        "weather_archive_assumption_required",
        public_read_continuity_assumption=False,
    )
    _refusal(
        "weather_archive_time_invalid",
        fixture=(request, index, grib, selected, captured),
        captured_at_utc=datetime(2025, 1, 15, 9, 0, 4),
    )
    _refusal(
        "weather_archive_time_invalid",
        fixture=(request, index, grib, selected, captured),
        captured_at_utc=datetime(2025, 1, 15, 8, 0, 0, tzinfo=UTC),
    )


def test_decoded_identity_and_reference_mismatches_are_refused():
    request, index, grib, selected, captured = _fixture()
    for changed in (
        _decoded(param_id=168),
        _decoded(units="C"),
        _decoded(step_type="avg"),
        _decoded(grid_type="reduced_gg"),
        _decoded(grid_ni=1439),
        _decoded(validity_at_utc=VALID_AT + timedelta(hours=1)),
        _decoded(forecast_step_hours=21),
        _decoded(request_sha256="0" * 64),
        _decoded(decoder_version="2.49.9"),
    ):
        _refusal(
            "weather_archive_identity_mismatch",
            fixture=(request, index, grib, selected, captured),
            selected_message=replace(selected, decoded=changed),
        )

    for changed_reference in (
        replace(selected.reference, source=EcmwfSource.ECMWF),
        replace(selected.reference, origin="other origin"),
        replace(selected.reference, asset_url=INDEX_URL),
        replace(selected.reference, index_row_offset=1),
        replace(selected.reference, step_hours=21),
        replace(selected.reference, request_sha256="0" * 64),
    ):
        _refusal(
            "weather_archive_identity_mismatch",
            fixture=(request, index, grib, selected, captured),
            selected_message=replace(selected, reference=changed_reference),
        )


def test_s3_literal_null_version_is_retained_but_never_claimed_pinned():
    request, index, grib, selected, captured = _fixture()
    index = replace(
        index,
        metadata=replace(index.metadata, version_id="null"),
        http=replace(index.http, version_id="null"),
    )
    grib = replace(
        grib,
        metadata=replace(grib.metadata, version_id="null"),
        http=replace(grib.http, version_id="null"),
    )
    evidence = _evidence(fixture=(request, index, grib, selected, captured))
    assert evidence.index.version_id == evidence.grib.version_id == "null"
    assert sum("not version-pinned" in item for item in evidence.limitations) == 2
