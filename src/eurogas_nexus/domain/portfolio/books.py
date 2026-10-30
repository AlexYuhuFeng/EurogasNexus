"""Trading books and the organisation they roll up into.

Positions are held in books; books belong to a business (desk) in a region of a legal
entity. Head office reads the whole firm, a regional head a region, a desk head a
business, a trader a book, each in one reporting currency. The levels mirror an ETRM's
portfolio hierarchy, so the same position can be read at any level without copying it.

Example: legal entity ``EGN-UK``, region ``europe``, business ``NW Europe gas``, book
``NBP-TTF spreads``; a Canada desk adds legal entity ``EGN-CA``, region
``north_america``, business ``Alberta gas and power``, books ``AECO physical`` and
``AESO power``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

#: Roll-up levels from the whole firm down to a single book.
LEVELS = ("firm", "legal_entity", "region", "business", "book")
UNASSIGNED = "UNASSIGNED"


@dataclass(frozen=True)
class Book:
    book_id: str
    name: str
    legal_entity: str
    region: str
    business: str
    base_currency: str = "EUR"
    commodities: tuple[str, ...] = ()
    active: bool = True

    def key(self, level: str) -> str:
        """The group this book belongs to at ``level``."""

        if level == "firm":
            return "FIRM"
        if level == "book":
            return self.book_id
        return str(getattr(self, level))


def unassigned_book() -> Book:
    return Book(UNASSIGNED, "Unassigned", UNASSIGNED, UNASSIGNED, UNASSIGNED)


def group_key(book_id: str, books: Mapping[str, Book], level: str) -> str:
    """Group of a position's book at ``level``; positions without a known book are UNASSIGNED."""

    if level not in LEVELS:
        raise ValueError(f"level must be one of {LEVELS}")
    return books.get(book_id or UNASSIGNED, unassigned_book()).key(level)


def hierarchy(books: Iterable[Book]) -> dict[str, dict[str, dict[str, list[str]]]]:
    """legal entity -> region -> business -> book ids, for navigation and reporting."""

    tree: dict[str, dict[str, dict[str, list[str]]]] = {}
    for book in sorted(books, key=lambda b: (b.legal_entity, b.region, b.business, b.book_id)):
        tree.setdefault(book.legal_entity, {}).setdefault(book.region, {}).setdefault(
            book.business, []
        ).append(book.book_id)
    return tree
