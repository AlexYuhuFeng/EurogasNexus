"""Read one exchange export with its format into canonical deals, reporting every bad row.

The engine is the same for every layout: find the header, read each row through the
format's column and value tables, apply the format's adapter hook if it names one, and
build a :class:`CanonicalDeal` in exact decimals. A row that cannot be read becomes a
:class:`RowProblem` with its line, a reason code, the field and the value; it is never
dropped silently. Volumes become total MWh over the delivery period on the hub's gas-day
calendar (a 23- or 25-hour day counts as such); prices stay in the quoted unit, and the
per-MWh price in the hub's currency is derived when a reader needs it.

逐行读取导出文件；无法读取的行附行号、原因与字段，绝不静默丢弃。数量按燃气日历折算为 MWh。
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from eurogas_nexus.domain.deals.formats import DealFormat
from eurogas_nexus.domain.deals.record import (
    INSTRUMENTS,
    CanonicalDeal,
    ParsedFile,
    RowProblem,
)

MAX_ROWS = 50_000
_CANCELLED = {"cancelled", "canceled", "deleted", "void", "voided", "withdrawn", "cancel"}
_BUY = {"buy", "b", "bought", "bid", "long", "purchase", "kauf", "k"}
_SELL = {"sell", "s", "sold", "offer", "ask", "short", "sale", "verkauf", "v"}
_TRUE = {"yes", "y", "true", "1", "cleared", "clr", "physical", "phys", "x"}
_FALSE = {"no", "n", "false", "0", "bilateral", "otc", "financial", "fin", "cash", ""}
#: Volume units a deal may state, and what one of them is.
VOLUME_UNITS = ("MW", "MWh/d", "MWh", "th/d", "th", "kWh/h", "lots")
_UNIT_ALIASES = {
    "mw": "MW", "mwh/h": "MW", "mw/h": "MW", "mwh/d": "MWh/d", "mwh/day": "MWh/d",
    "mwh": "MWh", "th/d": "th/d", "therm/d": "th/d", "therms/day": "th/d", "th/day": "th/d",
    "thm/d": "th/d", "th": "th", "therm": "th", "therms": "th", "kwh/h": "kWh/h",
    "lot": "lots", "lots": "lots", "contracts": "lots", "contract": "lots",
}  # fmt: skip
_PRICE_ALIASES = {
    "p/th": "GBp/th", "p/therm": "GBp/th", "pence/therm": "GBp/th",
    "gbx/th": "GBp/th", "€/mwh": "EUR/MWh", "eur/mwh": "EUR/MWh", "gbp/mwh": "GBP/MWh",
    "usd/mmbtu": "USD/MMBtu", "gbp/therm": "GBP/th", "pence per therm": "GBp/th",
    "euro/mwh": "EUR/MWh", "eur per mwh": "EUR/MWh",
}  # fmt: skip
_MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
_PRODUCT_ALIASES = {
    "BALMO": "BOM", "BALMONTH": "BOM", "BALANCEOFMONTH": "BOM", "BAL-MONTH": "BOM",
    "DAYAHEAD": "DA", "DAY-AHEAD": "DA", "D+1": "DA", "NEXTDAY": "DA",
    "WITHINDAY": "WD", "WITHIN-DAY": "WD", "WEEKEND": "WE", "WKND": "WE",
}  # fmt: skip
_ISO_MONTH = re.compile(r"^(\d{4})-?(\d{2})$")
_SEASON_WORD = re.compile(r"^(SUMMER|WINTER)-?(\d{2}|\d{4})$")


class RowError(ValueError):
    def __init__(self, code: str, message: str, field: str | None = None,
                 value: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.field = field
        self.value = value


@dataclass
class Row:
    """One row as the engine reads it: the file's cells and the values a hook set."""

    line: int
    cells: dict[str, str]
    headers: list[str]
    overrides: dict[str, str]
    fmt: DealFormat

    def raw(self, canonical: str) -> str:
        if canonical in self.overrides:
            return self.overrides[canonical]
        header = self.fmt.header_for(canonical, self.headers)
        value = (self.cells.get(header) or "").strip() if header else ""
        if not value:
            value = self.fmt.defaults.get(canonical, "")
        return value

    def get(self, canonical: str) -> str:
        return self.fmt.mapped(canonical, self.raw(canonical)).strip()

    def column(self, *names: str) -> str:
        """A raw cell by one of its header spellings (for adapter hooks)."""

        wanted = {" ".join(n.split()).casefold() for n in names}
        for header in self.headers:
            if " ".join(header.split()).casefold() in wanted:
                return (self.cells.get(header) or "").strip()
        return ""


