"""Small documents in the layouts of the consented publishers, written for the tests.

Each follows the publisher's layout as read on 2026-11-28 (element and column names, the date
and number formats, the PDF line shapes) with **invented values and a handful of rows**. No
publisher's file, page, table or text is committed: the repository is public, and the consents
cover the firm's own use only.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date, timedelta
from xml.sax.saxutils import escape

THE_API = "https://api.tradinghub.eu/api/dataexport/xmlexport/PricesEnergyImbalance"
NG_API = "https://api.nationalgas.com/operationaldata/v1/publications/gasday"
MIBGAS_PAGE = "https://www.mibgas.es/en/file-access"
EEX_NGP_PAGE = "https://www.eex.com/en/markets/natural-gas/gas-market-transparency"
EEX_NGP_FILE = "https://gasandregistry.eex.com/Gas/NGP/TTF_NGP_60_Days.csv"
EEX_CAL_PAGE = "https://www.eex.com/en/trading-resources/trading-information/calendar"
EEX_GAS_XLSX = ("https://www.eex.com/fileadmin/EEX/Downloads/Trading/Calendar/"
                "Natural_Gas_Trading_Calendar/20260121_NaturalGasTradingCalendar2026.xlsx")
EEX_HOLIDAY_PDF = ("https://www.eex.com/fileadmin/EEX/Downloads/Trading/Calendar/Holiday_Calendar/"
                   "EEX_Trading_Calendar_Emissions_Spot__Derivatives.pdf")
ENDEX_PDF = "https://www.ice.com/publicdocs/ICE_Endex_Trading_Schedule.pdf"
IFEU_PDF = "https://www.ice.com/publicdocs/Trading_Schedule.pdf"


def mibgas_url(year: int) -> str:
    return f"https://www.mibgas.es/en/file-access/MIBGAS_Data_{year}.csv?path=AGNO_{year}/XLS"


# ------------------------------------------------------------------------------- prices


def the_xml(days: list[tuple[date, float, float, float]], *, unit: str = "EUR/MWh",
            extra_field: bool = False) -> bytes:
    """``[(gas day, VTP daily average, positive, negative), ...]`` as THE's export."""

    rows = []
    for day, average, positive, negative in days:
        rows.append(
            "<PricesEnergyImbalance>"
            f"<Gasday>{day.isoformat()}</Gasday>"
            f"<PositiveEnergyImbalancePrice>{positive}</PositiveEnergyImbalancePrice>"
            f"<NegativeEnergyImbalancePrice>{negative}</NegativeEnergyImbalancePrice>"
            f"<VTPDailyAveragePrice>{average}</VTPDailyAveragePrice>"
            "<VTPDailyAveragePriceSmallAdjPlus>1</VTPDailyAveragePriceSmallAdjPlus>"
            "<VTPDailyAveragePriceSmallAdjMinus>1</VTPDailyAveragePriceSmallAdjMinus>"
            "<MarginalPriceSystemBuy xsi:nil=\"true\" />"
            "<MarginalPriceSystemSell xsi:nil=\"true\" />"
            + ("<NewField>1</NewField>" if extra_field else "")
            + f"<Unit>{unit}</Unit></PricesEnergyImbalance>"
        )
    return ("﻿<?xml version=\"1.0\" encoding=\"utf-8\"?>"
            "<PricesEnergyImbalance xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\">"
            + "".join(rows) + "</PricesEnergyImbalance>").encode()


def ng_json(days: list[tuple[date, str, str, str]], *, rename: bool = False) -> bytes:
    """``[(gas day, SAP, SMP buy, SMP sell), ...]`` in p/kWh as National Gas's answer."""

    def item(pid: str, name: str, index: int) -> dict:
        return {"publicationId": pid, "publicationName": name, "publications": [
            {"applicableAt": f"{(d + timedelta(days=1)).isoformat()}T11:40:00+00:00",
             "applicableFor": d.isoformat(), "value": values[index],
             "generatedTimeStamp": f"{(d + timedelta(days=1)).isoformat()}T11:41:00+00:00",
             "qualityIndicator": "", "substituted": "N",
             "createdDate": f"{(d + timedelta(days=1)).isoformat()}T11:41:11+00:00"}
            for d, *values in days]}

    return json.dumps([
        item("PUBOB603", "SAP, Daily" if rename else "SAP, Actual Day", 0),
        item("PUBOB604", "SMP Buy, Actual Day", 1),
        item("PUBOB605", "SMP Sell, Actual Day", 2),
    ]).encode()


def mibgas_csv(rows: list[tuple[date, str, date, date, str]], *, header: str | None = None
               ) -> bytes:
    """``[(trading day, product, first delivery, last delivery, price), ...]``."""

    head = header or ('Trading day;Product;Place of delivery;Area;First Day Delivery;'
                      'Last Day Delivery;"MIBGAS Daily Price [EUR/MWh]";')
    lines = ["Fecha Emisión :28/11/2026 - 09:00;", head]
    for day, product, first, last, price in rows:
        lines.append(f"{day:%d/%m/%Y};{product};PVB;ES;{first:%d/%m/%Y};{last:%d/%m/%Y};{price};")
    return ("﻿" + "\r\n".join(lines) + "\r\n").encode()


