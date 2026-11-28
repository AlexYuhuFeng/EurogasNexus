"""Read the exchanges' published trading calendars, fetched under written consent (2026-11-28).

Three publishers, four documents, each read into an :class:`ExchangeCalendar` for one venue of
the desk's calendar file (``reference_data/desk/trading_calendars.toml``, which stays as the
fallback while nothing has been fetched):

- **EEX natural gas trading calendar** (``.xlsx`` linked from EEX's trading calendar page):
  the sheet ``<year> Natural Gas Holidays`` lists the exchange holidays of the natural gas
  futures (column "Exchange Holidays - Natural Gas Futures"), and the ``Physical Futures``
  sheet each maturity's last trading day (the expiry).
- **EEX holiday calendar, derivatives** (``.pdf`` on the same page): the footnote that gas
  derivatives trade on 24 and 31 December from 08:00 to 13:00 CET. This is what settles the
  question the hand file left open: on those two days EEX gas trades shorter hours; it is
  not closed.
- **ICE Endex trading schedule** (``ICE_Endex_Trading_Schedule.pdf``): each listed day with
  "Closed" or the key letters of its early settlement and early close.
- **ICE Futures Europe trading schedule** (``Trading_Schedule.pdf``): the days UK natural gas
  is closed ("UK Natural Gas and Power Contracts Closed", or the whole exchange), and in the
  Christmas appendix the shortened settlement period of UK natural gas.

A layout the parser was not written for raises :class:`CalendarUncertain`; nothing is guessed
and the held record (or the hand file) stays in use until a person has looked.

Import-safe: no database, web or network import (``pypdf`` is a declared dependency).

交易所日历解析（经书面同意获取）：EEX 天然气交易日历与假日日历、ICE Endex 与 ICE 欧洲期货交易安排；
版式不符时不猜测。
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from datetime import date
from html import unescape
from urllib.parse import urljoin, urlsplit

from eurogas_nexus.domain.publications.xlsx import SpreadsheetError, excel_day, read_workbook

_MONTHS = {name: index for index, name in enumerate(
    ("january", "february", "march", "april", "may", "june", "july", "august", "september",
     "october", "november", "december"), start=1)}
_WEEKDAYS = "Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday"


class CalendarUncertain(ValueError):
    """The document is not in the layout the parser was written for."""


@dataclass(frozen=True)
class Expiry:
    """One maturity's last trading day, as the exchange publishes it."""

    maturity: str
    kind: str
    last_trading_day: date
    delivery_start: date

    def to_json(self) -> dict:
        return {"maturity": self.maturity, "kind": self.kind,
                "last_trading_day": self.last_trading_day.isoformat(),
                "delivery_start": self.delivery_start.isoformat()}


@dataclass(frozen=True)
class ExchangeCalendar:
    """One venue's published calendar: closed weekdays, early closes and expiries."""

    venue: str
    years: tuple[int, ...]
    closed: tuple[tuple[date, str], ...]
    early_closes: tuple[tuple[date, str], ...] = ()
    expiries: tuple[Expiry, ...] = ()
    #: The document's own version or date, when it states one.
    version: str = ""
    #: Rules that apply every year ("24 and 31 December: 08:00-13:00 CET").
    standing: tuple[str, ...] = field(default_factory=tuple)

    def to_json(self) -> dict:
        return {
            "venue": self.venue,
            "years": list(self.years),
            "closed": [{"day": d.isoformat(), "what": what} for d, what in self.closed],
            "early_closes": [{"day": d.isoformat(), "what": what}
                             for d, what in self.early_closes],
            "expiries": [e.to_json() for e in self.expiries],
            "version": self.version,
            "standing": list(self.standing),
        }


def _pdf_text(data: bytes) -> str:
    if not data.startswith(b"%PDF"):
        raise CalendarUncertain("not a PDF document")
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError

        reader = PdfReader(io.BytesIO(data))
        if len(reader.pages) > 60:
            raise CalendarUncertain("the PDF has more pages than a trading schedule")
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except (PdfReadError, ValueError, KeyError) as exc:
        raise CalendarUncertain(f"the PDF cannot be read: {exc.__class__.__name__}") from exc


def _links(html: str, base_url: str) -> list[str]:
    return [urljoin(base_url, unescape(href))
            for href in re.findall(r'href="([^"]+)"', html, flags=re.IGNORECASE)]


