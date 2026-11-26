"""CSV renditions of report reads, for spreadsheets, ERP and ETRM loaders.

A report route accepts ``format=csv`` and returns the same rows as ``text/csv`` (UTF-8 with a
byte-order mark, so Excel opens non-ASCII text correctly), with a stable header order and a
file name that carries the report and the date. Nested values are written as JSON text, and
the response says which rows it holds in ``X-Eurogas-Report-Rows``.

GOV-1 (P6): every file applies the export decision to the licensed source families its rows
were read from (``application/licensed_use.file_decision``). A denied file is refused with
403 ``export_denied``; a restricted file is delivered marked ``X-Eurogas-Export-Decision:
restricted`` with its restrictions and licensed families in headers and, in XLSX and PDF,
in the file's own description; the file write is counted as an export in the usage record.
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from fastapi.responses import Response


def _cell(value: Any) -> str:
    from eurogas_nexus.core.csv_safety import neutralise

    if value is None:
        return ""
    if isinstance(value, (list, dict, tuple)):
        return neutralise(json.dumps(value, sort_keys=True, ensure_ascii=False))
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, (int, bool)):
        return str(value)
    # Text from outside sources is never run as a spreadsheet formula (security review M4).
    return neutralise(str(value))


def _export_decision(file_format: str):
    """The export decision for this request's file; refuses a denied one (GOV-1, P6)."""

    from eurogas_nexus.application.licensed_use import file_decision
    from eurogas_nexus.governance.entitlement import ExportDecision
    from eurogas_nexus.governance.usage import current_meter

    meter = current_meter()
    decision = file_decision(meter.families if meter is not None else ())
    if decision.decision is ExportDecision.DENIED:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "export_denied",
                "message": (
                    "This file would carry licensed data whose export terms are not "
                    "registered (fail-closed export policy)."
                ),
                "licensed_families": list(decision.licensed_families),
                "research_only": True,
                "human_review_required": True,
            },
        )
    if meter is not None:
        meter.export_format = file_format
    return decision


def _decision_headers(decision) -> dict[str, str]:
    headers = {"X-Eurogas-Export-Decision": decision.decision.value}
    if decision.licensed_families:
        headers["X-Eurogas-Licensed-Sources"] = ",".join(decision.licensed_families)
    if decision.restrictions:
        headers["X-Eurogas-Export-Restrictions"] = ",".join(decision.restrictions)
    return headers


def _decision_about(decision) -> list[tuple[str, str]]:
    if not decision.licensed_families:
        return []
    use = (
        "Internal use only; not for redistribution outside the firm"
        if decision.restrictions
        else "Redistribution allowed by the licence"
    )
    return [("Licensed data", ", ".join(decision.licensed_families)), ("Use", use)]


def csv_response(
    rows: Iterable[Mapping[str, Any]],
    *,
    report: str,
    columns: Sequence[str] | None = None,
) -> Response:
    """The rows as a CSV download; columns in first-seen order across all rows.

    ``columns`` fixes the header instead (DATA-1, Power Query): those columns in that order,
    even when there are no rows, so a refreshed query keeps its shape.
    """

    rows = list(rows)  # built first: the rows' reads are what the decision is about
    decision = _export_decision("csv")
    if columns is not None:
        columns = list(columns)
    else:
        columns = []
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
            **_decision_headers(decision),
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
    decision = _export_decision(format)
    now = datetime.now(UTC)
    stamp = now.strftime("%Y%m%dT%H%MZ")
    heading = title or report.replace("-", " ").capitalize()
    details = [
        ("Report", heading),
        ("Generated (UTC)", now.strftime("%Y-%m-%d %H:%M")),
        *(about or []),
        *_decision_about(decision),
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
            **_decision_headers(decision),
        },
    )
