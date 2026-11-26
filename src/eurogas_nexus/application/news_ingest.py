"""Bring news items in: poll the registered feeds and make items of the REMIT messages held.

Two producers fill ``news_items`` (``db/models/news.py``):

* :func:`sync_remit_items` turns each REMIT message the platform already holds (latest version
  per message, ingested in a window) into an item: publisher the market participant, title the
  asset and the unavailability, summary the message's own fields with its figures as stated,
  linked to the message's market event subject ``outage:<message id>``. No outbound read.
* :func:`poll_source` reads one registered feed (``domain/news/sources``), only when the
  source's terms permit reuse and an address is recorded on the publisher's host, no more often
  than the source's interval, after reading the host's ``robots.txt`` (a disallowed feed is not
  read), with conditional headers (``ETag``, ``Last-Modified``). The fetcher is passed in, so
  tests run on recorded fixtures with no network; :func:`http_fetch` is the real one.

Each item's ``item_id`` is derived from its source and the entry's own identifier, so reading
the same entry again changes nothing (``unchanged``); a changed entry is the next revision. An
item that is new or changed publishes a ``news.published`` market event in the same
transaction. A feed item that names an asset with a held, open REMIT outage is linked to that
outage (``linked_event_key``) and its event carries the outage's key and the ``outages`` input
class, so the opportunities that read that outage re-evaluate (``market_events``). A REMIT
item's own outage event is published by change capture (M5), so its news event carries no key.

What is kept follows the source's terms: the feed's summary only where ``store`` is
``summary``. Nothing here signs in, registers, or sends anything.

新闻采集：轮询登记的订阅源（遵守条款、robots 与间隔），并将已持有的 REMIT 消息转为新闻条目；
新增或变更时发布 ``news.published`` 市场事件。
"""

from __future__ import annotations

import hashlib
import re
import urllib.robotparser
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from eurogas_nexus.domain.news.feeds import FeedError, parse_feed, plain_text
from eurogas_nexus.domain.news.sources import NewsSource, news_source, poll_refusal
from eurogas_nexus.domain.news.tagging import Tags, tag_text, zone_hub

USER_AGENT = "EurogasNexus-NewsPoller/1.0"
#: Cargo statuses whose vessel names are matched in items.
OPEN_CARGO_STATUSES = ("loading", "laden", "discharging")
EVENT_SOURCE = "src-news"
REMIT_WINDOW = timedelta(days=14)
_ASSET_KINDS = frozenset({"terminal", "pipeline", "field"})


@dataclass(frozen=True)
class FetchResult:
    """What one HTTP read returned."""

    status: int
    body: bytes = b""
    headers: dict[str, str] = field(default_factory=dict)


Fetcher = Callable[[str, dict[str, str]], FetchResult]


@dataclass
class PollOutcome:
    """What one poll of one source did."""

    source_id: str
    status: str
    detail: str = ""
    seen: int = 0
    new: int = 0
    changed: int = 0
    item_ids: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "status": self.status,
            "detail": self.detail,
            "seen": self.seen,
            "new": self.new,
            "changed": self.changed,
            "item_ids": list(self.item_ids),
        }


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def item_id_for(source_id: str, source_ref: str) -> str:
    """The stable id of an entry: a digest of its source and its own identifier."""

    digest = hashlib.sha256(f"{source_id}\n{source_ref}".encode()).hexdigest()
    return f"nw-{digest[:24]}"


def content_sha256(*, title: str, summary: str, url: str | None,
                   published: datetime | None) -> str:
    """SHA-256 over what is kept of an item (not when it was retrieved)."""

    when = _aware(published).isoformat() if published else ""
    text = "\n".join([title, summary, url or "", when])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------------- the store


def held_vessels(session) -> list[str]:
    """Vessel names of the firm's open cargoes (matched as whole names in items)."""

    from eurogas_nexus.db.models import LngCargoRecord

    rows = (
        session.query(LngCargoRecord.vessel_name)
        .filter(LngCargoRecord.status.in_(OPEN_CARGO_STATUSES))
        .all()
    )
    return sorted({row[0] for row in rows if row[0]})