Hook = Callable[[Row], None]


# ----------------------------------------------------------------------------- reading


def decode(content: bytes) -> str:
    """Text of an export: UTF-8 (with or without a byte-order mark), else Windows-1252."""

    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("latin-1")


def read_table(text: str, fmt: DealFormat) -> tuple[list[str], list[tuple[int, list[str]]]]:
    """The header row and the data rows (with their line numbers) of a delimited file."""

    reader = csv.reader(io.StringIO(text.lstrip("﻿")), delimiter=fmt.delimiter)
    header: list[str] | None = None
    rows: list[tuple[int, list[str]]] = []
    for index, raw in enumerate(reader, start=1):
        if index < fmt.header_line:
            continue
        if header is None:
            if not any(cell.strip() for cell in raw):
                continue  # blank lines before the header
            header = [cell.strip() for cell in raw]
            continue
        if not any((cell or "").strip() for cell in raw):
            continue
        rows.append((reader.line_num, raw))
        if len(rows) > MAX_ROWS:
            raise RowError("file_too_large", f"more than {MAX_ROWS} rows")
    return header or [], rows


def parse_deal_file(
    content: bytes | str,
    fmt: DealFormat,
    *,
    file_name: str,
    default_trader: str = "",
    book_id: str | None = None,
) -> ParsedFile:
    """Every deal in the file and every row that could not be read."""

    text = decode(content) if isinstance(content, bytes) else content
    result = ParsedFile(format_name=fmt.name)
    try:
        headers, rows = read_table(text, fmt)
    except RowError as exc:
        result.problems.append(RowProblem(0, exc.code, str(exc)))
        return result
    except csv.Error as exc:
        result.problems.append(RowProblem(0, "file_unreadable", f"not a delimited file: {exc}"))
        return result
    if not headers:
        result.problems.append(RowProblem(0, "file_empty", "the file has no header row"))
        return result
    missing = [
        name for name in ("venue_trade_id", "side", "volume", "price")
        if fmt.header_for(name, headers) is None and name not in fmt.defaults
    ]
    if missing:
        expected = "; ".join(f"{name}: {' / '.join(fmt.columns.get(name, ()))}" for name in missing)
        result.problems.append(
            RowProblem(0, "columns_missing",
                       f"the file has no column for {', '.join(missing)} (expected {expected})")
        )
        return result
    hook = HOOKS.get(fmt.adapter)
    for line, raw in rows:
        result.rows += 1
        text_row = fmt.delimiter.join(raw)[:2000]
        if len(raw) > len(headers) and any(cell.strip() for cell in raw[len(headers):]):
            result.problems.append(RowProblem(
                line, "column_count", f"{len(raw)} cells for {len(headers)} columns",
                raw=text_row))
            continue
        cells = {name: (raw[i] if i < len(raw) else "") for i, name in enumerate(headers)}
        row = Row(line=line, cells=cells, headers=headers, overrides={}, fmt=fmt)
        try:
            if hook is not None:
                hook(row)
            deal = canonical_deal(row, file_name=file_name, default_trader=default_trader,
                                  book_id=book_id)
        except RowError as exc:
            result.problems.append(RowProblem(line, exc.code, str(exc), exc.field, exc.value,
                                              raw=text_row))
            continue
        result.deals.append(deal)
    return result


# ----------------------------------------------------------------------------- values


def number(text: str, fmt: DealFormat | None, field: str) -> Decimal:
    """An exact decimal from export text: separators per the format, ``(1,000)`` negative."""

    value = (text or "").strip().replace(" ", "").replace(" ", "")
    if not value:
        raise RowError("value_missing", f"{field} is empty", field, text)
    negative = value.startswith("(") and value.endswith(")")
    if negative:
        value = value[1:-1]
    thousands = fmt.thousands_separator if fmt else ","
    decimal_sep = fmt.decimal_separator if fmt else "."
    if thousands:
        value = value.replace(thousands, "")
    if decimal_sep != ".":
        value = value.replace(decimal_sep, ".")
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        raise RowError("number_invalid", f"{field} {text!r} is not a number", field, text) from None
    if not parsed.is_finite():
        raise RowError("number_invalid", f"{field} {text!r} is not a number", field, text)
    return -parsed if negative else parsed


