#!/usr/bin/env python3
"""Bounded single-point ECMWF 2t capture/decode; no regional demand claim."""
from __future__ import annotations

import argparse
import dataclasses
import json
import math
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from eurogas_nexus.ingestion.ecmwf_grib import decode_field  # noqa: E402
from eurogas_nexus.ingestion.ecmwf_open_data import (  # noqa: E402
    CYCLE_HOURS,
    STEP_HOURS,
    EcmwfLocation,
    EcmwfOpenDataClient,
    EcmwfOpenDataRequest,
)

LABEL = "single_point_capture"

def _json_default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(type(value).__name__)

def _write(path: Path, payload: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(payload)

def _write_json(path: Path, value: object) -> None:
    payload = json.dumps(value, default=_json_default, indent=2, sort_keys=True) + "\n"
    _write(path, payload.encode("utf-8"))

def _code(exc: Exception) -> str:
    code = getattr(exc, "code", None)
    return code if isinstance(code, str) and code else type(exc).__name__

def _run_date(raw: str) -> date:
    value = date.fromisoformat(raw)
    if value.isoformat() != raw:
        raise ValueError("run date must be ISO YYYY-MM-DD")
    return value

def _steps(raw: str) -> tuple[int, ...]:
    parts = [part.strip() for part in raw.split(",")]
    valid = all(part.isascii() and part.isdigit() for part in parts)
    if not 1 <= len(parts) <= 12 or not valid:
        raise ValueError("steps must be one to twelve comma-separated integers")
    values = [int(part) for part in parts]
    if any(value not in STEP_HOURS for value in values) or len(set(values)) != len(values):
        raise ValueError("steps must be unique reviewed 3-hour steps")
    return tuple(sorted(values))

def _bounds(args: argparse.Namespace) -> tuple[date, int, tuple[int, ...], float, float]:
    cycles = {str(hour) for hour in CYCLE_HOURS}
    if args.cycle_hour not in cycles:
        raise ValueError("cycle hour must be 0/6/12/18")
    cycle_hour = int(args.cycle_hour)
    steps = _steps(args.steps)
    latitude = float(args.latitude)
    longitude = float(args.longitude)
    if not math.isfinite(latitude) or not -90.0 <= latitude <= 90.0:
        raise ValueError("latitude outside [-90, 90]")
    if not math.isfinite(longitude) or not -180.0 <= longitude <= 180.0:
        raise ValueError("longitude outside [-180, 180]")
    return _run_date(args.run_date), cycle_hour, steps, latitude, longitude

class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValueError("invalid arguments")

def _parser() -> argparse.ArgumentParser:
    parser = _Parser(description="Bounded ECMWF single-point 2t capture/decode probe.")
    for name in ("run-date", "cycle-hour", "steps", "latitude", "longitude", "output-dir"):
        parser.add_argument(f"--{name}", required=True)
    return parser

def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
    except Exception as exc:
        print(f"failed count=0 code={_code(exc)} report=")
        return 1
    out = Path(args.output_dir)
    report_path = out / "report.json"
    captured: list[dict[str, object]] = []
    report: dict[str, object] = {"label": LABEL, "complete": False, "artifacts": captured}
    created = False
    try:
        run_date, cycle_hour, steps, latitude, longitude = _bounds(args)
        if out.exists():
            raise FileExistsError("output directory must not exist")
        out.mkdir(parents=True, exist_ok=False)
        created = True
        report.update(
            {
                "run_date": run_date.isoformat(),
                "cycle_hour": cycle_hour,
                "steps": list(steps),
                "latitude": latitude,
                "longitude": longitude,
            }
        )
        location = EcmwfLocation(point_id="probe", latitude=latitude, longitude=longitude)
        with EcmwfOpenDataClient(source="ecmwf") as client:
            for step in steps:
                request = EcmwfOpenDataRequest(
                    run_date=run_date,
                    cycle_hour=cycle_hour,
                    step_hours=step,
                    locations=(location,),
                )
                field = client.retrieve(request)
                decoded = decode_field(field)
                field_doc = dataclasses.asdict(field)
                field_doc.pop("grib_bytes", None)
                grib_name = f"step_{step:03d}.grib2"
                json_name = f"step_{step:03d}.json"
                _write(out / grib_name, field.grib_bytes)
                _write_json(
                    out / json_name,
                    {
                        "label": LABEL,
                        "grib_file": grib_name,
                        "decoded": dataclasses.asdict(decoded),
                        "field": field_doc,
                    },
                )
                captured.append({"step": step, "grib": grib_name, "json": json_name})
        report["complete"] = True
        _write_json(report_path, report)
        print(f"ok count={len(captured)} report={report_path}")
        return 0
    except Exception as exc:
        report["complete"] = False
        report["error"] = {"type": type(exc).__name__, "code": _code(exc)}
        try:
            if created and not report_path.exists():
                _write_json(report_path, report)
        except Exception:
            pass
        print(f"failed count={len(captured)} code={_code(exc)} report={report_path}")
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
