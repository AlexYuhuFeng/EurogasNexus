"""Real PostgreSQL acceptance for RFC-0007 S3 append-or-verify.

Each test owns a disposable PG schema and persists the existing research ORM rows.
The actual S2 bounded transport path, the existing S1 decoder/evidence validation,
the existing forecast repository and the new application wrapper are exercised;
only the optional native ecCodes decoder is replaced by a synthetic mechanics
decoder.  This is not an actual provider capture, historical availability proof,
rights grant, archive-read eligibility or forecast-accuracy claim.
"""

from __future__ import annotations

import itertools
import json
import os
import time
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from email.utils import format_datetime
from threading import Event, Thread
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from eurogas_nexus.application.research.weather_archive_capture import (
    validate_archive_capture,
)
from eurogas_nexus.application.research.weather_archive_evidence import (
    WeatherArchiveMetadataError,
)
from eurogas_nexus.application.research.weather_archive_persistence import (
    persist_weather_archive_capture,
)
from eurogas_nexus.db.models.research import (
    CanonicalEntityRecord,
    ForecastObservationRecord,
    SeriesDefinitionRecord,
    SourceEntityMappingRecord,
)
from eurogas_nexus.db.repositories.ecmwf_forecasts import (
    _ARCHIVE_LOCK_BUDGET_SECONDS,
    _ARCHIVE_LOOKUP_LIMIT,
    EcmwfForecastArchiveBusy,
    EcmwfForecastArchiveChanged,
    EcmwfForecastArchiveEvidenceMissing,
    EcmwfForecastArchiveLookupLimit,
    EcmwfForecastArchivePendingWrites,
    EcmwfForecastPointBinding,
    EcmwfForecastSeriesError,
    EcmwfForecastValidationError,
    append_ecmwf_forecast,
)
from eurogas_nexus.ingestion.ecmwf_archive_capture import capture_archive_sources
from eurogas_nexus.ingestion.ecmwf_grib import (
    EcmwfDecodedField,
    EcmwfDecoderMetadata,
    EcmwfPoint,
)
from eurogas_nexus.ingestion.ecmwf_open_data import (
    EcmwfLocation,
    EcmwfOpenDataRequest,
)

_POSTGRES_URL = os.environ.get("EUROGAS_NEXUS_TEST_POSTGRES_URL") or os.environ.get(
    "RUNTIME_STORE_DATABASE_URL", ""
)
pytestmark = pytest.mark.skipif(
    not _POSTGRES_URL.startswith("postgresql"),
    reason="Explicit PostgreSQL test URL required; each test uses a disposable schema.",
)

RUN_DATE = date(2025, 1, 15)
VALID_AT = datetime(2025, 1, 16, 0, 0, tzinfo=UTC)
REQUEST = EcmwfOpenDataRequest(
    run_date=RUN_DATE,
    cycle_hour=0,
    step_hours=24,
    locations=(
        EcmwfLocation("london", 51.5, -0.1),
        EcmwfLocation("edinburgh", 55.95, -3.19),
    ),
)
LONDON_REQUEST = EcmwfOpenDataRequest(
    run_date=RUN_DATE,
    cycle_hour=0,
    step_hours=24,
    locations=(EcmwfLocation("london", 51.5, -0.1),),
)
EDINBURGH_REQUEST = EcmwfOpenDataRequest(
    run_date=RUN_DATE,
    cycle_hour=0,
    step_hours=24,
    locations=(EcmwfLocation("edinburgh", 55.95, -3.19),),
)
INDEX_ETAG = '"opaque-index-validator"'
GRIB_ETAG = '"opaque-grib-validator"'
INDEX_VERSION = "index-v1"
GRIB_VERSION = "grib-v1"
INDEX_LM = datetime(2025, 1, 15, 8, 34, 1, tzinfo=UTC)
GRIB_LM = datetime(2025, 1, 15, 8, 34, 29, tzinfo=UTC)
CLOCK_START = datetime(2025, 1, 15, 9, 0, 0, tzinfo=UTC)


