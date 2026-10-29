#!/usr/bin/env python3
"""Bounded operator ingestion for one explicit ECMWF IFS 0p25 oper 2t run.

The command captures an exact, explicitly requested run/cycle and step set from
ECMWF's official open-data origin, decodes each instantaneous 2t field, preserves
the GRIB2 bytes and decoder/transport metadata, and only then appends the decoded
points through the existing forecast repository.

Every point requires an explicit JSON binding with its own latitude, longitude,
series and canonical entity.  No geography, series, entity or mapping is inferred.
The command does not create schema, identities, mappings, certifications or source
activation, and it does not read provider credentials.

The repository remains the authority for approved existing identities.  This CLI
only supplies the explicit `EcmwfForecastPointBinding` values.  Dry-run captures
and decodes exact fields but never resolves or touches the database.

No demand-model, HDD/CDD or regional-aggregate claim is made by this command.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import re
import sys
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from eurogas_nexus.db.repositories.ecmwf_forecasts import (
        EcmwfForecastInsertSummary,
    )

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from eurogas_nexus.ingestion.ecmwf_grib import (  # noqa: E402
    EcmwfDecodedField,
    EcmwfGribDecoder,
)
from eurogas_nexus.ingestion.ecmwf_open_data import (  # noqa: E402
    CYCLE_HOURS,
    MIN_RUN_DATE,
    STEP_HOURS,
    EcmwfField,
    EcmwfLocation,
    EcmwfOpenDataClient,
    EcmwfOpenDataRequest,
    EcmwfSource,
)

SOURCE = "ecmwf"
RESEARCH_BASIS = (
    "explicit_point_bindings_instantaneous_2t_no_demand_or_regional_aggregate"
)
CAPTURE_SCHEMA = "ecmwf-forecast-operations-capture/v1"
MIN_BINDINGS = 1
MAX_BINDINGS = 64
MAX_BINDINGS_BYTES = 1024 * 1024
MAX_FIELDS = 12
_BINDING_KEYS = frozenset(
    {"point_id", "latitude", "longitude", "series_id", "entity_id"}
)
_SAFE_CODE_RE = re.compile(r"^[A-Za-z0-9_]{1,96}$")
_SAFE_TYPE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,95}$")


class CliError(RuntimeError):
    """Operator-safe failure carrying only a stable code."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class _Parser(argparse.ArgumentParser):
    """Argument parser that never echoes raw arguments or usage on failure."""

    def error(self, message: str) -> None:
        _ = message
        raise CliError("INVALID_ARGUMENTS")


@dataclass(frozen=True)
class _BindingRow:
    point_id: str
    latitude: float
    longitude: float
    series_id: str
    entity_id: str


@dataclass(frozen=True)
class _Plan:
    run_date: date
    cycle_hour: int
    steps: tuple[int, ...]
    bindings: tuple[_BindingRow, ...]
    output_dir: Path
    requests: tuple[EcmwfOpenDataRequest, ...]


@dataclass(frozen=True)
class _Captured:
    transport: EcmwfField
    decoded: EcmwfDecodedField
    step_hours: int


@dataclass
class _Progress:
    dry_run: bool | None = None
    run_date: date | None = None
    cycle_hour: int | None = None
    steps: tuple[int, ...] = ()
    binding_count: int = 0
    output_dir: Path | None = None
    fields_received: int = 0
    fields_decoded: int = 0
    fields_archived: int = 0
    fields_persisted: int = 0
    rows_seen: int = 0
    rows_inserted: int = 0
    rows_duplicate: int = 0
    hashes: list[dict[str, object]] = dataclass_field(default_factory=list)
    database: str = "not_attempted"
    ingested_at_utc: datetime | None = None


def _json_default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def _code(exc: BaseException) -> str:
    code = getattr(exc, "code", None)
    if isinstance(code, str) and _SAFE_CODE_RE.fullmatch(code):
        return code
    return "INGESTION_FAILED"


def _type_name(exc: BaseException) -> str:
    name = type(exc).__name__
    return name if _SAFE_TYPE_RE.fullmatch(name) else "Exception"


def _iso_or_none(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _emit(payload: dict[str, object], *, error: bool = False) -> None:
    stream = sys.stderr if error else sys.stdout
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        default=_json_default,
        allow_nan=False,
    )
    stream.write(encoded + "\n")


