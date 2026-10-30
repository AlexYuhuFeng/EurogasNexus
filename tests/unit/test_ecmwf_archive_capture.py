"""Focused synthetic tests for RFC-0007 S2 server-owned AWS archive capture.

The byte fixtures are structural GRIB2/index mechanics, not authentic provider
history.  A fake decoder isolates transport from optional native ecCodes; these
tests make no real-archive, receipt or forecast-accuracy claim.
"""

from __future__ import annotations

import hashlib
import inspect
import itertools
import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest

from eurogas_nexus.application.research.weather_archive_capture import (
    WeatherArchiveCaptureEvidence,
    validate_archive_capture,
)
from eurogas_nexus.application.research.weather_archive_evidence import (
    ARCHIVE_AVAILABILITY_BASIS,
    WeatherArchiveAssumptionError,
    WeatherArchiveIdentityError,
    WeatherArchiveMetadataError,
    WeatherArchivePolicyError,
    WeatherArchiveTimeError,
)
from eurogas_nexus.ingestion.ecmwf_archive_capture import (
    EcmwfArchiveChangedError,
    EcmwfArchiveClockError,
    EcmwfArchiveHttpStatusError,
    EcmwfArchiveMetadataError,
    EcmwfArchivePolicyError,
    EcmwfArchiveProtocolError,
    EcmwfArchiveRangeError,
    capture_archive_sources,
)
from eurogas_nexus.ingestion.ecmwf_grib import EcmwfDecodedField, EcmwfDecoderMetadata
from eurogas_nexus.ingestion.ecmwf_open_data import (
    EcmwfArchiveOperation,
    EcmwfInvalidRequestError,
    EcmwfLocation,
    EcmwfOpenDataClient,
    EcmwfOpenDataRequest,
    EcmwfOriginError,
    EcmwfRateLimitedError,
    EcmwfSource,
    EcmwfSourceError,
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
DATE_INDEX_HEAD = datetime(2025, 1, 15, 9, 0, 0, tzinfo=UTC)
DATE_GRIB_HEAD = datetime(2025, 1, 15, 9, 0, 0, tzinfo=UTC)
DATE_INDEX_GET = datetime(2025, 1, 15, 9, 0, 1, tzinfo=UTC)
DATE_GRIB_GET = datetime(2025, 1, 15, 9, 0, 1, tzinfo=UTC)


def _grib_bytes(length: int = 20) -> bytes:
    data = bytearray(length)
    data[0:4] = b"GRIB"
    data[7] = 2
    data[8:16] = length.to_bytes(8, "big")
    data[-4:] = b"7777"
    return bytes(data)


GRIB_BYTES = _grib_bytes()


def _index_bytes(
    *, length: int | None = None, duplicate: bool = False
) -> bytes:
    if length is None:
        length = len(GRIB_BYTES)
    row = json.dumps(
        {
            "date": "20250115",
            "time": "0000",
            "step": "24",
            "param": "2t",
            "levtype": "sfc",
            "levelist": "2",
            "_offset": "0",
            "_length": str(length),
            "units": "K",
            "type": "fc",
            "stream": "oper",
        },
        separators=(",", ":"),
    )
    lines = [row, row] if duplicate else [row]
    return ("\n".join(lines) + "\n").encode("utf-8")


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


def _remove_header(headers: dict[str, str], name: str) -> None:
    for key in [key for key in headers if key.lower() == name.lower()]:
        del headers[key]


def _set_header(headers: dict[str, str], name: str, value: str) -> None:
    _remove_header(headers, name)
    headers[name.lower()] = value


def _head_index(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        headers=_headers(
            length=len(INDEX_BYTES),
            etag=INDEX_ETAG,
            version=INDEX_VERSION,
            last_modified=INDEX_LM,
            date_header=DATE_INDEX_HEAD,
        ),
    )


def _head_grib(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        headers=_headers(
            length=len(GRIB_BYTES),
            etag=GRIB_ETAG,
            version=GRIB_VERSION,
            last_modified=GRIB_LM,
            date_header=DATE_GRIB_HEAD,
        ),
    )


def _get_index(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        headers=_headers(
            length=len(INDEX_BYTES),
            etag=INDEX_ETAG,
            version=INDEX_VERSION,
            last_modified=INDEX_LM,
            date_header=DATE_INDEX_GET,
        ),
        content=INDEX_BYTES,
    )


def _get_range(_request: httpx.Request) -> httpx.Response:
    headers = _headers(
        length=len(GRIB_BYTES),
        etag=GRIB_ETAG,
        version=GRIB_VERSION,
        last_modified=GRIB_LM,
        date_header=DATE_GRIB_GET,
    )
    headers["content-range"] = f"bytes 0-{len(GRIB_BYTES) - 1}/{len(GRIB_BYTES)}"
    return httpx.Response(206, headers=headers, content=GRIB_BYTES)


def _transport(**overrides):
    handlers = {
        "head_index": _head_index,
        "head_grib": _head_grib,
        "get_index": _get_index,
        "get_range": _get_range,
    }
    handlers.update(overrides)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "HEAD":
            name = "head_index" if request.url.path.endswith(".index") else "head_grib"
        else:
            name = "get_index" if request.url.path.endswith(".index") else "get_range"
        return handlers[name](request)

    return handler, requests


def _clock(start: datetime = DATE_INDEX_HEAD):
    ticks = itertools.count()

    def read() -> datetime:
        return start + timedelta(seconds=next(ticks))

    return read


def _capture(handler, *, clock=None):
    return capture_archive_sources(
        REQUEST,
        transport=httpx.MockTransport(handler),
        clock=clock or _clock(),
        sleep=lambda _seconds: None,
    )


def _valid_capture():
    handler, _requests = _transport()
    return _capture(handler)


def _decoded(**overrides) -> EcmwfDecoderMetadata:
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


class _FakeDecoder:
    def __init__(self, metadata=None, reference_transform=None) -> None:
        self.metadata = metadata or _decoded()
        self.reference_transform = reference_transform
        self.calls = 0

    def decode(self, field) -> EcmwfDecodedField:
        self.calls += 1
        reference = (
            field.reference
            if self.reference_transform is None
            else self.reference_transform(field.reference)
        )
        return EcmwfDecodedField(reference=reference, metadata=self.metadata, points=())


def test_valid_capture_uses_fixed_keys_validators_and_receipt_times():
    handler, requests = _transport()
    capture = _capture(handler)

    assert [request.method for request in requests] == ["HEAD", "HEAD", "GET", "GET"]
    assert all(request.url.host == ARCHIVE_HOST for request in requests)
    assert all(request.url.scheme == "https" for request in requests)
    assert all(request.headers["accept-encoding"] == "identity" for request in requests)
    assert "cookie" not in requests[0].headers
    assert "if-match" not in requests[0].headers
    assert "range" not in requests[0].headers
    assert requests[2].headers["if-match"] == INDEX_ETAG
    assert "range" not in requests[2].headers
    assert requests[3].headers["if-match"] == GRIB_ETAG
    assert requests[3].headers["range"] == f"bytes=0-{len(GRIB_BYTES) - 1}"

    assert capture.index.raw_bytes == INDEX_BYTES
    assert capture.grib.raw_bytes == GRIB_BYTES
    assert capture.index.head.bucket == "ecmwf-forecasts"
    assert capture.index.head.key == INDEX_KEY
    assert capture.grib.head.key == GRIB_KEY
    assert capture.index.head.url == INDEX_URL
    assert capture.grib.head.url == GRIB_URL
    assert capture.index.head.etag == INDEX_ETAG
    assert capture.grib.head.etag == GRIB_ETAG
    assert capture.index.head.version_id == INDEX_VERSION
    assert capture.grib.head.version_id == GRIB_VERSION
    assert capture.index.head.last_modified_utc == INDEX_LM
    assert capture.grib.head.last_modified_utc == GRIB_LM
    assert capture.index.head.date_header_utc == DATE_INDEX_HEAD
    assert capture.index.http.date_header_utc == DATE_INDEX_GET
    assert capture.grib.head.date_header_utc == DATE_GRIB_HEAD
    assert capture.grib.http.date_header_utc == DATE_GRIB_GET
    assert capture.index.head.captured_at_utc == DATE_INDEX_HEAD + timedelta(seconds=1)
    assert capture.grib.head.captured_at_utc == DATE_INDEX_HEAD + timedelta(seconds=2)
    assert capture.index.http.captured_at_utc == DATE_INDEX_HEAD + timedelta(seconds=3)
    assert capture.grib.http.captured_at_utc == DATE_INDEX_HEAD + timedelta(seconds=4)
    assert capture.started_at_utc == DATE_INDEX_HEAD
    assert capture.completed_at_utc == DATE_INDEX_HEAD + timedelta(seconds=5)
    assert capture.reference.index_sha256 == hashlib.sha256(INDEX_BYTES).hexdigest()
    assert capture.reference.grib_sha256 == hashlib.sha256(GRIB_BYTES).hexdigest()
    assert capture.reference.request_sha256 == REQUEST.fingerprint()
    assert capture.reference.index_row_offset == 0

    decoder = _FakeDecoder()
    result = validate_archive_capture(
        capture,
        public_read_continuity_assumption=True,
        decoder=decoder,
    )

    assert isinstance(result, WeatherArchiveCaptureEvidence)
    assert decoder.calls == 1
    assert result.availability_basis == ARCHIVE_AVAILABILITY_BASIS
    assert result.evidence.effective_archive_available_at_utc == GRIB_LM
    assert result.evidence.index.last_modified_utc == INDEX_LM
    assert result.evidence.grib.last_modified_utc == GRIB_LM
    assert result.evidence.index.etag == INDEX_ETAG
    assert result.evidence.index.version_id == INDEX_VERSION
    assert result.evidence.grib.version_id == GRIB_VERSION
    assert result.evidence.index.sha256 == hashlib.sha256(INDEX_BYTES).hexdigest()
    assert result.evidence.grib.sha256 == hashlib.sha256(GRIB_BYTES).hexdigest()
    assert result.evidence.decoded == decoder.metadata
    assert result.decoded.reference == capture.reference
    assert result.evidence.availability_is_local_receipt is False
    assert result.evidence.availability_is_prospective is False
    assert result.evidence.etag_is_content_hash is False
    assert result.evidence.public_read_continuity_assumption is True
    assert result.index_head_date_utc == DATE_INDEX_HEAD
    assert result.index_get_date_utc == DATE_INDEX_GET
    assert result.grib_head_date_utc == DATE_GRIB_HEAD
    assert result.grib_get_date_utc == DATE_GRIB_GET


def test_capture_entry_points_do_not_accept_url_source_or_headers():
    for entry_point in (capture_archive_sources, EcmwfOpenDataClient.archive_http):
        parameters = inspect.signature(entry_point).parameters
        assert "url" not in parameters
        assert "headers" not in parameters
        assert "source" not in parameters


def test_provider_cookie_is_never_replayed():
    base, _requests = _transport()
    cookies: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if "cookie" in request.headers:
            cookies.append(request.headers["cookie"])
        response = base(request)
        if request.method == "HEAD" and request.url.path.endswith(".index"):
            response.headers["set-cookie"] = "provider-session=1; Path=/"
        return response

    capture = _capture(handler)
    assert capture.grib.raw_bytes == GRIB_BYTES
    assert cookies == []


def test_wrong_host_redirect_is_refused_without_following():
    def redirect(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://evil.example/steal"})

    handler, requests = _transport(head_index=redirect)
    with pytest.raises(EcmwfOriginError) as excinfo:
        _capture(handler)
    assert excinfo.value.code == "ecmwf_origin_rejected"
    assert len(requests) == 1


def test_compressed_response_is_refused():
    def compressed(request: httpx.Request) -> httpx.Response:
        response = _head_index(request)
        response.headers["content-encoding"] = "gzip"
        return response

    handler, _requests = _transport(head_index=compressed)
    with pytest.raises(EcmwfArchiveProtocolError) as excinfo:
        _capture(handler)
    assert excinfo.value.code == "ecmwf_archive_protocol"


class _BytesStream(httpx.SyncByteStream):
    def __init__(self, data: bytes) -> None:
        self.data = data

    def __iter__(self):
        yield self.data

    def close(self) -> None:
        pass


def test_truncated_index_and_range_bodies_are_refused():
    def truncated_index(request: httpx.Request) -> httpx.Response:
        headers = dict(_get_index(request).headers)
        return httpx.Response(
            200, headers=headers, stream=_BytesStream(INDEX_BYTES[:-1])
        )

    handler, _requests = _transport(get_index=truncated_index)
    with pytest.raises(EcmwfArchiveProtocolError):
        _capture(handler)

    def truncated_range(request: httpx.Request) -> httpx.Response:
        headers = dict(_get_range(request).headers)
        return httpx.Response(
            206, headers=headers, stream=_BytesStream(GRIB_BYTES[:-1])
        )

    handler, _requests = _transport(get_range=truncated_range)
    with pytest.raises(EcmwfArchiveRangeError):
        _capture(handler)


def test_missing_or_malformed_head_metadata_is_refused():
    def without_etag(request: httpx.Request) -> httpx.Response:
        headers = dict(_head_index(request).headers)
        _remove_header(headers, "ETag")
        return httpx.Response(200, headers=headers)

    def bad_length(request: httpx.Request) -> httpx.Response:
        headers = dict(_head_index(request).headers)
        _set_header(headers, "Content-Length", "20x")
        return httpx.Response(200, headers=headers)

    def without_last_modified(request: httpx.Request) -> httpx.Response:
        headers = dict(_head_index(request).headers)
        _remove_header(headers, "Last-Modified")
        return httpx.Response(200, headers=headers)

    for override in (without_etag, bad_length, without_last_modified):
        handler, _requests = _transport(head_index=override)
        with pytest.raises(EcmwfArchiveMetadataError):
            _capture(handler)


def test_missing_or_malformed_get_metadata_is_refused():
    def index_without_etag(request: httpx.Request) -> httpx.Response:
        headers = dict(_get_index(request).headers)
        _remove_header(headers, "ETag")
        return httpx.Response(200, headers=headers, content=INDEX_BYTES)

    handler, _requests = _transport(get_index=index_without_etag)
    with pytest.raises(EcmwfArchiveMetadataError):
        _capture(handler)

    def range_without_content_range(request: httpx.Request) -> httpx.Response:
        headers = dict(_get_range(request).headers)
        _remove_header(headers, "Content-Range")
        return httpx.Response(206, headers=headers, content=GRIB_BYTES)

    handler, _requests = _transport(get_range=range_without_content_range)
    with pytest.raises(EcmwfArchiveRangeError):
        _capture(handler)

    def range_bad_content_range(request: httpx.Request) -> httpx.Response:
        headers = dict(_get_range(request).headers)
        _set_header(
            headers,
            "Content-Range",
            f"bytes 0-{len(GRIB_BYTES)}/{len(GRIB_BYTES)}",
        )
        return httpx.Response(206, headers=headers, content=GRIB_BYTES)

    handler, _requests = _transport(get_range=range_bad_content_range)
    with pytest.raises(EcmwfArchiveRangeError):
        _capture(handler)


def test_head_and_index_require_exact_status():
    def head_206(request: httpx.Request) -> httpx.Response:
        return httpx.Response(206, headers=dict(_head_index(request).headers))

    handler, _requests = _transport(head_index=head_206)
    with pytest.raises(EcmwfArchiveHttpStatusError) as excinfo:
        _capture(handler)
    assert excinfo.value.status_code == 206

    def index_206(request: httpx.Request) -> httpx.Response:
        headers = dict(_get_index(request).headers)
        return httpx.Response(206, headers=headers, content=INDEX_BYTES)

    handler, _requests = _transport(get_index=index_206)
    with pytest.raises(EcmwfArchiveHttpStatusError) as excinfo:
        _capture(handler)
    assert excinfo.value.status_code == 206


def test_http_status_error_does_not_leak_provider_body():
    def forbidden(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, content=b"provider-secret-body")

    handler, _requests = _transport(head_index=forbidden)
    with pytest.raises(EcmwfArchiveHttpStatusError) as excinfo:
        _capture(handler)
    assert "provider-secret-body" not in str(excinfo.value)


def test_412_is_a_changed_refusal_without_retry_or_fallback():
    def refused(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(412)

    handler, requests = _transport(get_index=refused)
    with pytest.raises(EcmwfArchiveChangedError) as excinfo:
        _capture(handler)
    assert excinfo.value.code == "ARCHIVE_OBJECT_CHANGED"
    assert len([request for request in requests if request.method == "GET"]) == 1


def _index_etag_changed(headers: dict[str, str]) -> None:
    _set_header(headers, "ETag", '"other-index-validator"')


def _index_version_changed(headers: dict[str, str]) -> None:
    _set_header(headers, "x-amz-version-id", "index-v2")


def _index_last_modified_changed(headers: dict[str, str]) -> None:
    _set_header(
        headers, "Last-Modified", _rfc1123(INDEX_LM + timedelta(seconds=1))
    )


def _index_length_changed(headers: dict[str, str]) -> None:
    _set_header(headers, "Content-Length", str(len(INDEX_BYTES) + 1))


@pytest.mark.parametrize(
    "mutate",
    [
        _index_etag_changed,
        _index_version_changed,
        _index_last_modified_changed,
        _index_length_changed,
    ],
)
def test_changed_get_validators_are_typed_refusals(mutate):
    def changed_index(request: httpx.Request) -> httpx.Response:
        headers = dict(_get_index(request).headers)
        mutate(headers)
        return httpx.Response(
            200, headers=headers, stream=_BytesStream(INDEX_BYTES)
        )

    handler, requests = _transport(get_index=changed_index)
    with pytest.raises(EcmwfArchiveChangedError):
        _capture(handler)
    assert len([request for request in requests if request.method == "GET"]) == 1


def _range_etag_changed(headers: dict[str, str]) -> None:
    _set_header(headers, "ETag", '"other-grib-validator"')


def _range_version_changed(headers: dict[str, str]) -> None:
    _set_header(headers, "x-amz-version-id", "grib-v2")


def _range_last_modified_changed(headers: dict[str, str]) -> None:
    _set_header(
        headers, "Last-Modified", _rfc1123(GRIB_LM + timedelta(seconds=1))
    )


@pytest.mark.parametrize(
    "mutate",
    [
        _range_etag_changed,
        _range_version_changed,
        _range_last_modified_changed,
    ],
)
def test_changed_grib_validators_are_typed_refusals(mutate):
    def changed_range(request: httpx.Request) -> httpx.Response:
        headers = dict(_get_range(request).headers)
        mutate(headers)
        return httpx.Response(206, headers=headers, content=GRIB_BYTES)

    handler, requests = _transport(get_range=changed_range)
    with pytest.raises(EcmwfArchiveChangedError):
        _capture(handler)
    assert len([request for request in requests if "range" in request.headers]) == 1


def test_range_412_is_a_changed_refusal_without_fallback():
    def refused(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(412)

    handler, requests = _transport(get_range=refused)
    with pytest.raises(EcmwfArchiveChangedError):
        _capture(handler)
    assert len([request for request in requests if "range" in request.headers]) == 1


def test_range_status_200_has_no_full_body_fallback():
    def full_body(request: httpx.Request) -> httpx.Response:
        headers = dict(_get_range(request).headers)
        return httpx.Response(200, headers=headers, content=GRIB_BYTES)

    handler, requests = _transport(get_range=full_body)
    with pytest.raises(EcmwfArchiveRangeError):
        _capture(handler)
    assert len([request for request in requests if "range" in request.headers]) == 1


@pytest.mark.parametrize("status", [429, 503])
def test_transient_rate_limit_is_retried(status):
    calls = 0

    def flaky(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(status, content=b"provider-secret-body")
        return _head_index(request)

    handler, _requests = _transport(head_index=flaky)
    capture = _capture(handler)
    assert calls == 2
    assert capture.index.raw_bytes == INDEX_BYTES


@pytest.mark.parametrize("status", [429, 503])
def test_rate_limit_retries_are_bounded_and_do_not_leak_body(status):
    calls = 0

    def limited(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(status, content=b"provider-secret-body")

    handler, requests = _transport(head_index=limited)
    with pytest.raises(EcmwfRateLimitedError) as excinfo:
        _capture(handler)
    assert calls == 3
    assert len(requests) == 3
    assert all(request.method == "HEAD" for request in requests)
    assert "provider-secret-body" not in str(excinfo.value)


def test_non_00z_and_wrong_request_are_refused_before_network():
    handler, requests = _transport()
    request_06 = EcmwfOpenDataRequest(
        run_date=RUN_DATE,
        cycle_hour=6,
        step_hours=24,
        locations=REQUEST.locations,
    )
    with pytest.raises(EcmwfArchivePolicyError) as excinfo:
        capture_archive_sources(
            request_06,
            transport=httpx.MockTransport(handler),
            sleep=lambda _seconds: None,
        )
    assert excinfo.value.code == "ecmwf_archive_policy_rejected"
    with pytest.raises(EcmwfArchivePolicyError):
        capture_archive_sources(
            "not-a-request",
            transport=httpx.MockTransport(handler),
            sleep=lambda _seconds: None,
        )
    assert requests == []


def test_archive_transport_requires_the_reviewed_aws_origin():
    with EcmwfOpenDataClient(source=EcmwfSource.ECMWF) as client:
        with pytest.raises(EcmwfInvalidRequestError):
            client.archive_http(REQUEST, EcmwfArchiveOperation.HEAD_INDEX)
    with pytest.raises(EcmwfSourceError):
        EcmwfOpenDataClient(source="unknown")


def test_clock_refuses_naive_non_datetime_and_backwards_values():
    handler, requests = _transport()
    with pytest.raises(EcmwfArchiveClockError):
        capture_archive_sources(
            REQUEST,
            transport=httpx.MockTransport(handler),
            clock=lambda: datetime(2025, 1, 15, 9, 0, 0),
            sleep=lambda _seconds: None,
        )
    assert requests == []

    with pytest.raises(EcmwfArchiveClockError):
        capture_archive_sources(
            REQUEST,
            transport=httpx.MockTransport(handler),
            clock=lambda: "not-a-datetime",
            sleep=lambda _seconds: None,
        )
    assert requests == []

    backwards = iter(
        [
            datetime(2025, 1, 15, 9, 0, 10, tzinfo=UTC),
            datetime(2025, 1, 15, 9, 0, 9, tzinfo=UTC),
        ]
    )
    with pytest.raises(EcmwfArchiveClockError):
        capture_archive_sources(
            REQUEST,
            transport=httpx.MockTransport(handler),
            clock=lambda: next(backwards),
            sleep=lambda _seconds: None,
        )
    assert len(requests) == 1


def test_head_body_is_never_read_and_response_is_closed():
    class HeadStream(httpx.SyncByteStream):
        def __init__(self) -> None:
            self.closed = False

        def __iter__(self):
            raise AssertionError("HEAD body was read")

        def close(self) -> None:
            self.closed = True

    stream = HeadStream()

    def head_with_stream(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers=_headers(
                length=len(INDEX_BYTES),
                etag=INDEX_ETAG,
                version=INDEX_VERSION,
                last_modified=INDEX_LM,
                date_header=DATE_INDEX_HEAD,
            ),
            stream=stream,
        )

    handler, _requests = _transport(head_index=head_with_stream)
    capture = _capture(handler)
    assert capture.grib.raw_bytes == GRIB_BYTES
    assert stream.closed is True


def test_safe_date_header_is_optional_and_receipt_clock_is_separate():
    def bad_date(request: httpx.Request) -> httpx.Response:
        headers = dict(_head_index(request).headers)
        _set_header(headers, "Date", "not-a-date")
        return httpx.Response(200, headers=headers)

    handler, _requests = _transport(head_index=bad_date)
    capture = _capture(handler)
    assert capture.index.head.date_header_utc is None
    assert capture.index.head.captured_at_utc == DATE_INDEX_HEAD + timedelta(seconds=1)


def test_explicit_null_version_is_retained():
    def head_without_version(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers=_headers(
                length=len(INDEX_BYTES),
                etag=INDEX_ETAG,
                version=None,
                last_modified=INDEX_LM,
                date_header=DATE_INDEX_HEAD,
            ),
        )

    def get_without_version(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers=_headers(
                length=len(INDEX_BYTES),
                etag=INDEX_ETAG,
                version=None,
                last_modified=INDEX_LM,
                date_header=DATE_INDEX_GET,
            ),
            content=INDEX_BYTES,
        )

    handler, _requests = _transport(
        head_index=head_without_version,
        get_index=get_without_version,
    )
    capture = _capture(handler)
    assert capture.index.head.version_id is None
    assert capture.index.http.version_id is None
    result = validate_archive_capture(
        capture,
        public_read_continuity_assumption=True,
        decoder=_FakeDecoder(),
    )
    assert result.evidence.index.version_id is None
    assert any("Index versionId is null" in item for item in result.evidence.limitations)


def test_application_requires_explicit_assumption_before_decode():
    capture = _valid_capture()
    decoder = _FakeDecoder()
    with pytest.raises(WeatherArchiveAssumptionError):
        validate_archive_capture(
            capture,
            public_read_continuity_assumption=False,
            decoder=decoder,
        )
    assert decoder.calls == 0


def test_application_refuses_untrusted_capture_before_decode():
    capture = _valid_capture()
    with pytest.raises(WeatherArchiveMetadataError):
        validate_archive_capture(
            object(),
            public_read_continuity_assumption=True,
            decoder=_FakeDecoder(),
        )
    with pytest.raises(WeatherArchiveIdentityError):
        validate_archive_capture(
            replace(capture, source=EcmwfSource.ECMWF),
            public_read_continuity_assumption=True,
            decoder=_FakeDecoder(),
        )
    with pytest.raises(WeatherArchiveIdentityError):
        validate_archive_capture(
            replace(capture, origin="other origin"),
            public_read_continuity_assumption=True,
            decoder=_FakeDecoder(),
        )
    with pytest.raises(WeatherArchiveIdentityError):
        validate_archive_capture(
            replace(capture, request_sha256="0" * 64),
            public_read_continuity_assumption=True,
            decoder=_FakeDecoder(),
        )
    with pytest.raises(WeatherArchivePolicyError):
        validate_archive_capture(
            replace(capture, request=replace(capture.request, cycle_hour=6)),
            public_read_continuity_assumption=True,
            decoder=_FakeDecoder(),
        )
    with pytest.raises(WeatherArchiveTimeError):
        validate_archive_capture(
            replace(
                capture,
                completed_at_utc=capture.started_at_utc - timedelta(seconds=1),
            ),
            public_read_continuity_assumption=True,
            decoder=_FakeDecoder(),
        )


def test_application_refuses_decoder_reference_or_metadata_mismatch():
    capture = _valid_capture()
    mismatched = _FakeDecoder(
        reference_transform=lambda reference: replace(
            reference, grib_sha256="0" * 64
        )
    )
    with pytest.raises(WeatherArchiveIdentityError):
        validate_archive_capture(
            capture,
            public_read_continuity_assumption=True,
            decoder=mismatched,
        )

    wrong_parameter = _FakeDecoder(metadata=_decoded(param_id=168))
    with pytest.raises(WeatherArchiveIdentityError):
        validate_archive_capture(
            capture,
            public_read_continuity_assumption=True,
            decoder=wrong_parameter,
        )


def test_duplicate_selected_index_row_is_refused():
    duplicate = _index_bytes(duplicate=True)

    def duplicate_index(_request: httpx.Request) -> httpx.Response:
        headers = _headers(
            length=len(duplicate),
            etag=INDEX_ETAG,
            version=INDEX_VERSION,
            last_modified=INDEX_LM,
            date_header=DATE_INDEX_GET,
        )
        return httpx.Response(200, headers=headers, content=duplicate)

    def duplicate_head(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers=_headers(
                length=len(duplicate),
                etag=INDEX_ETAG,
                version=INDEX_VERSION,
                last_modified=INDEX_LM,
                date_header=DATE_INDEX_HEAD,
            ),
        )

    handler, _requests = _transport(head_index=duplicate_head, get_index=duplicate_index)
    with pytest.raises(EcmwfArchiveMetadataError):
        _capture(handler)


def test_transport_failure_is_a_stable_refusal_without_driver_text():
    from eurogas_nexus.ingestion.ecmwf_archive_capture import EcmwfArchiveTransportError

    def timeout(request):
        raise httpx.ConnectTimeout("private-driver-detail", request=request)

    with pytest.raises(EcmwfArchiveTransportError) as caught:
        _capture(timeout)
    assert caught.value.code == "ecmwf_archive_transport_failed"
    assert "private-driver-detail" not in str(caught.value)


def test_http_receipts_are_recorded_after_complete_streamed_bodies():
    now = [DATE_INDEX_HEAD]

    class DelayedBody(httpx.SyncByteStream):
        def __init__(self, payload):
            self.payload = payload

        def __iter__(self):
            yield self.payload
            now[0] += timedelta(seconds=10)

    def index(request):
        original = _get_index(request)
        return httpx.Response(200, headers=original.headers, stream=DelayedBody(INDEX_BYTES))

    def message(request):
        original = _get_range(request)
        return httpx.Response(206, headers=original.headers, stream=DelayedBody(GRIB_BYTES))

    handler, _requests = _transport(get_index=index, get_range=message)
    capture = _capture(handler, clock=lambda: now[0])
    assert capture.index.http.captured_at_utc == DATE_INDEX_HEAD + timedelta(seconds=10)
    assert capture.grib.http.captured_at_utc == DATE_INDEX_HEAD + timedelta(seconds=20)
    assert capture.completed_at_utc == capture.grib.http.captured_at_utc