def _grib_bytes(*, length: int = 20, fill: int = 0) -> bytes:
    data = bytearray(length)
    data[0:4] = b"GRIB"
    data[4] = fill
    data[7] = 2
    data[8:16] = length.to_bytes(8, "big")
    data[-4:] = b"7777"
    return bytes(data)


def _index_bytes(
    *,
    grib_length: int = 20,
    offset: int = 0,
    length: int | None = None,
    note: str | None = None,
) -> bytes:
    if length is None:
        length = grib_length - offset
    row = json.dumps(
        {
            "date": "20250115",
            "time": "0000",
            "step": "24",
            "param": "2t",
            "levtype": "sfc",
            "levelist": "2",
            "_offset": str(offset),
            "_length": str(length),
            "units": "K",
            "type": "fc",
            "stream": "oper",
            **({"note": note} if note is not None else {}),
        },
        separators=(",", ":"),
    )
    return (row + "\n").encode("utf-8")


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


def _clock(start: datetime):
    ticks = itertools.count()
    return lambda: start + timedelta(seconds=next(ticks))


def _capture(
    *,
    request: EcmwfOpenDataRequest = REQUEST,
    grib_bytes: bytes | None = None,
    index_bytes: bytes | None = None,
    index_etag: str = INDEX_ETAG,
    grib_etag: str = GRIB_ETAG,
    index_version: str | None = INDEX_VERSION,
    grib_version: str | None = GRIB_VERSION,
    index_lm: datetime = INDEX_LM,
    grib_lm: datetime = GRIB_LM,
    grib_offset: int = 0,
    clock_start: datetime = CLOCK_START,
):
    grib = _grib_bytes() if grib_bytes is None else grib_bytes
    index = (
        _index_bytes(grib_length=len(grib), offset=grib_offset)
        if index_bytes is None
        else index_bytes
    )
    range_length = len(grib) - grib_offset

    def handler(http_request: httpx.Request) -> httpx.Response:
        is_index = http_request.url.path.endswith(".index")
        if http_request.method == "HEAD":
            return httpx.Response(
                200,
                headers=_headers(
                    length=len(index) if is_index else len(grib),
                    etag=index_etag if is_index else grib_etag,
                    version=index_version if is_index else grib_version,
                    last_modified=index_lm if is_index else grib_lm,
                    date_header=clock_start,
                ),
            )
        if is_index:
            return httpx.Response(
                200,
                headers=_headers(
                    length=len(index),
                    etag=index_etag,
                    version=index_version,
                    last_modified=index_lm,
                    date_header=clock_start + timedelta(seconds=1),
                ),
                content=index,
            )
        headers = _headers(
            length=range_length,
            etag=grib_etag,
            version=grib_version,
            last_modified=grib_lm,
            date_header=clock_start + timedelta(seconds=1),
        )
        headers["content-range"] = (
            f"bytes {grib_offset}-{grib_offset + range_length - 1}/{len(grib)}"
        )
        return httpx.Response(
            206,
            headers=headers,
            content=grib[grib_offset : grib_offset + range_length],
        )

    return capture_archive_sources(
        request,
        transport=httpx.MockTransport(handler),
        clock=_clock(clock_start),
        sleep=lambda _seconds: None,
    )


class _FakeDecoder:
    def __init__(self, request: EcmwfOpenDataRequest) -> None:
        self.request = request

    def decode(self, field) -> EcmwfDecodedField:
        points = tuple(
            EcmwfPoint(
                reference=field.reference,
                point_id=location.point_id,
                requested_latitude=location.latitude,
                requested_longitude=location.longitude,
                grid_latitude=location.latitude,
                grid_longitude=location.longitude,
                distance_km=0.0,
                temperature_kelvin=278.15 + index,
                temperature_celsius=(278.15 + index) - 273.15,
            )
            for index, location in enumerate(self.request.locations)
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
            data_time_utc=self.request.issued_at_utc,
            validity_at_utc=VALID_AT,
            forecast_step_hours=24,
            request_sha256=self.request.fingerprint(),
        )
        return EcmwfDecodedField(
            reference=field.reference,
            metadata=metadata,
            points=points,
        )


