"""Provider certification model for the simulated-to-live gate."""

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class ProviderCertificationRecord(Base):
    """Operator-recorded certification evidence for a licensed source system.

    A licensed (non-simulated) provider may only be treated as native live when
    a certification row exists with stage ``live_validated`` and the required
    checks. Absence of a row means ``unverified`` (fail closed).
    """

    __tablename__ = "provider_certifications"
    __table_args__ = (
        UniqueConstraint(
            "source_system",
            "dataset",
            "environment",
            name="uq_provider_certifications_scope",
        ),
    )

    certification_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset: Mapped[str] = mapped_column(String(128), nullable=False, default="", server_default="")
    environment: Mapped[str] = mapped_column(
        String(32), nullable=False, default="deployment", server_default="deployment"
    )
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    checks: Mapped[list] = mapped_column(JSON, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    evaluated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    evaluated_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    adapter_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    credential_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    entitlement_scope: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sample_period_start_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sample_period_end_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    tests_performed: Mapped[list | None] = mapped_column(JSON, nullable=True)
    expires_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    evidence_ref: Mapped[str | None] = mapped_column(String(256), nullable=True)
