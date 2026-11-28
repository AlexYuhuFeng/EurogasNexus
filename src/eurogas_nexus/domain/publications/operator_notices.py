"""Read LNG terminal operators' public slot and auction announcements (consented, 2026-11-28).

Pure parsers, one per operator layout, each returning :class:`SlotOffer` rows: the terminal,
the slot (its days and, where stated, its size), the auction window with its time zone, and the
announcement's link. A layout the parser was not written for raises :class:`NoticesUncertain`
(the held notices stay and a person is asked); nothing is guessed.

- **Fluxys LNG** (Zeebrugge and Dunkirk): the "Primary & secondary market" page lists the
  operator's news; a regasification slot sale is announced in a news item with each slot
  (``18/01/2027 21:59 HT069``), its size ("up to 140 000 m³ LNG over 10 days") and the
  auction day and time ("Slot of 18 January: Auction on 26 November 2026 at 10AM Belgian time
  (CET)"; later slots "within 15 minutes after the closing of the previous auction").
- **Grain LNG** (Isle of Grain): the use-it-or-lose-it bulletin board lists the berthing slots
  currently available ("Please see below the currently available slots:" then one date a
  line); bids go by e-mail, so a slot has no auction window, only the day it was first seen.
- **Deutsche Energy Terminal** (Wilhelmshaven 01 and 02, Brunsbüttel, Stade): the trader
  information page states each terminal's status ("Auction running", "No Auction Planned") and
  the auction information; the auctions themselves run on PRISMA.

Import-safe: no database, web or network import.

LNG 接收站运营商公开的档期与拍卖公告解析（经书面同意获取）；版式不符时不猜测。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from html import unescape
from urllib.parse import urljoin, urlsplit
from zoneinfo import ZoneInfo

_MONTHS = {name: index for index, name in enumerate(
    ("january", "february", "march", "april", "may", "june", "july", "august", "september",
     "october", "november", "december"), start=1)}
BRUSSELS = ZoneInfo("Europe/Brussels")
LONDON = ZoneInfo("Europe/London")
BERLIN = ZoneInfo("Europe/Berlin")


class NoticesUncertain(ValueError):
    """The page is not in the layout the parser was written for."""


@dataclass(frozen=True)
class SlotOffer:
    """One slot or auction an operator announced, as it announced it."""

    key: str
    kind: str
    terminal_id: str | None
    terminal_name: str
    hub: str
    title: str
    #: When bidding opens (UTC); for a board with no window, the day it was first seen.
    opens_at_utc: datetime
    closes_at_utc: datetime | None
    offers_from: date | None
    offers_to: date | None
    quantity: float | None
    quantity_unit: str | None
    link: str
    time_zone: str
    #: The window is the operator's (``published``) or the day the product saw it (``seen``).
    window_basis: str = "published"

    def to_json(self) -> dict:
        return {
            "key": self.key, "kind": self.kind, "terminal_id": self.terminal_id,
            "terminal_name": self.terminal_name, "hub": self.hub, "title": self.title,
            "opens_at_utc": self.opens_at_utc.isoformat(),
            "closes_at_utc": self.closes_at_utc.isoformat() if self.closes_at_utc else None,
            "offers_from": self.offers_from.isoformat() if self.offers_from else None,
            "offers_to": self.offers_to.isoformat() if self.offers_to else None,
            "quantity": self.quantity, "quantity_unit": self.quantity_unit, "link": self.link,
            "time_zone": self.time_zone, "window_basis": self.window_basis,
        }


@dataclass(frozen=True)
class NoticeRecord:
    """What one check read: the offers, and the documents they came from."""

    offers: tuple[SlotOffer, ...]
    documents: tuple[str, ...] = ()

    def to_json(self) -> dict:
        return {"offers": [o.to_json() for o in self.offers],
                "documents": list(self.documents)}


def _lines(html: str) -> list[str]:
    text = re.sub(r"<script.*?</script>|<style.*?</style>", "", html, flags=re.S | re.I)
    text = unescape(re.sub(r"<[^>]+>", "\n", text))
    return [re.sub(r"\s+", " ", line).strip() for line in text.split("\n")
            if line.strip()]


def _day(text: str) -> date:
    """``26 November 2026`` or ``30th November 2026``."""

    match = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})", text.strip())
    if not match or match.group(2).lower() not in _MONTHS:
        raise NoticesUncertain(f"date {text!r}")
    return date(int(match.group(3)), _MONTHS[match.group(2).lower()], int(match.group(1)))


# ---------------------------------------------------------------------------- Fluxys LNG

FLUXYS_HOST = "www.fluxys.com"
FLUXYS_TERMINALS = {
    "zeebrugge": ("zeebrugge", "Zeebrugge", "ZTP"),
    "dunkerque": ("dunkerque-lng", "Dunkerque LNG", "PEG"),
}


def fluxys_slot_news_links(page: bytes, base_url: str, *, limit: int = 4) -> list[str]:
    """The newest Fluxys LNG news items about slots or auctions, on Fluxys's own host."""

    html = page.decode("utf-8", "replace")
    links: list[str] = []
    for href in re.findall(r'href="([^"]+)"', html):
        url = urljoin(base_url, unescape(href))
        parts = urlsplit(url)
        if parts.scheme != "https" or parts.netloc != FLUXYS_HOST:
            continue
        if not re.match(r"^/en/news/fluxys-lng/\d{4}/", parts.path):
            continue
        if not re.search(r"slot|auction", parts.path, re.I):
            continue
        if url not in links:
            links.append(url)
    if "/en/news" not in html:
        raise NoticesUncertain("the Fluxys LNG market page carries no news list")
    return links[:limit]


