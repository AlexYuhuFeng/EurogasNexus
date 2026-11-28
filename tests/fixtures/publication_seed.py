"""A small ENTSOG-shaped auction calendar workbook and CAM NC page, written for the tests.

The layout follows ENTSOG's ``MAR0369-25`` (2026/2027) file as read on 2026-11-28: an
explanatory note naming the calendar and its years, and Yearly, Quarterly and Monthly sheets
each with a FIRM and an INTERRUPTIBLE table. The dates are a subset written here; no ENTSOG file
is committed (its site terms do not allow passing its content to another party).
"""

from __future__ import annotations

import io
import zipfile
from datetime import date
from xml.sax.saxutils import escape

PAGE_URL = "https://www.entsog.eu/capacity-allocation-mechanisms-nc"
FILE_2627 = ("https://www.entsog.eu/sites/default/files/2025-12/"
             "MAR0369-25_CAM%20NC%20Auction%20Calendar%202026-2027_Final_for_upload.xlsx")
FILE_2526 = ("https://www.entsog.eu/sites/default/files/2024-12/"
             "MAR0277-24_CAM%20NC%20Auction%20Calendar%202025-2026_Final%20for%20upload.xlsx")


def serial(day: date) -> str:
    return str((day - date(1899, 12, 30)).days)


def page_html(*links: str) -> bytes:
    anchors = "\n".join(f'<li><a href="{link}">calendar</a></li>' for link in links)
    return (f"<html><body><h2 id='cam-nc-early-implementation-documents-and-auction-calendar'>"
            f"Auction calendar</h2><ul>{anchors}</ul></body></html>").encode()


def _col(index: int) -> str:
    out = ""
    while index:
        index, rem = divmod(index - 1, 26)
        out = chr(65 + rem) + out
    return out


def _sheet_xml(rows: dict[int, dict[str, str]]) -> str:
    body = []
    for number, cells in sorted(rows.items()):
        parts = [f'<c r="{col}{number}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'
                 if not value.replace(".", "").isdigit()
                 else f'<c r="{col}{number}"><v>{value}</v></c>'
                 for col, value in cells.items()]
        body.append(f'<row r="{number}">{"".join(parts)}</row>')
    return ('<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.'
            'openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            + "".join(body) + "</sheetData></worksheet>")


HEAD = {"B": "Publication Date", "C": "Start date", "D": "Start time (UTC)", "E": "Run date",
        "F": "Run start (UTC)", "G": "End date", "H": "End time (UTC)"}


def table(start_row: int, title: str, auctions: list[tuple[date, date, str, list[tuple]]]):
    """Rows of one table: ``[(published, start, time, [(run, end), ...]), ...]``."""

    rows: dict[int, dict[str, str]] = {start_row: {"B": title}, start_row + 2: dict(HEAD)}
    number = start_row + 3
    for published, start, clock, runs in auctions:
        for index, (run, end) in enumerate(runs):
            row = {"E": serial(run), "F": "4:00", "G": serial(end), "H": "4:00"}
            if index == 0:
                row |= {"B": serial(published), "C": serial(start), "D": clock}
            rows[number] = row
            number += 1
        number += 1  # a blank line between auctions
    return rows, number + 2


def monthly(year: int, months: range) -> list[tuple]:
    out = []
    for month in months:
        first = date(year + (month == 12), month % 12 + 1, 1)
        end = date(first.year + (first.month == 12), first.month % 12 + 1, 1)
        start = date(year, month, 15)
        out.append((date(year, month, 8), start, "8:00", [(first, end)]))
    return out


def calendar_xlsx(*, monthly_override: dict[int, date] | None = None,
                  drop_sheet: str | None = None, rename_header: bool = False) -> bytes:
    """The workbook; ``monthly_override`` moves a firm monthly auction's start date."""

    note = {1: {"B": "MAR0369-25"}, 2: {"B": "Version date: November 12th 2025"},
            3: {"B": "Final"},
            11: {"B": "Auction Calendar 2026/2027 for Capacity Allocation Mechanism Network Code"}}
    yearly_rows, after = table(3, "FIRM CAPACITY - 1st Monday of July", [
        (date(2026, 6, 6), date(2026, 7, 6), "7:00",
         [(date(2026, 10, 1), date(2027, 10, 1)), (date(2027, 10, 1), date(2028, 10, 1))])])
    more, _ = table(after, "INTERRUPTIBLE CAPACITY - 3rd Monday of July", [
        (date(2026, 7, 13), date(2026, 7, 20), "7:00", [(date(2026, 10, 1), date(2027, 10, 1))])])
    yearly_rows |= more
    quarterly_rows, after = table(3, "FIRM CAPACITY - 1st Monday of August", [
        (date(2026, 7, 20), date(2026, 8, 3), "7:00",
         [(date(2026, 10, 1), date(2027, 1, 1)), (date(2027, 1, 1), date(2027, 4, 1))]),
        (date(2026, 10, 19), date(2026, 11, 2), "8:00", [(date(2027, 1, 1), date(2027, 4, 1))]),
        (date(2027, 1, 18), date(2027, 2, 1), "8:00", [(date(2027, 4, 1), date(2027, 7, 1))]),
    ])
    month_auctions = monthly(2026, range(3, 13))
    if monthly_override:
        month_auctions = [
            (pub, monthly_override.get(start.month, start), clock, runs)
            for pub, start, clock, runs in month_auctions
        ]
    monthly_rows, after = table(3, "FIRM CAPACITY - 3rd Monday of M-1", month_auctions)
    if rename_header:
        monthly_rows[5]["C"] = "Opening day"
    sheets = {"Explanatory note": note, "Yearly": yearly_rows, "Quarterly": quarterly_rows,
              "Monthly": monthly_rows,
              "Within-Day": {6: {"B": "Subject to capacity being made available, a within-day "
                                      "capacity auction shall be held every hour during the gas "
                                      "day."}}}
    if drop_sheet:
        sheets.pop(drop_sheet)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        entries, rels = [], []
        for index, (name, rows) in enumerate(sheets.items(), start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _sheet_xml(rows))
            entries.append(f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>')
            rels.append(f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/'
                        f'officeDocument/2006/relationships/worksheet" '
                        f'Target="worksheets/sheet{index}.xml"/>')
        archive.writestr("xl/workbook.xml", (
            '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/'
            'spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/'
            'officeDocument/2006/relationships"><sheets>' + "".join(entries)
            + "</sheets></workbook>"))
        archive.writestr("xl/_rels/workbook.xml.rels", (
            '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/'
            'package/2006/relationships">' + "".join(rels) + "</Relationships>"))
    return buffer.getvalue()


class PublicationFetcher:
    """Serves robots.txt, the CAM NC page and calendar files from memory; records requests."""

    def __init__(self, files: dict[str, bytes], *, page: bytes | None = None,
                 robots: tuple[int, bytes] = (404, b""), page_status: int = 200) -> None:
        from eurogas_nexus.application.news_ingest import FetchResult

        self._result = FetchResult
        self.files = dict(files)
        self.page = page if page is not None else page_html(*files)
        self.robots = robots
        self.page_status = page_status
        self.calls: list[str] = []

    def __call__(self, url: str, headers: dict[str, str]):
        self.calls.append(url)
        if url.endswith("/robots.txt"):
            return self._result(self.robots[0], self.robots[1], {})
        if url == PAGE_URL:
            return self._result(self.page_status, self.page if self.page_status == 200 else b"",
                                {})
        if url in self.files:
            return self._result(200, self.files[url], {})
        return self._result(404, b"", {})
