"""Operator tests for the ECMWF forecast ingestion script.

Only the network client and native decoder are replaced.  Transport and decoded
objects are the production typed dataclasses, and persistence uses the real
repository against SQLite.  The script is loaded from its actual path so a
production import failure stays visible rather than being mocked around.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from eurogas_nexus.db import session as db_session
from eurogas_nexus.db.base import Base
from eurogas_nexus.db.models.research import (
    CanonicalEntityRecord,
    ForecastObservationRecord,
    SeriesDefinitionRecord,
    SourceEntityMappingRecord,
)
from eurogas_nexus.db.repositories.ecmwf_forecasts import EcmwfForecastConflict
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

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "ingest_ecmwf_forecasts.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("ingest_ecmwf_forecasts", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ingest = _load_script()

RUN_DATE = date(2026, 1, 2)
CYCLE_HOUR = 0
RECEIPT = datetime(2026, 1, 2, 3, 0, tzinfo=UTC)
INGESTED = datetime(2026, 1, 2, 4, 0, tzinfo=UTC)
ENTITY_ID = "entity-london"
SERIES_ID = "series-london-2t"
MAPPING_ID = "mapping-a"
POINT_A = EcmwfLocation("point-a", 51.5, -0.1)
POINT_B = EcmwfLocation("point-b", 53.4, -2.2)
DEFAULT_BINDING = {
    "point_id": "point-a",
    "latitude": 51.5,
    "longitude": -0.1,
    "series_id": SERIES_ID,
    "entity_id": ENTITY_ID,
}
BINDING_B = {
    "point_id": "point-b",
    "latitude": 53.4,
    "longitude": -2.2,
    "series_id": "series-manchester-2t",
    "entity_id": "entity-manchester",
}
EXPLICIT_URL = "sqlite+pysqlite:///:memory:"


def _grib_bytes(step: int) -> bytes:
    return f"GRIB2 typed transport fixture step {step:03d}".encode("ascii")


def _transport(request: EcmwfOpenDataRequest) -> EcmwfField:
    grib = _grib_bytes(request.step_hours)
    grib_sha256 = hashlib.sha256(grib).hexdigest()
    row_json = f'{{"param":"2t","units":"K","step":{request.step_hours}}}'
    row = EcmwfIndexRow(
        row_offset=0,
        row_sha256=hashlib.sha256(row_json.encode("utf-8")).hexdigest(),
        row_json=row_json,
        param_id=167,
        short_name="2t",
        name="2 metre temperature",
        units="K",
        level_type="sfc",
        level="2",
        data_type="fc",
        stream="oper",
        run_date=request.run_date,
        cycle_hour=request.cycle_hour,
        step_hours=request.step_hours,
        byte_offset=0,
        byte_length=len(grib),
        param_id_basis=EcmwfParamIdBasis.INDEX_DECLARED,
    )
    index = EcmwfIndex(
        raw_sha256=hashlib.sha256(f"index-{request.step_hours}".encode()).hexdigest(),
        raw_size_bytes=len(row_json) + 1,
        row_count=1,
        selected=row,
    )
    reference = EcmwfFieldReference(
        source=EcmwfSource.ECMWF,
        origin="ECMWF official open data",
        asset_url=(
            f"https://data.ecmwf.int/forecasts/{request.run_date:%Y%m%d}/"
            f"{request.cycle_hour:02d}z/ifs/0p25/oper/f.grib2"
        ),
        request_sha256=request.fingerprint(),
        grib_sha256=grib_sha256,
        index_sha256=index.raw_sha256,
        index_row_offset=0,
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
        directory_url=(
            f"https://data.ecmwf.int/forecasts/{request.run_date:%Y%m%d}/"
            f"{request.cycle_hour:02d}z/ifs/0p25/oper/"
        ),
        asset_url=reference.asset_url,
        index_url=reference.asset_url + ".index",
        listing_pages=(
            EcmwfListingPage(
                url="https://data.ecmwf.int/forecasts/",
                sha256=hashlib.sha256(b"listing").hexdigest(),
            ),
        ),
        issued_at_utc=request.issued_at_utc,
        valid_at_utc=request.valid_at_utc,
        request_started_at_utc=RECEIPT - timedelta(minutes=2),
        receipt_completed_at_utc=RECEIPT,
        provider_last_modified_utc=RECEIPT - timedelta(minutes=10),
        availability_basis=EcmwfAvailabilityBasis.PROVIDER_LAST_MODIFIED,
    )
    return EcmwfField(
        run=run,
        index=index,
        reference=reference,
        grib_bytes=grib,
        grib_sha256=grib_sha256,
        content_range=f"bytes 0-{len(grib) - 1}/{len(grib)}",
        asset_total_bytes=len(grib),
    )


def _decoded(field: EcmwfField, temperature_celsius: float = 5.0) -> EcmwfDecodedField:
    request = field.run.request
    metadata = EcmwfDecoderMetadata(
        decoder_library="ecCodes",
        decoder_version="2.50.0",
        param_id=167,
        units="K",
        step_type="instant",
        grid_type="regular_ll",
        grid_ni=1440,
        grid_nj=721,
        data_date=request.run_date,
        data_time_utc=request.issued_at_utc,
        validity_at_utc=request.valid_at_utc,
        forecast_step_hours=request.step_hours,
        request_sha256=request.fingerprint(),
    )
    points = tuple(
        EcmwfPoint(
            reference=field.reference,
            point_id=location.point_id,
            requested_latitude=location.latitude,
            requested_longitude=location.longitude,
            grid_latitude=location.latitude + 0.1,
            grid_longitude=location.longitude + 0.2,
            distance_km=10.0 + offset,
            temperature_kelvin=temperature_celsius + 273.15,
            temperature_celsius=temperature_celsius,
        )
        for offset, location in enumerate(request.locations)
    )
    return EcmwfDecodedField(reference=field.reference, metadata=metadata, points=points)


def _install_capture(
    monkeypatch: pytest.MonkeyPatch,
    *,
    temperatures: dict[int, float] | None = None,
    fail_step: int | None = None,
    fail_message: str = "provider failed",
) -> list[EcmwfOpenDataRequest]:
    requests: list[EcmwfOpenDataRequest] = []
    values = {0: 5.0, 6: 7.5} if temperatures is None else temperatures

    class FakeClient:
        def __init__(self, *, source: EcmwfSource) -> None:
            assert source is EcmwfSource.ECMWF

        def __enter__(self):
            return self

        def __exit__(self, *exc_info) -> bool:
            return False

        def retrieve(self, request: EcmwfOpenDataRequest) -> EcmwfField:
            requests.append(request)
            if fail_step is not None and request.step_hours == fail_step:
                raise RuntimeError(fail_message)
            return _transport(request)

    class FakeDecoder:
        def __init__(self) -> None:
            pass

        def decode(self, field: EcmwfField) -> EcmwfDecodedField:
            return _decoded(field, values[field.run.request.step_hours])

    monkeypatch.setattr(ingest, "EcmwfOpenDataClient", FakeClient)
    monkeypatch.setattr(ingest, "EcmwfGribDecoder", FakeDecoder)
    return requests


def _forbid_db(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("database must not be resolved or opened")

    monkeypatch.setattr(db_session, "get_session_factory", forbidden)
    monkeypatch.setattr(db_session, "resolve_database_url", forbidden)


def _write_bindings(path: Path, value) -> str:
    path.write_text(
        value if isinstance(value, str) else json.dumps(value),
        encoding="utf-8",
    )
    return str(path)


def _args(
    *,
    bindings: str,
    output_dir: Path,
    steps: str = "0,6",
    dry_run: bool = True,
    database_url: str | None = None,
) -> list[str]:
    argv = [
        "--run-date",
        RUN_DATE.isoformat(),
        "--cycle-hour",
        str(CYCLE_HOUR),
        "--steps",
        steps,
        "--bindings",
        bindings,
        "--output-dir",
        str(output_dir),
    ]
    if dry_run:
        argv.append("--dry-run")
    if database_url is not None:
        argv.extend(["--database-url", database_url])
    return argv


def _sqlite_engine():
    engine = create_engine(
        EXPLICIT_URL,
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
    return engine


def _seed_identity(engine) -> None:
    with Session(engine) as session:
        session.add(
            CanonicalEntityRecord(
                canonical_entity_id=ENTITY_ID,
                entity_type="weather_point",
                canonical_code="LONDON",
                display_name="London",
            )
        )
        session.add(
            SeriesDefinitionRecord(
                series_id=SERIES_ID,
                name="London 2t forecast",
                metric_type="temperature",
                entity_type="weather_point",
                entity_id=ENTITY_ID,
                source_class="ECMWF_OPEN_DATA",
                native_frequency="6h",
                native_unit="degC",
                temporal_type="instant",
                availability_semantics="actual_local_receipt",
            )
        )
        session.add(
            SourceEntityMappingRecord(
                mapping_id=MAPPING_ID,
                canonical_entity_id=ENTITY_ID,
                source_id="ECMWF_OPEN_DATA",
                source_entity_type="grid_point",
                source_identifier="point-a",
                valid_from_utc=datetime(2025, 1, 1, tzinfo=UTC),
                valid_to_utc=None,
                mapping_status="ACTIVE",
            )
        )
        session.commit()


def _use_real_sqlite(monkeypatch: pytest.MonkeyPatch, engine) -> None:
    factory = db_session.create_session_factory(engine)

    def factory_for(**kwargs):
        assert kwargs["database_url"] == EXPLICIT_URL
        return factory

    monkeypatch.setattr(db_session, "get_session_factory", factory_for)
    monkeypatch.setattr(
        db_session,
        "resolve_database_url",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("explicit database URL must be used")
        ),
    )


def _captured(step: int, *, temperature: float = 5.0) -> object:
    request = EcmwfOpenDataRequest(
        run_date=RUN_DATE,
        cycle_hour=CYCLE_HOUR,
        step_hours=step,
        locations=(POINT_A,),
    )
    field = _transport(request)
    return ingest._Captured(
        transport=field,
        decoded=_decoded(field, temperature),
        step_hours=step,
    )


def _binding_row() -> object:
    return ingest._BindingRow(
        point_id=POINT_A.point_id,
        latitude=POINT_A.latitude,
        longitude=POINT_A.longitude,
        series_id=SERIES_ID,
        entity_id=ENTITY_ID,
    )


def test_dry_run_archives_exact_two_step_bytes_and_metadata_without_db(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    binding_rows = [DEFAULT_BINDING, BINDING_B]
    bindings = _write_bindings(tmp_path / "bindings.json", binding_rows)
    requests = _install_capture(monkeypatch)
    _forbid_db(monkeypatch)
    output = tmp_path / "capture"

    assert ingest.main(_args(bindings=bindings, output_dir=output)) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    payload = json.loads(captured.out)
    assert payload["status"] == "ok"
    assert payload["dry_run"] is True
    assert payload["persisted"] is False
    assert payload["database"] == "not_attempted"
    assert payload["steps"] == [0, 6]
    assert payload["bindings"] == 2
    assert payload["fields_requested"] == 2
    assert payload["fields_received"] == 2
    assert payload["fields_decoded"] == 2
    assert payload["fields_archived"] == 2
    assert payload["fields_persisted"] == 0
    assert payload["artifacts_complete"] is True
    assert payload["partial_artifacts"] is False
    assert payload["output_dir"] == str(output)

    expected_locations = [
        (row["point_id"], row["latitude"], row["longitude"]) for row in binding_rows
    ]
    assert [
        (
            request.run_date,
            request.cycle_hour,
            request.step_hours,
            [
                (location.point_id, location.latitude, location.longitude)
                for location in request.locations
            ],
        )
        for request in requests
    ] == [
        (RUN_DATE, CYCLE_HOUR, 0, expected_locations),
        (RUN_DATE, CYCLE_HOUR, 6, expected_locations),
    ]

    for step, request, entry in zip((0, 6), requests, payload["hashes"], strict=True):
        expected_field = _transport(request)
        expected_grib = _grib_bytes(step)
        expected_sha = hashlib.sha256(expected_grib).hexdigest()
        assert (output / f"step_{step:03d}.grib2").read_bytes() == expected_grib
        metadata = json.loads(
            (output / f"step_{step:03d}.json").read_text(encoding="utf-8")
        )
        assert metadata["schema"] == ingest.CAPTURE_SCHEMA
        assert metadata["source"] == "ecmwf"
        assert metadata["run_date"] == RUN_DATE.isoformat()
        assert metadata["cycle_hour"] == CYCLE_HOUR
        assert metadata["step_hours"] == step
        assert metadata["valid_at_utc"] == request.valid_at_utc.isoformat()
        assert metadata["grib_file"] == f"step_{step:03d}.grib2"
        assert metadata["grib_size_bytes"] == len(expected_grib)
        assert metadata["hashes"] == {
            "request_sha256": request.fingerprint(),
            "grib_sha256": expected_sha,
            "index_sha256": expected_field.reference.index_sha256,
            "index_row_sha256": expected_field.index.selected.row_sha256,
        }
        assert metadata["receipt_completed_at_utc"] == RECEIPT.isoformat()
        assert metadata["transport"]["grib_sha256"] == expected_sha
        assert "grib_bytes" not in metadata["transport"]
        assert metadata["decoder"]["metadata"]["decoder_library"] == "ecCodes"
        assert metadata["decoder"]["metadata"]["forecast_step_hours"] == step
        assert metadata["decoder"]["points"][0]["point_id"] == "point-a"
        assert entry == {
            "request_sha256": request.fingerprint(),
            "grib_sha256": expected_sha,
            "index_sha256": expected_field.reference.index_sha256,
            "index_row_sha256": expected_field.index.selected.row_sha256,
            "step_hours": step,
            "receipt_completed_at_utc": RECEIPT.isoformat(),
        }


@pytest.mark.parametrize(
    ("raw_bindings", "steps", "expected_code"),
    [
        (
            json.dumps(
                [
                    {
                        "point_id": "point-a",
                        "latitude": 51.5,
                        "longitude": -0.1,
                        "series_id": SERIES_ID,
                    }
                ]
            ),
            "0",
            "BINDING_KEYS_INVALID",
        ),
        (
            json.dumps([DEFAULT_BINDING, DEFAULT_BINDING]),
            "0",
            "BINDING_POINT_ID_DUPLICATE",
        ),
        (
            json.dumps([{**DEFAULT_BINDING, "latitude": float("nan")}]),
            "0",
            "BINDINGS_JSON_INVALID",
        ),
        (
            json.dumps([DEFAULT_BINDING]).replace("51.5", "1e999", 1),
            "0",
            "BINDING_COORDINATES_INVALID",
        ),
        (json.dumps([DEFAULT_BINDING]), "0,7", "INVALID_STEPS"),
    ],
)
def test_invalid_input_is_refused_before_client_or_output_creation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    raw_bindings: str,
    steps: str,
    expected_code: str,
) -> None:
    bindings = _write_bindings(tmp_path / "bindings.json", raw_bindings)

    def forbidden_client(*args, **kwargs):
        raise AssertionError("client must not be constructed")

    monkeypatch.setattr(ingest, "EcmwfOpenDataClient", forbidden_client)
    output = tmp_path / "never-created"

    assert ingest.main(_args(bindings=bindings, output_dir=output, steps=steps)) == 2

    error = json.loads(capsys.readouterr().err)
    assert error["code"] == expected_code
    assert error["output_dir"] is None
    assert error["fields_archived"] == 0
    assert not output.exists()


def test_existing_output_directory_is_never_reused(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "capture"
    output.mkdir()
    marker = output / "keep.txt"
    marker.write_text("keep this", encoding="utf-8")
    bindings = _write_bindings(tmp_path / "bindings.json", [DEFAULT_BINDING])
    _install_capture(monkeypatch)

    assert ingest.main(_args(bindings=bindings, output_dir=output)) == 2

    error = json.loads(capsys.readouterr().err)
    assert error["code"] == "OUTPUT_DIR_EXISTS"
    assert marker.read_text(encoding="utf-8") == "keep this"
    assert list(output.iterdir()) == [marker]


def test_capture_failure_reports_partial_archive_without_db_or_secrets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    db_url = "postgresql://operator:supersecret@db.internal/eurogas"
    _install_capture(
        monkeypatch,
        fail_step=6,
        fail_message=f"provider token=supersecret url={db_url}",
    )
    _forbid_db(monkeypatch)
    bindings = _write_bindings(tmp_path / "bindings.json", [DEFAULT_BINDING])
    output = tmp_path / "capture"

    assert (
        ingest.main(
            _args(
                bindings=bindings,
                output_dir=output,
                steps="0,6",
                dry_run=False,
                database_url=db_url,
            )
        )
        == 2
    )

    captured = capsys.readouterr()
    error = json.loads(captured.err)
    assert error["code"] == "INGESTION_FAILED"
    assert error["type"] == "RuntimeError"
    assert error["fields_received"] == 1
    assert error["fields_decoded"] == 1
    assert error["fields_archived"] == 1
    assert error["fields_persisted"] == 0
    assert error["database"] == "not_attempted"
    assert error["artifacts_complete"] is False
    assert error["partial_artifacts"] is True
    assert error["hashes"][0]["step_hours"] == 0
    assert (output / "step_000.grib2").read_bytes() == _grib_bytes(0)
    assert (output / "step_000.json").is_file()
    assert not (output / "step_006.grib2").exists()
    for secret in ("supersecret", "postgresql://", "db.internal"):
        assert secret not in captured.err
        assert secret not in captured.out


def test_persist_appends_all_steps_in_one_outer_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _sqlite_engine()
    _seed_identity(engine)
    _use_real_sqlite(monkeypatch, engine)
    captured = (_captured(0, temperature=5.0), _captured(6, temperature=7.5))
    progress = ingest._Progress()
    commits = []

    def on_commit(connection) -> None:
        commits.append(connection)

    event.listen(engine, "commit", on_commit)
    try:
        summaries = ingest._persist(
            EXPLICIT_URL,
            captured,
            (_binding_row(),),
            INGESTED,
            progress,
        )
    finally:
        event.remove(engine, "commit", on_commit)

    assert progress.database == "committed"
    assert len(commits) == 1
    assert [(summary.rows_seen, summary.inserted, summary.duplicates) for summary in summaries] == [
        (1, 1, 0),
        (1, 1, 0),
    ]
    with Session(engine) as session:
        rows = list(
            session.scalars(
                select(ForecastObservationRecord).order_by(
                    ForecastObservationRecord.forecast_valid_start
                )
            )
        )
    assert [(row.horizon, row.value) for row in rows] == [("0h", 5.0), ("6h", 7.5)]
    assert [row.provenance["grib_sha256"] for row in rows] == [
        hashlib.sha256(_grib_bytes(0)).hexdigest(),
        hashlib.sha256(_grib_bytes(6)).hexdigest(),
    ]
    assert {row.provenance["point"]["point_id"] for row in rows} == {"point-a"}


def test_persist_rolls_back_earlier_step_when_a_later_step_conflicts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = _sqlite_engine()
    _seed_identity(engine)
    _use_real_sqlite(monkeypatch, engine)
    first = _captured(0, temperature=5.0)
    conflict = ingest._Captured(
        transport=first.transport,
        decoded=_decoded(first.transport, 6.0),
        step_hours=0,
    )
    progress = ingest._Progress()
    commits = []

    def on_commit(connection) -> None:
        commits.append(connection)

    event.listen(engine, "commit", on_commit)
    try:
        with pytest.raises(EcmwfForecastConflict):
            ingest._persist(
                EXPLICIT_URL,
                (first, conflict),
                (_binding_row(),),
                INGESTED,
                progress,
            )
    finally:
        event.remove(engine, "commit", on_commit)

    assert progress.database == "failed"
    assert commits == []
    with Session(engine) as session:
        assert list(session.scalars(select(ForecastObservationRecord))) == []