_FLUXYS_SLOT = re.compile(r"(\d{2})/(\d{2})/(\d{4}) (\d{2}):(\d{2}) (HT\d+)")
_FLUXYS_SIZE = re.compile(r"up to ([\d  ., ]+?) ?m³ LNG over (\d+) days", re.I)
_FLUXYS_AUCTION = re.compile(
    r"Slot of (\d{1,2}) ([A-Za-z]+): Auction on (\d{1,2} [A-Za-z]+ \d{4})"
    r"(?: at (\d{1,2})(?::(\d{2}))? ?(AM|PM) Belgian time)?", re.I)


def parse_fluxys_slot_news(page: bytes, url: str, *, terminal: str | None = None
                           ) -> tuple[SlotOffer, ...]:
    """The slots one Fluxys LNG news item offers, with their auction day and time.

    ``terminal`` (``zeebrugge`` or ``dunkerque``) keeps only that terminal's item; an item
    about another terminal answers no slot.
    """

    lines = _lines(page.decode("utf-8", "replace"))
    text = " ".join(lines)
    # The site's menus name both terminals on every page; the item's own text says "the
    # Zeebrugge LNG Terminal" or "the Dunkirk LNG Terminal".
    named = re.search(r"(Zeebrugge|Dunkirk|Dunkerque) LNG [Tt]erminal", text)
    if not named:
        raise NoticesUncertain("the news item names no Fluxys LNG terminal")
    found = "zeebrugge" if named.group(1) == "Zeebrugge" else "dunkerque"
    if terminal is not None and found != terminal:
        return ()
    terminal_id, terminal_name, hub = FLUXYS_TERMINALS[found]
    slots = [(datetime(int(y), int(m), int(d), int(hh), int(mm), tzinfo=BRUSSELS), code)
             for d, m, y, hh, mm, code in _FLUXYS_SLOT.findall(text)]
    if not slots:
        raise NoticesUncertain("no slot line (DD/MM/YYYY HH:MM HTnnn) in the news item")
    size = _FLUXYS_SIZE.search(text)
    quantity = days = None
    if size:
        quantity = float(re.sub(r"[^\d.]", "", size.group(1).replace(",", "")))
        days = int(size.group(2))
    auctions: dict[tuple[int, int], datetime] = {}
    first_time: time | None = None
    for day_text, month_text, auction_day, hour, minute, ampm in _FLUXYS_AUCTION.findall(text):
        when = _day(auction_day)
        if hour:
            h = int(hour) % 12 + (12 if ampm.upper() == "PM" else 0)
            first_time = time(h, int(minute or 0))
        at = datetime.combine(when, first_time or time(0), tzinfo=BRUSSELS)
        if month_text.lower() not in _MONTHS:
            raise NoticesUncertain(f"month {month_text!r}")
        auctions[(_MONTHS[month_text.lower()], int(day_text))] = at
    if not auctions:
        raise NoticesUncertain("no 'Slot of <day>: Auction on <date>' line in the news item")
    out = []
    for arrival, code in slots:
        opens = auctions.get((arrival.month, arrival.day))
        if opens is None:
            raise NoticesUncertain(f"slot {code} has no auction date")
        last = arrival.date() + timedelta(days=(days or 1) - 1)
        amount = f"{quantity:,.0f}".replace(",", " ") if quantity else ""
        size_text = f", up to {amount} m³ LNG over {days} days" if quantity else ""
        out.append(SlotOffer(
            key=f"{terminal_id}:{code.lower()}:{arrival.date().isoformat()}",
            kind="lng_slot", terminal_id=terminal_id, terminal_name=terminal_name, hub=hub,
            title=(f"{terminal_name} regasification slot {code}, arrival {arrival:%d %b %Y %H:%M}"
                   f"{size_text}; auction {opens:%d %b %Y %H:%M} Belgian time"),
            opens_at_utc=opens.astimezone(UTC), closes_at_utc=None,
            offers_from=arrival.date(), offers_to=last, quantity=quantity,
            quantity_unit="m3_lng" if quantity else None, link=url,
            time_zone="Europe/Brussels",
        ))
    return tuple(out)


# ----------------------------------------------------------------------------- Grain LNG

GRAIN_HEADING = "Please see below the currently available slots:"


