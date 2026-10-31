"""Excel (XLSX) and PDF renditions of report rows, with no third-party dependency.

Desks hand reports on in the formats the rest of the firm reads: Excel for the middle
office, finance and the risk models, and PDF for sign-off packs, committee papers and the
audit file. Both writers take the same rows the JSON and CSV reads return, so every format
shows the same figures.

XLSX
    One sheet of data (bold, frozen header row, auto-filter, numbers stored as numbers with a
    thousands separator, sensible column widths) and an ``About`` sheet carrying the report
    name, the as-of instant, who generated it and the standing caveat. Office Open XML written
    directly (inline strings), which Excel, LibreOffice, Numbers and Google Sheets all open.
PDF
    A4 landscape, Helvetica, the header repeated on every page, numbers right-aligned, and a
    footer with the report, the generation time, the caveat and "page n of m". The standard
    PDF fonts carry Latin-1 only, so other characters (for example Chinese names) print as
    ``?``; the XLSX keeps them exactly. Wide reports shrink the type down to 6 pt and then
    shorten the longest cells, marking the cut with ``..``.
"""

from __future__ import annotations

import io
import json
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from typing import Any
from xml.sax.saxutils import escape

CAVEAT = "Decision support from Eurogas Nexus. Not the books and records of the firm."


