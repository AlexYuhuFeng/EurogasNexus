"""Frozen functional analysis inputs/results and versioned research model adoption."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class FunctionalRunRecord(Base):
    __tablename__ = "functional_runs"
    __table_args__ = (
        UniqueConstraint("owner_id", "idempotency_key", name="uq_functional_owner_key"),
    )

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("identity_principals.principal_id"), index=True
    )
    job_id: Mapped[str] = mapped_column(String(64), ForeignKey("job_records.job_id"), unique=True)
    kind: Mapped[str] = mapped_column(String(32))
    idempotency_key: Mapped[str] = mapped_column(String(80))
    request_hash: Mapped[str] = mapped_column(String(64))
    manifest: Mapped[dict] = mapped_column(JSON)
    inputs: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_scopes: Mapped[list] = mapped_column(JSON, default=list)
    deadline_seconds: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FunctionalModelRecord(Base):
    __tablename__ = "functional_models"
    __table_args__ = (
        UniqueConstraint("owner_id", "target", "version_hash", name="uq_functional_model_version"),
    )

    model_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String(80), ForeignKey("identity_principals.principal_id"), index=True
    )
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("functional_runs.run_id"))
    target: Mapped[str] = mapped_column(String(80))
    version_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    review: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FunctionalDependencyRecord(Base):
    __tablename__ = "functional_dependencies"
    run_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("functional_runs.run_id"), primary_key=True
    )
    reference: Mapped[str] = mapped_column(String(256), primary_key=True, index=True)
    version_hash: Mapped[str] = mapped_column(String(128))
    latest_hash: Mapped[str] = mapped_column(String(128))
    stale: Mapped[bool] = mapped_column(Boolean, default=False)
