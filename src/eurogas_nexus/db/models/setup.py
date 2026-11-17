"""The first-run setup flow's state, one row per installation (migration 0066)."""

from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class InstallationSetupRecord(Base):
    """Where the first administrator's welcome flow stands (never a key: those are encrypted
    in ``provider_credentials``)."""

    __tablename__ = "installation_setup"
    __table_args__ = (
        CheckConstraint(
            "status IN ('not_started', 'in_progress', 'completed', 'dismissed')",
            name="ck_installation_setup_status",
        ),
    )

    setup_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    current_step: Mapped[str | None] = mapped_column(String(32), nullable=True)
    steps_visited: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    configured_by: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
