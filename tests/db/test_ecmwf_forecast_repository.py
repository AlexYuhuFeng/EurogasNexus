"""Focused SQLite tests for the append-only ECMWF forecast repository.

These use real SQLite tables and typed transport/decoded fixtures.  The GRIB
bytes are a synthetic transport fixture: this file tests persistence and
cross-validation, not authentic ecCodes decoding.  Root's real capture/decode
probe remains the source of that evidence.

Every decoded point is bound explicitly.  There is no field-wide series/entity
default: a missing, duplicate, or mismatched binding is refused before any row
is written, and every row carries only its own point's mapping identity.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models.research import (
    CanonicalEntityRecord,
    ForecastObservationRecord,
    SeriesDefinitionRecord,
    SourceEntityMappingRecord,
)
from eurogas_nexus.db.repositories.ecmwf_forecasts import (
    CANONICAL_UNIT,
    SOURCE_SYSTEM,
    EcmwfForecastConflict,
    EcmwfForecastPointBinding,
    EcmwfForecastSeriesError,
    EcmwfForecastValidationError,
    append_ecmwf_forecast,
)
from eurogas_nexus.ingestion.ecmwf_grib import (
    EcmwfDecodedField,
    EcmwfDecoderMetadata,
    EcmwfPoint,
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
    EcmwfParamIdBasis,
    EcmwfRun,
    EcmwfSource,
)

ENTITY_ID = "entity-london"
ENTITY_B_ID = "entity-manchester"
ENTITY_C_ID = "entity-leeds"
SERIES_ID = "series-london-2t"
SERIES_B_ID = "series-manchester-2t"
SERIES_C_ID = "series-leeds-2t"
MAPPING_ID = "mapping-a"
MAPPING_B_ID = "mapping-b"
MAPPING_C_ID = "mapping-c"
RUN_DATE = date(2026, 1, 2)
CYCLE_HOUR = 0
STEP_HOURS = 6
GRIB_BYTES = b"GRIB2 synthetic typed transport fixture for repository tests"
GRIB_SHA256 = hashlib.sha256(GRIB_BYTES).hexdigest()
PROVIDER_LAST_MODIFIED = datetime(2026, 1, 2, 2, 50, tzinfo=UTC)
DEFAULT_RECEIPT = datetime(2026, 1, 2, 3, 0, tzinfo=UTC)
DEFAULT_MAPPING_VALID_FROM = datetime(2025, 1, 1, tzinfo=UTC)
SINGLE_LOCATION = (EcmwfLocation("point-a", 51.5, -0.1),)
TWO_LOCATIONS = (
    EcmwfLocation("point-a", 51.5, -0.1),
    EcmwfLocation("point-b", 53.4, -2.2),
)


def _fixture(
    *,
    receipt: datetime = DEFAULT_RECEIPT,
    provider_last_modified: datetime | None = PROVIDER_LAST_MODIFIED,
    locations: tuple[EcmwfLocation, ...] | None = None,
    temperatures_celsius: tuple[float, ...] | None = None,
    grib_bytes: bytes = GRIB_BYTES,
) -> tuple[EcmwfField, EcmwfDecodedField, EcmwfOpenDataRequest]:
    locations = locations or TWO_LOCATIONS
    grib_sha256 = hashlib.sha256(grib_bytes).hexdigest()
    request = EcmwfOpenDataRequest(
        run_date=RUN_DATE,
        cycle_hour=CYCLE_HOUR,
        step_hours=STEP_HOURS,
        locations=locations,
    )
    valid_at = request.valid_at_utc
    row = EcmwfIndexRow(
        row_offset=0,
        row_sha256=hashlib.sha256(b"index-row").hexdigest(),
        row_json='{"param":"2t","units":"K","step":6}',
        param_id=167,
        short_name="2t",
        name="2 metre temperature",
        units="K",
        level_type="sfc",
        level="2",
        data_type="fc",
        stream="oper",
        run_date=RUN_DATE,
        cycle_hour=CYCLE_HOUR,
        step_hours=STEP_HOURS,
        byte_offset=0,
        byte_length=len(grib_bytes),
        param_id_basis=EcmwfParamIdBasis.INDEX_DECLARED,
    )
    index = EcmwfIndex(
        raw_sha256=hashlib.sha256(b"index-body").hexdigest(),
        raw_size_bytes=10,
        row_count=1,
        selected=row,
    )
    reference = EcmwfFieldReference(
        source=EcmwfSource.ECMWF,
        origin="ECMWF official open data",
        asset_url="https://data.ecmwf.int/forecasts/20260102/00z/ifs/0p25/oper/f.grib2",
        request_sha256=request.fingerprint(),
        grib_sha256=grib_sha256,
        index_sha256=index.raw_sha256,
        index_row_offset=0,
        run_date=RUN_DATE,
        cycle_hour=CYCLE_HOUR,
        step_hours=STEP_HOURS,
        valid_at_utc=valid_at,
    )
    availability = (
        EcmwfAvailabilityBasis.PROVIDER_LAST_MODIFIED
        if provider_last_modified is not None
        else EcmwfAvailabilityBasis.LOCAL_RECEIPT_ONLY
    )
    run = EcmwfRun(
        request=request,
        request_sha256=request.fingerprint(),
        source=EcmwfSource.ECMWF,
        origin="ECMWF official open data",
        directory_url="https://data.ecmwf.int/forecasts/20260102/00z/ifs/0p25/oper/",
        asset_url=reference.asset_url,
        index_url=reference.asset_url + ".index",
        listing_pages=(
            EcmwfListingPage(
                url="https://data.ecmwf.int/forecasts/20260102/00z/",
                sha256=hashlib.sha256(b"listing").hexdigest(),
            ),
        ),
        issued_at_utc=request.issued_at_utc,
        valid_at_utc=valid_at,
        request_started_at_utc=receipt - timedelta(minutes=2),
        receipt_completed_at_utc=receipt,
        provider_last_modified_utc=provider_last_modified,
        availability_basis=availability,
    )
    field = EcmwfField(
        run=run,
        index=index,
        reference=reference,
        grib_bytes=grib_bytes,
        grib_sha256=grib_sha256,
        content_range=f"bytes 0-{len(grib_bytes) - 1}/{len(grib_bytes)}",
        asset_total_bytes=len(grib_bytes),
    )
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
        data_time_utc=request.issued_at_utc,
        validity_at_utc=valid_at,
        forecast_step_hours=STEP_HOURS,
        request_sha256=request.fingerprint(),
    )
    defaults = (5.0, 7.5, 9.0)
    values = temperatures_celsius or defaults[: len(locations)]
    points = []
    for offset, (location, celsius) in enumerate(zip(locations, values, strict=True)):
        kelvin = celsius + 273.15
        points.append(
            EcmwfPoint(
                reference=reference,
                point_id=location.point_id,
                requested_latitude=location.latitude,
                requested_longitude=location.longitude,
                grid_latitude=location.latitude + 0.1,
                grid_longitude=location.longitude + 0.2,
                distance_km=10.0 + offset,
                temperature_kelvin=kelvin,
                # Match the decoder's exact subtraction relation.
                temperature_celsius=kelvin - 273.15,
            )
        )
    decoded = EcmwfDecodedField(
        reference=reference,
        metadata=metadata,
        points=tuple(points),
    )
    return field, decoded, request


def _binding(
    point_id: str,
    *,
    entity_id: str = ENTITY_ID,
    series_id: str = SERIES_ID,
) -> EcmwfForecastPointBinding:
    return EcmwfForecastPointBinding(
        point_id=point_id,
        series_id=series_id,
        entity_id=entity_id,
    )


def _seed_identity(
    session: Session,
    *,
    point_id: str = "point-a",
    entity_id: str = ENTITY_ID,
    series_id: str = SERIES_ID,
    mapping_id: str = MAPPING_ID,
    canonical_code: str = "LONDON",
    display_name: str = "London",
    source_class: str = "ECMWF_OPEN_DATA",
    native_unit: str = "degC",
    temporal_type: str = "instant",
    mapping_status: str = "ACTIVE",
    mapping_source_entity_type: str = "grid_point",
    mapping_valid_from: datetime = DEFAULT_MAPPING_VALID_FROM,
    mapping_valid_to: datetime | None = None,
    mapping_entity_id: str | None = None,
    create_entity: bool = True,
    create_mapping: bool = True,
) -> EcmwfForecastPointBinding:
    if create_entity and session.get(CanonicalEntityRecord, entity_id) is None:
        session.add(
            CanonicalEntityRecord(
                canonical_entity_id=entity_id,
                entity_type="weather_point",
                canonical_code=canonical_code,
                display_name=display_name,
            )
        )

    series = session.get(SeriesDefinitionRecord, series_id)
    if series is None:
        series = SeriesDefinitionRecord(
            series_id=series_id,
            name=f"{display_name} 2t forecast",
            metric_type="temperature",
            entity_type="weather_point",
            entity_id=entity_id,
            source_class=source_class,
            native_frequency="6h",
            native_unit=native_unit,
            temporal_type=temporal_type,
            availability_semantics="actual_local_receipt",
        )
        session.add(series)
    else:
        series.entity_id = entity_id
        series.source_class = source_class
        series.native_unit = native_unit
        series.temporal_type = temporal_type

    if create_mapping:
        target_entity_id = mapping_entity_id or entity_id
        mapping = session.get(SourceEntityMappingRecord, mapping_id)
        if mapping is None:
            mapping = SourceEntityMappingRecord(
                mapping_id=mapping_id,
                canonical_entity_id=target_entity_id,
                source_id="ECMWF_OPEN_DATA",
                source_entity_type=mapping_source_entity_type,
                source_identifier=point_id,
                valid_from_utc=mapping_valid_from,
                valid_to_utc=mapping_valid_to,
                mapping_status=mapping_status,
            )
            session.add(mapping)
        else:
            mapping.canonical_entity_id = target_entity_id
            mapping.source_entity_type = mapping_source_entity_type
            mapping.source_identifier = point_id
            mapping.valid_from_utc = mapping_valid_from
            mapping.valid_to_utc = mapping_valid_to
            mapping.mapping_status = mapping_status
    session.flush()
    return _binding(point_id, entity_id=entity_id, series_id=series_id)


def _seed_two_point_identities(
    session: Session,
) -> tuple[EcmwfForecastPointBinding, EcmwfForecastPointBinding]:
    london = _seed_identity(
        session,
        point_id="point-a",
        entity_id=ENTITY_ID,
        series_id=SERIES_ID,
        mapping_id=MAPPING_ID,
        canonical_code="LONDON",
        display_name="London",
    )
    manchester = _seed_identity(
        session,
        point_id="point-b",
        entity_id=ENTITY_B_ID,
        series_id=SERIES_B_ID,
        mapping_id=MAPPING_B_ID,
        canonical_code="MANCHESTER",
        display_name="Manchester",
    )
    return london, manchester


def _append_forecast(
    session: Session,
    field: EcmwfField,
    decoded: EcmwfDecodedField,
    bindings: tuple[EcmwfForecastPointBinding, ...],
    *,
    ingested: datetime | None = None,
):
    return append_ecmwf_forecast(
        session,
        bindings=bindings,
        transport=field,
        decoded=decoded,
        ingested_at_utc=(
            ingested
            if ingested is not None
            else field.run.receipt_completed_at_utc + timedelta(minutes=1)
        ),
    )


def _rows(session: Session) -> list[ForecastObservationRecord]:
    return list(
        session.scalars(
            select(ForecastObservationRecord).order_by(
                ForecastObservationRecord.forecast_observation_id
            )
        )
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            CanonicalEntityRecord.__table__,
            SourceEntityMappingRecord.__table__,
            SeriesDefinitionRecord.__table__,
            ForecastObservationRecord.__table__,
        ],
    )
    with Session(engine) as db_session:
        yield db_session
    engine.dispose()


def test_lookup_queries_do_not_grow_with_the_number_of_points(session: Session) -> None:
    query_counts = []
    for count in (1, 64):
        locations = tuple(
            EcmwfLocation(f"batch-{count}-point-{index}", 51.5 + index * 0.001, -0.1)
            for index in range(count)
        )
        bindings = tuple(
            _seed_identity(
                session,
                point_id=location.point_id,
                entity_id=f"batch-{count}-entity-{index}",
                series_id=f"batch-{count}-series-{index}",
                mapping_id=f"batch-{count}-mapping-{index}",
                canonical_code=f"P{count}_{index}",
            )
            for index, location in enumerate(locations)
        )
        session.flush()
        field, decoded, _ = _fixture(
            locations=locations,
            temperatures_celsius=tuple(5.0 + index * 0.1 for index in range(count)),
        )
        selects = []

        def before_cursor_execute(
            connection, cursor, statement, parameters, context, many, selects=selects
        ):
            if statement.lstrip().upper().startswith("SELECT"):
                selects.append(statement)

        event.listen(session.bind, "before_cursor_execute", before_cursor_execute)
        try:
            result = _append_forecast(session, field, decoded, bindings)
        finally:
            event.remove(session.bind, "before_cursor_execute", before_cursor_execute)
        assert result.inserted == count
        query_counts.append(len(selects))
    assert query_counts[0] == query_counts[1]
    assert query_counts[1] <= 6


def test_appends_two_points_to_distinct_series_entities_and_mappings(session: Session) -> None:
    bindings = _seed_two_point_identities(session)
    field, decoded, request = _fixture()
    receipt = field.run.receipt_completed_at_utc
    ingested = receipt + timedelta(minutes=5)
    summary = _append_forecast(session, field, decoded, bindings, ingested=ingested)

    assert summary.rows_seen == 2
    assert summary.inserted == 2
    assert summary.duplicates == 0
    assert set(summary.forecast_observation_ids) == {
        row.forecast_observation_id for row in _rows(session)
    }

    rows = _rows(session)
    assert len(rows) == 2
    by_point = {row.provenance["point"]["point_id"]: row for row in rows}
    assert set(by_point) == {"point-a", "point-b"}
    expected = {
        "point-a": (SERIES_ID, ENTITY_ID, MAPPING_ID, "LONDON", "London"),
        "point-b": (
            SERIES_B_ID,
            ENTITY_B_ID,
            MAPPING_B_ID,
            "MANCHESTER",
            "Manchester",
        ),
    }
    for point_id, row in by_point.items():
        series_id, entity_id, mapping_id, code, display_name = expected[point_id]
        assert row.series_id == series_id
        assert row.entity_id == entity_id
        assert row.provenance["series"]["series_id"] == series_id
        assert row.provenance["series"]["entity_id"] == entity_id
        assert row.provenance["entity_id"] == entity_id
        assert row.provenance["identity_mapping_ids"] == [mapping_id]
        assert row.provenance["identity_mapping"]["mapping_id"] == mapping_id
        assert row.provenance["identity_mapping"]["source_identifier"] == point_id
        assert row.provenance["canonical_entity"]["canonical_entity_id"] == entity_id
        assert row.provenance["canonical_entity"]["canonical_code"] == code
        assert row.provenance["canonical_entity"]["display_name"] == display_name
        assert row.provenance["binding"] == {
            "point_id": point_id,
            "series_id": series_id,
            "entity_id": entity_id,
            "identity_mapping_id": mapping_id,
        }
        assert _utc(row.forecast_issued_at) == request.issued_at_utc
        assert _utc(row.forecast_valid_start) == request.valid_at_utc
        # Existing schema requires a non-null end; the instant is a zero-length interval.
        assert row.forecast_valid_end == row.forecast_valid_start
        assert row.horizon == "6h"
        assert row.unit == CANONICAL_UNIT
        assert row.source_system == SOURCE_SYSTEM
        assert row.model_provider == "ECMWF"
        assert row.quality_state == "FORECAST"
        assert _utc(row.available_at_utc) == receipt
        assert _utc(row.ingested_at_utc) == ingested
        # A future validity is allowed; availability still comes from actual receipt.
        assert _utc(row.forecast_valid_start) > receipt

        provenance = row.provenance
        assert provenance["source_system"] == "ECMWF_OPEN_DATA"
        assert provenance["source_origin_class"] == "ECMWF_OPEN_DATA"
        assert provenance["legacy_licensed_weather"] is False
        assert provenance["grib_sha256"] == GRIB_SHA256
        assert provenance["request_sha256"] == request.fingerprint()
        assert provenance["grib"]["sha256"] == GRIB_SHA256
        assert provenance["reference"]["asset_url"] == field.reference.asset_url
        assert provenance["reference"]["grib_sha256"] == GRIB_SHA256
        assert provenance["index"]["selected"]["row_json"] == field.index.selected.row_json
        assert provenance["request"]["sha256"] == request.fingerprint()
        assert provenance["decoder"]["library"] == "ecCodes"
        assert provenance["decoder"]["version"] == "2.50.0"
        assert provenance["run"]["receipt_completed_at_utc"] == receipt.isoformat()
        assert (
            provenance["receipt"]["provider_last_modified_utc"]
            == PROVIDER_LAST_MODIFIED.isoformat()
        )
        assert provenance["availability"]["available_at_utc"] == receipt.isoformat()
        assert provenance["availability"]["basis"] == "actual_local_receipt_completion"
        assert provenance["temporal"]["forecast_valid_end"] is None
        assert provenance["point"]["represents_observing_station"] is False
        assert provenance["point"]["temperature_kelvin"] > 0
        assert set(provenance["point"]) >= {
            "requested_coordinates",
            "nearest_grid_coordinates",
        }

    assert set(by_point["point-a"].provenance["identity_mapping_ids"]).isdisjoint(
        by_point["point-b"].provenance["identity_mapping_ids"]
    )
    assert (
        by_point["point-a"].provenance["batch_identity"]
        == by_point["point-b"].provenance["batch_identity"]
    )
    assert (
        by_point["point-a"].provenance["content_sha256"]
        != by_point["point-b"].provenance["content_sha256"]
    )
    assert session.get(SeriesDefinitionRecord, SERIES_ID).entity_id == ENTITY_ID
    assert session.get(SeriesDefinitionRecord, SERIES_B_ID).entity_id == ENTITY_B_ID


def test_single_london_point_accepts_one_explicit_binding(session: Session) -> None:
    binding = _seed_identity(session)
    field, decoded, _ = _fixture(
        locations=SINGLE_LOCATION,
        temperatures_celsius=(5.0,),
    )
    summary = _append_forecast(session, field, decoded, (binding,))

    assert summary.rows_seen == 1
    assert summary.inserted == 1
    rows = _rows(session)
    assert len(rows) == 1
    assert rows[0].series_id == SERIES_ID
    assert rows[0].entity_id == ENTITY_ID
    assert rows[0].provenance["point"]["point_id"] == "point-a"
    assert rows[0].provenance["identity_mapping_ids"] == [MAPPING_ID]
    assert rows[0].provenance["identity_mapping"]["source_identifier"] == "point-a"


def test_identical_repeat_ignores_later_receipt_and_provider_metadata(session: Session) -> None:
    bindings = _seed_two_point_identities(session)
    first_field, first_decoded, _ = _fixture()
    first_receipt = first_field.run.receipt_completed_at_utc
    _append_forecast(session, first_field, first_decoded, bindings)

    later_receipt = first_receipt + timedelta(hours=4)
    later_provider = PROVIDER_LAST_MODIFIED + timedelta(hours=3)
    later_field, later_decoded, _ = _fixture(
        receipt=later_receipt,
        provider_last_modified=later_provider,
    )
    second = _append_forecast(
        session,
        later_field,
        later_decoded,
        bindings,
        ingested=later_receipt + timedelta(minutes=5),
    )

    assert second.inserted == 0
    assert second.duplicates == 2
    rows = _rows(session)
    assert len(rows) == 2
    by_point = {row.provenance["point"]["point_id"]: row for row in rows}
    assert by_point["point-a"].provenance["identity_mapping_ids"] == [MAPPING_ID]
    assert by_point["point-b"].provenance["identity_mapping_ids"] == [MAPPING_B_ID]
    for row in rows:
        assert _utc(row.available_at_utc) == first_receipt
        assert row.provenance["run"]["receipt_completed_at_utc"] == first_receipt.isoformat()
        assert (
            row.provenance["receipt"]["provider_last_modified_utc"]
            == PROVIDER_LAST_MODIFIED.isoformat()
        )


def test_changed_canonical_value_is_refused_atomically(session: Session) -> None:
    bindings = _seed_two_point_identities(session)
    field, decoded, _ = _fixture()
    receipt = field.run.receipt_completed_at_utc
    _append_forecast(session, field, decoded, bindings)
    original_values = {row.provenance["point"]["point_id"]: row.value for row in _rows(session)}

    changed = decoded.points[0]
    changed_kelvin = changed.temperature_kelvin + 1.0
    conflicted_decoded = replace(
        decoded,
        points=(
            replace(
                changed,
                temperature_kelvin=changed_kelvin,
                temperature_celsius=changed_kelvin - 273.15,
            ),
            decoded.points[1],
        ),
    )
    with pytest.raises(EcmwfForecastConflict):
        _append_forecast(
            session,
            field,
            conflicted_decoded,
            bindings,
            ingested=receipt + timedelta(minutes=2),
        )

    rows = _rows(session)
    assert len(rows) == 2
    assert {row.provenance["point"]["point_id"]: row.value for row in rows} == original_values


def test_changed_canonical_entity_content_is_refused(session: Session) -> None:
    bindings = _seed_two_point_identities(session)
    field, decoded, _ = _fixture()
    receipt = field.run.receipt_completed_at_utc
    _append_forecast(session, field, decoded, bindings)

    entity = session.get(CanonicalEntityRecord, ENTITY_ID)
    entity.display_name = "Greater London"
    session.flush()

    with pytest.raises(EcmwfForecastConflict):
        _append_forecast(
            session,
            field,
            decoded,
            bindings,
            ingested=receipt + timedelta(minutes=2),
        )

    rows = _rows(session)
    assert len(rows) == 2
    by_point = {row.provenance["point"]["point_id"]: row for row in rows}
    assert by_point["point-a"].provenance["canonical_entity"]["display_name"] == "London"
    assert (
        by_point["point-b"].provenance["canonical_entity"]["display_name"]
        == "Manchester"
    )


def test_wider_request_duplicates_existing_points_and_appends_new_point(
    session: Session,
) -> None:
    bindings = _seed_two_point_identities(session)
    field, decoded, _ = _fixture()
    receipt = field.run.receipt_completed_at_utc
    _append_forecast(session, field, decoded, bindings)

    third = _seed_identity(
        session,
        point_id="point-c",
        entity_id=ENTITY_C_ID,
        series_id=SERIES_C_ID,
        mapping_id=MAPPING_C_ID,
        canonical_code="LEEDS",
        display_name="Leeds",
    )
    wider_receipt = receipt + timedelta(hours=2)
    wider_field, wider_decoded, _ = _fixture(
        receipt=wider_receipt,
        locations=TWO_LOCATIONS + (EcmwfLocation("point-c", 55.0, -3.0),),
        temperatures_celsius=(5.0, 7.5, 9.0),
    )
    summary = _append_forecast(
        session,
        wider_field,
        wider_decoded,
        (bindings[0], bindings[1], third),
        ingested=wider_receipt + timedelta(minutes=2),
    )

    assert summary.rows_seen == 3
    assert summary.inserted == 1
    assert summary.duplicates == 2

    rows = _rows(session)
    assert len(rows) == 3
    by_point = {row.provenance["point"]["point_id"]: row for row in rows}
    assert set(by_point) == {"point-a", "point-b", "point-c"}
    for point_id in ("point-a", "point-b"):
        assert _utc(by_point[point_id].available_at_utc) == receipt
        assert (
            by_point[point_id].provenance["run"]["receipt_completed_at_utc"]
            == receipt.isoformat()
        )
    assert _utc(by_point["point-c"].available_at_utc) == wider_receipt


def test_changed_grib_same_issuance_appends_new_version_and_replays_as_duplicates(
    session: Session,
) -> None:
    bindings = _seed_two_point_identities(session)
    field, decoded, _ = _fixture()
    first_receipt = field.run.receipt_completed_at_utc
    first = _append_forecast(session, field, decoded, bindings)
    assert first.inserted == 2

    original = {
        row.provenance["point"]["point_id"]: (
            row.forecast_observation_id,
            row.value,
            _utc(row.available_at_utc),
            row.provenance["grib_sha256"],
        )
        for row in _rows(session)
    }

    revised_bytes = GRIB_BYTES + b" provider-corrected revision"
    revised_sha256 = hashlib.sha256(revised_bytes).hexdigest()
    revised_receipt = first_receipt + timedelta(hours=3)
    revised_field, revised_decoded, _ = _fixture(
        grib_bytes=revised_bytes,
        receipt=revised_receipt,
        temperatures_celsius=(6.0, 8.5),
    )
    revised = _append_forecast(
        session,
        revised_field,
        revised_decoded,
        bindings,
        ingested=revised_receipt + timedelta(minutes=2),
    )

    assert revised.inserted == 2
    assert revised.duplicates == 0
    assert revised.batch_identity != first.batch_identity
    rows = _rows(session)
    assert len(rows) == 4

    old_rows = [row for row in rows if row.provenance["grib_sha256"] == GRIB_SHA256]
    new_rows = [row for row in rows if row.provenance["grib_sha256"] == revised_sha256]
    assert len(old_rows) == 2
    assert len(new_rows) == 2
    for row in old_rows:
        point_id = row.provenance["point"]["point_id"]
        assert (
            row.forecast_observation_id,
            row.value,
            _utc(row.available_at_utc),
            row.provenance["grib_sha256"],
        ) == original[point_id]
    expected_new_values = {"point-a": 6.0, "point-b": 8.5}
    for row in new_rows:
        point_id = row.provenance["point"]["point_id"]
        assert row.value == expected_new_values[point_id]
        assert _utc(row.available_at_utc) == revised_receipt
        assert (
            row.provenance["run"]["receipt_completed_at_utc"]
            == revised_receipt.isoformat()
        )
    assert {row.forecast_observation_id for row in old_rows}.isdisjoint(
        {row.forecast_observation_id for row in new_rows}
    )

    replay = _append_forecast(
        session,
        revised_field,
        revised_decoded,
        bindings,
        ingested=revised_receipt + timedelta(hours=1),
    )
    assert replay.inserted == 0
    assert replay.duplicates == 2
    replayed_rows = _rows(session)
    assert len(replayed_rows) == 4
    for row in replayed_rows:
        point_id = row.provenance["point"]["point_id"]
        if row.provenance["grib_sha256"] == GRIB_SHA256:
            assert (
                row.forecast_observation_id,
                row.value,
                _utc(row.available_at_utc),
                row.provenance["grib_sha256"],
            ) == original[point_id]
        else:
            assert row.provenance["grib_sha256"] == revised_sha256
            assert row.value == expected_new_values[point_id]
            assert _utc(row.available_at_utc) == revised_receipt


def test_outer_rollback_removes_the_whole_savepoint_batch(session: Session) -> None:
    bindings = _seed_two_point_identities(session)
    field, decoded, _ = _fixture()
    _append_forecast(session, field, decoded, bindings)
    assert len(_rows(session)) == 2

    session.rollback()
    assert _rows(session) == []


@pytest.mark.parametrize(
    "ingested",
    [
        datetime(2026, 1, 2, 3, 5),  # naive
        datetime(2026, 1, 2, 4, 5, tzinfo=timezone(timedelta(hours=1))),  # non-UTC offset
        datetime(2026, 1, 2, 2, 59, tzinfo=UTC),  # before actual receipt
    ],
)
def test_ingested_at_requires_explicit_utc_not_before_receipt(
    session: Session, ingested: datetime
) -> None:
    bindings = _seed_two_point_identities(session)
    field, decoded, _ = _fixture()
    with pytest.raises(EcmwfForecastValidationError):
        _append_forecast(session, field, decoded, bindings, ingested=ingested)
    assert _rows(session) == []


def test_missing_series_fails_without_rows(session: Session) -> None:
    bindings = (
        EcmwfForecastPointBinding("point-a", SERIES_ID, ENTITY_ID),
        EcmwfForecastPointBinding("point-b", SERIES_B_ID, ENTITY_B_ID),
    )
    field, decoded, _ = _fixture()
    with pytest.raises(EcmwfForecastSeriesError):
        _append_forecast(session, field, decoded, bindings)
    assert _rows(session) == []


def test_legacy_licensed_series_and_non_celsius_units_are_refused(session: Session) -> None:
    binding = _seed_identity(session, source_class="WEATHER")
    field, decoded, _ = _fixture(
        locations=SINGLE_LOCATION,
        temperatures_celsius=(5.0,),
    )
    with pytest.raises(EcmwfForecastSeriesError):
        _append_forecast(session, field, decoded, (binding,))
    assert _rows(session) == []

    session.rollback()
    binding = _seed_identity(session, native_unit="K")
    field, decoded, _ = _fixture(
        locations=SINGLE_LOCATION,
        temperatures_celsius=(5.0,),
    )
    with pytest.raises(EcmwfForecastSeriesError):
        _append_forecast(session, field, decoded, (binding,))
    assert _rows(session) == []


def test_transport_decoded_reference_and_temperature_mismatches_are_refused(
    session: Session,
) -> None:
    binding = _seed_identity(session)
    field, decoded, _ = _fixture(
        locations=SINGLE_LOCATION,
        temperatures_celsius=(5.0,),
    )
    bad_reference = replace(
        decoded,
        reference=replace(decoded.reference, grib_sha256="0" * 64),
    )
    with pytest.raises(EcmwfForecastValidationError):
        _append_forecast(session, field, bad_reference, (binding,))

    bad_point = replace(
        decoded.points[0],
        temperature_celsius=decoded.points[0].temperature_celsius + 1,
    )
    bad_temperature = replace(decoded, points=(bad_point,))
    with pytest.raises(EcmwfForecastValidationError):
        _append_forecast(session, field, bad_temperature, (binding,))
    assert _rows(session) == []


def test_missing_active_identity_mapping_is_refused(session: Session) -> None:
    london = _seed_identity(session)
    manchester = _seed_identity(
        session,
        point_id="point-b",
        entity_id=ENTITY_B_ID,
        series_id=SERIES_B_ID,
        mapping_id=MAPPING_B_ID,
        canonical_code="MANCHESTER",
        display_name="Manchester",
        create_mapping=False,
    )
    field, decoded, _ = _fixture()
    with pytest.raises(EcmwfForecastSeriesError, match="no active approved"):
        _append_forecast(session, field, decoded, (london, manchester))
    assert _rows(session) == []


def test_identity_mapping_to_other_entity_is_refused(session: Session) -> None:
    bindings = _seed_two_point_identities(session)
    mapping = session.get(SourceEntityMappingRecord, MAPPING_ID)
    mapping.canonical_entity_id = ENTITY_B_ID
    session.flush()

    field, decoded, _ = _fixture()
    with pytest.raises(EcmwfForecastSeriesError):
        _append_forecast(session, field, decoded, bindings)
    assert _rows(session) == []


def test_missing_canonical_entity_is_refused(session: Session) -> None:
    _seed_identity(
        session,
        point_id="point-b",
        entity_id=ENTITY_B_ID,
        series_id=SERIES_B_ID,
        mapping_id=MAPPING_B_ID,
        canonical_code="MANCHESTER",
        display_name="Manchester",
    )
    binding = _seed_identity(
        session,
        entity_id="entity-missing",
        create_entity=False,
        mapping_entity_id=ENTITY_B_ID,
    )
    field, decoded, _ = _fixture(
        locations=SINGLE_LOCATION,
        temperatures_celsius=(5.0,),
    )
    with pytest.raises(EcmwfForecastSeriesError, match="canonical entity"):
        _append_forecast(session, field, decoded, (binding,))
    assert _rows(session) == []


def test_missing_or_duplicate_bindings_fail_without_rows(session: Session) -> None:
    london, _ = _seed_two_point_identities(session)
    field, decoded, _ = _fixture()

    with pytest.raises(EcmwfForecastValidationError):
        _append_forecast(session, field, decoded, (london,))
    assert _rows(session) == []

    with pytest.raises(EcmwfForecastValidationError):
        _append_forecast(session, field, decoded, (london, london))
    assert _rows(session) == []

    unknown = EcmwfForecastPointBinding("point-c", SERIES_C_ID, ENTITY_C_ID)
    with pytest.raises(EcmwfForecastValidationError):
        _append_forecast(session, field, decoded, (london, unknown))
    assert _rows(session) == []


def test_ambiguous_active_identity_mapping_is_refused(session: Session) -> None:
    bindings = _seed_two_point_identities(session)
    session.add(
        SourceEntityMappingRecord(
            mapping_id="mapping-a-second",
            canonical_entity_id=ENTITY_ID,
            source_id="ECMWF_OPEN_DATA",
            source_entity_type="grid_point",
            source_identifier="point-a",
            valid_from_utc=datetime(2025, 2, 1, tzinfo=UTC),
            mapping_status="ACTIVE",
        )
    )
    session.flush()

    field, decoded, _ = _fixture()
    with pytest.raises(EcmwfForecastSeriesError, match="ambiguous"):
        _append_forecast(session, field, decoded, bindings)
    assert _rows(session) == []


@pytest.mark.parametrize(
    "mapping_kwargs",
    [
        {"mapping_status": "PROPOSED"},
        {"mapping_valid_from": datetime(2026, 1, 3, tzinfo=UTC)},
        {"mapping_valid_to": datetime(2026, 1, 2, 6, 0, tzinfo=UTC)},
        {"mapping_source_entity_type": "region"},
    ],
)
def test_unapproved_or_invalid_identity_mapping_is_refused(
    session: Session, mapping_kwargs: dict
) -> None:
    binding = _seed_identity(session, **mapping_kwargs)
    field, decoded, _ = _fixture(
        locations=SINGLE_LOCATION,
        temperatures_celsius=(5.0,),
    )
    with pytest.raises(EcmwfForecastSeriesError):
        _append_forecast(session, field, decoded, (binding,))
    assert _rows(session) == []
