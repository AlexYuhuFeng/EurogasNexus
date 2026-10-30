"""Market-data licence register (one row per vendor contract or licence schedule)."""

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from eurogas_nexus.db.base import Base


class MarketDataLicenceRecord(Base):
    __tablename__ = "market_data_licences"

    licence_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    vendor: Mapped[str] = mapped_column(String(64), nullable=False)
    source_family: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    licence_type: Mapped[str] = mapped_column(String(16), nullable=False)
    licensed_use: Mapped[str] = mapped_column(String(32), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    offices: Mapped[list | None] = mapped_column(JSON, nullable=True)
    seats: Mapped[int | None] = mapped_column(Integer, nullable=True)
    contract_reference: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_by: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
