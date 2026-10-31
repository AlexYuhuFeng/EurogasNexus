"""Which books a person may see: head office everything, a regional office only its own.

With ``EUROGAS_NEXUS_PORTFOLIO_ISOLATION=true`` every read of contracts, trades and books is
restricted to the books the caller's data scopes name:

- ``BOOKS:*``                    every book, and positions not yet in a book (head office)
- ``BOOKS:ENTITY:<legal entity>`` books of that legal entity (for example EGN-UK)
- ``BOOKS:REGION:<region>``       books of that region (europe, north_america, asia)
- ``BOOKS:BOOK:<book id>``        one book

``*`` (service accounts) sees everything. A person with no ``BOOKS:`` scope sees no
positions. Scopes come from the administrator or from SSO groups through
``EUROGAS_NEXUS_OIDC_GROUPS_SCOPE_MAP``, so a regional head's access follows the directory.

The scope is set once per request by the identity dependency and applied by
:func:`restrict` wherever a query touches a book-bearing table, so a new read path cannot
forget it as long as it goes through the helper. With isolation off (the default for a
single-office installation) every caller sees every book, as before.
"""

from __future__ import annotations

import os
from contextvars import ContextVar
from dataclasses import dataclass, field

ISOLATION_ENV = "EUROGAS_NEXUS_PORTFOLIO_ISOLATION"
PREFIX = "BOOKS:"


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
_current: ContextVar[BookScope | None] = ContextVar("eurogas_book_scope", default=None)


def isolation_enabled(environ: dict[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return str(env.get(ISOLATION_ENV, "")).strip().lower() in {"1", "true", "yes", "on"}


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


def set_request_scope(data_scopes: tuple[str, ...] | list[str] | None) -> None:
    """Called by the identity dependency for every request with a principal."""

    _current.set(scope_from_data_scopes(data_scopes or ()) if isolation_enabled() else None)


def current_scope() -> BookScope | None:
    """The caller's scope, or ``None`` when isolation is off or outside a request."""

    return _current.get()


def visible_book_ids(session) -> set[str] | None:
    """Book ids the caller may see; ``None`` means unrestricted."""

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
