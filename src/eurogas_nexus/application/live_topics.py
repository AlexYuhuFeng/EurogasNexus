"""What changed, by topic, for the live stream (``GET /api/stream/live``).

A page subscribes to the topics it shows and answers a change notice with its own read (a
conditional read: a 304 when nothing it shows moved), so a notice carries a topic and a time,
never a row. A notice must still not reveal that something changed in data the caller may not
read: each topic's changed rows pass the rule its REST read applies before they count.

Where the notices come from:

* **The market event outbox** (``market_events``, read through ``application.change_feed`` with
  its cursor, its commit horizon and its entitlement): ``price.updated``, ``fx.updated`` and
  ``rate.updated`` are ``prices``; ``outage.published`` is ``outages``; ``tariff.changed`` is
  ``tariffs``; ``cargo.changed`` is ``cargoes``; ``contract.changed``, ``mark.changed``,
  ``limit.changed``, ``assumption.changed`` and ``freight.changed`` are ``book``;
  ``capacity.changed`` is ``capacity``; ``source.ingested`` is ``sources``; ``news.published``
  is ``news``.
* **Tables the outbox does not carry** (written many times a second, or the firm's own records
  that have no event type yet), each by the rule its REST read applies: ``prices`` also from
  market quotes (screens, the demo exchange feed) and market observations not yet captured;
  ``trades`` from booked trades, by book (positions and the day P&L move with ``prices``,
  ``trades`` and ``book`` together); ``alerts`` from monitoring alerts, by the alert's own
  visibility rule; ``nominations`` from recorded nomination steps, by book; ``tariffs`` also
  from TSO tariff publications (public information); ``outages``, ``flows``, ``cargoes``,
  ``slots``, ``opportunities`` from the map's fast inputs, under the map's own rules
  (``streaming._fetch_map_changes``).

Jobs are not a notice topic: the stream sends each of the caller's own jobs as a ``jobs`` event
whenever its status, progress or step changes (see :func:`job_events`).

实时流的主题变更：每个主题只告知「何时变化」，不携带数据行；调用方不可见的数据不会产生通知。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

#: Topics a page may subscribe to, in a stable order.
NOTICE_TOPICS = (
    "prices",
    "trades",
    "alerts",
    "nominations",
    "tariffs",
    "outages",
    "flows",
    "cargoes",
    "slots",
    "opportunities",
    "book",
    "capacity",
    "sources",
    "news",
)
#: The outbox's event types by topic (``domain.market_events.model.EVENT_TYPES``).
OUTBOX_TOPICS: dict[str, str] = {
    "price.updated": "prices",
    "fx.updated": "prices",
    "rate.updated": "prices",
    "outage.published": "outages",
    "tariff.changed": "tariffs",
    "cargo.changed": "cargoes",
    "contract.changed": "book",
    "mark.changed": "book",
    "limit.changed": "book",
    "assumption.changed": "book",
    "freight.changed": "book",
    "capacity.changed": "capacity",
    "source.ingested": "sources",
    "news.published": "news",
}
#: Outbox events read per poll at most; more wait for the next poll (the cursor keeps them).
OUTBOX_PAGE = 500
#: The rows looked at per topic and poll, newest first: enough to find one the caller sees.
NOTICE_PAGE = 200
#: The map's groups, read together by the map's own notice source.
MAP_TOPICS = ("outages", "flows", "cargoes", "slots", "opportunities")
#: Job states that still move.
ACTIVE_JOB_STATES = ("QUEUED", "RUNNING", "WAITING_FOR_INPUT")
#: Jobs sent per poll at most (a caller's own work: a handful).
JOB_PAGE = 50

Cursor = datetime | None


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def parse_topics(raw: str | None) -> tuple[str, ...]:
    """The known topics in ``raw`` (comma-separated), in the stable order; ``jobs`` included."""

    asked = {part.strip().lower() for part in (raw or "").split(",") if part.strip()}
    known = [topic for topic in NOTICE_TOPICS if topic in asked]
    if "jobs" in asked:
        known.append("jobs")
    return tuple(known)


def _changed(query, stamp, since: Cursor) -> list:
    if since is not None:
        query = query.filter(stamp > since)
    return query.order_by(stamp.desc()).limit(NOTICE_PAGE).all()


def _notice(topic: str, rows: list[tuple[datetime, bool]]) -> dict | None:
    """One notice for a topic from (changed_at, visible) pairs, or None when nothing changed."""

    if not rows:
        return None
    latest = max(as_utc(at) for at, _ in rows)
    visible = [as_utc(at) for at, ok in rows if ok]
    return {
        "topic": topic,
        "changed_at": max(visible) if visible else latest,
        "visible": bool(visible),
        "cursor": latest,
    }


def _entitled_flags(
    principal, rows: list[tuple[datetime, str | None]]
) -> list[tuple[datetime, bool]]:
    if principal is None:
        return [(at, True) for at, _ in rows]
    from eurogas_nexus.application.projections.market_reads import filter_entitled_rows

    dicts = [{"changed_at": at, "source_system": source} for at, source in rows]
    seen = {id(row) for row in filter_entitled_rows(principal, dicts, source_key="source_system")}
    return [(row["changed_at"], id(row) in seen) for row in dicts]


class _Books:
    """The caller's visible books, read once per poll and only when a topic needs them."""

    def __init__(self, session, principal) -> None:
        self.session = session
        self.principal = principal
        self._ids: set | None = None
        self._read = False

    def ids(self) -> set | None:
        if not self._read:
            self._read = True
            if self.principal is not None:
                from eurogas_nexus.security.portfolio_scope import (
                    scope_for_principal,
                    visible_book_ids,
                )

                self._ids = visible_book_ids(
                    self.session, scope_for_principal(self.principal.data_scopes)
                )
        return self._ids

    def sees(self, book_id) -> bool:
        books = self.ids()
        if books is None:
            return True
        # A row held in no book is head office's: only an unrestricted caller counts it.
        return book_id is not None and book_id in books


