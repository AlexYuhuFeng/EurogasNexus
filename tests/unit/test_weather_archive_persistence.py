"""Focused synthetic tests for RFC-0007 S3 archive append validation.

The transport fixture is structural GRIB/index mechanics and the decoder is a fake
isolation seam.  These tests are not provider history, a real capture, archive
eligibility, rights or forecast-accuracy evidence.
"""

from __future__ import annotations

import hashlib
import itertools
import json
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from eurogas_nexus.application.research.weather_archive_capture import (
    validate_archive_capture,
)
from eurogas_nexus.application.research.weather_archive_evidence import (
    ARCHIVE_AVAILABILITY_BASIS,
    WeatherArchiveAssumptionError,
    WeatherArchiveMetadataError,
)
from eurogas_nexus.application.research.weather_archive_persistence import (
    PERSISTENCE_EVIDENCE_SCHEMA,
    build_archive_persistence_payload,
    persist_weather_archive_capture,
)
from eurogas_nexus.db.repositories.ecmwf_forecasts import (
    EcmwfForecastArchiveValidationError,
    EcmwfForecastPointBinding,
    EcmwfForecastValidationError,
    append_ecmwf_forecast,
)
from eurogas_nexus.ingestion.ecmwf_archive_capture import capture_archive_sources
from eurogas_nexus.ingestion.ecmwf_archive_evidence import (
    archive_evidence_hash,
    archive_limitations,
    archive_method_hash,
    archive_policy_hash,
)
from eurogas_nexus.ingestion.ecmwf_grib import (
    EcmwfDecodedField,
    EcmwfDecoderMetadata,
    EcmwfPoint,
)
from eurogas_nexus.ingestion.ecmwf_open_data import (
    EcmwfLocation,
    EcmwfOpenDataRequest,
)

RUN_DATE = date(2025, 1, 15)
VALID_AT = datetime(2025, 1, 16, 0, 0, tzinfo=UTC)
REQUEST = EcmwfOpenDataRequest(
    run_date=RUN_DATE,
    cycle_hour=0,
    step_hours=24,
    locations=(EcmwfLocation("london", 51.5, -0.1),),
)
INDEX_KEY = REQUEST.s3_prefix + REQUEST.index_filename
GRIB_KEY = REQUEST.s3_prefix + REQUEST.asset_filename
ARCHIVE_HOST = "ecmwf-forecasts.s3.eu-central-1.amazonaws.com"
INDEX_URL = f"https://{ARCHIVE_HOST}/{INDEX_KEY}"
GRIB_URL = f"https://{ARCHIVE_HOST}/{GRIB_KEY}"
INDEX_ETAG = '"opaque-index-validator"'
GRIB_ETAG = '"opaque-grib-validator"'
INDEX_VERSION = "index-v1"
GRIB_VERSION = "grib-v1"
INDEX_LM = datetime(2025, 1, 15, 8, 34, 1, tzinfo=UTC)
GRIB_LM = datetime(2025, 1, 15, 8, 34, 29, tzinfo=UTC)
CLOCK_START = datetime(2025, 1, 15, 9, 0, 0, tzinfo=UTC)


def _grib_bytes(length: int = 20) -> bytes:
    data = bytearray(length)
    data[0:4] = b"GRIB"
    data[7] = 2
    data[8:16] = length.to_bytes(8, "big")
    data[-4:] = b"7777"
    return bytes(data)


GRIB_BYTES = _grib_bytes()


def _index_bytes(grib_length: int = len(GRIB_BYTES)) -> bytes:
    row = json.dumps(
        {
            "date": "20250115",
            "time": "0000",
            "step": "24",
            "param": "2t",
            "levtype": "sfc",
            "levelist": "2",
            "_offset": "0",
            "_length": str(grib_length),
            "units": "K",
            "type": "fc",
            "stream": "oper",
        },
        separators=(",", ":"),
    )
    return (row + "\n").encode("utf-8")


INDEX_BYTES = _index_bytes()