def flag(text: str, field: str) -> bool:
    key = (text or "").strip().casefold()
    if key in _TRUE:
        return True
    if key in _FALSE:
        return False
    raise RowError("flag_invalid", f"{field} {text!r} is not yes or no", field, text)


def parse_day(text: str, fmt: DealFormat | None, field: str) -> date:
    value = (text or "").strip()
    if not value:
        raise RowError("value_missing", f"{field} is empty", field, text)
    formats = (fmt.date_formats if fmt else ()) + ("%Y-%m-%d",)
    for pattern in formats:
        try:
            return datetime.strptime(value[: len(value)], pattern).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        raise RowError("date_invalid", f"{field} {text!r} is not a date this format reads",
                       field, text) from None


def parse_instant(text: str, day: date | None, fmt: DealFormat) -> datetime | None:
    """The trade instant in UTC from a date-time or a time with the trade date."""

    value = (text or "").strip()
    if not value:
        return None
    try:
        zone = ZoneInfo(fmt.timezone)
    except ZoneInfoNotFoundError:
        zone = ZoneInfo("UTC")
    parsed: datetime | None = None
    for pattern in fmt.datetime_formats:
        try:
            parsed = datetime.strptime(value, pattern)
            break
        except ValueError:
            continue
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
    if parsed is None and day is not None:
        for pattern in ("%H:%M:%S", "%H:%M:%S.%f", "%H:%M"):
            try:
                clock = datetime.strptime(value, pattern).time()
            except ValueError:
                continue
            parsed = datetime.combine(day, clock)
            break
    if parsed is None:
        raise RowError("time_invalid", f"trade time {text!r} is not a time this format reads",
                       "trade_time", text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=zone)
    return parsed.astimezone(UTC)


def side_of(text: str) -> str:
    key = (text or "").strip().casefold()
    if key in _BUY:
        return "buy"
    if key in _SELL:
        return "sell"
    raise RowError("side_invalid", f"side {text!r} is neither buy nor sell", "side", text)


def volume_unit_of(text: str) -> str:
    key = (text or "").strip().casefold().replace(" ", "")
    unit = _UNIT_ALIASES.get(key)
    if unit is None:
        raise RowError("unit_unknown", f"volume unit {text!r} is not one of "
                       f"{', '.join(VOLUME_UNITS)}", "volume_unit", text)
    return unit


def price_unit_of(text: str, currency: str) -> str:
    """The price unit as the units authority spells it (``GBp/th``, ``EUR/MWh``)."""

    from eurogas_nexus.domain.ontology.quantity import UnitError, convert_price

    raw = (text or "").strip()
    # As written first (GBp/th is pence, GBP/th pounds: the case matters), then an alias.
    for unit in (raw, _PRICE_ALIASES.get(raw.casefold(), "")):
        if not unit:
            continue
        try:
            convert_price(1.0, unit, f"{currency}/MWh")
        except (UnitError, ValueError):
            continue
        return unit
    raise RowError("price_unit_invalid",
                   f"price unit {text!r} is not a {currency} price per energy unit",
                   "price_unit", text)


def price_currency(unit: str) -> str:
    head = unit.split("/", 1)[0]
    return "GBP" if head in {"GBp", "GBX", "p"} else head.upper()


# ----------------------------------------------------------------------------- period


@dataclass(frozen=True)
class Period:
    label: str
    first: date
    last: date
    hours: Decimal

    @property
    def gas_days(self) -> int:
        return (self.last - self.first).days + 1


def period_hours(first: date, last: date, calendar: str) -> Decimal:
    from eurogas_nexus.domain.market.gas_day import gas_day_start_for_date

    start = gas_day_start_for_date(first, calendar)
    end = gas_day_start_for_date(last + timedelta(days=1), calendar)
    return Decimal(int((end - start).total_seconds())) / Decimal(3600)


def product_code(text: str) -> str:
    """An export's product text as a desk code ``resolve_product`` reads."""

    key = (text or "").strip().upper().replace(" ", "").replace("_", "")
    key = _PRODUCT_ALIASES.get(key, key)
    iso = _ISO_MONTH.match(key)
    if iso and 1 <= int(iso.group(2)) <= 12:
        return f"{_MONTHS[int(iso.group(2)) - 1]}-{iso.group(1)[2:]}"
    season = _SEASON_WORD.match(key)
    if season:
        return f"{'SUM' if season.group(1) == 'SUMMER' else 'WIN'}-{season.group(2)[-2:]}"
    return key


