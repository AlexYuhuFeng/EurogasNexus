"""Watch the public publications the desk relies on, and tell the desk what changed.

The registry (``domain/publications/registry``) says, for each publication, where it is and
whether its terms let the product keep it: allowed by the terms (``fetch``), or forbidden by
the terms but covered by the publisher's written consent (``consented``, owner 2026-11-28;
``domain/publications/consents``). :func:`check_publication` does one check:

1. A publication the product may not fetch (hand-maintained, link only, no entry in the legal
   register, consented but not yet implemented, a site that refuses automated reading, or a
   consent an administrator has withdrawn) is recorded with that state and never read.
2. Within its interval nothing is read again (``skipped``); after a failed check the next one
   waits longer each time (doubling the interval, at most a day) and never before a
   publisher's ``Retry-After``. Otherwise the host's ``robots.txt`` is read first (a
   disallowed page is not read), then the publication, with this product's own generic
   User-Agent (:data:`PUBLICATION_USER_AGENT`) and the conditional headers of the last read.
   Requests of one check go one after another, :data:`REQUEST_PAUSE_SECONDS` apart.
3. The document's SHA-256 is compared with the one held. The same digest: ``current``.
4. A new digest: the document is kept once by its digest (``raw_payload_contents``) and parsed.
   Parsed with confidence: the record is replaced, the previous record is kept beside it with
   its fetch time, and the parser's records are applied (ENTSOG's auctions to the capacity
   notices; a price publication's figures to the observation store and the board's quotes,
   ``public_prices``; an exchange calendar stays on its record and replaces the desk's hand
   file for the years it covers). When an earlier record existed, a calendar's change is told
   once in a notification. Not parsed with confidence (a layout change): the held record
   stays, the state becomes ``needs_confirmation`` with the document's link, and the desk is
   told once for that document; nothing is guessed.
5. A page or document that cannot be read: ``unreachable`` with the reason, told once a day.

:func:`calendar_items` is the desk's calendar: upcoming non-trading days and early closes
(fetched where the exchange's calendar has been read, else the hand-maintained file, marked
so), last trading days, auction windows and offer-level publication days, reminders to check a
hand-maintained calendar, and sources that need a person. Every item carries its source and,
for fetched ones, when it was published and fetched. :func:`effective_trading_calendar` is the
same calendar for the daily pack. :func:`source_status` is the administrators' list of every
watched publication. :func:`queue_deadline_notifications` raises the existing notifications
ahead of a non-trading day and a calendar check. :func:`watch_publications_if_due` is the
scheduler's hook.

The fetcher is passed in, so tests run on fixtures with no network (:func:`publication_fetch`
is the real one). Nothing here signs in, registers or accepts terms.

发布物监控：在条款或书面同意允许时按间隔礼貌获取、以摘要检测变化、解析并保留旧记录；无法确定时保留旧值并请人确认；
出错时退避，遵守 Retry-After 与 robots.txt。
"""

from __future__ import annotations

import hashlib
import json
import os
import time as _time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from eurogas_nexus.application.news_ingest import Fetcher, FetchResult, http_fetch, robots_allows
from eurogas_nexus.domain.publications import entsog_cam_calendar as entsog
from eurogas_nexus.domain.publications import exchange_calendars as calendars
from eurogas_nexus.domain.publications import operator_notices as operators
from eurogas_nexus.domain.publications import public_prices as prices
from eurogas_nexus.domain.publications.registry import (
    CONSENTED,
    FETCH,
    FETCHED_VERDICTS,
    WATCHED_PUBLICATIONS,
    WatchedPublication,
    fetch_refusal,
    unfetched_state,
    watched_publication,
)

EVENT_SOURCE = "src-publications"
#: ``off`` stops the scheduler's hook (tests set it; an installation without outbound
#: network can too). Anything else, or unset, leaves it on: live by default (rule 19).
WATCH_ENV = "EUROGAS_NEXUS_PUBLICATION_WATCH"
#: The scheduler loop runs every minute; the watch looks at its publications at most this often
#: (each publication then keeps its own interval).
HOOK_EVERY = timedelta(minutes=15)
#: How far ahead a non-trading day is notified, and a calendar check is reminded.
NON_TRADING_LEAD = timedelta(days=3)
CHECK_LEAD = timedelta(days=14)
#: How often an unreachable publication is told again.
UNREACHABLE_RETELL = timedelta(days=1)
#: The product's name to every publisher: generic, no person, firm or place (THE's API
#: manual asks every client to name itself and a version).
PUBLICATION_USER_AGENT = "EurogasNexus-PublicationWatch/1.0"
#: Between two requests of one check (a history read is several requests).
REQUEST_PAUSE_SECONDS = 2.0
#: The longest a failed publication waits before the next try.
MAX_BACKOFF = timedelta(hours=24)
#: The largest document read (THE's full imbalance history is about 1.2 MB).
DOCUMENT_MAX_BYTES = 8_000_000

_HOOK_STATE: dict[str, datetime] = {}


