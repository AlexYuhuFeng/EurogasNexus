"""Which monitoring alerts a caller may see.

Most alerts are about the market (outages, spreads, feeds) and every user sees them. A
limits alert (credit, mandate) names a counterparty's or a trader's position, so with
portfolio isolation on it is shown only to callers who can see every book behind it. With
isolation off, or for head office (``BOOKS:*``), every alert is visible.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

#: Alert categories that carry book-level figures.
BOOK_SCOPED_CATEGORIES = frozenset({"limits"})


def alert_visibility(session, **scope: Any) -> Callable[[Any], bool]:
    """A predicate over alert rows (records or payload dicts) for the current caller.

    Pass ``scope=<BookScope or None>`` to decide for an explicit principal instead of the
    current request (the alert stream does, on every poll).
    """

    from eurogas_nexus.security.portfolio_scope import visible_book_ids

    allowed = visible_book_ids(session, **scope)
    if allowed is None:
        return lambda _row: True

    def visible(row: Any) -> bool:
        get = row.get if isinstance(row, dict) else lambda key: getattr(row, key, None)
        if get("category") not in BOOK_SCOPED_CATEGORIES:
            return True
        books = (get("evidence_snapshot") or {}).get("book_ids") or []
        return bool(books) and all(book in allowed for book in books)

    return visible
