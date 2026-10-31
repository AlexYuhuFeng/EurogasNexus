"""CSV renditions of report reads, for spreadsheets, ERP and ETRM loaders.

A report route accepts ``format=csv`` and returns the same rows as ``text/csv`` (UTF-8 with a
byte-order mark, so Excel opens non-ASCII text correctly), with a stable header order and a
file name that carries the report and the date. Nested values are written as JSON text, and
the response says which rows it holds in ``X-Eurogas-Report-Rows``.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

from fastapi.responses import Response


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict, tuple)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    if isinstance(value, float):
        return repr(value)
    return str(value)


def csv_response(rows: Iterable[Mapping[str, Any]], *, report: str) -> Response:
    """The rows as a CSV download; columns in first-seen order across all rows."""

    rows = list(rows)
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    buffer = io.StringIO()
    buffer.write("﻿")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_cell(row.get(column)) for column in columns])
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%MZ")
    return Response(
        content=buffer.getvalue().encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="eurogas-nexus-{report}-{stamp}.csv"',
            "X-Eurogas-Report-Rows": str(len(rows)),
        },
    )


REPORT_FORMAT_PATTERN = "^(json|csv|xlsx|pdf)$"

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def report_response(
    rows: Iterable[Mapping[str, Any]],
    *,
    report: str,
    format: str,
    title: str | None = None,
    about: list[tuple[str, str]] | None = None,
) -> Response:
    """The rows as CSV, Excel (XLSX) or PDF, with the same figures in each."""

    if format == "csv":
        return csv_response(rows, report=report)
    from eurogas_nexus.core.report_files import pdf_bytes, xlsx_bytes

    rows = list(rows)
    now = datetime.now(UTC)
    stamp = now.strftime("%Y%m%dT%H%MZ")
    heading = title or report.replace("-", " ").capitalize()
    details = [
        ("Report", heading),
        ("Generated (UTC)", now.strftime("%Y-%m-%d %H:%M")),
        *(about or []),
    ]
    if format == "xlsx":
        content, media, suffix = xlsx_bytes(rows, sheet=heading, about=details), _XLSX, "xlsx"
    elif format == "pdf":
        subtitle = " · ".join(f"{key}: {value}" for key, value in details[1:])
        content = pdf_bytes(rows, title=heading, subtitle=subtitle, footer=heading)
        media, suffix = "application/pdf", "pdf"
    else:  # pragma: no cover - routes validate the pattern
        raise ValueError(f"unsupported report format {format!r}")
    return Response(
        content=content,
        media_type=media,
        headers={
            "Content-Disposition": (
                f'attachment; filename="eurogas-nexus-{report}-{stamp}.{suffix}"'
            ),
            "X-Eurogas-Report-Rows": str(len(rows)),
        },
    )