def _success_payload(plan: _Plan, progress: _Progress) -> dict[str, object]:
    return {
        "status": "ok",
        "dry_run": bool(progress.dry_run),
        "persisted": progress.database == "committed",
        "source": SOURCE,
        "research_basis": RESEARCH_BASIS,
        "run_date": plan.run_date.isoformat(),
        "cycle_hour": plan.cycle_hour,
        "steps": list(plan.steps),
        "bindings": len(plan.bindings),
        "fields_requested": len(plan.steps),
        "fields_received": progress.fields_received,
        "fields_decoded": progress.fields_decoded,
        "fields_archived": progress.fields_archived,
        "fields_persisted": progress.fields_persisted,
        "rows_seen": progress.rows_seen,
        "inserted": progress.rows_inserted,
        "duplicates": progress.rows_duplicate,
        "hashes": list(progress.hashes),
        "output_dir": str(plan.output_dir),
        "artifacts_complete": progress.fields_archived == len(plan.steps),
        "partial_artifacts": progress.fields_archived != len(plan.steps),
        "database": progress.database,
        "ingested_at_utc": _iso_or_none(progress.ingested_at_utc),
    }


def _error_payload(progress: _Progress, exc: BaseException) -> dict[str, object]:
    artifacts_complete = bool(progress.steps) and (
        progress.fields_archived == len(progress.steps)
    )
    return {
        "status": "error",
        "code": _code(exc),
        "type": _type_name(exc),
        "dry_run": progress.dry_run,
        "source": SOURCE,
        "research_basis": RESEARCH_BASIS,
        "run_date": None if progress.run_date is None else progress.run_date.isoformat(),
        "cycle_hour": progress.cycle_hour,
        "steps": list(progress.steps),
        "bindings": progress.binding_count,
        "fields_requested": len(progress.steps),
        "fields_received": progress.fields_received,
        "fields_decoded": progress.fields_decoded,
        "fields_archived": progress.fields_archived,
        "fields_persisted": progress.fields_persisted,
        "rows_seen": progress.rows_seen,
        "inserted": progress.rows_inserted,
        "duplicates": progress.rows_duplicate,
        "hashes": list(progress.hashes),
        "output_dir": (
            None if progress.output_dir is None else str(progress.output_dir)
        ),
        "artifacts_complete": artifacts_complete,
        "partial_artifacts": progress.output_dir is not None and not artifacts_complete,
        "database": progress.database,
        "ingested_at_utc": _iso_or_none(progress.ingested_at_utc),
    }


def _parse_run_date(raw: str) -> date:
    if not isinstance(raw, str) or not raw or raw != raw.strip():
        raise CliError("INVALID_RUN_DATE")
    try:
        value = date.fromisoformat(raw)
    except (TypeError, ValueError):
        raise CliError("INVALID_RUN_DATE") from None
    if value.isoformat() != raw:
        raise CliError("INVALID_RUN_DATE")
    if value < MIN_RUN_DATE or value > datetime.now(UTC).date():
        raise CliError("RUN_DATE_OUT_OF_BOUNDS")
    return value


def _parse_cycle_hour(raw: str) -> int:
    if (
        not isinstance(raw, str)
        or not raw
        or raw != raw.strip()
        or not raw.isascii()
        or not raw.isdigit()
        or len(raw) > 2
    ):
        raise CliError("INVALID_CYCLE_HOUR")
    value = int(raw)
    if value not in CYCLE_HOURS:
        raise CliError("INVALID_CYCLE_HOUR")
    return value


def _parse_steps(raw: str) -> tuple[int, ...]:
    if not isinstance(raw, str) or not raw or raw != raw.strip():
        raise CliError("INVALID_STEPS")
    parts = raw.split(",")
    if not 1 <= len(parts) <= MAX_FIELDS:
        raise CliError("INVALID_STEPS")
    values: list[int] = []
    for part in parts:
        text = part.strip()
        if not text or not text.isascii() or not text.isdigit():
            raise CliError("INVALID_STEPS")
        try:
            value = int(text)
        except ValueError:
            raise CliError("INVALID_STEPS") from None
        if value not in STEP_HOURS:
            raise CliError("INVALID_STEPS")
        values.append(value)
    if len(set(values)) != len(values):
        raise CliError("INVALID_STEPS")
    return tuple(sorted(values))


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant {value}")


def _binding_text(value: object, code: str, *, maximum: int | None = None) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or any(ord(character) < 32 for character in value)
    ):
        raise CliError(code)
    if maximum is not None and len(value) > maximum:
        raise CliError(code)
    return value