def _prices(session, since: Cursor, principal, books: _Books) -> list[tuple[datetime, bool]]:
    from eurogas_nexus.db.models import MarketObservationRecord, MarketQuoteRecord

    quotes = _changed(
        session.query(MarketQuoteRecord.observed_at_utc, MarketQuoteRecord.source_system),
        MarketQuoteRecord.observed_at_utc,
        since,
    )
    observations = _changed(
        session.query(
            MarketObservationRecord.observed_at_utc, MarketObservationRecord.source_system
        ),
        MarketObservationRecord.observed_at_utc,
        since,
    )
    return _entitled_flags(principal, [tuple(row) for row in [*quotes, *observations]])


def _trades(session, since: Cursor, principal, books: _Books) -> list[tuple[datetime, bool]]:
    from eurogas_nexus.db.models import ScreenOrderObservationRecord

    rows = _changed(
        session.query(
            ScreenOrderObservationRecord.observed_at_utc, ScreenOrderObservationRecord.book_id
        ),
        ScreenOrderObservationRecord.observed_at_utc,
        since,
    )
    return [(at, books.sees(book)) for at, book in rows]


def _nominations(session, since: Cursor, principal, books: _Books) -> list[tuple[datetime, bool]]:
    from eurogas_nexus.db.models import GasDayNominationEventRecord

    rows = _changed(
        session.query(
            GasDayNominationEventRecord.recorded_at_utc, GasDayNominationEventRecord.book_id
        ),
        GasDayNominationEventRecord.recorded_at_utc,
        since,
    )
    return [(at, books.sees(book)) for at, book in rows]


def _tariffs(session, since: Cursor, principal, books: _Books) -> list[tuple[datetime, bool]]:
    from eurogas_nexus.db.models import TariffPublicationRecord

    rows = _changed(
        session.query(TariffPublicationRecord.updated_at_utc),
        TariffPublicationRecord.updated_at_utc,
        since,
    )
    return [(at, True) for (at,) in rows]


def _alerts(session, since: Cursor, principal, books: _Books) -> list[tuple[datetime, bool]]:
    from eurogas_nexus.db.models import MonitoringAlertRecord

    query = session.query(MonitoringAlertRecord)
    if since is not None:
        query = query.filter(MonitoringAlertRecord.updated_at_utc > since)
    records = query.order_by(MonitoringAlertRecord.updated_at_utc.desc()).limit(NOTICE_PAGE).all()
    if not records:
        return []
    if principal is None:
        return [(row.updated_at_utc, True) for row in records]
    from eurogas_nexus.application.alert_scope import alert_visibility
    from eurogas_nexus.security.portfolio_scope import scope_for_principal

    visible = alert_visibility(
        session, scope=scope_for_principal(principal.data_scopes), principal=principal
    )
    out = []
    for row in records:
        payload = {column.name: getattr(row, column.name) for column in row.__table__.columns}
        out.append((row.updated_at_utc, bool(visible(payload))))
    return out


TopicSource = Callable[[Any, Cursor, Any, _Books], list[tuple[datetime, bool]]]
SOURCES: dict[str, TopicSource] = {
    "prices": _prices,
    "trades": _trades,
    "alerts": _alerts,
    "nominations": _nominations,
    "tariffs": _tariffs,
}