def _latest_remit(session, *, since: datetime | None = None, open_at: datetime | None = None):
    from eurogas_nexus.db.models import RemitUmmRecord

    query = session.query(RemitUmmRecord)
    naive = session.get_bind().dialect.name == "sqlite"
    if since is not None:
        query = query.filter(
            RemitUmmRecord.ingested_at_utc >= (since.replace(tzinfo=None) if naive else since)
        )
    latest: dict[str, Any] = {}
    # An unordered ``.limit(20_000)`` here picked an arbitrary part of the versions, so past
    # the bound a message's "latest" could be an older version; the bound now refuses.
    from eurogas_nexus.application.bounded_reads import read_bounded

    for row in read_bounded(query, 20_000, what="REMIT message version"):
        held = latest.get(row.message_id)
        if held is None or row.version > held.version:
            latest[row.message_id] = row
    rows = list(latest.values())
    if open_at is not None:
        rows = [
            row for row in rows
            if str(row.event_status).lower() == "active"
            and (row.event_stop_utc is None or _aware(row.event_stop_utc) > open_at)
        ]
    return rows


def outage_link(session, tags: Tags, *, at: datetime) -> tuple[str | None, dict[str, Any] | None]:
    """The held, open REMIT outage an outage item names by its asset, or ``(None, None)``.

    An asset is named when the item and the message's asset name share a terminal, pipeline
    or field of the gazetteer. An operator, a hub or a country alone is not an asset: an
    operator runs many, so "Gassco reports an outage" does not say which message it is. The
    most recently published message wins.
    """

    if "outage" not in tags.event_types:
        return None, None
    named = {e.entity_id for e in tags.entities if e.kind in _ASSET_KINDS}
    if not named:
        return None, None
    best = None
    for row in _latest_remit(session, open_at=at):
        assets = {e.entity_id for e in tag_text(str(row.asset_name or "")).entities
                  if e.kind in _ASSET_KINDS}
        if assets & named and (best is None or _aware(row.published_at_utc)
                               > _aware(best.published_at_utc)):
            best = row
    if best is None:
        return None, None
    return f"outage:{best.message_id}", {"message_id": best.message_id,
                                         "asset_name": best.asset_name}


def upsert_item(
    session,
    *,
    source: NewsSource,
    source_ref: str,
    url: str | None,
    publisher: str,
    title: str,
    summary: str,
    language: str,
    published: datetime | None,
    retrieved: datetime,
    tags: Tags,
    linked_event_key: str | None,
    now: datetime,
) -> tuple[str, str]:
    """Store one item; ``(item_id, "new" | "changed" | "unchanged")``. Publishes its event."""

    from eurogas_nexus.db.models import NewsItemRecord

    item_id = item_id_for(source.source_id, source_ref)
    kept_summary = summary if source.store == "summary" else ""
    digest = content_sha256(title=title, summary=kept_summary, url=url, published=published)
    row = session.get(NewsItemRecord, item_id)
    values = {
        "url": url or None,
        "publisher": publisher[:200],
        "title": title[:400],
        "summary": kept_summary,
        "language": (language or source.language or "en")[:8],
        "published_at_utc": _aware(published),
        "content_sha256": digest,
        "licence_note": f"{source.licence}; {source.attribution}"[:300],
        "event_types": list(tags.event_types),
        "entities": [entity.as_dict() for entity in tags.entities],
        "hubs": list(tags.hubs),
        "countries": list(tags.countries),
        "capacity_change": bool(tags.capacity_change),
        "linked_event_key": linked_event_key,
    }
    if row is None:
        row = NewsItemRecord(
            item_id=item_id,
            source_id=source.source_id,
            source_ref=source_ref[:400],
            retrieved_at_utc=retrieved,
            revision=1,
            first_seen_at_utc=now,
            updated_at_utc=now,
            **values,
        )
        session.add(row)
        state = "new"
    elif row.content_sha256 == digest and row.linked_event_key == linked_event_key and list(
        row.event_types or []
    ) == list(tags.event_types):
        return item_id, "unchanged"
    else:
        for key, value in values.items():
            setattr(row, key, value)
        row.revision = int(row.revision or 1) + 1
        row.retrieved_at_utc = retrieved
        row.updated_at_utc = now
        state = "changed"
    session.flush()
    _publish(session, row, source, now=now)
    return item_id, state