def _persist(
    session: Session,
    capture,
    bindings: tuple[EcmwfForecastPointBinding, ...],
    *,
    ingested_at_utc: datetime | None = None,
):
    return persist_weather_archive_capture(
        session,
        capture,
        bindings=bindings,
        ingested_at_utc=(
            capture.completed_at_utc + timedelta(minutes=10)
            if ingested_at_utc is None
            else ingested_at_utc
        ),
        public_read_continuity_assumption=True,
        decoder=_FakeDecoder(capture.request),
    )


def _seed_identity(
    session: Session,
    point_ids: tuple[str, ...],
) -> dict[str, EcmwfForecastPointBinding]:
    bindings: dict[str, EcmwfForecastPointBinding] = {}
    for point_id in point_ids:
        entity_id = f"entity-{point_id}"
        series_id = f"series-{point_id}"
        session.add(
            CanonicalEntityRecord(
                canonical_entity_id=entity_id,
                entity_type="grid_point",
                canonical_code=point_id.upper(),
                display_name=point_id,
                description="synthetic archive-persistence identity",
            )
        )
        session.add(
            SeriesDefinitionRecord(
                series_id=series_id,
                name=f"2t {point_id}",
                metric_type="temperature",
                entity_type="grid_point",
                entity_id=entity_id,
                source_class="PUBLIC_OPEN_DATA",
                native_frequency="instant",
                native_unit="degC",
                temporal_type="instantaneous",
                availability_semantics="archive_evidence_only",
                schema_version="series/v1",
            )
        )
        session.add(
            SourceEntityMappingRecord(
                mapping_id=f"mapping-{point_id}",
                canonical_entity_id=entity_id,
                source_id="ECMWF_OPEN_DATA",
                source_entity_type="GRID_POINT",
                source_identifier=point_id,
                valid_from_utc=datetime(2024, 1, 1, tzinfo=UTC),
                mapping_status="ACTIVE",
                confidence="CONFIRMED",
                evidence="synthetic archive-persistence mapping",
            )
        )
        bindings[point_id] = EcmwfForecastPointBinding(point_id, series_id, entity_id)
    session.flush()
    return bindings


@contextmanager
def _session():
    url = make_url(_POSTGRES_URL)
    connect_args = (
        {"timeout": 5} if url.get_driver_name() == "pg8000" else {"connect_timeout": 5}
    )
    engine = create_engine(url, future=True, connect_args=connect_args)
    schema = f"weatherarchivepersistence_{uuid4().hex}"
    schema_created = False
    try:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL statement_timeout = '10s'"))
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            schema_created = True
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            CanonicalEntityRecord.__table__.create(bind=connection)
            SeriesDefinitionRecord.__table__.create(bind=connection)
            SourceEntityMappingRecord.__table__.create(bind=connection)
            ForecastObservationRecord.__table__.create(bind=connection)
            with Session(bind=connection) as session:
                yield session
    finally:
        try:
            if schema_created:
                with engine.begin() as connection:
                    connection.execute(text("SET LOCAL statement_timeout = '10s'"))
                    connection.execute(text("SET LOCAL lock_timeout = '5s'"))
                    connection.execute(
                        text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                    )
        finally:
            engine.dispose()


@contextmanager
def _two_sessions():
    """Two independent PostgreSQL sessions sharing one disposable schema."""

    url = make_url(_POSTGRES_URL)
    connect_args = (
        {"timeout": 5} if url.get_driver_name() == "pg8000" else {"connect_timeout": 5}
    )
    engine = create_engine(url, future=True, connect_args=connect_args)
    schema = f"weatherarchiveconcurrency_{uuid4().hex}"
    schema_created = False
    sessions: list[Session] = []
    try:
        with engine.begin() as connection:
            connection.execute(text("SET LOCAL statement_timeout = '10s'"))
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
            schema_created = True
            connection.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            CanonicalEntityRecord.__table__.create(bind=connection)
            SeriesDefinitionRecord.__table__.create(bind=connection)
            SourceEntityMappingRecord.__table__.create(bind=connection)
            ForecastObservationRecord.__table__.create(bind=connection)
        for _ in range(2):
            connection = engine.connect()
            connection.execute(text(f'SET search_path TO "{schema}"'))
            connection.execute(text("SET statement_timeout = '10s'"))
            connection.execute(text("SET lock_timeout = '5s'"))
            connection.commit()
            sessions.append(Session(bind=connection))
        yield sessions[0], sessions[1]
    finally:
        for session in sessions:
            session.close()
        try:
            if schema_created:
                with engine.begin() as connection:
                    connection.execute(text("SET LOCAL statement_timeout = '10s'"))
                    connection.execute(text("SET LOCAL lock_timeout = '5s'"))
                    connection.execute(
                        text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
                    )
        finally:
            engine.dispose()