def topic_changes(
    session,
    topics: tuple[str, ...],
    cursors: dict[str, Cursor],
    principal=None,
    map_changes: Callable[..., list[dict]] | None = None,
) -> list[dict]:
    """One notice per subscribed topic that changed after its cursor.

    Each notice is ``{"topic", "changed_at", "visible", "cursor"}``: every one moves the
    topic's cursor; only the visible ones are announced. Without a principal (an internal
    caller) every change counts. ``map_changes`` is the map's own notice source
    (``streaming._fetch_map_changes``: session, cursor, principal), passed in by the stream.
    """

    books = _Books(session, principal)
    out: list[dict] = []
    for topic in topics:
        source = SOURCES.get(topic)
        if source is None:
            continue
        notice = _notice(topic, source(session, cursors.get(topic), principal, books))
        if notice:
            out.append(notice)
    map_topics = [topic for topic in topics if topic in MAP_TOPICS]
    if map_topics and map_changes is not None:
        since = min((cursors.get(topic) for topic in map_topics), default=None, key=_order)
        cursor = None if since is None else (since, "")
        for item in map_changes(session, cursor, principal):
            topic = item["group"]
            if topic not in map_topics:
                continue
            mine = cursors.get(topic)
            if mine is not None and as_utc(item["cursor"]) <= mine:
                continue
            out.append(
                {
                    "topic": topic,
                    "changed_at": item["changed_at"],
                    "visible": item["visible"],
                    "cursor": item["cursor"],
                }
            )
    return out


def _order(value: Cursor) -> datetime:
    return datetime.min.replace(tzinfo=UTC) if value is None else value


def job_payload(row) -> dict:
    """The ``jobs`` event: what a progress line needs, no inputs or outputs.

    ``step`` is the current step's label when the job records one (``step_label``), else None.
    """

    progress = float(row.progress or 0.0)
    return {
        "job_id": row.job_id,
        "kind": row.kind,
        "status": row.status,
        "progress": max(0.0, min(1.0, progress)),
        "step": getattr(row, "step_label", None),
        "error_code": row.error_code or None,
        "created_at": row.created_at_utc,
        "started_at": row.started_at_utc,
        "finished_at": row.finished_at_utc,
    }


def job_events(session, principal, since: datetime, seen: dict[str, tuple]) -> list[dict]:
    """The caller's own jobs whose status, progress or step changed since the last poll.

    Jobs belong to a named identity (``owner_principal_id``), as the jobs REST read rules; a
    caller with none (the static deployment token) gets none. ``seen`` is the connection's
    memory of what it already sent; it is updated in place. The first poll sends every job
    still moving, so a page opened mid-run shows it at once.
    """

    owner = getattr(principal, "principal_id", None)
    if not owner or getattr(principal, "auth_method", None) == "legacy_public_token":
        return []
    from sqlalchemy import or_

    from eurogas_nexus.db.models import JobRecord

    rows = (
        session.query(JobRecord)
        .filter(JobRecord.owner_principal_id == owner)
        .filter(
            or_(
                JobRecord.status.in_(ACTIVE_JOB_STATES),
                JobRecord.finished_at_utc > since,
                JobRecord.created_at_utc > since,
            )
        )
        .order_by(JobRecord.created_at_utc.desc())
        .limit(JOB_PAGE)
        .all()
    )
    out = []
    for row in rows:
        payload = job_payload(row)
        state = (payload["status"], round(payload["progress"], 4), payload["step"])
        if seen.get(row.job_id) == state:
            continue
        seen[row.job_id] = state
        out.append(payload)
    return out


def outbox_start(session):
    """The outbox position a new connection starts from: its newest event (only news after)."""

    from eurogas_nexus.application.change_feed import LATEST, read_changes

    return read_changes(session, None, after=LATEST).next_cursor


def outbox_changes(
    session, topics: tuple[str, ...], after: str, principal=None
) -> tuple[list[dict], str]:
    """Notices from the market event outbox after ``after``, and the cursor to continue from.

    The outbox's own feed reads the events (commit order, its horizon, the caller's
    entitlement: market families by licence, desk events only to a book-wide portfolio
    reader); the events of one poll collapse to one notice per topic, at the newest ingestion
    time. Withheld events move the cursor and announce nothing.
    """

    from eurogas_nexus.application.change_feed import parse_cursor, read_changes

    kinds = sorted(kind for kind, topic in OUTBOX_TOPICS.items() if topic in topics)
    if not kinds:
        return [], after
    page = read_changes(
        session, principal, after=parse_cursor(after), kinds=kinds, limit=OUTBOX_PAGE
    )
    newest: dict[str, datetime] = {}
    for change in page.changes:
        topic = OUTBOX_TOPICS.get(change["event_type"])
        stamp = change.get("ingested_at_utc")
        if topic is None or not stamp:
            continue
        at = as_utc(datetime.fromisoformat(stamp))
        if topic not in newest or at > newest[topic]:
            newest[topic] = at
    notices = [
        {"topic": topic, "changed_at": at, "visible": True, "cursor": None}
        for topic, at in newest.items()
    ]
    return notices, page.next_cursor
