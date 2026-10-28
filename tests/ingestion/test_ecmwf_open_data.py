"""Unit tests for bounded ECMWF transport mechanics with HTTPX MockTransport.

These are not live-provider evidence.  The GRIB payload here is a small transport
fixture; root's isolated ecCodes probe is the separate authentic-byte check.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime

import httpx
import pytest

from eurogas_nexus.ingestion.ecmwf_open_data import (
    ALLOWED_HOSTS,
    MAX_FIELD_BYTES,
    MAX_INDEX_BYTES,
    MAX_LISTING_BYTES,
    MAX_RETRY_AFTER_SECONDS,
    EcmwfAssetNotFoundError,
    EcmwfHttpStatusError,
    EcmwfIndexAmbiguousError,
    EcmwfIndexError,
    EcmwfIndexMismatchError,
    EcmwfInvalidRequestError,
    EcmwfLocation,
    EcmwfOpenDataClient,
    EcmwfOpenDataRequest,
    EcmwfOriginError,
    EcmwfParamIdBasis,
    EcmwfRangeError,
    EcmwfResponseTooLargeError,
    EcmwfSourceError,
    _build_index_row,
    parse_grib_index,
    resolve_origin,
)

RUN_DATE = date(2023, 1, 18)
RECEIPT = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)
BASE = f"https://data.ecmwf.int/forecasts/{RUN_DATE:%Y%m%d}/"

# Literal rows copied from root's captured official 2026-10-27 00z 24 h index.
# They intentionally have no paramId/shortName/name/units.
ACTUAL_RUN_DATE = date(2026, 10, 27)
ACTUAL_2T_ROW = (
    '{"domain": "g", "date": "20261027", "time": "0000", "expver": "0001", '
    '"class": "od", "type": "fc", "stream": "oper", "levtype": "sfc", '
    '"step": "24", "param": "2t", "_offset": 23736393, "_length": 316916}'
)
ACTUAL_100U_ROW = (
    '{"domain": "g", "date": "20261027", "time": "0000", "expver": "0001", '
    '"class": "od", "type": "fc", "stream": "oper", "step": "24", '
    '"levtype": "sfc", "param": "100u", "_offset": 23092835, "_length": 643558}'
)
ACTUAL_CP_ROW = (
    '{"domain": "g", "date": "20261027", "time": "0000", "expver": "0001", '
    '"class": "od", "type": "fc", "stream": "oper", "step": "24", '
    '"levtype": "sfc", "param": "cp", "_offset": 24053309, "_length": 368921}'
)


def make_grib(size: int = 96) -> bytes:
    data = bytearray(size)
    data[0:4] = b"GRIB"
    data[7] = 2
    data[8:16] = size.to_bytes(8, "big")
    data[-4:] = b"7777"
    return bytes(data)


def make_request(*, step: int = 0, cycle: int = 0) -> EcmwfOpenDataRequest:
    return EcmwfOpenDataRequest(
        run_date=RUN_DATE,
        cycle_hour=cycle,
        step_hours=step,
        locations=(
            EcmwfLocation(point_id="london", latitude=51.5, longitude=-0.1),
            EcmwfLocation(point_id="berlin", latitude=52.52, longitude=13.405),
        ),
    )


def index_line(grib: bytes, *, step: int = 0, **overrides: object) -> str:
    row: dict[str, object] = {
        "domain": "g",
        "date": f"{RUN_DATE:%Y%m%d}",
        "time": "0000",
        "expver": "0001",
        "class": "od",
        "type": "fc",
        "stream": "oper",
        "step": str(step),
        "levtype": "sfc",
        "param": "2t",
        "paramId": 167,
        "shortName": "2t",
        "name": "2 metre temperature",
        "units": "K",
        "_offset": 0,
        "_length": len(grib),
    }
    row.update(overrides)
    return json.dumps(row, separators=(",", ":"))


def index_body(grib: bytes, *, step: int = 0, **overrides: object) -> bytes:
    return (index_line(grib, step=step, **overrides) + "\n").encode("utf-8")


def range_response(request: httpx.Request, grib: bytes) -> httpx.Response:
    headers = {
        "Content-Length": str(len(grib)),
        "Content-Range": f"bytes 0-{len(grib) - 1}/{len(grib)}",
        "Last-Modified": "Wed, 18 Jan 2023 01:00:00 GMT",
    }
    assert request.headers["range"] == f"bytes=0-{len(grib) - 1}"
    return httpx.Response(206, content=grib, headers=headers)


class OfficialProvider:
    def __init__(self, *, grib: bytes | None = None, index: bytes | None = None) -> None:
        self.grib = grib or make_grib()
        self.index = index if index is not None else index_body(self.grib)
        self.seen: list[httpx.Request] = []
        self.file_requests: list[httpx.Request] = []
        self.file_responder = None
        self.index_responder = None
        self.page_override: dict[str, bytes] = {}
        self.pages = self._pages()

    def _pages(self) -> dict[str, str]:
        cycle = f"{BASE}00z/"
        model = f"{cycle}ifs/"
        grid = f"{model}0p25/"
        product = f"{grid}oper/"
        filename = f"{RUN_DATE:%Y%m%d}000000-0h-oper-fc.grib2"
        index_filename = f"{RUN_DATE:%Y%m%d}000000-0h-oper-fc.index"
        return {
            "/forecasts/": (
                f'<a href="/forecasts/{RUN_DATE:%Y%m%d}/">run</a>'
                '<a href="https://untrusted.example/forecasts/">mirror</a>'
            ),
            f"/forecasts/{RUN_DATE:%Y%m%d}/": f'<a href="{cycle.removeprefix(BASE)}">00z</a>',
            f"/forecasts/{RUN_DATE:%Y%m%d}/00z/": f'<a href="{model.removeprefix(cycle)}">ifs</a>',
            f"/forecasts/{RUN_DATE:%Y%m%d}/00z/ifs/": (
                f'<a href="{grid.removeprefix(model)}">0p25</a>'
            ),
            f"/forecasts/{RUN_DATE:%Y%m%d}/00z/ifs/0p25/": (
                f'<a href="{product.removeprefix(grid)}">oper</a>'
            ),
            f"/forecasts/{RUN_DATE:%Y%m%d}/00z/ifs/0p25/oper/": (
                f'<a href="{filename}">{filename}</a>'
                f'<a href="{index_filename}">{index_filename}</a>'
            ),
        }

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        path = request.url.path
        if path in self.page_override:
            return httpx.Response(200, content=self.page_override[path])
        if path.endswith(".index"):
            if self.index_responder is not None:
                return self.index_responder(request)
            return httpx.Response(200, content=self.index)
        if path.endswith(".grib2"):
            self.file_requests.append(request)
            if self.file_responder is not None:
                return self.file_responder(request)
            return range_response(request, self.grib)
        page = self.pages.get(path)
        if page is None:
            return httpx.Response(404, content=b"not found")
        return httpx.Response(200, text=page, headers={"Content-Type": "text/html"})


def fixed_clock() -> datetime:
    return RECEIPT


def make_actual_request() -> EcmwfOpenDataRequest:
    return EcmwfOpenDataRequest(
        run_date=ACTUAL_RUN_DATE,
        cycle_hour=0,
        step_hours=24,
        locations=(EcmwfLocation(point_id="london", latitude=51.5, longitude=-0.1),),
    )


def test_filename_contract_uses_provider_suffix_replacement() -> None:
    request = make_request(step=24)
    assert request.asset_filename == "20230118000000-24h-oper-fc.grib2"
    assert request.index_filename == "20230118000000-24h-oper-fc.index"


def test_actual_official_2t_row_without_param_id_is_derived_from_reviewed_short_name() -> None:
    raw = (ACTUAL_100U_ROW + "\n" + ACTUAL_2T_ROW + "\n" + ACTUAL_CP_ROW + "\n").encode()
    index = parse_grib_index(raw, make_actual_request())

    selected = index.selected
    assert index.row_count == 3
    assert selected.row_json == ACTUAL_2T_ROW
    assert selected.param_id == 167
    assert selected.param_id_basis is EcmwfParamIdBasis.REVIEWED_SHORT_NAME
    assert selected.short_name == "2t"
    assert selected.units is None
    assert selected.name is None
    assert selected.level_type == "sfc"
    assert selected.level is None
    assert selected.data_type == "fc"
    assert selected.stream == "oper"
    assert selected.run_date == ACTUAL_RUN_DATE
    assert selected.cycle_hour == 0
    assert selected.step_hours == 24
    assert selected.byte_offset == 23736393
    assert selected.byte_length == 316916
    assert index.raw_sha256 == hashlib.sha256(raw).hexdigest()


def test_non_2t_rows_without_param_id_are_never_assigned_167() -> None:
    raw = (ACTUAL_100U_ROW + "\n" + ACTUAL_CP_ROW + "\n").encode()
    with pytest.raises(EcmwfAssetNotFoundError):
        parse_grib_index(raw, make_actual_request())

    for literal in (ACTUAL_100U_ROW, ACTUAL_CP_ROW):
        row = _build_index_row(
            json.loads(literal),
            row_offset=0,
            row_json=literal,
            row_sha256=hashlib.sha256(literal.encode()).hexdigest(),
        )
        assert row.param_id is None
        assert row.param_id_basis is None


def test_declared_param_id_is_distinguished_from_reviewed_derivation() -> None:
    row = ACTUAL_2T_ROW.replace('"param": "2t"', '"param": "2t", "paramId": 167')
    index = parse_grib_index((row + "\n").encode(), make_actual_request())

    assert index.selected.param_id == 167
    assert index.selected.param_id_basis is EcmwfParamIdBasis.INDEX_DECLARED


@pytest.mark.parametrize(
    "row",
    [
        ACTUAL_2T_ROW.replace('"param": "2t"', '"param": "2t", "paramId": 168'),
        ACTUAL_2T_ROW.replace('"param": "2t"', '"param": "z", "paramId": 167'),
        ACTUAL_2T_ROW.replace('"param": "2t"', '"param": "2t", "shortName": "2d"'),
    ],
)
def test_conflicting_param_declarations_are_refused(row: str) -> None:
    with pytest.raises(EcmwfIndexError):
        parse_grib_index((row + "\n").encode(), make_actual_request())


def test_duplicate_index_key_is_refused() -> None:
    row = ACTUAL_2T_ROW.replace('"param": "2t"', '"param": "2t", "param": "2t"')
    with pytest.raises(EcmwfIndexError):
        parse_grib_index((row + "\n").encode(), make_actual_request())


def test_official_transport_selects_exact_message_and_preserves_receipt() -> None:
    provider = OfficialProvider()
    transport = httpx.MockTransport(provider)
    with EcmwfOpenDataClient(
        source="ecmwf", transport=transport, clock=fixed_clock
    ) as client:
        field = client.retrieve(make_request())

    assert field.grib_bytes == provider.grib
    assert field.grib_sha256 == hashlib.sha256(provider.grib).hexdigest()
    assert field.reference.grib_sha256 == field.grib_sha256
    assert field.byte_offset == 0
    assert field.byte_length == len(provider.grib)
    assert field.content_range == f"bytes 0-{len(provider.grib) - 1}/{len(provider.grib)}"
    assert field.run.source.value == "ecmwf"
    assert field.run.origin == "ECMWF official open data"
    assert field.run.issued_at_utc == datetime(2023, 1, 18, tzinfo=UTC)
    assert field.run.valid_at_utc == datetime(2023, 1, 18, tzinfo=UTC)
    assert field.run.request_started_at_utc == RECEIPT
    assert field.run.receipt_completed_at_utc == RECEIPT
    assert field.run.provider_last_modified_utc == datetime(2023, 1, 18, 1, tzinfo=UTC)
    assert field.run.availability_basis.value == "provider_last_modified"
    assert field.run.request_sha256 == field.reference.request_sha256
    assert len(field.run.listing_pages) == 6
    assert field.index.raw_sha256 == hashlib.sha256(provider.index).hexdigest()
    assert field.index.selected.row_offset == 0

    assert provider.file_requests[0].headers["range"] == (
        f"bytes=0-{len(provider.grib) - 1}"
    )
    assert provider.file_requests[0].method == "GET"
    for request in provider.seen:
        assert request.url.host in ALLOWED_HOSTS
        assert "authorization" not in request.headers
        assert "cookie" not in request.headers


def test_aws_listing_uses_fixed_bucket_prefix_and_records_origin() -> None:
    grib = make_grib()
    prefix = f"{RUN_DATE:%Y%m%d}/00z/ifs/0p25/oper/"
    filename = f"{RUN_DATE:%Y%m%d}000000-0h-oper-fc.grib2"
    index_filename = f"{RUN_DATE:%Y%m%d}000000-0h-oper-fc.index"
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">
  <Name>ecmwf-forecasts</Name>
  <Prefix>{prefix}</Prefix>
  <IsTruncated>false</IsTruncated>
  <Contents><Key>{prefix}{filename}</Key></Contents>
  <Contents><Key>{prefix}{index_filename}</Key></Contents>
</ListBucketResult>""".encode()
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith(".index"):
            return httpx.Response(200, content=index_body(grib))
        if request.url.path.endswith(".grib2"):
            return range_response(request, grib)
        return httpx.Response(200, content=xml, headers={"Content-Type": "application/xml"})

    with EcmwfOpenDataClient(
        source="aws", transport=httpx.MockTransport(handler), clock=fixed_clock
    ) as client:
        field = client.retrieve(make_request())

    listing = seen[0]
    assert listing.url.host == "ecmwf-forecasts.s3.eu-central-1.amazonaws.com"
    assert listing.url.params["list-type"] == "2"
    assert listing.url.params["prefix"] == prefix
    assert listing.url.params["max-keys"] == "1000"
    assert field.run.source.value == "aws"
    assert field.run.origin == "ECMWF-managed AWS Open Data replica"
    assert field.reference.asset_url.endswith(f"/{prefix}{filename}")
    assert field.grib_sha256 == hashlib.sha256(grib).hexdigest()