def _count(session: Session, model: type[object]) -> int:
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_first_insert_replay_preserves_first_receipt_and_immutable_provenance():
    with _session() as session:
        bindings = _seed_identity(session, ("london",))
        first_capture = _capture(request=LONDON_REQUEST)
        first = _persist(
            session,
            first_capture,
            (bindings["london"],),
        )

        assert first.inserted == 1
        assert first.duplicates == 0
        assert first.rows_seen == 1
        assert first.availability_basis == "ARCHIVE_OBJECT_LAST_MODIFIED_RECONSTRUCTION"
        observation_id = first.forecast_observation_ids[0]
        row = session.get(ForecastObservationRecord, observation_id)
        assert row is not None
        assert row.available_at_utc == first_capture.completed_at_utc
        first_available = row.available_at_utc
        first_ingested = row.ingested_at_utc
        first_provenance = deepcopy(row.provenance)
        assert first_provenance["schema"] == "ecmwf-open-data-forecast-observation/v3"
        assert first_provenance["request"]["locations"] == [
            {"point_id": "london", "latitude": 51.5, "longitude": -0.1}
        ]
        archive_block = first_provenance["archive_evidence"]
        assert archive_block["captured_at_utc"] == (
            first_capture.completed_at_utc.isoformat()
        )
        assert archive_block["evidence_hash"] == first.archive_evidence_hash
        assert archive_block["effective_archive_available_at_utc"] == GRIB_LM.isoformat()
        assert archive_block["binding"]["forecast_observation_id"] == observation_id

        replay_capture = _capture(
            request=LONDON_REQUEST,
            clock_start=first_capture.completed_at_utc + timedelta(days=1),
        )
        replay = _persist(
            session,
            replay_capture,
            (bindings["london"],),
        )

        assert replay.inserted == 0
        assert replay.duplicates == 1
        assert replay.forecast_observation_ids == first.forecast_observation_ids
        assert replay.archive_evidence_hash != first.archive_evidence_hash
        replay_row = session.get(ForecastObservationRecord, observation_id)
        assert replay_row is not None
        assert replay_row.available_at_utc == first_available
        assert replay_row.ingested_at_utc == first_ingested
        assert replay_row.provenance == first_provenance
        assert _count(session, ForecastObservationRecord) == 1
        assert session.in_transaction()


def test_tied_object_last_modified_uses_the_single_tied_instant():
    with _session() as session:
        bindings = _seed_identity(session, ("london",))
        capture = _capture(
            request=LONDON_REQUEST,
            index_lm=GRIB_LM,
        )
        summary = _persist(session, capture, (bindings["london"],))
        assert summary.inserted == 1
        assert summary.effective_archive_available_at_utc == GRIB_LM
        row = session.get(
            ForecastObservationRecord, summary.forecast_observation_ids[0]
        )
        assert row is not None
        block = row.provenance["archive_evidence"]
        assert block["effective_archive_available_at_utc"] == GRIB_LM.isoformat()


def test_changed_same_object_key_with_new_hash_refuses_across_ids():
    with _session() as session:
        bindings = _seed_identity(session, ("london",))
        first_capture = _capture(request=LONDON_REQUEST)
        first = _persist(session, first_capture, (bindings["london"],))
        row = session.get(
            ForecastObservationRecord, first.forecast_observation_ids[0]
        )
        assert row is not None
        first_provenance = deepcopy(row.provenance)

        changed_capture = _capture(
            request=LONDON_REQUEST,
            grib_bytes=_grib_bytes(fill=1),
        )
        assert (
            changed_capture.reference.grib_sha256
            != first_capture.reference.grib_sha256
        )
        with pytest.raises(EcmwfForecastArchiveChanged) as excinfo:
            _persist(session, changed_capture, (bindings["london"],))
        assert excinfo.value.code == "ARCHIVE_OBJECT_CHANGED"
        assert _count(session, ForecastObservationRecord) == 1
        unchanged = session.get(
            ForecastObservationRecord, first.forecast_observation_ids[0]
        )
        assert unchanged is not None
        assert unchanged.provenance == first_provenance