def _publish(session, row, source: NewsSource, *, now: datetime) -> None:
    from eurogas_nexus.application.market_events import publish
    from eurogas_nexus.domain.market_events.model import MarketEvent

    feed_link = row.linked_event_key if source.kind != "remit_held" else None
    published = _aware(row.published_at_utc)
    publish(
        session,
        MarketEvent(
            source_id=EVENT_SOURCE,
            event_type="news.published",
            subject_key=f"news:{row.item_id}",
            ingested_at_utc=now,
            market_time_utc=published,
            published_at_utc=published if published and published <= now else None,
            payload={
                "item_id": row.item_id,
                "source_id": row.source_id,
                "revision": int(row.revision),
                "content_sha256": row.content_sha256,
                "event_types": list(row.event_types or []),
                "hubs": list(row.hubs or []),
                "capacity_change": bool(row.capacity_change),
                "linked_event_key": row.linked_event_key,
            },
            dependency_keys=(feed_link,) if feed_link else (),
            input_class="outages" if feed_link else None,
            identity=row.item_id,
            correlation_id=row.item_id,
        ),
    )


# ------------------------------------------------------------------------------- REMIT


def _figure(value: Any) -> str | None:
    if value is None:
        return None
    number = float(value)
    return f"{number:,.0f}" if number >= 100 else f"{number:,.1f}".rstrip("0").rstrip(".")


def _day(moment: datetime | None) -> str:
    return _aware(moment).strftime("%d %b %Y %H:%M UTC") if moment else "open-ended"


def remit_text(row) -> tuple[str, str]:
    """``(title, summary)`` of one REMIT message: its own fields, figures as it states them."""

    kind = str(row.unavailability_type or "").lower() or "unstated"
    title = (
        f"{row.asset_name}: {kind} unavailability from {_day(row.event_start_utc)} "
        f"to {_day(row.event_stop_utc)}"
    )
    parts = [f"Status {str(row.event_status).lower()} (version {row.version})."]
    unavailable = _figure(row.unavailable_capacity)
    technical = _figure(row.technical_capacity)
    if unavailable is not None:
        parts.append(
            f"Unavailable {unavailable} {row.unit}"
            + (f" of technical {technical} {row.unit}" if technical is not None else "")
            + "."
        )
    if row.unavailable_gwh_d is not None:
        parts.append(f"Daily figure {_figure(row.unavailable_gwh_d)} GWh/d.")
    if row.balancing_zone:
        parts.append(f"Balancing zone {row.balancing_zone}.")
    if row.reason:
        parts.append(f"Reason: {plain_text(row.reason, 240)}.")
    if row.remarks:
        parts.append(plain_text(row.remarks, 400))
    return title, " ".join(parts)


def _url_in(reference: str | None) -> str | None:
    match = re.search(r"https://[^\s\]\)\"']+", reference or "")
    return match.group(0) if match else None


