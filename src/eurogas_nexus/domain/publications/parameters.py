"""A publisher's published operating figure, fetched rather than typed (owner, 2026-11-28).

Terminal fuel and boil-off loss rates, regasification tariffs, entry and exit capacity tariffs,
imbalance and scheduling charges, exchange and clearing fees: each is a named figure a
publisher states for a period, in a document, on a page or in a table. This is the record such
a publication's parser returns; a watched publication of kind ``published_parameters``
(``registry.KINDS``) carries it, under the same terms or written-consent rule as every other
publication (``registry.fetch_refusal``, ``consents``). No parser of this kind exists yet.

Import-safe: no database, web or network import.

发布方公布的运营参数（燃料与蒸发损耗率、再气化费率、出入口容量费率、不平衡与调度费用、交易所与清算费用）的记录格式。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class PublishedParameter:
    """One figure as its publisher states it, with where it was read and when."""

    #: Stable id within its publication (``zeebrugge:fuel-loss-pct``).
    key: str
    name: str
    value: str
    unit: str
    valid_from: date | None
    valid_to: date | None
    #: The document the figure is in, and where in it (a page, a table, a cell).
    document_url: str
    location: str
    publisher: str
    publication_id: str
    #: The publisher's own date for the document, when it states one; and our read.
    published_at_utc: datetime | None
    fetched_at_utc: datetime
    #: The consent record it was fetched under, when the site's terms alone do not allow it.
    consent_publisher: str | None = None
    #: What the figure applies to (a terminal, a point, a contract), as the publisher names it.
    applies_to: str = ""

    def to_json(self) -> dict:
        return {
            "key": self.key, "name": self.name, "value": self.value, "unit": self.unit,
            "valid_from": self.valid_from.isoformat() if self.valid_from else None,
            "valid_to": self.valid_to.isoformat() if self.valid_to else None,
            "document_url": self.document_url, "location": self.location,
            "publisher": self.publisher, "publication_id": self.publication_id,
            "published_at_utc": self.published_at_utc.isoformat()
            if self.published_at_utc else None,
            "fetched_at_utc": self.fetched_at_utc.isoformat(),
            "consent_publisher": self.consent_publisher, "applies_to": self.applies_to,
        }


__all__ = ["PublishedParameter"]