def label_for(first: date, last: date) -> str:
    """The desk label of a delivery period given by dates (``Dec-26``, ``Q1-27``, a day)."""

    if first == last:
        return f"{first.day:02d}-{_MONTHS[first.month - 1].title()}-{first.year % 100:02d}"
    month_end = (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    if first.day == 1 and last == month_end:
        return f"{_MONTHS[first.month - 1].title()}-{first.year % 100:02d}"
    span = (last.year - first.year) * 12 + last.month - first.month + 1
    next_day = last + timedelta(days=1)
    if first.day == 1 and next_day.day == 1:
        if span == 3 and first.month in (1, 4, 7, 10):
            return f"Q{(first.month - 1) // 3 + 1}-{first.year % 100:02d}"
        if span == 6 and first.month == 4:
            return f"Sum-{first.year % 100:02d}"
        if span == 6 and first.month == 10:
            return f"Win-{first.year % 100:02d}"
        if span == 12 and first.month == 1:
            return f"Cal-{first.year % 100:02d}"
        if span == 12 and first.month == 10:
            return f"GY-{first.year % 100:02d}"
    if first.weekday() == 5 and last == first + timedelta(days=1):
        return f"WE {first.day:02d}-{_MONTHS[first.month - 1].title()}"
    return (f"{first.day:02d}-{_MONTHS[first.month - 1].title()}-{first.year % 100:02d}.."
            f"{last.day:02d}-{_MONTHS[last.month - 1].title()}-{last.year % 100:02d}")


def resolve_period(row: Row, trade_date: date, calendar: str) -> Period:
    from eurogas_nexus.domain.market.products import ProductCodeError, resolve_product

    start_text, end_text = row.get("delivery_start"), row.get("delivery_end")
    if start_text and end_text:
        first = parse_day(start_text, row.fmt, "delivery_start")
        last = parse_day(end_text, row.fmt, "delivery_end")
        if not row.fmt.end_inclusive:
            last -= timedelta(days=1)
        if last < first:
            raise RowError("period_reversed", "delivery end is before delivery start",
                           "delivery_end", end_text)
        # The desk label from the dates (Dec-26, Q1-27), whatever the export calls it.
        return Period(label_for(first, last), first, last, period_hours(first, last, calendar))
    text = row.get("product")
    if not text:
        raise RowError("value_missing", "neither a product nor delivery dates are given",
                       "product", text)
    try:
        period = resolve_product(product_code(text), trade_date, calendar=calendar)
    except ProductCodeError as exc:
        raise RowError("product_unknown", f"product {text!r}: {exc}", "product", text) from None
    return Period(period.label, period.first_gas_day, period.last_gas_day,
                  Decimal(int(round(period.hours * 3600))) / Decimal(3600))


# ----------------------------------------------------------------------------- quantity


def factor(from_unit: str, to_unit: str) -> Decimal:
    """The units authority's factor as an exact decimal (therms from its BTU definition)."""

    from eurogas_nexus.domain.ontology.quantity import BTU_JOULES, convert

    if (from_unit, to_unit) == ("th", "MWh"):
        return Decimal(repr(BTU_JOULES)) * Decimal(100_000) / Decimal(3_600_000_000)
    return Decimal(repr(convert(1.0, from_unit, to_unit)))


def price_factor(unit: str, target: str) -> Decimal:
    from eurogas_nexus.domain.ontology.quantity import convert_price

    return Decimal(repr(convert_price(1.0, unit, target)))


def total_mwh(volume: Decimal, unit: str, period: Period) -> Decimal:
    """MWh delivered over the period by ``volume`` in ``unit`` (lots resolved before)."""

    if unit == "MW":
        return volume * period.hours
    if unit == "kWh/h":
        return volume * period.hours / Decimal(1000)
    if unit == "MWh/d":
        return volume * period.gas_days
    if unit == "MWh":
        return volume
    if unit == "th/d":
        return volume * period.gas_days * factor("th", "MWh")
    if unit == "th":
        return volume * factor("th", "MWh")
    raise RowError("unit_unknown", f"volume unit {unit!r} is not supported", "volume_unit", unit)


def lot_size(fmt: DealFormat, hub: str) -> tuple[Decimal, str]:
    """One lot of ``hub`` as (amount, unit) from the format's ``[lot_sizes]``."""

    text = fmt.lot_sizes.get(hub.upper()) or fmt.lot_sizes.get("*") or ""
    parts = text.split()
    if len(parts) != 2:
        raise RowError("lot_size_missing",
                       f"the volume is in lots and the format gives no lot size for {hub}",
                       "volume_unit", "lots")
    amount = number(parts[0], None, "lot size")
    return amount, volume_unit_of(parts[1])


# ----------------------------------------------------------------------------- deal


def canonical_deal(row: Row, *, file_name: str | None, default_trader: str = "",
                   book_id: str | None = None, origin: str = "file",
                   entered_by_hand: tuple[str, ...] = ()) -> CanonicalDeal:
    """One canonical deal from one row; raises :class:`RowError` with the reason."""

    from eurogas_nexus.domain.ontology.boundary import check_boundary

    fmt = row.fmt
    trade_id = row.get("venue_trade_id")
    if not trade_id:
        raise RowError("value_missing", "the trade id is empty", "venue_trade_id", "")
    venue = (row.get("venue") or fmt.venue).upper()[:32]
    trade_time_text = row.get("trade_time")
    day_text = row.get("trade_date")
    trade_day = parse_day(day_text, fmt, "trade_date") if day_text else None
    instant = parse_instant(trade_time_text, trade_day, fmt)
    if trade_day is None:
        if instant is None:
            raise RowError("value_missing", "neither a trade date nor a trade time is given",
                           "trade_date", "")
        trade_day = instant.astimezone(ZoneInfo(fmt.timezone)).date()
    hub_text = row.get("hub")
    checked = check_boundary(market=hub_text, gas_hub_required=True)
    if checked.market is None or not checked.ok:
        raise RowError("hub_unknown", f"{hub_text!r} is not a gas hub", "hub", hub_text)
    market = checked.market
    side = side_of(row.get("side"))
    period = resolve_period(row, trade_day, market.calendar)
    volume = number(row.get("volume"), fmt, "volume")
    unit = volume_unit_of(row.get("volume_unit") or ("th/d" if market.currency == "GBP" else
                                                     "MW"))
    if unit == "lots":
        size, unit = lot_size(fmt, market.code)
        volume = volume * size
    if volume < 0:
        # Some exports sign the volume instead of a side column: the side already says it.
        volume = -volume
    if volume == 0:
        raise RowError("volume_not_positive", "the volume is zero", "volume", row.get("volume"))
    total = total_mwh(volume, unit, period).quantize(Decimal("0.000001"))
    default_unit = "GBp/th" if market.currency == "GBP" else f"{market.currency}/MWh"
    price_unit = price_unit_of(row.get("price_unit") or default_unit, market.currency)
    price = number(row.get("price"), fmt, "price")
    counterparty = row.get("counterparty")[:160]
    cleared_text = row.get("cleared")
    cleared = flag(cleared_text, "cleared") if cleared_text else not counterparty
    physical_text = row.get("physical")
    physical = flag(physical_text, "physical") if physical_text else False
    instrument = (row.get("instrument") or ("future" if cleared else "forward")).casefold()
    if instrument not in INSTRUMENTS:
        if "option" in instrument or instrument in {"call", "put"}:
            instrument = "option"
        elif "swap" in instrument:
            instrument = "swap"
        elif "spot" in instrument:
            instrument = "spot"
        elif "fut" in instrument:
            instrument = "future"
        else:
            raise RowError("instrument_unknown",
                           f"instrument {instrument!r} is not one of {', '.join(INSTRUMENTS)}",
                           "instrument", instrument)
    fees_text = row.get("fees")
    fees = number(fees_text, fmt, "fees") if fees_text else None
    status_text = row.get("status")
    status = "cancelled" if status_text.casefold() in _CANCELLED else "live"
    trader = (row.get("trader") or default_trader)[:128]
    if not trader:
        raise RowError("value_missing", "the trader is empty", "trader", "")
    book = row.get("book") or book_id
    return CanonicalDeal(
        venue=venue,
        venue_trade_id=trade_id[:128],
        leg_id=row.get("leg_id")[:16],
        trade_date=trade_day,
        trade_time_utc=instant,
        trader=trader,
        counterparty=counterparty,
        cleared=cleared,
        hub=market.code,
        product=period.label[:32],
        delivery_start=period.first,
        delivery_end=period.last,
        side=side,
        volume=volume,
        volume_unit=unit,
        total_mwh=total,
        price=price,
        price_currency=price_currency(price_unit),
        price_unit=price_unit,
        physical=physical,
        instrument=instrument,
        fees=fees,
        fee_currency=(row.get("fee_currency") or price_currency(price_unit)).upper()[:3]
        if fees is not None else None,
        status=status,
        book_id=(book or None),
        origin=origin,
        source_file=file_name,
        source_line=row.line if origin == "file" else None,
        entered_by_hand=entered_by_hand,
    )


def price_per_mwh(deal: CanonicalDeal) -> Decimal:
    """The deal's price in its currency per MWh (``GBp/th`` to ``GBP/MWh``), exact factor."""

    return deal.price * price_factor(deal.price_unit, f"{deal.price_currency}/MWh")


# ----------------------------------------------------------------------------- hooks

_TENOR = {"M": "month", "Q": "quarter", "S": "season", "Y": "year", "D": "day", "W": "weekend"}


def _eex_hook(row: Row) -> None:
    """EEX: a product id ending in its tenor letter plus the contract's month and year.

    The T7 daily trade confirmation names a derivative by product id (for example ``G3BM``,
    the last letter the tenor) and the contract's expiry month and year, not by a desk label;
    this hook turns those into ``Dec-26``, ``Q1-27``, ``Win-26`` or ``Cal-27`` when the file
    has no product or delivery-date column. Spot trades carry their delivery day instead.
    """

    if row.get("product") or (row.get("delivery_start") and row.get("delivery_end")):
        return
    month_text = row.column("cntrExpMthDat", "Expiry Month", "Contract Month", "Delivery Month")
    year_text = row.column("cntrExpYrDat", "Expiry Year", "Contract Year", "Delivery Year")
    product_id = row.column("prodId", "Product ID", "Product", "Product Code")
    delivery_day = row.column("Delivery Day", "Delivery Date", "dlvyDat")
    if delivery_day:
        row.overrides["delivery_start"] = delivery_day
        row.overrides["delivery_end"] = delivery_day
        return
    if not (month_text and year_text):
        return
    try:
        month, year = int(month_text), int(year_text)
    except ValueError:
        raise RowError("product_unknown", f"contract month {month_text!r}/{year_text!r} "
                       "is not a month and a year", "product", f"{month_text}/{year_text}"
                       ) from None
    if not 1 <= month <= 12:
        raise RowError("product_unknown", f"contract month {month_text!r} is not 1 to 12",
                       "product", month_text)
    yy = f"{year % 100:02d}"
    tenor = _TENOR.get(product_id[-1:].upper(), "month")
    if tenor == "quarter":
        row.overrides["product"] = f"Q{(month - 1) // 3 + 1}-{yy}"
    elif tenor == "season":
        row.overrides["product"] = f"{'Sum' if 4 <= month <= 9 else 'Win'}-{yy}"
    elif tenor == "year":
        row.overrides["product"] = f"Cal-{yy}"
    else:
        row.overrides["product"] = f"{_MONTHS[month - 1].title()}-{yy}"


def _ice_hook(row: Row) -> None:
    """ICE: a deal report states lots and a total quantity; a clearing venue means cleared.

    When both are present the total quantity with its unit is used (it already includes the
    lot size), so a lot size need not be configured; a non-empty clearing venue other than a
    bilateral marker makes the deal cleared.
    """

    total = row.column("Total Quantity", "Total Qty")
    unit = row.column("Qty Units", "Quantity Units", "Total Quantity Units")
    if total and unit:
        row.overrides["volume"] = total
        row.overrides["volume_unit"] = row.fmt.mapped("volume_unit", unit)
    venue = row.column("Clearing Venue", "Clearing House")
    if "cleared" not in row.overrides and not row.raw("cleared"):
        row.overrides["cleared"] = "no" if venue.casefold() in {"", "bilateral", "otc",
                                                                 "none"} else "yes"


HOOKS: dict[str, Hook] = {"eex": _eex_hook, "ice": _ice_hook}


def hand_entry_row(fmt: DealFormat, values: dict[str, str]) -> Row:
    """A manual deal as a row of the built-in ``manual`` layout (same checks as a file)."""

    headers = list(values)
    return Row(line=0, cells=dict(values), headers=headers, overrides={}, fmt=fmt)


def as_of_time(day: date) -> datetime:
    return datetime.combine(day, time(0), tzinfo=UTC)
