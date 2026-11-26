"""Raw payload archive model (raw -> canonical lineage)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class RawPayloadArchiveRecord(Base):
    """Immutable raw provider payload kept for lineage and replay.

    Normalized rows carry ``source_reference`` values that resolve to these
    archives, so the raw -> canonical transformation is auditable (Gate 4).
    """

    __tablename__ = "raw_payload_archives"

    archive_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset: Mapped[str] = mapped_column(String(64), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(256), nullable=False)
    payload_text: Mapped[str | None] = mapped_column(Text(), nullable=True)
    # ``none_as_null``: a receipt without a page holds SQL NULL, not the JSON value ``null``
    # (the default would make "no inline page" indistinguishable to ``IS NULL``).
    payload_json: Mapped[dict | None] = mapped_column(JSON(none_as_null=True), nullable=True)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    record_count: Mapped[int] = mapped_column(Integer, nullable=False)
    received_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    research_only: Mapped[bool] = mapped_column(Boolean, nullable=False)
    human_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False)


class RawPayloadContentRecord(Base):
    """One distinct raw page, stored once, keyed by the SHA-256 of its exact bytes.

    A fetch writes a small receipt to ``raw_payload_archives`` (what was asked, when it was
    received, the digest) and the page itself here only if this digest is new. Before
    migration ``0096_retention_by_class`` every fetch stored the whole page again, as text and
    as parsed JSON, which made the archive about 91 % of the database's growth.

    ``payload_compressed`` holds the gzip of the exact bytes while the page is hot; after the
    retention job offloads it, the bytes live in object storage under ``object_key`` (verified
    against ``payload_sha256`` before the hot copy is cleared) and ``stored_in`` says so.
    """

    __tablename__ = "raw_payload_contents"
    __table_args__ = (
        Index("ix_raw_payload_contents_offload", "stored_in", "last_received_at_utc"),
    )

    payload_sha256: Mapped[str] = mapped_column(String(64), primary_key=True)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    compression: Mapped[str] = mapped_column(String(16), nullable=False)
    payload_compressed: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    stored_in: Mapped[str] = mapped_column(String(16), nullable=False)
    object_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    first_received_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_received_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    offloaded_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