def parse_grain_bulletin(page: bytes, url: str, *, seen_on: date) -> tuple[SlotOffer, ...]:
    """The berthing slots Grain LNG's UIOLI bulletin board lists as available now.

    An empty list under the heading is a board with nothing on offer (the held slots are then
    withdrawn); a page without the heading is not read.
    """

    lines = _lines(page.decode("utf-8", "replace"))
    try:
        start = lines.index(GRAIN_HEADING)
    except ValueError as exc:
        raise NoticesUncertain("the UIOLI bulletin board's heading was not found") from exc
    days: list[date] = []
    for line in lines[start + 1:]:
        if not re.fullmatch(r"\d{1,2}(?:st|nd|rd|th)? [A-Za-z]+ \d{4}", line):
            break
        days.append(_day(line))
    opens = datetime.combine(seen_on, time(0), tzinfo=UTC)
    return tuple(SlotOffer(
        key=f"grain-lng:berth:{day.isoformat()}", kind="lng_slot", terminal_id="grain-lng",
        terminal_name="Isle of Grain", hub="NBP",
        title=(f"Isle of Grain berthing slot available {day:%d %b %Y} (UIOLI bulletin board; "
               "bids by e-mail on a Short Term Access Confirmation Notice)"),
        opens_at_utc=opens, closes_at_utc=None, offers_from=day, offers_to=day, quantity=None,
        quantity_unit=None, link=url, time_zone="Europe/London", window_basis="seen",
    ) for day in sorted(set(days)))


# ------------------------------------------------------------------ Deutsche Energy Terminal

DET_TERMINALS = {
    "Wilhelmshaven 01": ("wilhelmshaven:fsru-1", r"Wilhelmshaven 01|WHV01|Wilhelmshaven 1\b"),
    "Wilhelmshaven 02": ("wilhelmshaven:fsru-2", r"Wilhelmshaven 02|WHV02|Wilhelmshaven 2\b"),
    "Brunsbüttel": ("brunsbuttel", r"Brunsbüttel"),
    "Stade": (None, r"\bStade\b"),
}
_DET_WINDOW = re.compile(r"from (\d{1,2} [A-Za-z]+ \d{4}) to (\d{1,2} [A-Za-z]+ \d{4})")


def parse_det_trader_information(page: bytes, url: str, *, seen_on: date
                                 ) -> tuple[SlotOffer, ...]:
    """Each DET terminal whose status is "Auction running", with what the page says of it."""

    lines = _lines(page.decode("utf-8", "replace"))
    status: dict[str, str] = {}
    for index, line in enumerate(lines[:-1]):
        if line in DET_TERMINALS and lines[index + 1] in {"Auction running",
                                                          "No Auction Planned"}:
            status.setdefault(line, lines[index + 1])
    if len(status) < 2:
        raise NoticesUncertain("the terminals' auction status block was not found")
    out = []
    for name, state in status.items():
        if state != "Auction running":
            continue
        terminal_id, pattern = DET_TERMINALS[name]
        others = [p for n, (_t, p) in DET_TERMINALS.items() if n != name]
        candidates = [line for line in lines if re.search(pattern, line)
                      and re.search(r"Auction|Offering|Capacities", line)
                      and len(line) < 200 and line not in DET_TERMINALS]
        # The terminal's own headline first (one that names no other terminal).
        candidates.sort(key=lambda line: any(re.search(p, line) for p in others))
        headline = candidates[0] if candidates else ""
        year = re.search(r"(?:Calendar Year|for|of) (\d{4})", headline)
        offers_from = date(int(year.group(1)), 1, 1) if year else None
        offers_to = date(int(year.group(1)), 12, 31) if year else None
        window = None
        if headline:
            start = lines.index(headline)
            for line in lines[start:start + 8]:
                window = _DET_WINDOW.search(line) or window
                if window:
                    break
        opens = (datetime.combine(_day(window.group(1)), time(0), tzinfo=BERLIN)
                 if window else datetime.combine(seen_on, time(0), tzinfo=UTC))
        closes = (datetime.combine(_day(window.group(2)), time(23, 59), tzinfo=BERLIN)
                  if window else None)
        out.append(SlotOffer(
            key=f"det:{(terminal_id or name).lower()}:{offers_from or seen_on}",
            kind="lng_slot", terminal_id=terminal_id, terminal_name=name, hub="THE",
            title=(f"{name}: auction running on PRISMA"
                   + (f" ({headline})" if headline else "")),
            opens_at_utc=opens.astimezone(UTC), closes_at_utc=closes.astimezone(UTC)
            if closes else None, offers_from=offers_from, offers_to=offers_to, quantity=None,
            quantity_unit=None, link=url, time_zone="Europe/Berlin",
            window_basis="published" if window else "seen",
        ))
    return tuple(out)


__all__ = [
    "NoticeRecord",
    "NoticesUncertain",
    "SlotOffer",
    "fluxys_slot_news_links",
    "parse_det_trader_information",
    "parse_fluxys_slot_news",
    "parse_grain_bulletin",
]
