"""Which books a person may see: head office everything, a regional office only its own.

Book isolation is on by default (security review H1). Every read of contracts, trades, books,
credit lines, mandates, decision cases and the other book-bearing tables is restricted to the
books the caller's data scopes name:

- ``BOOKS:*``                    every book, and positions not yet in a book (head office)
- ``BOOKS:ENTITY:<legal entity>`` books of that legal entity (for example EGN-UK)
- ``BOOKS:REGION:<region>``       books of that region (europe, north_america, asia)
- ``BOOKS:BOOK:<book id>``        one book

``*`` (service accounts) sees everything. A person with no ``BOOKS:`` scope sees no
positions. Scopes come from the administrator or from SSO groups through
``EUROGAS_NEXUS_OIDC_GROUPS_SCOPE_MAP``, so a regional head's access follows the directory.

The scope is set once per request by the identity dependency. It is enforced in one place,
the ORM layer (``eurogas_nexus.db.book_scope``): every ORM read and write in a request passes
through a session event that adds the scope's criteria to each book-bearing table, so a new
route, repository or AI path cannot forget it. A request starts with a deny-all scope until
its caller is identified, so a path that skips identification sees no rows.
:func:`restrict` and :func:`visible_book_ids` remain for callers that need the book list.

Outside a request (workers, the scheduler, command-line tools) the process acts as the
system and is not narrowed; their results are filtered when a person reads them.

Isolation can be switched off only with ``EUROGAS_NEXUS_PORTFOLIO_ISOLATION=false``; in a
trial or release environment the application then refuses to start unless the deployment
also declares ``EUROGAS_NEXUS_SINGLE_BOOK_FIRM=true`` (one office, one book family, no
information barrier to enforce).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

ISOLATION_ENV = "EUROGAS_NEXUS_PORTFOLIO_ISOLATION"
SINGLE_BOOK_FIRM_ENV = "EUROGAS_NEXUS_SINGLE_BOOK_FIRM"
PREFIX = "BOOKS:"
_OFF = {"0", "false", "no", "off"}
_ON = {"1", "true", "yes", "on"}


class BookScopeViolation(PermissionError):
    """A write into a book the caller's scope does not include (403 ``book_outside_scope``)."""

    def __init__(self, table: str, book_id: str) -> None:
        super().__init__(f"{table}: book {book_id!r} is outside your book scope")
        self.table = table
        self.book_id = book_id


@dataclass(frozen=True)
class BookScope:
    """The books a caller may see."""

    all_books: bool = False
    entities: frozenset[str] = field(default_factory=frozenset)
    regions: frozenset[str] = field(default_factory=frozenset)
    books: frozenset[str] = field(default_factory=frozenset)

    def allows(self, book_id: str | None, legal_entity: str | None, region: str | None) -> bool:
        if self.all_books:
            return True
        if not book_id:
            return False  # positions outside any book are head-office only
        return (
            book_id.upper() in self.books
            or (legal_entity or "").upper() in self.entities
            or (region or "").upper() in self.regions
        )


UNRESTRICTED = BookScope(all_books=True)
#: The scope of a request whose caller is not identified yet: no book at all.
DENY_ALL = BookScope()
_current: ContextVar[BookScope | None] = ContextVar("eurogas_book_scope", default=None)
#: The identified caller of the request, for object rules that follow the author
#: (a decision case or an analysis snapshot is always visible to the person who made it).
_current_principal: ContextVar[tuple[str, ...]] = ContextVar(
    "eurogas_scope_principal", default=()
)


def isolation_enabled(environ: dict[str, str] | None = None) -> bool:
    """On unless the deployment says ``EUROGAS_NEXUS_PORTFOLIO_ISOLATION=false``."""

    env = os.environ if environ is None else environ
    return str(env.get(ISOLATION_ENV, "")).strip().lower() not in _OFF


