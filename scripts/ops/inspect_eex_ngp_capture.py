"""Inspect one local EEX TTF NGP capture file and print a JSON report.

This is the operator-facing half of the read-only EEX NGP capture-inspection seam. It reads one
explicit local file, never downloads anything, never contacts EEX, never writes a database and
never touches source activation, entitlement or certification records.

Typical invocation from the source checkout (with ``src`` on ``PYTHONPATH``)::

    python scripts/ops/inspect_eex_ngp_capture.py \\
        --input /path/to/TTF_NGP_15_Mins.csv \\
        --retrieved-at 2026-05-29T17:05:00+02:00

Exit codes:

* ``0`` — the payload was inspected and every data row passed the pure EEX parser;
* ``1`` — inspection refused the payload or at least one row was rejected;
* ``2`` — invalid arguments, a missing input file or an unreadable input file.

All output is JSON on stdout, including refusals; no traceback is printed. Even a successful
report states that canonical publication is prohibited.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from eurogas_nexus.ingestion.eex_ngp_capture import (
    MAX_CAPTURE_BYTES,
    EexNgpCaptureError,
    inspect_eex_ngp_capture,
    serialize_capture_report,
)

PROG = "inspect_eex_ngp_capture.py"
_EXIT_OK = 0
_EXIT_REFUSED = 1
_EXIT_USAGE = 2


class _UsageError(Exception):
    """Internal: command-line usage is invalid."""


class _FileReadError(Exception):
    """Internal: the local input file could not be read under a stable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class _Parser(argparse.ArgumentParser):
    """Argument parser that raises instead of printing a usage traceback."""

    def error(self, message: str) -> None:
        raise _UsageError(message)


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog=PROG,
        description=(
            "Read one operator-supplied local EEX TTF NGP CSV and print a byte-preserving "
            "JSON inspection report. This command performs no download and no persistence."
        ),
    )
    parser.add_argument(
        "--input",
        dest="input_path",
        required=True,
        help="Path to one local EEX TTF NGP CSV file (no URL or download is supported).",
    )
    parser.add_argument(
        "--retrieved-at",
        dest="retrieved_at",
        required=True,
        help="Explicit aware ISO-8601 retrieval instant, e.g. 2026-05-29T17:05:00+02:00.",
    )
    return parser


def _parse_retrieved_at(value: str) -> datetime:
    """Parse the operator timestamp syntactically; the module enforces an explicit offset."""

    candidate = value.strip()
    if not candidate:
        raise _UsageError("--retrieved-at must not be blank.")
    try:
        return datetime.fromisoformat(candidate)
    except ValueError as error:
        raise _UsageError(
            "--retrieved-at must be an ISO-8601 timestamp with an explicit UTC offset."
        ) from error


def _read_local_file(path: Path) -> bytes:
    """Read at most ``MAX_CAPTURE_BYTES + 1`` bytes; never slurp an unbounded file."""

    try:
        with path.open("rb") as handle:
            data = handle.read(MAX_CAPTURE_BYTES + 1)
    except FileNotFoundError as error:
        raise _FileReadError(
            "input_not_found", f"input file does not exist: {path}"
        ) from error
    except (OSError, ValueError) as error:
        raise _FileReadError(
            "input_read_error", f"input file could not be read: {path}"
        ) from error
    if len(data) > MAX_CAPTURE_BYTES:
        raise _FileReadError(
            "payload_too_large",
            (
                f"input file exceeds the {MAX_CAPTURE_BYTES}-byte inspection limit; only "
                "the bounded prefix was read."
            ),
        )
    return data


def _emit(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True))


def _emit_error(
    code: str,
    message: str,
    *,
    exit_code: int,
    parser_code: str | None = None,
) -> int:
    error: dict[str, Any] = {
        "code": code,
        "message": " ".join(message.split())[:600],
    }
    if parser_code is not None:
        error["parser_code"] = parser_code
    _emit({"ok": False, "error": error})
    return exit_code


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except _UsageError as error:
        return _emit_error("invalid_arguments", str(error), exit_code=_EXIT_USAGE)

    try:
        retrieved_at = _parse_retrieved_at(args.retrieved_at)
    except _UsageError as error:
        return _emit_error("invalid_retrieved_at", str(error), exit_code=_EXIT_USAGE)

    try:
        raw_bytes = _read_local_file(Path(args.input_path))
    except _FileReadError as error:
        exit_code = _EXIT_REFUSED if error.code == "payload_too_large" else _EXIT_USAGE
        return _emit_error(error.code, error.message, exit_code=exit_code)

    try:
        report = inspect_eex_ngp_capture(raw_bytes, retrieved_at_utc=retrieved_at)
    except EexNgpCaptureError as error:
        return _emit_error(
            error.code,
            error.message,
            exit_code=_EXIT_REFUSED,
            parser_code=error.parser_code,
        )
    except Exception:  # noqa: BLE001 - CLI must not print a traceback to the operator
        return _emit_error(
            "inspection_failed",
            "the capture inspection failed unexpectedly; no traceback or payload was echoed.",
            exit_code=_EXIT_REFUSED,
        )

    try:
        print(serialize_capture_report(report))
    except EexNgpCaptureError as error:
        return _emit_error(error.code, error.message, exit_code=_EXIT_REFUSED)
    except Exception:  # noqa: BLE001 - a CLI refusal must never become a raw traceback
        return _emit_error(
            "inspection_failed",
            "the capture report could not be emitted safely; no traceback was printed.",
            exit_code=_EXIT_REFUSED,
        )
    return _EXIT_OK if report["ok"] else _EXIT_REFUSED


if __name__ == "__main__":
    raise SystemExit(main())
