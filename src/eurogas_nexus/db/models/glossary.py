"""Glossary persistence models."""

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class GlossaryTermRecord(Base):
    __tablename__ = "glossary_terms"

    term_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    term: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    definition_en: Mapped[str] = mapped_column(Text(), nullable=False)
    definition_zh_cn: Mapped[str] = mapped_column(Text(), nullable=False)
    aliases: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    related_terms: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    source_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