def eex_ngp_csv(rows: list[tuple[date, float]]) -> bytes:
    lines = ["Index name;Delivery date;Index Value (€/MWh);Index Volume (MWh);Number of trades;"]
    for day, value in rows:
        lines.append(f"TTF Neutral Gas Price {day.isoformat()};{day.isoformat()};{value};1000;10")
    return ("﻿" + "\n".join(lines) + "\n").encode()


def eex_ngp_page() -> bytes:
    return (f'<html><body><a href="{EEX_NGP_FILE}">TTF NGP 60 days</a>'
            '<a href="https://gasandregistry.eex.com/Gas/NGP/TTF_NGP_15_Mins.csv">15</a>'
            "</body></html>").encode()


# ---------------------------------------------------------------------------- calendars


def _xlsx(sheets: dict[str, dict[int, dict[str, str]]]) -> bytes:
    names = list(sheets)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("_rels/.rels", (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'))
        archive.writestr("xl/workbook.xml", (
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            "<sheets>" + "".join(f'<sheet name="{escape(n)}" sheetId="{i + 1}" r:id="rId{i + 1}"/>'
                                 for i, n in enumerate(names)) + "</sheets></workbook>"))
        archive.writestr("xl/_rels/workbook.xml.rels", (
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            + "".join(f'<Relationship Id="rId{i + 1}" Type="http://schemas.openxmlformats.org/'
                      f'officeDocument/2006/relationships/worksheet" '
                      f'Target="worksheets/sheet{i + 1}.xml"/>' for i in range(len(names)))
            + "</Relationships>"))
        for index, name in enumerate(names):
            body = []
            for number, cells in sorted(sheets[name].items()):
                parts = [f'<c r="{col}{number}"><v>{value}</v></c>'
                         if value.replace(".", "").isdigit()
                         else (f'<c r="{col}{number}" t="inlineStr"><is><t>'
                               f'{escape(value)}</t></is></c>')
                         for col, value in cells.items()]
                body.append(f'<row r="{number}">{"".join(parts)}</row>')
            archive.writestr(f"xl/worksheets/sheet{index + 1}.xml", (
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                "<sheetData>" + "".join(body) + "</sheetData></worksheet>"))
    return buffer.getvalue()


def serial(day: date) -> str:
    return str((day - date(1899, 12, 30)).days)


def eex_gas_xlsx(holidays: list[tuple[date, str]], *, drop_column: bool = False) -> bytes:
    """EEX's natural gas calendar workbook: the holiday sheet and the physical futures sheet."""

    head = {"B": "Bank Holidays - Natural Gas Spot"}
    if not drop_column:
        head["E"] = "Exchange Holidays - Natural Gas Futures"
    rows: dict[int, dict[str, str]] = {2: head, 4: {"B": "Date", "C": "Calendar event",
                                                   "E": "Date", "F": "Calendar event"}}
    for offset, (day, what) in enumerate(holidays):
        rows[5 + offset] = {"B": serial(day) + ".25", "C": "Bank holiday",
                            "E": serial(day), "F": what}
    rows[5 + len(holidays) + 2] = {"E": "Natural Gas Futures - Tradable Contracts"}
    futures = {
        2: {"B": "Physical Futures - Natural Gas Futures"},
        5: {"B": "Maturities", "D": "Number of Days", "E": "Trading Start date",
            "F": "Trading End date", "G": "Delivery Start", "H": "Delivery End"},
        6: {"B": "Month", "C": " December 2026", "D": "31", "E": serial(date(2024, 12, 1)),
            "F": serial(date(2026, 11, 27)), "G": serial(date(2026, 12, 1)),
            "H": serial(date(2027, 1, 1))},
        7: {"B": "Month", "C": " January 2027", "D": "31", "E": serial(date(2025, 1, 1)),
            "F": serial(date(2026, 12, 30)), "G": serial(date(2027, 1, 1)),
            "H": serial(date(2027, 2, 1))},
    }
    return _xlsx({"2026 Natural Gas Holidays": rows, "Physical Futures": futures})


def eex_calendar_page() -> bytes:
    return (f'<html><body><a href="{EEX_GAS_XLSX}">Natural Gas Trading Calendar 2026</a>'
            f'<a href="{EEX_HOLIDAY_PDF}">Holiday calendar</a>'
            '<a href="/fileadmin/EEX/Downloads/Trading/Calendar/Auction_Calendar/x.xlsx">a</a>'
            "</body></html>").encode()


def pdf(lines: list[str]) -> bytes:
    """A one-font PDF whose pages carry ``lines`` (40 a page), readable by ``pypdf``."""

    pages = [lines[i:i + 40] for i in range(0, len(lines), 40)] or [[]]
    objects: list[bytes] = []

    def esc(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    kids = []
    for index, page_lines in enumerate(pages):
        stream = "BT /F1 9 Tf 40 800 Td 12 TL " + " ".join(
            f"({esc(line)}) Tj T*" for line in page_lines) + " ET"
        content_id = 4 + 2 * index
        page_id = 5 + 2 * index
        kids.append(page_id)
        objects.append(f"{content_id} 0 obj << /Length {len(stream.encode('latin-1'))} >> "
                       f"stream\n{stream}\nendstream endobj\n".encode("latin-1"))
        objects.append((f"{page_id} 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                        f"/Contents {content_id} 0 R /Resources << /Font << /F1 3 0 R >> >> >> "
                        "endobj\n").encode())
    head = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n",
        (f"2 0 obj << /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] "
         f"/Count {len(kids)} >> endobj\n").encode(),
        b"3 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
        b"/Encoding /WinAnsiEncoding >> endobj\n",
    ]
    body = b"%PDF-1.4\n"
    offsets = []
    for chunk in [*head, *objects]:
        offsets.append(len(body))
        body += chunk
    xref = len(body)
    body += f"xref\n0 {len(offsets) + 1}\n0000000000 65535 f \n".encode()
    body += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    body += (f"trailer << /Size {len(offsets) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
             ).encode()
    return body


def eex_holiday_pdf(*, footnote: bool = True) -> bytes:
    return pdf([
        "Holiday Calendar",
        "Exchange days are all business days Monday to Friday which are not listed below.",
        "Christmas Eve - 24th December*",
        "New Year's Eve - 31st December*",
        ("* Gas and Freight derivatives are offered for trading on 24th and 31st December from "
         "09:00 am to 12:30 CET." if footnote else "* See the exchange notices."),
        "The calendar is applicable continuously for all years until further notice.",
    ])


def endex_pdf() -> bytes:
    return pdf([
        "ICE ENDEX TRADING SCHEDULE | v 9.9 | October 2026 1",
        "ICE ENDEX TRADING SCHEDULE",
        "Year: 2026 Occasion Status",
        "Friday 03 April 2026 Good Friday Closed",
        "Thursday 24 December 2026 Christmas Eve AC",
        "Friday 25 December 2026 Christmas Closed",
        "Year: 2027 Occasion Status",
        "Friday 01 January 2027 New Year Closed",
        "Monday 31 May 2027",
        "Spring Bank Holiday",
        "D",
        "2. Trading Schedule Key",
        "A: Early Settlements",
        "Settlement Times",
        "13:40 - 13:50 (CET)",
        "C: Market Close at 19:00 CET",
        "D: Market Close at 18:30 CET",
    ])


def ifeu_pdf() -> bytes:
    return pdf([
        "IFEU Trading Schedule: Oil, Utilities and Agricultural | November 2026 1",
        "2026 Trading Schedule",
        "Year: 2026",
        "Friday 03 April",
        "Good Friday",
        "UK and US Holiday",
        "Closed",
        "Monday 04 May",
        "May Day",
        "UK Holiday",
        "TD",
        "UK Natural Gas and Power Contracts Closed",
        "Monday 19 October Some Day US Holiday C",
        "Year: 2027",
        "Friday 01 January",
        "New Year Day UK and US Holiday Closed",
        "Appendix 1",
        "Thursday 24 December 2026",
        "Contract Time of designated settlement periods Trading ceases",
        ("UK Natural Gas and Power Contracts 12:40-12:50 (GMT) 07:40-07:50 (ET) 18:00 (GMT) "
         "13:00 (ET)"),
        "Monday 28 December 2026",
        "The Exchange will be OPEN for trading EXCEPT for the following contracts:",
        "UK Natural Gas and Power Contracts UK Emissions Contracts",
    ])


class ConsentedFetcher:
    """Serves robots.txt and the documents above from memory; records every request."""

    def __init__(self, files: dict[str, bytes], *, robots: dict[str, tuple[int, bytes]] | None
                 = None, statuses: dict[str, tuple[int, dict]] | None = None) -> None:
        from eurogas_nexus.application.news_ingest import FetchResult

        self._result = FetchResult
        self.files = dict(files)
        self.robots = robots or {}
        self.statuses = statuses or {}
        self.calls: list[tuple[str, dict, bytes | None]] = []

    def urls(self) -> list[str]:
        return [url for url, _h, _b in self.calls]

    def __call__(self, url: str, headers: dict[str, str], body: bytes | None = None):
        self.calls.append((url, dict(headers), body))
        if url.endswith("/robots.txt"):
            host = url.split("/")[2]
            status, text = self.robots.get(host, (404, b""))
            return self._result(status, text, {})
        base = url.split("?")[0] if url.startswith((THE_API,)) else url
        if base in self.statuses:
            status, found = self.statuses[base]
            return self._result(status, b"", found)
        if url in self.files:
            return self._result(200, self.files[url], {"etag": '"e1"'})
        if base in self.files:
            return self._result(200, self.files[base], {})
        return self._result(404, b"", {})
