"""Per-user preferences and organisation defaults (see domain/settings/preferences.py)."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class PrincipalPreferenceRecord(Base):
    """One row per identity principal: the choices that person made."""

    __tablename__ = "principal_preferences"

    principal_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    preferences_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OrganisationSettingRecord(Base):
    """Organisation-wide defaults, one row per setting, with who changed it last."""

    __tablename__ = "organisation_settings"

    setting_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_json: Mapped[object] = mapped_column(JSON, nullable=False)
    updated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
