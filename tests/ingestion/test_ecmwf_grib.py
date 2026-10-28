"""Decoder unit mechanics with an injected fake ecCodes binding.

No test here claims that the mock is a live ecCodes or live-provider result.  Root
must perform the separate authentic-GRIB integration probe with isolated ecCodes 2.50.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from eurogas_nexus.ingestion.ecmwf_grib import (
    EcmwfDecoderUnavailableError,
    EcmwfDecoderVersionError,
    EcmwfGribDecoder,
    EcmwfGribError,
    EcmwfGribGridMismatchError,
    EcmwfGribInstantMismatchError,
    EcmwfGribMetadataError,
    EcmwfGribParamMismatchError,
    EcmwfGribReferenceMismatchError,
    EcmwfGribRunMismatchError,
    EcmwfGribUnitMismatchError,
    EcmwfGribValidationError,
    EcmwfGribValidityMismatchError,
    EcmwfGribValueMissingError,
)
from eurogas_nexus.ingestion.ecmwf_open_data import (
    EcmwfAvailabilityBasis,
    EcmwfField,
    EcmwfFieldReference,
    EcmwfIndex,
    EcmwfIndexRow,
    EcmwfListingPage,
    EcmwfLocation,
    EcmwfOpenDataRequest,
    EcmwfRun,
    EcmwfSource,
)

RUN_DATE = date(2023, 1, 18)
RECEIPT = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)


def make_grib(size: int = 96, *, edition: int = 2, end: bytes = b"7777") -> bytes:
    data = bytearray(size)
    data[0:4] = b"GRIB"
    data[7] = edition
    data[8:16] = size.to_bytes(8, "big")
    data[-4:] = end
    return bytes(data)


def make_request(*, step: int = 0) -> EcmwfOpenDataRequest:
    return EcmwfOpenDataRequest(
        run_date=RUN_DATE,
        cycle_hour=0,
        step_hours=step,
        locations=(EcmwfLocation("london", 51.5, -0.1),),
    )


def base_metadata(*, step: int = 0) -> dict[str, object]:
    valid = datetime(2023, 1, 18, tzinfo=UTC)
    if step:
        from datetime import timedelta

        valid = valid + timedelta(hours=step)
    return {
        "paramId": 167,
        "units": "K",
        "stepType": "instant",
        "dataDate": 20230118,
        "dataTime": 0,
        "validityDate": int(f"{valid:%Y%m%d}"),
        "validityTime": valid.hour * 100 + valid.minute,
        "step": step,
        "gridType": "regular_ll",
        "Ni": 1440,
        "Nj": 721,
    }


def make_field(
    *,
    grib: bytes | None = None,
    request: EcmwfOpenDataRequest | None = None,
    reference: EcmwfFieldReference | None = None,
) -> EcmwfField:
    request = request or make_request()
    grib = make_grib() if grib is None else grib
    sha = hashlib.sha256(grib).hexdigest()
    selected = EcmwfIndexRow(
        row_offset=0,
        row_sha256="a" * 64,
        row_json="{}",
        param_id=167,
        short_name="2t",
        name="2 metre temperature",
        units="K",
        level_type="sfc",
        level=None,
        data_type="fc",
        stream="oper",
        run_date=request.run_date,
        cycle_hour=request.cycle_hour,
        step_hours=request.step_hours,
        byte_offset=0,
        byte_length=len(grib),
    )
    index = EcmwfIndex(
        raw_sha256="b" * 64,
        raw_size_bytes=1,
        row_count=1,
        selected=selected,
    )
    default_reference = EcmwfFieldReference(
        source=EcmwfSource.ECMWF,
        origin="ECMWF official open data",
        asset_url=(
            "https://data.ecmwf.int/forecasts/20230118/00z/ifs/0p25/oper/"
            "20230118000000-0h-oper-fc.grib2"
        ),
        request_sha256=request.fingerprint(),
        grib_sha256=sha,
        index_sha256=index.raw_sha256,
        index_row_offset=selected.row_offset,
        run_date=request.run_date,
        cycle_hour=request.cycle_hour,
        step_hours=request.step_hours,
        valid_at_utc=request.valid_at_utc,
    )
    run = EcmwfRun(
        request=request,
        request_sha256=request.fingerprint(),
        source=EcmwfSource.ECMWF,
        origin="ECMWF official open data",
        directory_url="https://data.ecmwf.int/forecasts/20230118/00z/ifs/0p25/oper/",
        asset_url=default_reference.asset_url,
        index_url=(
            "https://data.ecmwf.int/forecasts/20230118/00z/ifs/0p25/oper/"
            "20230118000000-0h-oper-fc.index"
        ),
        listing_pages=(EcmwfListingPage(url="https://data.ecmwf.int/forecasts/", sha256="c" * 64),),
        issued_at_utc=request.issued_at_utc,
        valid_at_utc=request.valid_at_utc,
        request_started_at_utc=RECEIPT,
        receipt_completed_at_utc=RECEIPT,
        provider_last_modified_utc=None,
        availability_basis=EcmwfAvailabilityBasis.LOCAL_RECEIPT_ONLY,
    )
    return EcmwfField(
        run=run,
        index=index,
        reference=reference or default_reference,
        grib_bytes=grib,
        grib_sha256=sha,
        content_range=f"bytes 0-{len(grib) - 1}/{len(grib)}",
        asset_total_bytes=len(grib),
    )


class FakeCodes:
    __version__ = "2.50.0"

    def __init__(
        self,
        *,
        metadata: dict[str, object] | None = None,
        nearest: dict[str, object] | None = None,
    ) -> None:
        self.metadata = base_metadata()
        if metadata:
            self.metadata.update(metadata)
        self.nearest = {
            "lat": 51.5,
            "lon": 0.0,
            "distance": 12.5,
            "value": 280.15,
        }
        if nearest:
            self.nearest.update(nearest)
        self.created: list[object] = []
        self.released: list[object] = []
        self.find_calls: list[dict[str, object]] = []

    def codes_new_from_message(self, data: bytes) -> object:
        handle = object()
        self.created.append(handle)
        return handle

    def codes_get(self, handle: object, key: str) -> object:
        if key not in self.metadata:
            raise KeyError(key)
        return self.metadata[key]

    def codes_grib_find_nearest(
        self,
        handle: object,
        latitude: float,
        longitude: float,
        *,
        npoints: int = 1,
    ) -> list[dict[str, object]]:
        self.find_calls.append(
            {
                "handle": handle,
                "latitude": latitude,
                "longitude": longitude,
                "npoints": npoints,
            }
        )
        if npoints != 1:
            raise AssertionError("decoder must request exactly one nearest point")
        return [dict(self.nearest)]

    def codes_release(self, handle: object) -> None:
        self.released.append(handle)


def test_decodes_one_nearest_point_and_always_releases() -> None:
    binding = FakeCodes()
    field = make_field()
    decoded = EcmwfGribDecoder(binding=binding).decode(field)

    assert decoded.reference.grib_sha256 == field.grib_sha256
    assert decoded.metadata.decoder_library == "ecCodes"
    assert decoded.metadata.decoder_version == "2.50.0"
    assert decoded.metadata.param_id == 167
    assert decoded.metadata.units == "K"
    assert decoded.metadata.step_type == "instant"
    assert decoded.metadata.grid_type == "regular_ll"
    assert decoded.metadata.grid_ni == 1440
    assert decoded.metadata.grid_nj == 721
    assert decoded.metadata.data_time_utc == datetime(2023, 1, 18, tzinfo=UTC)
    assert decoded.metadata.validity_at_utc == datetime(2023, 1, 18, tzinfo=UTC)
    assert decoded.metadata.forecast_step_hours == 0
    assert decoded.points[0].point_id == "london"
    assert decoded.points[0].grid_latitude == 51.5
    assert decoded.points[0].grid_longitude == 0.0
    assert decoded.points[0].distance_km == 12.5
    assert decoded.points[0].temperature_kelvin == 280.15
    assert decoded.points[0].temperature_celsius == pytest.approx(7.0)
    assert decoded.points[0].grib_sha256 == field.grib_sha256
    assert binding.find_calls == [
        {
            "handle": binding.created[0],
            "latitude": 51.5,
            "longitude": -0.1,
            "npoints": 1,
        }
    ]
    assert binding.released == binding.created


def test_future_valid_temperature_is_allowed_with_separate_receipt() -> None:
    request = make_request(step=168)
    binding = FakeCodes(metadata=base_metadata(step=168))
    decoded = EcmwfGribDecoder(binding=binding).decode(make_field(request=request))

    assert decoded.metadata.validity_at_utc == datetime(2023, 1, 25, tzinfo=UTC)
    assert decoded.reference.valid_at_utc == datetime(2023, 1, 25, tzinfo=UTC)
    assert decoded.reference.valid_at_utc > request.issued_at_utc
    assert binding.released == binding.created


@pytest.mark.parametrize(
    ("override", "error"),
    [
        ({"paramId": 168}, EcmwfGribParamMismatchError),
        ({"units": "C"}, EcmwfGribUnitMismatchError),
        ({"stepType": "avg"}, EcmwfGribInstantMismatchError),
        ({"dataDate": 20230119}, EcmwfGribRunMismatchError),
        ({"dataTime": 600}, EcmwfGribRunMismatchError),
        ({"validityTime": 100}, EcmwfGribValidityMismatchError),
        ({"step": 3}, EcmwfGribValidityMismatchError),
        ({"gridType": "regular_ga"}, EcmwfGribGridMismatchError),
        ({"Ni": 720}, EcmwfGribGridMismatchError),
    ],
)
def test_wrong_field_metadata_is_refused_and_handle_released(
    override: dict[str, object], error: type[Exception]
) -> None:
    binding = FakeCodes(metadata=override)
    with pytest.raises(error):
        EcmwfGribDecoder(binding=binding).decode(make_field())
    assert binding.released == binding.created


def test_missing_required_metadata_is_typed_and_released() -> None:
    binding = FakeCodes()
    del binding.metadata["validityTime"]
    with pytest.raises(EcmwfGribMetadataError) as exc:
        EcmwfGribDecoder(binding=binding).decode(make_field())
    assert exc.value.code == "ecmwf_grib_metadata_missing"
    assert binding.released == binding.created


@pytest.mark.parametrize("value", [float("nan"), float("inf"), None, 9999.0])
def test_missing_or_non_finite_nearest_value_is_refused(value: object) -> None:
    binding = FakeCodes(nearest={"value": value}, metadata={"missingValue": 9999.0})
    with pytest.raises(EcmwfGribValueMissingError):
        EcmwfGribDecoder(binding=binding).decode(make_field())
    assert binding.released == binding.created


@pytest.mark.parametrize(
    "grib",
    [
        b"NOTGRIB" + b"\x00" * 28,
        make_grib(edition=1),
        b"",
        make_grib()[:-4] + b"0000",
        make_grib() + make_grib(),
        make_grib()[:-4],
    ],
)
def test_malformed_or_multi_message_grib_is_refused_before_ecCodes(grib: bytes) -> None:
    binding = FakeCodes()
    with pytest.raises(EcmwfGribValidationError):
        EcmwfGribDecoder(binding=binding).decode(make_field(grib=grib))
    assert binding.created == []
    assert binding.released == []


def test_declared_length_mismatch_is_refused_before_ecCodes() -> None:
    grib = bytearray(make_grib())
    grib[8:16] = (len(grib) + 1).to_bytes(8, "big")
    binding = FakeCodes()
    with pytest.raises(EcmwfGribValidationError):
        EcmwfGribDecoder(binding=binding).decode(make_field(grib=bytes(grib)))
    assert binding.created == []


def test_hash_mismatch_is_refused_before_ecCodes() -> None:
    field = make_field()
    object.__setattr__(field, "grib_sha256", "0" * 64)
    binding = FakeCodes()
    with pytest.raises(EcmwfGribError):
        EcmwfGribDecoder(binding=binding).decode(field)
    assert binding.created == []


def test_missing_binding_is_a_typed_error_not_a_skip() -> None:
    with pytest.raises(EcmwfDecoderUnavailableError) as exc:
        EcmwfGribDecoder(binding=None).decode(make_field())
    assert exc.value.code == "ecmwf_decoder_unavailable"


def test_old_binding_version_is_refused() -> None:
    binding = FakeCodes()
    binding.__version__ = "2.49.0"
    with pytest.raises(EcmwfDecoderVersionError):
        EcmwfGribDecoder(binding=binding).decode(make_field())
    assert binding.created == []


def test_reference_cross_run_mismatch_is_refused_before_ecCodes() -> None:
    request = make_request()
    field = make_field(request=request)
    bad_reference = replace(field.reference, step_hours=3, valid_at_utc=request.valid_at_utc)
    bad_field = replace(field, reference=bad_reference)
    binding = FakeCodes()
    with pytest.raises(EcmwfGribReferenceMismatchError):
        EcmwfGribDecoder(binding=binding).decode(bad_field)
    assert binding.created == []


def test_decoder_proves_grib_param_and_units_when_index_omits_them() -> None:
    field = make_field()
    selected = replace(field.index.selected, units=None, name=None)
    field = replace(field, index=replace(field.index, selected=selected))

    with pytest.raises(EcmwfGribParamMismatchError):
        EcmwfGribDecoder(binding=FakeCodes(metadata={"paramId": 168})).decode(field)
    with pytest.raises(EcmwfGribUnitMismatchError):
        EcmwfGribDecoder(binding=FakeCodes(metadata={"units": "C"})).decode(field)