def columns_of(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Column names in first-seen order across all rows."""

    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    return columns


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (list, dict, tuple)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _display_number(value: float) -> str:
    if isinstance(value, int) or float(value).is_integer() and abs(value) >= 1000:
        return f"{value:,.0f}"
    magnitude = abs(value)
    if magnitude >= 1000:
        return f"{value:,.1f}"
    if magnitude >= 1:
        return f"{value:,.2f}"
    return f"{value:.4g}"


# --------------------------------------------------------------------------------------- XLSX


def _column_letter(index: int) -> str:
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def _sheet_xml(header: list[str], body: list[list[Any]], *, frozen: bool) -> str:
    widths = [len(name) for name in header]
    for row in body:
        for index, value in enumerate(row):
            shown = _display_number(value) if _is_number(value) else _text(value)
            widths[index] = max(widths[index], min(len(shown), 60))
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
    ]
    if frozen and header:
        parts.append(
            '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" '
            'activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        )
    if header:
        parts.append("<cols>")
        for index, width in enumerate(widths):
            parts.append(
                f'<col min="{index + 1}" max="{index + 1}" width="{min(width + 3, 64)}" '
                'customWidth="1"/>'
            )
        parts.append("</cols>")
    parts.append("<sheetData>")
    for row_index, row in enumerate([header, *body], start=1):
        parts.append(f'<row r="{row_index}">')
        for col_index, value in enumerate(row):
            ref = f"{_column_letter(col_index)}{row_index}"
            if row_index == 1 and frozen:
                parts.append(
                    f'<c r="{ref}" t="inlineStr" s="1"><is><t>{escape(_text(value))}</t></is></c>'
                )
            elif _is_number(value):
                style = "3" if isinstance(value, int) else "2"
                parts.append(f'<c r="{ref}" s="{style}"><v>{value!r}</v></c>')
            elif isinstance(value, bool):
                parts.append(f'<c r="{ref}" t="b"><v>{int(value)}</v></c>')
            elif value is None or value == "":
                continue
            else:
                text = escape(_text(value))
                parts.append(
                    f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'
                )
        parts.append("</row>")
    parts.append("</sheetData>")
    if frozen and header and body:
        last = f"{_column_letter(len(header) - 1)}{len(body) + 1}"
        parts.append(f'<autoFilter ref="A1:{last}"/>')
    parts.append("</worksheet>")
    return "".join(parts)


_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
    '<numFmts count="1"><numFmt numFmtId="164" formatCode="#,##0.00"/></numFmts>'
    '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
    '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
    '<fills count="2"><fill><patternFill patternType="none"/></fill>'
    '<fill><patternFill patternType="gray125"/></fill></fills>'
    '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
    '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
    '<cellXfs count="4">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="3" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    "</cellXfs></styleSheet>"
)


def xlsx_bytes(
    rows: Iterable[Mapping[str, Any]],
    *,
    sheet: str,
    about: Sequence[tuple[str, str]] = (),
) -> bytes:
    """An XLSX workbook: the rows on ``sheet`` and the report metadata on ``About``."""

    rows = list(rows)
    header = columns_of(rows)
    body = [[row.get(column) for column in header] for row in rows]
    sheet_name = escape("".join(ch for ch in sheet if ch not in "[]:*?/\\")[:31] or "Report")
    about_rows = [["Item", "Value"], *[[key, value] for key, value in about], ["Note", CAVEAT]]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/'
            'vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
            '2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        )
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets><sheet name="{sheet_name}" sheetId="1" r:id="rId1"/>'
            '<sheet name="About" sheetId="2" r:id="rId2"/></sheets>'
            + (
                '<definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0" '
                f"hidden=\"1\">'{sheet_name}'!$A$1:${_column_letter(len(header) - 1)}$"
                f"{len(body) + 1}</definedName></definedNames>"
                if header and body
                else ""
            )
            + "</workbook>",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/'
            '2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/'
            '2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
            '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/'
            '2006/relationships/styles" Target="styles.xml"/></Relationships>',
        )
        archive.writestr("xl/styles.xml", _STYLES)
        archive.writestr("xl/worksheets/sheet1.xml", _sheet_xml(header, body, frozen=True))
        archive.writestr(
            "xl/worksheets/sheet2.xml",
            _sheet_xml(about_rows[0], about_rows[1:], frozen=True),
        )
    return buffer.getvalue()


# ---------------------------------------------------------------------------------------- PDF

_UNITS = {
    "mwh": "MWh", "gwh": "GWh", "twh": "TWh", "mwh/d": "MWh/d", "eur": "EUR", "usd": "USD",
    "gbp": "GBP", "pct": "%", "mmbtu": "MMBtu", "utc": "UTC", "id": "ID", "pnl": "P&L",
    "mtm": "MtM", "var": "VaR", "dcq": "DCQ", "acq": "ACQ", "des": "DES", "fob": "FOB",
    "lng": "LNG", "eic": "EIC", "tso": "TSO", "d": "/d", "p": "p",
}  # fmt: skip


def column_label(name: str) -> str:
    """``physical_mwh`` -> ``Physical MWh``; units keep their desk spelling."""

    words = [part for part in name.replace("-", "_").split("_") if part]
    shown = []
    for index, word in enumerate(words):
        unit = _UNITS.get(word.casefold())
        if unit == "/d" and shown:
            shown[-1] += "/d"
            continue
        if unit and unit not in {"/d", "p"}:
            shown.append(unit)
        else:
            shown.append(word.capitalize() if index == 0 else word)
    return " ".join(shown) or name


# Helvetica advance widths (1/1000 em) for ASCII 32..126, from the standard AFM.
_HELVETICA = [
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278,
    556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556,
    1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778,
    667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278, 278, 278, 469, 556,
    333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
    556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584,
]  # fmt: skip

PAGE_WIDTH, PAGE_HEIGHT = 842.0, 595.0  # A4 landscape, points
MARGIN = 36.0


def _latin1(text: str) -> str:
    return text.encode("latin-1", "replace").decode("latin-1")


def _width(text: str, size: float, *, bold: bool = False) -> float:
    total = 0
    for char in text:
        code = ord(char)
        total += _HELVETICA[code - 32] if 32 <= code <= 126 else 556
    return total * size / 1000 * (1.04 if bold else 1.0)


def _fit(text: str, width: float, size: float, *, bold: bool = False) -> str:
    if _width(text, size, bold=bold) <= width:
        return text
    while text and _width(text + "..", size, bold=bold) > width:
        text = text[:-1]
    return text + ".."


def _pdf_string(text: str) -> str:
    text = _latin1(text)
    return "(" + text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ")"


def pdf_bytes(
    rows: Iterable[Mapping[str, Any]],
    *,
    title: str,
    subtitle: str = "",
    footer: str = "",
) -> bytes:
    """A paginated PDF table of the rows."""

    rows = list(rows)
    header = columns_of(rows)
    labels = [column_label(name) for name in header]
    cells = [
        [
            (
                _display_number(row.get(column))
                if _is_number(row.get(column))
                else _text(row.get(column))
            )
            for column in header
        ]
        for row in rows
    ]
    numeric = [
        any(_is_number(row.get(column)) for row in rows)
        and all(row.get(column) is None or _is_number(row.get(column)) for row in rows)
        for column in header
    ]
    usable = PAGE_WIDTH - 2 * MARGIN
    padding = 6.0

    def natural(size: float) -> list[float]:
        widths = []
        for index, name in enumerate(labels):
            longest = _width(_latin1(name), size, bold=True)
            for row in cells:
                longest = max(longest, _width(_latin1(row[index]), size))
            widths.append(longest + padding)
        return widths

    size = 8.0
    widths = natural(size)
    while header and sum(widths) > usable and size > 6.0:
        size -= 0.5
        widths = natural(size)
    if header and sum(widths) > usable:
        # Shorten the widest columns until the table fits; numbers keep their room.
        cap = max(widths)
        while sum(min(w, cap) for w in widths) > usable and cap > 30:
            cap -= 2
        widths = [min(w, cap) for w in widths]
    row_height = size * 1.55
    top = PAGE_HEIGHT - MARGIN
    table_top = top - 40
    bottom = MARGIN + 24
    per_page = max(1, int((table_top - row_height - bottom) // row_height))
    chunks = [cells[i : i + per_page] for i in range(0, len(cells), per_page)] or [[]]

    def text_op(x: float, y: float, value: str, font: str, font_size: float) -> str:
        return f"BT /{font} {font_size:.1f} Tf {x:.2f} {y:.2f} Td {_pdf_string(value)} Tj ET"

    streams: list[str] = []
    pages = len(chunks)
    for page_index, chunk in enumerate(chunks, start=1):
        ops = [text_op(MARGIN, top - 14, title, "F2", 13)]
        if subtitle:
            ops.append(text_op(MARGIN, top - 28, subtitle, "F1", 8))
        y = table_top
        # Header band.
        ops.append(
            f"0.92 g {MARGIN:.2f} {y - row_height + 2:.2f} {sum(widths):.2f} "
            f"{row_height:.2f} re f 0 g"
        )
        x = MARGIN
        for index, name in enumerate(labels):
            shown = _fit(_latin1(name), widths[index] - padding, size, bold=True)
            tx = (
                x + widths[index] - padding / 2 - _width(shown, size, bold=True)
                if numeric[index]
                else x + padding / 2
            )
            ops.append(text_op(tx, y - row_height + 2 + size * 0.45, shown, "F2", size))
            x += widths[index]
        y -= row_height
        for row_number, row in enumerate(chunk):
            if row_number % 2 == 1:
                ops.append(
                    f"0.97 g {MARGIN:.2f} {y - row_height + 2:.2f} {sum(widths):.2f} "
                    f"{row_height:.2f} re f 0 g"
                )
            x = MARGIN
            for index, value in enumerate(row):
                shown = _fit(_latin1(value), widths[index] - padding, size)
                tx = (
                    x + widths[index] - padding / 2 - _width(shown, size)
                    if numeric[index]
                    else x + padding / 2
                )
                ops.append(text_op(tx, y - row_height + 2 + size * 0.45, shown, "F1", size))
                x += widths[index]
            y -= row_height
        if not rows:
            ops.append(text_op(MARGIN, y - 14, "No rows for this selection.", "F1", 9))
        ops.append(
            f"0.6 G 0.5 w {MARGIN:.2f} {MARGIN + 14:.2f} m "
            f"{PAGE_WIDTH - MARGIN:.2f} {MARGIN + 14:.2f} l S"
        )
        left = " · ".join(part for part in (footer, CAVEAT) if part)
        ops.append(text_op(MARGIN, MARGIN + 4, left, "F1", 7))
        label = f"Page {page_index} of {pages}"
        ops.append(text_op(PAGE_WIDTH - MARGIN - _width(label, 7), MARGIN + 4, label, "F1", 7))
        streams.append("\n".join(ops))

    objects: list[bytes] = []
    # 1 catalog, 2 pages, 3 font regular, 4 font bold, then (page, content) pairs.
    kids = " ".join(f"{5 + 2 * i} 0 R" for i in range(pages))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>".encode())
    for name in ("Helvetica", "Helvetica-Bold"):
        objects.append(
            f"<< /Type /Font /Subtype /Type1 /BaseFont /{name} "
            "/Encoding /WinAnsiEncoding >>".encode()
        )
    for index, stream in enumerate(streams):
        content = stream.encode("latin-1", "replace")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH:.0f} {PAGE_HEIGHT:.0f}] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
            f"/Contents {6 + 2 * index} 0 R >>".encode()
        )
        objects.append(
            f"<< /Length {len(content)} >>\nstream\n".encode() + content + b"\nendstream"
        )
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return out.getvalue()
