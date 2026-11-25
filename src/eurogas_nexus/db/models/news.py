"""News items and source poll state (NEWS-1, migration 0084, ADR Decision 35).

``news_items`` holds one row per item a registered source published (a feed entry, or a REMIT
message the platform already holds): where it came from (source, publisher, link), when it was
published and retrieved, its language, the licence note it is kept under, what was kept of it
(title, and the feed's own summary only where the source's terms allow), the SHA-256 of that
content, and its deterministic tags. ``item_id`` is derived from the source and the entry's own
identifier, so polling the same feed again is idempotent; a changed entry is the next
``revision``. ``linked_event_key`` names the market event subject an item maps to (a REMIT
outage, ``outage:<message id>``), so opportunities re-evaluate on it.

``news_source_polls`` holds, per source, when it was last polled and how that went, so the
poller keeps each source's interval and the registry shows its state.

新闻条目与来源轮询状态：来源、链接、发布与抓取时间、内容哈希、语言、许可说明与确定性标注。
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class NewsItemRecord(Base):
    """One news, policy or event item from one registered source."""

    __tablename__ = "news_items"
    __table_args__ = (
        Index("ix_news_items_published", "published_at_utc"),
        Index("ix_news_items_source", "source_id"),
        Index("ix_news_items_linked_event", "linked_event_key"),
    )

    item_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(48), nullable=False)
    #: The entry's own identifier in its source (feed guid, REMIT message id).
    source_ref: Mapped[str] = mapped_column(String(400), nullable=False)
    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    publisher: Mapped[str] = mapped_column(String(200), nullable=False)
    title: Mapped[str] = mapped_column(String(400), nullable=False)
    #: The source's own summary, kept only where its terms allow (else empty).
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    language: Mapped[str] = mapped_column(String(8), nullable=False)
    published_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retrieved_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    licence_note: Mapped[str] = mapped_column(String(300), nullable=False)
    event_types: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    entities: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    hubs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    countries: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    capacity_change: Mapped[bool] = mapped_column(nullable=False, default=False)
    linked_event_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_seen_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class NewsSourcePollRecord(Base):
    """When one source was last polled, and what came of it."""

    __tablename__ = "news_source_polls"

    source_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    last_polled_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_success_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: ``ok``, ``not_modified``, ``robots_disallowed``, ``refused``, ``failed``.
    last_status: Mapped[str] = mapped_column(String(24), nullable=False)
    last_detail: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    feed_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    items_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_changed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    etag: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String(64), nullable=True)
