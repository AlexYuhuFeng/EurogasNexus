"""Watch the public publications the desk relies on, and tell the desk what changed.

The registry (``domain/publications/registry``) says, for each publication, where it is and
whether its terms let the product keep it. :func:`check_publication` does one check:

1. A publication the product may not fetch (hand-maintained, link only, or no entry in the
   legal register) is recorded with that state and never read.
2. Within its interval nothing is read again (``skipped``). Otherwise the host's
   ``robots.txt`` is read first (a disallowed page is not read), then the publication's page,
   then the document the page links, with this product's own User-Agent and the conditional
   headers of the last read.
3. The document's SHA-256 is compared with the one held. The same digest: ``current``.
4. A new digest: the document is kept once by its digest (``raw_payload_contents``) and parsed.
   Parsed with confidence: the record is replaced, the previous record is kept beside it with
   its fetch time, the parser's records are applied (ENTSOG's auctions to the capacity
   notices), a ``capacity.changed`` event goes on the outbox and, when an earlier record
   existed, one notification says what moved. Not parsed with confidence (a layout change):
   the held record stays, the state becomes ``needs_confirmation`` with the document's link,
   and the desk is told once for that document; nothing is guessed.
5. A page or document that cannot be read: ``unreachable`` with the reason, told once a day.

:func:`calendar_items` is the desk's calendar: upcoming non-trading days and early closes
(the hand-maintained file, marked so), auction windows and offer-level publication days,
reminders to check a hand-maintained calendar, and sources that need a person. Every item
carries its source and, for fetched ones, when it was published and fetched.
:func:`source_status` is the administrators' list of every watched publication.
:func:`queue_deadline_notifications` raises the existing notifications ahead of a non-trading
day and a calendar check. :func:`watch_publications_if_due` is the scheduler's hook.

The fetcher is passed in, so tests run on fixtures with no network
(``news_ingest.http_fetch`` is the real one). Nothing here signs in, registers or accepts terms.

发布物监控：在条款允许时按间隔获取、以摘要检测变化、解析并保留旧记录；无法确定时保留旧值并请人确认。
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from eurogas_nexus.application.news_ingest import Fetcher, FetchResult, http_fetch, robots_allows
from eurogas_nexus.domain.publications import entsog_cam_calendar as entsog
from eurogas_nexus.domain.publications.registry import (
    FETCH,
    HAND_MAINTAINED,
    LINK_ONLY,
    WATCHED_PUBLICATIONS,
    WatchedPublication,
    fetch_refusal,
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

_HOOK_STATE: dict[str, datetime] = {}


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

    #: The document's URL from the page's bytes (raises the parser's uncertainty error).
    locate: Callable[[bytes, str], str]
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


PARSERS: dict[str, Parser] = {
    "entsog_cam_calendar": Parser(
        locate=_entsog_locate,
        parse=entsog.parse_calendar,
        apply=_entsog_apply,
        uncertain=entsog.CalendarUncertain,
    ),
}


def describe_change(previous: dict | None, current: dict) -> list[str]:
    """What moved between two ENTSOG calendar records, in plain words (at most ten lines)."""

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
            state="never_fetched" if item.verdict == FETCH else item.verdict,
            detail="",
        )
        session.add(row)
    return row


def _tell(session, *, key: str, title: str, body: str, now: datetime,
          severity: str = "medium", category: str = "source") -> bool:
    from eurogas_nexus.application.notifications import queue_notification

    return queue_notification(session, category=category, severity=severity, title=title,
                              body=body, dedupe_key=key, now=now)


def _unreachable(session, row, item: WatchedPublication, why: str, now: datetime
                 ) -> CheckOutcome:
    row.state = "unreachable"
    row.detail = f"Could not be read on {now:%d %b %Y %H:%M} UTC: {why}"[:500]
    _tell(session, key=f"publication:{item.publication_id}:unreachable:{now:%Y-%m-%d}",
          title=f"Not read: {item.title}",
          body=(f"{item.title} ({item.publisher}) could not be read: {why}.\n"
                f"Page: {item.url}\nThe last record held stays in use; the next check tries "
                "again."),
          now=now, severity="low")
    return CheckOutcome(item.publication_id, "unreachable", why)


def _publish_event(session, item: WatchedPublication, row, *, now: datetime,
                   lines: list[str]) -> None:
    from eurogas_nexus.application.market_events import publish
    from eurogas_nexus.domain.market_events.model import MarketEvent

    publish(session, MarketEvent(
        source_id=EVENT_SOURCE,
        event_type="capacity.changed",
        subject_key=f"publication:{item.publication_id}",
        ingested_at_utc=now,
        payload={"publication_id": item.publication_id, "content_sha256": row.content_sha256,
                 "document_url": row.document_url, "changes": lines},
        identity=f"publication:{item.publication_id}:{row.content_sha256}",
        correlation_id=item.publication_id,
    ))


def check_publication(session, item: WatchedPublication, *, fetch: Fetcher, now: datetime,
                      force: bool = False) -> CheckOutcome:
    """One check of one publication (see the module text); commit is the caller's."""

    from eurogas_nexus.db.repositories.raw_archive import store_payload_content

    now = _aware(now)
    row = _row(session, item)
    refusal = fetch_refusal(item)
    if refusal:
        row.state = item.verdict if item.verdict in {HAND_MAINTAINED, LINK_ONLY} else "link_only"
        row.detail = refusal
        session.flush()
        return CheckOutcome(item.publication_id, "not_fetched", refusal)
    last = _aware(row.last_checked_at_utc)
    if not force and last is not None and now - last < timedelta(minutes=item.interval_minutes):
        return CheckOutcome(item.publication_id, "skipped", "within the publication's interval")
    row.last_checked_at_utc = now
    parser = PARSERS[item.parser]
    allowed, why = robots_allows(fetch, item.url)
    if not allowed:
        return _unreachable(session, row, item, why, now)
    page = fetch(item.url, {})
    if page.status != 200:
        return _unreachable(session, row, item, _status(page), now)
    try:
        document_url = parser.locate(page.body, item.url)
    except parser.uncertain as exc:
        return _needs_person(session, row, item, now=now, digest=_sha(page.body),
                             url=item.url, why=str(exc))
    headers: dict[str, str] = {}
    if row.document_url == document_url:
        if row.etag:
            headers["If-None-Match"] = row.etag
        if row.last_modified:
            headers["If-Modified-Since"] = row.last_modified
    document = fetch(document_url, headers)
    if document.status == 304:
        row.last_fetched_at_utc = now
        if row.state == "unreachable":
            row.state = "current" if row.record else "never_fetched"
        session.flush()
        return CheckOutcome(item.publication_id, "current", "unchanged since the last read")
    if document.status != 200:
        return _unreachable(session, row, item, _status(document), now)
    digest = _sha(document.body)
    row.last_fetched_at_utc = now
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
    # Kept once by its digest, where the terms allow storing it (only fetched ones get here).
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
    row.previous_record = row.record
    row.previous_fetched_at_utc = row.record_fetched_at_utc
    row.record = record
    row.record_fetched_at_utc = now
    row.content_sha256 = digest
    row.document_url = document_url
    row.last_changed_at_utc = now
    row.pending_sha256 = row.pending_url = row.pending_since_utc = None
    row.state = "current"
    applied = parser.apply(session, item, parsed, now=now, document_url=document_url)
    row.detail = (f"Read {now:%d %b %Y} from {document_url}"
                  + (f"; {len(lines)} change(s)" if lines else ""))[:500]
    session.flush()
    _publish_event(session, item, row, now=now, lines=lines)
    if not first_read:
        _tell(session, key=f"publication:{item.publication_id}:changed:{digest}",
              title=f"Updated: {item.title}",
              body="\n".join([
                  f"{item.publisher} published a new version of {item.title}; the product has "
                  "read it and updated the calendar.",
                  *(lines or ["No auction date moved."]),
                  f"Document: {document_url}",
                  item.attribution,
              ]),
              now=now, severity="info")
    return CheckOutcome(item.publication_id, "changed" if not first_read else "first_read",
                        f"{len(lines)} change(s)", applied)


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
                    "The dates it held before stay in use until a person has looked.\n"
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


