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
from decimal import Decimal
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
    if isinstance(value, Decimal):
        return value.is_finite()
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value


def _xml_number(value: Any) -> str:
    """A number as an XLSX cell value: a decimal exactly as held, never via a float."""

    return format(value, "f") if isinstance(value, Decimal) else repr(value)


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


def _display_number(value: float | Decimal) -> str:
    if isinstance(value, Decimal):
        places = max(0, -value.as_tuple().exponent) if isinstance(value.as_tuple().exponent,
                                                                    int) else 2
        return f"{value:,.{min(places, 6)}f}"
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
    width_count = max([len(header), *(len(row) for row in body)] or [0])
    widths = [len(name) for name in header] + [0] * (width_count - len(header))
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
    if widths:
        parts.append("<cols>")
        for index, width in enumerate(widths):
            parts.append(
                f'<col min="{index + 1}" max="{index + 1}" width="{min(width + 3, 64)}" '
                'customWidth="1"/>'
            )
        parts.append("</cols>")
    parts.append("<sheetData>")
    for row_index, row in enumerate([header, *body] if header else body, start=1):
        parts.append(f'<row r="{row_index}">')
        for col_index, value in enumerate(row):
            ref = f"{_column_letter(col_index)}{row_index}"
            if row_index == 1 and frozen and header:
                parts.append(
                    f'<c r="{ref}" t="inlineStr" s="1"><is><t>{escape(_text(value))}</t></is></c>'
                )
            elif _is_number(value):
                style = (
                    "3" if isinstance(value, int) else "4" if isinstance(value, Decimal) else "2"
                )
                parts.append(f'<c r="{ref}" s="{style}"><v>{_xml_number(value)}</v></c>')
            elif isinstance(value, bool):
                parts.append(f'<c r="{ref}" t="b"><v>{int(value)}</v></c>')
            elif value is None or value == "":
                continue
            else:
                # inlineStr cells are never formulas; neutralised as well for tools that
                # re-save a workbook as CSV (security review M4).
                from eurogas_nexus.core.csv_safety import neutralise

                text = escape(neutralise(_text(value)))
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
    '<cellXfs count="5">'
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
    '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
    '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    '<xf numFmtId="3" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>'
    # Exact decimals (deal capture): General, so every held digit shows.
    '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
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
    return xlsx_workbook([(sheet, header, body)], about=about)


def _sheet_name(text: str, taken: set[str]) -> str:
    name = "".join(ch for ch in text if ch not in "[]:*?/\\")[:31] or "Sheet"
    base, number = name, 2
    while name.casefold() in taken:
        suffix = f" ({number})"
        name, number = base[: 31 - len(suffix)] + suffix, number + 1
    taken.add(name.casefold())
    return name