@pytest.mark.parametrize(
    "variant",
    [
        "index_etag",
        "grib_etag",
        "version",
        "null_version",
        "size",
        "last_modified",
        "index_hash",
        "message_hash",
        "range",
    ],
)
def test_changed_object_metadata_is_a_typed_refusal(variant: str):
    with _session() as session:
        bindings = _seed_identity(session, ("london",))
        _persist(session, _capture(request=LONDON_REQUEST), (bindings["london"],))

        if variant == "index_etag":
            capture = _capture(
                request=LONDON_REQUEST, index_etag='"changed-index"'
            )
        elif variant == "grib_etag":
            capture = _capture(
                request=LONDON_REQUEST, grib_etag='"changed-grib"'
            )
        elif variant == "version":
            capture = _capture(request=LONDON_REQUEST, index_version="index-v2")
        elif variant == "null_version":
            capture = _capture(request=LONDON_REQUEST, grib_version=None)
        elif variant == "size":
            capture = _capture(
                request=LONDON_REQUEST,
                grib_bytes=_grib_bytes(length=21),
            )
        elif variant == "last_modified":
            capture = _capture(
                request=LONDON_REQUEST,
                index_lm=INDEX_LM + timedelta(seconds=1),
            )
        elif variant == "index_hash":
            capture = _capture(
                request=LONDON_REQUEST,
                index_bytes=_index_bytes(note="changed index row"),
            )
        elif variant == "message_hash":
            capture = _capture(
                request=LONDON_REQUEST,
                grib_bytes=_grib_bytes(fill=7),
            )
        else:
            capture = _capture(
                request=LONDON_REQUEST,
                grib_bytes=_grib_bytes(length=21),
                grib_offset=1,
            )

        with pytest.raises(EcmwfForecastArchiveChanged) as excinfo:
            _persist(session, capture, (bindings["london"],))
        assert excinfo.value.code == "ARCHIVE_OBJECT_CHANGED"
        assert _count(session, ForecastObservationRecord) == 1


def test_archive_append_keeps_default_v3_identity_and_provenance_fields():
    capture = _capture(request=LONDON_REQUEST)
    ingested = capture.completed_at_utc + timedelta(minutes=10)

    with _session() as default_session:
        default_bindings = _seed_identity(default_session, ("london",))
        validated = validate_archive_capture(
            capture,
            public_read_continuity_assumption=True,
            decoder=_FakeDecoder(capture.request),
        )
        default_summary = append_ecmwf_forecast(
            default_session,
            bindings=(default_bindings["london"],),
            transport=validated.field,
            decoded=validated.decoded,
            ingested_at_utc=ingested,
        )
        default_row = default_session.get(
            ForecastObservationRecord,
            default_summary.forecast_observation_ids[0],
        )
        assert default_row is not None
        default_id = default_row.forecast_observation_id
        default_provenance = deepcopy(default_row.provenance)

    with _session() as archive_session:
        archive_bindings = _seed_identity(archive_session, ("london",))
        archive_summary = _persist(
            archive_session,
            capture,
            (archive_bindings["london"],),
            ingested_at_utc=ingested,
        )
        archive_row = archive_session.get(
            ForecastObservationRecord,
            archive_summary.forecast_observation_ids[0],
        )
        assert archive_row is not None
        assert archive_row.forecast_observation_id == default_id
        archive_provenance = deepcopy(archive_row.provenance)

    archive_block = archive_provenance.pop("archive_evidence")
    assert archive_provenance == default_provenance
    assert archive_block["schema"] == "ecmwf-archive-persistence-evidence/v1"
    assert archive_block["binding"]["forecast_observation_id"] == default_id