def test_untrusted_redirect_is_rejected_without_following() -> None:
    provider = OfficialProvider()

    def redirect(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"Location": "https://untrusted.example/forecasts/field.grib2"},
        )

    provider.file_responder = redirect
    with EcmwfOpenDataClient(
        source="ecmwf", transport=httpx.MockTransport(provider), clock=fixed_clock
    ) as client:
        with pytest.raises(EcmwfOriginError) as exc:
            client.retrieve(make_request())
    assert "untrusted" not in str(exc.value)
    assert len(provider.file_requests) == 1


def test_503_retry_after_is_bounded_and_retried() -> None:
    provider = OfficialProvider()
    sleeps: list[float] = []
    calls = {"count": 0}

    def retrying(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(503, headers={"Retry-After": "999"}, content=b"busy")
        return httpx.Response(200, content=provider.index)

    provider.index_responder = retrying
    with EcmwfOpenDataClient(
        source="ecmwf",
        transport=httpx.MockTransport(provider),
        clock=fixed_clock,
        sleep=sleeps.append,
    ) as client:
        field = client.retrieve(make_request())

    assert field.grib_sha256
    assert calls["count"] == 2
    assert sleeps == [MAX_RETRY_AFTER_SECONDS]


def test_error_body_is_not_leaked() -> None:
    provider = OfficialProvider()
    provider.index_responder = lambda request: httpx.Response(
        500, content=b"TOP-SECRET-PROVIDER-BODY"
    )
    with EcmwfOpenDataClient(
        source="ecmwf", transport=httpx.MockTransport(provider), clock=fixed_clock
    ) as client:
        with pytest.raises(EcmwfHttpStatusError) as exc:
            client.retrieve(make_request())
    assert exc.value.status_code == 500
    assert "TOP-SECRET" not in str(exc.value)
    assert provider.file_requests == []


def test_ambiguous_index_refuses_before_range_request() -> None:
    grib = make_grib()
    provider = OfficialProvider(
        grib=grib,
        index=(index_line(grib) + "\n" + index_line(grib) + "\n").encode(),
    )
    with EcmwfOpenDataClient(
        source="ecmwf", transport=httpx.MockTransport(provider), clock=fixed_clock
    ) as client:
        with pytest.raises(EcmwfIndexAmbiguousError):
            client.retrieve(make_request())
    assert provider.file_requests == []


@pytest.mark.parametrize(
    "index",
    [
        b'{"paramId":167',
        b'{"paramId":167,"_offset":0,"_length":10,"levtype":"sfc"}\nnot-json\n',
    ],
)
def test_malformed_index_is_rejected(index: bytes) -> None:
    provider = OfficialProvider(index=index)
    with EcmwfOpenDataClient(
        source="ecmwf", transport=httpx.MockTransport(provider), clock=fixed_clock
    ) as client:
        with pytest.raises(EcmwfIndexError):
            client.retrieve(make_request())
    assert provider.file_requests == []


def test_index_metadata_mismatch_is_not_silently_selected() -> None:
    grib = make_grib()
    provider = OfficialProvider(grib=grib, index=index_body(grib, step="3"))
    with EcmwfOpenDataClient(
        source="ecmwf", transport=httpx.MockTransport(provider), clock=fixed_clock
    ) as client:
        with pytest.raises(EcmwfIndexMismatchError):
            client.retrieve(make_request())
    assert provider.file_requests == []


@pytest.mark.parametrize(
    ("body_size", "headers"),
    [
        (
            96,
            {
                "Content-Length": "96",
                "Content-Range": "bytes 1-96/96",
                "Last-Modified": "Wed, 18 Jan 2023 01:00:00 GMT",
            },
        ),
        (
            95,
            {
                "Content-Length": "95",
                "Content-Range": "bytes 0-95/96",
                "Last-Modified": "Wed, 18 Jan 2023 01:00:00 GMT",
            },
        ),
        (
            96,
            {
                "Content-Length": "96",
                "Content-Range": "bytes 0-95/95",
                "Last-Modified": "Wed, 18 Jan 2023 01:00:00 GMT",
            },
        ),
    ],
)
def test_wrong_range_headers_are_rejected(
    body_size: int, headers: dict[str, str]
) -> None:
    provider = OfficialProvider()
    body = provider.grib[:body_size]
    provider.file_responder = lambda request: httpx.Response(
        206, content=body, headers=headers
    )
    with EcmwfOpenDataClient(
        source="ecmwf", transport=httpx.MockTransport(provider), clock=fixed_clock
    ) as client:
        with pytest.raises(EcmwfRangeError):
            client.retrieve(make_request())


def test_full_body_200_is_never_used_as_a_range_fallback() -> None:
    provider = OfficialProvider()
    provider.file_responder = lambda request: httpx.Response(200, content=provider.grib)
    with EcmwfOpenDataClient(
        source="ecmwf", transport=httpx.MockTransport(provider), clock=fixed_clock
    ) as client:
        with pytest.raises(EcmwfRangeError):
            client.retrieve(make_request())


def test_index_and_field_bounds_are_enforced_before_range() -> None:
    grib = make_grib()
    oversized_index = OfficialProvider(
        grib=grib,
        index=b" " * (MAX_INDEX_BYTES + 1),
    )
    with EcmwfOpenDataClient(
        source="ecmwf",
        transport=httpx.MockTransport(oversized_index),
        clock=fixed_clock,
    ) as client:
        with pytest.raises(EcmwfResponseTooLargeError):
            client.retrieve(make_request())
    assert oversized_index.file_requests == []

    oversized_field = OfficialProvider(grib=grib)
    oversized_field.index = index_body(
        grib,
        _length=MAX_FIELD_BYTES + 1,
    )
    with EcmwfOpenDataClient(
        source="ecmwf",
        transport=httpx.MockTransport(oversized_field),
        clock=fixed_clock,
    ) as client:
        with pytest.raises(EcmwfResponseTooLargeError):
            client.retrieve(make_request())
    assert oversized_field.file_requests == []


def test_listing_bound_is_enforced() -> None:
    provider = OfficialProvider()
    provider.page_override["/forecasts/"] = b"x" * (MAX_LISTING_BYTES + 1)
    with EcmwfOpenDataClient(
        source="ecmwf", transport=httpx.MockTransport(provider), clock=fixed_clock
    ) as client:
        with pytest.raises(EcmwfResponseTooLargeError):
            client.retrieve(make_request())
    assert len(provider.seen) == 1


def test_source_is_a_fixed_choice_not_an_arbitrary_host() -> None:
    assert resolve_origin("aws").host in ALLOWED_HOSTS
    with pytest.raises(EcmwfSourceError):
        EcmwfOpenDataClient(source="https://untrusted.example")
    with pytest.raises(EcmwfSourceError):
        resolve_origin("mirror")


def test_request_and_location_bounds_are_explicit() -> None:
    with pytest.raises(EcmwfInvalidRequestError):
        EcmwfLocation(point_id="bad", latitude=91, longitude=0)
    with pytest.raises(EcmwfInvalidRequestError):
        EcmwfLocation(point_id="bad", latitude=0, longitude=181)
    with pytest.raises(EcmwfInvalidRequestError):
        EcmwfLocation(point_id="bad", latitude=float("nan"), longitude=0)
    with pytest.raises(EcmwfInvalidRequestError):
        EcmwfOpenDataRequest(
            run_date=RUN_DATE,
            cycle_hour=1,
            step_hours=0,
            locations=(EcmwfLocation("x", 0, 0),),
        )
    with pytest.raises(EcmwfInvalidRequestError):
        EcmwfOpenDataRequest(
            run_date=RUN_DATE,
            cycle_hour=0,
            step_hours=2,
            locations=(EcmwfLocation("x", 0, 0),),
        )
    with pytest.raises(EcmwfInvalidRequestError):
        EcmwfOpenDataRequest(
            run_date=date(2099, 1, 1),
            cycle_hour=0,
            step_hours=0,
            locations=(EcmwfLocation("x", 0, 0),),
        )
    with pytest.raises(EcmwfInvalidRequestError):
        EcmwfOpenDataRequest(
            run_date=RUN_DATE,
            cycle_hour=0,
            step_hours=0,
            locations=(
                EcmwfLocation("same", 0, 0),
                EcmwfLocation("same", 1, 1),
            ),
        )


def test_missing_official_link_is_a_typed_not_found() -> None:
    provider = OfficialProvider()
    provider.page_override["/forecasts/"] = b"<html>no run links</html>"
    with EcmwfOpenDataClient(
        source="ecmwf", transport=httpx.MockTransport(provider), clock=fixed_clock
    ) as client:
        with pytest.raises(EcmwfAssetNotFoundError):
            client.retrieve(make_request())
