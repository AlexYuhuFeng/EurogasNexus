"""Download one exact official EEX TTF NGP capture and write sanitized metadata.

This is an explicit, operator-invoked acquisition step. It performs one bounded HTTPS download
of the fixed official EEX file, passes the exact bytes to the existing read-only capture
inspector (``inspect_eex_ngp_capture``) and only then writes:

* the raw response bytes to ``--output`` unchanged; and
* a sanitized JSON metadata sidecar (by default ``<output>.metadata.json``).

It does not write a database, grant or infer rights, activate a source, schedule a feed, map
canonical observations or print raw CSV rows. The existing
``scripts/ops/inspect_eex_ngp_capture.py`` command remains the explicit row-level inspection
path; this command's stdout and metadata contain counts and contract blockers only.

Both destination paths are operator-selected, must not exist, must not be symlinks and must be
inside an existing directory. An absolute path outside the repository is allowed when the
operator selects it explicitly. Files are opened with exclusive creation so a path that appears
between validation and writing is still not overwritten.

Exit codes:

* ``0`` — download and capture inspection succeeded; both files were written;
* ``1`` — transport or inspection refused the capture; no capture file was written;
* ``2`` — invalid arguments or an output-path problem; no download was attempted.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

from eurogas_nexus.ingestion.eex_ngp_capture import (
    EexNgpCaptureError,
    inspect_eex_ngp_capture,
)
from eurogas_nexus.ingestion.eex_public_download import (
    EexPublicCapture,
    EexPublicDownloadError,
    fetch_eex_public_capture,
)

PROG = "fetch_eex_public_capture.py"
METADATA_VERSION = "eex-ngp-public-capture/v1"
MAX_MESSAGE_LENGTH = 600

_EXIT_OK = 0
_EXIT_REFUSED = 1
_EXIT_USAGE = 2


class _UsageError(Exception):
    """Internal: invalid command-line usage."""


class _OutputPathError(Exception):
    """Internal: a requested output path cannot be used safely."""

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
            "Download the fixed official EEX TTF NGP CSV under a bounded transport contract, "
            "inspect the exact bytes with the existing capture seam, and write the raw file plus "
            "sanitized metadata. No canonicalisation, database write or source activation."
        ),
    )
    parser.add_argument(
        "--output",
        required=True,
        help=(
            "New path for the exact downloaded CSV bytes. The file must not exist and must not "
            "be a symlink; an explicit absolute path outside the repository is allowed."
        ),
    )
    parser.add_argument(
        "--metadata-output",
        help=(
            "Optional new path for the sanitized JSON metadata. Defaults to "
            "<output>.metadata.json. Must also be a new, non-symlink file."
        ),
    )
    return parser


def _resolve_new_path(value: str, *, role: str) -> Path:
    """Resolve an operator-selected new file path without creating anything.

    Explicit absolute paths are accepted, including outside the repository. The final component
    must not exist or be a symlink, and its parent must already be a directory. Exclusive
    creation at write time closes the remaining race.
    """

    if not value.strip():
        raise _OutputPathError(f"{role}_invalid", f"the {role} path is blank.")
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = Path.cwd() / candidate

    if candidate.is_symlink():
        raise _OutputPathError(
            f"{role}_symlink", f"the {role} path is a symlink and is refused."
        )
    if candidate.exists():
        raise _OutputPathError(
            f"{role}_exists", f"the {role} path already exists and is never overwritten."
        )
    if not candidate.parent.is_dir():
        raise _OutputPathError(
            f"{role}_parent_missing",
            f"the {role} parent directory does not exist or is not a directory.",
        )

    # Resolve the existing parent, not the final component, so the last name remains the
    # operator-selected new file. A symlinked parent is part of the operator's chosen location.
    try:
        parent = candidate.parent.resolve(strict=True)
    except OSError:
        raise _OutputPathError(
            f"{role}_parent_missing",
            f"the {role} parent directory could not be resolved.",
        ) from None
    resolved = parent / candidate.name
    if resolved.is_symlink():
        raise _OutputPathError(
            f"{role}_symlink", f"the {role} path is a symlink and is refused."
        )
    if resolved.exists():
        raise _OutputPathError(
            f"{role}_exists", f"the {role} path already exists and is never overwritten."
        )
    return resolved


def _write_new_bytes(path: Path, data: bytes, *, role: str) -> None:
    """Create exactly one new file; ``xb`` prevents overwrite and symlink-follow races."""

    try:
        with path.open("xb") as handle:
            handle.write(data)
    except FileExistsError:
        raise _OutputPathError(
            f"{role}_exists", f"the {role} path appeared before writing and is refused."
        ) from None
    except OSError:
        raise _OutputPathError(
            f"{role}_write_failed", f"the {role} file could not be written."
        ) from None


def _sanitized_url(value: str) -> str:
    """Keep scheme/host/path for reporting; drop query, fragment and any userinfo."""

    parts = urlsplit(value)
    hostname = parts.hostname or ""
    netloc = hostname if parts.port in (None, 443) else f"{hostname}:{parts.port}"
    return urlunsplit(("https", netloc, parts.path or "/", "", ""))


def _metadata(capture: EexPublicCapture, report: dict[str, Any]) -> dict[str, Any]:
    """Select sanitized fields only; the parser report's row list is deliberately omitted."""

    if report["raw_sha256"] != capture.raw_sha256:
        raise EexNgpCaptureError(
            "inspection_hash_mismatch",
            "the capture inspector returned a hash for different bytes.",
        )
    if report["raw_byte_length"] != capture.raw_byte_length:
        raise EexNgpCaptureError(
            "inspection_length_mismatch",
            "the capture inspector returned a length for different bytes.",
        )

    return {
        "metadata_version": METADATA_VERSION,
        "ok": True,
        "source_system": report["source_system"],
        "source_dataset": report["source_dataset"],
        "source_reference": report["source_reference"],
        "source_page_url": report["source_page_url"],
        "source_file_url": report["source_file_url"],
        "download": {
            "method": "GET",
            "source_url": capture.source_url,
            "final_url": _sanitized_url(capture.final_url),
            "status_code": capture.status_code,
            "content_type": capture.content_type,
            "content_encoding": capture.content_encoding,
            "http_attempts": capture.http_attempts,
            "redirect_count": capture.redirect_count,
            "retrieved_at_utc": capture.retrieved_at_utc.isoformat(),
        },
        "raw_artifact": {
            "raw_sha256": capture.raw_sha256,
            "raw_byte_length": capture.raw_byte_length,
            "hash_scope": "exact_downloaded_bytes",
            "bom_present": report["bom_present"],
            "encoding": report["encoding"],
            "line_endings": "preserved_in_raw_bytes",
        },
        "inspection": {
            "report_version": report["report_version"],
            "inspection_status": report["inspection_status"],
            "row_count": report["row_count"],
            "rejected_row_count": report["rejected_row_count"],
            "blank_lines_skipped": report["blank_lines_skipped"],
        },
        "retrieved_at_utc": report["retrieved_at_utc"],
        "retrieved_at_source": "download_receipt_clock_utc",
        "inspection_retrieved_at_source": report["retrieved_at_source"],
        "canonicalization_allowed": False,
        "canonicalization_reason": report["canonicalization_reason"],
        "executable_quote": False,
        "publication_timezone_proven": False,
        "gas_day_calendar_proven": False,
        "delivery_granularity_proven": False,
        "rights_or_certification_assessed": False,
        "source_activation": False,
        "blockers": report["blockers"],
        "canonical_publication": report["canonical_publication"],
        "timezone_contract": report["timezone_contract"],
        "provenance": report["provenance"],
        "metadata_note": (
            "Raw bytes and sanitized metadata only. No CSV row values are included here; use "
            "the existing inspect_eex_ngp_capture command for explicit row-level inspection. "
            "This step does not establish timezone, gas-day calendar, granularity, freshness, "
            "quality, rights, certification or source activation."
        ),
    }