def _rfc1123(value: datetime) -> str:
    return format_datetime(value, usegmt=True)


def _headers(
    *,
    length: int,
    etag: str,
    version: str | None,
    last_modified: datetime,
    date_header: datetime,
) -> dict[str, str]:
    headers = {
        "content-length": str(length),
        "etag": etag,
        "last-modified": _rfc1123(last_modified),
        "date": _rfc1123(date_header),
    }
    if version is not None:
        headers["x-amz-version-id"] = version
    return headers


def _handler(request: httpx.Request) -> httpx.Response:
    is_index = request.url.path.endswith(".index")
    if request.method == "HEAD":
        length = len(INDEX_BYTES) if is_index else len(GRIB_BYTES)
        return httpx.Response(
            200,
            headers=_headers(
                length=length,
                etag=INDEX_ETAG if is_index else GRIB_ETAG,
                version=INDEX_VERSION if is_index else GRIB_VERSION,
                last_modified=INDEX_LM if is_index else GRIB_LM,
                date_header=CLOCK_START,
            ),
        )
    if is_index:
        return httpx.Response(
            200,
            headers=_headers(
                length=len(INDEX_BYTES),
                etag=INDEX_ETAG,
                version=INDEX_VERSION,
                last_modified=INDEX_LM,
                date_header=CLOCK_START + timedelta(seconds=1),
            ),
            content=INDEX_BYTES,
        )
    headers = _headers(
        length=len(GRIB_BYTES),
        etag=GRIB_ETAG,
        version=GRIB_VERSION,
        last_modified=GRIB_LM,
        date_header=CLOCK_START + timedelta(seconds=1),
    )
    headers["content-range"] = f"bytes 0-{len(GRIB_BYTES) - 1}/{len(GRIB_BYTES)}"
    return httpx.Response(206, headers=headers, content=GRIB_BYTES)


def _clock():
    ticks = itertools.count()
    return lambda: CLOCK_START + timedelta(seconds=next(ticks))


class _FakeDecoder:
    def __init__(self, request: EcmwfOpenDataRequest) -> None:
        self.request = request
        self.calls = 0

    def decode(self, field) -> EcmwfDecodedField:
        self.calls += 1
        location = self.request.locations[0]
        metadata = EcmwfDecoderMetadata(
            decoder_library="ecCodes",
            decoder_version="2.50.0",
            param_id=167,
            units="K",
            step_type="instant",
            grid_type="regular_ll",
            grid_ni=1440,
            grid_nj=721,
            data_date=RUN_DATE,
            data_time_utc=self.request.issued_at_utc,
            validity_at_utc=VALID_AT,
            forecast_step_hours=24,
            request_sha256=self.request.fingerprint(),
        )
        point = EcmwfPoint(
            reference=field.reference,
            point_id=location.point_id,
            requested_latitude=location.latitude,
            requested_longitude=location.longitude,
            grid_latitude=location.latitude,
            grid_longitude=location.longitude,
            distance_km=0.0,
            temperature_kelvin=278.15,
            temperature_celsius=5.0,
        )
        return EcmwfDecodedField(
            reference=field.reference,
            metadata=metadata,
            points=(point,),
        )


def _capture():
    return capture_archive_sources(
        REQUEST,
        transport=httpx.MockTransport(_handler),
        clock=_clock(),
        sleep=lambda _seconds: None,
    )


def _validated():
    return validate_archive_capture(
        _capture(),
        public_read_continuity_assumption=True,
        decoder=_FakeDecoder(REQUEST),
    )


def _session() -> Session:
    return Session(create_engine("sqlite+pysqlite:///:memory:", future=True))


def _binding() -> EcmwfForecastPointBinding:
    return EcmwfForecastPointBinding("london", "series", "entity")