def _coordinate(value: object, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CliError("BINDING_COORDINATES_INVALID")
    try:
        number = float(value)
    except (OverflowError, ValueError):
        raise CliError("BINDING_COORDINATES_INVALID") from None
    if not math.isfinite(number) or not low <= number <= high:
        raise CliError("BINDING_COORDINATES_INVALID")
    return number


def _load_bindings(raw_path: str) -> tuple[_BindingRow, ...]:
    if not isinstance(raw_path, str) or not raw_path:
        raise CliError("BINDINGS_NOT_FILE")
    try:
        path = Path(raw_path)
        if not path.is_file():
            raise CliError("BINDINGS_NOT_FILE")
        if path.stat().st_size > MAX_BINDINGS_BYTES:
            raise CliError("BINDINGS_TOO_LARGE")
        raw = path.read_bytes()
    except CliError:
        raise
    except (OSError, ValueError):
        raise CliError("BINDINGS_READ_FAILED") from None

    try:
        document = json.loads(
            raw.decode("utf-8"),
            parse_constant=_reject_json_constant,
            object_pairs_hook=_unique_object,
        )
    except (UnicodeDecodeError, TypeError, ValueError):
        raise CliError("BINDINGS_JSON_INVALID") from None

    if not isinstance(document, list):
        raise CliError("BINDINGS_JSON_INVALID")
    if not MIN_BINDINGS <= len(document) <= MAX_BINDINGS:
        raise CliError("BINDINGS_COUNT_INVALID")

    rows: list[_BindingRow] = []
    point_ids: set[str] = set()
    for item in document:
        if not isinstance(item, dict) or set(item) != _BINDING_KEYS:
            raise CliError("BINDING_KEYS_INVALID")
        point_id = _binding_text(
            item["point_id"], "BINDING_POINT_ID_INVALID", maximum=64
        )
        if point_id in point_ids:
            raise CliError("BINDING_POINT_ID_DUPLICATE")
        point_ids.add(point_id)
        series_id = _binding_text(item["series_id"], "BINDING_SERIES_INVALID")
        entity_id = _binding_text(item["entity_id"], "BINDING_ENTITY_INVALID")
        latitude = _coordinate(item["latitude"], -90.0, 90.0)
        longitude = _coordinate(item["longitude"], -180.0, 180.0)
        rows.append(
            _BindingRow(
                point_id=point_id,
                latitude=latitude,
                longitude=longitude,
                series_id=series_id,
                entity_id=entity_id,
            )
        )
    return tuple(rows)


def _parse_output_dir(raw: str) -> Path:
    if not isinstance(raw, str) or not raw or raw != raw.strip() or "\x00" in raw:
        raise CliError("OUTPUT_DIR_INVALID")
    try:
        path = Path(raw)
        if path.is_symlink() or path.exists():
            raise CliError("OUTPUT_DIR_EXISTS")
    except CliError:
        raise
    except (OSError, ValueError):
        raise CliError("OUTPUT_DIR_INVALID") from None
    return path


def _create_output_dir(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise CliError("OUTPUT_DIR_EXISTS") from None
    except OSError:
        raise CliError("OUTPUT_DIR_CREATE_FAILED") from None


def _plan(args: argparse.Namespace, progress: _Progress) -> _Plan:
    run_date = _parse_run_date(args.run_date)
    progress.run_date = run_date
    cycle_hour = _parse_cycle_hour(args.cycle_hour)
    progress.cycle_hour = cycle_hour
    steps = _parse_steps(args.steps)
    progress.steps = steps
    bindings = _load_bindings(args.bindings)
    progress.binding_count = len(bindings)
    output_dir = _parse_output_dir(args.output_dir)

    locations = tuple(
        EcmwfLocation(
            point_id=row.point_id,
            latitude=row.latitude,
            longitude=row.longitude,
        )
        for row in bindings
    )
    requests = tuple(
        EcmwfOpenDataRequest(
            run_date=run_date,
            cycle_hour=cycle_hour,
            step_hours=step,
            locations=locations,
        )
        for step in steps
    )
    return _Plan(
        run_date=run_date,
        cycle_hour=cycle_hour,
        steps=steps,
        bindings=bindings,
        output_dir=output_dir,
        requests=requests,
    )


def _validate_field(field: EcmwfField, request: EcmwfOpenDataRequest) -> None:
    if (
        field.run.source != EcmwfSource.ECMWF
        or field.reference.source != EcmwfSource.ECMWF
    ):
        raise CliError("ECMWF_SOURCE_MISMATCH")
    run_request = field.run.request
    if (
        run_request.run_date != request.run_date
        or run_request.cycle_hour != request.cycle_hour
        or run_request.step_hours != request.step_hours
        or field.reference.run_date != request.run_date
        or field.reference.cycle_hour != request.cycle_hour
        or field.reference.step_hours != request.step_hours
        or field.run.issued_at_utc != request.issued_at_utc
        or field.run.valid_at_utc != request.valid_at_utc
        or field.reference.valid_at_utc != request.valid_at_utc
    ):
        raise CliError("ECMWF_RUN_MISMATCH")
    raw = field.grib_bytes
    if not isinstance(raw, bytes) or not raw:
        raise CliError("ECMWF_GRIB_HASH_MISMATCH")
    actual = hashlib.sha256(raw).hexdigest()
    if actual != field.grib_sha256 or actual != field.reference.grib_sha256:
        raise CliError("ECMWF_GRIB_HASH_MISMATCH")


def _hashes(field: EcmwfField) -> dict[str, object]:
    return {
        "request_sha256": field.run.request_sha256,
        "grib_sha256": field.grib_sha256,
        "index_sha256": field.reference.index_sha256,
        "index_row_sha256": field.index.selected.row_sha256,
    }


def _hash_entry(field: EcmwfField, step_hours: int) -> dict[str, object]:
    entry = _hashes(field)
    entry.update(
        {
            "step_hours": step_hours,
            "receipt_completed_at_utc": (
                field.run.receipt_completed_at_utc.isoformat()
            ),
        }
    )
    return entry


def _metadata_document(
    field: EcmwfField,
    decoded: EcmwfDecodedField,
    grib_name: str,
) -> dict[str, object]:
    transport = dataclasses.asdict(field)
    transport.pop("grib_bytes", None)
    return {
        "schema": CAPTURE_SCHEMA,
        "source": field.run.source.value,
        "source_origin": field.run.origin,
        "research_basis": RESEARCH_BASIS,
        "run_date": field.run.request.run_date.isoformat(),
        "cycle_hour": field.run.request.cycle_hour,
        "step_hours": field.run.request.step_hours,
        "valid_at_utc": field.run.valid_at_utc.isoformat(),
        "grib_file": grib_name,
        "grib_size_bytes": len(field.grib_bytes),
        "hashes": _hashes(field),
        "receipt_completed_at_utc": (
            field.run.receipt_completed_at_utc.isoformat()
        ),
        "transport": transport,
        "decoder": dataclasses.asdict(decoded),
    }


def _write_bytes(path: Path, payload: bytes) -> None:
    try:
        with path.open("xb") as handle:
            handle.write(payload)
    except FileExistsError:
        raise CliError("ARTIFACT_EXISTS") from None
    except OSError:
        raise CliError("ARTIFACT_WRITE_FAILED") from None


def _write_json(path: Path, value: object) -> None:
    try:
        text = (
            json.dumps(
                value,
                sort_keys=True,
                indent=2,
                default=_json_default,
                allow_nan=False,
            )
            + "\n"
        )
    except (TypeError, ValueError):
        raise CliError("ARTIFACT_METADATA_INVALID") from None
    _write_bytes(path, text.encode("utf-8"))


def _capture(
    plan: _Plan,
    decoder: EcmwfGribDecoder,
    progress: _Progress,
) -> tuple[_Captured, ...]:
    captured: list[_Captured] = []
    with EcmwfOpenDataClient(source=EcmwfSource.ECMWF) as client:
        for request in plan.requests:
            field = client.retrieve(request)
            progress.fields_received += 1
            _validate_field(field, request)
            step = request.step_hours
            grib_name = f"step_{step:03d}.grib2"
            json_name = f"step_{step:03d}.json"
            _write_bytes(plan.output_dir / grib_name, field.grib_bytes)
            decoded = decoder.decode(field)
            progress.fields_decoded += 1
            _write_json(
                plan.output_dir / json_name,
                _metadata_document(field, decoded, grib_name),
            )
            progress.fields_archived += 1
            progress.hashes.append(_hash_entry(field, step))
            captured.append(
                _Captured(
                    transport=field,
                    decoded=decoded,
                    step_hours=step,
                )
            )
    return tuple(captured)


def _persist(
    explicit_database_url: str | None,
    captured: tuple[_Captured, ...],
    bindings: tuple[_BindingRow, ...],
    ingested_at_utc: datetime,
    progress: _Progress,
) -> tuple[EcmwfForecastInsertSummary, ...]:
    from eurogas_nexus.db.repositories.ecmwf_forecasts import (
        EcmwfForecastPointBinding,
        append_ecmwf_forecast,
    )
    from eurogas_nexus.db.session import get_session_factory, resolve_database_url

    database_url = explicit_database_url.strip() if explicit_database_url else None
    if not database_url:
        database_url = resolve_database_url()
    if not database_url:
        raise CliError("DATABASE_URL_REQUIRED")

    binding_values = tuple(
        EcmwfForecastPointBinding(
            point_id=row.point_id,
            series_id=row.series_id,
            entity_id=row.entity_id,
        )
        for row in bindings
    )

    summaries: list[EcmwfForecastInsertSummary] = []
    progress.database = "attempted"
    try:
        session_factory = get_session_factory(database_url=database_url)
        with session_factory() as session, session.begin():
            for item in captured:
                summaries.append(
                    append_ecmwf_forecast(
                        session,
                        bindings=binding_values,
                        transport=item.transport,
                        decoded=item.decoded,
                        ingested_at_utc=ingested_at_utc,
                    )
                )
    except Exception:
        progress.database = "failed"
        raise
    progress.database = "committed"
    return tuple(summaries)


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit operator surface."""

    parser = _Parser(
        description=(
            "Capture and optionally persist one explicit ECMWF IFS 0p25 oper 2t "
            "run. Every point requires explicit coordinates and existing series/"
            "entity identities. No source is activated by this command."
        )
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help=(
            "Explicit SQLAlchemy URL; otherwise use the existing DB URL "
            "precedence. Ignored with --dry-run."
        ),
    )
    parser.add_argument(
        "--run-date",
        required=True,
        metavar="YYYY-MM-DD",
        help="Explicit UTC run date (2023-01-18 or later; not in the future).",
    )
    parser.add_argument(
        "--cycle-hour",
        required=True,
        help="Explicit ECMWF cycle hour: 0/6/12/18 (00/06/12/18 also accepted).",
    )
    parser.add_argument(
        "--steps",
        required=True,
        help=(
            "One to twelve unique forecast steps in hours, comma-separated, "
            "from 0 to 360 in 3-hour increments."
        ),
    )
    parser.add_argument(
        "--bindings",
        required=True,
        metavar="JSON",
        help=(
            "JSON array of 1-64 objects with exactly point_id, latitude, "
            "longitude, series_id and entity_id. No geography is inferred."
        ),
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        metavar="DIR",
        help=(
            "New non-existing directory for exact GRIB2 and metadata JSON "
            "artifacts; created exclusively and never reused."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Capture and decode only; do not resolve or touch the database.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    progress = _Progress()
    try:
        args = build_parser().parse_args(argv)
        progress.dry_run = bool(args.dry_run)
        plan = _plan(args, progress)
        decoder = EcmwfGribDecoder()
        _create_output_dir(plan.output_dir)
        progress.output_dir = plan.output_dir
        captured = _capture(plan, decoder, progress)
        if len(captured) != len(plan.steps):
            raise CliError("CAPTURE_INCOMPLETE")

        summaries: tuple[EcmwfForecastInsertSummary, ...] = ()
        if args.dry_run:
            progress.database = "not_attempted"
        else:
            ingested_at_utc = datetime.now(UTC)
            latest_receipt = max(
                item.transport.run.receipt_completed_at_utc for item in captured
            )
            if ingested_at_utc < latest_receipt:
                raise CliError("INGESTION_CLOCK_BEFORE_RECEIPT")
            progress.ingested_at_utc = ingested_at_utc
            summaries = _persist(
                args.database_url,
                captured,
                plan.bindings,
                ingested_at_utc,
                progress,
            )
            progress.fields_persisted = len(summaries)
            progress.rows_seen = sum(summary.rows_seen for summary in summaries)
            progress.rows_inserted = sum(
                summary.inserted for summary in summaries
            )
            progress.rows_duplicate = sum(
                summary.duplicates for summary in summaries
            )

        _emit(_success_payload(plan, progress))
        return 0
    except Exception as exc:
        _emit(_error_payload(progress, exc), error=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
