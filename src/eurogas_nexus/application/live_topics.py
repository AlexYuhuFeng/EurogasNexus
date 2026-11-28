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
  ``trades`` and ``book`` together); ``deals`` from captured deals (a new deal, a correction or
  a cancellation, a physical or financial choice by hand, a day's close), by book: a page that
  shows positions answers it at once, not at the pace of its price re-reads (small-desk plan
  section 5); ``alerts`` from monitoring alerts, by the alert's own
  visibility rule; ``nominations`` from recorded nomination steps, by book; ``tariffs`` also
  from TSO tariff publications (public information); ``outages``, ``flows``, ``cargoes``,
  ``slots``, ``opportunities`` from the map's fast inputs, under the map's own rules
  (``streaming._fetch_map_changes``).

Jobs are not a notice topic: the stream sends each of the caller's own jobs as a ``jobs`` event
whenever its status, progress or step changes (see :func:`job_events`).

Shared reads (:class:`Reads`): an API process polls once per interval for all of its open streams
(``api.stream_hub``). Each source is read once, from the oldest cursor any stream holds, and each
stream takes the rows after its own cursor and applies its own caller's rule in memory. The
caller's books are read once per poll per distinct caller. Every function here also accepts a
plain session (one stream, a test), and then reads exactly what that one caller asks for.

实时流的主题变更：每个主题只告知「何时变化」，不携带数据行；调用方不可见的数据不会产生通知。
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

#: Topics a page may subscribe to, in a stable order.
NOTICE_TOPICS = (
    "prices",
    "trades",
    "deals",
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


# --- Shared reads -----------------------------------------------------------------------------


@dataclass(frozen=True)
class NewestSource:
    """A change source read newest first: the columns a notice needs and the change stamp."""

    columns: Callable[[Any], Any]  # session -> query of the columns (``stamp`` among them)
    stamp: str


def _newest_sources() -> dict[str, NewestSource]:
    from eurogas_nexus.application.identity_resolution import identity_clause
    from eurogas_nexus.db.models import (
        CapturedDealRecord,
        DealDayCloseRecord,
        DealPositionKindRecord,
        FlowObservationRecord,
        GasDayNominationEventRecord,
        LngCargoRecord,
        MarketObservationRecord,
        MarketQuoteRecord,
        MonitoringAlertRecord,
        OpportunityRecord,
        RegasSlotRecord,
        RemitUmmRecord,
        ScreenOrderObservationRecord,
        TariffPublicationRecord,
    )

    q, o = MarketQuoteRecord, MarketObservationRecord
    t, n = ScreenOrderObservationRecord, GasDayNominationEventRecord
    f, r, c, sl, op = (
        FlowObservationRecord,
        RemitUmmRecord,
        LngCargoRecord,
        RegasSlotRecord,
        OpportunityRecord,
    )
    return {
        "quotes": NewestSource(
            lambda s: s.query(q.observed_at_utc, q.source_system), "observed_at_utc"
        ),
        "observations": NewestSource(
            lambda s: s.query(o.observed_at_utc, o.source_system), "observed_at_utc"
        ),
        "screen_orders": NewestSource(
            lambda s: s.query(t.observed_at_utc, t.book_id), "observed_at_utc"
        ),
        "nominations": NewestSource(
            lambda s: s.query(n.recorded_at_utc, n.book_id), "recorded_at_utc"
        ),
        # Captured deals: every version (a correction or a cancellation is a new one), the
        # physical or financial choices made by hand, and the day's closes.
        "captured_deals": NewestSource(
            lambda s: s.query(CapturedDealRecord.recorded_at_utc, CapturedDealRecord.book_id),
            "recorded_at_utc",
        ),
        "deal_kinds": NewestSource(
            lambda s: s.query(DealPositionKindRecord.entered_at_utc,
                              DealPositionKindRecord.book_id),
            "entered_at_utc",
        ),
        "deal_closes": NewestSource(
            lambda s: s.query(DealDayCloseRecord.closed_at_utc, DealDayCloseRecord.book_id),
            "closed_at_utc",
        ),
        "tariffs": NewestSource(
            lambda s: s.query(TariffPublicationRecord.updated_at_utc), "updated_at_utc"
        ),
        "alerts": NewestSource(lambda s: s.query(MonitoringAlertRecord), "updated_at_utc"),
        # The map's fast inputs (``streaming._fetch_map_changes``).
        "map_flows": NewestSource(
            lambda s: s.query(f.observed_at_utc, f.source_system).filter(identity_clause(s, f)),
            "observed_at_utc",
        ),
        "map_outages": NewestSource(
            lambda s: s.query(r.ingested_at_utc, r.source_system), "ingested_at_utc"
        ),
        "map_cargoes": NewestSource(
            lambda s: s.query(c.updated_at_utc, c.book_id, c.source_system), "updated_at_utc"
        ),
        "map_slots": NewestSource(
            lambda s: s.query(sl.updated_at_utc, sl.book_id), "updated_at_utc"
        ),
        "map_opportunities": NewestSource(
            lambda s: s.query(
                op.last_changed_utc,
                op.opportunity_id,
                op.lane,
                op.book_ids,
                op.source_families,
                op.state,
            ),
            "last_changed_utc",
        ),
    }


_SOURCES: dict[str, NewestSource] | None = None


def newest_source(key: str) -> NewestSource:
    global _SOURCES
    if _SOURCES is None:
        _SOURCES = _newest_sources()
    return _SOURCES[key]


def _not_after(left, right) -> bool:
    """``left <= right`` where ``None`` is the beginning of time."""

    if left is None:
        return True
    if right is None:
        return False
    return left <= right


class Reads:
    """What one poll reads from the store, shared by every stream that poll serves.

    A stream first says what it needs (:meth:`want`, :meth:`want_outbox`, :meth:`want_jobs`);
    each source is then read once, from the oldest cursor wanted, and every stream takes the
    rows after its own cursor. Anything a caller may or may not see is decided per caller, in
    memory, after the read; what needs the store for that (the caller's books) is read once
    per poll per distinct caller (:meth:`books`, :meth:`memo`). A read that fails fails for
    every stream of the poll without being retried within it.
    """

    def __init__(self, session, now: datetime | None = None) -> None:
        self.session = session
        self.now = now or datetime.now(UTC)
        self._floors: dict[Hashable, Any] = {}
        self._memo: dict[Hashable, tuple[bool, Any]] = {}
        self._outbox_kinds: set[str] = set()
        self._job_owners: set[str] = set()
        self._revocations: set[tuple] = set()
        #: Reads that went to the store (for the hub's metrics and the tests).
        self.queries = 0
        #: The first error a stream recovered from in this poll (``sys.exc_info()``): the
        #: streams answer it with a warning event, the hub logs and counts it once.
        self.failure: tuple | None = None

    # What the streams need ---------------------------------------------------------------

    def want(self, key: Hashable, since) -> None:
        """A stream will read ``key`` after ``since`` (``None``: from the beginning)."""

        if key in self._floors:
            held = self._floors[key]
            self._floors[key] = held if _not_after(held, since) else since
        else:
            self._floors[key] = since

    def want_outbox(self, after: str | None, kinds) -> None:
        from eurogas_nexus.application.change_feed import ChangeFeedError, parse_cursor

        if after is None:
            return
        try:
            position = parse_cursor(after)
        except ChangeFeedError:
            return
        if isinstance(position, str):
            return
        self._outbox_kinds.update(kinds)
        self.want("outbox", position)

    def want_revocation(self, session_hash, principal_id, opened: datetime) -> None:
        """A stream will ask whether a revocation note ends it (one read for all streams)."""

        self._revocations.add((session_hash, principal_id, opened))

    def revoked(self, session_hash, principal_id, opened: datetime) -> bool | None:
        """Whether a revocation note ends the stream (None: the cache cannot say)."""

        def read():
            from eurogas_nexus.security.session_revocation import revoked_streams

            asked = sorted(
                self._revocations | {(session_hash, principal_id, opened)},
                key=lambda item: (item[0] or "", item[1] or "", item[2]),
            )
            return dict(zip(asked, revoked_streams(asked), strict=True))

        found = self.memo("revocations", read)
        held = found.get((session_hash, principal_id, opened))
        if held is None and (session_hash, principal_id, opened) not in found:
            from eurogas_nexus.security.session_revocation import revoked_streams

            return revoked_streams([(session_hash, principal_id, opened)])[0]
        return held

    def want_jobs(self, owner: str | None, since: datetime) -> None:
        if owner:
            self._job_owners.add(owner)
            self.want("jobs", as_utc(since))

    def recover(self) -> None:
        """After a failed read: end the session's failed transaction so later reads may run.

        Called from the ``except`` block of the failed read; the error is kept for the hub."""

        if self.failure is None:
            info = sys.exc_info()
            if info[0] is not None:
                self.failure = info
        try:
            self.session.rollback()
        except Exception:  # noqa: BLE001 - the store is gone; the next poll tries again
            return

    # Memo ------------------------------------------------------------------------------------

    def memo(self, key: Hashable, factory: Callable[[], Any]) -> Any:
        """``factory()`` once per poll; a failure is remembered and raised again."""

        if key not in self._memo:
            try:
                self._memo[key] = (True, factory())
            except Exception as exc:
                self._memo[key] = (False, exc)
        ok, value = self._memo[key]
        if not ok:
            raise value
        return value

    def _start(self, key: Hashable, since):
        floor = self._floors.get(key, since)
        return floor if _not_after(floor, since) else since

    # Sources ---------------------------------------------------------------------------------

    def newest(self, key: str, since: Cursor) -> list:
        """Rows of ``key`` changed after ``since``, newest first, at most :data:`NOTICE_PAGE`.

        Read once from the oldest cursor wanted: the newest rows after an older cursor include
        every one of the newest rows after a later cursor, so the slice is exact.
        """

        source = newest_source(key)
        start = self._start(key, since)

        def read():
            self.queries += 1
            query = source.columns(self.session)
            column = getattr(query.column_descriptions[0]["entity"], source.stamp)
            if start is not None:
                query = query.filter(column > start)
            return query.order_by(column.desc()).limit(NOTICE_PAGE).all()

        rows = self.memo(("newest", key, start), read)
        if start == since or since is None:
            return rows
        bound = as_utc(since)
        return [row for row in rows if as_utc(getattr(row, source.stamp)) > bound]

    def ascending(
        self,
        key: Hashable,
        fetch: Callable[[Any, Any], list],
        cursor,
        cursor_of: Callable[[Any], Any],
        page: int,
    ) -> list:
        """Rows ``fetch(session, cursor)`` returns (oldest first, at most ``page``), shared.

        A page read from an older cursor serves a later one when it is not full or reaches
        past the later cursor; otherwise the later cursor is read on its own.
        """

        start = self._start(key, cursor)

        def read(at):
            def run():
                self.queries += 1
                return fetch(self.session, at)

            return run

        rows = self.memo(("ascending", key, start), read(start))
        if start == cursor:
            return rows
        marks = [cursor_of(row) for row in rows]
        if any(mark is None for mark in marks) or (
            len(rows) >= page and not _not_after(cursor, marks[-1])
        ):
            return self.memo(("ascending", key, cursor), read(cursor))
        return [
            row
            for row, mark in zip(rows, marks, strict=True)
            if cursor is None or mark > cursor
        ]

    def outbox_latest(self) -> str:
        """The outbox position a new connection starts from (its newest event)."""

        def read():
            from eurogas_nexus.application.change_feed import LATEST, read_changes

            self.queries += 1
            return read_changes(self.session, None, after=LATEST).next_cursor

        return self.memo("outbox-latest", read)

    def outbox_page(self, after, kinds):
        """The outbox's events after ``after`` (every caller's: entitled per caller later)."""

        from eurogas_nexus.application.change_feed import read_changes

        start = self._start("outbox", after)
        every = tuple(sorted(self._outbox_kinds | set(kinds))) if start != after else tuple(
            sorted(kinds)
        )

        def read():
            self.queries += 1
            return read_changes(self.session, None, after=start, kinds=every, limit=OUTBOX_PAGE)

        return self.memo(("outbox", start, every), read)

    def jobs(self, owner: str, since: datetime) -> list:
        """The owner's jobs that still move or started or finished after ``since``."""

        since = as_utc(since)
        start = self._start("jobs", since)
        owners = tuple(sorted(self._job_owners | {owner})) if start != since else (owner,)

        def read():
            from sqlalchemy import func, or_, select

            from eurogas_nexus.db.models import JobRecord

            self.queries += 1
            ranked = (
                select(
                    JobRecord.job_id,
                    func.row_number()
                    .over(
                        partition_by=JobRecord.owner_principal_id,
                        order_by=JobRecord.created_at_utc.desc(),
                    )
                    .label("rank"),
                )
                .where(JobRecord.owner_principal_id.in_(owners))
                .where(
                    or_(
                        JobRecord.status.in_(ACTIVE_JOB_STATES),
                        JobRecord.finished_at_utc > start,
                        JobRecord.created_at_utc > start,
                    )
                )
                .subquery()
            )
            return (
                self.session.query(JobRecord)
                .join(ranked, ranked.c.job_id == JobRecord.job_id)
                .filter(ranked.c.rank <= JOB_PAGE)
                .order_by(JobRecord.created_at_utc.desc())
                .all()
            )

        rows = self.memo(("jobs", start, owners), read)

        def moved(row) -> bool:
            if row.status in ACTIVE_JOB_STATES:
                return True
            return any(
                stamp is not None and as_utc(stamp) > since
                for stamp in (row.finished_at_utc, row.created_at_utc)
            )

        return [row for row in rows if row.owner_principal_id == owner and moved(row)][:JOB_PAGE]

    # The caller ------------------------------------------------------------------------------

    def books(self, principal) -> set | None:
        """The caller's visible books (``None``: every book), once per poll per caller."""

        if principal is None:
            return None

        def read():
            from eurogas_nexus.security.portfolio_scope import (
                scope_for_principal,
                visible_book_ids,
            )

            scope = scope_for_principal(principal.data_scopes)
            if scope is not None and not scope.all_books:
                self.queries += 1
            return visible_book_ids(self.session, scope)

        return self.memo(("books", principal_key(principal)), read)


def principal_key(principal) -> Hashable:
    """A caller as a memo key: the same identity with the same scopes is one caller."""

    try:
        hash(principal)
    except TypeError:
        return ("object", id(principal))
    return principal


def as_reads(session_or_reads) -> Reads:
    return session_or_reads if isinstance(session_or_reads, Reads) else Reads(session_or_reads)


def parse_topics(raw: str | None) -> tuple[str, ...]:
    """The known topics in ``raw`` (comma-separated), in the stable order; ``jobs`` included."""

    asked = {part.strip().lower() for part in (raw or "").split(",") if part.strip()}
    known = [topic for topic in NOTICE_TOPICS if topic in asked]
    if "jobs" in asked:
        known.append("jobs")
    return tuple(known)


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

    def __init__(self, reads: Reads, principal) -> None:
        self.reads = reads
        self.principal = principal

    def ids(self) -> set | None:
        return self.reads.books(self.principal)

    def sees(self, book_id) -> bool:
        books = self.ids()
        if books is None:
            return True
        # A row held in no book is head office's: only an unrestricted caller counts it.
        return book_id is not None and book_id in books


def _prices(reads: Reads, since: Cursor, principal, books: _Books) -> list[tuple[datetime, bool]]:
    rows = [*reads.newest("quotes", since), *reads.newest("observations", since)]
    return _entitled_flags(principal, [(row.observed_at_utc, row.source_system) for row in rows])


def _trades(reads: Reads, since: Cursor, principal, books: _Books) -> list[tuple[datetime, bool]]:
    return [
        (row.observed_at_utc, books.sees(row.book_id))
        for row in reads.newest("screen_orders", since)
    ]


#: The newest captured-deal change this process has told its warm views about.
_DEALS_NOTED: list[datetime] = []


def _note_deals(changed: list[datetime]) -> None:
    """A deal stored by another process (the watched folder): this process's position views
    stop answering from before it (``warm_views.note_deals``), before the notice goes out."""

    if not changed:
        return
    newest = max(as_utc(at) for at in changed)
    if _DEALS_NOTED and newest <= _DEALS_NOTED[0]:
        return
    _DEALS_NOTED[:] = [newest]
    from eurogas_nexus.application.warm_views import views

    views().note_deals()


def _deals(reads: Reads, since: Cursor, principal, books: _Books) -> list[tuple[datetime, bool]]:
    rows = [
        (getattr(row, stamp), row.book_id)
        for key, stamp in (("captured_deals", "recorded_at_utc"),
                           ("deal_kinds", "entered_at_utc"),
                           ("deal_closes", "closed_at_utc"))
        for row in reads.newest(key, since)
    ]
    _note_deals([at for at, _book in rows])
    return [(at, books.sees(book)) for at, book in rows]


def _nominations(
    reads: Reads, since: Cursor, principal, books: _Books
) -> list[tuple[datetime, bool]]:
    return [
        (row.recorded_at_utc, books.sees(row.book_id))
        for row in reads.newest("nominations", since)
    ]


def _tariffs(reads: Reads, since: Cursor, principal, books: _Books) -> list[tuple[datetime, bool]]:
    return [(row.updated_at_utc, True) for row in reads.newest("tariffs", since)]


def _alerts(reads: Reads, since: Cursor, principal, books: _Books) -> list[tuple[datetime, bool]]:
    records = reads.newest("alerts", since)
    if not records:
        return []
    if principal is None:
        return [(row.updated_at_utc, True) for row in records]
    visible = alert_predicate(reads, principal)
    out = []
    for row in records:
        payload = {column.name: getattr(row, column.name) for column in row.__table__.columns}
        out.append((row.updated_at_utc, bool(visible(payload))))
    return out


def alert_predicate(reads: Reads, principal) -> Callable[[Any], bool]:
    """The alert read rule for one caller (``alert_scope.alert_visibility``), once per poll."""

    def build():
        from eurogas_nexus.application.alert_scope import alert_rule

        return alert_rule(reads.books(principal), principal)

    return reads.memo(("alert-visible", principal_key(principal)), build)


TopicSource = Callable[[Reads, Cursor, Any, _Books], list[tuple[datetime, bool]]]
SOURCES: dict[str, TopicSource] = {
    "prices": _prices,
    "trades": _trades,
    "deals": _deals,
    "alerts": _alerts,
    "nominations": _nominations,
    "tariffs": _tariffs,
}
#: The shared sources each topic reads (what a stream asks the poll for).
TOPIC_SOURCES: dict[str, tuple[str, ...]] = {
    "prices": ("quotes", "observations"),
    "trades": ("screen_orders",),
    "deals": ("captured_deals", "deal_kinds", "deal_closes"),
    "alerts": ("alerts",),
    "nominations": ("nominations",),
    "tariffs": ("tariffs",),
}
MAP_SOURCES = ("map_flows", "map_outages", "map_cargoes", "map_slots", "map_opportunities")


def want_topics(reads: Reads, topics: tuple[str, ...], cursors: dict[str, Cursor]) -> None:
    """Tell the poll what :func:`topic_changes` will read for these topics and cursors."""

    for topic in topics:
        for key in TOPIC_SOURCES.get(topic, ()):
            reads.want(key, cursors.get(topic))
    map_topics = [topic for topic in topics if topic in MAP_TOPICS]
    if map_topics:
        since = min((cursors.get(topic) for topic in map_topics), default=None, key=_order)
        for key in MAP_SOURCES:
            reads.want(key, since)


def topic_changes(
    session,  # a session, or the poll's shared reads
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

    reads = as_reads(session)
    books = _Books(reads, principal)
    out: list[dict] = []
    for topic in topics:
        source = SOURCES.get(topic)
        if source is None:
            continue
        notice = _notice(topic, source(reads, cursors.get(topic), principal, books))
        if notice:
            out.append(notice)
    map_topics = [topic for topic in topics if topic in MAP_TOPICS]
    if map_topics and map_changes is not None:
        since = min((cursors.get(topic) for topic in map_topics), default=None, key=_order)
        cursor = None if since is None else (since, "")
        for item in map_changes(reads, cursor, principal):
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
    rows = as_reads(session).jobs(owner, since)
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

    return as_reads(session).outbox_latest()


def outbox_changes(
    session, topics: tuple[str, ...], after: str, principal=None
) -> tuple[list[dict], str]:
    """Notices from the market event outbox after ``after``, and the cursor to continue from.

    The outbox's own feed reads the events (commit order, its horizon, the caller's
    entitlement: market families by licence, desk events only to a book-wide portfolio
    reader); the events of one poll collapse to one notice per topic, at the newest ingestion
    time. Withheld events move the cursor and announce nothing.
    """

    from eurogas_nexus.application.change_feed import change_allowed, parse_cursor

    kinds = sorted(kind for kind, topic in OUTBOX_TOPICS.items() if topic in topics)
    if not kinds:
        return [], after
    position = parse_cursor(after)
    page = as_reads(session).outbox_page(position, kinds)
    wanted = set(kinds)
    newest_cursor = parse_cursor(page.next_cursor)
    changes = []
    for change in page.changes:
        if change["event_type"] not in wanted or parse_cursor(change["cursor"]) <= position:
            continue
        if change_allowed(principal, change["event_type"], change["source_id"]):
            changes.append(change)
    following = page.next_cursor if newest_cursor > position else after
    newest: dict[str, datetime] = {}
    for change in changes:
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
    return notices, following