def assert_isolation_setting_allowed(
    environment: str, environ: dict[str, str] | None = None
) -> None:
    """Refuse to start a trial or release deployment with isolation off, unless declared.

    Raises:
        RuntimeError: isolation is off in a trial/release environment without
            ``EUROGAS_NEXUS_SINGLE_BOOK_FIRM=true``.
    """

    env = os.environ if environ is None else environ
    if isolation_enabled(env):
        return
    if str(environment or "").strip().lower() not in {"trial", "release"}:
        return
    if str(env.get(SINGLE_BOOK_FIRM_ENV, "")).strip().lower() in _ON:
        return
    raise RuntimeError(
        f"{ISOLATION_ENV}=false is refused in a {environment!r} environment: book isolation "
        f"keeps one office or legal entity from reading another's positions. Turn it back on, "
        f"or declare {SINGLE_BOOK_FIRM_ENV}=true if this installation serves one office only."
    )


def scope_from_data_scopes(data_scopes: tuple[str, ...] | list[str]) -> BookScope:
    """Parse ``BOOKS:`` entries (case-insensitive) into a scope."""

    entities, regions, books = set(), set(), set()
    for raw in data_scopes or ():
        value = str(raw).strip().upper()
        if value == "*" or value == f"{PREFIX}*":
            return UNRESTRICTED
        if not value.startswith(PREFIX):
            continue
        kind, _, target = value[len(PREFIX) :].partition(":")
        if not target:
            continue
        {"ENTITY": entities, "REGION": regions, "BOOK": books}.get(kind, set()).add(target)
    return BookScope(False, frozenset(entities), frozenset(regions), frozenset(books))


def set_request_scope(
    data_scopes: tuple[str, ...] | list[str] | None, *identifiers: str | None
) -> None:
    """Called by the identity dependency for every request with a principal.

    ``identifiers`` are the caller's principal id and name: authored objects (decision cases,
    analysis snapshots) record one or the other.
    """

    _current.set(scope_from_data_scopes(data_scopes or ()) if isolation_enabled() else None)
    _current_principal.set(tuple(value for value in identifiers if value))


def deny_request_scope() -> None:
    """Start of a request: no book is visible until the caller is identified (fail closed)."""

    _current.set(DENY_ALL if isolation_enabled() else None)
    _current_principal.set(())


def current_principal_ids() -> tuple[str, ...]:
    """The identified caller of the current request (principal id and name), if any."""

    return _current_principal.get()


def current_scope() -> BookScope | None:
    """The caller's scope, or ``None`` when isolation is off or outside a request."""

    return _current.get()


@contextmanager
def firm_wide_scope() -> Iterator[None]:
    """Run a firm-wide calculation inside a request as a worker would: every book.

    A firm-wide evaluation stores results for every book and each reader is filtered when
    reading, so the person who asked for a fresh run must not narrow what is stored. The
    previous scope is restored on exit.
    """

    token = _current.set(None)
    try:
        yield
    finally:
        _current.reset(token)


_REQUEST_SCOPE = object()


def scope_for_principal(data_scopes: tuple[str, ...] | list[str] | None) -> BookScope | None:
    """The scope of an explicit principal (a long-lived stream, a worker); ``None`` = all."""

    return scope_from_data_scopes(data_scopes or ()) if isolation_enabled() else None


def visible_book_ids(session, scope: object = _REQUEST_SCOPE) -> set[str] | None:
    """Book ids the caller may see; ``None`` means unrestricted.

    ``scope`` defaults to the current request's; a stream that outlives the request passes
    the scope it re-derives from the principal.
    """

    if scope is _REQUEST_SCOPE:
        scope = current_scope()
    if scope is None or scope.all_books:
        return None
    from eurogas_nexus.db.models import TradingBookRecord

    return {
        row.book_id
        for row in session.query(
            TradingBookRecord.book_id, TradingBookRecord.legal_entity, TradingBookRecord.region
        ).all()
        if scope.allows(row.book_id, row.legal_entity, row.region)
    }


def restrict(query, model, session):
    """Limit a query on a table with ``book_id`` (or the books table) to visible books."""

    allowed = visible_book_ids(session)
    if allowed is None:
        return query
    return query.filter(model.book_id.in_(sorted(allowed)))


def firm_level_visible() -> bool:
    """Whether firm-level figures with no book (P&L snapshots) may be shown."""

    scope = current_scope()
    return scope is None or scope.all_books