def publication_fetch(url: str, headers: dict[str, str], *, body: bytes | None = None
                      ) -> FetchResult:
    """The real fetcher: HTTPS only, this product's generic User-Agent, bounded size."""

    return http_fetch(url, headers, body=body, user_agent=PUBLICATION_USER_AGENT,
                      max_bytes=DOCUMENT_MAX_BYTES, timeout=90.0)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _iso(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _aware(value).isoformat()
    return value.isoformat()


# ----------------------------------------------------------------------------- parsers


@dataclass(frozen=True)
class Parser:
    """How one publication is read: find the document on the page, parse it, apply it."""

    #: The document's URL from the page's bytes (raises the parser's uncertainty error);
    #: ``None`` when the publication's address is the document itself.
    locate: Callable[[bytes, str], str] | None
    #: The typed record from the document (raises the uncertainty error).
    parse: Callable[[bytes], Any]
    #: Store what the record says where the product reads it; returns counts.
    apply: Callable[..., dict[str, int]]
    uncertain: type[Exception]


def _entsog_locate(page: bytes, base_url: str) -> str:
    url, _first = entsog.calendar_link(page.decode("utf-8", "replace"), base_url=base_url)
    return url


def _entsog_apply(session, item: WatchedPublication, calendar: entsog.AuctionCalendar, *,
                  now: datetime, document_url: str) -> dict[str, int]:
    """ENTSOG's auctions as published capacity notices; rule-derived ones they cover retire."""

    from eurogas_nexus.application.tariff_book import (
        ENTSOG_CALENDAR_PUBLISHER,
        NoticeSpec,
        record_notices,
    )
    from eurogas_nexus.db.models import CapacityNoticeRecord as N

    years = f"{calendar.first_year}/{calendar.last_year % 100:02d}"
    specs = []
    for auction in calendar.auctions:
        offer = auction.offer_levels_published_on
        specs.append(NoticeSpec(
            notice_key=f"{ENTSOG_CALENDAR_PUBLISHER}:{auction.key}",
            publisher_id=ENTSOG_CALENDAR_PUBLISHER,
            kind="auction",
            basis="published",
            product=auction.product,
            title=(f"{auction.label()} (ENTSOG calendar {years}"
                   + (f"; offer levels published {offer:%d %b %Y}" if offer else "") + ")"),
            opens_at_utc=auction.opens_at_utc,
            offers_from=auction.offers_from,
            offers_to=auction.offers_to,
            facility_kind="point",
            facility_id="all-interconnection-points",
            facility_name="Every EU interconnection point offering bundled capacity",
            source_url=document_url,
            retrieved_at_utc=now,
        ))
    counts = record_notices(session, specs, now_utc=now)
    keys = {spec.notice_key for spec in specs}
    first = min(a.opens_at_utc for a in calendar.auctions)
    last = max(a.opens_at_utc for a in calendar.auctions)
    withdrawn = 0
    for row in (session.query(N).filter(N.publisher_id == ENTSOG_CALENDAR_PUBLISHER)
                .filter(N.opens_at_utc >= first).filter(N.opens_at_utc <= last)
                .filter(N.state == "open").all()):
        if row.notice_key not in keys:
            row.state = "cancelled"
            row.changed_at_utc = now
            row.revision += 1
            withdrawn += 1
    firm = {(a.product, a.offers_from) for a in calendar.auctions if a.capacity == "firm"}
    retired = 0
    for row in (session.query(N).filter(N.publisher_id == "cam-nc-calendar")
                .filter(N.state == "open").all()):
        if (row.product, row.offers_from) in firm:
            row.state = "superseded"
            row.changed_at_utc = now
            retired += 1
    session.flush()
    return {**counts, "withdrawn": withdrawn, "rule_derived_retired": retired}


def _calendar_apply(session, item: WatchedPublication, calendar, *, now: datetime,
                    document_url: str) -> dict[str, int]:
    """An exchange calendar stays on its record; the calendar reads overlay it on the file."""

    return {"closed": len(calendar.closed), "early_closes": len(calendar.early_closes),
            "expiries": len(calendar.expiries)}


def _desk_years() -> tuple[int, ...]:
    """The years the desk's calendar covers (the hand file's), and the current one."""

    held = _hand_calendar()
    years = set(held.years) if held else set()
    years.add(datetime.now(UTC).year)
    return tuple(sorted(years))


PARSERS: dict[str, Parser] = {
    "entsog_cam_calendar": Parser(
        locate=_entsog_locate,
        parse=entsog.parse_calendar,
        apply=_entsog_apply,
        uncertain=entsog.CalendarUncertain,
    ),
    "eex_gas_calendar": Parser(
        locate=lambda page, base: calendars.eex_document_link(page, base, kind="gas"),
        parse=calendars.parse_eex_gas_calendar,
        apply=_calendar_apply,
        uncertain=calendars.CalendarUncertain,
    ),
    "eex_holiday_calendar": Parser(
        locate=lambda page, base: calendars.eex_document_link(page, base, kind="holidays"),
        parse=lambda data: calendars.parse_eex_holiday_calendar(data, years=_desk_years()),
        apply=_calendar_apply,
        uncertain=calendars.CalendarUncertain,
    ),
    "ice_endex_schedule": Parser(
        locate=None,
        parse=calendars.parse_ice_endex_schedule,
        apply=_calendar_apply,
        uncertain=calendars.CalendarUncertain,
    ),
    "ifeu_schedule": Parser(
        locate=None,
        parse=calendars.parse_ifeu_schedule,
        apply=_calendar_apply,
        uncertain=calendars.CalendarUncertain,
    ),
}


# ------------------------------------------------------------------------- price series


@dataclass(frozen=True)
class SeriesRequest:
    """One request of a price publication's check."""

    url: str
    body: bytes | None = None
    headers: dict[str, str] = field(default_factory=dict)
    #: A history request the publisher may not have (an early year): a 404 is noted, not an
    #: error.
    optional: bool = False


class _Unreachable(Exception):
    """A page a request plan needed could not be read."""

    def __init__(self, why: str, result: FetchResult | None = None) -> None:
        super().__init__(why)
        self.result = result


#: THE's publication start (its API raises an earlier start date to this one).
THE_START = date(2021, 10, 1)
#: National Gas: "for most data items, 5 years of rolling historic data can be accessed";
#: one request may cover at most 3,600 days x items, so a year of three items per request.
NG_HISTORY_YEARS = 5
#: MIBGAS publishes a CSV a year from 2016 (2015 as a workbook only).
MIBGAS_FIRST_YEAR = 2016


def _plan_the(item: WatchedPublication, row, now: datetime, fetch: Fetcher
              ) -> list[SeriesRequest]:
    today = now.date()
    start = THE_START if not row.record else today - timedelta(days=7)
    return [SeriesRequest(f"{item.url}?startDate={start.isoformat()}&endDate={today.isoformat()}")]


def _plan_national_gas(item: WatchedPublication, row, now: datetime, fetch: Fetcher
                       ) -> list[SeriesRequest]:
    today = now.date()
    if row.record:
        windows = [(today - timedelta(days=10), today)]
    else:
        windows = [(today - timedelta(days=365 * (k + 1) - 1), today - timedelta(days=365 * k))
                   for k in range(NG_HISTORY_YEARS)]
    ids = sorted(prices.NATIONAL_GAS_ITEMS)
    return [SeriesRequest(item.url, body=json.dumps({
        "fromDate": start.isoformat(), "toDate": end.isoformat(), "publicationIds": ids,
        "latestValue": "Y"}).encode(), headers={"Content-Type": "application/json"})
        for start, end in windows]


def _mibgas_url(year: int) -> str:
    return (f"https://www.mibgas.es/en/file-access/MIBGAS_Data_{year}.csv"
            f"?path=AGNO_{year}/XLS")


def _plan_mibgas(item: WatchedPublication, row, now: datetime, fetch: Fetcher
                 ) -> list[SeriesRequest]:
    year = now.year
    if not row.record:
        return [SeriesRequest(_mibgas_url(y), optional=True)
                for y in range(MIBGAS_FIRST_YEAR, year)] + [SeriesRequest(_mibgas_url(year))]
    out = [SeriesRequest(_mibgas_url(year))]
    if now.month == 1 and now.day <= 7:
        out.insert(0, SeriesRequest(_mibgas_url(year - 1), optional=True))
    return out


EEX_NGP_FILE = "https://gasandregistry.eex.com/Gas/NGP/TTF_NGP_60_Days.csv"


def _plan_eex_ngp(item: WatchedPublication, row, now: datetime, fetch: Fetcher
                  ) -> list[SeriesRequest]:
    page = fetch(item.url, {})
    if page.status != 200:
        raise _Unreachable(_status(page), page)
    if EEX_NGP_FILE.encode() not in page.body:
        raise prices.PricesUncertain("the gas market transparency page no longer links the TTF "
                                     "neutral gas price 60-day file")
    return [SeriesRequest(EEX_NGP_FILE)]


@dataclass(frozen=True)
class SeriesSource:
    plan: Callable[..., list[SeriesRequest]]
    parse: Callable[[bytes, datetime], prices.PriceRecord]


SERIES_SOURCES: dict[str, SeriesSource] = {
    "the_prices": SeriesSource(
        plan=_plan_the,
        parse=lambda data, now: prices.parse_the_imbalance(data, today=now.date())),
    "national_gas_prices": SeriesSource(
        plan=_plan_national_gas, parse=lambda data, now: prices.parse_national_gas(data)),
    "mibgas_prices": SeriesSource(
        plan=_plan_mibgas, parse=lambda data, now: prices.parse_mibgas(data)),
    "eex_ngp": SeriesSource(
        plan=_plan_eex_ngp, parse=lambda data, now: prices.parse_eex_ngp(data)),
}


# ------------------------------------------------------------------- operators' notices


def _plan_fluxys(item: WatchedPublication, row, now: datetime, fetch: Fetcher
                 ) -> list[SeriesRequest]:
    """The Fluxys LNG market page, then the newest news items about slots it links."""

    page = fetch(item.url, {})
    if page.status != 200:
        raise _Unreachable(_status(page), page)
    links = operators.fluxys_slot_news_links(page.body, item.url)
    return [SeriesRequest(link) for link in links]


def _plan_page(item: WatchedPublication, row, now: datetime, fetch: Fetcher
               ) -> list[SeriesRequest]:
    return [SeriesRequest(item.url)]


@dataclass(frozen=True)
class NoticeSource:
    """An operator's announcements: what to read, how to read one page, and whether the page
    is the whole board (a slot no longer listed is withdrawn) or one announcement of many."""

    plan: Callable[..., list[SeriesRequest]]
    parse: Callable[[bytes, str, datetime], tuple[operators.SlotOffer, ...]]
    board: bool = False


NOTICE_SOURCES: dict[str, NoticeSource] = {
    "fluxys_lng_slots": NoticeSource(
        plan=_plan_fluxys,
        parse=lambda data, url, now: operators.parse_fluxys_slot_news(
            data, url, terminal="zeebrugge")),
    "fluxys_lng_slots_dunkerque": NoticeSource(
        plan=_plan_fluxys,
        parse=lambda data, url, now: operators.parse_fluxys_slot_news(
            data, url, terminal="dunkerque")),
    "grain_uioli": NoticeSource(
        plan=_plan_page,
        parse=lambda data, url, now: operators.parse_grain_bulletin(data, url,
                                                                    seen_on=now.date()),
        board=True),
    "det_trader_information": NoticeSource(
        plan=_plan_page,
        parse=lambda data, url, now: operators.parse_det_trader_information(
            data, url, seen_on=now.date()),
        board=True),
}


def _apply_offers(session, item: WatchedPublication, offers, *, now: datetime,
                  board: bool) -> dict[str, int]:
    """The offers as capacity notices (``lng_slot``), where the regas auction desk picks them.

    A board's slot no longer listed is withdrawn (``cancelled``). A slot seen on a board with no
    published window keeps the day it was first seen as its opening.
    """

    from eurogas_nexus.application.tariff_book import NoticeSpec, record_notices
    from eurogas_nexus.db.models import CapacityNoticeRecord as N

    specs = []
    for offer in offers:
        key = f"{item.publication_id}:{offer.key}"[:160]
        opens = offer.opens_at_utc
        if offer.window_basis == "seen":
            held = session.get(N, key)
            if held is not None and held.opens_at_utc is not None:
                opens = _aware(held.opens_at_utc)
        specs.append(NoticeSpec(
            notice_key=key, publisher_id=item.publication_id, kind=offer.kind,
            basis="published", product="LNG_SLOT", title=offer.title, opens_at_utc=opens,
            closes_at_utc=offer.closes_at_utc, offers_from=offer.offers_from,
            offers_to=offer.offers_to, facility_kind="terminal",
            facility_id=offer.terminal_id, facility_name=offer.terminal_name,
            quantity=offer.quantity, quantity_unit=offer.quantity_unit,
            source_url=offer.link, retrieved_at_utc=now,
        ))
    counts = record_notices(session, specs, now_utc=now)
    withdrawn = 0
    if board:
        keys = {spec.notice_key for spec in specs}
        for row in (session.query(N).filter(N.publisher_id == item.publication_id)
                    .filter(N.state == "open").all()):
            if row.notice_key not in keys:
                row.state = "cancelled"
                row.changed_at_utc = now
                row.revision += 1
                withdrawn += 1
    session.flush()
    return {**counts, "withdrawn": withdrawn}


def _check_notices(session, row, item: WatchedPublication, *, fetch: Fetcher, now: datetime,
                   pause: Callable[[float], None]) -> CheckOutcome:
    """One check of an operator's announcements: read, parse, record as slot notices."""

    from eurogas_nexus.db.repositories.raw_archive import store_payload_content

    source = NOTICE_SOURCES[item.parser]
    allowed, why = robots_allows(fetch, item.url, user_agent=PUBLICATION_USER_AGENT)
    if not allowed:
        return _unreachable(session, row, item, why, now)
    try:
        requests = source.plan(item, row, now, fetch)
    except _Unreachable as exc:
        return _unreachable(session, row, item, str(exc), now, exc.result)
    except operators.NoticesUncertain as exc:
        return _needs_person(session, row, item, now=now, digest=_sha(str(exc).encode()),
                             url=item.url, why=str(exc))
    bodies: list[tuple[str, bytes]] = []
    for index, request in enumerate(requests):
        if index:
            pause(REQUEST_PAUSE_SECONDS)
        result = fetch(request.url, {})
        if result.status != 200:
            return _unreachable(session, row, item, _status(result), now, result)
        bodies.append((request.url, result.body))
    row.last_fetched_at_utc = now
    _succeeded(row)
    digest = hashlib.sha256(b"".join(hashlib.sha256(b).digest() for _u, b in bodies)
                            ).hexdigest()
    if bodies and digest == row.content_sha256:
        if row.state in {"unreachable", "never_fetched"}:
            row.state = "current"
        row.detail = "Unchanged since the last read."
        session.flush()
        return CheckOutcome(item.publication_id, "current", "unchanged")
    offers: list[operators.SlotOffer] = []
    for url, body in bodies:
        store_payload_content(session, payload_sha256=_sha(body), data=body, received_at_utc=now)
        try:
            offers.extend(source.parse(body, url, now))
        except operators.NoticesUncertain as exc:
            return _needs_person(session, row, item, now=now, digest=digest, url=url,
                                 why=str(exc))
    record = operators.NoticeRecord(tuple(offers), tuple(url for url, _b in bodies)).to_json()
    first_read = row.record is None
    lines = [] if first_read else _offer_changes(row.record, record)
    _replace_record(row, record, now=now, digest=digest,
                    document_url=bodies[-1][0] if bodies else item.url)
    applied = _apply_offers(session, item, offers, now=now, board=source.board)
    row.detail = (f"Read {now:%d %b %Y}: {len(offers)} slot or auction offer(s)"
                  + (f"; {len(lines)} change(s)" if lines else ""))[:500]
    session.flush()
    if lines:
        _tell(session, key=f"publication:{item.publication_id}:changed:{digest}",
              title=f"New from {item.publisher}: {item.title}",
              body="\n".join([*lines, f"Page: {item.url}", item.attribution]),
              now=now, severity="info", category="alert")
    return CheckOutcome(item.publication_id, "first_read" if first_read else "changed",
                        f"{len(offers)} offer(s)", applied)


def _offer_changes(previous: dict | None, current: dict) -> list[str]:
    before = {o["key"]: o for o in (previous or {}).get("offers", [])}
    after = {o["key"]: o for o in current.get("offers", [])}
    lines = [f"Offered: {o['title']}." for key, o in after.items() if key not in before]
    lines += [f"No longer listed: {o['title']}." for key, o in before.items() if key not in after]
    return lines[:10]


def describe_change(previous: dict | None, current: dict) -> list[str]:
    """What moved between two records, in plain words (at most ten lines).

    An ENTSOG calendar: auctions new, moved or no longer listed. An exchange calendar: days
    newly closed, no longer closed, and early closes added. A price record: nothing (the board
    shows the figure; a daily price is not news).
    """

    if "auctions" in current:
        before = {a["key"]: a for a in (previous or {}).get("auctions", [])}
        after = {a["key"]: a for a in current.get("auctions", [])}
        opens = [a["opens_at_utc"] for a in after.values()]
        lines: list[str] = []
        for key, auction in after.items():
            held = before.get(key)
            if held is None:
                lines.append(f"New: {auction['label']} opens {auction['opens_at_utc']}.")
            elif held["opens_at_utc"] != auction["opens_at_utc"]:
                lines.append(f"Moved: {auction['label']} from {held['opens_at_utc']} to "
                             f"{auction['opens_at_utc']}.")
        for key, auction in before.items():
            # Only what the new calendar covers: a next year's file does not drop this year's.
            if key not in after and opens and min(opens) <= auction["opens_at_utc"] <= max(opens):
                lines.append(f"No longer listed: {auction['label']}.")
        return lines[:10]
    if "closed" in current:
        before_closed = {c["day"]: c["what"] for c in (previous or {}).get("closed", [])}
        after_closed = {c["day"]: c["what"] for c in current.get("closed", [])}
        before_early = {c["day"]: c["what"] for c in (previous or {}).get("early_closes", [])}
        lines = [f"Now closed: {day} ({what})." for day, what in sorted(after_closed.items())
                 if day not in before_closed]
        lines += [f"No longer closed: {day}." for day in sorted(before_closed)
                  if day not in after_closed]
        lines += [f"Shorter hours: {c['day']} ({c['what']})."
                  for c in current.get("early_closes", []) if c["day"] not in before_early]
        return lines[:10]
    return []


# ------------------------------------------------------------------------------- checks


@dataclass
class CheckOutcome:
    """What one check of one publication did."""

    publication_id: str
    status: str
    detail: str = ""
    applied: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {"publication_id": self.publication_id, "status": self.status,
                "detail": self.detail, "applied": dict(self.applied)}


def _row(session, item: WatchedPublication):
    from eurogas_nexus.db.models import WatchedPublicationRecord

    row = session.get(WatchedPublicationRecord, item.publication_id)
    if row is None:
        row = WatchedPublicationRecord(
            publication_id=item.publication_id,
            state=unfetched_state(item) or "never_fetched",
            detail="",
            consecutive_failures=0,
        )
        session.add(row)
    return row


def _tell(session, *, key: str, title: str, body: str, now: datetime,
          severity: str = "medium", category: str = "source") -> bool:
    from eurogas_nexus.application.notifications import queue_notification

    return queue_notification(session, category=category, severity=severity, title=title,
                              body=body, dedupe_key=key, now=now)


def _retry_after(result: FetchResult | None) -> timedelta | None:
    if result is None:
        return None
    value = (result.headers or {}).get("retry-after", "").strip()
    if value.isdigit():
        return timedelta(seconds=min(int(value), 7 * 24 * 3600))
    return None


def _unreachable(session, row, item: WatchedPublication, why: str, now: datetime,
                 result: FetchResult | None = None) -> CheckOutcome:
    row.state = "unreachable"
    row.consecutive_failures = int(row.consecutive_failures or 0) + 1
    interval = timedelta(minutes=item.interval_minutes or 60)
    wait = min(interval * (2 ** (row.consecutive_failures - 1)), MAX_BACKOFF)
    asked = _retry_after(result)
    if asked is not None:
        wait = max(wait, asked)
    row.next_check_at_utc = now + wait
    row.detail = (f"Could not be read on {now:%d %b %Y %H:%M} UTC: {why}; next try after "
                  f"{row.next_check_at_utc:%d %b %H:%M} UTC")[:500]
    _tell(session, key=f"publication:{item.publication_id}:unreachable:{now:%Y-%m-%d}",
          title=f"Not read: {item.title}",
          body=(f"{item.title} ({item.publisher}) could not be read: {why}.\n"
                f"Page: {item.url}\nThe last record held stays in use; the next check tries "
                "again later."),
          now=now, severity="low")
    session.flush()
    return CheckOutcome(item.publication_id, "unreachable", why)


def _succeeded(row) -> None:
    row.consecutive_failures = 0
    row.next_check_at_utc = None


def _publish_event(session, item: WatchedPublication, row, *, now: datetime,
                   lines: list[str], event_type: str = "capacity.changed",
                   payload: dict | None = None) -> None:
    from eurogas_nexus.application.market_events import publish
    from eurogas_nexus.domain.market_events.model import MarketEvent

    publish(session, MarketEvent(
        source_id=EVENT_SOURCE,
        event_type=event_type,
        subject_key=f"publication:{item.publication_id}",
        ingested_at_utc=now,
        payload=payload or {"publication_id": item.publication_id,
                            "content_sha256": row.content_sha256,
                            "document_url": row.document_url, "changes": lines},
        identity=f"publication:{item.publication_id}:{row.content_sha256}",
        correlation_id=item.publication_id,
    ))


def _not_fetched(session, row, item: WatchedPublication, *, now: datetime
                 ) -> CheckOutcome | None:
    """The outcome for a publication the product does not read now, or ``None`` to read it."""

    refusal = fetch_refusal(item)
    if refusal:
        row.state = unfetched_state(item) or "link_only"
        row.detail = refusal + (f": {item.site_refusal}" if item.site_refusal else "")
        session.flush()
        return CheckOutcome(item.publication_id, "not_fetched", refusal)
    if item.verdict == CONSENTED:
        from eurogas_nexus.application.publisher_consents import withdrawn_on

        withdrawn = withdrawn_on(session, item.consent_publisher)
        if withdrawn is not None:
            row.state = "consent_withdrawn"
            row.detail = (f"Consent withdrawn on {withdrawn:%Y-%m-%d}: not fetched; the data "
                          "held stays, marked")
            session.flush()
            return CheckOutcome(item.publication_id, "not_fetched",
                                f"consent withdrawn on {withdrawn:%Y-%m-%d}")
    return None


def check_publication(session, item: WatchedPublication, *, fetch: Fetcher, now: datetime,
                      force: bool = False, pause: Callable[[float], None] | None = None
                      ) -> CheckOutcome:
    """One check of one publication (see the module text); commit is the caller's."""

    now = _aware(now)
    row = _row(session, item)
    stopped = _not_fetched(session, row, item, now=now)
    if stopped is not None:
        return stopped
    if row.state in {"consent_withdrawn", "link_only", "not_implemented", "site_refuses",
                     "hand_maintained"}:
        row.state = "current" if row.record else "never_fetched"
    last = _aware(row.last_checked_at_utc)
    if not force and last is not None and now - last < timedelta(minutes=item.interval_minutes):
        return CheckOutcome(item.publication_id, "skipped", "within the publication's interval")
    waits = _aware(row.next_check_at_utc)
    if not force and waits is not None and now < waits:
        return CheckOutcome(item.publication_id, "skipped",
                            f"waiting after {row.consecutive_failures} failed check(s)")
    row.last_checked_at_utc = now
    if item.parser in NOTICE_SOURCES:
        return _check_notices(session, row, item, fetch=fetch, now=now,
                              pause=pause if pause is not None else _time.sleep)
    if item.parser in SERIES_SOURCES:
        return _check_series(session, row, item, fetch=fetch, now=now,
                             pause=pause if pause is not None else _time.sleep)
    return _check_document(session, row, item, fetch=fetch, now=now)


def _check_document(session, row, item: WatchedPublication, *, fetch: Fetcher,
                    now: datetime) -> CheckOutcome:
    from eurogas_nexus.db.repositories.raw_archive import store_payload_content

    parser = PARSERS[item.parser]
    allowed, why = robots_allows(fetch, item.url, user_agent=PUBLICATION_USER_AGENT)
    if not allowed:
        return _unreachable(session, row, item, why, now)
    if parser.locate is None:
        document_url = item.url
    else:
        page = fetch(item.url, {})
        if page.status != 200:
            return _unreachable(session, row, item, _status(page), now, page)
        try:
            document_url = parser.locate(page.body, item.url)
        except parser.uncertain as exc:
            return _needs_person(session, row, item, now=now, digest=_sha(page.body),
                                 url=item.url, why=str(exc))
        if document_url.split("/")[2] != item.url.split("/")[2]:
            # The document is on another host: its own robots.txt is read first too.
            allowed, why = robots_allows(fetch, document_url, user_agent=PUBLICATION_USER_AGENT)
            if not allowed:
                return _unreachable(session, row, item, why, now)
    headers: dict[str, str] = {}
    if row.document_url == document_url:
        if row.etag:
            headers["If-None-Match"] = row.etag
        if row.last_modified:
            headers["If-Modified-Since"] = row.last_modified
    document = fetch(document_url, headers)
    if document.status == 304:
        row.last_fetched_at_utc = now
        _succeeded(row)
        if row.state == "unreachable":
            row.state = "current" if row.record else "never_fetched"
        session.flush()
        return CheckOutcome(item.publication_id, "current", "unchanged since the last read")
    if document.status != 200:
        return _unreachable(session, row, item, _status(document), now, document)
    digest = _sha(document.body)
    row.last_fetched_at_utc = now
    _succeeded(row)
    row.etag = (document.headers.get("etag") or None)
    row.last_modified = (document.headers.get("last-modified") or None)
    if digest == row.content_sha256:
        if row.state in {"unreachable", "never_fetched"}:
            row.state = "current"
        row.detail = "Unchanged since the last read."
        session.flush()
        return CheckOutcome(item.publication_id, "current", "unchanged")
    if digest == row.pending_sha256:
        session.flush()
        return CheckOutcome(item.publication_id, "needs_confirmation",
                            "the changed document still awaits a person")
    # Kept once by its digest, where the terms (or the publisher's consent) allow storing it.
    store_payload_content(session, payload_sha256=digest, data=document.body,
                          received_at_utc=now)
    try:
        parsed = parser.parse(document.body)
    except parser.uncertain as exc:
        return _needs_person(session, row, item, now=now, digest=digest, url=document_url,
                             why=str(exc))
    record = parsed.to_json()
    first_read = row.record is None
    lines = [] if first_read else describe_change(row.record, record)
    _replace_record(row, record, now=now, digest=digest, document_url=document_url)
    applied = parser.apply(session, item, parsed, now=now, document_url=document_url)
    row.detail = (f"Read {now:%d %b %Y} from {document_url}"
                  + (f"; {len(lines)} change(s)" if lines else ""))[:500]
    session.flush()
    if item.parser == "entsog_cam_calendar":
        _publish_event(session, item, row, now=now, lines=lines)
    if not first_read:
        _tell(session, key=f"publication:{item.publication_id}:changed:{digest}",
              title=f"Updated: {item.title}",
              body="\n".join([
                  f"{item.publisher} published a new version of {item.title}; the product has "
                  "read it and updated the calendar.",
                  *(lines or ["No date moved."]),
                  f"Document: {document_url}",
                  item.attribution,
              ]),
              now=now, severity="info")
    return CheckOutcome(item.publication_id, "changed" if not first_read else "first_read",
                        f"{len(lines)} change(s)", applied)


def _replace_record(row, record: dict, *, now: datetime, digest: str, document_url: str) -> None:
    row.previous_record = row.record
    row.previous_fetched_at_utc = row.record_fetched_at_utc
    row.record = record
    row.record_fetched_at_utc = now
    row.content_sha256 = digest
    row.document_url = document_url[:1000]
    row.last_changed_at_utc = now
    row.pending_sha256 = row.pending_url = row.pending_since_utc = None
    row.state = "current"


def _check_series(session, row, item: WatchedPublication, *, fetch: Fetcher, now: datetime,
                  pause: Callable[[float], None]) -> CheckOutcome:
    """One check of a price publication: its requests in turn, then the figures stored."""

    from eurogas_nexus.application.public_prices import store_points
    from eurogas_nexus.db.repositories.raw_archive import store_payload_content

    source = SERIES_SOURCES[item.parser]
    allowed, why = robots_allows(fetch, item.url, user_agent=PUBLICATION_USER_AGENT)
    if not allowed:
        return _unreachable(session, row, item, why, now)
    try:
        requests = source.plan(item, row, now, fetch)
    except _Unreachable as exc:
        return _unreachable(session, row, item, str(exc), now, exc.result)
    except prices.PricesUncertain as exc:
        return _needs_person(session, row, item, now=now, digest=_sha(str(exc).encode()),
                             url=item.url, why=str(exc))
    hosts_read = {item.url.split("/")[2]}
    bodies: list[tuple[SeriesRequest, bytes]] = []
    missing: list[str] = []
    unchanged = 0
    for index, request in enumerate(requests):
        host = request.url.split("/")[2]
        if host not in hosts_read:
            allowed, why = robots_allows(fetch, request.url, user_agent=PUBLICATION_USER_AGENT)
            if not allowed:
                return _unreachable(session, row, item, why, now)
            hosts_read.add(host)
        if index:
            pause(REQUEST_PAUSE_SECONDS)
        headers = dict(request.headers)
        if len(requests) == 1 and row.document_url == request.url and request.body is None:
            if row.etag:
                headers["If-None-Match"] = row.etag
            if row.last_modified:
                headers["If-Modified-Since"] = row.last_modified
        result = (fetch(request.url, headers, body=request.body) if request.body is not None
                  else fetch(request.url, headers))
        if result.status == 304:
            unchanged += 1
            continue
        if result.status == 404 and request.optional:
            missing.append(request.url)
            continue
        if result.status != 200:
            return _unreachable(session, row, item, _status(result), now, result)
        if len(requests) == 1:
            row.etag = result.headers.get("etag") or None
            row.last_modified = result.headers.get("last-modified") or None
        bodies.append((request, result.body))
    row.last_fetched_at_utc = now
    _succeeded(row)
    if not bodies:
        if row.state in {"unreachable", "never_fetched"}:
            row.state = "current" if row.record else "never_fetched"
        row.detail = "Unchanged since the last read."
        session.flush()
        return CheckOutcome(item.publication_id, "current", "unchanged since the last read")
    digest = hashlib.sha256(b"".join(hashlib.sha256(body).digest()
                                     for _r, body in bodies)).hexdigest()
    # Each document is compared with those already read: a later check reads fewer
    # documents (the current year's file only), so their combined digest alone would differ.
    body_digests = [_sha(body) for _r, body in bodies]
    seen = list((row.record or {}).get("documents") or [])
    if digest == row.content_sha256 or (seen and set(body_digests) <= set(seen)):
        if row.state in {"unreachable", "never_fetched"}:
            row.state = "current"
        row.detail = "Unchanged since the last read."
        session.flush()
        return CheckOutcome(item.publication_id, "current", "unchanged")
    points: list[prices.PricePoint] = []
    for request, body in bodies:
        store_payload_content(session, payload_sha256=_sha(body), data=body, received_at_utc=now)
        try:
            points.extend(source.parse(body, now).points)
        except prices.PricesUncertain as exc:
            return _needs_person(session, row, item, now=now, digest=digest, url=request.url,
                                 why=str(exc))
    if not points:
        return _needs_person(session, row, item, now=now, digest=digest, url=item.url,
                             why="the publication answered with no price")
    applied = store_points(
        session, points, family=item.source_family or item.publisher,
        publication_id=item.publication_id, publisher=item.publisher,
        consent_publisher=item.consent_publisher, document_url=bodies[-1][0].url, now=now,
    )
    record = prices.PriceRecord(tuple(points)).to_json()
    held_first = (row.record or {}).get("first_day")
    if held_first and (record["first_day"] is None or held_first < record["first_day"]):
        record["first_day"] = held_first
    record["requests"] = len(requests)
    record["documents"] = list(dict.fromkeys([*body_digests, *seen]))[:50]
    if missing:
        record["not_published"] = [url.split("?")[0].split("/")[-1] for url in missing]
    first_read = row.record is None
    _replace_record(row, record, now=now, digest=digest, document_url=bodies[-1][0].url)
    row.detail = (f"Read {now:%d %b %Y}: {len(points)} figure(s), "
                  f"{applied['observations_added']} new, {applied['observations_revised']} "
                  f"revised; newest {record['last_day']}")[:500]
    session.flush()
    _publish_event(session, item, row, now=now, lines=[], event_type="price.updated",
                   payload={"publication_id": item.publication_id,
                            "source_system": item.source_family,
                            "latest": {k: {"day": v["day"], "value": v["value"],
                                           "unit": v["unit"]}
                                       for k, v in record["latest"].items()}})
    return CheckOutcome(item.publication_id, "first_read" if first_read else "changed",
                        f"{len(points)} figure(s)", applied)


def _needs_person(session, row, item: WatchedPublication, *, now: datetime, digest: str,
                  url: str, why: str) -> CheckOutcome:
    """The source changed and cannot be read with confidence: hold the old record, ask once."""

    if row.pending_sha256 != digest:
        row.pending_sha256 = digest
        row.pending_url = url[:1000]
        row.pending_since_utc = now
        _tell(session, key=f"publication:{item.publication_id}:confirm:{digest}",
              title=f"Please check: {item.title} has changed",
              body=(f"{item.publisher} changed {item.title} on {now:%d %b %Y}, and the product "
                    f"could not read the new version with confidence ({why}).\n"
                    "What it held before stays in use until a person has looked.\n"
                    f"Document: {url}\nConfirm it in Admin -> Data sources -> Watched "
                    "publications once checked."),
              now=now, severity="medium")
    row.state = "needs_confirmation"
    row.detail = (f"Source changed on {_aware(row.pending_since_utc):%d %b %Y}, needs a person to "
                  f"confirm: {why}")[:500]
    session.flush()
    return CheckOutcome(item.publication_id, "needs_confirmation", why)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _status(result: FetchResult) -> str:
    return f"status {result.status} {result.headers.get('error', '')}".strip()


def confirm_publication(session, publication_id: str, *, principal: str, now: datetime
                        ) -> dict[str, Any]:
    """A person has looked at a changed document: the held dates stay, the alarm clears.

    The product still could not read the document, so the record is not changed: the person
    has confirmed that the dates held are right (or entered a moved date as a notice). The
    next document the publisher puts up is read again as usual.
    """

    from eurogas_nexus.db.models import WatchedPublicationRecord
    from eurogas_nexus.db.repositories.audit import record_audit_event

    item = watched_publication(publication_id)
    row = session.get(WatchedPublicationRecord, item.publication_id)
    if row is None or row.state != "needs_confirmation":
        raise ValueError("nothing to confirm: the publication is not waiting for a person")
    now = _aware(now)
    row.content_sha256 = row.pending_sha256
    row.document_url = row.pending_url
    row.pending_sha256 = row.pending_url = row.pending_since_utc = None
    row.state = "current" if row.record else "never_fetched"
    row.confirmed_by = principal[:128]
    row.confirmed_at_utc = now
    row.detail = f"Checked by {principal} on {now:%d %b %Y}; the dates held were kept."[:500]
    record_audit_event(
        session, event_type="governance.data", principal=principal[:128],
        action="publication.confirm", resource=f"watched_publication:{publication_id}",
        outcome="success", severity="info",
        detail=f"Confirmed the changed document of {item.title}", source_system=EVENT_SOURCE,
        now_utc=now,
    )
    session.flush()
    return source_row(item, row, now=now)


def watch_all(session, *, fetch: Fetcher, now: datetime, force: bool = False,
              pause: Callable[[float], None] | None = None) -> list[CheckOutcome]:
    """Check every watched publication (each within its interval), then the deadlines."""

    out = [check_publication(session, item, fetch=fetch, now=now, force=force, pause=pause)
           for item in WATCHED_PUBLICATIONS]
    queue_deadline_notifications(session, now=now)
    return out


def watch_publications_if_due(session_factory, *, now_utc: datetime,
                              fetch: Fetcher | None = None, environ=None) -> dict[str, Any]:
    """The scheduler's hook: at most every :data:`HOOK_EVERY`; never raises."""

    env = os.environ if environ is None else environ
    if str(env.get(WATCH_ENV, "")).strip().lower() == "off":
        return {"status": "off"}
    last = _HOOK_STATE.get("last")
    if last is not None and now_utc - last < HOOK_EVERY:
        return {"status": "not_due"}
    _HOOK_STATE["last"] = now_utc
    try:
        with session_factory() as session:
            outcomes = watch_all(session, fetch=fetch or publication_fetch, now=now_utc)
            from eurogas_nexus.application.notifications import dispatch

            dispatch(session, now=now_utc)
            session.commit()
    except Exception as exc:  # noqa: BLE001 - the watch never stops ingestion
        return {"status": "failed", "error_type": exc.__class__.__name__}
    return {"status": "ok",
            "outcomes": {o.publication_id: o.status for o in outcomes
                         if o.status not in {"skipped", "not_fetched"}}}


# --------------------------------------------------------------------------- calendar


def _hand_calendar():
    from eurogas_nexus.domain.deals.formats import FormatError
    from eurogas_nexus.domain.deals.position import load_trading_calendar

    try:
        return load_trading_calendar()
    except (FormatError, OSError):
        return None


def _published(row) -> datetime | None:
    """When the publisher dated the record it holds (the document's own version date)."""

    if row is None or not row.record or not row.record.get("published_on"):
        return None
    return datetime.combine(date.fromisoformat(row.record["published_on"]), time(0), tzinfo=UTC)


def _hand_item(venue_code: str) -> WatchedPublication | None:
    return next((i for i in WATCHED_PUBLICATIONS if i.hand_venue == venue_code), None)


def _source(item: WatchedPublication | None, *, basis: str, url: str | None = None,
            fetched_at: datetime | None = None, published_at: datetime | None = None,
            changed_at: datetime | None = None, consent: str | None = None) -> dict[str, Any]:
    return {
        "publication_id": item.publication_id if item else None,
        "publisher": item.publisher if item else None,
        "title": item.title if item else None,
        "url": url or (item.url if item else None),
        "basis": basis,
        "fetched_at_utc": _iso(fetched_at),
        "published_at_utc": _iso(published_at),
        "changed_at_utc": _iso(changed_at),
        "attribution": item.attribution if item else "",
        **({"consent": consent} if consent else {}),
    }


@dataclass
class _VenueDays:
    """One venue's days on the desk's calendar, each with where it came from."""

    code: str
    title: str
    hubs: list[str]
    #: ``day -> (what, source)``
    closed: dict[date, tuple[str, dict]] = field(default_factory=dict)
    early: dict[date, tuple[str, dict]] = field(default_factory=dict)
    expiries: list[tuple[dict, dict]] = field(default_factory=list)
    fetched_years: set[int] = field(default_factory=set)
    hand: Any = None


def _consent_line(session, item: WatchedPublication) -> str | None:
    if item.verdict != CONSENTED:
        return None
    from eurogas_nexus.application.publisher_consents import withdrawn_on
    from eurogas_nexus.domain.publications.consents import publisher_consent

    consent = publisher_consent(item.consent_publisher)
    if consent is None:
        return None
    withdrawn = withdrawn_on(session, item.consent_publisher) if session is not None else None
    return f"consent withdrawn on {withdrawn:%Y-%m-%d}" if withdrawn else consent.line()


def _venue_days(session, rows: dict[str, Any]) -> list[_VenueDays]:
    """The hand file's venues with every fetched exchange calendar laid over them.

    For each year a fetched calendar covers, its closed days replace the hand file's; a day the
    exchange publishes as an early close is not a closed day, whatever the file says.
    """

    hand = _hand_calendar()
    out: dict[str, _VenueDays] = {}
    for venue in (hand.venues if hand else ()):
        item = _hand_item(venue.code)
        source = _source(item, basis="hand_maintained", url=venue.check_url or None)
        source["checked"] = venue.checked
        source["file_source"] = venue.source
        days = _VenueDays(code=venue.code, title=venue.title,
                          hubs=list(item.hubs) if item else [], hand=venue)
        for day in venue.closed:
            days.closed[day] = ("closed", source)
        for day, what in venue.early_closes:
            days.early[day] = (what, source)
        out[venue.code] = days
    for item in WATCHED_PUBLICATIONS:
        if not item.calendar_venue or item.verdict not in FETCHED_VERDICTS:
            continue
        row = rows.get(item.publication_id)
        if row is None or not row.record or "closed" not in row.record:
            continue
        record = row.record
        days = out.setdefault(item.calendar_venue, _VenueDays(
            code=item.calendar_venue, title=item.title, hubs=list(item.hubs)))
        source = _source(item, basis="fetched", url=row.document_url,
                         fetched_at=_aware(row.last_fetched_at_utc),
                         changed_at=_aware(row.last_changed_at_utc),
                         consent=_consent_line(session, item))
        source["version"] = record.get("version") or ""
        years = {int(y) for y in record.get("years") or []}
        if record.get("closed"):
            for day in [d for d in days.closed if d.year in years]:
                del days.closed[day]
            for day in [d for d in days.early if d.year in years]:
                del days.early[day]
            days.fetched_years |= years
            for entry in record["closed"]:
                days.closed[date.fromisoformat(entry["day"])] = (entry["what"], source)
        for entry in record.get("early_closes") or []:
            day = date.fromisoformat(entry["day"])
            days.early[day] = (entry["what"], source)
            days.closed.pop(day, None)
        for expiry in record.get("expiries") or []:
            days.expiries.append((expiry, source))
    return list(out.values())


def effective_trading_calendar(session=None):
    """The desk's trading calendar: fetched exchange calendars over the hand file.

    The daily pack's check "no deals on a trading day" uses it. Without a runtime store (or
    when it cannot be read) it is the hand file alone.
    """

    from eurogas_nexus.domain.deals.position import TradingCalendar, Venue

    hand = _hand_calendar() or TradingCalendar(years=frozenset(), venues=())
    if session is None:
        try:
            from eurogas_nexus.db.session import get_session_factory, resolve_database_url

            if resolve_database_url() is None:
                return hand
            with get_session_factory()() as own:
                return effective_trading_calendar(own)
        except Exception:  # noqa: BLE001 - the hand file is the fallback
            return hand
    from eurogas_nexus.db.models import WatchedPublicationRecord

    try:
        rows = {row.publication_id: row for row in session.query(WatchedPublicationRecord).all()}
    except Exception:  # noqa: BLE001 - no table yet: the hand file
        return hand
    venues = []
    years = set(hand.years)
    for days in _venue_days(session, rows):
        held = days.hand
        fetched = bool(days.fetched_years)
        years |= days.fetched_years
        venues.append(Venue(
            code=days.code, title=days.title,
            source=(", ".join(sorted({s["title"] or "" for _w, s in days.closed.values()
                                      if s["basis"] == "fetched"}))
                    if fetched else (held.source if held else "")),
            checked=fetched or bool(held and held.checked),
            closed=frozenset(days.closed),
            check_url=held.check_url if held else "",
            check_by=None if fetched else (held.check_by if held else None),
            early_closes=tuple(sorted((d, w) for d, (w, _s) in days.early.items())),
        ))
    return TradingCalendar(years=frozenset(years), venues=tuple(venues),
                           source_path=hand.source_path, notes=list(hand.notes))


def calendar_items(session, *, now: datetime, days: int = 60,
                   allowed_publishers: set[str] | None = None) -> list[dict[str, Any]]:
    """The desk's calendar from now to ``days`` ahead (see the module text), soonest first."""

    from eurogas_nexus.application.tariff_book import list_notices
    from eurogas_nexus.db.models import WatchedPublicationRecord

    now = _aware(now)
    end = now + timedelta(days=days)
    items: list[dict[str, Any]] = []
    rows = {row.publication_id: row for row in session.query(WatchedPublicationRecord).all()}
    for venue in _venue_days(session, rows):
        for day, (what, source) in sorted(venue.closed.items()):
            at = datetime.combine(day, time(0), tzinfo=UTC)
            if now - timedelta(days=1) <= at <= end and day.weekday() < 5:
                title = f"{venue.title}: closed" + (f" ({what})" if what != "closed" else "")
                items.append({"key": f"closed:{venue.code}:{day.isoformat()}",
                              "kind": "non_trading_day", "at": _iso(at), "day": day.isoformat(),
                              "title": title, "hubs": venue.hubs,
                              "venue": venue.code, "source": source})
        for day, (what, source) in sorted(venue.early.items()):
            at = datetime.combine(day, time(0), tzinfo=UTC)
            if now - timedelta(days=1) <= at <= end:
                items.append({"key": f"early:{venue.code}:{day.isoformat()}",
                              "kind": "early_close", "at": _iso(at), "day": day.isoformat(),
                              "title": f"{venue.title}: {what}", "hubs": venue.hubs,
                              "venue": venue.code, "source": source})
        for expiry, source in venue.expiries:
            day = date.fromisoformat(expiry["last_trading_day"])
            at = datetime.combine(day, time(0), tzinfo=UTC)
            if now - timedelta(days=1) <= at <= end:
                items.append({"key": f"expiry:{venue.code}:{expiry['kind']}:"
                                     f"{expiry['delivery_start']}",
                              "kind": "expiry", "at": _iso(at), "day": day.isoformat(),
                              "title": (f"{venue.title}: last trading day of the "
                                        f"{expiry['maturity']} {expiry['kind']} futures"),
                              "hubs": venue.hubs, "venue": venue.code, "source": source})
        held = venue.hand
        if held is not None and not venue.fetched_years and held.check_by is not None and (
                not held.checked or held.check_by <= end.date()):
            at = datetime.combine(held.check_by, time(9), tzinfo=UTC)
            if at <= end:
                item = _hand_item(venue.code)
                source = _source(item, basis="hand_maintained", url=held.check_url or None)
                source["checked"] = held.checked
                source["file_source"] = held.source
                items.append({"key": f"check:{venue.code}:{held.check_by.isoformat()}",
                              "kind": "check_calendar", "at": _iso(at),
                              "day": held.check_by.isoformat(),
                              "title": (f"{held.title}: compare the holidays with the "
                                        "publisher's page"),
                              "hubs": venue.hubs, "venue": venue.code, "overdue": at < now,
                              "source": source})
    entsog_item = watched_publication("entsog-cam-auction-calendar")
    entsog_row = rows.get(entsog_item.publication_id)
    for notice in list_notices(session, now_utc=now, days=days, kind="auction",
                               allowed_publishers=allowed_publishers):
        if notice.get("state", "open") != "open":
            continue
        fetched = notice["publisher_id"] == entsog_item.tariff_publisher_id
        items.append({
            "key": f"auction:{notice['notice_key']}",
            "kind": "auction",
            "at": notice["opens_at_utc"],
            "title": notice["title"],
            "product": notice["product"],
            "capacity": "interruptible" if ":interruptible:" in notice["notice_key"] else "firm",
            "hubs": list(entsog_item.hubs),
            "offers_from": notice.get("offers_from"),
            "offers_to": notice.get("offers_to"),
            "source": _source(
                entsog_item if fetched else None,
                basis="fetched" if fetched else notice["basis"],
                url=notice.get("source_url"),
                fetched_at=_aware(entsog_row.last_fetched_at_utc) if fetched and entsog_row
                else None,
                published_at=_published(entsog_row) if fetched else None,
                changed_at=_aware(entsog_row.last_changed_at_utc) if fetched and entsog_row
                else None,
            ) | ({} if fetched else {"publisher": notice.get("publisher_name"),
                                     "title": notice.get("publisher_name")}),
        })
    if entsog_row is not None and entsog_row.record and (
        allowed_publishers is None or entsog_item.tariff_publisher_id in allowed_publishers
    ):
        for auction in entsog_row.record.get("auctions", []):
            day = auction.get("offer_levels_published_on")
            if not day or auction.get("capacity") != "firm":
                continue
            at = datetime.combine(date.fromisoformat(day), time(0), tzinfo=UTC)
            if now - timedelta(days=1) <= at <= end:
                items.append({
                    "key": f"offer_levels:{auction['key']}", "kind": "offer_levels",
                    "at": _iso(at), "day": day,
                    "title": f"Offer levels published for the {auction['label'].lower()}",
                    "hubs": list(entsog_item.hubs),
                    "source": _source(entsog_item, basis="fetched", url=entsog_row.document_url,
                                      fetched_at=_aware(entsog_row.last_fetched_at_utc),
                                      published_at=_published(entsog_row),
                                      changed_at=_aware(entsog_row.last_changed_at_utc)),
                })
    # Slot and auction offers an operator published, fetched under its consent (in force).
    from eurogas_nexus.application.publisher_consents import withdrawn_on

    for item in WATCHED_PUBLICATIONS:
        if item.parser not in NOTICE_SOURCES:
            continue
        row = rows.get(item.publication_id)
        if withdrawn_on(session, item.consent_publisher) is not None:
            continue
        for notice in list_notices(session, now_utc=now, days=days, kind="lng_slot",
                                   publisher_id=item.publication_id):
            if notice.get("state", "open") != "open":
                continue
            items.append({
                "key": f"slot:{notice['notice_key']}",
                "kind": "slot_offer",
                "at": notice["opens_at_utc"],
                "title": notice["title"],
                "hubs": list(item.hubs),
                "offers_from": notice.get("offers_from"),
                "offers_to": notice.get("offers_to"),
                "facility_id": notice.get("facility_id"),
                "source": _source(item, basis="fetched", url=notice.get("source_url"),
                                  fetched_at=_aware(row.last_fetched_at_utc) if row else None,
                                  changed_at=_aware(row.last_changed_at_utc) if row else None,
                                  consent=_consent_line(session, item)),
            })
    for item in WATCHED_PUBLICATIONS:
        row = rows.get(item.publication_id)
        if row is not None and row.state == "needs_confirmation":
            items.append({
                "key": f"confirm:{item.publication_id}", "kind": "source_changed",
                "at": _iso(_aware(row.pending_since_utc) or now),
                "title": f"{item.title}: source changed, needs a person to confirm",
                "hubs": list(item.hubs),
                "source": _source(item, basis="fetched", url=row.pending_url,
                                  fetched_at=_aware(row.last_fetched_at_utc),
                                  changed_at=_aware(row.pending_since_utc)),
            })
    # The desk's own regas auction cases: the auction close and the cargo offer's expiry (the
    # session's book scope applies to the cases read).
    from eurogas_nexus.application.regas_auction import calendar_items as regas_items

    items += regas_items(session, now=now, days=days)
    return sorted(items, key=lambda entry: (entry["at"] or "", entry["key"]))


def queue_deadline_notifications(session, *, now: datetime) -> int:
    """Tell the desk ahead of a non-trading day and of a hand-maintained calendar's check day.

    Auction windows are already alerted by the tariff book's monitoring (three days ahead,
    category ``capacity``), so they are not repeated here. Each notice goes once. A venue whose
    exchange calendar has been fetched needs no check reminder.
    """

    from eurogas_nexus.db.models import WatchedPublicationRecord

    now = _aware(now)
    queued = 0
    rows = {row.publication_id: row for row in session.query(WatchedPublicationRecord).all()}
    for venue in _venue_days(session, rows):
        for day, (_what, source) in sorted(venue.closed.items()):
            at = datetime.combine(day, time(0), tzinfo=UTC)
            if day.weekday() < 5 and now <= at <= now + NON_TRADING_LEAD:
                fetched = source["basis"] == "fetched"
                origin = (f"From {source['title']}, read {source['fetched_at_utc'] or ''}"
                          if fetched else
                          f"From the desk's hand-maintained calendar ({source.get('file_source')}"
                          + ("" if source.get("checked") else "; not yet checked against the "
                             "publisher's page") + ")")
                queued += _tell(
                    session, key=f"calendar:closed:{venue.code}:{day.isoformat()}",
                    title=f"{day:%a %d %b}: {venue.title} closed",
                    body=(f"{venue.title} does not trade on {day:%A %d %B %Y}.\n{origin}.\n"
                          f"Publisher's page: {source.get('url') or ''}"),
                    now=now, severity="info", category="alert")
        held = venue.hand
        if held is not None and not venue.fetched_years and held.check_by is not None \
                and not held.checked:
            due = datetime.combine(held.check_by, time(9), tzinfo=UTC)
            if now >= due - CHECK_LEAD:
                item = _hand_item(venue.code)
                queued += _tell(
                    session, key=f"calendar:check:{venue.code}:{held.check_by.isoformat()}",
                    title=f"Check by {held.check_by:%d %b}: {held.title} holidays",
                    body=(f"The product has not read {held.title}'s calendar yet, so the desk's "
                          "hand-maintained file is in use. Please compare "
                          "reference_data/desk/trading_calendars.toml with the publisher's page "
                          f"by {held.check_by:%d %B %Y}, then set checked = true.\n"
                          f"Page: {held.check_url or (item.url if item else '')}"),
                    now=now, severity="low")
    return queued


# --------------------------------------------------------------------------- status


def source_row(item: WatchedPublication, row, *, now: datetime, session=None) -> dict[str, Any]:
    state = row.state if row is not None else (unfetched_state(item) or "never_fetched")
    out = item.to_json() | {
        "state": state,
        "detail": (row.detail if row is not None else "") or "",
        "last_checked_at_utc": _iso(_aware(row.last_checked_at_utc)) if row else None,
        "last_fetched_at_utc": _iso(_aware(row.last_fetched_at_utc)) if row else None,
        "last_changed_at_utc": _iso(_aware(row.last_changed_at_utc)) if row else None,
        "document_url": row.document_url if row else None,
        "pending_url": row.pending_url if row else None,
        "pending_since_utc": _iso(_aware(row.pending_since_utc)) if row else None,
        "confirmed_by": row.confirmed_by if row else None,
        "confirmed_at_utc": _iso(_aware(row.confirmed_at_utc)) if row else None,
        "has_previous_record": bool(row is not None and row.previous_record),
        "fetch_refusal": fetch_refusal(item),
        "consecutive_failures": int(getattr(row, "consecutive_failures", 0) or 0) if row else 0,
        "next_check_at_utc": _iso(_aware(getattr(row, "next_check_at_utc", None))) if row
        else None,
        "consent_line": _consent_line(session, item) if session is not None else (
            _consent_line(None, item)),
        "record_summary": _summary(row.record) if row is not None and row.record else None,
    }
    if item.hand_venue:
        calendar = _hand_calendar()
        venue = next((v for v in (calendar.venues if calendar else ())
                      if v.code == item.hand_venue), None)
        out["hand_file"] = None if venue is None else {
            "venue": venue.code, "checked": venue.checked,
            "check_by": _iso(venue.check_by), "source": venue.source,
            "years": sorted(calendar.years),
            "overdue": bool(venue.check_by and not venue.checked
                            and venue.check_by < _aware(now).date()
                            and not (row is not None and row.record)),
            "fallback_only": bool(row is not None and row.record),
        }
    return out


def _summary(record: dict) -> dict[str, Any]:
    """A short summary of the record held, for the administrators' list."""

    if "latest" in record:
        return {"kind": "prices", "first_day": record.get("first_day"),
                "last_day": record.get("last_day"), "series": len(record.get("latest") or {}),
                "not_published": record.get("not_published") or []}
    if "closed" in record:
        return {"kind": "calendar", "years": record.get("years") or [],
                "closed": len(record.get("closed") or []),
                "early_closes": len(record.get("early_closes") or []),
                "expiries": len(record.get("expiries") or []),
                "version": record.get("version") or ""}
    if "auctions" in record:
        return {"kind": "auctions", "auctions": len(record.get("auctions") or []),
                "published_on": record.get("published_on")}
    return {"kind": "other"}


def source_status(session, *, now: datetime) -> list[dict[str, Any]]:
    """Every watched publication with its terms, state and times (the administrators' list)."""

    from eurogas_nexus.db.models import WatchedPublicationRecord

    rows = {row.publication_id: row for row in session.query(WatchedPublicationRecord).all()}
    return [source_row(item, rows.get(item.publication_id), now=now, session=session)
            for item in WATCHED_PUBLICATIONS]


__all__ = [
    "EVENT_SOURCE",
    "FETCH",
    "PARSERS",
    "PUBLICATION_USER_AGENT",
    "NOTICE_SOURCES",
    "SERIES_SOURCES",
    "WATCH_ENV",
    "CheckOutcome",
    "calendar_items",
    "check_publication",
    "confirm_publication",
    "describe_change",
    "effective_trading_calendar",
    "publication_fetch",
    "queue_deadline_notifications",
    "source_status",
    "watch_all",
    "watch_publications_if_due",
]