def xlsx_workbook(
    sheets: Sequence[tuple[str, Sequence[Any], Sequence[Sequence[Any]]]],
    *,
    about: Sequence[tuple[str, str]] = (),
    caveat: str | None = CAVEAT,
) -> bytes:
    """An XLSX workbook of several sheets ``(name, header, rows)`` and an ``About`` sheet.

    A sheet with an empty header has no header row (the ETRM entry sheet without titles).
    Decimals are written exactly as held.
    """

    taken: set[str] = set()
    named = [(_sheet_name(name, taken), list(header), [list(row) for row in body])
             for name, header, body in sheets]
    about_name = _sheet_name("About", taken)
    about_rows = [["Item", "Value"], *[[key, value] for key, value in about]]
    if caveat:
        about_rows.append(["Note", caveat])
    named.append((about_name, about_rows[0], about_rows[1:]))
    count = len(named)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        overrides = "".join(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for index in range(1, count + 1)
        )
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/'
            'vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            + overrides
            + '<Override PartName="/xl/styles.xml" ContentType="application/'
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
        sheet_entries = "".join(
            f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
            for index, (name, _header, _body) in enumerate(named, start=1)
        )
        defined = "".join(
            '<definedName name="_xlnm._FilterDatabase" localSheetId="'
            f"{index}\" hidden=\"1\">'{escape(name)}'!$A$1:$"
            f"{_column_letter(len(header) - 1)}${len(body) + 1}</definedName>"
            for index, (name, header, body) in enumerate(named)
            if header and body
        )
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f"<sheets>{sheet_entries}</sheets>"
            + (f"<definedNames>{defined}</definedNames>" if defined else "")
            + "</workbook>",
        )
        relationships = "".join(
            f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/'
            f'officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
            for index in range(1, count + 1)
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + relationships
            + f'<Relationship Id="rId{count + 1}" Type="http://schemas.openxmlformats.org/'
            'officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        )
        archive.writestr("xl/styles.xml", _STYLES)
        for index, (_name, header, body) in enumerate(named, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml",
                             _sheet_xml(header, body, frozen=True))
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


# ------------------------------------------------------------------- multi-section document
#
# A pack (the daily management summary, the risk pack) is several short sections, each a
# heading, a few lines and a table. Chinese text needs a CJK font: the PDF uses the standard
# Adobe Chinese (Simplified) font ``STSong-Light`` with the ``UniGB-UCS2-H`` encoding, which
# PDF readers provide themselves (Acrobat, browsers, Preview), so nothing is embedded and no
# font file or licence is added. Latin text in a Chinese document is drawn with the same font.

CJK_FONT = "STSong-Light"


def _has_cjk(text: str) -> bool:
    return any(ord(char) > 0x2E7F for char in text)


def _cjk_width(text: str, size: float) -> float:
    return sum(500 if ord(char) < 0x2E80 else 1000 for char in text) * size / 1000


def _cjk_string(text: str) -> str:
    encoded = "".join(
        f"{ord(char):04X}" if ord(char) <= 0xFFFF else "003F" for char in text
    )
    return f"<{encoded}>"


def _cjk_fit(text: str, width: float, size: float) -> str:
    if _cjk_width(text, size) <= width:
        return text
    while text and _cjk_width(text + "..", size) > width:
        text = text[:-1]
    return text + ".."


def pdf_document(
    *,
    title: str,
    subtitle: str = "",
    sections: Sequence[Mapping[str, Any]],
    footer: str = "",
    banner: str = "",
    cjk: bool = False,
    caveat: str | None = CAVEAT,
) -> bytes:
    """A paginated PDF of sections: ``{"heading", "lines", "columns", "rows", "numeric"}``.

    ``banner`` is printed at the top of the first page in a boxed band (a pack that failed a
    sanity check says so there). ``cjk`` draws every text with the Chinese font.
    """

    def width(text: str, size: float, bold: bool = False) -> float:
        return _cjk_width(text, size) if cjk else _width(_latin1(text), size, bold=bold)

    def fit(text: str, room: float, size: float, bold: bool = False) -> str:
        return _cjk_fit(text, room, size) if cjk else _fit(_latin1(text), room, size, bold=bold)

    def op(x: float, y: float, text: str, size: float, bold: bool = False) -> str:
        if cjk:
            return f"BT /F3 {size:.1f} Tf {x:.2f} {y:.2f} Td {_cjk_string(text)} Tj ET"
        font = "F2" if bold else "F1"
        return f"BT /{font} {size:.1f} Tf {x:.2f} {y:.2f} Td {_pdf_string(text)} Tj ET"

    usable = PAGE_WIDTH - 2 * MARGIN
    top = PAGE_HEIGHT - MARGIN
    bottom = MARGIN + 24
    pages: list[list[str]] = []
    state = {"y": top}

    def new_page() -> None:
        pages.append([])
        state["y"] = top

    def need(height: float) -> None:
        if not pages or state["y"] - height < bottom:
            new_page()

    new_page()
    page = pages[-1]
    page.append(op(MARGIN, top - 14, title, 13, bold=True))
    state["y"] = top - 22
    if subtitle:
        page.append(op(MARGIN, state["y"] - 6, subtitle, 8))
        state["y"] -= 16
    if banner:
        lines = _wrap(banner, usable - 12, 9, width)
        height = 8 + 12 * len(lines)
        page.append(f"0.85 0.15 0.1 RG 1.2 w {MARGIN:.2f} {state['y'] - height:.2f} "
                    f"{usable:.2f} {height:.2f} re S 0 G")
        y = state["y"] - 14
        for line in lines:
            page.append(op(MARGIN + 6, y, line, 9, bold=True))
            y -= 12
        state["y"] -= height + 10
    size, padding = 7.5, 6.0
    row_height = size * 1.6
    for section in sections:
        heading = str(section.get("heading") or "")
        need(40)
        pages[-1].append(op(MARGIN, state["y"] - 12, heading, 10.5, bold=True))
        state["y"] -= 18
        for text in section.get("lines") or ():
            for line in _wrap(str(text), usable, 8, width):
                need(12)
                pages[-1].append(op(MARGIN, state["y"] - 9, line, 8))
                state["y"] -= 11
        columns = [str(c) for c in section.get("columns") or ()]
        rows = [[_cell_text(v) for v in row] for row in section.get("rows") or ()]
        numeric = list(section.get("numeric") or [False] * len(columns))
        if columns:
            natural = []
            for index, name in enumerate(columns):
                longest = width(name, size, True)
                for row in rows:
                    longest = max(longest, width(row[index], size))
                natural.append(longest + padding)
            if sum(natural) > usable:
                cap = max(natural)
                while sum(min(w, cap) for w in natural) > usable and cap > 30:
                    cap -= 2
                natural = [min(w, cap) for w in natural]

            def header_band(natural=natural, columns=columns, numeric=numeric) -> None:
                y = state["y"]
                pages[-1].append(f"0.92 g {MARGIN:.2f} {y - row_height + 2:.2f} "
                                 f"{sum(natural):.2f} {row_height:.2f} re f 0 g")
                x = MARGIN
                for index, name in enumerate(columns):
                    shown = fit(name, natural[index] - padding, size, True)
                    tx = (x + natural[index] - padding / 2 - width(shown, size, True)
                          if numeric[index] else x + padding / 2)
                    pages[-1].append(op(tx, y - row_height + 2 + size * 0.45, shown, size, True))
                    x += natural[index]
                state["y"] -= row_height

            need(row_height * 2 + 4)
            state["y"] -= 2
            header_band()
            for number, row in enumerate(rows):
                if state["y"] - row_height < bottom:
                    new_page()
                    header_band()
                y = state["y"]
                if number % 2 == 1:
                    pages[-1].append(f"0.97 g {MARGIN:.2f} {y - row_height + 2:.2f} "
                                     f"{sum(natural):.2f} {row_height:.2f} re f 0 g")
                x = MARGIN
                for index, value in enumerate(row):
                    shown = fit(value, natural[index] - padding, size)
                    tx = (x + natural[index] - padding / 2 - width(shown, size)
                          if numeric[index] else x + padding / 2)
                    pages[-1].append(op(tx, y - row_height + 2 + size * 0.45, shown, size))
                    x += natural[index]
                state["y"] -= row_height
            if not rows and section.get("empty"):
                pages[-1].append(op(MARGIN, state["y"] - 10, str(section["empty"]), 8))
                state["y"] -= 12
        state["y"] -= 10
    total = len(pages)
    streams = []
    for index, ops in enumerate(pages, start=1):
        ops = list(ops)
        ops.append(f"0.6 G 0.5 w {MARGIN:.2f} {MARGIN + 14:.2f} m "
                   f"{PAGE_WIDTH - MARGIN:.2f} {MARGIN + 14:.2f} l S 0 G")
        left = " · ".join(part for part in (footer, caveat or "") if part)
        ops.append(op(MARGIN, MARGIN + 4, fit(left, usable - 80, 7), 7))
        label = f"{index} / {total}"
        ops.append(op(PAGE_WIDTH - MARGIN - width(label, 7), MARGIN + 4, label, 7))
        streams.append("\n".join(ops))
    return _pdf_file(streams, cjk=cjk)


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f"{value:,.2f}" if value.is_finite() else str(value)
    if _is_number(value):
        return _display_number(value)
    return _text(value)


def _wrap(text: str, room: float, size: float, width) -> list[str]:
    """Lines of ``text`` that fit ``room`` (words for Latin text, characters for Chinese)."""

    out: list[str] = []
    for paragraph in text.split("\n"):
        tokens = list(paragraph) if _has_cjk(paragraph) else paragraph.split(" ")
        joiner = "" if _has_cjk(paragraph) else " "
        line = ""
        for token in tokens:
            candidate = f"{line}{joiner}{token}" if line else token
            if width(candidate, size) <= room or not line:
                line = candidate
            else:
                out.append(line)
                line = token
        out.append(line)
    return out


def _pdf_file(streams: list[str], *, cjk: bool) -> bytes:
    objects: list[bytes] = []
    pages = len(streams)
    # 1 catalog, 2 pages, 3 Helvetica, 4 Helvetica-Bold, 5 CJK Type0, 6 its CIDFont,
    # 7 its descriptor, then (page, content) pairs from 8.
    first_page = 8
    kids = " ".join(f"{first_page + 2 * i} 0 R" for i in range(pages))
    objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objects.append(f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>".encode())
    for name in ("Helvetica", "Helvetica-Bold"):
        objects.append(
            f"<< /Type /Font /Subtype /Type1 /BaseFont /{name} "
            "/Encoding /WinAnsiEncoding >>".encode()
        )
    objects.append(
        f"<< /Type /Font /Subtype /Type0 /BaseFont /{CJK_FONT} /Encoding /UniGB-UCS2-H "
        "/DescendantFonts [6 0 R] >>".encode()
    )
    objects.append(
        f"<< /Type /Font /Subtype /CIDFontType0 /BaseFont /{CJK_FONT} "
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (GB1) /Supplement 2 >> "
        "/FontDescriptor 7 0 R /DW 1000 /W [1 95 500] >>".encode()
    )
    objects.append(
        f"<< /Type /FontDescriptor /FontName /{CJK_FONT} /Flags 6 "
        "/FontBBox [-25 -254 1000 880] /ItalicAngle 0 /Ascent 880 /Descent -120 "
        "/CapHeight 880 /StemV 93 >>".encode()
    )
    for index, stream in enumerate(streams):
        content = stream.encode("latin-1", "replace")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_WIDTH:.0f} {PAGE_HEIGHT:.0f}] "
            f"/Resources << /Font << /F1 3 0 R /F2 4 0 R /F3 5 0 R >> >> "
            f"/Contents {first_page + 1 + 2 * index} 0 R >>".encode()
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