def test_different_point_query_fingerprint_is_not_an_object_change():
    with _session() as session:
        bindings = _seed_identity(session, ("london", "edinburgh"))
        first_capture = _capture(request=LONDON_REQUEST)
        first = _persist(session, first_capture, (bindings["london"],))
        assert first.inserted == 1
        row = session.get(
            ForecastObservationRecord, first.forecast_observation_ids[0]
        )
        assert row is not None
        first_provenance = deepcopy(row.provenance)

        second_capture = _capture(request=REQUEST)
        assert second_capture.request_sha256 != first_capture.request_sha256
        second = _persist(
            session,
            second_capture,
            (bindings["london"], bindings["edinburgh"]),
        )

        assert second.inserted == 1
        assert second.duplicates == 1
        replay_row = session.get(
            ForecastObservationRecord, first.forecast_observation_ids[0]
        )
        assert replay_row is not None
        assert replay_row.provenance == first_provenance
        assert _count(session, ForecastObservationRecord) == 2


@pytest.mark.parametrize(
    ("field", "tampered"),
    [
        ("forecast_observation_id", "ecmwf-tampered"),
        ("point_id", "tampered-point"),
        ("series_id", "tampered-series"),
        ("entity_id", "tampered-entity"),
        ("identity_mapping_id", "tampered-mapping"),
        ("request_sha256", "0" * 64),
        ("grib_sha256", "1" * 64),
        ("index_sha256", "2" * 64),
        ("valid_at_utc", "2025-01-16T01:00:00+00:00"),
    ],
)
def test_replay_refuses_tampered_stored_binding_with_unchanged_evidence_hash(
    field: str,
    tampered: str,
):
    with _session() as session:
        bindings = _seed_identity(session, ("london",))
        first = _persist(
            session,
            _capture(request=LONDON_REQUEST),
            (bindings["london"],),
        )
        row = session.get(
            ForecastObservationRecord, first.forecast_observation_ids[0]
        )
        assert row is not None
        provenance = deepcopy(row.provenance)
        block = provenance["archive_evidence"]
        original_evidence_hash = block["evidence_hash"]
        block["binding"][field] = tampered
        row.provenance = provenance
        session.flush()

        assert row.provenance["archive_evidence"]["evidence_hash"] == (
            original_evidence_hash
        )
        with pytest.raises(EcmwfForecastArchiveChanged) as excinfo:
            _persist(
                session,
                _capture(request=LONDON_REQUEST),
                (bindings["london"],),
            )
        assert excinfo.value.code == "ARCHIVE_OBJECT_CHANGED"
        assert _count(session, ForecastObservationRecord) == 1


def test_two_session_concurrent_replay_is_idempotent_with_bounded_timeouts():
    with _two_sessions() as (first_session, second_session):
        bindings = _seed_identity(first_session, ("london",))
        first_session.commit()
        capture = _capture(request=LONDON_REQUEST)
        first = _persist(first_session, capture, (bindings["london"],))
        assert first.inserted == 1

        outcome: dict[str, object] = {}
        started = Event()
        lock_reached = Event()

        def observe_lock(
            _connection,
            _cursor,
            statement,
            _parameters,
            _context,
            _executemany,
        ) -> None:
            if "advisory_xact_lock" in statement.lower():
                lock_reached.set()

        def replay() -> None:
            started.set()
            try:
                outcome["summary"] = _persist(
                    second_session,
                    capture,
                    (bindings["london"],),
                )
            except Exception as exc:  # report the typed refusal, never hide it
                outcome["error"] = exc

        second_bind = second_session.get_bind()
        event.listen(second_bind, "before_cursor_execute", observe_lock)
        try:
            worker = Thread(target=replay, daemon=True)
            worker.start()
            assert started.wait(timeout=5)
            assert lock_reached.wait(timeout=5), (
                "second session did not reach the PostgreSQL archive advisory lock"
            )
            worker.join(timeout=0.5)
            assert worker.is_alive(), (
                "second session did not wait before the first transaction committed"
            )
            first_session.commit()
            worker.join(timeout=10)
            assert not worker.is_alive(), (
                "concurrent replay exceeded its bounded timeout"
            )
        finally:
            event.remove(second_bind, "before_cursor_execute", observe_lock)
        assert "error" not in outcome, repr(outcome.get("error"))
        replay_summary = outcome["summary"]
        assert replay_summary.inserted == 0
        assert replay_summary.duplicates == 1
        assert _count(first_session, ForecastObservationRecord) == 1


