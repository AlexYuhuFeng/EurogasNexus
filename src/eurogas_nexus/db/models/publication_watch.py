"""What the product last found at each watched publication (``domain/publications``).

One row per publication: when it was last checked, fetched and changed, the SHA-256 of the
document it holds, the state the desk sees, the record parsed from the document and the one
before it. The document itself is kept once by its digest in ``raw_payload_contents`` where the
terms allow storing it.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base

#: ``current``: the record matches the document last fetched. ``needs_confirmation``: the
#: document changed and could not be read with confidence; the previous record stays.
#: ``unreachable``: the last check failed. ``never_fetched``: allowed, nothing held yet.
#: ``hand_maintained`` and ``link_only``: not fetched (the registry's terms verdict).
WATCH_STATES = (
    "current",
    "needs_confirmation",
    "unreachable",
    "never_fetched",
    "hand_maintained",
    "link_only",
)


class WatchedPublicationRecord(Base):
    """The product's state of one watched publication."""

    __tablename__ = "watched_publications"
    __table_args__ = (
        CheckConstraint(
            "state IN ('current', 'needs_confirmation', 'unreachable', 'never_fetched', "
            "'hand_maintained', 'link_only')",
            name="ck_watched_publications_state",
        ),
    )

    publication_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    detail: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    last_checked_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: The last time the document was read successfully (whether or not it had changed).
    last_fetched_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: When the document last differed from the one held.
    last_changed_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    document_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    #: The digest of the document the record was parsed from.
    content_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    #: A changed document that could not be read with confidence (state needs_confirmation).
    pending_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pending_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    pending_since_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: The parsed record, as the parser's ``to_json``, with when it was published and fetched.
    record: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    record_fetched_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: The record before the last change, kept so the desk can see what moved.
    previous_record: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    previous_fetched_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: A person who confirmed a changed document by hand, and when.
    confirmed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    confirmed_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    etag: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_modified: Mapped[str | None] = mapped_column(String(64), nullable=True)
