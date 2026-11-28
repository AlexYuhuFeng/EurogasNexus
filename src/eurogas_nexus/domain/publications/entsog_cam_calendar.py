"""ENTSOG's CAM network code auction calendar: find the current file and read its auctions.

ENTSOG publishes, by January each year, the "Auction Calendar" for capacity auctions from March
to February (Regulation (EU) 2017/459 Art. 3(15)), as an ``.xlsx`` file linked from
https://www.entsog.eu/capacity-allocation-mechanisms-nc (section "CAM NC early implementation
documents and auction calendar"). The file has one sheet per product: *Yearly*, *Quarterly*,
*Monthly* (each with a FIRM and an INTERRUPTIBLE table: publication date of the offer levels,
start date and start time in UTC, and the run and end date of each product offered), and
*Daily* and *Within-Day* (standing rules, not dated auctions).

:func:`calendar_link` picks the newest calendar file the page links; :func:`parse_calendar`
reads it into :class:`CalendarAuction` records. Either raises :class:`CalendarUncertain` when
the page or the file does not have the shape described here (a layout change, a renamed
sheet, too few auctions): the caller then keeps what it holds and asks a person to look, and
guesses nothing.

The format was read from ENTSOG's file ``MAR0369-25`` (2026/2027, version date 12 November
2025, read 2026-11-28); the test fixture is a small workbook written for the tests in the same
layout, not ENTSOG's file.

ENTSOG CAM 拍卖日历：找到最新文件并读取其拍卖；格式不符时不猜测，交由人工确认。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from urllib.parse import unquote, urljoin, urlsplit

from eurogas_nexus.domain.publications.xlsx import (
    Sheet,
    SpreadsheetError,
    clock_time,
    excel_day,
    read_workbook,
)

PAGE_URL = "https://www.entsog.eu/capacity-allocation-mechanisms-nc"
HOST = "www.entsog.eu"
ATTRIBUTION = "Source: ENTSOG and/or its members, CAM NC Auction Calendar"

ANNUAL = "ANNUAL"
QUARTERLY = "QUARTERLY"
MONTHLY = "MONTHLY"
_SHEETS = {"Yearly": ANNUAL, "Quarterly": QUARTERLY, "Monthly": MONTHLY}
#: Fewest firm auctions per sheet a whole calendar has (1 yearly, 4 quarterly, 12 monthly).
_MIN_FIRM = {ANNUAL: 1, QUARTERLY: 3, MONTHLY: 10}

_LINK = re.compile(r"""href=["']([^"']+\.xlsx)["']""", re.IGNORECASE)
_FILE_YEARS = re.compile(r"auction[\s_-]*calendar[\s_-]*(\d{4})[\s_/-]+(\d{4})", re.IGNORECASE)
_TITLE_YEARS = re.compile(r"auction calendar\s+(\d{4})\s*/\s*(\d{4})", re.IGNORECASE)
_DOCUMENT_ID = re.compile(r"[A-Z]{2,4}\d{3,5}-\d{2}")


class CalendarUncertain(ValueError):
    """The page or the file is not in the shape the parser knows: nothing is guessed."""


@dataclass(frozen=True)
class CalendarAuction:
    """One dated auction of the calendar."""

    product: str
    #: ``firm`` or ``interruptible``.
    capacity: str
    opens_at_utc: datetime
    #: The day the TSOs publish the offer levels (the calendar's "Publication Date").
    offer_levels_published_on: date | None
    #: First and last gas day of the capacity offered (the products' run dates).
    offers_from: date
    offers_to: date

    @property
    def key(self) -> str:
        return f"{self.capacity}:{self.product.lower()}:{self.offers_from.isoformat()}"

    def label(self) -> str:
        capacity = "firm" if self.capacity == "firm" else "interruptible"
        if self.product == MONTHLY:
            return f"Monthly auction, {capacity}: {self.offers_from:%B %Y}"
        if self.product == QUARTERLY:
            return f"Quarterly auction, {capacity}: quarters from {self.offers_from:%b %Y}"
        start = self.offers_from.year
        return f"Yearly auction, {capacity}: gas years from {start}/{(start + 1) % 100:02d}"

    def to_json(self) -> dict:
        return {
            "key": self.key,
            "product": self.product,
            "capacity": self.capacity,
            "opens_at_utc": self.opens_at_utc.isoformat(),
            "offer_levels_published_on": (
                self.offer_levels_published_on.isoformat()
                if self.offer_levels_published_on
                else None
            ),
            "offers_from": self.offers_from.isoformat(),
            "offers_to": self.offers_to.isoformat(),
            "label": self.label(),
        }


@dataclass(frozen=True)
class AuctionCalendar:
    """The calendar as read: its identity and its dated auctions."""

    document_id: str
    version: str
    #: The version date the file states ("Version date: November 12th 2025"), if readable.
    published_on: date | None
    status: str
    first_year: int
    last_year: int
    auctions: tuple[CalendarAuction, ...]
    #: The day-ahead and within-day rules, as the calendar states them (no dated auctions).
    standing_rules: tuple[str, ...]

    def to_json(self) -> dict:
        return {
            "document_id": self.document_id,
            "version": self.version,
            "published_on": self.published_on.isoformat() if self.published_on else None,
            "status": self.status,
            "years": [self.first_year, self.last_year],
            "auctions": [auction.to_json() for auction in self.auctions],
            "standing_rules": list(self.standing_rules),
        }


def calendar_link(page_html: str, *, base_url: str = PAGE_URL) -> tuple[str, int]:
    """``(url, first year)`` of the newest auction calendar file the page links."""

    best: tuple[int, str] | None = None
    for href in _LINK.findall(page_html):
        url = urljoin(base_url, href)
        name = unquote(urlsplit(url).path.rsplit("/", 1)[-1])
        match = _FILE_YEARS.search(name)
        if not match or urlsplit(url).hostname not in {HOST, "entsog.eu"}:
            continue
        first, last = int(match.group(1)), int(match.group(2))
        if last != first + 1:
            continue
        if best is None or first > best[0]:
            best = (first, url)
    if best is None:
        raise CalendarUncertain("the page links no auction calendar file")
    return best[1], best[0]


def _sheet(sheets: list[Sheet], name: str) -> Sheet:
    for sheet in sheets:
        if sheet.name.strip().lower() == name.lower():
            return sheet
    raise CalendarUncertain(f"the calendar has no {name!r} sheet")


_HEADERS = {
    "publication date": "published",
    "start date": "start",
    "start time (utc)": "time",
    "run date": "run",
    "end date": "end",
}


def _instant(day: date, value: str) -> datetime:
    hour, minute = clock_time(value)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=UTC)


def _read_sheet(sheet: Sheet, product: str) -> list[CalendarAuction]:
    out: list[CalendarAuction] = []
    capacity: str | None = None
    columns: dict[str, str] | None = None
    current: dict | None = None

    def close() -> None:
        nonlocal current
        if current is not None:
            if not current["runs"]:
                raise CalendarUncertain(f"{sheet.name}: an auction lists no product")
            out.append(
                CalendarAuction(
                    product=product,
                    capacity=current["capacity"],
                    opens_at_utc=current["opens"],
                    offer_levels_published_on=current["published"],
                    offers_from=min(start for start, _ in current["runs"]),
                    offers_to=max(end for _, end in current["runs"]),
                )
            )
        current = None

    for _number, row in sheet.rows().items():
        texts = {column: value.strip() for column, value in row.items()}
        lowered = {column: value.lower() for column, value in texts.items()}
        section = next(
            (value for value in lowered.values()
             if value.startswith("firm capacity") or value.startswith("interruptible capacity")),
            None,
        )
        if section is not None:
            close()
            capacity = "firm" if section.startswith("firm") else "interruptible"
            columns = None
            continue
        if "publication date" in lowered.values():
            close()
            columns = {
                _HEADERS[value]: column for column, value in lowered.items() if value in _HEADERS
            }
            if set(columns) != set(_HEADERS.values()):
                raise CalendarUncertain(f"{sheet.name}: the table's columns have changed")
            continue
        if columns is None or capacity is None:
            continue
        try:
            start_text = texts.get(columns["start"], "")
            if start_text:
                close()
                start = excel_day(start_text)
                published = texts.get(columns["published"], "")
                current = {
                    "capacity": capacity,
                    "opens": _instant(start, texts.get(columns["time"], "")),
                    "published": excel_day(published) if published else None,
                    "runs": [],
                }
            run_text, end_text = texts.get(columns["run"], ""), texts.get(columns["end"], "")
            if current is not None and run_text and end_text:
                run, end = excel_day(run_text), excel_day(end_text)
                if end <= run:
                    raise CalendarUncertain(f"{sheet.name}: a product ends before it runs")
                current["runs"].append((run, end - timedelta(days=1)))
            elif current is not None and not start_text and not run_text:
                close()
        except SpreadsheetError as exc:
            raise CalendarUncertain(f"{sheet.name}: {exc}") from exc
    close()
    return out


_MONTHS = {name: number for number, name in enumerate(
    ("january", "february", "march", "april", "may", "june", "july", "august", "september",
     "october", "november", "december"), start=1)}
_VERSION_DATE = re.compile(r"([A-Za-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})")


def _version_date(text: str) -> date | None:
    match = _VERSION_DATE.search(text)
    if not match or match.group(1).lower() not in _MONTHS:
        return None
    try:
        return date(int(match.group(3)), _MONTHS[match.group(1).lower()], int(match.group(2)))
    except ValueError:
        return None


def parse_calendar(data: bytes) -> AuctionCalendar:
    """Read the calendar file (see the module text); :class:`CalendarUncertain` if unsure."""

    try:
        sheets = read_workbook(data)
    except SpreadsheetError as exc:
        raise CalendarUncertain(str(exc)) from exc
    note = _sheet(sheets, "Explanatory note")
    title = next((v for v in note.cells.values() if _TITLE_YEARS.search(v)), "")
    years = _TITLE_YEARS.search(title)
    if not years:
        raise CalendarUncertain("the explanatory note does not name the calendar's years")
    first, last = int(years.group(1)), int(years.group(2))
    document_id = next(
        (v.strip() for v in note.cells.values() if _DOCUMENT_ID.fullmatch(v.strip())), ""
    )
    version = next((v.strip() for v in note.cells.values() if v.lower().startswith("version")), "")
    status = next(
        (v.strip() for v in note.cells.values() if v.strip().lower() in {"final", "draft"}), ""
    )
    auctions: list[CalendarAuction] = []
    for name, product in _SHEETS.items():
        found = _read_sheet(_sheet(sheets, name), product)
        firm = [item for item in found if item.capacity == "firm"]
        if len(firm) < _MIN_FIRM[product]:
            raise CalendarUncertain(
                f"{name}: {len(firm)} firm auctions, fewer than a whole calendar has"
            )
        auctions.extend(found)
    window_start = date(first - 1, 1, 1)
    window_end = date(last + 1, 12, 31)
    for auction in auctions:
        if not window_start <= auction.opens_at_utc.date() <= window_end:
            raise CalendarUncertain(f"an auction opens outside {first}/{last}")
        published = auction.offer_levels_published_on
        if published is not None and published > auction.opens_at_utc.date():
            raise CalendarUncertain("offer levels published after the auction opens")
    rules = []
    for name in ("Daily", "Within-Day"):
        try:
            sheet = _sheet(sheets, name)
        except CalendarUncertain:
            continue
        rules.extend(
            value.strip()
            for value in sheet.cells.values()
            if len(value) > 60 and not value.lower().startswith("as an example")
        )
    return AuctionCalendar(
        document_id=document_id,
        version=version,
        published_on=_version_date(version),
        status=status,
        first_year=first,
        last_year=last,
        auctions=tuple(sorted(auctions, key=lambda a: (a.opens_at_utc, a.capacity, a.product))),
        standing_rules=tuple(rules[:12]),
    )


__all__ = [
    "ANNUAL",
    "ATTRIBUTION",
    "AuctionCalendar",
    "CalendarAuction",
    "CalendarUncertain",
    "HOST",
    "MONTHLY",
    "PAGE_URL",
    "QUARTERLY",
    "calendar_link",
    "parse_calendar",
]