def test_payload_is_exact_s1_evidence_without_raw_bytes():
    capture = _capture()
    decoder = _FakeDecoder(REQUEST)
    validated = validate_archive_capture(
        capture,
        public_read_continuity_assumption=True,
        decoder=decoder,
    )
    assert decoder.calls == 1
    payload = build_archive_persistence_payload(
        validated.evidence,
        reference=validated.field.reference,
    )

    assert payload["schema"] == PERSISTENCE_EVIDENCE_SCHEMA
    assert payload["availability_basis"] == ARCHIVE_AVAILABILITY_BASIS
    assert payload["provider_source"] == "aws"
    assert payload["provider_origin"] == "ECMWF-managed AWS Open Data replica"
    assert payload["index"]["bucket"] == "ecmwf-forecasts"
    assert payload["index"]["key"] == INDEX_KEY
    assert payload["grib"]["key"] == GRIB_KEY
    assert payload["index"]["url"] == INDEX_URL
    assert payload["grib"]["url"] == GRIB_URL
    assert payload["index"]["etag"] == INDEX_ETAG
    assert payload["grib"]["version_id"] == GRIB_VERSION
    assert payload["index"]["sha256"] == hashlib.sha256(INDEX_BYTES).hexdigest()
    assert payload["grib"]["sha256"] == hashlib.sha256(GRIB_BYTES).hexdigest()
    assert payload["effective_archive_available_at_utc"] == GRIB_LM.isoformat()
    assert payload["captured_at_utc"] == capture.completed_at_utc.isoformat()
    assert payload["decoded"]["request_sha256"] == REQUEST.fingerprint()
    assert payload["reference"]["request_sha256"] == REQUEST.fingerprint()
    assert payload["public_read_continuity_assumption"] is True
    assert payload["availability_is_local_receipt"] is False
    assert payload["availability_is_prospective"] is False
    assert payload["etag_is_content_hash"] is False
    assert len(payload["policy_hash"]) == 64
    assert len(payload["method_hash"]) == 64
    assert len(payload["evidence_hash"]) == 64
    assert any("not a local capture receipt" in item for item in payload["limitations"])

    encoded = json.dumps(payload, sort_keys=True)
    assert GRIB_BYTES.hex() not in encoded
    assert INDEX_BYTES.hex() not in encoded
    assert "raw_bytes" not in encoded
    assert "grib_bytes" not in encoded
    assert len(encoded) < 20_000


def test_ingestion_schema_recomputes_exact_s1_hashes_and_limitations():
    validated = _validated()
    payload = build_archive_persistence_payload(
        validated.evidence,
        reference=validated.field.reference,
    )

    assert payload["policy_hash"] == archive_policy_hash()
    assert payload["method_hash"] == archive_method_hash(
        validated.decoded.metadata.decoder_version
    )
    assert tuple(payload["limitations"]) == archive_limitations(
        payload["index"]["version_id"],
        payload["grib"]["version_id"],
    )
    assert payload["evidence_hash"] == archive_evidence_hash(payload)


def test_repository_refuses_tampered_transport_binding_before_sql():
    validated = _validated()
    payload = build_archive_persistence_payload(
        validated.evidence,
        reference=validated.field.reference,
    )
    session = _session()

    def bad_index_hash(value: dict) -> None:
        value["index"]["sha256"] = "0" * 64

    def bad_capture_clock(value: dict) -> None:
        value["captured_at_utc"] = "2025-01-15T09:00:06+00:00"

    def bad_decoded_request(value: dict) -> None:
        value["decoded"]["request_sha256"] = "0" * 64

    def bad_effective(value: dict) -> None:
        value["effective_archive_available_at_utc"] = INDEX_LM.isoformat()

    def bad_policy_hash(value: dict) -> None:
        value["policy_hash"] = "0" * 64

    def bad_method_hash(value: dict) -> None:
        value["method_hash"] = "1" * 64

    def bad_evidence_hash(value: dict) -> None:
        value["evidence_hash"] = "2" * 64

    def dropped_mandatory_limitation(value: dict) -> None:
        value["limitations"] = value["limitations"][1:]

    def arbitrary_limitation_text(value: dict) -> None:
        value["limitations"] = ["replay accepted this text instead of S1 limitations"]

    for mutate in (
        bad_index_hash,
        bad_capture_clock,
        bad_decoded_request,
        bad_effective,
        bad_policy_hash,
        bad_method_hash,
        bad_evidence_hash,
        dropped_mandatory_limitation,
        arbitrary_limitation_text,
    ):
        tampered = deepcopy(payload)
        mutate(tampered)
        with pytest.raises(EcmwfForecastArchiveValidationError) as excinfo:
            append_ecmwf_forecast(
                session,
                bindings=(_binding(),),
                transport=validated.field,
                decoded=validated.decoded,
                ingested_at_utc=(
                    validated.field.run.receipt_completed_at_utc + timedelta(minutes=10)
                ),
                archive_evidence=tampered,
            )
        assert excinfo.value.code == "ECMWF_ARCHIVE_EVIDENCE_INVALID"
    assert not session.in_transaction()