# ------------------------------------------------------------------------------------ EEX

EEX_HOST = "www.eex.com"


def eex_document_link(page: bytes, base_url: str, *, kind: str) -> str:
    """The calendar document EEX's page links: ``gas`` (the natural gas ``.xlsx``) or
    ``holidays`` (the derivatives holiday ``.pdf``), on EEX's own host only."""

    html = page.decode("utf-8", "replace")
    pattern = {
        "gas": r"/Natural_Gas_Trading_Calendar/[^/]*NaturalGasTradingCalendar(\d{4})\.xlsx$",
        "holidays": r"/Holiday_Calendar/[^/]*Derivatives[^/]*\.pdf$",
    }[kind]
    found = []
    for link in _links(html, base_url):
        parts = urlsplit(link)
        if parts.scheme != "https" or parts.netloc != EEX_HOST:
            continue
        match = re.search(pattern, parts.path)
        if match:
            found.append((int(match.group(1)) if match.groups() else 0, link))
    if not found:
        raise CalendarUncertain(f"EEX's calendar page links no {kind} calendar")
    return max(found)[1]


def parse_eex_gas_calendar(data: bytes) -> ExchangeCalendar:
    """EEX's natural gas trading calendar workbook (see the module text)."""

    try:
        sheets = read_workbook(data)
    except SpreadsheetError as exc:
        raise CalendarUncertain(f"not a readable workbook: {exc}") from exc
    holidays = next((s for s in sheets if re.fullmatch(r"\d{4} Natural Gas Holidays",
                                                       s.name.strip())), None)
    if holidays is None:
        raise CalendarUncertain("no '<year> Natural Gas Holidays' sheet")
    year = int(holidays.name.strip()[:4])
    rows = holidays.rows()
    column = None
    head_row = None
    for number, cells in sorted(rows.items()):
        for col, value in cells.items():
            if value.strip().lower() == "exchange holidays - natural gas futures":
                column, head_row = col, number
    if column is None:
        raise CalendarUncertain("no 'Exchange Holidays - Natural Gas Futures' column")
    name_col = chr(ord(column) + 1)
    closed: list[tuple[date, str]] = []
    started = False
    for number, cells in sorted(rows.items()):
        if number <= head_row:
            continue
        value = cells.get(column, "").strip()
        if value.lower() == "date":
            started = True
            continue
        if not started:
            continue
        if not value:
            if closed:
                break
            continue
        try:
            day = excel_day(value.split(".")[0])
        except SpreadsheetError:
            break  # the next table ("Natural Gas Futures - Tradable Contracts") starts
        if day.year != year:
            raise CalendarUncertain(f"a {day.year} holiday in the {year} sheet")
        closed.append((day, cells.get(name_col, "").strip() or "exchange holiday"))
    if not closed:
        raise CalendarUncertain("the natural gas futures holiday list is empty")
    expiries: list[Expiry] = []
    futures = next((s for s in sheets if s.name.strip() == "Physical Futures"), None)
    if futures is not None:
        for _number, cells in sorted(futures.rows().items()):
            kind = cells.get("B", "").strip()
            if kind not in {"Month", "Quarter", "Season", "Calendar"}:
                continue
            try:
                last = excel_day(cells.get("F", "").split(".")[0])
                start = excel_day(cells.get("G", "").split(".")[0])
            except SpreadsheetError:
                continue
            if start.year < year:
                continue
            expiries.append(Expiry(maturity=cells.get("C", "").strip(), kind=kind.lower(),
                                   last_trading_day=last, delivery_start=start))
    return ExchangeCalendar(venue="EEX", years=(year,), closed=tuple(sorted(closed)),
                            expiries=tuple(expiries), version=f"Natural Gas Trading Calendar "
                            f"{year}")


_EEX_SHORT = re.compile(
    r"Gas and Freight derivatives are offered for trading on (\d{1,2})\w* and (\d{1,2})\w* "
    r"December from (\d{2}:\d{2}) ?am to (\d{2}:\d{2}) CET", re.IGNORECASE)