def test_two_session_held_lock_times_out_within_budget_without_partial_inserts():
    with _two_sessions() as (holder_session, contender_session):
        bindings = _seed_identity(holder_session, ("london",))
        holder_session.commit()
        capture = _capture(request=LONDON_REQUEST)
        held = _persist(holder_session, capture, (bindings["london"],))
        assert held.inserted == 1
        # The holder's outer transaction is deliberately left open, so its
        # transaction-scoped archive advisory lock remains held.
        assert holder_session.in_transaction()

        # No effective caller lock_timeout: the helper's own monotonic budget is
        # the only reason this attempt can refuse at the asserted bound.
        contender_session.execute(text("SET LOCAL lock_timeout = '0'"))
        assert contender_session.in_transaction()

        statements: list[str] = []

        def observe_statement(
            _connection,
            _cursor,
            statement,
            _parameters,
            _context,
            _executemany,
        ) -> None:
            statements.append(statement.lower())

        contender_bind = contender_session.get_bind()
        event.listen(contender_bind, "before_cursor_execute", observe_statement)
        try:
            started = time.monotonic()
            with pytest.raises(EcmwfForecastArchiveBusy) as excinfo:
                _persist(contender_session, capture, (bindings["london"],))
            elapsed = time.monotonic() - started
        finally:
            event.remove(contender_bind, "before_cursor_execute", observe_statement)

        assert excinfo.value.code == "ECMWF_ARCHIVE_BUSY"
        assert excinfo.value.retryable is True
        assert contender_session.in_transaction()
        # Deterministic intrinsic bound, independent of caller lock_timeout.
        assert elapsed <= _ARCHIVE_LOCK_BUDGET_SECONDS + 1.0
        assert elapsed >= _ARCHIVE_LOCK_BUDGET_SECONDS - 0.5
        assert not contender_session.new
        assert not contender_session.dirty
        assert not contender_session.deleted
        assert not any(
            statement.startswith("insert into")
            and "forecast_observations" in statement
            for statement in statements
        )
        with contender_session.no_autoflush:
            assert _count(contender_session, ForecastObservationRecord) == 0

        # A retry after the first transaction commits is idempotent.
        holder_session.commit()
        replay = _persist(contender_session, capture, (bindings["london"],))
        assert replay.inserted == 0
        assert replay.duplicates == 1
        assert _count(holder_session, ForecastObservationRecord) == 1


def test_object_lookup_refuses_limit_plus_one_instead_of_materializing():
    with _session() as session:
        bindings = _seed_identity(session, ("london",))
        for index in range(_ARCHIVE_LOOKUP_LIMIT + 1):
            capture = _capture(
                request=LONDON_REQUEST,
                grib_bytes=_grib_bytes(fill=index),
            )
            validated = validate_archive_capture(
                capture,
                public_read_continuity_assumption=True,
                decoder=_FakeDecoder(capture.request),
            )
            append_ecmwf_forecast(
                session,
                bindings=(bindings["london"],),
                transport=validated.field,
                decoded=validated.decoded,
                ingested_at_utc=capture.completed_at_utc + timedelta(minutes=10),
            )
        assert _count(session, ForecastObservationRecord) == _ARCHIVE_LOOKUP_LIMIT + 1

        with pytest.raises(EcmwfForecastArchiveLookupLimit) as excinfo:
            _persist(
                session,
                _capture(request=LONDON_REQUEST),
                (bindings["london"],),
            )
        assert excinfo.value.code == "ECMWF_ARCHIVE_LOOKUP_LIMIT"
        assert _count(session, ForecastObservationRecord) == _ARCHIVE_LOOKUP_LIMIT + 1