def _emit(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")))


def _bounded_message(value: object, *, limit: int = MAX_MESSAGE_LENGTH) -> str:
    compact = " ".join(str(value).split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _emit_error(
    code: str,
    message: str,
    *,
    exit_code: int,
    rejected_row_count: int | None = None,
    rejection_reasons: list[str] | None = None,
) -> int:
    error: dict[str, Any] = {
        "code": code,
        "message": _bounded_message(message),
    }
    if rejected_row_count is not None:
        error["rejected_row_count"] = rejected_row_count
    if rejection_reasons:
        error["rejection_reasons"] = rejection_reasons
    _emit({"ok": False, "error": error})
    return exit_code


def main(
    argv: Sequence[str] | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
    clock: Callable[[], datetime] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> int:
    """Run the bounded acquisition CLI; optional hooks exist for deterministic tests."""

    parser = _build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except _UsageError as error:
        return _emit_error("invalid_arguments", str(error), exit_code=_EXIT_USAGE)

    try:
        output_path = _resolve_new_path(args.output, role="output")
        metadata_value = args.metadata_output or f"{output_path}.metadata.json"
        metadata_path = _resolve_new_path(metadata_value, role="metadata_output")
        if output_path == metadata_path:
            raise _OutputPathError(
                "metadata_output_conflict",
                "the metadata output must be a different path from the raw output.",
            )
    except _OutputPathError as error:
        return _emit_error(error.code, error.message, exit_code=_EXIT_USAGE)

    try:
        capture = fetch_eex_public_capture(
            transport=transport,
            clock=clock,
            sleep=sleep,
        )
    except EexPublicDownloadError as error:
        return _emit_error(error.code, error.message, exit_code=_EXIT_REFUSED)
    except Exception:  # noqa: BLE001 - operator CLI must not print a traceback
        return _emit_error(
            "download_failed",
            "the bounded download failed unexpectedly; no response body was echoed.",
            exit_code=_EXIT_REFUSED,
        )

    try:
        report = inspect_eex_ngp_capture(
            capture.raw_bytes,
            retrieved_at_utc=capture.retrieved_at_utc,
        )
    except EexNgpCaptureError as error:
        return _emit_error(error.code, error.message, exit_code=_EXIT_REFUSED)
    except Exception:  # noqa: BLE001 - operator CLI must not print a traceback
        return _emit_error(
            "inspection_failed",
            "the capture inspection failed unexpectedly; no payload was echoed.",
            exit_code=_EXIT_REFUSED,
        )

    if not report["ok"]:
        reasons = sorted(
            {
                str(item.get("reason"))
                for item in report.get("rejections", [])
                if isinstance(item, dict) and item.get("reason")
            }
        )
        return _emit_error(
            "capture_rejected",
            (
                "the downloaded capture contains rows the existing parser refused; no raw or "
                "metadata file was written."
            ),
            exit_code=_EXIT_REFUSED,
            rejected_row_count=report["rejected_row_count"],
            rejection_reasons=reasons,
        )

    try:
        metadata = _metadata(capture, report)
        metadata_bytes = json.dumps(
            metadata,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        _write_new_bytes(output_path, capture.raw_bytes, role="output")
        _write_new_bytes(metadata_path, metadata_bytes, role="metadata_output")
    except EexNgpCaptureError as error:
        return _emit_error(error.code, error.message, exit_code=_EXIT_REFUSED)
    except _OutputPathError as error:
        return _emit_error(error.code, error.message, exit_code=_EXIT_USAGE)
    except Exception:  # noqa: BLE001 - a refused write must not become a traceback
        return _emit_error(
            "output_failed",
            "the capture could not be written safely; no payload was echoed.",
            exit_code=_EXIT_USAGE,
        )

    _emit(metadata)
    return _EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