def watch_all(session, *, fetch: Fetcher, now: datetime, force: bool = False
              ) -> list[CheckOutcome]:
    """Check every watched publication (each within its interval), then the deadlines."""

    out = [check_publication(session, item, fetch=fetch, now=now, force=force)
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
            outcomes = watch_all(session, fetch=fetch or http_fetch, now=now_utc)
            from eurogas_nexus.application.notifications import dispatch

            dispatch(session, now=now_utc)
            session.commit()
    except Exception as exc:  # noqa: BLE001 - the watch never stops ingestion
        return {"status": "failed", "error_type": exc.__class__.__name__}
    return {"status": "ok",
            "outcomes": {o.publication_id: o.status for o in outcomes
                         if o.status not in {"skipped", "not_fetched"}}}


# --------------------------------------------------------------------------- calendar


def _calendar():
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
            changed_at: datetime | None = None) -> dict[str, Any]:
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
    }


def calendar_items(session, *, now: datetime, days: int = 60,
                   allowed_publishers: set[str] | None = None) -> list[dict[str, Any]]:
    """The desk's calendar from now to ``days`` ahead (see the module text), soonest first."""

    from eurogas_nexus.application.tariff_book import list_notices
    from eurogas_nexus.db.models import WatchedPublicationRecord

    now = _aware(now)
    end = now + timedelta(days=days)
    items: list[dict[str, Any]] = []
    calendar = _calendar()
    for venue in (calendar.venues if calendar else ()):
        item = _hand_item(venue.code)
        hubs = list(item.hubs) if item else []
        basis = "hand_maintained"
        source = _source(item, basis=basis, url=venue.check_url or None)
        source["checked"] = venue.checked
        source["file_source"] = venue.source
        for day in sorted(venue.closed):
            at = datetime.combine(day, time(0), tzinfo=UTC)
            if now - timedelta(days=1) <= at <= end and day.weekday() < 5:
                items.append({"key": f"closed:{venue.code}:{day.isoformat()}",
                              "kind": "non_trading_day", "at": _iso(at), "day": day.isoformat(),
                              "title": f"{venue.title}: closed", "hubs": hubs,
                              "venue": venue.code, "source": source})
        for day, what in venue.early_closes:
            at = datetime.combine(day, time(0), tzinfo=UTC)
            if now - timedelta(days=1) <= at <= end:
                items.append({"key": f"early:{venue.code}:{day.isoformat()}",
                              "kind": "early_close", "at": _iso(at), "day": day.isoformat(),
                              "title": f"{venue.title}: {what}", "hubs": hubs,
                              "venue": venue.code, "source": source})
        if venue.check_by is not None and (not venue.checked or venue.check_by <= end.date()):
            at = datetime.combine(venue.check_by, time(9), tzinfo=UTC)
            if at <= end:
                items.append({"key": f"check:{venue.code}:{venue.check_by.isoformat()}",
                              "kind": "check_calendar", "at": _iso(at),
                              "day": venue.check_by.isoformat(),
                              "title": (f"{venue.title}: compare the holidays with the "
                                        "publisher's page"),
                              "hubs": hubs, "venue": venue.code, "overdue": at < now,
                              "source": source})
    rows = {row.publication_id: row for row in session.query(WatchedPublicationRecord).all()}
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
    category ``capacity``), so they are not repeated here. Each notice goes once.
    """

    now = _aware(now)
    queued = 0
    calendar = _calendar()
    for venue in (calendar.venues if calendar else ()):
        item = _hand_item(venue.code)
        for day in sorted(venue.closed):
            at = datetime.combine(day, time(0), tzinfo=UTC)
            if day.weekday() < 5 and now <= at <= now + NON_TRADING_LEAD:
                queued += _tell(
                    session, key=f"calendar:closed:{venue.code}:{day.isoformat()}",
                    title=f"{day:%a %d %b}: {venue.title} closed",
                    body=(f"{venue.title} does not trade on {day:%A %d %B %Y}.\n"
                          f"From the desk's hand-maintained calendar ({venue.source}"
                          + ("" if venue.checked else "; not yet checked against the "
                             "publisher's page") + f").\nPublisher's page: {venue.check_url}"),
                    now=now, severity="info", category="alert")
        if venue.check_by is not None and not venue.checked:
            due = datetime.combine(venue.check_by, time(9), tzinfo=UTC)
            if now >= due - CHECK_LEAD:
                queued += _tell(
                    session, key=f"calendar:check:{venue.code}:{venue.check_by.isoformat()}",
                    title=f"Check by {venue.check_by:%d %b}: {venue.title} holidays",
                    body=(f"The product may not store {venue.title}'s calendar (the "
                          "publisher's terms), so the desk keeps it by hand. Please compare "
                          "reference_data/desk/trading_calendars.toml with the publisher's page "
                          f"by {venue.check_by:%d %B %Y}, then set checked = true.\n"
                          f"Page: {venue.check_url or (item.url if item else '')}"),
                    now=now, severity="low")
    return queued


# --------------------------------------------------------------------------- status


def source_row(item: WatchedPublication, row, *, now: datetime) -> dict[str, Any]:
    state = row.state if row is not None else (
        "never_fetched" if item.verdict == FETCH else item.verdict
    )
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
    }
    if item.hand_venue:
        calendar = _calendar()
        venue = next((v for v in (calendar.venues if calendar else ())
                      if v.code == item.hand_venue), None)
        out["hand_file"] = None if venue is None else {
            "venue": venue.code, "checked": venue.checked,
            "check_by": _iso(venue.check_by), "source": venue.source,
            "years": sorted(calendar.years),
            "overdue": bool(venue.check_by and not venue.checked
                            and venue.check_by < _aware(now).date()),
        }
    return out


def source_status(session, *, now: datetime) -> list[dict[str, Any]]:
    """Every watched publication with its terms, state and times (the administrators' list)."""

    from eurogas_nexus.db.models import WatchedPublicationRecord

    rows = {row.publication_id: row for row in session.query(WatchedPublicationRecord).all()}
    return [source_row(item, rows.get(item.publication_id), now=now)
            for item in WATCHED_PUBLICATIONS]


__all__ = [
    "EVENT_SOURCE",
    "PARSERS",
    "WATCH_ENV",
    "CheckOutcome",
    "calendar_items",
    "check_publication",
    "confirm_publication",
    "describe_change",
    "queue_deadline_notifications",
    "source_status",
    "watch_all",
    "watch_publications_if_due",
]