def test_existing_non_archive_row_is_a_typed_refusal_not_backfilled():
    with _session() as session:
        bindings = _seed_identity(session, ("london",))
        capture = _capture(request=LONDON_REQUEST)
        validated = validate_archive_capture(
            capture,
            public_read_continuity_assumption=True,
            decoder=_FakeDecoder(capture.request),
        )
        appended = append_ecmwf_forecast(
            session,
            bindings=(bindings["london"],),
            transport=validated.field,
            decoded=validated.decoded,
            ingested_at_utc=capture.completed_at_utc + timedelta(minutes=10),
        )
        observation_id = appended.forecast_observation_ids[0]
        row = session.get(ForecastObservationRecord, observation_id)
        assert row is not None
        assert "archive_evidence" not in row.provenance
        first_provenance = deepcopy(row.provenance)

        with pytest.raises(EcmwfForecastArchiveEvidenceMissing) as excinfo:
            _persist(session, capture, (bindings["london"],))
        assert excinfo.value.code == "ECMWF_ARCHIVE_EVIDENCE_MISSING"

        changed = _capture(
            request=LONDON_REQUEST,
            grib_bytes=_grib_bytes(fill=1),
        )
        with pytest.raises(EcmwfForecastArchiveEvidenceMissing):
            _persist(session, changed, (bindings["london"],))
        after = session.get(ForecastObservationRecord, observation_id)
        assert after is not None
        assert after.provenance == first_provenance
        assert _count(session, ForecastObservationRecord) == 1


def test_pending_caller_write_is_refused_before_sql_without_flush():
    with _session() as session:
        bindings = _seed_identity(session, ("london",))
        pending = CanonicalEntityRecord(
            canonical_entity_id="pending-unrelated-entity",
            entity_type="market_hub",
            canonical_code="PENDING",
            display_name="Pending unrelated row",
        )
        session.add(pending)
        assert pending in session.new

        with pytest.raises(EcmwfForecastArchivePendingWrites) as excinfo:
            _persist(session, _capture(request=LONDON_REQUEST), (bindings["london"],))
        assert excinfo.value.code == "ECMWF_ARCHIVE_PENDING_CALLER_WRITES"
        assert pending in session.new
        with session.no_autoflush:
            assert _count(session, ForecastObservationRecord) == 0
        assert pending in session.new


def test_batch_atomicity_keeps_an_earlier_new_row_out_when_a_later_binding_changed():
    with _session() as session:
        bindings = _seed_identity(session, ("london", "edinburgh"))
        _persist(
            session,
            _capture(request=EDINBURGH_REQUEST),
            (bindings["edinburgh"],),
        )
        assert _count(session, ForecastObservationRecord) == 1
        old_row = session.scalars(select(ForecastObservationRecord)).one()
        old_provenance = deepcopy(old_row.provenance)

        changed = _capture(
            request=REQUEST,
            grib_bytes=_grib_bytes(fill=1),
        )
        with pytest.raises(EcmwfForecastArchiveChanged) as excinfo:
            _persist(
                session,
                changed,
                (bindings["london"], bindings["edinburgh"]),
            )
        assert excinfo.value.code == "ARCHIVE_OBJECT_CHANGED"
        assert _count(session, ForecastObservationRecord) == 1
        surviving = session.scalars(select(ForecastObservationRecord)).one()
        assert surviving.series_id == "series-edinburgh"
        assert surviving.provenance == old_provenance


def test_invalid_mapping_type_and_clock_are_refused_without_forecast_rows():
    with _session() as session:
        missing = EcmwfForecastPointBinding(
            "london", "missing-series", "missing-entity"
        )
        with pytest.raises(EcmwfForecastSeriesError):
            _persist(session, _capture(request=LONDON_REQUEST), (missing,))
        assert _count(session, ForecastObservationRecord) == 0

    with _session() as session:
        with pytest.raises(WeatherArchiveMetadataError):
            persist_weather_archive_capture(
                session,
                object(),
                bindings=(missing,),
                ingested_at_utc=CLOCK_START + timedelta(minutes=10),
                public_read_continuity_assumption=True,
                decoder=_FakeDecoder(LONDON_REQUEST),
            )
        with pytest.raises(EcmwfForecastValidationError):
            _persist(
                session,
                _capture(request=LONDON_REQUEST),
                (missing,),
                ingested_at_utc=datetime(2025, 1, 15, 9, 10),
            )
        assert _count(session, ForecastObservationRecord) == 0
