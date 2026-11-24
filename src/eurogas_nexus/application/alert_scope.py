"""Which monitoring alerts a caller may see.

Most alerts are about the market (outages, spreads, feeds) and every user sees them. Two
kinds are narrower:

- A limits alert (credit, mandate) names a counterparty's or a trader's position, and a
  delivery-shortfall alert a contract's book, so with portfolio isolation on each is shown
  only to callers who can see every book behind it. With isolation off, or for head office
  (``BOOKS:*``), every such alert is visible.
- A market alert built from a price (the price-move alert, gap G3 of the role-first redesign)
  carries a licensed figure, so it is shown only to callers entitled to the source family of
  that price (the row entitlement every price read applies). Public and demo families are
  visible to every caller; outside a request with no principal, a licensed one is hidden.
- An opportunity alert (M7) is shown by the opportunity's own rule (``opportunities.listing.
  visible_to``): every source family behind it must be one the caller may read, and unless it
  is a market item (lane ``market``) every book behind it must be one the caller can see.
"""

from __future__ import annotations

from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

#: Alert categories that carry book-level figures.
BOOK_SCOPED_CATEGORIES = frozenset({"limits", "delivery"})
#: Alert categories that carry a price and name its source system in the evidence.
SOURCE_SCOPED_CATEGORIES = frozenset({"market", "fundamentals"})
#: Alerts about one opportunity of the opportunity engine.
OPPORTUNITY_CATEGORY = "opportunity"

_request_principal: ContextVar[Any] = ContextVar("eurogas_alert_principal", default=None)
_UNSET = object()


def set_request_principal(principal: Any) -> None:
    """Called by the identity dependency for every request (``None`` without a principal)."""

    _request_principal.set(principal)


def _source_allowed(principal: Any, source_system: str) -> bool:
    from eurogas_nexus.security.identity import (
        AuthenticatedPrincipal,
        principal_allows_source_family,
    )

    if principal is not None and getattr(principal, "auth_method", "") == "legacy_public_token":
        return True
    if principal is None:
        # Fail closed: only public and demo families, as a principal with no grant sees them.
        principal = AuthenticatedPrincipal(
            principal_id="", name="", principal_type="USER", role="VIEWER", status="ACTIVE",
            data_scopes=(),
        )
    return principal_allows_source_family(principal, source_system)


def alert_visibility(session, *, principal: Any = _UNSET, **scope: Any) -> Callable[[Any], bool]:
    """A predicate over alert rows (records or payload dicts) for the current caller.

    Pass ``scope=<BookScope or None>`` and ``principal=`` to decide for an explicit principal
    instead of the current request (the alert stream does, on every poll).
    """

    from eurogas_nexus.security.portfolio_scope import visible_book_ids

    allowed = visible_book_ids(session, **scope)
    reader = _request_principal.get() if principal is _UNSET else principal

    def visible(row: Any) -> bool:
        get = row.get if isinstance(row, dict) else lambda key: getattr(row, key, None)
        category = get("category")
        if category == OPPORTUNITY_CATEGORY:
            evidence = get("evidence_snapshot") or {}
            if not all(
                _source_allowed(reader, str(family))
                for family in evidence.get("source_families") or []
            ):
                return False
            if allowed is None or evidence.get("lane") == "market":
                return True
            books = evidence.get("book_ids") or []
            return bool(books) and all(book in allowed for book in books)
        if category in SOURCE_SCOPED_CATEGORIES:
            source = (get("evidence_snapshot") or {}).get("source_system")
            if source and not _source_allowed(reader, str(source)):
                return False
        if allowed is None or category not in BOOK_SCOPED_CATEGORIES:
            return True
        books = (get("evidence_snapshot") or {}).get("book_ids") or []
        return bool(books) and all(book in allowed for book in books)

    return visible