def sync_remit_items(
    session, *, now: datetime, window: timedelta = REMIT_WINDOW,
    vessels: Iterable[str] | None = None,
) -> PollOutcome:
    """Make or refresh an item for each REMIT message ingested within ``window``."""

    source = news_source("remit-umm")
    vessel_names = list(vessels) if vessels is not None else held_vessels(session)
    outcome = PollOutcome(source.source_id, "ok")
    for row in _latest_remit(session, since=now - window):
        title, summary = remit_text(row)
        hub = zone_hub(row.balancing_zone)
        tags = tag_text(f"{title} {summary} {row.market_participant}", vessels=vessel_names,
                        remit=True, zone_hubs=(hub,) if hub else ())
        item_id, state = upsert_item(
            session,
            source=source,
            source_ref=str(row.message_id),
            url=_url_in(row.source_reference),
            publisher=str(row.market_participant or "REMIT market participant"),
            title=title,
            summary=summary,
            language="en",
            published=_aware(row.published_at_utc),
            retrieved=_aware(row.ingested_at_utc) or now,
            tags=tags,
            linked_event_key=f"outage:{row.message_id}",
            now=now,
        )
        outcome.seen += 1
        if state != "unchanged":
            setattr(outcome, state, getattr(outcome, state) + 1)
            outcome.item_ids.append(item_id)
    _record_poll(session, source.source_id, outcome, now=now, feed_url=None)
    return outcome


# -------------------------------------------------------------------------------- feeds


def http_fetch(url: str, headers: dict[str, str]) -> FetchResult:
    """One HTTPS GET with this product's User-Agent (the real fetcher; tests pass their own)."""

    import urllib.error
    import urllib.request

    if urlsplit(url).scheme != "https":
        return FetchResult(0, b"", {"error": "https only"})
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **headers})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310 - https only
            body = response.read(2_000_001)
            return FetchResult(response.status, body, {k.lower(): v for k, v in
                                                       response.headers.items()})
    except urllib.error.HTTPError as exc:
        return FetchResult(exc.code, b"", {k.lower(): v for k, v in (exc.headers or {}).items()})
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return FetchResult(0, b"", {"error": type(exc).__name__})