def parse_eex_holiday_calendar(data: bytes, *, years: tuple[int, ...]) -> ExchangeCalendar:
    """EEX's derivatives holiday calendar: the shortened gas hours on 24 and 31 December.

    The document says it applies "continuously for all years until further notice", so the
    two days are stated for each of ``years`` (the years the desk's calendar covers).
    """

    text = re.sub(r"\s+", " ", _pdf_text(data))
    if "continuously for all years" not in text:
        raise CalendarUncertain("the holiday calendar no longer says it applies every year")
    match = _EEX_SHORT.search(text)
    if not match:
        raise CalendarUncertain("the gas footnote on 24 and 31 December was not found")
    first, second, start, end = match.groups()
    what = f"gas derivatives trade {start}-{end} CET only"
    early = tuple(sorted((date(y, 12, int(d)), what) for y in years for d in (first, second)))
    return ExchangeCalendar(venue="EEX", years=years, closed=(), early_closes=early,
                            standing=(f"{first} and {second} December: {what}",),
                            version="EEX Holiday Calendar, Derivatives and Emissions Spot")


# ------------------------------------------------------------------------------- ICE Endex

_ENDEX_LINE = re.compile(
    rf"^(?:{_WEEKDAYS}) (\d{{2}}) ([A-Za-z]+) (\d{{4}})\b(.*)$")


def parse_ice_endex_schedule(data: bytes) -> ExchangeCalendar:
    """ICE Endex's trading schedule: a day per line, "Closed" or key letters (A-D)."""

    text = _pdf_text(data)
    if "ICE ENDEX TRADING SCHEDULE" not in text.upper():
        raise CalendarUncertain("not the ICE Endex trading schedule")
    version = re.search(r"\bv ?(\d+\.\d+) \| ([A-Za-z]+ \d{4})", text)
    keys: dict[str, str] = {}
    key_text = text.split("Trading Schedule Key", 1)[1] if "Trading Schedule Key" in text else ""
    for letter, body in re.findall(r"^([A-D]): ([^\n]+(?:\n(?![A-D]: )[^\n]*){0,3})", key_text,
                                   flags=re.MULTILINE):
        flat = re.sub(r"\s+", " ", body).strip()
        if letter == "A":
            times = re.search(r"(\d{2}:\d{2}) ?- ?(\d{2}:\d{2}) \(CET\)", flat)
            keys[letter] = (f"early settlement {times.group(1)}-{times.group(2)} CET" if times
                            else "early settlement")
        else:
            close = re.search(r"Market Close at (\d{2}:\d{2}) CET", flat)
            if close:
                keys[letter] = f"market closes {close.group(1)} CET"
    if not keys:
        raise CalendarUncertain("the schedule key (A-D) was not found")
    lines = [line.strip() for line in text.splitlines()]
    closed: list[tuple[date, str]] = []
    early: list[tuple[date, str]] = []
    years: set[int] = set()
    index = 0
    while index < len(lines):
        match = _ENDEX_LINE.match(lines[index])
        if not match:
            index += 1
            continue
        day_text, month, year, rest = match.groups()
        if month.lower() not in _MONTHS:
            raise CalendarUncertain(f"month {month!r}")
        day = date(int(year), _MONTHS[month.lower()], int(day_text))
        block = [rest.strip()]
        index += 1
        while index < len(lines) and not _ENDEX_LINE.match(lines[index]) and lines[index] and \
                not lines[index].startswith(("ICE ENDEX", "©", "Year:", "2. ")):
            block.append(lines[index])
            index += 1
        words = " ".join(part for part in block if part).strip()
        status = words.rsplit(" ", 1)[-1] if words else ""
        occasion = words[: -len(status)].strip() if status else words
        years.add(day.year)
        if status == "Closed":
            closed.append((day, occasion or "closed"))
        elif re.fullmatch(r"[A-D]+", status):
            parts = [keys[letter] for letter in status if letter in keys]
            if len(parts) != len(status):
                raise CalendarUncertain(f"key letters {status!r} not all in the key")
            early.append((day, f"{occasion}: " + "; ".join(parts)))
        else:
            raise CalendarUncertain(f"status {status!r} for {day.isoformat()}")
    if not closed:
        raise CalendarUncertain("no closed day in the ICE Endex schedule")
    return ExchangeCalendar(venue="ICE_ENDEX", years=tuple(sorted(years)),
                            closed=tuple(sorted(closed)), early_closes=tuple(sorted(early)),
                            version=(f"v{version.group(1)} {version.group(2)}" if version
                                     else ""))


