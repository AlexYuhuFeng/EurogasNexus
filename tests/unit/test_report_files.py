"""Excel and PDF renditions of report rows."""

from __future__ import annotations

import io
import re
import zipfile
from xml.etree import ElementTree

from eurogas_nexus.api.csv_export import report_response
from eurogas_nexus.core.report_files import columns_of, pdf_bytes, xlsx_bytes

ROWS = [
    {
        "hub": "TTF",
        "month": "2026-12",
        "physical_mwh": 744000.0,
        "financial_mwh": -372000,
        "note": "a & <b>",
    },
    {"hub": "NBP", "month": "2026-12", "physical_mwh": 12.5, "financial_mwh": None, "extra": True},
    {
        "hub": "THE",
        "month": "2027-01",
        "physical_mwh": -3.25,
        "financial_mwh": 0,
        "note": "Gaspool 天然气",
    },
]
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def test_columns_keep_first_seen_order():
    assert columns_of(ROWS) == ["hub", "month", "physical_mwh", "financial_mwh", "note", "extra"]


def test_xlsx_is_a_valid_workbook_with_numbers_as_numbers():
    data = xlsx_bytes(ROWS, sheet="Position ladder", about=[("Horizon", "Dec 26 to Jan 27")])
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = set(archive.namelist())
        assert {"[Content_Types].xml", "xl/workbook.xml", "xl/worksheets/sheet1.xml"} <= names
        for name in names:
            if name.endswith((".xml", ".rels")):
                ElementTree.fromstring(archive.read(name))  # well-formed
        sheet = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        about = archive.read("xl/worksheets/sheet2.xml").decode()
        workbook = archive.read("xl/workbook.xml").decode()
    assert 'name="Position ladder"' in workbook and 'name="About"' in workbook
    cells = {c.get("r"): c for c in sheet.iter(f"{{{NS['m']}}}c")}
    assert cells["C2"].find("m:v", NS).text == "744000.0" and cells["C2"].get("t") is None
    assert cells["D2"].find("m:v", NS).text == "-372000"
    assert "D3" not in cells  # None stays empty
    assert cells["F3"].get("t") == "b"
    assert cells["E4"].find("m:is/m:t", NS).text == "Gaspool 天然气"
    assert cells["E2"].find("m:is/m:t", NS).text == "a & <b>"
    assert sheet.find("m:autoFilter", NS).get("ref") == "A1:F4"
    assert "Dec 26 to Jan 27" in about and "Not the books and records" in about


def test_pdf_is_structurally_valid_and_paginates():
    rows = [{"day": f"2026-11-{(i % 30) + 1:02d}", "value": i * 1000.5} for i in range(120)]
    data = pdf_bytes(rows, title="Delivery performance", subtitle="Generated", footer="x")
    assert data.startswith(b"%PDF-1.4") and data.rstrip().endswith(b"%%EOF")
    count = int(re.search(rb"/Count (\d+)", data).group(1))
    assert count >= 3
    # xref offsets point at the objects they name.
    xref = int(re.search(rb"startxref\n(\d+)", data).group(1))
    table = data[xref:].split(b"\n")
    total = int(table[1].split()[1])
    for number in range(1, total):
        offset = int(table[2 + number].split()[0])
        assert data[offset:].startswith(f"{number} 0 obj".encode())
    assert b"(Page 1 of " in data and b"(119,059.5)" in data
    assert b"(0)" in data


def test_pdf_handles_wide_tables_empty_rows_and_non_latin_text():
    wide = [{f"column_{i}": "x" * 80 for i in range(14)}]
    assert pdf_bytes(wide, title="Wide").startswith(b"%PDF")
    empty = pdf_bytes([], title="Empty")
    assert b"No rows for this selection." in empty
    assert b"(Gaspool ???)" in pdf_bytes([{"n": "Gaspool 天然气"}], title="t")
    assert b"\\(" in pdf_bytes([{"n": "a (b)"}], title="t")


def test_report_response_media_types():
    for fmt, media, magic in (
        ("xlsx", "spreadsheetml", b"PK"),
        ("pdf", "application/pdf", b"%PDF"),
        ("csv", "text/csv", "﻿".encode()),
    ):
        response = report_response(ROWS, report="position-ladder", format=fmt, title="Ladder")
        assert media in response.media_type
        assert response.body.startswith(magic)
        assert response.headers["X-Eurogas-Report-Rows"] == "3"
        assert f'.{fmt}"' in response.headers["Content-Disposition"]


def test_pdf_column_labels_use_desk_units():
    from eurogas_nexus.core.report_files import column_label

    assert column_label("physical_mwh") == "Physical MWh"
    assert column_label("mark_to_market") == "Mark to market"
    assert column_label("bid_usd_mmbtu") == "Bid USD MMBtu"
    assert column_label("dcq_mwh_d") == "DCQ MWh/d"
    assert column_label("pnl_eur") == "P&L EUR"