def robots_allows(fetch: Fetcher, url: str) -> tuple[bool, str]:
    """Whether the host's ``robots.txt`` lets this product read ``url``.

    No file (4xx) allows; a file that cannot be read (5xx or no answer) does not, so a poll
    never goes ahead on a host whose rules were not read.
    """

    parts = urlsplit(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    result = fetch(robots_url, {})
    if 400 <= result.status < 500:
        return True, "no robots.txt"
    if result.status != 200:
        return False, f"robots.txt not readable (status {result.status})"
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(result.body.decode("utf-8", "replace").splitlines())
    if parser.can_fetch(USER_AGENT, url):
        return True, "robots.txt allows"
    return False, "robots.txt disallows the feed"


def _record_poll(session, source_id: str, outcome: PollOutcome, *, now: datetime,
                 feed_url: str | None, etag: str | None = None,
                 last_modified: str | None = None) -> None:
    from eurogas_nexus.db.models import NewsSourcePollRecord

    row = session.get(NewsSourcePollRecord, source_id)
    if row is None:
        row = NewsSourcePollRecord(source_id=source_id, last_status=outcome.status)
        session.add(row)
    row.last_polled_at_utc = now
    row.last_status = outcome.status
    row.last_detail = outcome.detail[:500]
    row.feed_url = feed_url
    row.items_seen = outcome.seen
    row.items_new = outcome.new
    row.items_changed = outcome.changed
    if outcome.status in {"ok", "not_modified"}:
        row.last_success_at_utc = now
        if etag is not None:
            row.etag = etag[:200]
        if last_modified is not None:
            row.last_modified = last_modified[:64]
    session.flush()


def poll_source(
    session,
    source: NewsSource,
    *,
    fetch: Fetcher,
    now: datetime,
    feed_url: str | None = None,
    force: bool = False,
    vessels: Iterable[str] | None = None,
) -> PollOutcome:
    """Poll one feed source (see the module text). ``feed_url`` overrides the registry's
    address only on the publisher's own host."""

    from eurogas_nexus.db.models import NewsSourcePollRecord

    if source.kind == "remit_held":
        return sync_remit_items(session, now=now, vessels=vessels)
    refusal = poll_refusal(source, feed_url=feed_url)
    if refusal:
        outcome = PollOutcome(source.source_id, "refused", refusal)
        _record_poll(session, source.source_id, outcome, now=now, feed_url=feed_url)
        return outcome
    address = feed_url or source.feed_url or ""
    held = session.get(NewsSourcePollRecord, source.source_id)
    last = _aware(held.last_polled_at_utc) if held is not None else None
    if not force and last is not None and now - last < timedelta(minutes=source.poll_minutes):
        return PollOutcome(source.source_id, "skipped", "within the source's poll interval")
    allowed, why = robots_allows(fetch, address)
    if not allowed:
        outcome = PollOutcome(source.source_id, "robots_disallowed", why)
        _record_poll(session, source.source_id, outcome, now=now, feed_url=address)
        return outcome
    headers: dict[str, str] = {}
    if held is not None and held.feed_url == address:
        if held.etag:
            headers["If-None-Match"] = held.etag
        if held.last_modified:
            headers["If-Modified-Since"] = held.last_modified
    result = fetch(address, headers)
    if result.status == 304:
        outcome = PollOutcome(source.source_id, "not_modified", "feed unchanged since last poll")
        _record_poll(session, source.source_id, outcome, now=now, feed_url=address)
        return outcome
    if result.status != 200:
        outcome = PollOutcome(source.source_id, "failed", f"status {result.status} "
                              f"{result.headers.get('error', '')}".strip())
        _record_poll(session, source.source_id, outcome, now=now, feed_url=address)
        return outcome
    try:
        language, entries = parse_feed(result.body)
    except FeedError as exc:
        outcome = PollOutcome(source.source_id, "failed", str(exc))
        _record_poll(session, source.source_id, outcome, now=now, feed_url=address)
        return outcome
    vessel_names = list(vessels) if vessels is not None else held_vessels(session)
    outcome = PollOutcome(source.source_id, "ok", why)
    for entry in entries:
        ref = entry.guid or entry.url
        if not ref or not entry.title:
            continue
        tags = tag_text(f"{entry.title} {entry.summary}", vessels=vessel_names)
        link, _ = outage_link(session, tags, at=now)
        item_id, state = upsert_item(
            session,
            source=source,
            source_ref=ref,
            url=entry.url or None,
            publisher=source.publisher,
            title=entry.title,
            summary=entry.summary,
            language=(entry.language or language or source.language).split("-")[0],
            published=entry.published_at_utc,
            retrieved=now,
            tags=tags,
            linked_event_key=link,
            now=now,
        )
        outcome.seen += 1
        if state != "unchanged":
            setattr(outcome, state, getattr(outcome, state) + 1)
            outcome.item_ids.append(item_id)
    _record_poll(session, source.source_id, outcome, now=now, feed_url=address,
                 etag=result.headers.get("etag"),
                 last_modified=result.headers.get("last-modified"))
    return outcome


def poll_all(session, *, fetch: Fetcher, now: datetime, force: bool = False
             ) -> list[PollOutcome]:
    """REMIT items, then every registered feed source that may be polled."""

    from eurogas_nexus.domain.news.sources import NEWS_SOURCES

    vessels = held_vessels(session)
    out = [sync_remit_items(session, now=now, vessels=vessels)]
    for source in NEWS_SOURCES:
        if source.kind == "remit_held":
            continue
        out.append(poll_source(session, source, fetch=fetch, now=now, force=force,
                               vessels=vessels))
    return out


__all__ = [
    "EVENT_SOURCE",
    "USER_AGENT",
    "FetchResult",
    "Fetcher",
    "PollOutcome",
    "content_sha256",
    "held_vessels",
    "http_fetch",
    "item_id_for",
    "outage_link",
    "poll_all",
    "poll_source",
    "remit_text",
    "robots_allows",
    "sync_remit_items",
    "upsert_item",
]