# ---------------------------------------------------------------------- ICE Futures Europe

_IFEU_DATE = re.compile(rf"(?:{_WEEKDAYS})\s+(\d{{1,2}})\s+([A-Z][a-z]+)(?:\s+(\d{{4}}))?")
_IFEU_GAS_WINDOW = re.compile(
    r"UK Natural Gas and Power Contracts\s+(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})\s*\(GMT\)"
    r"[^A-Za-z]*?\(ET\)\s+(\d{2}:\d{2})\s*\(GMT\)")


def _ifeu_blocks(section: str, year: int) -> list[tuple[date, str]]:
    """``(day, text)`` for each dated entry of one year's table (or of an appendix)."""

    matches = [m for m in _IFEU_DATE.finditer(section) if m.group(2).lower() in _MONTHS]
    out = []
    for position, match in enumerate(matches):
        end = matches[position + 1].start() if position + 1 < len(matches) else len(section)
        day = date(int(match.group(3) or year), _MONTHS[match.group(2).lower()],
                   int(match.group(1)))
        out.append((day, re.sub(r"\s+", " ", section[match.end():end]).strip()))
    return out


def parse_ifeu_schedule(data: bytes) -> ExchangeCalendar:
    """ICE Futures Europe's trading schedule, read for UK natural gas only."""

    text = _pdf_text(data)
    if "IFEU Trading Schedule" not in text:
        raise CalendarUncertain("not the IFEU trading schedule")
    version = re.search(r"IFEU Trading Schedule: [^|\n]+\| ([A-Za-z]+ \d{4})", text)
    # The appendices (Christmas and New Year hours) follow every year's table, each under a
    # line of its own; the tables only refer to them ("... Appendix 1" inside a line).
    sections = re.split(r"\n\s*Appendix \d\s*\n", text)
    main, appendix_parts = sections[0], sections[1:]
    year_parts = re.split(r"Year: (\d{4})", main)
    if len(year_parts) < 3:
        raise CalendarUncertain("no 'Year:' tables in the IFEU schedule")
    closed: list[tuple[date, str]] = []
    years: list[int] = []
    for position in range(1, len(year_parts) - 1, 2):
        year = int(year_parts[position])
        years.append(year)
        for day, block in _ifeu_blocks(year_parts[position + 1], year):
            occasion = re.split(r"\s+(?:UK|US|UK and US) Holiday|\s+TD\b|\s+[A-D]\b", block)[0]
            if re.search(r"Holiday(?: \(in lieu\))?\s+Closed\b", block) or \
                    "UK Natural Gas and Power Contracts Closed" in block:
                closed.append((day, occasion.strip() or "closed"))
    early: list[tuple[date, str]] = []
    for appendix in appendix_parts:
        for day, block in _ifeu_blocks(appendix, years[0] if years else date.today().year):
            except_list = re.search(r"EXCEPT for the following contracts:(.*)", block)
            if except_list and "UK Natural Gas and Power Contracts" in except_list.group(1):
                if day not in {d for d, _w in closed}:
                    closed.append((day, "UK natural gas closed (holiday hours appendix)"))
                continue
            match = _IFEU_GAS_WINDOW.search(block)
            if match and day not in {d for d, _w in closed}:
                early.append((day, f"UK natural gas settles {match.group(1)}-{match.group(2)} "
                                   f"GMT; trading ceases {match.group(3)} GMT"))
    if not closed:
        raise CalendarUncertain("no UK natural gas closed day in the IFEU schedule")
    first_closed: dict[date, str] = {}
    for day, what in closed:
        first_closed.setdefault(day, what)
    unique_early = tuple(sorted(dict(early).items()))
    return ExchangeCalendar(venue="ICE_FUTURES_EUROPE", years=tuple(sorted(set(years))),
                            closed=tuple(sorted(first_closed.items())), early_closes=unique_early,
                            version=version.group(1) if version else "")


__all__ = [
    "CalendarUncertain",
    "ExchangeCalendar",
    "Expiry",
    "eex_document_link",
    "parse_eex_gas_calendar",
    "parse_eex_holiday_calendar",
    "parse_ice_endex_schedule",
    "parse_ifeu_schedule",
]
