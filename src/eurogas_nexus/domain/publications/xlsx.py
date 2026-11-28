"""Read the cells of an Office Open XML spreadsheet (``.xlsx``) with the standard library only.

A publisher's calendar arrives as an ``.xlsx`` file; the product needs its cell values, not a
spreadsheet engine, so no dependency is added. Values are returned as the file stores them:
text, or the number's own digits (a date is an Excel serial day, see :func:`excel_day`).

The file is untrusted: the archive is bounded (members, total size), and an XML part that
declares a document type (where entity tricks live) is refused.

只用标准库读取 xlsx 单元格；对不可信文件设置大小上限并拒绝带 DOCTYPE 的 XML。
"""

from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from datetime import date, timedelta
from xml.etree import ElementTree

_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
_NS = {"m": _MAIN}

MAX_MEMBERS = 400
MAX_TOTAL_BYTES = 40_000_000
_CELL = re.compile(r"^([A-Z]+)(\d+)$")


class SpreadsheetError(ValueError):
    """The bytes are not a readable spreadsheet."""


@dataclass(frozen=True)
class Sheet:
    name: str
    #: ``"B12" -> value`` for every non-empty cell.
    cells: dict[str, str]

    def get(self, ref: str) -> str:
        return self.cells.get(ref, "")

    def rows(self) -> dict[int, dict[str, str]]:
        """Row number -> column letters -> value."""

        out: dict[int, dict[str, str]] = {}
        for ref, value in self.cells.items():
            match = _CELL.match(ref)
            if match:
                out.setdefault(int(match.group(2)), {})[match.group(1)] = value
        return dict(sorted(out.items()))


def _xml(data: bytes) -> ElementTree.Element:
    if b"<!DOCTYPE" in data[:4096] or b"<!ENTITY" in data:
        raise SpreadsheetError("an XML part declares a document type")
    try:
        return ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise SpreadsheetError(f"an XML part is not well formed: {exc}") from exc


def read_workbook(data: bytes) -> list[Sheet]:
    """Every sheet of the workbook, in the workbook's order."""

    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise SpreadsheetError("not an xlsx file (not a zip archive)") from exc
    infos = archive.infolist()
    if len(infos) > MAX_MEMBERS or sum(info.file_size for info in infos) > MAX_TOTAL_BYTES:
        raise SpreadsheetError("the spreadsheet is larger than a calendar can be")
    names = {info.filename for info in infos}

    def part(name: str) -> bytes:
        if name not in names:
            raise SpreadsheetError(f"the spreadsheet has no {name}")
        return archive.read(name)

    shared: list[str] = []
    if "xl/sharedStrings.xml" in names:
        for item in _xml(part("xl/sharedStrings.xml")).findall("m:si", _NS):
            shared.append("".join(text.text or "" for text in item.iter(f"{{{_MAIN}}}t")))
    workbook = _xml(part("xl/workbook.xml"))
    targets = {
        rel.get("Id"): rel.get("Target") or ""
        for rel in _xml(part("xl/_rels/workbook.xml.rels")).findall(f"{{{_PKG_REL}}}Relationship")
    }
    sheets: list[Sheet] = []
    container = workbook.find("m:sheets", _NS)
    for entry in [] if container is None else list(container):
        target = targets.get(entry.get(f"{{{_REL}}}id"), "")
        path = target.lstrip("/")
        path = path if path.startswith("xl/") else f"xl/{path}"
        cells: dict[str, str] = {}
        for cell in _xml(part(path)).iter(f"{{{_MAIN}}}c"):
            ref = cell.get("r") or ""
            kind = cell.get("t")
            value_node = cell.find("m:v", _NS)
            if kind == "inlineStr":
                inline = cell.find("m:is", _NS)
                value = "" if inline is None else "".join(
                    text.text or "" for text in inline.iter(f"{{{_MAIN}}}t")
                )
            elif value_node is None or value_node.text is None:
                continue
            elif kind == "s":
                try:
                    value = shared[int(value_node.text)]
                except (ValueError, IndexError) as exc:
                    raise SpreadsheetError(f"cell {ref} points at a missing string") from exc
            else:
                value = value_node.text
            if value.strip():
                cells[ref] = value
        sheets.append(Sheet(name=str(entry.get("name") or ""), cells=cells))
    if not sheets:
        raise SpreadsheetError("the workbook lists no sheets")
    return sheets


#: Day 0 of the 1900 date system as Excel counts it (it believes 1900 was a leap year).
_EXCEL_EPOCH = date(1899, 12, 30)


def excel_day(value: str) -> date:
    """A date cell (an Excel serial day, e.g. ``46209``) as a date."""

    try:
        serial = float(value)
    except ValueError as exc:
        raise SpreadsheetError(f"{value!r} is not a date serial") from exc
    if not 20_000 < serial < 80_000:  # 1954 to 2119: outside that it is not a calendar date
        raise SpreadsheetError(f"{value!r} is not a plausible date serial")
    return _EXCEL_EPOCH + timedelta(days=int(serial))


def clock_time(value: str) -> tuple[int, int]:
    """A time cell as ``(hour, minute)``: ``"7:00"`` text or an Excel day fraction."""

    text = value.strip()
    match = re.fullmatch(r"(\d{1,2}):(\d{2})", text)
    if match:
        hour, minute = int(match.group(1)), int(match.group(2))
    else:
        try:
            fraction = float(text)
        except ValueError as exc:
            raise SpreadsheetError(f"{value!r} is not a time") from exc
        if not 0 <= fraction < 1:
            raise SpreadsheetError(f"{value!r} is not a time of day")
        total = round(fraction * 24 * 60)
        hour, minute = divmod(total, 60)
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise SpreadsheetError(f"{value!r} is not a time of day")
    return hour, minute


__all__ = ["Sheet", "SpreadsheetError", "clock_time", "excel_day", "read_workbook"]
