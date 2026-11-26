"""Retention by data class: policy overrides, archive manifests and run records.

The classes, their floors and their default actions are code
(:mod:`eurogas_nexus.application.retention`); this table holds only what an operator raised.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class RetentionPolicyRecord(Base):
    """An operator's setting for one data class (raised above the floor, never below it)."""

    __tablename__ = "retention_policies"
    __table_args__ = (
        CheckConstraint("hot_days IS NULL OR hot_days >= 0", name="ck_retention_hot_days"),
    )

    data_class: Mapped[str] = mapped_column(String(64), primary_key=True)
    hot_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(Text(), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RetentionArchiveRecord(Base):
    """One verified archive file in object storage and the rows it holds.

    Written only after the file was read back and its digest matched; rows are removed from
    the hot store only after this record exists. ``status`` becomes ``restored`` when an
    operator loads the range back.
    """

    __tablename__ = "retention_archives"
    __table_args__ = (
        # One record per archive object: a day's file has a fixed key, so a day is archived
        # once; a raw-page batch's key is its manifest, named by run.
        UniqueConstraint("object_key", name="uq_retention_archive_object"),
        Index("ix_retention_archives_class_range", "data_class", "range_start_utc"),
    )

    archive_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    data_class: Mapped[str] = mapped_column(String(64), nullable=False)
    table_name: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    range_start_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    range_end_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    object_store: Mapped[str] = mapped_column(String(256), nullable=False)
    object_key: Mapped[str] = mapped_column(String(512), nullable=False)
    manifest_key: Mapped[str] = mapped_column(String(512), nullable=False)
    row_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rows_removed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    verified_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    restored_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class RetentionRunRecord(Base):
    """One pass of the retention job (scheduled or by hand), dry-run or enforced."""

    __tablename__ = "retention_runs"
    __table_args__ = (Index("ix_retention_runs_started", "started_at_utc"),)

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    principal: Mapped[str] = mapped_column(String(128), nullable=False)
    started_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
