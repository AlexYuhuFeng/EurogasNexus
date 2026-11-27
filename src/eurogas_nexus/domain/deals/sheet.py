"""The ETRM entry sheet: the day's deals in the column order and formats of the ETRM template.

The layout is a TOML file (``etrm_entry_sheet.toml``): one ``[[column]]`` per column with its
header and either a deal field or a fixed value, value spellings (``buy`` as ``B``), decimal
places, and the sheet's date and time formats. Matching the desk's real template is an edit
of that file. The same rows are written as CSV and XLSX.

ETRM 录入表：按布局文件（列顺序、表头、取值、格式、固定值）生成 CSV 与 XLSX。
"""

from __future__ import annotations

import csv
import io
import tomllib
from dataclasses import dataclass
from dataclasses import field as dc_field
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from eurogas_nexus.domain.deals.formats import FormatError

#: The deal values a column may name.
SHEET_FIELDS = (
    "deal_key", "venue", "venue_trade_id", "leg_id", "trade_date", "trade_time", "trader",
    "counterparty", "counterparty_or_venue", "cleared", "hub", "product", "delivery_start",
    "delivery_end", "side", "volume", "volume_unit", "total_mwh", "price", "price_unit",
    "price_currency", "price_per_mwh", "physical", "instrument", "fees", "fee_currency", "book",
    "source", "version", "status",
)  # fmt: skip


@dataclass(frozen=True)
class SheetColumn:
    header: str
    field: str | None = None
    value: str | None = None
    values: dict[str, str] = dc_field(default_factory=dict)
    decimals: int | None = None
    number: bool = False


@dataclass(frozen=True)
class SheetLayout:
    name: str
    title: str
    sheet_name: str
    columns: tuple[SheetColumn, ...]
    include_header: bool = True
    csv_delimiter: str = ","
    date_format: str = "%Y-%m-%d"
    datetime_format: str = "%Y-%m-%d %H:%M"
    timezone: str = "UTC"
    decimal_separator: str = "."
    include_cancelled: bool = False
    etrm_system: str = "ETRM"
    etrm_reference_column: str = ""
    source_path: str = ""

    def describe(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "title": self.title,
            "headers": [column.header for column in self.columns],
            "date_format": self.date_format,
            "source_path": self.source_path,
            "etrm_reference_column": self.etrm_reference_column,
        }


def parse_layout(text: str, *, source_path: str = "") -> SheetLayout:
    """The sheet layout from its TOML text; raises :class:`FormatError` with what to fix."""

    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise FormatError(f"{source_path or 'sheet layout'}: not valid TOML ({exc})") from exc
    where = source_path or "sheet layout"
    blocks = raw.get("column") or []
    if not isinstance(blocks, list) or not blocks:
        raise FormatError(f"{where}: add at least one [[column]] block")
    columns = []
    for index, block in enumerate(blocks, start=1):
        header = str(block.get("header") or "").strip()
        if not header:
            raise FormatError(f"{where}: column {index} has no header")
        name = block.get("field")
        if name is not None and name not in SHEET_FIELDS:
            raise FormatError(f"{where}: column {header!r} names an unknown field {name!r}; "
                              f"the fields are {', '.join(SHEET_FIELDS)}")
        if name is None and "value" not in block:
            raise FormatError(f"{where}: column {header!r} needs a field or a fixed value")
        decimals = block.get("decimals")
        if decimals is not None and (not isinstance(decimals, int) or not 0 <= decimals <= 10):
            raise FormatError(f"{where}: column {header!r}: decimals must be 0 to 10")
        columns.append(SheetColumn(
            header=header,
            field=name,
            value=None if "value" not in block else str(block["value"]),
            values={str(k).casefold(): str(v) for k, v in (block.get("values") or {}).items()},
            decimals=decimals,
            number=str(block.get("type") or "").casefold() == "number",
        ))
    export = raw.get("etrm_export") or {}
    delimiter = str(raw.get("csv_delimiter") or ",")
    return SheetLayout(
        name=str(raw.get("name") or "etrm_entry_sheet"),
        title=str(raw.get("title") or "ETRM entry sheet"),
        sheet_name=str(raw.get("sheet_name") or "ETRM entry")[:31],
        columns=tuple(columns),
        include_header=bool(raw.get("include_header", True)),
        csv_delimiter="\t" if delimiter == "\\t" else delimiter[:1],
        date_format=str(raw.get("date_format") or "%Y-%m-%d"),
        datetime_format=str(raw.get("datetime_format") or "%Y-%m-%d %H:%M"),
        timezone=str(raw.get("timezone") or "UTC"),
        decimal_separator=str(raw.get("decimal_separator") or "."),
        include_cancelled=bool(raw.get("include_cancelled", False)),
        etrm_system=str(export.get("system") or "ETRM"),
        etrm_reference_column=str(export.get("reference_column") or "").strip(),
        source_path=source_path,
    )


def load_layout(path: Path) -> SheetLayout:
    return parse_layout(path.read_text(encoding="utf-8"), source_path=str(path))


def _zone(name: str):
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def cell(layout: SheetLayout, column: SheetColumn, deal: dict[str, Any]) -> Any:
    """One cell: the fixed value, or the deal's value through the column's rules."""

    if column.field is None:
        return column.value or ""
    value = deal.get(column.field)
    if column.values:
        key = str(value).casefold() if not isinstance(value, bool) else str(value).casefold()
        if key in column.values:
            return column.values[key]
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.astimezone(_zone(layout.timezone)).strftime(layout.datetime_format)
    if isinstance(value, date):
        return value.strftime(layout.date_format)
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, Decimal):
        shown = value
        if column.decimals is not None:
            shown = value.quantize(Decimal(1).scaleb(-column.decimals))
        if column.number:
            return shown
        text = format(shown, "f")
        return text.replace(".", layout.decimal_separator) if layout.decimal_separator != "." \
            else text
    return str(value)


def sheet_rows(layout: SheetLayout, deals: list[dict[str, Any]]) -> list[list[Any]]:
    """The body rows, in the order of ``deals`` (cancelled ones left out unless asked)."""

    return [
        [cell(layout, column, deal) for column in layout.columns]
        for deal in deals
        if layout.include_cancelled or deal.get("status") != "cancelled"
    ]


def sheet_csv(layout: SheetLayout, deals: list[dict[str, Any]]) -> bytes:
    """The sheet as CSV (UTF-8 with a byte-order mark, which Excel reads as UTF-8)."""

    from eurogas_nexus.core.csv_safety import neutralise

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=layout.csv_delimiter, lineterminator="\r\n")
    if layout.include_header:
        writer.writerow([column.header for column in layout.columns])
    for row in sheet_rows(layout, deals):
        writer.writerow([
            (format(value, "f").replace(".", layout.decimal_separator)
             if isinstance(value, Decimal) else neutralise(str(value)))
            for value in row
        ])
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def sheet_xlsx(layout: SheetLayout, deals: list[dict[str, Any]], about: list[tuple[str, str]]
               ) -> bytes:
    from eurogas_nexus.core.report_files import xlsx_workbook

    header = [column.header for column in layout.columns] if layout.include_header else []
    return xlsx_workbook([(layout.sheet_name, header, sheet_rows(layout, deals))], about=about)