def test_application_accepts_only_typed_capture_and_assumption_before_sql():
    session = _session()
    with pytest.raises(WeatherArchiveMetadataError) as excinfo:
        persist_weather_archive_capture(
            session,
            object(),
            bindings=(_binding(),),
            ingested_at_utc=CLOCK_START + timedelta(minutes=10),
            public_read_continuity_assumption=True,
            decoder=_FakeDecoder(REQUEST),
        )
    assert excinfo.value.code == "weather_archive_metadata_invalid"

    with pytest.raises(WeatherArchiveAssumptionError):
        persist_weather_archive_capture(
            session,
            _capture(),
            bindings=(_binding(),),
            ingested_at_utc=CLOCK_START + timedelta(minutes=10),
            public_read_continuity_assumption=False,
            decoder=_FakeDecoder(REQUEST),
        )
    assert not session.in_transaction()


def test_naive_or_pre_receipt_ingested_clock_is_refused_before_sql():
    validated = _validated()
    payload = build_archive_persistence_payload(
        validated.evidence,
        reference=validated.field.reference,
    )
    session = _session()
    receipt = validated.field.run.receipt_completed_at_utc

    with pytest.raises(EcmwfForecastValidationError):
        append_ecmwf_forecast(
            session,
            bindings=(_binding(),),
            transport=validated.field,
            decoded=validated.decoded,
            ingested_at_utc=receipt - timedelta(seconds=1),
            archive_evidence=payload,
        )
    with pytest.raises(EcmwfForecastValidationError):
        append_ecmwf_forecast(
            session,
            bindings=(_binding(),),
            transport=validated.field,
            decoded=validated.decoded,
            ingested_at_utc=datetime(2025, 1, 15, 9, 10),
            archive_evidence=payload,
        )
    assert not session.in_transaction()


def test_unpinned_version_and_opaque_etag_are_retained_not_hashes():
    capture = _capture()
    unpinned = replace(
        capture,
        index=replace(
            capture.index,
            head=replace(capture.index.head, version_id=None),
            http=replace(capture.index.http, version_id=None),
        ),
        grib=replace(
            capture.grib,
            head=replace(capture.grib.head, version_id=None),
            http=replace(capture.grib.http, version_id=None),
        ),
    )
    validated = validate_archive_capture(
        unpinned,
        public_read_continuity_assumption=True,
        decoder=_FakeDecoder(REQUEST),
    )
    payload = build_archive_persistence_payload(
        validated.evidence,
        reference=validated.field.reference,
    )
    assert payload["index"]["etag"] == INDEX_ETAG
    assert payload["grib"]["etag"] == GRIB_ETAG
    assert payload["index"]["version_id"] is None
    assert payload["grib"]["version_id"] is None
    assert payload["etag_is_content_hash"] is False
    assert sum("not version-pinned" in item for item in payload["limitations"]) == 2
    assert tuple(payload["limitations"]) == archive_limitations(None, None)
    assert payload["evidence_hash"] == archive_evidence_hash(payload)
