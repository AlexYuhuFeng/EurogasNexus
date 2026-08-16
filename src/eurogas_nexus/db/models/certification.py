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
        UniqueConstraint("source_system", name="uq_provider_certifications_source_system"),
    )

    certification_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_system: Mapped[str] = mapped_column(String(64), nullable=False)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    checks: Mapped[list] = mapped_column(JSON, nullable=False)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False)
    evaluated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    evaluated_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
